#!/usr/bin/env python3
"""Original-source GA034 paragraph, contents, prose-recovery and note checks."""
from collections import Counter, defaultdict
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import tempfile
import unittest

from build_ga034_recipe import BASELINE, RECIPE, REVIEW, SOURCE, augment_original, build, check_source
from check_essay_layout import inspect_reviewed_essay_layout
from check_proofreading_samples import inspect_source_layout
from finalize_library import read_json
from repair_ga034_readability import apply_layout
from repair_source_structure import recipe_digest, sha, validate_layout


def block_text(passage, block):
    return passage['text'].encode('utf-16-le')[2*block['start_offset']:2*block['end_offset']].decode('utf-16-le')


class GA034ReadabilityTests(unittest.TestCase):
    maxDiff = 1200

    @classmethod
    def setUpClass(cls):
        cls.before = read_json(Path(os.environ.get('GA034_TEST_INPUT', str(BASELINE))))
        cls.recipe, cls.review = read_json(RECIPE), read_json(REVIEW)
        cls.after, cls.changes = apply_layout(cls.before, cls.recipe)
        cls.passages = {p['id']: p for p in cls.after['passages']}
        cls.events = defaultdict(list)
        for event in cls.changes:
            cls.events[event['passage_id']].append(event)

    def test_frozen_recipe_rebuilds_complete_retained_inventory(self):
        self.assertEqual(build(self.before), self.recipe)
        self.assertEqual(len(self.before['passages']), 7)
        self.assertEqual(sum(len(w['source_parts']) for w in self.review['passages'].values()), 1706)
        self.assertEqual(sum(len(p['metadata']['reading_blocks']) for p in self.after['passages']), 1053)
        self.assertEqual(self.review['whole_source_review']['printed_body_pages'], list(range(11,620)))

    def test_independent_full_source_reconstruction_and_projection(self):
        errors, repairs = inspect_reviewed_essay_layout(self.before, self.after, self.recipe,
            self.events, SOURCE, REVIEW, inspect_source_layout)
        self.assertEqual(errors, [])
        self.assertEqual(repairs, 63)

    def test_ids_sources_existing_note_fields_and_proofing_are_preserved(self):
        for before, after in zip(self.before['passages'], self.after['passages']):
            for key in ('id','source_text','source_member','source_label','ga_page'):
                self.assertEqual(before[key], after[key], key)
            expected = deepcopy(before['metadata']['annotations'])
            for repair in self.recipe['annotation_repairs']:
                if repair['passage_id'] == before['id']:
                    note = next(n for n in expected if n['id'] == repair['annotation_id'])
                    self.assertEqual(note['text'], repair['before'])
                    note['text'] = repair['after']
            self.assertEqual(after['metadata']['annotations'], expected)
            self.assertEqual(sha(after['text']), after['checksum'])
            validate_layout(after)
        for key in ('proofing','source_sha256','source_epub_sha256','passage_count','content_completeness'):
            self.assertEqual(self.before[key], self.after[key], key)

    def test_all_original_author_contents_targets_are_unique_and_grouped(self):
        author = [row for row in self.after['table_of_contents'] if row['source_role'] == 'author']
        self.assertEqual(len(author),106)
        self.assertEqual(len({(row['passage_id'],row['start_offset']) for row in author}),106)
        groups = [row for row in self.after['table_of_contents'] if row['source_role']=='group']
        self.assertEqual(len(groups),6)
        self.assertEqual([row['title'] for row in groups], ['AUFSÄTZE','FRAGEN UND ANTWORTEN',
            'DIE KULTUR DER GEGENWART IM SPIEGEL DER THEOSOPHIE - ZEITBILDER',
            'BEMERKUNGEN ZU AUFSÄTZEN','BESPRECHUNGEN THEOSOPHISCHER LITERATUR',
            'VON DER THEOSOPHISCHEN ARBEIT'])
        city = next(row for row in author if row['id']=='ga-034-original-toc-93')
        self.assertEqual((city['level'],city['parent_id']),(3,'ga-034-original-toc-92'))

    def test_front_is_coherent_full_original_contents_and_first_essay_is_accessible(self):
        first, second = self.after['passages'][:2]
        self.assertEqual(first['title'],'Inhalt')
        self.assertTrue(first['text'].startswith('Zur Einführung — S. 11\n\nAUFSÄTZE\n'))
        self.assertNotIn('Wissen schaft', first['text'])
        self.assertIn('Meditation — Juli 1903 — S. 33',first['text'])
        self.assertIn('Meditation — September 1903 — S. 66',first['text'])
        self.assertTrue(second['text'].startswith('VON DER THEOSOPHISCHEN ARBEIT\n'))
        self.assertIn('Übersicht über die Rudolf Steiner Gesamtausgabe — S. 661',second['text'])
        intro=next(row for row in self.after['table_of_contents'] if row['id']=='ga-034-original-toc-1')
        self.assertEqual((intro['passage_id'],intro['start_offset']),('ga-034-doc-heading-4',0))
        self.assertIn('ZUR EINFÜHRUNG',self.passages['ga-034-doc-heading-4']['title'])
        excluded = [row for row in self.review['original_toc_target_review'] if row['source_role']=='excluded_apparatus']
        self.assertEqual(len(excluded),5)
        self.assertTrue(all('target' not in row for row in excluded))

    def test_meditations_are_prose_and_original_poetic_lines_are_exact(self):
        verses=[]
        for passage in self.after['passages']:
            for block in passage['metadata']['reading_blocks']:
                if block['kind']=='verse':verses.append(block_text(passage,block))
        self.assertEqual(len(verses),7)
        self.assertEqual(sum(len(text.splitlines()) for text in verses),16)
        self.assertTrue(any('geboren\nUnd nicht in dir:' in text for text in verses))
        self.assertTrue(any('verloren.\nDas Kreuz zu Golgatha' in text for text in verses))
        self.assertIn('«Im reinen Gedanken findest du\ndas Selbst, das sich halten kann.»',verses)
        self.assertFalse(any('Selbsterkenntnis' in text for text in verses))

    def test_titles_subtitles_signatures_and_bibliography_are_not_extra_articles(self):
        titles=[row['title'] for row in self.after['table_of_contents']]
        self.assertFalse(any(title.startswith('Januar 1904') for title in titles))
        self.assertFalse(any('Generalsekretär der deutschen Sektion' in title for title in titles))
        self.assertFalse(any(title.startswith('Übersetzt von Marie') for title in titles))
        self.assertFalse(any(title.startswith('Die Blüte und die Frucht') for title in titles))
        p=self.passages['ga-034-doc-heading-10']
        self.assertIn('DIE ÜBERSINNLICHE WELT UND IHRE ERKENNTNIS',self.passages['ga-034-doc-heading-9']['text'])
        self.assertEqual(sum('Flita' in row['title'] for row in self.after['table_of_contents']),1)
        self.assertIn('Zum Beginn des neuen Jahrganges (Juni 1905)',self.passages['ga-034-doc-heading-9']['text'])
        self.assertNotIn('Juniipoj',self.passages['ga-034-doc-heading-9']['text'])

    def test_false_prose_heading_is_recovered_at_actual_word_seam_without_new_id(self):
        ninth=self.passages['ga-034-doc-heading-9'];tenth=self.passages['ga-034-doc-heading-10']
        self.assertIn('Anschauung anderer als nur aus Vorurteil und Aberglauben entspringen lassen.',ninth['text'])
        self.assertTrue(ninth['text'].endswith('die folgenden Sätze zu lesen sind:'))
        self.assertTrue(tenth['text'].startswith('«Hilfe gegen das undurchdringliche Dunkel'))
        self.assertEqual(tenth['title'],'VORURTEILE AUS VERMEINTLICHER WISSENSCHAFT')
        self.assertFalse(any(row['passage_id']==tenth['id'] and row['start_offset']==0 for row in self.after['table_of_contents']))
        self.assertEqual(len(self.recipe['source_additions']),1)
        self.assertEqual(len(self.recipe['source_additions'][0]['text']),235)
        self.assertEqual(self.events[ninth['id']][-1]['rule'],'source_restoration')

    def test_exact_footnote_wraps_and_all_reviewed_word_seams_preserve_letters(self):
        self.assertEqual(len(self.recipe['annotation_repairs']),12)
        self.assertEqual(sum(r['before'].count('\n')for r in self.recipe['annotation_repairs']),309)
        self.assertEqual(sum(len(r['word_joins'])for r in self.recipe['annotation_repairs']),18)
        for repair in self.recipe['annotation_repairs']:
            self.assertNotIn('\n',repair['after'])
            compact=lambda text:re.sub(r'\s','',text)
            self.assertEqual(compact(repair['before']).replace('anthroposophi-schen','anthroposophischen'),compact(repair['after']))
            self.assertEqual(repair['before'].count('↩'),repair['after'].count('↩'))
        self.assertEqual(len(self.review['known_gaps']),2)
        self.assertEqual([row['body_index']for row in self.review['known_gaps']],[43,48])
        self.assertEqual(sum(len(p['metadata']['annotations'])for p in self.after['passages']),12)

    def test_footer_removal_and_historical_ocr_do_not_become_spelling_modernization(self):
        self.assertEqual(sum(len(p.get('omissions',[]))for p in self.review['passages'].values()),9)
        seams=[e for p in self.recipe['passages'].values()for e in p['edits']if e['kind']=='physical_word_seam']
        self.assertEqual(len(seams),51)
        self.assertTrue(any(e['new']=='TatSachen' for e in seams))
        self.assertTrue(any(e['new']=='PhiloSophie' for e in seams))
        self.assertTrue(any(e['new']=='Vorstelhingen' for e in seams))
        self.assertTrue(any(e['new']=='Dilettantismus' for e in seams))
        self.assertIn('Pflanzen- und',self.passages['ga-034-doc-heading-5']['text'])
        self.assertIn('Mut- und',self.passages['ga-034-doc-heading-4']['text'])

    def test_reapplication_is_exact_and_emits_no_events(self):
        rendered,events=apply_layout(self.after,self.recipe)
        self.assertEqual(rendered,self.after)
        self.assertEqual(events,[])

    def test_source_text_note_and_recovery_anchor_drift_fail_closed(self):
        for field in ('source_text','text'):
            altered=deepcopy(self.before);altered['passages'][3][field]+='X'
            with self.assertRaises(ValueError):apply_layout(altered,self.recipe)
        altered=deepcopy(self.before);altered['passages'][4]['metadata']['annotations'][0]['text']+=' '
        with self.assertRaises(ValueError):apply_layout(altered,self.recipe)
        altered=deepcopy(self.before);altered['passages'][-2]['text']=altered['passages'][-2]['text'][:-1]+' '
        with self.assertRaises(ValueError):apply_layout(altered,self.recipe)

    def test_source_witness_and_unknown_edit_type_fail_closed(self):
        review=deepcopy(self.review);review['passages']['ga-034-doc-heading-4']['starts'][0]['source_paragraph_sha256']='0'*64
        with self.assertRaises(ValueError):check_source(SOURCE,review)
        review=deepcopy(self.review);review['passages']['ga-034-doc-heading-5']['edits'][0]['kind']='spelling_modernization'
        with self.assertRaises(ValueError):check_source(SOURCE,review)

    def test_rendered_extra_navigation_article_and_note_text_drift_are_rejected(self):
        altered=deepcopy(self.after);row=deepcopy(altered['table_of_contents'][-1]);row['id']='invented-signature';altered['table_of_contents'].append(row)
        errors,_=inspect_reviewed_essay_layout(self.before,altered,self.recipe,self.events,SOURCE,REVIEW,inspect_source_layout)
        self.assertTrue(errors)
        altered=deepcopy(self.after);altered['passages'][4]['metadata']['annotations'][0]['text']+=' invented'
        errors,_=inspect_reviewed_essay_layout(self.before,altered,self.recipe,self.events,SOURCE,REVIEW,inspect_source_layout)
        self.assertTrue(errors)


if __name__=='__main__':
    unittest.main()
