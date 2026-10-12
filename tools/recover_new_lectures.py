#!/usr/bin/env python3
"""Recover publicly linked German source witnesses for unavailable GA rows.

This research script never edits a catalog or reader content. Downloaded source
editions may contain editorial matter; hashes and counts do not certify authorship.
"""
from __future__ import annotations
import concurrent.futures
import datetime
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "research/unavailable-recovery/new-lectures"
REPORT = ROOT / "tools/recovery-new-lectures.json"
NUMBERS = "068a 068b 068c 068d 069a 069b 069c 069d 069e 070a 070b 071a 071b 075 080a 080b 080c 085 086 087 090a 090b 090c 091 111 244 246 247 250 251 252 270-4 277d 288 331b 332b 336".split()

class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.text=[]
    def handle_starttag(self, tag, attrs):
        if tag=='a':
            href=dict(attrs).get('href')
            if href: self.links.append(href)
    def handle_data(self, data): self.text.append(data)

def fetch(url, path):
    req=urllib.request.Request(url, headers={'User-Agent':'GA-source-recovery/1.0'})
    with urllib.request.urlopen(req,timeout=60) as r:
        data=r.read(); final=r.geturl(); kind=r.headers.get('Content-Type','')
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    return {'url':url,'resolved_url':final,'file':str(path.relative_to(ROOT)),
            'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'mime_type':kind}

def epub_evidence(path):
    out=[]
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.lower().endswith(('.html','.xhtml','.htm')):
                p=Page();p.feed(z.read(name).decode('utf-8',errors='replace'))
                t='\n'.join(p.text)
                out.append({'file':name,'characters':len(t),'sample':t[:200]})
    return {'text_characters':sum(x['characters'] for x in out),'html_file_count':len(out),
            'sections':out}

def recover(number, work):
    folder=DEST/work['id']; folder.mkdir(parents=True,exist_ok=True)
    n=re.sub(r'^0+', '', number).replace('-','/')
    row={'id':work['id'],'ga_number':work['ga_number'],'title':work['title'],
         'classification':'text_volume','source_status':'not_recovered','sources':[],
         'blockers':[], 'completeness':'unverified','eligible_original_text_only':False}
    url='https://anthrowiki.at/GA_'+urllib.parse.quote(n,safe='/')
    row['discovery_url']=url
    try:
        meta=fetch(url,folder/'discovery.html'); raw=(folder/'discovery.html').read_text()
        page=Page();page.feed(raw);txt='\n'.join(page.text)
        row['discovery_file']=meta
        row['metadata_excerpt']=txt[max(0,txt.find('Aus AnthroWiki')):][:3000]
        row['publisher_urls']=[u for u in page.links if 'steinerverlag.com' in u and ('ga-' in u.lower() or '/de/' in u)]
        links=[]
        for u in page.links:
            if 'odysseetheater.org/GA/' in u and re.search(r'\.(pdf|epub)(?:#|$)',u):
                links.append(u.split('#')[0])
        for u in dict.fromkeys(links):
            filename=urllib.parse.unquote(urllib.parse.urlparse(u).path.rsplit('/',1)[-1])
            try:
                info=fetch(u,folder/filename)
                p=folder/filename
                if filename.lower().endswith('.pdf'):
                    if not p.read_bytes().startswith(b'%PDF'):raise ValueError('Response is not a PDF')
                    try:
                        textpath=p.with_suffix('.txt')
                        subprocess.run(['pdftotext','-layout',str(p),str(textpath)],check=True,capture_output=True)
                        text=textpath.read_text();info['text_file']=str(textpath.relative_to(ROOT));info['text_characters']=len(text)
                        info['page_count']=text.count('\f');info['text_sha256']=hashlib.sha256(textpath.read_bytes()).hexdigest()
                        info['beginning']=text[:1200];info['ending']=text[-1200:]
                    except FileNotFoundError:info['text_extraction']='pdftotext unavailable'
                else: info.update(epub_evidence(p))
                row['sources'].append(info)
                print(number,filename,info.get('text_characters'),flush=True)
            except Exception as e:row['blockers'].append({'url':u,'error':str(e)})
        row['linked_fulltext_urls']=[u for u in page.links if any(x in u for x in ['bdn-steiner.ru/cat/ga/','archive.org/details/','steiner.wiki/GA_','rsarchive.org/Lectures/GA'])]
    except Exception as e:row['blockers'].append({'url':url,'error':str(e)})
    if row['sources']:
        row['source_status']='downloaded_source_edition'
        row['completeness']='source_edition_downloaded_not_collated'
        row['blockers'].append('Original Steiner text must be separated from introductions, reports by others, editorial notes, indexes, and later illustrations before reader import.')
    else:row['blockers'].append('No complete open German source downloaded from the discovery page; publisher edition or further individual-lecture research required.')
    cached=[]
    for p in sorted((ROOT/'research/ia_metadata').glob('*.json')):
        if p.stem in {'rudolf-steiner-ga-'+number,'rudolf-steiner-ga-'+number.replace('-','_')}:
            cached.append(str(p.relative_to(ROOT)))
    row['cached_ia_manifests']=cached
    return row

def main():
    works=json.loads((ROOT/'server/priv/library/catalog.json').read_text())['works']
    assigned=[w for w in works if w['id'] in {'ga-'+n for n in NUMBERS}]
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures={pool.submit(recover,w['id'][3:],w):w for w in assigned}
        for f in concurrent.futures.as_completed(futures):
            r=f.result();results.append(r)
            REPORT.write_text(json.dumps({'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'rows':sorted(results,key=lambda x:x['id'])},ensure_ascii=False,indent=2)+'\n')
    for w in works:
        if w.get('content_completeness')!='unavailable':continue
        if w['id'].startswith('ga-k-') or w['id'].startswith('ga-ega-') or 'Leernummer' in w['title']:
            kind='artwork_facsimile' if w['id'].startswith('ga-k-') else 'digital_manuscript_edition' if w['id'].startswith('ga-ega-') else 'catalogue_blank_number'
            results.append({'id':w['id'],'ga_number':w['ga_number'],'title':w['title'],
              'classification':kind,'source_status':'not_recovered','sources':[],
              'completeness':'not_applicable_to_plain_text_volume' if kind=='catalogue_blank_number' else 'unverified',
              'eligible_original_text_only':False,'blockers':[
              'A current catalogue blank is not an unavailable book; historical assignments must not be substituted.' if kind=='catalogue_blank_number' else
              'Artwork and facsimile catalogue rows need their actual images, catalogue scope and rights provenance; transcribing a related lecture does not recover this edition.' if kind=='artwork_facsimile' else
              'This is a digital notebook/manuscript edition; requires the original digital witnesses and provenance, not a substitute lecture text.']})
    REPORT.write_text(json.dumps({'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'policy':'Research sources only. Preserve catalogue identity and German originals; no reader catalogue edits or publication.',
        'rows':sorted(results,key=lambda x:x['id'])},ensure_ascii=False,indent=2)+'\n')
    print('report',REPORT,'rows',len(results),flush=True)

if __name__=='__main__':main()
