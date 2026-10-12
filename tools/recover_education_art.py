#!/usr/bin/env python3
"""Recover unchanged original German source files and extraction candidates.

No production catalog mutations. Use cached IA manifests to select full scan OCR
and original DOC, keep SHA256 provenance, and require reviewed scope before import.
"""
from __future__ import annotations
import concurrent.futures, hashlib, json, re, shutil, subprocess, time, urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research/unavailable-recovery/education-art'
NUMBERS=['281','282','283','284','286','287','289','291','291a','292','293','294','295','296','297','297a','298','299','300a','300b','300c']
# Source-member scopes reviewed against body authorship, source TOC, and end
# headings. These select Steiner's text, excluding named other authors/apparatus.
SCOPES={
 '281': {'start':10,'end':246,'exclude':[58,162], 'expected_sections':14,
         'evidence':'Steiner lectures/addresses; Marie Steiner Niedergang und Aufbau (content58) and 1928 seminar (content162) excluded; Nachwort begins content247.'},
 '282': {'start':14,'end':386,'exclude':[36],'expected_sections':20,'evidence':'10 April 1921 question session and 19 September1924 dramatic-course lectures; preparatory language course (content36) and content387 foreword both explicitly Marie Steiner, excluded.'},
 '283': {'start':12,'end':149,'expected_sections':12,'evidence':'Four 1906 lectures, 1920 question sessions and two concluding remarks, three March 1923 lectures; publisher Hinweise begins content150.'},
 '286': {'start':26,'end':233,'trim_before':'DER URSPRUNG DER ARCHITEKTUR\nAUS DEM SEELISCHEN DES MENSCHEN',
         'evidence':'Eight lectures (12 December 1911 through 26 July 1914), two 1914 appendix notes and reconstruction writings; 1945 Marie foreword trimmed inside content26; publisher Hinweise begins content234.'},
 '291': {'start':4,'end':15,'expected_sections':12,'evidence':'Three May 1921 color lectures + nine supplementary lectures; three publisher/Marie introductions removed and Hinweise begins content16.'},
 '293': {'start':18,'end':219,'expected_sections':15,'evidence':'Fourteen lectures 21 August through 5 September 1919 + 20 August 1919 address. Marie introduction content10 excluded; apparatus begins content220.'},
 '294': {'start':8,'end':196,'expected_sections':15,'editorial_suffix':'Damit schließen die Allsführungen Rudolf Steiners am 5. September 1919.', 'evidence':'Fourteen lectures 21 August through 5 September 1919 + 6 September 1919 closing remarks; publisher transition after14thlecture trimmed and Hinweise begins content197.'},
 '295': {'start':10,'end':187,'expected_sections':17,'evidence':'Fifteen seminar sessions and three curriculum lectures (last session combined with third lecture); Bemerkungen zur ersten Buchausgabe begins content188.'},
 '296': {'start':10,'end':117,'expected_sections':6,'evidence':'All six lectures 9,10,11,15,16,17 August 1919; Hinweise begins content118.'},
 '297': {'start':16,'end':278,'expected_sections':11,'evidence':'All ten original lectures + questions, 24 August 1919 through 29 December 1920. Newspaper report begins content279; notebook facsimile placeholder content287 excluded.'},
 '297a': {'start':14,'end':172,'expected_sections':8,'evidence':'Six original lectures/author report + two question sessions from 24 February 1921 through 4 April 1924. Appendix newspaper report starts content173.'},
 '298': {'start':10,'end':221,'exclude':[19],'expected_sections':23,'evidence':'1919 essay plus Steiner school addresses September 1919 through June 1924. Emil Molt opening speech content19 removed; Hinweise starts content222.'},
 '299': {'start':10,'end':85,'expected_sections':6,'evidence':'All six lectures 26 December 1919 through 3 January 1920; Hinweise begins content86.'},
 '300a': {'start':62,'end':290,'expected_sections':15,'evidence':'20 August 1919 address, school-start directions, 13 conference headings through 26 May 1921. Editorial foreword/introductions before content62 and chronology/notes from content291 excluded.'},
 '300b': {'start':10,'end':307,'expected_sections':6,'evidence':'Original Waldorf essay followed by conferences June 1921 through March 1923, including bare-body inline conference headings. Editorial chronology/notes starts content308.'},
 '300c': {'start':10,'end':195,'expected_sections':5,'evidence':'Original pedagogical essay followed by conferences March 1923 through September 1924, including inline conference headings. Editorial chronology/notes/index starts content196.'},
}

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def fetch(url,path,expected_size=None):
    if path.exists() and (expected_size is None or path.stat().st_size==int(expected_size)): return
    path.parent.mkdir(parents=True,exist_ok=True)
    error=None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'GA source recovery (local research)'}),timeout=45) as response:
                data=response.read()
            if expected_size is not None and len(data)!=int(expected_size): raise ValueError(f'Size mismatch: {len(data)} != {expected_size}')
            path.write_bytes(data);return
        except Exception as exc:
            error=exc;time.sleep(attempt+1)
    raise RuntimeError(f'{url}: {error}')

def norm(text):
    text=text.replace('\u00ad','')
    text=re.sub(r'(?m)^Copyright Rudolf Steiner Nachlass-Verwaltung.*$','',text)
    text=re.sub(r'(?m)^Buch:\s*\d+.*?Seite:\s*\d+.*$','',text)
    return re.sub(r'\n{3,}','\n\n',text).strip()

def extract_xml(path):
    root=ET.parse(path).getroot();pages=[]
    for i,obj in enumerate(root.findall('.//OBJECT')):
        lines=[' '.join((w.text or '') for w in line.findall('.//WORD')) for line in obj.findall('.//LINE')]
        text=norm('\n'.join(lines))
        pages.append({'scan_index':i,'text':text,'chars':len(text)})
    return pages

def body_text(element):
    """Keep text AND tail nodes, including naked continuation text after p."""
    out=[]
    def walk(node):
        tag=node.tag.rsplit('}',1)[-1]
        if tag in {'h1','h2','h3','h4'}: return
        if tag in {'p','div','li','blockquote','table','tr'}:out.append('\n\n')
        if tag=='br':out.append('\n')
        if node.text:out.append(node.text)
        for child in node:
            walk(child)
            if child.tail:out.append(child.tail)
        if tag in {'p','div','li','blockquote','table','tr'}:out.append('\n\n')
    walk(element)
    return ''.join(out)

def clean_epub_body(value):
    # Delete generated first source title only; keep titles later within members.
    value=re.sub(r'^\s*#G[^\n]*\n\s*#TI.*?#TX\s*','',value, count=1, flags=re.S)
    value=re.sub(r'(?m)^\s*#G[^\n]*$','',value)
    value=re.sub(r'#SE\d[^\s]*','',value)
    value=re.sub(r'#(?:TI|TX|BI|LI|IR|HY|MU)\b','',value)
    value=re.sub(r'(?m)^\s*#Bild[^\n]*$','',value)
    value=value.replace('\u00ad','').replace('\u00a0',' ').replace('\u0096','–')
    value='\n'.join(re.sub(r'[ \t]+',' ',line).strip() for line in value.splitlines())
    return re.sub(r'\n{3,}','\n\n',value).strip()

def epub_candidates(report):
    for rec in report['records']:
        n=rec['ga_number'];folder=OUT/rec['work_id'];path=folder/f'GA{n}.epub'
        url=f'https://odysseetheater.org/GA/eBook/epub/GA{n}.epub'
        try:fetch(url,path)
        except Exception as exc:rec['epub_error']=str(exc);continue
        rec['source_files'].append({'url':url,'path':str(path.relative_to(ROOT)),'format':'EPUB','sha256':sha(path),'bytes':path.stat().st_size})
        rec['status']='source_recovered'
        rec['scope_reference_url']=f'https://anthrowiki.at/GA_{n}'
        scope=SCOPES.get(n)
        members=[];excluded=[];passages=[];full_epub=[]
        with ZipFile(path) as z:
            for member in sorted(z.namelist(), key=lambda x:int(re.search(r'content(\d+)',x)[1]) if re.search(r'content(\d+)',x) else 999999):
                mm=re.fullmatch(r'content(\d+)\.xhtml',member)
                if not mm:continue
                root=ET.fromstring(z.read(member));body=root.find('{*}body')
                title=' '.join(' '.join(''.join(h.itertext()).split()) for h in body if h.tag.rsplit('}',1)[-1] in ['h1','h2','h3'])
                raw=body_text(body)
                full_epub.append(title+'\n\n'+clean_epub_body(raw))
                source_pages=[int(x) for x in re.findall(r'#(?:G[^\s]*?-SE|SE[\da-z]+-)(\d{1,4})',raw)]
                members.append({'member':member,'title':title,'body_chars':len(raw),'sha256':hashlib.sha256(z.read(member)).hexdigest(),'bare_body_text_nodes':sum(bool(c.tail and c.tail.strip()) for c in body)})
                i=int(mm[1])
                if not scope or not(scope['start']<=i<=scope['end']) or i in scope.get('exclude',[]):
                    excluded.append({'member':member,'title':title});continue
                if i==scope['start'] and scope.get('trim_before'):
                    pos=raw.index(scope['trim_before']);raw=raw[pos:];title='DER URSPRUNG DER ARCHITEKTUR — Erster Vortrag, Berlin, 12. Dezember 1911'
                text=clean_epub_body(raw)
                if scope.get('editorial_suffix') and scope['editorial_suffix'] in text:
                    text=text.split(scope['editorial_suffix'],1)[0].rstrip()
                passages.append({'id':f'{rec["work_id"]}-source-{i:03d}','title':title,'source_label':'Rudolf Steiner Online Archiv / Odyssee-Theater EPUB','source_member':member,'text':text,'source_text':raw.strip(),'checksum':hashlib.sha256(text.encode()).hexdigest(),'ga_page':f'S. {min(source_pages)}–{max(source_pages)}' if source_pages else None,'metadata':{'page_numbers':list(dict.fromkeys(source_pages)),'page_marker_source':'original_source_macros','annotations':[]}})
        rec['epub_members']=members
        full_path=folder/'epub-full.txt';full_path.write_text('\n\n'.join(full_epub)+'\n')
        rec['epub_text_path']=str(full_path.relative_to(ROOT));rec['epub_text_sha256']=sha(full_path);rec['epub_full_chars']=sum(len(x) for x in full_epub);rec['epub_full_words']=sum(len(x.split()) for x in full_epub)
        if not scope:
            rec['import_ready']=False
            rec['concerns'].append({'284':'Mixed Steiner texts, Marie correspondence, Stockmeyer contributions and editor text: individual authorship boundaries need review.', '289':'1958 source contains one Bern lecture (29 June 1921) and Goethe essays, not the expanded 2017 GA289 with ten lectures. Partial relative to modern GA volume.', '291a':'Editorial introductions and texts by other authors interleaved with original Steiner excerpts; needs individual subsection scope review.', '292':'Thirteen original lectures present, but internal image lists and editor notes interleaved; heading-only exclusion is insufficient.'}.get(n,'Source scope unreviewed.'))
            continue
        if scope.get('expected_sections') and len(passages)!=scope['expected_sections']:
            rec['concerns'].append(f'Expected {scope["expected_sections"]} member sections but extracted {len(passages)}.')
        candidate=folder/'candidate-passages.json';candidate.write_text(json.dumps(passages,ensure_ascii=False,indent=2)+'\n')
        txt=folder/'candidate-text.txt';txt.write_text('\n\n'.join(p['title']+'\n\n'+p['text'] for p in passages)+'\n')
        rec['scope']=scope;rec['excluded_members']=excluded;rec['candidate_path']=str(candidate.relative_to(ROOT));rec['candidate_sha256']=sha(candidate);rec['candidate_text_path']=str(txt.relative_to(ROOT));rec['candidate_text_sha256']=sha(txt)
        rec['candidate_chars']=sum(len(p['text']) for p in passages);rec['candidate_words']=sum(len(p['text'].split()) for p in passages);rec['candidate_passage_count']=len(passages)
        rec['import_ready']=not any('Expected ' in x for x in rec['concerns'] if isinstance(x,str))
        rec['scope_completeness']='All original typed Steiner text in the recovered source edition; publisher and named other-author sections excluded. Supporting visual facsimiles not reproduced.'
        rec['concerns'].append('Working text contains source spelling/OCR errors and inline source references; no word-level facsimile proofread. Bare text/tail nodes preserved.')
        rec['body_start_evidence']=passages[0]['text'][:240];rec['body_end_evidence']=passages[-1]['text'][-240:]

def pdf_candidate_287(report):
    rec=next(r for r in report['records'] if r['ga_number']=='287')
    folder=OUT/'ga-287';path=folder/'GA_287.pdf';url='https://odysseetheater.org/GA/Buecher/GA_287.pdf'
    fetch(url,path)
    rec['source_files'].append({'url':url,'path':str(path.relative_to(ROOT)),'format':'Text PDF','sha256':sha(path),'bytes':path.stat().st_size})
    dest=folder/'pdf-full.txt'
    subprocess.run(['pdftotext','-layout',str(path),str(dest)],check=True,capture_output=True)
    pages=dest.read_text().split('\f')
    scopes=[(13,23,9,19,'Erster Vortrag — Dornach, 10. Oktober 1914'),
            (24,37,20,33,'Zweiter Vortrag — Dornach, 18. Oktober 1914'),
            (38,53,34,49,'Dritter Vortrag — Dornach, 19. Oktober 1914'),
            (54,64,50,60,'Vierter Vortrag — Dornach, 24. Oktober 1914'),
            (65,78,61,74,'Fünfter Vortrag — Dornach, 25. Oktober 1914'),
            (93,97,81,85,'Besprechung der Schnitzarbeiten — Dornach, 12. Oktober 1914')]
    passages=[]
    for start,end,gs,ge,title in scopes:
        raw='\n\n'.join(pages[start-1:end]);clean=norm(raw)
        clean=re.sub(r'Die seitlichen Ziffern beziehen sich auf die Abbildung 8,.*?gedacht und nicht bindend\.','',clean,flags=re.S)
        clean='\n'.join(line.strip() for line in clean.splitlines())
        clean=re.sub(r'\n{3,}','\n\n',clean).strip()
        passages.append({'id':f'ga-287-source-{gs:03d}','title':title,'source_label':'Rudolf Steiner Gesamtausgabe 287 (1985) / Odyssee-Theater PDF','source_member':f'PDF pages {start}–{end}','text':clean,'source_text':raw.strip(),'checksum':hashlib.sha256(clean.encode()).hexdigest(),'ga_page':f'S. {gs}–{ge}','metadata':{'page_numbers':list(range(gs,ge+1)),'pdf_page_numbers':list(range(start,end+1)),'page_marker_source':'reviewed_pdf_source_pages','annotations':[]}})
    candidate=folder/'candidate-passages.json';candidate.write_text(json.dumps(passages,ensure_ascii=False,indent=2)+'\n')
    txt=folder/'candidate-text.txt';txt.write_text('\n\n'.join(p['title']+'\n\n'+p['text'] for p in passages)+'\n')
    rec.update(status='source_recovered',import_ready=True,candidate_path=str(candidate.relative_to(ROOT)),candidate_sha256=sha(candidate),candidate_text_path=str(txt.relative_to(ROOT)),candidate_text_sha256=sha(txt),candidate_chars=sum(len(p['text']) for p in passages),candidate_words=sum(len(p['text'].split()) for p in passages),candidate_passage_count=len(passages),pdf_text_path=str(dest.relative_to(ROOT)),scope_reference_url='https://anthrowiki.at/GA_287')
    rec['scope']={'pdf_page_ranges':[[a,b] for a,b,_,_,_ in scopes],'ga_page_ranges':[[a,b] for _,_,a,b,_ in scopes],'expected_sections':6,'evidence':'1985 source TOC identifies five October1914 lectures and 12 October1914 architrave workshop notes. First/last original text and appendix visually inspected; named Marie/Assja/publisher sections excluded.'}
    rec['scope_completeness']='All five lectures and original workshop notes from the full 1985 GA287 edition. Figure images omitted from text extraction.'
    rec['concerns'].append('PDF extraction preserves proper umlauts and full original prose, but line-wrap hyphenation and figure glyph artifacts remain; no full facsimile proofreading. One explicitly publisher-authored appendix footnote excluded.')
    rec['body_start_evidence']=passages[0]['text'][:240];rec['body_end_evidence']=passages[-1]['text'][-240:]

def doc_candidate_283(report):
    rec=next(r for r in report['records'] if r['ga_number']=='283')
    folder=OUT/'ga-283';path=folder/'doc-full.txt';full=path.read_text()
    body_start=full.index('\fERSTER VORTRAG\nKöln, 3. Dezember 1906')
    body_end=full.index('\fANHANG\nNotizen von Mathilde Scholl',body_start)
    text=full[body_start:body_end]
    starts=[m.start() for m in re.finditer(r'\f(?:(?:ERSTER|ZWEITER|DRITTER|VIERTER) VORTRAG|FRAGENBEANTWORTUNG(?:\n|\u2028)|ERSTES SCHLUSSWORT|ZWEITES SCHLUSSWORT|DES MENSCHEN ÄUSSERUNG)',text)]
    starts.append(len(text));passages=[]
    for i,(a,b) in enumerate(zip(starts,starts[1:])):
        raw=text[a:b];page_numbers=[int(x) for x in re.findall(r'\n(\d{1,3})\s*(?=\f|$)',raw)]
        clean=re.sub(r'\n\d{1,3}\s*(?=\f|$)','\n',raw)
        clean=clean.replace('\u2028','\n').replace('\f','\n\n').replace('\u00a0',' ')
        clean='\n'.join(re.sub(r'[ \t]+',' ',line).strip() for line in clean.splitlines())
        clean=re.sub(r'\n{3,}','\n\n',clean).strip()
        title=' — '.join(clean.splitlines()[:2])
        if title.startswith('DES MENSCHEN'):title='Des Menschen Äußerung durch Ton und Wort — Dornach, 2. Dezember 1922'
        passages.append({'id':f'ga-283-source-{i+1:03d}','title':title,'source_label':'Rudolf Steiner Gesamtausgabe 283 (1989) / Original DOC mirrored by Internet Archive','source_member':f'DOC section {i+1}','text':clean,'source_text':raw.strip(),'checksum':hashlib.sha256(clean.encode()).hexdigest(),'ga_page':f'S. {min(page_numbers)}–{max(page_numbers)}' if page_numbers else None,'metadata':{'page_numbers':page_numbers,'page_marker_source':'doc_source_page_footers','annotations':[]}})
    assert len(passages)==12, len(passages)
    candidate=folder/'candidate-passages.json';candidate.write_text(json.dumps(passages,ensure_ascii=False,indent=2)+'\n')
    txt=folder/'candidate-text.txt';txt.write_text('\n\n'.join(p['title']+'\n\n'+p['text'] for p in passages)+'\n')
    rec.update(status='source_recovered',import_ready=True,candidate_path=str(candidate.relative_to(ROOT)),candidate_sha256=sha(candidate),candidate_text_path=str(txt.relative_to(ROOT)),candidate_text_sha256=sha(txt),candidate_chars=sum(len(p['text']) for p in passages),candidate_words=sum(len(p['text'].split()) for p in passages),candidate_passage_count=len(passages))
    rec['scope']={'source_format':'DOC','source_edition_year':1989,'body_start':'ERSTER VORTRAG\\nKöln, 3. Dezember 1906','body_end_before':'ANHANG\\nNotizen von Mathilde Scholl aus dem Jahr 1905 (1906?)','expected_sections':12,'evidence':'1989 source TOC: eight lectures, two question sessions, two closing remarks. Added 2 December1922 lecture present. Mathilde Scholl appendix excluded because publisher itself describes authorship/context as uncertain.'}
    rec['scope_completeness']='All eight lectures, two question sessions and two closing remarks in the 1989 GA283 edition. Ambiguous Scholl notes and publisher apparatus excluded.'
    rec['concerns'].append('Odyssee EPUB is a 1969 edition missing the lecture added in1975; reader candidate therefore uses full1989 original DOC. Word extraction contains line-wrap hyphenation and source spelling; not fully proofread.')
    rec['body_start_evidence']=passages[0]['text'][:240];rec['body_end_evidence']=passages[-1]['text'][-240:]

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    catalog={x['id']:x for x in json.loads((ROOT/'server/priv/library/catalog.json').read_text())['works']}
    tasks=[];records=[]
    for n in NUMBERS:
        wid=f'ga-{n}';folder=OUT/wid;folder.mkdir(exist_ok=True)
        rec={'work_id':wid,'ga_number':n,'title':catalog[wid]['title'],'status':'not_recovered','source_files':[],'concerns':[]}
        records.append(rec)
        mp=ROOT/f'research/ia_metadata/rudolf-steiner-ga-{n}.json'
        if not mp.exists(): rec['concerns'].append('No cached Internet Archive item manifest for this work.');continue
        shutil.copyfile(mp,folder/'ia_metadata.json')
        d=json.loads(mp.read_text());rec['item_url']=f'https://archive.org/details/rudolf-steiner-ga-{n}'
        rec['metadata_path']=str((folder/'ia_metadata.json').relative_to(ROOT));rec['scan_imagecount']=int(d['metadata'].get('imagecount',0))
        for f in d['files']:
            if f.get('format') not in ['Word Document','Djvu XML']:continue
            url=f'https://archive.org/download/rudolf-steiner-ga-{n}/{f["name"]}';dest=folder/f['name']
            source={'url':url,'path':str(dest.relative_to(ROOT)),'format':f['format'],'ia_md5':f.get('md5'),'expected_bytes':int(f['size'])}
            rec['source_files'].append(source);tasks.append((rec,source,dest))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(fetch,s['url'],p,s['expected_bytes']):(r,s,p) for r,s,p in tasks}
        for future in concurrent.futures.as_completed(futures):
            rec,s,p=futures[future]
            try:future.result();s['sha256']=sha(p);s['bytes']=p.stat().st_size;print(f'Fetched {p.name}',flush=True)
            except Exception as exc:s['error']=str(exc);rec['concerns'].append(str(exc));print(str(exc),flush=True)
    for rec in records:
        for s in rec['source_files']:
            if 'error' in s:continue
            p=ROOT/s['path']
            if s['format']=='Djvu XML':
                pages=extract_xml(p);dest=p.parent/'ocr-pages.json';dest.write_text(json.dumps(pages,ensure_ascii=False,indent=2)+'\n')
                txt=p.parent/'ocr-full.txt';txt.write_text('\n\n'.join(x['text'] for x in pages)+'\n')
                rec['ocr_pages_path']=str(dest.relative_to(ROOT));rec['ocr_text_path']=str(txt.relative_to(ROOT));rec['ocr_page_count']=len(pages);rec['ocr_chars']=sum(x['chars'] for x in pages);rec['status']='source_recovered'
            else:
                dest=p.parent/'doc-full.txt'
                result=subprocess.run(['textutil','-convert','txt','-output',str(dest),str(p)],capture_output=True,text=True)
                if result.returncode:rec['concerns'].append(f'DOC extraction failed: {result.stderr}');continue
                txt=norm(dest.read_text());dest.write_text(txt+'\n');rec['doc_text_path']=str(dest.relative_to(ROOT));rec['doc_chars']=len(txt)
        rec['concerns'].append('Automatic extraction; not a facsimile-proofread edition. Full scan includes publisher apparatus until reviewed scope is applied.')
    report={'schema_version':1,'purpose':'Original German source recovery for unavailable art/education GA volumes','records':records}
    epub_candidates(report)
    pdf_candidate_287(report)
    doc_candidate_283(report)
    (ROOT/'tools/recovery-education-art.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':run()
