#!/usr/bin/env python3
"""Source-bound GA035 round-trip and meaningful independent tamper checks."""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import unittest
from build_ga035_recipe import ROOT, BASELINE, RECIPE, REVIEW, SOURCE, build, check_source
from repair_ga035_readability import apply_layout
from finalize_library import read_json
from check_essay_layout import inspect_reviewed_essay_layout
from check_proofreading_samples import inspect_source_layout

class GA035ReadabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = read_json(BASELINE if BASELINE.exists() else ROOT / "server/priv/content/ga-035.json.gz")
        cls.recipe = read_json(RECIPE)
        cls.after, events = apply_layout(cls.before, cls.recipe)
        cls.events = defaultdict(list)
        for event in events:
            cls.events[event['passage_id']].append({k:v for k,v in event.items() if k != 'passage_id'})

    def inspect(self, after=None, recipe=None):
        return inspect_reviewed_essay_layout(self.before, after or self.after, recipe or self.recipe,
            self.events, SOURCE, REVIEW, inspect_source_layout)

    def test_complete_source_bound_round_trip_and_idempotence(self):
        errors, _ = self.inspect()
        self.assertEqual(errors, [])
        again, changes = apply_layout(self.after, self.recipe)
        self.assertEqual(again, self.after)
        self.assertEqual(changes, [])
        self.assertEqual([(p['id'],p['source_text']) for p in self.before['passages']],
                         [(p['id'],p['source_text']) for p in self.after['passages']])

    def test_original_essays_and_nested_parts_keep_dates_and_pages(self):
        toc = self.after['table_of_contents']
        self.assertEqual(len(toc), 26)
        self.assertEqual(sum(row['source_role'] in ('article','appendix_article') for row in toc), 19)
        self.assertEqual(sum(row['source_role'] == 'subpart' for row in toc), 6)
        self.assertIn('21. Juni 1904 (S. 7)', toc[0]['title'])
        self.assertTrue(all(row.get('parent_id') for row in toc if row['source_role'] == 'subpart'))
        self.assertTrue(all('Rudolf Steiner' != row['title'] for row in toc))

    def test_goethe_real_verse_and_internal_paragraph_boundaries(self):
        passage = next(p for p in self.after['passages'] if p['id'] == 'ga-035-doc-heading-3')
        verses = []
        for block in passage['metadata']['reading_blocks']:
            if block['kind'] == 'verse':
                verses.append(passage['text'].encode('utf-16-le')[block['start_offset']*2:block['end_offset']*2].decode('utf-16-le'))
        self.assertEqual(len(verses), 20)
        self.assertEqual([len(verse.splitlines()) for verse in verses],
                         [12,7,1,2,5,2,6,2,4,6,3,2,12,2,4,4,2,4,2,4])
        math = self.after['passages'][0]
        self.assertIn('\n\nDer Mensch kann sich ja nur schwer freimachen', math['text'])

    def test_exact_annotation_words_and_four_printed_word_joins(self):
        notes = [n for p in self.after['passages'] for n in p['metadata']['annotations']]
        self.assertEqual(len(notes), 4)
        self.assertTrue(all('\n' not in n['text'] for n in notes))
        note = next(n for n in notes if n['id'].endswith('chapter-0003.xhtml#footnote-recovered-2'))
        for word in ('Schelling', 'Denker', 'Bestrebungen', 'erfahren'):
            self.assertIn(word, note['text'])
        self.assertTrue(note['text'].endswith('↩'))

    def test_rejects_original_source_mutation(self):
        before = deepcopy(self.before)
        before['passages'][0]['source_text'] += ' erfunden'
        with self.assertRaisesRegex(ValueError, 'source|drift'):
            build(before)

    def test_rejects_missing_real_verse_line_slice(self):
        recipe = deepcopy(self.recipe)
        verse = next(s for s in recipe['passages']['ga-035-doc-heading-3']['segments'] if s['kind'] == 'verse')
        verse['parts'].pop()
        with self.assertRaisesRegex(ValueError, 'slices'):
            self.inspect(recipe=recipe)

    def test_rejects_unknown_word_edit_kind_and_extra_toc_target(self):
        recipe = deepcopy(self.recipe)
        next(p for p in recipe['passages'].values() if p['edits'])['edits'][0]['kind'] = 'general_ocr'
        with self.assertRaisesRegex(ValueError, 'repairs'):
            self.inspect(recipe=recipe)
        recipe = deepcopy(self.recipe)
        recipe['table_of_contents'].append(dict(recipe['table_of_contents'][0],id='invented'))
        with self.assertRaisesRegex(ValueError, 'contents'):
            self.inspect(recipe=recipe)

    def test_rejects_unreviewed_annotation_and_printed_title_changes(self):
        after = deepcopy(self.after)
        next(p for p in after['passages'] if p['metadata']['annotations'])['metadata']['annotations'][0]['text'] += ' erfunden'
        errors, _ = self.inspect(after=after)
        self.assertTrue(any('annotation' in error for error in errors))
        after = deepcopy(self.after)
        after['passages'][4]['title'] = 'UND DIE'
        errors, _ = self.inspect(after=after)
        self.assertTrue(any('title' in error or 'metadata' in error for error in errors))

if __name__ == '__main__':
    unittest.main()
