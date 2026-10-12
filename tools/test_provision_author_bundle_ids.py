"""Author provisioning scope checks, with no Apple credentials or network."""
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import provision_author_bundle_ids as provision


class ProvisionAuthorTests(unittest.TestCase):
    def setUp(self):
        self.author = next(a for a in provision.load_authors() if a["slug"] == "franz-kafka")
        with patch.dict(os.environ, {"ASC_ISSUER_ID": "test-team-issuer"}), patch.object(provision.ASCClient, "__init__"):
            self.client = provision.AuthorProvisioningClient(self.author, allow_writes=True)
        self.client.bundle_resource_id = "author-bundle"

    def test_requires_team_key_before_loading_private_key(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(provision.ASCClient, "__init__") as initializer:
            with self.assertRaisesRegex(RuntimeError, "team API key"):
                provision.AuthorProvisioningClient(self.author)
            initializer.assert_not_called()

    def test_protected_bundle_rejected_before_key_load(self):
        author = copy.deepcopy(self.author)
        author["bundle_id"] = "com.jonathankutscher.ga"
        with patch.object(provision.ASCClient, "__init__") as initializer:
            with self.assertRaisesRegex(RuntimeError, "allowlisted"):
                provision.AuthorProvisioningClient(author)
            initializer.assert_not_called()

    def test_existing_identifiers_cannot_be_modified(self):
        for method in ("PATCH", "DELETE"):
            with patch.object(provision.ASCClient, "request") as backend:
                with self.assertRaisesRegex(RuntimeError, "creation only"):
                    self.client.request(method, "/v1/bundleIds/author-bundle", {"data": {"type": "bundleIds"}})
                backend.assert_not_called()

    def test_foreign_identifier_and_capability_blocked(self):
        bodies = [
            ("bundleIds", {"type": "bundleIds", "attributes": {"identifier": "com.jonathankutscher.ga", "platform": "IOS", "name": "GA"}}),
            ("bundleIdCapabilities", {"type": "bundleIdCapabilities", "attributes": {"capabilityType": "ICLOUD", "settings": provision.ICLOUD_SETTINGS},
                                      "relationships": {"bundleId": provision.relation("bundleIds", "steiner-bundle")}}),
        ]
        for resource, data in bodies:
            with patch.object(provision.ASCClient, "request") as backend:
                with self.assertRaises(RuntimeError):
                    self.client.request("POST", "/v1/" + resource, {"data": data})
                backend.assert_not_called()

    def test_unscoped_reads_cannot_seed_foreign_identifier(self):
        with patch.object(provision.ASCClient, "request") as backend:
            with self.assertRaisesRegex(RuntimeError, "filter"):
                self.client.request("GET", "/v1/bundleIds")
            backend.assert_not_called()

    def test_cloudkit_capability_accepts_only_verified_author(self):
        data = {"type": "bundleIdCapabilities", "attributes": {"capabilityType": "ICLOUD", "settings": provision.ICLOUD_SETTINGS},
                "relationships": {"bundleId": provision.relation("bundleIds", "author-bundle")}}
        with patch.object(provision.ASCClient, "request", return_value={"data": {"id": "author-icloud"}}) as backend:
            self.client.request("POST", "/v1/bundleIdCapabilities", {"data": data})
            backend.assert_called_once()

    def test_capability_mode_requires_cloudkit_not_legacy_icloud(self):
        self.assertTrue(provision.cloudkit_enabled({"attributes": {"capabilityType": "ICLOUD", "settings": provision.ICLOUD_SETTINGS}}))
        self.assertTrue(provision.cloudkit_enabled({"attributes": {"capabilityType": "ICLOUD", "settings": [{"key": "ICLOUD_VERSION", "options": [{"key": "XCODE_6"}]}]}}))
        self.assertFalse(provision.cloudkit_enabled({"attributes": {"capabilityType": "ICLOUD", "settings": [{"key": "ICLOUD_VERSION", "options": [{"key": "XCODE_6", "enabled": False}]}]}}))
        self.assertFalse(provision.cloudkit_enabled({"attributes": {"capabilityType": "ICLOUD", "settings": [{"key": "ICLOUD_VERSION", "options": [{"key": "XCODE_5", "enabled": True}]}]}}))


if __name__ == "__main__":
    unittest.main()
