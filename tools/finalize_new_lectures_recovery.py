#!/usr/bin/env python3
"""Merge recovered witnesses and scope corrections without changing the reader.

Run after recover_new_lectures.py, recover_rsarchive_new.py, and
recover_new_lectures_mirror.py. Official evidence and the partial GA 270i image
selection are downloaded only if absent; cached original artifacts are retained.
"""
import argparse
import hashlib
import json
from pathlib import Path
import py_compile
import re
import subprocess
from recover_new_lectures import ROOT, DEST, REPORT, fetch

OFFICIAL={
 'annual-report-2024.pdf':'https://www.rudolf-steiner.com/wp-content/uploads/2025/04/250307_RSA_Jahresbericht_24-klein.pdf',
 'publisher-ga-online-flyer.pdf':'https://steinerverlag.com/wp-content/uploads/Flyer-GA-online-web.pdf',
 'publisher-catalogue-2022.pdf':'https://steinerverlag.com/wp-content/uploads/RudolfSteinerVerlag_GV_2022.pdf',
}
GA270I_URL='https://odysseetheater.org/GA/Buecher/GA_270i.pdf'

def ensure_pdf(path,url):
    """Retrieve explicit source prerequisites, leaving existing witnesses intact."""
    if not path.exists():fetch(url,path)
    if not path.read_bytes().startswith(b'%PDF'):raise ValueError(f'Not a PDF: {path}')
    textpath=path.with_suffix('.txt')
    if not textpath.exists():
        subprocess.run(['pdftotext','-layout',str(path),str(textpath)],check=True,capture_output=True)
    return file_info(path,url)

def file_info(path,url):
    info={'url':url,'file':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,
      'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    textpath=path.with_suffix('.txt')
    if textpath.exists():
        t=textpath.read_text();info.update({'text_file':str(textpath.relative_to(ROOT)),
          'text_characters':len(t),'text_sha256':hashlib.sha256(textpath.read_bytes()).hexdigest(),
          'page_count':t.count('\f')})
    return info

def verify_source_artifacts(report):
    """Verify actual source/text witnesses separately from discovery metadata."""
    checked={};primary=set()
    def walk(value,is_primary=True):
        if isinstance(value,list):
            for item in value:walk(item,is_primary)
        elif isinstance(value,dict):
            for pathkey,hashkey in [('file','sha256'),('text_file','text_sha256')]:
                if value.get(pathkey) and value.get(hashkey):
                    path=(ROOT/value[pathkey]).resolve()
                    if not path.is_relative_to(DEST.resolve()):raise ValueError(f'Witness outside recovery folder: {path}')
                    digest=hashlib.sha256(path.read_bytes()).hexdigest()
                    if digest!=value[hashkey]:raise ValueError(f'Witness hash mismatch: {path}')
                    checked[path]=digest
                    if is_primary:primary.add(path)
            for item in value.values():
                if isinstance(item,(dict,list)):walk(item,False)
    for row in report['rows']:
        walk(row['sources']);walk(row.get('secondary_ocr_witnesses',[]))
        if row.get('rsarchive'):
            index=json.loads((ROOT/row['rsarchive']['source_index']).read_text())
            walk(index['german_witnesses'])
    for name in ('recover_new_lectures.py','recover_rsarchive_new.py',
                 'recover_new_lectures_mirror.py','finalize_new_lectures_recovery.py'):
        py_compile.compile(str(ROOT/'tools'/name),doraise=True)
    return {'python_scripts_compile':True,
            'distinct_source_and_text_files_checked':len(primary),
            'distinct_compare_source_files_checked':len(set(checked)-primary),
            'hash_failures':[]}

def finalize(report_path=REPORT,output_path=REPORT):
    report=json.loads(report_path.read_text());byid={r['id']:r for r in report['rows']}
    if len(byid)!=len(report['rows']):raise ValueError('Duplicate assigned recovery rows')
    evidence={name:ensure_pdf(DEST/'official'/name,url) for name,url in OFFICIAL.items()}
    if not (DEST/'mirror-sources.json').exists():
        from recover_new_lectures_mirror import main as recover_mirrors
        recover_mirrors()
    mirrors=json.loads((DEST/'mirror-sources.json').read_text())['sources']
    for r in report['rows']:
        r['metadata_sources']=[evidence['publisher-catalogue-2022.pdf'],evidence['annual-report-2024.pdf']]
        if r.get('discovery_file'):
            html=(ROOT/r['discovery_file']['file']).read_text()
            r['publisher_urls']=list(dict.fromkeys(u for u in re.findall(r'href="([^"]+)"',html) if 'steinerverlag.com/shop/' in u))
        r['secondary_ocr_witnesses']=[m['source'] for m in mirrors if m['id']==r['id'] and 'source' in m]
        if r.get('rsarchive'):
            indexpath=ROOT/r['rsarchive']['source_index'];d=json.loads(indexpath.read_text())
            unique={w['text_file']:w for w in d['german_witnesses']}
            flags=[]
            for w in unique.values():
                t=(ROOT/w['text_file']).read_text()
                hints=[]
                if re.search(r'Bericht (?:in|aus|über)|von Felix Löhnis|Protokoll(?:arische|ierte)? (?:Aufzeichnung|Mitschrift)|Aus (?:den|einem) (?:Erinnerungen|Bericht)',t[:1000],re.I):hints.append('report_or_protocol_contains_third_party_narration')
                if re.search(r'Rudolf Steiner\s*:',t) and re.search(r'(?:Roman Boos|Emil Molt|Hans Kühn|Walther|Herr [A-ZÄÖÜ][\wäöüß-]+|Dr\. [A-Z][\w-]+)\s*:',t):hints.append('multiple_speakers')
                if re.search(r'Nach (?:Notizen|Notiz|Angaben)|Notizen von|Mitschrift von|Aufzeichnung von',t[:700],re.I):hints.append('listener_notes_or_report_scope_requires_review')
                if r['id']=='ga-277d' and ('Programm' in t[:1200] or len(t)<1500):hints.append('programme_or_short_performance_document')
                if hints:flags.append({'text_file':w['text_file'],'flags':hints})
            r['rsarchive'].update({'source_index_sha256':hashlib.sha256(indexpath.read_bytes()).hexdigest(),
                'unique_german_witness_count':len(unique),'duplicate_index_witness_count':len(d['german_witnesses'])-len(unique),
                'unique_text_characters':sum(w['text_characters'] for w in unique.values()),
                'authorship_scope_flags':flags,
                'completeness_evidence':'Counts describe archive index coverage, not a claim that the printed GA edition or original-only reader scope is complete.'})
            if unique:r['source_status']='downloaded_german_witnesses_needs_scope_review'
            r['blockers']=[b for b in r['blockers'] if not (isinstance(b,str) and b.startswith('No complete open German source downloaded') and unique)]
        if r['classification']=='artwork_facsimile':
            r['completeness_evidence']='Publisher catalogue places this row under artistic works, forms or blackboard facsimiles. Related prose volumes do not demonstrate a recovered full artwork set.'
        if r['classification']=='catalogue_blank_number':
            r['source_status']='not_a_missing_book';r['completeness_evidence']='Publisher catalogue marks this GA number as Leernummer.'
    for n,target in [('086','ga-085'),('247','ga-246')]:
        r=byid['ga-'+n];r.update({'classification':'superseded_planned_volume','source_status':'not_an_independent_published_volume',
          'completeness':'not_applicable_to_superseded_plan','current_volume':target,
          'completeness_evidence':'Rudolf Steiner Nachlassverwaltung annual report 2024, printed p. 11: originally planned GA 85/86 and GA 246/247 were combined into one volume each, GA 85 and GA 246.',
          'blockers':['The legacy row denotes an abandoned planned split. Do not fabricate an independent book or copy the current combined volume into both rows.']})
    r=byid['ga-270-4'];source=ensure_pdf(DEST/'ga-270-4/GA_270i.pdf',GA270I_URL)
    r.update({'classification':'artwork_facsimile','source_status':'downloaded_partial_related_facsimile','sources':[source],
      'completeness':'partial_related_blackboard_selection','completeness_evidence':'PDF metadata title specifies GA 270i Wandtafelzeichnungen, 11 pages. Pages are labelled fifth through seventeenth lesson and repetition lessons. This proves a related image selection, not full historical GA 270/IV with manuscripts.',
      'blockers':['Full historical GA 270/IV contains blackboard and manuscript facsimiles; this 11 page selection does not establish complete coverage. Current 2022 publisher catalogue lists a consolidated 857 page GA 270 edition. No prose substitute is appropriate.']})
    r=byid['ga-ega-47-48'];r['metadata_sources'].append(evidence['publisher-ga-online-flyer.pdf']);r['source_status']='subscription_digital_edition_not_recovered'
    r['completeness_evidence']='Official GA-online flyer identifies an exclusive digital edition with manuscript facsimiles and line-identical transcriptions. Annual report 2024 says publication continues beyond 2025.'
    r=byid['ga-k-48'];r['catalogue_scope_note']='Legacy planned title Das zeichnerische Werk. Annual report 2024 lists completed 2025 scope as K 17–22, 25, 48: Zeichnungen. Karikaturen, Kostüme, Physiognomisches. Preserve identity until reconciled with publisher metadata.'
    byid['ga-k-26a']['authorship_scope_note']='Catalogue explicitly describes Annemarie Bäschlin’s painted realizations; distinguish Steiner’s original designs from another artist’s execution.'
    byid['ga-k-23-7']['original_language_note']='Forms accompany English poems. German-only metadata is insufficient to classify the original artistic material.'
    byid['ga-k-23-8']['original_language_note']='Forms accompany French and Russian poems. German-only metadata is insufficient to classify the original artistic material.'
    byid['ga-244']['completeness_evidence']='2022 publisher catalogue specifies 936 pages of chronological written/oral questions and interviews; RSArchive page contains an index without linked original texts. Existing Q&A elsewhere is not a demonstrated complete recovery of this separate catalogue edition.'
    byid['ga-331b']['catalogue_scope_note']='Legacy planned Kulturräte title exists in older catalogues, but no independently published full source was substantiated. Current 2022 catalogue instead documents GA 332b (2020), which includes Kulturrat material. Do not equate the two catalogue identities without further evidence.'
    byid['ga-277d']['catalogue_scope_note']='Annual report 2024 gives actual final volume scope 1923–1924; existing catalogue row says 1923–1925. Archive index 195 entries includes programmes; 31 German containers are empty and cannot be substituted with English translations.'
    report['summary']={'assigned_rows':len(report['rows']),
      'german_lecture_witness_rows':sum(bool(r.get('rsarchive',{}).get('unique_german_witness_count')) for r in report['rows']),
      'unique_german_lecture_files':sum(r.get('rsarchive',{}).get('unique_german_witness_count',0) for r in report['rows']),
      'unique_german_lecture_characters':sum(r.get('rsarchive',{}).get('unique_text_characters',0) for r in report['rows']),
      'downloaded_secondary_ocr_pages':len([m for m in mirrors if 'source' in m]),
      'scope_review_required':True,'reader_catalogue_edited':False}
    report['policy']='Research only; no publishing or catalogue mutations. Raw HTML/PDF editions are retained for proofing. German original containers alone are extracted; translated and automated-translation containers are excluded. Modern sources may include reports, interlocutors, programmes, and editorial matter requiring original-only scope review.'
    report['verification']=verify_source_artifacts(report)
    output_path.parent.mkdir(parents=True,exist_ok=True)
    output_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(report['summary'])

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=REPORT,help='Input recovery report')
    parser.add_argument('--output',type=Path,default=REPORT,help='Finalized report (default: tools/recovery-new-lectures.json)')
    args=parser.parse_args();finalize(args.input,args.output)
