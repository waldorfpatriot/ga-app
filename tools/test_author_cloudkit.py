"""Verify author isolation and additive CKDB changes without contacting Apple."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from setup_author_cloudkit import (GA_CONTAINER, CKToolError, additive_schema,
                                  checked_authors, cktool, schema_status, write_status)


class CloudKitSetupTests(unittest.TestCase):
    def test_missing_cli_token_preserves_console_production_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'status.json').write_text(json.dumps({'status': 'production_schema_verified', 'productionSchemaVerified': True}))
            write_status(directory, {'status': 'blocked_missing_management_token'})
            status = json.loads((directory / 'status.json').read_text())
            self.assertEqual(status['status'], 'production_schema_verified')
            self.assertTrue(status['productionSchemaVerified'])
            self.assertEqual(json.loads((directory / 'cktool-status.json').read_text())['status'], 'blocked_missing_management_token')

    def test_all_author_containers_are_isolated(self):
        manifest = json.loads((Path(__file__).resolve().parents[1] / "editions/authors.json").read_text())
        authors = checked_authors(manifest, None)
        self.assertEqual(len(authors), 11)
        self.assertNotIn(GA_CONTAINER, [a["cloudkit_container"] for a in authors])

    def test_original_ga_rejected_even_if_manifest_changed(self):
        manifest = {"authors": [{"slug": "test-author", "bundle_id": "com.jonathankutscher.ga", "cloudkit_container": GA_CONTAINER}]}
        with self.assertRaises(ValueError):
            checked_authors(manifest, None)

    def test_complete_existing_schema_is_preserved(self):
        schema = '''DEFINE SCHEMA
 CREATE ROLE Reviewer;
 RECORD TYPE Existing ("___recordID" REFERENCE QUERYABLE, name STRING SEARCHABLE, GRANT READ TO "_world");
'''
        merged = additive_schema(schema)
        self.assertTrue(merged.startswith(schema))
        self.assertTrue(schema_status(merged)["ready"])
        self.assertFalse(schema_status(merged)["publicGrantsPresent"])
        self.assertEqual(additive_schema(merged), merged)

    def test_add_missing_field_preserves_indexes_grants_and_comments(self):
        schema = '''DEFINE SCHEMA
 RECORD TYPE "GAReadingState" (
   // retain existing options
   payload ASSET,
   "___createTime" TIMESTAMP QUERYABLE SORTABLE,
   GRANT READ TO "_creator"
 );
'''
        merged = additive_schema(schema)
        self.assertIn(schema[schema.index("\n   //"):], merged)
        self.assertTrue(schema_status(merged)["ready"])
        self.assertTrue(schema_status(merged)["publicGrantsPresent"])

    def test_ready_schema_is_byte_identical(self):
        schema = 'DEFINE SCHEMA\nRECORD TYPE GAReadingState ("payload" ASSET, schemaVersion INT64 QUERYABLE);\n'
        self.assertEqual(additive_schema(schema), schema)

    def test_comments_do_not_create_false_record_types(self):
        schema = 'DEFINE SCHEMA\n/* RECORD TYPE GAReadingState (payload STRING); */\n'
        self.assertTrue(schema_status(additive_schema(schema))["ready"])

    def test_conflicting_types_rejected(self):
        schema = 'DEFINE SCHEMA\nRECORD TYPE GAReadingState (payload STRING, schemaVersion INT64);'
        self.assertFalse(schema_status(schema)["ready"])
        with self.assertRaises(ValueError):
            additive_schema(schema)

    def test_partial_fragment_cannot_replace_full_schema(self):
        with self.assertRaises(ValueError):
            additive_schema('RECORD TYPE GAReadingState (payload ASSET);')

    def test_errors_do_not_expose_captured_credentials(self):
        result = subprocess.CompletedProcess([], 64, "secret-never-printed", "No management token found")
        with patch('setup_author_cloudkit.subprocess.run', return_value=result) as run:
            with self.assertRaises(CKToolError) as caught:
                cktool(["get-teams"])
        self.assertEqual(str(caught.exception), 'blocked_missing_management_token')
        self.assertNotIn("--token", run.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
