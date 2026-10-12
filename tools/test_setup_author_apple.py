"""Author-only Apple setup guards, without credentials or network requests."""
import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import setup_author_apple as setup


def client_init(self, *, allow_writes=False):
    self.allow_writes = allow_writes


class AuthorAppleTests(unittest.TestCase):
    def setUp(self):
        self.author = next(a for a in setup.load_authors() if a["slug"] == "franz-kafka")
        with patch.object(setup.ASCClient, "__init__", client_init):
            self.client = setup.AuthorClient(self.author, allow_writes=True)
        self.client.owned = {"apps": {"author-app"}, "appInfos": {"author-info"},
                             "appStoreVersions": {"author-version"}, "subscriptionGroups": {"author-group"}}

    def test_all_prepared_author_metadata_is_valid(self):
        for author in setup.load_authors():
            metadata = setup.prepared_metadata(author)
            self.assertEqual(metadata["bundle_id"], author["bundle_id"])
            self.assertNotIn(metadata["bundle_id"], setup.PROTECTED_BUNDLES)

    def test_protected_bundle_and_app_id_rejected(self):
        author = copy.deepcopy(self.author)
        author["bundle_id"] = "com.jonathankutscher.ga"
        with self.assertRaisesRegex(RuntimeError, "Steiner"):
            setup.AuthorClient(author)
        response = {"data": [{"type": "apps", "id": "6820947669", "attributes": {"bundleId": self.author["bundle_id"]}}]}
        with patch.object(setup.ASCClient, "request", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "allowlist"):
                self.client.request("GET", "/v1/apps", params={"filter[bundleId]": self.author["bundle_id"]})

    def test_cannot_patch_steiner_or_unrelated_resources(self):
        body = {"data": {"type": "appInfos", "id": "steiner-info", "attributes": {"name": "Changed"}}}
        with patch.object(setup.ASCClient, "request") as backend:
            with self.assertRaisesRegex(RuntimeError, "outside"):
                self.client.request("PATCH", "/v1/appInfos/steiner-info", body)
            backend.assert_not_called()

    def test_unrelated_reads_do_not_expand_write_allowlist(self):
        response = {"data": [{"type": "appInfos", "id": "foreign-info", "attributes": {}}]}
        with patch.object(setup.ASCClient, "request", return_value=response):
            self.client.request("GET", "/v1/apps/foreign-app/appInfos")
        self.assertFalse(self.client.owns("appInfos", "foreign-info"))

    def test_owned_child_read_can_register_localization(self):
        response = {"data": [{"type": "appInfoLocalizations", "id": "author-local", "attributes": {"locale": "de-DE"}}]}
        with patch.object(setup.ASCClient, "request", return_value=response):
            self.client.request("GET", "/v1/appInfos/author-info/appInfoLocalizations")
        self.assertTrue(self.client.owns("appInfoLocalizations", "author-local"))

    def test_foreign_product_id_rejected_before_request(self):
        body = {"data": {"type": "subscriptions", "attributes": {"productId": "com.jonathankutscher.ga.annual"},
                         "relationships": {"group": setup.relation("subscriptionGroups", "author-group")}}}
        with patch.object(setup.ASCClient, "request") as backend:
            with self.assertRaisesRegex(RuntimeError, "allowlist"):
                self.client.request("POST", "/v1/subscriptions", body)
            backend.assert_not_called()

    def test_new_resource_requires_owned_parent(self):
        body = {"data": {"type": "subscriptionGroups", "attributes": {"referenceName": "Kafka-App-Zugang"},
                         "relationships": {"app": setup.relation("apps", "6820947669")}}}
        with patch.object(setup.ASCClient, "request") as backend:
            with self.assertRaisesRegex(RuntimeError, "must belong"):
                self.client.request("POST", "/v1/subscriptionGroups", body)
            backend.assert_not_called()

    def test_existing_author_product_cannot_be_moved_to_ga_group(self):
        self.client.owned["subscriptions"] = {"author-annual"}
        body = {"data": {"type": "subscriptions", "id": "author-annual", "relationships": {
            "group": setup.relation("subscriptionGroups", "steiner-group")}}}
        with patch.object(setup.ASCClient, "request") as backend:
            with self.assertRaisesRegex(RuntimeError, "unrelated parent"):
                self.client.request("PATCH", "/v1/subscriptions/author-annual", body)
            backend.assert_not_called()

    def test_valid_author_creation_registers_result(self):
        body = {"data": {"type": "subscriptions", "attributes": {"productId": self.author["bundle_id"] + ".annual"},
                         "relationships": {"group": setup.relation("subscriptionGroups", "author-group")}}}
        response = {"data": {"type": "subscriptions", "id": "author-annual", "attributes": body["data"]["attributes"]}}
        with patch.object(setup.ASCClient, "request", return_value=response) as backend:
            self.client.request("POST", "/v1/subscriptions", body)
            backend.assert_called_once()
        self.assertTrue(self.client.owns("subscriptions", "author-annual"))

    def test_release_and_legal_attestations_cannot_change(self):
        for attrs in ({"releaseType": "AFTER_APPROVAL"}, {"contentRightsDeclaration": "DOES_NOT_USE_THIRD_PARTY_CONTENT"}, {"appVersionState": "READY_FOR_REVIEW"}):
            body = {"data": {"type": "appStoreVersions", "id": "author-version", "attributes": attrs}}
            with patch.object(setup.ASCClient, "request") as backend:
                with self.assertRaises(RuntimeError):
                    self.client.request("PATCH", "/v1/appStoreVersions/author-version", body)
                backend.assert_not_called()

    def test_build_selection_and_review_submission_not_allowed(self):
        body = {"data": {"type": "appStoreVersions", "id": "author-version", "relationships": {"build": setup.relation("builds", "build")}}}
        with self.assertRaisesRegex(RuntimeError, "Build selection"):
            self.client._write_allowed("PATCH", "/v1/appStoreVersions/author-version", body)
        with self.assertRaisesRegex(RuntimeError, "draft configuration"):
            self.client._write_allowed("POST", "/v1/reviewSubmissions", {"data": {"type": "reviewSubmissions"}})

    def test_metadata_status_does_not_write(self):
        class ReadOnlyMetadata:
            def rows(self, path, params):
                if path.endswith("/appInfos"):
                    return [{"id": "author-info", "attributes": {"state": "PREPARE_FOR_SUBMISSION"}}]
                if path.endswith("/appStoreVersions"):
                    return [{"id": "author-version", "attributes": {"versionString": "1.0", "appVersionState": "PREPARE_FOR_SUBMISSION"}}]
                raise AssertionError("Unexpected read: " + path)

            def write(self, *args, **kwargs):
                raise AssertionError("Read-only metadata status tried to write")

        result = setup.metadata_status(ReadOnlyMetadata(), {"id": "author-app"}, self.author, setup.prepared_metadata(self.author), "ios", "1.0", False)
        self.assertFalse(result["applied"])
        self.assertEqual(result["editableVersionIds"], ["author-version"])

    def test_price_rows_remain_scoped_to_author_subscription(self):
        self.client.owned["subscriptions"] = {"author-annual"}
        self.client.owned["subscriptionPricePoints"] = {"usa-point"}
        references = [{"type": "subscriptionPrices", "id": "${price-USA}"}]
        included = [{"type": "subscriptionPrices", "id": "${price-USA}", "attributes": {"startDate": None, "planType": "UPFRONT"},
                     "relationships": {"subscription": setup.relation("subscriptions", "author-annual"),
                                       "subscriptionPricePoint": setup.relation("subscriptionPricePoints", "usa-point"),
                                       "territory": setup.relation("territories", "USA")}}]
        body = {"data": {"type": "subscriptions", "id": "author-annual", "relationships": {"prices": {"data": references}}}, "included": included}
        self.client._write_allowed("PATCH", "/v1/subscriptions/author-annual", body)
        body["included"][0]["relationships"]["subscription"] = setup.relation("subscriptions", "steiner-subscription")
        with self.assertRaisesRegex(RuntimeError, "different subscription"):
            self.client._write_allowed("PATCH", "/v1/subscriptions/author-annual", body)

    def test_price_point_reference_from_owned_price_can_be_registered(self):
        self.client.owned["subscriptions"] = {"author-annual"}
        response = {"data": [{"type": "subscriptionPrices", "id": "de-price", "relationships": {"subscriptionPricePoint": setup.relation("subscriptionPricePoints", "de-point")}}]}
        with patch.object(setup.ASCClient, "request", return_value=response):
            self.client.request("GET", "/v1/subscriptions/author-annual/prices")
        self.assertTrue(self.client.owns("subscriptionPricePoints", "de-point"))

    def test_only_owned_immutable_price_catalogue_is_cached(self):
        self.client.owned["subscriptions"] = {"author-annual"}
        response = [{"type": "subscriptionPricePoints", "id": "de-point", "attributes": {"customerPrice": "30.00"}}]
        with patch.object(setup.ASCClient, "rows", return_value=response) as backend:
            first = self.client.rows("/v1/subscriptions/author-annual/pricePoints", {"filter[territory]": "DEU"})
            first[0]["attributes"]["customerPrice"] = "changed locally"
            second = self.client.rows("/v1/subscriptions/author-annual/pricePoints", {"filter[territory]": "DEU"})
            self.assertEqual(second[0]["attributes"]["customerPrice"], "30.00")
            self.assertEqual(backend.call_count, 1)
            self.client.rows("/v1/subscriptions/author-annual/prices")
            self.client.rows("/v1/subscriptions/author-annual/prices")
            self.assertEqual(backend.call_count, 3)
            self.client.rows("/v1/subscriptions/foreign-sub/pricePoints")
            self.client.rows("/v1/subscriptions/foreign-sub/pricePoints")
            self.assertEqual(backend.call_count, 5)

    def test_prices_apply_cannot_report_success_when_products_are_missing(self):
        with patch.object(setup, "AuthorClient"), patch.object(setup, "find_app", return_value={"id": "author-app"}), \
                patch.object(setup, "setup_products", return_value={"products": []}), patch.object(setup, "complete_prices") as prices:
            with self.assertRaisesRegex(RuntimeError, "Both author products"):
                setup.run_author(self.author, apply=True, step="prices", platforms=["ios"], version_string="1.0")
            prices.assert_not_called()
            report = setup.run_author(self.author, apply=False, step="prices", platforms=["ios"], version_string="1.0")
            self.assertTrue(report["pricePrerequisitesMissing"])
            self.assertEqual(report["status"], "author_draft_status")

    def test_concurrent_apply_runs_for_one_author_are_serialized(self):
        first_entered, release_first, second_entered = threading.Event(), threading.Event(), threading.Event()

        @setup.serialize_author_writes
        def operation(author, *, apply, first=False):
            if first:
                first_entered.set()
                if not release_first.wait(2):
                    raise AssertionError("First author writer was not released")
            else:
                second_entered.set()

        with tempfile.TemporaryDirectory() as directory, patch.object(setup, "AUTHOR_LOCK_DIRECTORY", Path(directory)), ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(operation, self.author, apply=True, first=True)
            self.assertTrue(first_entered.wait(1))
            second = workers.submit(operation, self.author, apply=True)
            try:
                self.assertFalse(second_entered.wait(0.05))
            finally:
                release_first.set()
            first.result(timeout=1)
            second.result(timeout=1)
            self.assertTrue(second_entered.is_set())


if __name__ == "__main__":
    unittest.main()
