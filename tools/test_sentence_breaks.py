#!/usr/bin/env python3
"""Regression cases for prose continuations beside verse and page furniture."""
from copy import deepcopy
import gzip
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from build_sentence_breaks import classify, running_heads
from finalize_library import read_json, write_json
from repair_sentence_breaks import apply_plan, apply_verified_stage, digest, strip_headers, transform
from check_sentence_breaks import inspect_sentence_layer


class SentenceBreakTests(unittest.TestCase):
    def test_prose_continuations_abbreviations_and_quoted_clauses(self):
        text = 'Ein Notizheft, in dem\n\nman etwas fand.\nHerr Dr.\nSteiner sagte: «Das ist so.»\nund setzte fort.\n\nEin neuer Satz.'
        joins, _, _ = classify(text, [])
        self.assertEqual(joins, [0, 2, 3])

    def test_verse_edges_and_internal_lines_survive_beside_prose(self):
        verse = 'Menschenseele!\nDu lebest in den Gliedern,\nDie dich durch die Raumeswelt tragen.'
        text = 'Wir lesen den Spruch:\n\n' + verse + '\n\nDies erklärt die\nGestaltung des Menschen.'
        start = text.index(verse)
        joins, kept, _ = classify(text, [(start, start + len(verse))])
        self.assertEqual(joins, [4])
        self.assertEqual(kept['reviewed_verse_or_structure'], 4)

    def test_lists_dates_and_diagram_rows_keep_their_boundaries(self):
        text = 'Dornach, 25. Dezember 1923\nWir betrachten\nden Aufbau:\n1. Körper\n2. Seele\n3. Geist\n\n#Bild 4\nDas Bild zeigt\nden Zusammenhang.'
        joins, _, _ = classify(text, [])
        self.assertEqual(joins, [1, 7])
        reference = 'Einen\nHinweis darauf enthält der Vortrag vom 3. Juni 1922.'
        self.assertEqual(classify(reference, [])[0], [0])

    def test_only_reviewed_running_head_forms_are_removed(self):
        text = 'Es erklärt die\n\nGA 103 Das Johannes-Evangelium\nSeite 011\n\nEntwickelung.'
        headers = running_heads('ga-103', text)
        self.assertEqual(strip_headers(text, headers), 'Es erklärt die\n\nEntwickelung.')
        self.assertEqual(running_heads('ga-103', 'GA 103, S. 11 ist eine Quellenangabe.'), [])
        stanza = 'Vers eins\n\n\nVers zwei'
        self.assertEqual(strip_headers(stanza, []), stanza)
        with_header = stanza + '\n\nGA 103 Das Johannes-Evangelium\nSeite 011\n\nDie Fortsetzung.'
        self.assertTrue(strip_headers(with_header, running_heads('ga-103', with_header)).startswith(stanza))

    def test_exact_input_hash_prevents_unreviewed_edits(self):
        text = 'Der Satz\nsetzt sich fort.'
        plan = dict(text_sha256=digest(text), headerless_sha256=digest(text),
                    result_sha256=digest('Der Satz setzt sich fort.'), joins=[0])
        self.assertEqual(transform(text, plan), 'Der Satz setzt sich fort.')
        with self.assertRaises(ValueError):
            transform('Ein Satz\nsetzt sich fort.', plan)

    def test_independent_validator_rejects_changed_spelling_and_source(self):
        text = 'Die Seele\nlebt im Menschen.'
        new = 'Die Seele lebt im Menschen.'
        prior = {'work_id': 'ga-120', 'source_epub_sha256': 'edition', 'passages': [
            {'id': 'p1', 'text': text, 'checksum': digest(text), 'source_text': text, 'metadata': {'page_numbers': [15]}}]}
        plan = {'work_id': 'ga-120', 'source_epub_sha256': 'edition', 'passages': {'p1': {
            'text_sha256': digest(text), 'source_text_sha256': digest(text),
            'headerless_sha256': digest(text), 'result_sha256': digest(new), 'joins': [0],
            'before_excerpt': text, 'after_excerpt': new}}}
        final, _ = apply_plan(prior, plan)
        self.assertEqual(inspect_sentence_layer(prior, final, plan)[0], [])
        damaged = deepcopy(final)
        damaged['passages'][0]['source_text'] = 'Andere Quelle'
        self.assertTrue(inspect_sentence_layer(prior, damaged, plan)[0])
        damaged = deepcopy(final)
        damaged['passages'][0].update(text=new.replace('Seele', 'Welt'), checksum=digest(new.replace('Seele', 'Welt')))
        self.assertTrue(inspect_sentence_layer(prior, damaged, plan)[0])
        self.assertEqual(apply_plan(final, plan), (final, []))

    def test_false_section_title_is_restored_as_sentence_continuation(self):
        left, right = 'Und seither nimmt der obere', 'Wir können die Entwicklung verfolgen.'
        original_title = 'Teil des astralischen Leibes ab.'
        prior = {'work_id': 'ga-227', 'source_epub_sha256': 'edition', 'passages': [
            {'id': 'a', 'title': 'Dreizehnter Vortrag', 'text': left, 'checksum': digest(left), 'source_text': left},
            {'id': 'b', 'title': original_title, 'text': right, 'checksum': digest(right), 'source_text': right}]}
        plan = {'work_id': 'ga-227', 'source_epub_sha256': 'edition', 'passages': {}, 'bridges': [
            {'left_id': 'a', 'right_id': 'b', 'right_prefix': '', 'restore_right_title': True,
             'right_title': 'Dreizehnter Vortrag (Fortsetzung)'}]}
        final, changes = apply_plan(prior, plan)
        self.assertEqual(final['passages'][0]['text'], left + ' ' + original_title)
        self.assertEqual(final['passages'][1]['text'], right)
        self.assertEqual([p['id'] for p in final['passages']], ['a', 'b'])
        self.assertEqual([p['source_text'] for p in final['passages']], [left, right])
        self.assertEqual(len(changes), 2)

    def test_selective_apply_checks_original_container_and_preserves_other_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, stage, baseline = (Path(temporary) / p for p in ('root', 'stage', 'baseline'))
            for folder in (root / 'content', root / 'library', root / 'proofreading/works',
                           stage / 'content', stage / 'proofreading/works', baseline / 'content'):
                folder.mkdir(parents=True)
            old = {'work_id': 'ga-051', 'passages': [
                {'id': 'p1', 'title': 'Vortrag', 'text': 'Der Satz\nsetzt sich fort.',
                 'checksum': digest('Der Satz\nsetzt sich fort.')} ]}
            final = deepcopy(old)
            final['passages'][0].update(text='Der Satz setzt sich fort.',
                                        checksum=digest('Der Satz setzt sich fort.'))
            current_file = root / 'content/ga-051.json.gz'
            write_json(current_file, old)
            # Recompress identical JSON with a different gzip timestamp, as in
            # an original import versus the deterministic baseline writer.
            current_file.write_bytes(gzip.compress(gzip.decompress(current_file.read_bytes()), mtime=1))
            input_file = baseline / 'content/ga-051.json.gz'
            write_json(input_file, old)
            self.assertNotEqual(digest(current_file.read_bytes()), digest(input_file.read_bytes()))
            self.assertEqual(read_json(current_file), read_json(input_file))
            final_file = stage / 'content/ga-051.json.gz'
            write_json(final_file, final)
            detail = {'work': {'application_base_sha256': digest(current_file.read_bytes()),
                               'sentence_input_sha256': digest(input_file.read_bytes()),
                               'after_sha256': digest(final_file.read_bytes())}}
            write_json(stage / 'proofreading/works/ga-051.json', detail)
            write_json(stage / 'proofreading/catalog.json', {'generated_at': 'fixture'})
            write_json(root / 'library/catalog.json', {'works': [
                {'id': 'ga-051', 'passages': [{'id': 'p1', 'title': 'Vortrag', 'checksum': old['passages'][0]['checksum']}]}]})
            other = root / 'content/ga-026.json.gz'
            other.write_bytes(b'concurrent earlier-band work')
            recipe = {'works': {'ga-051': {}}}
            with patch('check_sentence_breaks.validate', return_value={'status': 'passed', 'summary': {'works': 1}}), \
                 patch('repair_sentence_breaks.verify'), patch('proofread_library.complete_stage'):
                self.assertEqual(apply_verified_stage(root, stage, recipe, baseline), {'works': 1})
            self.assertEqual(read_json(current_file), final)
            self.assertEqual(other.read_bytes(), b'concurrent earlier-band work')
            summary = read_json(root / 'library/catalog.json')['works'][0]['passages'][0]
            self.assertEqual(summary['checksum'], final['passages'][0]['checksum'])
            current_file.write_bytes(b'unreviewed concurrent change')
            with patch('check_sentence_breaks.validate', return_value={'status': 'passed', 'summary': {'works': 1}}), \
                 patch('repair_sentence_breaks.verify'), patch('proofread_library.complete_stage'):
                with self.assertRaisesRegex(ValueError, 'Working volume changed'):
                    apply_verified_stage(root, stage, recipe, baseline)
            self.assertEqual(current_file.read_bytes(), b'unreviewed concurrent change')


if __name__ == '__main__':
    unittest.main()
