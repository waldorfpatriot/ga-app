#!/usr/bin/env python3
"""Download explicitly linked original German lecture pages for research."""
from __future__ import annotations
import concurrent.futures
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
from recover_new_lectures import ROOT, DEST, REPORT

VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
class Node:
    def __init__(self,tag='',attrs=None,parent=None):self.tag=tag;self.attrs=attrs or {};self.children=[];self.parent=parent
    def walk(self):
        yield self
        for c in self.children:
            if isinstance(c,Node):yield from c.walk()
    def text(self):
        if self.tag in {'script','style'} or 'paragraphMarker' in self.attrs.get('class','').split():return ''
        t=''.join(c.text() if isinstance(c,Node) else c for c in self.children)
        return t+'\n' if self.tag in {'p','br','h1','h2','h3','h4','li','div','tr'} else t
class DOM(HTMLParser):
    def __init__(self):super().__init__();self.root=Node();self.current=self.root
    def handle_starttag(self,tag,attrs):
        n=Node(tag,dict(attrs),self.current);self.current.children.append(n)
        if tag not in VOID:self.current=n
    def handle_endtag(self,tag):
        n=self.current
        while n.parent and n.tag!=tag:n=n.parent
        if n.tag==tag and n.parent:self.current=n.parent
    def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs);self.handle_endtag(tag)
    def handle_data(self,data):self.current.children.append(data)

def read(url,path):
    url=url.replace('https://rsarchive.org/','http://rsarchive.org/').replace('https://www.rsarchive.org/','http://rsarchive.org/')
    if path.exists():data=path.read_bytes();final=url.replace('http:','https:',1)
    else:
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req,timeout=45) as r:data=r.read();final=r.geturl()
        except (ConnectionResetError,TimeoutError):
            with urllib.request.urlopen(req,timeout=45) as r:data=r.read();final=r.geturl()
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    d=DOM();d.feed(data.decode('utf-8',errors='replace'))
    return d.root,{'url':url,'resolved_url':final,'file':str(path.relative_to(ROOT)),
                   'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}

def links(node,base):
    out=[]
    for n in node.walk():
        if n.tag!='a' or 'href' not in n.attrs:continue
        u=urllib.parse.urljoin(base,n.attrs['href'])
        # Correct two observed malformed internal archive links, retaining the
        # actual href in the raw index witness for provenance.
        if u.startswith(('http://Lectures/','https://Lectures/')):
            u='http://rsarchive.org/Lectures/'+u.split('/Lectures/',1)[1]
        u=re.sub(r'/Lectures/GA[^/]+/Lectures/','/Lectures/',u)
        out.append((u,n.text().strip()))
    return out

def index(row):
    number=row['id'][3:];url='http://rsarchive.org/Lectures/GA'+number+'/'
    folder=DEST/row['id']/'rsarchive'
    out={'url':url,'rows':[],'errors':[]}
    try:
        node,info=read(url,folder/'index.html');out['index_source']=info
        for tr in node.walk():
            if tr.tag!='tr':continue
            ls=[(u,t) for u,t in links(tr,url) if re.search(r'/Lectures/GA'+re.escape(number)+r'/.*\.html(?:$|\?)',u)]
            if not ls:continue
            de=[(u,t) for u,t in ls if '/German/' in u]
            choice=(de or ls)[0]
            out['rows'].append({'index_title':choice[1],'index_text':re.sub(r'\s+',' ',tr.text()).strip(),'url':choice[0]})
        # Some historical indexes use table-free text.
        if not out['rows']:
            for u,t in links(node,url):
                if re.search(r'/Lectures/GA'+re.escape(number)+r'/(?:English|German)/.*\.html$',u):
                    out['rows'].append({'index_title':t,'url':u})
        dedup={r['url']:r for r in out['rows']};out['rows']=list(dedup.values())
    except Exception as e:out['errors'].append(str(e))
    print(row['id'],'index',len(out['rows']),out['errors'],flush=True)
    return row['id'],out

def lecture(item):
    work_id,entry=item;u=entry['url'];folder=DEST/work_id/'rsarchive'
    filename=Path(urllib.parse.urlparse(u).path).name
    try:
        node,info=read(u,folder/('original-'+filename if '/German/' in u else 'english-'+filename))
        content=None
        if '/German/' not in u:
            content=next((n for n in node.walk() if 'German' in n.attrs.get('class','').split()),None)
            if content is not None:
                # Some bilingual pages include a second, automated translation
                # inside .German. Restrict those pages to #original.
                content=next((n for n in content.walk() if n.attrs.get('id')=='original'),content)
        if '/German/' not in u and content is None:
            compares=[x for x,t in links(node,u) if '/Compare_' in x]
            if not compares:raise ValueError('No original German page or compare witness linked')
            cnode,cinfo=read(compares[0],folder/Path(urllib.parse.urlparse(compares[0]).path).name)
            german=[x for x,t in links(cnode,compares[0]) if '/German/' in x]
            if not german:raise ValueError('Compare page has no explicit original German source')
            u=german[0]
            filename=Path(urllib.parse.urlparse(u).path).name
            node,info=read(u,folder/('original-'+filename));info['compare_source']=cinfo
        if content is None:
            content=next((n for n in node.walk() if 'contentBegins' in n.attrs.get('class','').split()),None)
        if content is None:raise ValueError('No original lecture content container')
        title=next((n.text().strip() for n in content.walk() if n.tag in {'h3','h2'}),'')
        text=re.sub(r'\n\s*\n(?:\s*\n)+','\n\n',content.text()).strip()+'\n'
        if len(text)<150:raise ValueError('Empty or negligible German witness')
        textpath=folder/('original-'+filename.rsplit('.',1)[0]+'.txt');textpath.write_text(text)
        info.update({'text_file':str(textpath.relative_to(ROOT)),'text_characters':len(text),'text_sha256':hashlib.sha256(textpath.read_bytes()).hexdigest(),
                    'title':title,'index_text':entry.get('index_text',''),'language':'de',
                    'content_boundary':'div#original' if content.attrs.get('id')=='original' else 'div.German' if 'German' in content.attrs.get('class','').split() else 'div.contentBegins',
                    'paragraph_count':sum(n.tag=='p' for n in content.walk()),'start_sample':text[:150],'end_sample':text[-150:]})
        return work_id,info,None
    except Exception as e:return work_id,None,{'url':u,'error':str(e)}

def main():
    report=json.loads(REPORT.read_text());byid={r['id']:r for r in report['rows']}
    rows=[r for r in report['rows'] if r['classification']=='text_volume' and r['id'] not in {'ga-086','ga-247','ga-270-4'}]
    indexes={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for work_id,result in pool.map(index,rows):indexes[work_id]=result
    tasks=[(work_id,entry) for work_id,i in indexes.items() for entry in i['rows']]
    print('German lecture candidates',len(tasks),flush=True)
    recovered={};failed={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for work_id,info,error in pool.map(lecture,tasks):
            if info:recovered.setdefault(work_id,[]).append(info)
            if error:failed.setdefault(work_id,[]).append(error)
    for work_id,i in indexes.items():
        source_index=DEST/work_id/'rsarchive/source-index.json'
        source_index.parent.mkdir(parents=True,exist_ok=True)
        docs=recovered.get(work_id,[])
        payload={'index':i,'german_witnesses':docs,'errors':failed.get(work_id,[]),'expected_index_entries':len(i['rows'])}
        source_index.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
        r=byid[work_id];r['rsarchive']={'source_index':str(source_index.relative_to(ROOT)),
          'index_url':i['url'],'index_entry_count':len(i['rows']),'german_witness_count':len(docs),
          'text_characters':sum(d['text_characters'] for d in docs),'errors':i['errors']+failed.get(work_id,[])}
        if docs:
            r['source_status']='downloaded_german_lecture_witnesses'
            r['completeness']='all_linked_archive_lectures_downloaded' if len(docs)==len(i['rows']) else 'partial_archive_lectures_downloaded'
            r['blockers'].append('Archive lecture index coverage must be matched to the actual catalogue edition; downloaded witnesses may include listener reports, interlocutor speech and editorial footnotes.')
        print(work_id,len(docs),'/',len(i['rows']),r['rsarchive']['text_characters'],flush=True)
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
