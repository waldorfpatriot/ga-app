#!/usr/bin/env python3
"""Independently reconstruct GA039 letter headings and exact source additions."""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'research/proofreading-sources/ga-039.epub'
RULE = 'source_letter_headings'
LABEL = 'GA 039: Originalbriefnummern und Briefüberschriften quellengebunden hergestellt'
RESTORATION_LABEL = 'GA 039: im Import ausgelassenen Originalbrief quellengebunden wiederhergestellt'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(text):
    return digest(text.encode())


def stable(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')))


def utf16(text):
    return len(text.encode('utf-16-le')) // 2


def original_atom(archive, witness):
    data = archive.read(witness['source_member'])
    if digest(data) != witness['member_sha256']:
        raise ValueError('GA039 original member bytes differ')
    body = ET.fromstring(data).find('{*}body')
    atom = body[witness['body_index']]
    for child in witness.get('child_path', []):
        atom = atom[child]
    raw = ''.join(atom.itertext())
    if (sha(raw) != witness['source_paragraph_sha256']
            or witness.get('element_sha256') and digest(ET.tostring(atom)) != witness['element_sha256']):
        raise ValueError('GA039 original paragraph identity differs')
    fragment=witness.get('rawitertext_slice')
    if fragment is not None:
        path=witness.get('child_path',[])
        start,stop=fragment['start_codepoint'],fragment['end_codepoint']
        boundary=raw.find('319.')
        if (witness['source_member']!='EPUB/chapter-0004.xhtml' or witness['body_index']!=218
                or path not in ([],[0]) or boundary<0 or type(start) is not int or type(stop) is not int
                or (path==[] and (start!=boundary or stop!=len(raw)))
                or (path==[0] and (start!=0 or stop!=boundary))
                or not 0<=start<stop<=len(raw) or sha(raw[start:stop])!=fragment['text_sha256']):
            raise ValueError('GA039 original mixed signature/heading slice differs')
        raw=raw[start:stop]
    return atom, raw


def source_reading(atom, mode):
    if mode not in {'paragraph', 'br', 'literal'}:
        raise ValueError('GA039 unknown source whitespace mode')
    marker = '\ufdd0'
    def collect(node):
        parts = [node.text or '']
        for child in node:
            parts.append(marker if child.tag.rsplit('}', 1)[-1] == 'br' else collect(child))
            parts.append(child.tail or '')
        return ''.join(parts)
    raw = collect(atom)
    if marker in ''.join(atom.itertext()):
        raise ValueError('GA039 source contains the reserved line-break marker')
    if mode == 'literal':
        if (atom.tag.rsplit('}', 1)[-1] != 'pre'
                and atom.get('{http://www.w3.org/XML/1998/namespace}space') != 'preserve'
                and 'source-lines' not in atom.get('class', '').split()
                and not re.search(r'white-space\s*:\s*(?:pre|pre-wrap)', atom.get('style', ''))):
            raise ValueError('GA039 restored literal mode lacks original markup')
        return raw.replace(marker, '\n').strip()
    if mode == 'paragraph' and marker in raw:
        raise ValueError('GA039 explicit source line break mislabeled as physical XML whitespace')
    return '\n'.join(' '.join(line.split()) for line in raw.split(marker)).strip()


def prefix_repair(repair, current):
    start, old, new = repair['start_codepoint'], repair['old'], repair['new']
    if (type(repair.get('count')) is not int or repair['count'] != 1 or type(start) is not int or start < 0
            or current[start:start+len(old)] != old or not repair.get('evidence')):
        raise ValueError('GA039 exact input heading prefix differs')
    if repair.get('kind') == 'source_editorial_label':
        if (repair['passage_id'] != 'ga-039-doc-heading-113' or repair['field'] != 'title'
                or start != 0 or old != current or new != 'Verzeichnis der Briefe'):
            raise ValueError('GA039 editorial label exceeds the exact misclassified contents heading')
    else:
        old_prefix=repair.get('old_prefix',old);new_prefix=repair.get('new_prefix',new)
        if (repair['field'] not in {'title', 'text'} or old == new
                or not re.fullmatch(r'[0-9A-Za-z.,$^° *\-]+', old_prefix)
                or not re.fullmatch(r'[1-9]\d{1,2}[ab]?\.', new_prefix)
                or not old.startswith(old_prefix) or new!=new_prefix+old[len(old_prefix):]
                or start and current[max(0,start-2):start] != '\n\n'
                or old==old_prefix and current[start+len(old):start+len(old)+1] not in {' ', '\n'}):
            raise ValueError('GA039 replacement is outside a complete original heading number')
    return current[:start] + new + current[start+len(old):]


def reading_blocks(text, headings):
    selected = sorted((h['start_codepoint'], h['end_codepoint']) for h in headings if h['field'] == 'text')
    end = 0
    for start, stop in selected:
        if start < end or stop <= start or stop > len(text):
            raise ValueError('GA039 heading ranges overlap or exceed reading text')
        end = stop
    regions = [(a,b,'heading') for a,b in selected]
    for match in re.finditer(r'[^\n](?:(?!\n\n).)*', text, re.DOTALL):
        cursor, stop = match.span()
        for start, end in selected:
            if end <= cursor or start >= stop:
                continue
            if cursor < start:
                regions.append((cursor,start,'prose'))
            cursor = max(cursor,end)
        if cursor < stop:
            regions.append((cursor,stop,'prose'))
    blocks = []
    for start,end,kind in sorted(regions):
        while start < end and text[start].isspace():start += 1
        while end > start and text[end-1].isspace():end -= 1
        if start < end:
            block={'kind':kind,'start_offset':utf16(text[:start]),'end_offset':utf16(text[:end])}
            if kind == 'heading':block['level']=1
            blocks.append(block)
    return blocks


def verify_printed_repair(repair, review, pdf):
    from check_essay_layout import original_page_raster, original_page_lines
    rasters=repair.get('pdf_raster_witnesses',[])
    if not rasters:
        raise ValueError('GA039 corrected original heading number lacks original printed pixels')
    for raster in rasters:
        page=raster['pdf_page']
        width,height,pixels=original_page_raster(pdf,review['original_pdf_sha256'],page)
        if (raster.get('original_pdf_sha256') != review['original_pdf_sha256']
                or raster.get('page_index') != page-1 or raster.get('original_page_mode') != '1'
                or raster.get('original_page_size') != [width,height]
                or raster.get('visible_page_pixels_sha256') != digest(pixels)):
            raise ValueError('GA039 original heading scan pixels differ')
        transcription=raster.get('printed_prefix_transcription',raster.get('printed_heading_transcription'))
        wanted=repair.get('new_prefix',repair.get('new'))
        if raster.get('visual_verified') is not True or not isinstance(transcription,str) or transcription.casefold()!=wanted.casefold():
            raise ValueError('GA039 printed prefix differs from its reviewed visual transcription')
    # Full source-line geometry and the manually reviewed printed transcription
    # are checked separately; the OCR text itself may contain the bad numeral.
    lines=repair.get('pdf_line_witnesses',[])
    for witness in lines:
        expected=original_page_lines(pdf,review['original_pdf_sha256'],witness['pdf_page'])
        box=witness['bbox_pt']
        if len([1 for text,bbox in expected if text==witness['text']
                and len(box)==4 and all(abs(a-b)<.002 for a,b in zip(bbox,box))])!=1:
            raise ValueError('GA039 original numbered heading line differs')


def inspect_ga039_headings(prior, final, review, events, source=SOURCE):
    if (prior.get('work_id') != 'ga-039' or review.get('work_id') != 'ga-039'
            or digest(source.read_bytes()) != review['source_epub_sha256']
            or any(prior.get(key) != review.get(key) for key in ('source_sha256','source_epub_sha256'))):
        raise ValueError('GA039 exact original edition identity differs')
    for kind in ('doc','pdf'):
        path=ROOT/review['original_'+kind+'_path']
        if digest(path.read_bytes())!=review['original_'+kind+'_sha256']:
            raise ValueError('GA039 original '+kind+' bytes differ')
    if review['original_doc_sha256']!=review['source_sha256']:
        raise ValueError('GA039 original DOC is not the imported source')
    pdf=ROOT/review['original_pdf_path']
    plans=review['input_passages']
    if len(plans)!=102 or list(plans)!=[p['id'] for p in prior['passages']]:
        raise ValueError('GA039 original 102 passage inventory differs')
    for passage in prior['passages']:
        plan=plans[passage['id']]
        if (sha(passage['text'])!=plan['input_text_sha256'] or passage['checksum']!=plan['input_text_sha256']
                or sha(passage['title'])!=plan['input_title_sha256']
                or sha(passage['source_text'])!=plan['source_text_sha256']):
            raise ValueError('GA039 frozen original title/text/source differs')
    expected=deepcopy(prior)
    originals={p['id']:p for p in prior['passages']}
    restored={};after=defaultdict(list)
    additions=review['source_restorations']
    if len(additions)!=41:
        raise ValueError('GA039 original source restoration inventory differs')
    selected_segments=set()
    with ZipFile(source) as archive:
        for addition in additions:
            pid=addition['id'];number=str(addition['original_number'])
            if (pid!='ga-039-source-letter-'+number or pid in originals or pid in restored
                    or addition['after_existing_pid'] not in originals
                    or addition['source_join']!='double_newline' or not addition.get('evidence')):
                raise ValueError('GA039 restoration identity, source placement or join differs')
            _, raw_title=original_atom(archive,addition['heading_source_witness'])
            title=' '.join(raw_title.split())
            raw_parts=[];reading=[]
            for segment in addition['source_segments']:
                key=(segment['source_member'],segment['body_index'],tuple(segment.get('child_path',[])))
                if key in selected_segments:
                    raise ValueError('GA039 restored original source segment is repeated')
                selected_segments.add(key)
                atom,raw=original_atom(archive,segment)
                raw_parts.append(raw)
                part=' '.join(raw.split()) if segment.get('rawitertext_slice') else source_reading(atom,segment['mode'])
                marker=segment.get('list_marker')
                if marker is not None:
                    ordinal=marker['ordinal'];parent_witness=marker['parent_source_witness']
                    parent,_=original_atom(archive,parent_witness)
                    parent_path=parent_witness.get('child_path',[]);item=marker['item_index']
                    if (number!='356' or type(ordinal) is not int or ordinal not in {1,2,3,5,6,7,8,9,10,11,12}
                            or parent.tag.rsplit('}',1)[-1]!='ol' or type(item) is not int
                            or not 0<=item<len(parent) or parent[item].tag.rsplit('}',1)[-1]!='li'
                            or parent_witness['source_member']!=segment['source_member']
                            or parent_witness['body_index']!=segment['body_index']
                            or segment.get('child_path',[])[:len(parent_path)+1]!=parent_path+[item]
                            or not marker.get('evidence')):
                        raise ValueError('GA039 restored list marker is outside its exact original list item')
                    verify_printed_repair(dict(marker,new=str(ordinal)+'.'),review,pdf)
                    part=str(ordinal)+'. '+part
                if part:reading.append(part)
            markers=[s['list_marker']['ordinal'] for s in addition['source_segments'] if s.get('list_marker')]
            if number=='356' and markers!=[1,2,3,5,6,7,8,9,10,11,12]:
                raise ValueError('GA039 original list marker inventory differs')
            raw='\n\n'.join(raw_parts).strip();text='\n\n'.join(reading).strip()
            if (title!=addition['title'] or text!=addition['text'] or raw!=addition['source_text']
                    or sha(raw)!=addition['source_text_sha256']
                    or sha(title)!=addition['input_title_sha256'] or sha(text)!=addition['input_text_sha256']):
                raise ValueError('GA039 restored original heading/body differs from exact XML atoms')
            passage={'id':pid,'title':title,'text':text,'source_text':raw,'checksum':sha(text),'ga_page':None,
                'source_label':prior['passages'][0]['source_label'],'source_member':addition['source_member'],
                'metadata':{'page_numbers':[],'page_marker_source':'reviewed_original_letter_source','annotations':[]}}
            restored[pid]=passage;after[addition['after_existing_pid']].append(passage)
        merged=[]
        for passage in expected['passages']:
            merged.append(passage);merged.extend(after[passage['id']])
        expected['passages']=merged
        if [p['id'] for p in merged]!=review['passage_order'] or len(merged)!=143:
            raise ValueError('GA039 restored original passage sequence differs')
        by_id={p['id']:p for p in merged}
        ids=set();targets=set()
        for repair in review['repairs']:
            rid=repair['id'];pid=repair['passage_id'];field=repair['field'];start=repair['start_codepoint']
            if rid in ids or pid not in by_id or (pid,field,start) in targets:
                raise ValueError('GA039 duplicate or foreign heading-number repair')
            ids.add(rid);targets.add((pid,field,start))
            raws=[original_atom(archive,w)[1] for w in repair['source_witnesses']]
            original=' '.join(' '.join(raws).split())
            token=repair['new'] if repair.get('kind')=='source_editorial_label' else repair.get('old_prefix',repair['old'])
            if (repair.get('kind')=='source_editorial_label' and original.casefold()!=token.casefold()
                    or repair.get('kind')!='source_editorial_label' and not original.startswith(' '.join(token.split()))):
                raise ValueError('GA039 numbered heading is outside its exact original atom')
            verify_printed_repair(repair,review,pdf)
        for repair in sorted(review['repairs'],key=lambda r:(r['passage_id'],r['field'],-r['start_codepoint'])):
            passage=by_id[repair['passage_id']];field=repair['field']
            passage[field]=prefix_repair(repair,passage[field])
        headings=review['headings'];numbers=[];heading_ids=set();locations=[];by_passage=defaultdict(list);toc=[]
        order={p['id']:i for i,p in enumerate(merged)}
        for heading in headings:
            pid=heading['passage_id'];field=heading['field'];start=heading['start_codepoint'];end=heading['end_codepoint']
            if pid not in by_id or heading['id'] in heading_ids or field not in {'title','text'}:
                raise ValueError('GA039 original heading target or identity differs')
            heading_ids.add(heading['id']);p=by_id[pid]
            label=p['title'] if field=='title' else p['text'][start:end]
            if (label!=heading['label'] or field=='title' and (start or end)
                    or field=='text' and (not 0<=start<end<=len(p['text'])
                        or start and p['text'][start-2:start]!='\n\n'
                        or end<len(p['text']) and p['text'][end:end+2]!='\n\n')):
                raise ValueError('GA039 original heading is not its exact output paragraph')
            source_heading=' '.join(' '.join(original_atom(archive,w)[1] for w in heading['source_witnesses']).split())
            if not source_heading.startswith(' '.join(heading['old_source_full_heading'].split())):
                raise ValueError('GA039 original heading source identity differs')
            source_label=' '.join(heading['old_source_full_heading'].split())
            for repair in review['repairs']:
                if (repair['passage_id']==pid and repair['field']==field
                        and str(repair.get('corrected_number'))==str(heading.get('original_number'))):
                    prefix_old=repair.get('old_prefix',repair['old']);prefix_new=repair.get('new_prefix',repair['new'])
                    if source_label.startswith(prefix_old):source_label=prefix_new+source_label[len(prefix_old):]
            if ' '.join(label.split()).casefold()!=source_label.casefold():
                raise ValueError('GA039 heading changes source recipient or dateline')
            number=heading.get('original_number')
            if number is not None:
                number=str(number)
                if not label.startswith(number+'.'):
                    raise ValueError('GA039 original letter number differs from printed heading')
                numbers.append(number)
            elif label.casefold() not in {'nachtrag zu den briefen','nachtrag zu briefe i','verzeichnis der briefe'}:
                raise ValueError('GA039 invented editorial heading')
            locations.append((order[pid],0 if field=='title' else start+1))
            by_passage[pid].append(heading)
            toc.append({'id':heading['id'],'title':label,'passage_id':pid,
                'start_offset':0 if field=='title' else utf16(p['text'][:start]),'level':1,'parent_id':None,
                'source_role':'letter' if number is not None else 'table_of_contents'})
        main=[str(i) for i in range(253,652)]
        if (locations!=sorted(locations) or [n for n in numbers if n in main]!=main
                or Counter(numbers)!=Counter(main+['74a','74b','637a','637b'])):
            raise ValueError('GA039 399 original main letters/four supplements are incomplete or renumbered')
        if toc!=review['table_of_contents'] or stable(toc)!=review['output_table_of_contents_sha256']:
            raise ValueError('GA039 exact source navigation differs')
    revision=stable(review);marker={'review_sha256':revision,'source_epub_sha256':review['source_epub_sha256']}
    expected['table_of_contents']=toc;expected['passage_count']=143
    expected.setdefault('metadata',{})['source_letter_heading_review']=marker
    addition_by_id={a['id']:a for a in additions};expected_events={}
    for p in expected['passages']:
        pid=p['id'];before=originals.get(pid);plan=plans.get(pid,addition_by_id.get(pid))
        blocks=reading_blocks(p['text'],by_passage[pid]);p['metadata']['reading_blocks']=blocks
        p['checksum']=sha(p['text'])
        if (sha(p['text'])!=plan['output_text_sha256'] or sha(p['title'])!=plan['output_title_sha256']
                or stable(blocks)!=plan['output_reading_blocks_sha256']):
            raise ValueError('GA039 independently projected output hashes differ: '+pid)
        replacements=[r for r in review['repairs'] if r['passage_id']==pid]
        event={'passage_id':pid,'input_sha256':sha(before['text']) if before else sha(''),
            'output_sha256':p['checksum'],'input_title_sha256':sha(before['title']) if before else sha(''),
            'output_title_sha256':sha(p['title']),'source_text_sha256':sha(p['source_text']),
            'input_reading_blocks_sha256':stable(before.get('metadata',{}).get('reading_blocks',[])) if before else stable([]),
            'output_reading_blocks_sha256':stable(blocks),'input_table_of_contents_sha256':stable(prior.get('table_of_contents',[])),
            'output_table_of_contents_sha256':stable(toc),'heading_count':len(by_passage[pid]),
            'replacements':replacements,'before_excerpt':before['text'][:600] if before else '', 'after_excerpt':p['text'][:600]}
        if not before:
            addition=addition_by_id[pid]
            p['metadata']['source_letter_restoration']={**marker,'original_number':addition['original_number'],'source_member':addition['source_member']}
            event.update(rule='source_restoration',label=RESTORATION_LABEL,count=1,restoration_id=pid,
                source_segments=addition['source_segments'],heading_source_witness=addition['heading_source_witness'])
        else:
            event.update(rule=RULE,label=LABEL,count=max(1,len(replacements)))
        expected_events[pid]=[event]
    actual={pid:[dict(e,passage_id=pid) for e in items if e['rule'] in {RULE,'source_restoration'}]
            for pid,items in events.items() if any(e['rule'] in {RULE,'source_restoration'} for e in items)}
    if actual!=expected_events:
        raise ValueError('GA039 exact heading/restoration correction ledger differs')
    if final!=expected:
        return ['GA039 original numbered letter text, navigation or retained metadata differs'],{}
    return [],{'ga039_original_letter_headings':len(numbers),'ga039_heading_number_repairs':sum(r['kind']!='source_editorial_label' for r in review['repairs']),
        'ga039_editorial_heading_repairs':sum(r['kind']=='source_editorial_label' for r in review['repairs']),
        'ga039_restored_letter_passages':len(additions),'source_restored_items':len(additions),'source_restored_passages':len(additions)}
