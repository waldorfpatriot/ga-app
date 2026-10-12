#!/usr/bin/env python3
"""GA030 regression checks for exact restorations and source-bound layout."""
from copy import deepcopy
import gzip
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from build_ga030_recipe import BASELINE, RECIPE, REVIEW, SOURCE, ORIGINAL_IDS, build, check_source, augment_original
from finalize_library import read_json, write_json
from repair_ga030_readability import apply_layout, stage
from repair_source_structure import sha, validate_layout


class GA030ReadabilityTests(unittest.TestCase):
    maxDiff = 1200

    def assertContains(self, needle, text):
        self.assertTrue(needle in text, 'Missing reviewed excerpt: ' + needle)

    def assertAbsent(self, needle, text):
        self.assertFalse(needle in text, 'Unexpected excerpt: ' + needle)

    @classmethod
    def setUpClass(cls):
        cls.before = read_json(BASELINE)
        cls.recipe = read_json(RECIPE)
        cls.review = read_json(REVIEW)
        cls.after, cls.changes = apply_layout(cls.before, cls.recipe)
        cls.passages = {p['id']:p for p in cls.after['passages']}

    def test_recipe_rebuilds_from_exact_epub_and_review(self):
        self.assertEqual(build(self.before), self.recipe)
        self.assertEqual(len(self.recipe['source_additions']), 9)
        self.assertEqual(len(self.after['passages']), 7)
        self.assertEqual(len(self.review['completeness_review']['original_sections']), 92)
        self.assertEqual(len(self.after['table_of_contents']), 101)
        self.assertEqual(sum(s.get('pdf_internal_override', False) for p in self.review['passages'].values() for s in p['starts']), 24)
        self.assertEqual(sum(len(p.get('omitted_parts', [])) for p in self.recipe['passages'].values()), 15)

    def test_original_sources_and_annotations_are_preserved(self):
        self.assertEqual([p['id'] for p in self.before['passages']], ORIGINAL_IDS)
        for before in self.before['passages']:
            after = self.passages[before['id']]
            self.assertEqual(before['source_text'], after['source_text'])
            self.assertEqual(before['title'], after['title'])
            self.assertEqual(after['metadata']['annotations'][:len(before['metadata']['annotations'])], before['metadata']['annotations'])
        notes = self.passages[ORIGINAL_IDS[2]]['metadata']['annotations']
        self.assertEqual(len(notes), len(self.before['passages'][2]['metadata']['annotations']) + 1)
        self.assertEqual(notes[-1]['id'], 'EPUB/chapter-0011.xhtml#footnote-recovered-116')
        self.assertEqual(notes[-1]['marker'], '**')
        self.assertNotIn('↩', notes[-1]['text'])
        for passage in self.after['passages']:
            self.assertEqual(sha(passage['text']), passage['checksum'])
            validate_layout(passage)

    def test_restored_year_and_pages_keep_download_contract(self):
        passage = self.passages[ORIGINAL_IDS[1]]
        self.assertContains('Leiden 1895 eine Debatte', passage['text'])
        self.assertContains('[1895]', passage['source_text'])
        self.assertNotIn(1895, passage['metadata']['page_numbers'])
        self.assertTrue(all(a['page'] < 659 for p in self.after['passages'] for a in p['metadata']['page_anchors']))
        self.assertEqual(self.after['content_completeness'], 'complete')
        gap = self.after['proofing']['known_source_gaps'][0]
        self.assertEqual(gap['toc_page'], 659)
        self.assertFalse(gap['present_in_epub'])
        self.assertFalse(gap['present_in_pdf'])
        self.assertEqual(gap['role'], 'publisher_back_matter')
        self.assertEqual(self.after['proofing']['excluded_sections'], [])
        self.assertEqual(self.after['proofing']['source_import_excluded_sections'], self.before['proofing']['excluded_sections'])

    def test_true_interior_paragraphs_and_word_seams(self):
        intro = self.passages['ga-030-introduction']['text']
        self.assertContains('\n\nNichts anderes als', intro)
        self.assertAbsent('Philo- sophie', intro)
        main = self.passages[ORIGINAL_IDS[2]]['text']
        self.assertContains('\n\nDer Geist, in dessen Schaffen', main)
        self.assertContains('zusammenhängender', main)
        self.assertAbsent('charak- terisiert', main)
        self.assertContains('charakterisiert', main)
        self.assertContains('Begriffs-Sammlung', main)
        self.assertContains('Begriffs-Systeme', self.passages[ORIGINAL_IDS[1]]['text'])

    def test_article_sections_cover_all_text_and_register_keeps_references(self):
        for passage in self.after['passages']:
            sections = passage['metadata']['reading_sections']
            self.assertEqual(sections[0]['start_offset'], 0)
            self.assertEqual(sections[-1]['end_offset'], len(passage['text'].encode('utf-16-le')) // 2)
        register = self.passages['ga-030-name-index']
        self.assertIn('220-', register['text'])
        self.assertIn('221', register['text'])
        self.assertIn('109', register['text'])
        self.assertGreater(len(register['metadata']['reading_blocks']), 200)
        self.assertTrue(any('\n' in register['text'].encode('utf-16-le')[b['start_offset']*2:b['end_offset']*2].decode('utf-16-le') for b in register['metadata']['reading_blocks']))

    def test_idempotence_and_unreviewed_input_fail_closed(self):
        repeated, changes = apply_layout(self.after, self.recipe)
        self.assertEqual(repeated, self.after)
        self.assertEqual(changes, [])
        for mutation in ('text', 'source_text', 'inventory', 'addition', 'year_metadata', 'coverage'):
            before, recipe = deepcopy(self.before), deepcopy(self.recipe)
            if mutation == 'text': before['passages'][0]['text'] += ' fremd'
            elif mutation == 'source_text': before['passages'][0]['source_text'] += ' fremd'
            elif mutation == 'inventory': before['passages'].pop()
            elif mutation == 'addition': recipe['source_additions'][0]['text'] += ' erfunden'
            elif mutation == 'year_metadata': before['passages'][1]['ga_page'] = 'S. 183'
            else: recipe['passages'][ORIGINAL_IDS[0]]['segments'].pop()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                apply_layout(before, recipe)
        review = deepcopy(self.review)
        review['source_additions'][-1]['source_token'] = '[1896]'
        with self.assertRaises(ValueError): check_source(SOURCE, review)

    def test_stage_binds_current_gzip_and_preserved_input_separately(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, baseline, output = [Path(temporary) / name for name in ('root', 'baseline', 'stage')]
            for folder in ('content', 'library', 'proofreading/works'):
                (root / folder).mkdir(parents=True)
            original = root / 'content/ga-030.json.gz'
            original.write_bytes(gzip.compress(gzip.decompress(BASELINE.read_bytes()), compresslevel=1, mtime=123))
            application_hash = hashlib.sha256(original.read_bytes()).hexdigest()
            write_json(root / 'proofreading/works/ga-030.json', {'work': {'after_sha256':application_hash,'checks':[]}, 'changes':[]})
            write_json(root / 'proofreading/catalog.json', {'generated_at':'unchanged'})
            write_json(root / 'library/catalog.json', {'works':[{'id':'ga-030','content_path':'content/ga-030.json.gz','content_completeness':'complete','passages':[{'id':p['id']} for p in self.before['passages']]}]})
            with patch('proofread_library.complete_stage'), patch('repair_ga030_readability.verify'):
                stage(root, output, self.recipe, baseline)
            saved = baseline / 'content/ga-030.json.gz'
            frozen_hash = hashlib.sha256(saved.read_bytes()).hexdigest()
            self.assertNotEqual(application_hash, frozen_hash)
            report = read_json(output / 'proofreading/works/ga-030.json')['work']
            self.assertEqual(report['application_base_sha256'], application_hash)
            self.assertEqual(report['layout_input_sha256'], frozen_hash)
            work = read_json(output / 'library/catalog.json')['works'][0]
            self.assertEqual(work['content_completeness'], 'complete')
            self.assertEqual(work['content_path'], 'content/ga-030.json.gz')
            self.assertEqual(work['catalog_passage_count'], 7)
            repeated = Path(temporary) / 'repeat'
            with patch('proofread_library.complete_stage'), patch('repair_ga030_readability.verify'):
                self.assertEqual(stage(output, repeated, self.recipe, baseline), [])
            self.assertEqual(read_json(repeated / 'content/ga-030.json.gz'), self.after)


if __name__ == '__main__':
    unittest.main()
