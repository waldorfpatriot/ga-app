#!/usr/bin/env python3
"""Complete GA036 source reconstruction and independent meaningful tamper checks."""
from collections import defaultdict
from copy import deepcopy
import unittest
from build_ga036_recipe import ROOT, BASELINE, RECIPE, REVIEW, SOURCE, build
from repair_ga036_readability import apply_layout
from finalize_library import read_json
from check_essay_layout import inspect_reviewed_essay_layout
from check_proofreading_samples import inspect_source_layout

class GA036ReadabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = read_json(BASELINE if BASELINE.exists() else ROOT / 'server/priv/content/ga-036.json.gz')
        cls.recipe = read_json(RECIPE)
        cls.after, changes = apply_layout(cls.before, cls.recipe)
        cls.events = defaultdict(list)
        for event in changes:
            cls.events[event['passage_id']].append({k: v for k, v in event.items() if k != 'passage_id'})

    def inspect(self, *, after=None, recipe=None, events=None):
        return inspect_reviewed_essay_layout(self.before, after or self.after, recipe or self.recipe,
            events or self.events, SOURCE, REVIEW, inspect_source_layout)

    def passage(self, number):
        return next(p for p in self.after['passages'] if p['id'] == f'ga-036-doc-heading-{number}')

    @staticmethod
    def block_text(passage, block):
        return passage['text'].encode('utf-16-le')[block['start_offset'] * 2:block['end_offset'] * 2].decode('utf-16-le')

    def test_complete_original_source_coverage_and_idempotence(self):
        errors, _ = self.inspect()
        self.assertEqual(errors, [])
        self.assertEqual(len(self.after['passages']), 51)
        self.assertEqual([(p['id'], p['source_text']) for p in self.before['passages']],
                         [(p['id'], p['source_text']) for p in self.after['passages']])
        again, changes = apply_layout(self.after, self.recipe)
        self.assertEqual(again, self.after)
        self.assertEqual(changes, [])

    def test_original_contents_groups_dates_pages_and_nested_subparts(self):
        toc = self.after['table_of_contents']
        self.assertEqual(len(toc), 95)
        self.assertEqual(sum(t['source_role'] == 'article' for t in toc), 77)
        self.assertEqual(sum(t['source_role'] == 'subpart' for t in toc), 12)
        self.assertEqual([t['title'] for t in toc if t['source_role'] == 'group'], [
            'Zur Weltlage', 'Beiträge zur Wiederbelebung des verschütteten Geisteslebens — Goethe-Studien',
            'Buchbesprechungen', 'Anthroposophie — Das Goetheanum und seine Arbeit', 'Vom Seelenleben'])
        first = self.passage(1)
        self.assertEqual(first['title'], 'Inhalt')
        self.assertTrue(first['text'].startswith('Inhalt\n\nZur Weltlage'))
        self.assertIn('I. Jahrgang Nr. 1, 21. August 1921 — S. 11', first['text'])
        self.assertIn('17. Dezember 1922 — S. 282', first['text'])
        self.assertNotIn('6z', first['text'])
        self.assertEqual(sum(t.get('parent_id') == 'ga-036-seelenleben' for t in toc), 4)
        self.assertTrue(all(t.get('parent_id') for t in toc if t['source_role'] == 'subpart'))

    def test_full_printed_verse_lines_stanzas_and_stage_directions(self):
        verses = [self.block_text(p, b) for p in self.after['passages']
                  for b in p['metadata']['reading_blocks'] if b['kind'] == 'verse']
        self.assertEqual([len(v.splitlines()) for v in verses],
            [56,2,5,8,4,4,6,6,6,6,6,6,6,6,6,16,5,4,4,10,11,1,10,1])
        self.assertEqual(sum(len(v.splitlines()) for v in verses), 195)
        drama = self.passage(39)
        stage = [self.block_text(drama, b) for b in drama['metadata']['reading_blocks'] if b['kind'] == 'note']
        self.assertIn('(Pause)', stage)
        self.assertIn('(stark)', stage)
        self.assertIn('Nimm denn!', verses)
        self.assertTrue(all(t['title'] not in ('Thamal', '(Pause)', '(stark)') for t in self.after['table_of_contents']))

    def test_five_exact_notes_restore_in_source_order_with_words_preserved(self):
        notes = [n for p in self.after['passages'] for n in p['metadata']['annotations']]
        self.assertEqual(len(notes), 12)
        self.assertEqual(sum('source_restoration' in n for n in notes), 5)
        self.assertTrue(all('\n' not in n['text'] for n in notes))
        for prior, final in zip(self.before['passages'], self.after['passages']):
            original_ids = [n['id'] for n in prior['metadata']['annotations']]
            self.assertEqual([n['id'] for n in final['metadata']['annotations'] if n['id'] in original_ids], original_ids)
        self.assertTrue(all(n['text'].endswith('↩') for n in notes))
        self.assertEqual(self.after['metadata']['source_layout']['source_annotation_restoration_count'], 5)

    def test_exact_complete_headers_and_physical_word_seams(self):
        self.assertIn('GOETHE-STUDIEN', self.passage(17)['text'])
        self.assertIn('ANTHROPOSOPHIE DAS GOETHEANUM UND SEINE ARBEIT', self.passage(42)['text'])
        self.assertIn('umzusehn', self.passage(37)['text'])
        self.assertNotIn('um- zusehn', self.passage(37)['text'])
        self.assertIn('poIitisch', self.passage(7)['text'])
        self.assertIn('Mensehen', self.passage(48)['text'])
        self.assertIn('Erziehungs- und', self.passage(48)['text'])

    def test_rejects_original_source_drift(self):
        before = deepcopy(self.before)
        before['passages'][1]['source_text'] += ' erfunden'
        with self.assertRaisesRegex(ValueError, 'source|drift'):
            build(before)

    def test_rejects_missing_true_poem_line_and_spurious_navigation(self):
        recipe = deepcopy(self.recipe)
        verse = next(s for s in recipe['passages']['ga-036-doc-heading-22']['segments'] if s['kind'] == 'verse')
        verse['parts'].pop()
        with self.assertRaisesRegex(ValueError, 'slices'):
            self.inspect(recipe=recipe)
        recipe = deepcopy(self.recipe)
        recipe['table_of_contents'].append(dict(recipe['table_of_contents'][0], id='false-signature'))
        with self.assertRaisesRegex(ValueError, 'contents'):
            self.inspect(recipe=recipe)

    def test_rejects_unreviewed_contents_heading_and_note_word_changes(self):
        for number, field, suffix in [(1, 'text', ' falscher Inhalt'), (42, 'title', ' frei erfunden')]:
            after = deepcopy(self.after)
            next(p for p in after['passages'] if p['id'] == f'ga-036-doc-heading-{number}')[field] += suffix
            errors, _ = self.inspect(after=after)
            self.assertTrue(errors)
        after = deepcopy(self.after)
        next(p for p in after['passages'] if p['metadata']['annotations'])['metadata']['annotations'][0]['text'] += ' erfunden'
        errors, _ = self.inspect(after=after)
        self.assertTrue(any('annotation' in error for error in errors))

    def test_rejects_missing_or_foreign_author_note_addition(self):
        recipe = deepcopy(self.recipe)
        recipe['annotation_additions'].pop()
        with self.assertRaisesRegex(ValueError, 'restoration|review'):
            self.inspect(recipe=recipe)
        recipe = deepcopy(self.recipe)
        recipe['annotation_additions'][0]['source_reference']['source_heading_witness']['body_index'] += 1
        with self.assertRaisesRegex(ValueError, 'restoration|review'):
            self.inspect(recipe=recipe)

    def test_rejects_missing_restoration_ledger_and_arbitrary_word_repair(self):
        events = deepcopy(self.events)
        for pid in events:
            events[pid] = [event for event in events[pid] if event['rule'] != 'source_restoration']
        with self.assertRaisesRegex(ValueError, 'ledger'):
            self.inspect(events=events)
        recipe = deepcopy(self.recipe)
        next(plan for plan in recipe['passages'].values() if plan['edits'])['edits'][0]['kind'] = 'general_ocr'
        with self.assertRaisesRegex(ValueError, 'repairs'):
            self.inspect(recipe=recipe)

if __name__ == '__main__':
    unittest.main()
