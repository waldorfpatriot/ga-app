#!/usr/bin/env python3
"""Regressions for byte preservation and source-page/checksum finalization."""
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from finalize_library import finalize, read_json, verify


class FinalizationTests(unittest.TestCase):
    def test_finalization_preserves_core_source_notes_and_actual_pages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "content").mkdir()
            (root / "library").mkdir()
            core_text = "Unveränderter Originaltext."
            core_checksum = hashlib.sha256(core_text.encode()).hexdigest()
            core = {"work_id": "ga-003", "passages": [{"id": "core", "text": core_text, "checksum": core_checksum}]}
            core_bytes = json.dumps(core, ensure_ascii=False, indent=4).encode() + b"\n\n"
            (root / "content" / "ga-003.json").write_bytes(core_bytes)
            source_text = "  Äußere  Welt [15]\n\tNeue\t\tZeile [16]  \n\n Vers bleibt. [15] "
            passage = {"id": "original", "text": source_text, "source_text": source_text,
                       "checksum": "old", "ga_page": None,
                       "metadata": {"page_numbers": [14, 15], "page_marker_source": "epub_source_page_labels",
                                    "annotations": [{"text": "Originale  Anmerkung [9]."}]}}
            payload = {"work_id": "ga-120", "passages": [passage]}
            (root / "content" / "ga-120.json.gz").write_bytes(gzip.compress(json.dumps(payload).encode()))
            seed_bytes = b'{"work_id":"ga-120","passages":[]}'
            (root / "content" / "ga-120.json").write_bytes(seed_bytes)
            catalog = {"works": [
                {"id": "ga-003", "content_path": "/core", "passages": [{"id": "core", "checksum": core_checksum}]},
                {"id": "ga-120", "content_path": "/original", "passages": [{"id": "original", "checksum": "old"}]},
            ]}
            (root / "library" / "catalog.json").write_text(json.dumps(catalog))
            report = finalize(root)
            result = read_json(root / "content" / "ga-120.json.gz")["passages"][0]
            self.assertEqual(result["text"], "Äußere Welt\nNeue Zeile\n\nVers bleibt.")
            self.assertEqual(result["source_text"], source_text)
            self.assertEqual(result["metadata"]["annotations"], passage["metadata"]["annotations"])
            self.assertEqual(result["metadata"]["page_numbers"], [14, 15, 16])
            self.assertEqual(result["ga_page"], "S. 14–16")
            self.assertEqual(result["checksum"], hashlib.sha256(result["text"].encode()).hexdigest())
            self.assertEqual((root / "content" / "ga-003.json").read_bytes(), core_bytes)
            self.assertEqual((root / "content" / "ga-120.json").read_bytes(), seed_bytes)
            self.assertEqual(report["added_inline_page_count"], 1)
            before = (root / "content" / "ga-120.json.gz").read_bytes()
            self.assertEqual(before[4:8], b"\0\0\0\0")
            self.assertEqual(finalize(root)["changed_text_count"], 0)
            self.assertEqual((root / "content" / "ga-120.json.gz").read_bytes(), before)
            self.assertEqual(verify(root)["available_count"], 2)

    def test_catalog_checksum_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "content").mkdir()
            (root / "library").mkdir()
            text = "Originaler Text."
            checksum = hashlib.sha256(text.encode()).hexdigest()
            payload = {"work_id": "ga-003", "passages": [{"id": "core", "text": text, "checksum": checksum}]}
            (root / "content" / "ga-003.json").write_text(json.dumps(payload))
            catalog = {"works": [{"id": "ga-003", "content_path": "/core", "passages": [{"id": "core", "checksum": "stale"}]}]}
            (root / "library" / "catalog.json").write_text(json.dumps(catalog))
            with self.assertRaisesRegex(ValueError, "catalog_checksum_mismatches"):
                verify(root)


if __name__ == "__main__":
    unittest.main()
