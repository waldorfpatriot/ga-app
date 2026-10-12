#!/usr/bin/env python3
"""Exact GA045 reflow/source coverage and meaningful tamper regressions."""
from collections import defaultdict
from copy import deepcopy
import re
import unittest

from build_ga045_recipe import ROOT, BASELINE, RECIPE, REVIEW, SOURCE, build
from repair_ga045_readability import apply_layout
from finalize_library import read_json
from check_essay_layout import inspect_reviewed_essay_layout
from check_proofreading_samples import inspect_source_layout


class GA045ReadabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = read_json(BASELINE if BASELINE.exists() else ROOT / 'server/priv/content/ga-045.json.gz')
        cls.recipe = read_json(RECIPE)
        cls.after, changes = apply_layout(cls.before, cls.recipe)
        cls.events = defaultdict(list)
        for event in changes:
            cls.events[event['passage_id']].append({k: v for k, v in event.items() if k != 'passage_id'})

    def inspect(self, *, after=None, recipe=None, events=None):
        return inspect_reviewed_essay_layout(self.before, after or self.after, recipe or self.recipe,
            events or self.events, SOURCE, REVIEW, inspect_source_layout)

    def passage(self, number):
        return next(p for p in self.after['passages'] if p['id'] == f'ga-045-doc-heading-{number}')

    @staticmethod
    def block_text(passage, block):
        return passage['text'].encode('utf-16-le')[block['start_offset'] * 2:block['end_offset'] * 2].decode('utf-16-le')

    def test_complete_source_preservation_and_idempotence(self):
        errors, checked = self.inspect()
        self.assertEqual(errors, [])
        self.assertGreater(checked, 0)
        self.assertEqual(len(self.after['passages']), 11)
        self.assertEqual([(p['id'], p['source_text']) for p in self.before['passages']],
                         [(p['id'], p['source_text']) for p in self.after['passages']])
        self.assertEqual([p['metadata']['annotations'] for p in self.before['passages']],
                         [p['metadata']['annotations'] for p in self.after['passages']])
        again, changes = apply_layout(self.after, self.recipe)
        self.assertEqual(again, self.after)
        self.assertEqual(changes, [])

    def test_prose_reflows_but_real_paragraphs_and_compounds_remain(self):
        for passage in self.after['passages']:
            prose = [self.block_text(passage, block) for block in passage['metadata']['reading_blocks']
                     if block['kind'] == 'prose']
            self.assertTrue(all('\n' not in text for text in prose))
        self.assertIn('\n\nVerschieden von diesem Sinn', self.passage(2)['text'])
        self.assertIn('\n\nNun müssen im Menschen dem Lebenssinn', self.passage(7)['text'])
        self.assertIn('Bewegungsimpulse', self.passage(7)['text'])
        self.assertNotIn('Be- wegungsimpulse', self.passage(7)['text'])
        self.assertIn('Ich-Menschen', self.passage(5)['text'])
        self.assertIn('links-rechts', self.passage(10)['text'])
        self.assertIn('geschmack-ausstrahlende', self.passage(7)['text'])
        self.assertIn('durch-dringt', self.passage(5)['text'])

    def test_both_four_item_lists_keep_original_sequence(self):
        passage = self.passage(10)
        notes = [self.block_text(passage, block) for block in passage['metadata']['reading_blocks']
                 if block['kind'] == 'note']
        self.assertEqual(len(notes), 9)
        self.assertEqual(notes[0], 'Es wird vorausgesetzt:')
        self.assertEqual([text.split(';', 1)[0] for text in notes[1:5]], [
            'Eine höhere Geisteswelt', 'Eine niedere Geisteswelt', 'Die astrale Welt', 'Die physische Welt'])
        self.assertTrue(notes[5].startswith('Die Gestaltung des physischen Menschenleibes'))
        self.assertTrue(notes[6].startswith('Die Gestalt des Menschenleibes'))
        self.assertTrue(notes[7].endswith('«rechts-links» wie «links-rechts».'))
        self.assertTrue(notes[8].startswith('4. Das Ergebnis dieser Gestaltungen'))

    def test_appendix_headings_caps_stops_table_and_diagram_remain(self):
        passage = self.passage(11)
        blocks = [(block, self.block_text(passage, block)) for block in passage['metadata']['reading_blocks']]
        self.assertEqual([text for block, text in blocks if block['kind'] == 'heading' and text.startswith('ANHANG')],
                         ['ANHANG l', 'ANHANG 2', 'ANHANG 3', 'ANHANG 4', 'ANHANG 5'])
        self.assertEqual(sum(text == 'Hier bricht der Text ab.' for _, text in blocks), 4)
        caption = next(text for _, text in blocks if text.startswith('Diese Ausführungen gehören'))
        self.assertTrue(caption.endswith('Menschen» zugehörig.'))
        self.assertIn('Eigenbewegungs- und', passage['text'])
        self.assertIn('Atmungs- und', passage['text'])
        self.assertEqual(sum(text == 'Absonderung' for _, text in blocks), 2)
        self.assertIn('Gesicht-\nanlage', [text for _, text in blocks])
        self.assertIn('Geschmack-\nanlage', [text for _, text in blocks])
        self.assertTrue(any('Wärmeempfindungs-\nanlage Erhaltung' in text for _, text in blocks))
        self.assertTrue(any('Strebungen-Begehrungen: Die Phantasie' in text for _, text in blocks))

    def test_one_exact_main_paragraph_restored_at_original_position(self):
        passage = self.passage(4)
        self.assertIn('* Es ist gesagt worden, daß im «Ich» gleichsam zu einem Punkte zusammengeschrumpft', passage['text'])
        source = self.recipe['source_additions'][0]
        self.assertEqual(source['source_segments'][0]['body_indices'], [46])
        self.assertTrue(source['source_text'].endswith('↩'))
        self.assertNotIn('↩', source['text'])
        self.assertEqual(passage['metadata']['source_restorations'], [source['id']])
        paragraphs = [self.block_text(passage, block) for block in passage['metadata']['reading_blocks']]
        restored = next(i for i, text in enumerate(paragraphs) if text.startswith('* Es ist gesagt worden'))
        self.assertTrue(paragraphs[restored - 1].endswith('unmittelbar zur Offenbarung kommen.'))
        self.assertTrue(paragraphs[restored + 1].startswith('Der «Ich-Mensch» und der «astralische Mensch» stellen'))
        events = [event for items in self.events.values() for event in items if event['rule'] == 'source_restoration']
        self.assertEqual(len(events), 1)
        self.assertEqual(self.after['metadata']['source_layout']['source_restoration_count'], 1)

    def test_rejects_missing_foreign_or_misplaced_restoration(self):
        from build_ga045_recipe import augment_original
        for field, value in [('source_segments', []), ('position_codepoint', 0), ('text', 'Erfundener Absatz')]:
            recipe = deepcopy(self.recipe)
            recipe['source_additions'][0][field] = value
            with self.assertRaisesRegex(ValueError, 'restor|paragraph|source'):
                augment_original(self.before, recipe)
        recipe = deepcopy(self.recipe)
        recipe['source_additions'] = []
        with self.assertRaisesRegex(ValueError, 'restor|paragraph|source'):
            augment_original(self.before, recipe)

    def test_rejects_original_source_and_annotation_drift(self):
        before = deepcopy(self.before)
        before['passages'][0]['source_text'] += ' erfunden'
        with self.assertRaisesRegex(ValueError, 'original|source|drift|layout'):
            apply_layout(before, self.recipe)
        before = deepcopy(self.before)
        before['passages'][0]['metadata']['annotations'][0]['text'] += ' erfunden'
        with self.assertRaisesRegex(ValueError, 'annotation'):
            apply_layout(before, self.recipe)

    def test_rejects_dropped_slice_and_unreviewed_word_change(self):
        recipe = deepcopy(self.recipe)
        recipe['passages'][self.before['passages'][0]['id']]['segments'][0]['parts'].pop()
        with self.assertRaisesRegex(ValueError, 'slices'):
            self.inspect(recipe=recipe)
        after = deepcopy(self.after)
        after['passages'][0]['text'] = after['passages'][0]['text'].replace('Menschen', 'Fremden', 1)
        errors, _ = self.inspect(after=after)
        self.assertTrue(errors)

    def test_rejects_source_seam_tamper(self):
        recipe = deepcopy(self.recipe)
        recipe['passages'][self.before['passages'][0]['id']]['edits'][0]['new'] += 'x'
        with self.assertRaisesRegex(ValueError, 'repairs'):
            self.inspect(recipe=recipe)
        review = read_json(REVIEW)
        review['passages'][self.before['passages'][0]['id']]['edits'][0]['source_doc_witnesses'][0]['source_doc_paragraph_index'] += 1
        with self.assertRaisesRegex(ValueError, 'DOC'):
            build(self.before, review=review)

    def test_eight_exact_page_seams_and_unchanged_source_letters(self):
        expected = {1: [('Berges- höhe', 'Bergeshöhe')],
                    2: [('Auf- zählung', 'Aufzählung')],
                    6: [('Wärme- vorgänge', 'Wärmevorgänge')],
                    7: [('angenom- menen', 'angenommenen')],
                    9: [('umgewen- deten', 'umgewendeten')],
                    11: [('Wech- seispiel', 'Wechseispiel'),
                         ('Eigenbe- wegungssinn', 'Eigenbewegungssinn'),
                         ('zwi- sehen', 'zwisehen')]}
        for number, repairs in expected.items():
            passage = self.passage(number)
            plan = self.recipe['passages'][passage['id']]
            for old, new in repairs:
                self.assertNotIn(old, passage['text'])
                self.assertIn(new, passage['text'])
                matches = [repair for repair in plan['edits'] if repair['old'] == old]
                self.assertEqual(len(matches), 1)
                repair = matches[0]
                self.assertTrue(repair['physical_page_seam'])
                self.assertFalse(repair['source_contains_exact_physical_lf'])
                self.assertEqual(len(repair['source_witnesses']), 2)
                self.assertEqual(len(repair['source_doc_witnesses']), 2)
                self.assertEqual(repair['new'], repair['old'].replace('- ', ''))
        self.assertEqual(sum(repair.get('physical_page_seam', False)
                             for plan in self.recipe['passages'].values() for repair in plan['edits']), 8)
        # Source checks are independent of a reading-text projection and reject
        # moving either source fragment or its intervening printed footer.
        from build_ga045_recipe import check_source
        review = read_json(REVIEW)
        check_source(SOURCE, review)
        review = deepcopy(review)
        repair = next(repair for plan in review['passages'].values() for repair in plan['edits']
                      if repair.get('physical_page_seam'))
        repair['source_doc_page_footer']['page'] += 1
        with self.assertRaisesRegex(ValueError, 'footer'):
            check_source(SOURCE, review)
        again, changes = apply_layout(self.after, self.recipe)
        self.assertEqual(again, self.after)
        self.assertEqual(changes, [])

    def test_frozen_builder_is_reproducible(self):
        self.assertEqual(build(self.before), self.recipe)


if __name__ == '__main__':
    unittest.main()
