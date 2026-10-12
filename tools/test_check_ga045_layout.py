"""Independent guards for the recovered original GA045 main paragraph."""
from copy import deepcopy
from pathlib import Path
import unittest

from check_essay_layout import inspect_ga045_text_recovery, read

ROOT = Path(__file__).resolve().parents[1]


class GA045RecoveryValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = read(ROOT / 'tools/ga045_layout_review.json')
        if not cls.review.get('source_additions'):
            raise unittest.SkipTest('The frozen GA045 recovery review is not available')
        path = ROOT / 'research/proofreading-layout-baseline/content/ga-045.json.gz'
        if not path.exists():
            path = ROOT / 'server/priv/content/ga-045.json.gz'
        cls.prior = read(path)
        cls.source = ROOT / 'research/proofreading-sources/ga-045.epub'

    def values(self):
        review = deepcopy(self.review)
        recipe = {key: deepcopy(review[key]) for key in ('source_additions', 'original_passages')}
        addition = recipe['source_additions'][0]
        event = {'rule': 'source_restoration', 'count': 1,
                 'label': 'Exakt belegten Originalquellentext wiederhergestellt',
                 'addition_id': addition['id'], 'source_text_sha256': addition['source_text_sha256'],
                 'text_sha256': addition['text_sha256'], 'before_excerpt': '',
                 'after_excerpt': addition['text'][:440], 'evidence': addition['evidence']}
        return deepcopy(self.prior), recipe, review, {addition['passage_id']: [event]}, self.source

    def test_exact_main_paragraph_restoration_preserves_raw_import_and_input(self):
        values = self.values()
        untouched = deepcopy(values[:4])
        result = inspect_ga045_text_recovery(*values)
        self.assertEqual(values[:4], untouched)
        self.assertEqual([p['id'] for p in result['passages']], [p['id'] for p in self.prior['passages']])
        self.assertEqual([p['source_text'] for p in result['passages']], [p['source_text'] for p in self.prior['passages']])
        body = result['passages'][3]['text']
        self.assertIn('* Es ist gesagt worden, daß im «Ich»', body)
        self.assertNotIn('↩', body)
        self.assertEqual([p['metadata']['annotations'] for p in result['passages']],
                         [p['metadata']['annotations'] for p in self.prior['passages']])

    def test_rejects_moved_insertion_and_changed_original_paragraph(self):
        for field, value in (('position_codepoint', 15267), ('text', 'Different main text'),
                             ('source_doc_paragraph_index', 219), ('source_text', 'Changed source')):
            values = self.values()
            for document in values[1:3]:
                document['source_additions'][0][field] = value
            with self.assertRaises(ValueError):
                inspect_ga045_text_recovery(*values)

    def test_rejects_duplicated_restoration_and_forged_ledger(self):
        values = self.values()
        for document in values[1:3]:
            document['source_additions'] *= 2
        with self.assertRaises(ValueError):
            inspect_ga045_text_recovery(*values)
        values = self.values()
        values[3]['ga-045-doc-heading-4'][0]['count'] = 2
        with self.assertRaises(ValueError):
            inspect_ga045_text_recovery(*values)


if __name__ == '__main__':
    unittest.main()
