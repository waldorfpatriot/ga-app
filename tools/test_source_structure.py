#!/usr/bin/env python3
"""Regression checks for edition-bound repairs and real GA 040 source evidence."""
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from repair_source_structure import apply_recipe, sha, validate_layout, stage
from finalize_library import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]


class SourceStructureTests(unittest.TestCase):
    def fixture(self):
        text="📖 Frühling\n\n5 2 Wenn\n\nDie Sonne - *\n\n91"
        p={"id":"verse","title":"Kalender","text":text,"source_text":"Original remains unchanged","checksum":sha(text),"ga_page":None,"metadata":{"annotations":[{"id":"EPUB/chapter.xhtml#note","marker":"*","text":"*\nOriginal note ↩"}]}}
        plan={"input_sha256":sha(text),"group_title":"Seelenkalender","segments":[
            {"kind":"heading","parts":[0],"level":1},
            {"kind":"heading","parts":[{"block":1,"end":3}],"level":3},
            {"kind":"verse","parts":[{"block":1,"start":4},2],"join":"\n","pages":[91]}],
            "edits":[{"old":"5 2","new":"52","evidence":"Verified sequence label"}],
            "typographic_dashes":"Reviewed literary punctuation profile",
            "omitted_parts":[{"block":3,"page":91,"evidence":"Observed original page footer"}],
            "annotations":{"EPUB/chapter.xhtml#note":{"text":"Original note","reference_context":"Die Sonne – *"}}}
        payload={"work_id":"fixture","source_sha256":"doc","source_epub_sha256":"epub","passages":[p]}
        recipe={"work_id":"fixture","source_sha256":"doc","source_epub_sha256":"epub","source_url":"https://example.org/original","passages":{"verse":plan}}
        return payload,recipe

    def test_complete_structure_preserves_text_source_and_exact_note_anchor(self):
        payload,recipe=self.fixture()
        result,changes=apply_recipe(payload,recipe)
        p=result['passages'][0]
        self.assertEqual(p['text'],"📖 Frühling\n\n52\n\nWenn\nDie Sonne – *")
        self.assertEqual(p['source_text'],payload['passages'][0]['source_text'])
        self.assertEqual(payload['passages'][0]['text'],"📖 Frühling\n\n5 2 Wenn\n\nDie Sonne - *\n\n91")
        note=p['metadata']['annotations'][0]
        self.assertEqual(p['text'].encode('utf-16-le')[2*note['start_offset']:2*note['end_offset']].decode('utf-16-le'),'*')
        self.assertEqual(p['metadata']['page_anchors'][0]['page'],91)
        self.assertEqual(len(changes),1)

    def test_source_drift_missing_coverage_overlap_and_unproven_repair_fail_closed(self):
        for mutation in ['source','text','lost','duplicate','repair','note']:
            payload,recipe=self.fixture()
            plan=recipe['passages']['verse']
            if mutation=='source':payload['source_sha256']='different'
            if mutation=='text':payload['passages'][0]['text']+=' edited'
            if mutation=='lost':plan['segments'].pop(0)
            if mutation=='duplicate':plan['segments'].append(deepcopy(plan['segments'][0]))
            if mutation=='repair':plan['edits'][0]['evidence']=''
            if mutation=='note':plan['annotations']['EPUB/chapter.xhtml#note']['reference_context']='Unknown *'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):apply_recipe(payload,recipe)

    def test_idempotence_and_surrogate_boundary_rejection(self):
        payload,recipe=self.fixture()
        result,_=apply_recipe(payload,recipe)
        recipe['passages']['verse']['output_sha256']=result['passages'][0]['checksum']
        final,_=apply_recipe(payload,recipe)
        repeated,changes=apply_recipe(final,recipe)
        self.assertEqual(final,repeated)
        self.assertEqual(changes,[])
        final['passages'][0]['metadata']['reading_blocks'][0]['end_offset']=1
        with self.assertRaises(ValueError):validate_layout(final['passages'][0])

    def test_pages_follow_parts_and_survive_length_changing_repairs(self):
        payload,recipe=self.fixture()
        segment=recipe['passages']['verse']['segments'][-1]
        segment.pop('pages')
        segment['page_evidence']=[
            {'page':90,'part_index':0,'start_codepoint':0,'confidence':'observed_footer','source_section':1},
            {'page':91,'part_index':1,'start_codepoint':4,'confidence':'observed_footer','source_section':2}]
        recipe['passages']['verse']['edits'].append({'old':'Die Sonne','new':'Die strahlende Sonne','evidence':'Verified fixture spelling'})
        recipe['passages']['verse']['annotations']['EPUB/chapter.xhtml#note']['reference_context']='Die strahlende Sonne – *'
        result,_=apply_recipe(payload,recipe)
        passage=result['passages'][0]
        anchors=passage['metadata']['page_anchors']
        encoded=passage['text'].encode('utf-16-le')
        self.assertEqual(encoded[2*anchors[0]['start_offset']:].decode('utf-16-le').splitlines()[0],'Wenn')
        self.assertEqual(encoded[2*anchors[1]['start_offset']:].decode('utf-16-le'),'Sonne – *')
        self.assertGreater(anchors[1]['start_offset'],anchors[0]['start_offset'])

    def test_recipe_revision_uses_guarded_input_and_keeps_prior_history(self):
        from proofread_library import apply_stage
        payload,recipe=self.fixture()
        rendered,_=apply_recipe(payload,recipe)
        recipe['passages']['verse']['output_sha256']=rendered['passages'][0]['checksum']
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'root'
            baseline=Path(directory)/'baseline'
            for folder in ['content','library','proofreading/works']:(root/folder).mkdir(parents=True)
            (baseline/'content').mkdir(parents=True)
            path=root/'content/fixture.json.gz'
            write_json(path,payload)
            write_json(baseline/'content/fixture.json.gz',payload)
            source_hash=hashlib.sha256(path.read_bytes()).hexdigest()
            write_json(root/'library/catalog.json',{'works':[{'id':'fixture','content_path':'fixture',
                'passages':[{'id':'verse','checksum':payload['passages'][0]['checksum'],'ga_page':None}]}]})
            write_json(root/'proofreading/works/fixture.json',{'work':{'id':'fixture','available':True,
                'before_sha256':source_hash,'after_sha256':source_hash,'passage_count':1,'newlines_removed':0},'changes':[],'flags':[]})
            write_json(root/'proofreading/catalog.json',{'generated_at':'stable'})
            first=Path(directory)/'first'
            stage(root,first,recipe,baseline)
            apply_stage(root,first)
            prior_hash=hashlib.sha256(path.read_bytes()).hexdigest()
            recipe['passages']['verse']['group_title']='Reviewed new heading'
            second=Path(directory)/'second'
            stage(root,second,recipe,baseline)
            report=read_json(second/'proofreading/works/fixture.json')
            self.assertEqual(report['work']['application_base_sha256'],prior_hash)
            self.assertEqual(report['work']['layout_input_sha256'],source_hash)
            self.assertEqual(len(report['structure_history']),1)
            self.assertEqual(len(report['structure_history'][0]['changes']),1)
            self.assertEqual(len(report['changes']),1)
            apply_stage(root,second)
            self.assertEqual(read_json(path)['passages'][0]['metadata']['group_title'],'Reviewed new heading')
            tampered=read_json(path)
            tampered['passages'][0]['source_text']='Unreviewed source change'
            write_json(path,tampered)
            recipe['passages']['verse']['group_title']='Another revision'
            with self.assertRaises(ValueError):stage(root,Path(directory)/'rejected',recipe,baseline)
            self.assertEqual(read_json(path),tampered)

    def test_real_ga040_recipe_keeps_all_38_ids_and_52_weeks(self):
        before_path=ROOT/'research/proofreading-layout-baseline/content/ga-040.json.gz'
        if not before_path.exists():self.skipTest('Local pre-layout research baseline not available')
        before=read_json(before_path)
        recipe=read_json(ROOT/'tools/ga040_structure.json')
        result,changes=apply_recipe(before,recipe)
        self.assertEqual([p['id'] for p in before['passages']],[p['id'] for p in result['passages']])
        self.assertEqual([p['source_text'] for p in before['passages']],[p['source_text'] for p in result['passages']])
        first=result['passages'][0]
        labels=[]
        for block in first['metadata']['reading_blocks']:
            text=first['text'].encode('utf-16-le')[2*block['start_offset']:2*block['end_offset']].decode('utf-16-le')
            if block['kind']=='heading' and text.isdigit():labels.append(int(text))
        self.assertEqual(labels,list(range(1,53)))
        self.assertIn('Gerade deshalb aber wird auch jede Seele',first['text'])
        self.assertNotIn('WinterhorTnung',first['text'])
        self.assertNotIn('heiPge',first['text'])
        self.assertEqual(len([entry for entry in result['table_of_contents'] if entry['level']==1]),5)
        calendar_sections=first['metadata']['reading_sections']
        self.assertEqual([s['title'] for s in calendar_sections],[first['title'],'VORWORT ZUR ZWEITEN AUSGABE 1918','FRÜHLING','SOMMER','HERBST','WINTER'])
        calendar_toc=[e for e in result['table_of_contents'] if e['passage_id']==first['id']]
        roots=[e for e in calendar_toc if e['level']==2]
        self.assertEqual([e['title'] for e in roots],[s['title'] for s in calendar_sections])
        self.assertEqual(len({e['parent_id'] for e in roots}),1)
        self.assertEqual(len([e for e in calendar_toc if e['level']==4 and e['title'].isdigit()]),52)
        self.assertTrue(all(e['level']==3 for e in calendar_toc if 'April' in e['title']))
        reviewed=read_json(ROOT/'tools/ga040_poem_boundaries.json')
        noncalendar=[p for p in result['passages'] if p['id']!='ga-040-doc-heading-2']
        self.assertEqual(sum(bool(block.get('poem_start')) for p in noncalendar for block in p['metadata']['reading_blocks']),142)
        columns=next(p for p in result['passages'] if p['id']=='ga-040-doc-heading-9')
        blocks=columns['metadata']['reading_blocks']
        couplets=[columns['text'][b['start_offset']:b['end_offset']] for b in blocks[:6] if b['kind']=='verse']
        self.assertEqual([text.splitlines()[0] for text in couplets],[
            'Im reinen Gedanken findest du', 'Wandelst zum Bilde du den Gedanken,',
            'Verdichtest du das Gefühl zum Licht,', 'Verdinglichst du den Willen zum Wesen,'])
        self.assertTrue(all(len(text.splitlines())==2 for text in couplets))
        self.assertTrue(blocks[2].get('poem_start'))
        self.assertTrue(blocks[5].get('poem_start'))
        self.assertEqual(next(a for a in columns['metadata']['page_anchors'] if a['page']==75)['start_offset'],blocks[6]['start_offset'])
        sections=columns['metadata']['reading_sections']
        self.assertEqual(len(sections),7)
        self.assertEqual([s['label_kind'] for s in sections],['source_title','incipit','incipit','source_title','incipit','incipit','incipit'])
        self.assertEqual([(s['start_offset'],s['end_offset']) for s in sections],[(0,285),(287,464),(466,569),(571,857),(859,1035),(1037,1125),(1127,1414)])
        works=[e for e in result['table_of_contents'] if e['passage_id']==columns['id'] and e['level']==2]
        self.assertEqual([e['title'] for e in works],[s['title'] for s in sections])
        self.assertEqual(len({e['parent_id'] for e in works}),1)
        self.assertEqual(sum(e['title']=='TISCHGEBET' for e in result['table_of_contents']),1)
        for invalid in [dict(sections[1],title='An invented title'),dict(sections[1],start_offset=288),dict(sections[1],end_offset=465)]:
            malformed=deepcopy(columns)
            malformed['metadata']['reading_sections'][1]=invalid
            with self.assertRaises(ValueError):validate_layout(malformed)
        for continuation in reviewed['excluded_continuations']:
            passage=next(p for p in result['passages'] if p['id']==continuation['passage_id'])
            for segment,block in zip(recipe['passages'][passage['id']]['segments'],passage['metadata']['reading_blocks']):
                first=segment['parts'][0]
                original_index=first if type(first) is int else first['block']
                if original_index==continuation['block_index']:
                    self.assertFalse(block.get('poem_start',False),continuation['evidence'])
        for suffix,page,left,right in [('heading-6',42,'wer','den'),('heading-41',275,'Reli','gion')]:
            passage=next(p for p in result['passages'] if p['id'].endswith(suffix))
            anchor=next(a for a in passage['metadata']['page_anchors'] if a['page']==page)
            encoded=passage['text'].encode('utf-16-le')
            self.assertTrue(encoded[:2*anchor['start_offset']].decode('utf-16-le').endswith(left))
            self.assertTrue(encoded[2*anchor['start_offset']:].decode('utf-16-le').startswith(right))
        second,events=apply_recipe(result,recipe)
        self.assertEqual(result,second)
        self.assertEqual(events,[])


if __name__=='__main__':unittest.main()
