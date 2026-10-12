import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from configure_author_revenuecat import (RevenueCatRedirects, checked_records,
                                        offering_products, public_offering)


class RevenueCatAuthorTests(unittest.TestCase):
    def setUp(self):
        self.authors = json.loads((Path(__file__).resolve().parents[1] / 'editions/authors.json').read_text())['authors']
        self.author = self.authors[0]

    def response(self, author):
        return {'current_offering_id': 'default', 'offerings': [{'identifier': 'default', 'packages': [
            {'identifier': '$rc_annual', 'platform_product_identifier': author['bundle_id'] + '.annual'},
            {'identifier': 'supporter', 'platform_product_identifier': author['bundle_id'] + '.supporter'}]}]}

    def row(self, author, project, key):
        return {'slug': author['slug'], 'projectId': project, 'appId': 'app-fixture',
                'publicKey': key, 'productsImported': True, 'entitlement': 'ga_access', 'offering': 'default'}

    def test_exact_two_default_products(self):
        _, products = offering_products(self.response(self.author))
        self.assertEqual(products, sorted(self.author['bundle_id'] + '.' + p for p in ['annual', 'supporter']))

    def test_wrong_author_offering_is_rejected_without_customer_request(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(self.response(self.authors[1])).encode()
        with patch('configure_author_revenuecat.urllib.request.build_opener', return_value=opener):
            with self.assertRaises(ValueError):
                public_offering(self.author, 'appl_FixtureOnly')
        self.assertEqual(opener.open.call_count, 1)
        self.assertTrue(opener.open.call_args.args[0].full_url.endswith('/offerings'))

    def test_incremental_pending_author_does_not_block_completed_author(self):
        configured = self.row(self.author, 'authorprojectone', 'appl_FixtureOne')
        pending = {'slug': self.authors[1]['slug'], 'projectId': 'authorprojecttwo', 'publicKey': ''}
        self.assertEqual(set(checked_records(self.authors, [configured, pending])), {self.author['slug']})

    def test_shared_project_is_rejected(self):
        rows = [self.row(self.authors[0], 'sharedproject', 'appl_FixtureOne'),
                self.row(self.authors[1], 'sharedproject', 'appl_FixtureTwo')]
        with self.assertRaises(ValueError):
            checked_records(self.authors, rows)

    def test_shared_public_key_is_rejected(self):
        rows = [self.row(self.authors[0], 'authorprojectone', 'appl_FixtureOne'),
                self.row(self.authors[1], 'authorprojecttwo', 'appl_FixtureOne')]
        with self.assertRaises(ValueError):
            checked_records(self.authors, rows)

    def test_different_origin_redirect_is_rejected(self):
        with self.assertRaises(RuntimeError):
            RevenueCatRedirects().redirect_request(None, None, 302, '', {}, 'https://different.example/offerings')


if __name__ == '__main__':
    unittest.main()
