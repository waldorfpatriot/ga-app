#!/usr/bin/env python3
"""GA033 source, original contents hierarchy and exact layout regression checks."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import re
import unittest

from build_ga033_recipe import BASELINE, SOURCE, REVIEW, RECIPE, ADDED_ID, build, check_source, augment_original
from finalize_library import read_json
from repair_ga033_readability import apply_layout
from repair_source_structure import sha, validate_layout


class GA033ReadabilityTests(unittest.TestCase):
    maxDiff = 1000

    @classmethod
    def setUpClass(cls):
        cls.before = read_json(BASELINE)
        cls.review = read_json(REVIEW)
        cls.recipe = read_json(RECIPE)
        cls.after, cls.changes = apply_layout(cls.before, cls.recipe)
        cls.passages = {p['id']: p for p in cls.after['passages']}

    def text_blocks(self, pid, kind):
        passage = self.passages[pid]
        encoded = passage['text'].encode('utf-16-le')
        return [encoded[2*b['start_offset']:2*b['end_offset']].decode('utf-16-le')
                for b in passage['metadata']['reading_blocks'] if b['kind'] == kind]

    def test_review_rebuilds_complete_source_inventory(self):
        self.assertEqual(build(self.before), self.recipe)
        self.assertEqual(len(self.before['passages']), 15)
        self.assertEqual(len(self.after['passages']), 16)
        self.assertEqual(sum(len(p['source_parts']) for p in self.review['passages'].values()), 825)
        self.assertEqual(sum(len(p['metadata']['reading_blocks']) for p in self.after['passages']), 459)
        for old in self.before['passages']:
            new = self.passages[old['id']]
            self.assertEqual(old['source_text'], new['source_text'])
            self.assertEqual(old['source_member'], new['source_member'])
            self.assertEqual(old['source_label'], new['source_label'])
        self.assertEqual(self.before['content_completeness'], self.after['content_completeness'])
        self.assertEqual(self.before['source_sha256'], self.after['source_sha256'])
        self.assertEqual(self.before['source_epub_sha256'], self.after['source_epub_sha256'])
        for passage in self.after['passages']:
            validate_layout(passage)
            self.assertEqual(sha(passage['text']), passage['checksum'])

    def test_only_the_exact_author_subsection_is_added(self):
        new = self.passages[ADDED_ID]
        addition = self.recipe['source_additions'][0]
        self.assertEqual(new['source_text'], addition['source_text'])
        self.assertEqual(addition['source_pdf_pages'], [265, 266, 267, 268])
        ids = [p['id'] for p in self.after['passages']]
        self.assertEqual(ids[ids.index(ADDED_ID)-1], 'ga-033-doc-heading-16')
        self.assertEqual(ids[ids.index(ADDED_ID)+1], 'ga-033-doc-heading-17')
        self.assertIn('Frauenstädt', new['text'])
        self.assertIn('Schopenhauerschen', new['text'])
        self.assertIn('Gwinners', new['text'])
        self.assertNotIn('Frauen-städt', new['text'])
        old_exclusions = self.before['proofing']['excluded_sections']
        self.assertEqual(self.after['proofing']['source_import_excluded_sections'], old_exclusions)
        self.assertEqual(len(self.after['proofing']['excluded_sections']), 2)
        expected = deepcopy(self.before['proofing'])
        expected['source_import_excluded_sections'] = old_exclusions
        expected['excluded_sections'] = self.recipe['proofing_repairs']['excluded_sections']['after']
        self.assertEqual(expected, self.after['proofing'])
        self.assertEqual(len([e for e in self.changes if e['rule'] == 'source_restoration']), 1)

    def test_original_contents_main_and_child_hierarchy(self):
        toc = self.after['table_of_contents']
        self.assertEqual(len(toc), 79)
        self.assertEqual(Counter(r['level'] for r in toc), {1: 4, 2: 9, 3: 66})
        self.assertEqual([r['title'] for r in toc if r.get('source_role') == 'group'],
                         ['BIOGRAPHISCHE SKIZZEN', 'VIER BIOGRAPHIEN'])
        mains = [r for r in toc if r['level'] == 2]
        self.assertEqual(len(mains), 9)
        jacobowski = next(r for r in mains if r['id'] == 'ga-033-jacobowski')
        self.assertEqual(jacobowski['title'], 'Ludwig Jacobowski. Ein Lebens- und Charakterbild des Dichters')
        self.assertFalse(any(r['title'] == 'Ein Lebens- und Charakterbild des Dichters' for r in toc))
        bibliography = next(r for r in toc if r['title'] == 'Bibliographisches und Textbehandlung')
        self.assertEqual((bibliography['level'], bibliography['parent_id'], bibliography['passage_id']),
                         (3, 'ga-033-schopenhauer', ADDED_ID))
        self.assertTrue(all(r['level'] == 3 and r['parent_id'] == 'ga-033-lyrik'
                            for r in toc if '-roman-' in r['id']))

    def test_front_contents_are_separate_and_no_retained_entry_is_lost(self):
        rows = self.review['original_contents_rows']
        self.assertEqual(len(rows), 69)
        for number, label in [(1, 'Biographische Skizzen'), (2, 'Vier Biographien')]:
            pid = f'ga-033-doc-heading-{number}'
            p = self.passages[pid]
            self.assertEqual(p['title'], 'Inhalt — ' + label)
            self.assertEqual(self.review['passages'][pid]['source_role'], 'table_of_contents')
            self.assertEqual(p['text'], self.review['passages'][pid]['restored_contents_text'])
            self.assertFalse(any(token in p['text'] for token in ['}$', '2^0', '26$', '26p', '33 j', '3 jp', 'Oberblick']))
        front = '\n'.join(self.passages[f'ga-033-doc-heading-{n}']['text'] for n in (1, 2))
        self.assertTrue(all(row['display_text'] in front for row in rows))
        self.assertIn('Einfluß Goethes (250)', front)
        self.assertIn('Bibliographisches und Textbehandlung (265)', front)

    def test_all_four_printed_internal_paragraphs_are_restored(self):
        expected = [('ga-033-doc-heading-4', 'Von nicht geringerer Bedeutung war die Pflege des'),
                    ('ga-033-doc-heading-8', 'Im echtesten Sinne des Wortes eine Nachblüte'),
                    ('ga-033-doc-heading-16', 'Im Jahre 1793 wurde die bis dahin freie Stadt Danzig'),
                    ('ga-033-doc-heading-17', 'Ganz in die Unbestimmtheit der Gefühlsschwelgerei')]
        for pid, opening in expected:
            self.assertTrue(any(block.startswith(opening) for block in self.text_blocks(pid, 'prose')), (pid, opening))
        first = self.passages['ga-033-doc-heading-4']['text']
        self.assertIn('Neigungen und Leidenschaften der Mensehen', first)
        self.assertNotIn('Men- sehen', first)
        self.assertIn('Natur- und Menschenlebens', first)
        self.assertIn('furchtbar-sdimerzliche', self.passages['ga-033-doc-heading-6']['text'])

    def test_all_true_verse_lines_and_page_continuation(self):
        verse = [block for p in self.after['passages'] for block in self.text_blocks(p['id'], 'verse')]
        self.assertEqual(len(verse), 9)
        self.assertEqual(sum(len(block.splitlines()) for block in verse), 54)
        self.assertTrue(any(block.splitlines()[-1] == 'Nachtumhüllt.' for block in verse))
        twelve = next(block for block in verse if block.startswith('Die Sonne breitet ihren Segen'))
        self.assertEqual(len(twelve.splitlines()), 12)
        self.assertNotIn('\n\n', twelve)
        self.assertTrue(any(block == 'Ihr sollt sprechen: willekommen!»' for block in verse))
        self.assertTrue(any(block.startswith('Nidit in kalten') for block in verse))

    def test_annotation_whitespace_and_all_source_characters(self):
        repair = self.recipe['annotation_repairs'][0]
        self.assertEqual(len(self.recipe['annotation_repairs']), 1)
        self.assertEqual(repair['before'].count('\n'), 3)
        self.assertEqual(re.sub(r'\s', '', repair['before']), re.sub(r'\s', '', repair['after']))
        note = self.passages[repair['passage_id']]['metadata']['annotations'][0]
        self.assertEqual(note['text'], repair['after'])
        self.assertEqual(note['text'].count('↩'), 2)
        augmented = augment_original(self.before, self.recipe)
        for old in augmented['passages'][2:]:
            expected = Counter(re.sub(r'\s', '', old['text']))
            for edit in self.recipe['passages'][old['id']]['edits']:
                expected.subtract(Counter(re.sub(r'\s', '', edit['old'])))
                expected.update(Counter(re.sub(r'\s', '', edit['new'])))
            self.assertEqual(+expected, Counter(re.sub(r'\s', '', self.passages[old['id']]['text'])), old['id'])

    def test_repeated_layout_is_idempotent_and_rejects_reading_or_toc_drift(self):
        repeated, events = apply_layout(self.after, self.recipe)
        self.assertEqual(repeated, self.after)
        self.assertEqual(events, [])
        for mutate in ('text', 'toc'):
            bad = deepcopy(self.after)
            if mutate == 'text': bad['passages'][2]['text'] += 'x'
            else: bad['table_of_contents'][3]['title'] = 'Unbelegter Aufsatz'
            with self.assertRaises(ValueError): apply_layout(bad, self.recipe)

    def test_rejects_source_drift_and_expanded_restoration(self):
        for mutate in ('source', 'addition'):
            bad = deepcopy(self.review)
            if mutate == 'source': bad['passages']['ga-033-doc-heading-1']['source_parts'][0]['source_paragraph_sha256'] = '0'*64
            else: bad['source_additions'][0]['source_segments'][0]['body_indices'].append(25)
            with self.assertRaises(ValueError): check_source(SOURCE, bad)

    def test_rejects_prose_contents_rewrite_and_wrong_printed_pixels(self):
        bad = deepcopy(self.review)
        passage = bad['passages']['ga-033-doc-heading-4']
        edit = deepcopy(bad['passages']['ga-033-doc-heading-1']['edits'][0])
        passage['source_role'] = 'table_of_contents'
        passage['restored_contents_text'] = edit['new']
        passage['edits'].append(edit)
        with self.assertRaises(ValueError): check_source(SOURCE, bad)
        bad = deepcopy(self.review)
        bad['passages']['ga-033-doc-heading-1']['edits'][0]['pdf_raster_witnesses'][0]['visible_page_pixels_sha256'] = '0'*64
        with self.assertRaises(ValueError): check_source(SOURCE, bad)


if __name__ == '__main__':
    unittest.main()
