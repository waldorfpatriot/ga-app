#!/usr/bin/env python3
"""Discover and download explicitly linked secondary OCR witnesses.

The public index and candidate manifest are cached. Run the finalizer after this
script to merge these witnesses and the scope corrections into the GA report.
"""
import argparse
import concurrent.futures
import hashlib
import json
import re
from pathlib import Path
from recover_rsarchive_new import ROOT, DEST, read, links
from recover_new_lectures import NUMBERS

INDEX_URL='https://losversatoio.altervista.org/ga332b-2/'
CANDIDATES=DEST/'mirror-candidates.json'

def discover():
    """Use only links observed on the retained mirror index, never guessed URLs."""
    node,info=read(INDEX_URL,DEST/'mirror-index.html')
    assigned={'ga-'+number for number in NUMBERS}
    candidates=[];seen=set()
    for url,title in links(node,INDEX_URL):
        if not url.startswith('https://losversatoio.altervista.org/'):continue
        slug=url.rstrip('/').rsplit('/',1)[-1]
        match=re.fullmatch(r'(?:rudolf-steiner-)?ga-?(\d+)(?:-?([a-z]))?(?:-\d+)?',slug)
        if not match:continue
        number=match[1].zfill(3)+(match[2] or '')
        work_id='ga-'+number
        if work_id not in assigned or url in seen:continue
        seen.add(url);candidates.append({'id':work_id,'url':url,'title':title.strip()})
    if not candidates:raise ValueError('Mirror index contains no assigned source links')
    return {'index_source':info,'candidates':candidates}

def recover(candidate):
    row=dict(candidate);folder=DEST/row['id']/'mirror'
    slug=row['url'].rstrip('/').rsplit('/',1)[-1]
    try:
        node,info=read(row['url'],folder/(slug+'.html'))
        content=next((n for n in node.walk() if 'entry-content' in n.attrs.get('class','').split()),None)
        if content is None:raise ValueError('No article content container')
        text=content.text().strip()+'\n'
        textpath=folder/(slug+'.txt');textpath.write_text(text)
        info.update({'text_file':str(textpath.relative_to(ROOT)),'text_characters':len(text),
           'text_sha256':hashlib.sha256(textpath.read_bytes()).hexdigest(),
           'source_quality':'Secondary OCR witness, includes publisher/editorial content and OCR spelling errors; not reader-ready.',
           'start_sample':text[:250],'end_sample':text[-250:]})
        row['source']=info
        print(row['id'],slug,len(text),flush=True)
    except Exception as e:row['error']=str(e)
    return row

def main(rediscover=False):
    if rediscover or not CANDIDATES.exists():
        data=discover()
        CANDIDATES.parent.mkdir(parents=True,exist_ok=True)
        CANDIDATES.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    else:data=json.loads(CANDIDATES.read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(recover,data['candidates']))
    (DEST/'mirror-sources.json').write_text(json.dumps({'index_source':data['index_source'],'sources':rows},ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--discover',action='store_true',help='Rebuild candidate links from the cached public index')
    main(parser.parse_args().discover)
