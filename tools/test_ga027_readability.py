#!/usr/bin/env python3
"""Source-bound GA027 layout regression checks against the retained facsimiles."""
from collections import Counter
from copy import deepcopy
import hashlib
import gzip
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from build_ga027_recipe import build, check_source, REVIEW, RECIPE, SOURCE, BASELINE
from finalize_library import read_json, write_json
from repair_ga027_readability import apply_layout, stage
from repair_source_structure import validate_layout


class GA027ReadabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = read_json(BASELINE)
        cls.recipe = read_json(RECIPE)
        cls.review = read_json(REVIEW)
        cls.after, cls.changes = apply_layout(cls.before, cls.recipe)

    def test_frozen_recipe_rebuilds_from_bound_source(self):
        self.assertEqual(build(self.before), self.recipe)
        self.assertEqual(len(check_source(SOURCE, self.review)), 138)
        self.assertEqual(len(self.review['pages']), 134)
        self.assertEqual(len(self.changes), 20)
        self.assertEqual(sum(len(p['metadata']['reading_blocks']) for p in self.after['passages']), 355)

    def test_all_source_characters_retained_except_reviewed_seams_and_table_order(self):
        table = self.review['table']
        for before, after in zip(self.before['passages'], self.after['passages']):
            expected = before['text']
            if before['id'] == table['passage_id']:
                # Independently require each complete, original table row and
                # the table's exact source-token multiset, including numbers.
                begin = after['text'].index('3 Nach dem Titel folgte:')
                end = after['text'].index(table['footer']) + len(table['footer'])
                new_table = after['text'][begin:end]
                self.assertEqual(Counter(table['old'].split()), Counter(new_table.split()))
                for row in table['rows']:
                    self.assertIn(f"{row['page']} {row['line']} {row['description']}\n", new_table)
                expected = expected.replace(table['old'], new_table)
            expected = re.sub(r'(\w)-\n+(\w)', r'\1\2', expected)
            self.assertEqual(re.sub(r'\s', '', expected), re.sub(r'\s', '', after['text']), before['id'])
            self.assertEqual(before['source_text'], after['source_text'])
            self.assertEqual(before['id'], after['id'])
            self.assertEqual(before['title'], after['title'])
            for key, value in before['metadata'].items():
                self.assertEqual(value, after['metadata'][key])
            self.assertEqual(hashlib.sha256(after['text'].encode()).hexdigest(), after['checksum'])
            validate_layout(after)
        self.assertEqual([p['id'] for p in self.before['passages']], [e['id'] for e in self.after['table_of_contents']])
        self.assertEqual(sum(len(p['edits']) for p in self.recipe['passages'].values()), 6)

    def test_true_paragraphs_and_continuations_follow_printed_indentation(self):
        first = self.after['passages'][0]
        self.assertEqual(len(first['text'].split('\n\n')), 38)
        self.assertIn('\n\nNicht um eine Opposition', first['text'])
        self.assertIn('\n\nAllein wir fügen', first['text'])
        self.assertIn('\n\nEine Einwendung', first['text'])
        self.assertIn('dem Denken stehen bleibt', first['text'])
        self.assertNotIn('\n\nMan muß betonen', first['text'])
        self.assertNotIn('\n\nWieder wird man', first['text'])
        nineteenth = self.after['passages'][18]['text']
        self.assertNotIn('\n\nDabei liegt eine Anschauung', nineteenth)
        self.assertIn('\n\nErster Fall\n\nMan hat', nineteenth)
        self.assertIn('\n\nNeunter Fall Migräne-artige Zustände im Klimakterium\n\nDie Patientin', nineteenth)

    def test_standalone_note_and_appendix_lists_retain_roles(self):
        second = self.after['passages'][1]
        self.assertEqual(second['metadata']['reading_blocks'][-1]['kind'], 'note')
        self.assertIn('\n\n* Durch ein Vergleichen', second['text'])
        last = self.after['passages'][-1]['text']
        self.assertIn('seinen Weg finden bei allen, die suchen', last)
        self.assertIn('\n\nArlesheim-Dornach, September 1925\n\nha Wegman, Dr. med.', last)
        for heading in ['VORWORT ZUR ERSTEN AUFLAGE', 'NACHWORT', 'HINWEISE DES HERAUSGEBERS', 'Hinweise zum Text', 'NAMENREGISTE R']:
            self.assertIn('\n\n' + heading + '\n\n', last)
        self.assertIn('\n\n7 noch weitere Erkenntnisse', last)
        self.assertIn('\n\nDu Bois-Reymond, Emil 26\n\nMolt, Emil 96', last)
        self.assertIn('Anwendüng', last)
        self.assertIn('Wachstums-, Ernährungs- etc. -Vorgängen', self.after['passages'][13]['text'])

    def test_stage_separates_current_compressed_bytes_from_preserved_input(self):
        from repair_source_structure import stage as source_stage
        with tempfile.TemporaryDirectory() as temporary:
            root, baseline, output = [Path(temporary) / name for name in ('root', 'baseline', 'stage')]
            for folder in ('content', 'library', 'proofreading/works'):
                (root / folder).mkdir(parents=True)
            content = root / 'content/ga-027.json.gz'
            # gzip header/level differences do not change the exact JSON input.
            raw = gzip.decompress(BASELINE.read_bytes())
            content.write_bytes(gzip.compress(raw, compresslevel=1, mtime=123))
            actual_current = hashlib.sha256(content.read_bytes()).hexdigest()
            write_json(root / 'proofreading/works/ga-027.json', {'work': {
                'after_sha256': actual_current, 'application_base_sha256': actual_current,
                'checks': []}, 'changes': []})
            write_json(root / 'proofreading/catalog.json', {'generated_at': 'unchanged'})
            write_json(root / 'library/catalog.json', {'works': [{'id': 'ga-027', 'passages': [
                {'id': p['id']} for p in self.before['passages']]}]})
            # The stage wrapper must hand the saved byte hash to the common
            # engine. Its content/slice/ledger path runs; only corpus-wide final
            # verification is replaced for this one-volume fixture.
            with patch('proofread_library.complete_stage'), patch('repair_source_structure.verify'):
                stage(root, output, self.recipe, baseline)
            saved = baseline / 'content/ga-027.json.gz'
            frozen_input = hashlib.sha256(saved.read_bytes()).hexdigest()
            self.assertNotEqual(actual_current, frozen_input)
            self.assertEqual(gzip.decompress(content.read_bytes()), gzip.decompress(saved.read_bytes()))
            report = read_json(output / 'proofreading/works/ga-027.json')['work']
            self.assertEqual(report['application_base_sha256'], actual_current)
            self.assertEqual(report['layout_input_sha256'], frozen_input)
            with patch('proofread_library.complete_stage'), patch('repair_source_structure.verify'):
                with self.assertRaisesRegex(ValueError, 'Preserved layout input hash/payload differs'):
                    source_stage(root, Path(temporary) / 'bad-stage', self.recipe, baseline,
                                 preserved_input_sha256='wrong byte hash')

    def test_idempotence_and_edition_text_scan_drift_fail_closed(self):
        repeated, changes = apply_layout(self.after, self.recipe)
        self.assertEqual(repeated, self.after)
        self.assertEqual(changes, [])
        for mutation in ['source', 'text', 'source_text', 'coverage', 'duplicate']:
            before, recipe = deepcopy(self.before), deepcopy(self.recipe)
            if mutation == 'source': before['source_epub_sha256'] = 'drift'
            elif mutation == 'text': before['passages'][0]['text'] += ' verändert'
            elif mutation == 'source_text': before['passages'][0]['source_text'] += ' verändert'
            elif mutation == 'coverage': recipe['passages'][before['passages'][0]['id']]['segments'].pop()
            else: recipe['passages'][before['passages'][0]['id']]['segments'].append(deepcopy(recipe['passages'][before['passages'][0]['id']]['segments'][0]))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                apply_layout(before, recipe)
        review = deepcopy(self.review)
        review['pages']['7']['image_sha256'] = 'wrong'
        with self.assertRaises(ValueError): check_source(SOURCE, review)
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'changed.epub'
            source.write_bytes(b'wrong edition')
            with self.assertRaises(ValueError): build(self.before, source)


if __name__ == '__main__':
    unittest.main()
