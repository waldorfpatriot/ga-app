#!/usr/bin/env python3
"""Focused regressions: conservative word repair and durable editorial anchors."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from proofread_library import audit_flags, repair_words, repair_reviewed_syllables, repair_reviewed_ocr, preserve_layout_baseline
from finalize_library import read_json
from proofreading_server import Workspace, Handler


class RepairTests(unittest.TestCase):
    def test_source_scope_observations_do_not_become_unresolved_reader_flags(self):
        payload = {"work_id": "ga-033", "metadata": {"source_layout": {"recipe_sha256": "frozen"}},
                   "passages": [{"id": "source", "text": "Geprüfter Absatz."}]}
        actionable = {"passage_id": "source", "rule": "ocr_source_review", "count": 1, "label": "Original prüfen"}
        recipe = {"review_flags": ["Retained original source spelling.", {"kind": "source_scope", "evidence": "Original apparatus boundary."}, actionable]}
        with patch("proofread_library.read_json", return_value=recipe):
            self.assertEqual(audit_flags(payload), [actionable])
        with patch("proofread_library.read_json", return_value={"review_flags": [{"rule": "ocr_source_review"}]}):
            with self.assertRaisesRegex(ValueError, "Malformed source review flag"):
                audit_flags(payload)

    def test_structural_baseline_is_preserved_and_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            payload={'work_id':'ga-fixture','passages':[{'text':'Geprüfte Quelle 😀'}]}
            digest=preserve_layout_baseline(payload,root)
            self.assertEqual(preserve_layout_baseline(payload,root),digest)
            self.assertEqual(read_json(root/'content/ga-fixture.json.gz'),payload)
            with self.assertRaises(ValueError):
                preserve_layout_baseline({'work_id':'ga-fixture','passages':[]},root)
            self.assertEqual(read_json(root/'content/ga-fixture.json.gz'),payload)
    def test_print_verified_ocr_replacements_are_exact_words(self):
        result, replacements = repair_reviewed_ocr("fiir und dafi erfiillt. iiber grofien miissen. iibertragung bleibt.")
        self.assertEqual(result, "für und daß erfüllt. über großen müssen. iibertragung bleibt.")
        self.assertEqual(sum(r["count"] for r in replacements), 6)
    def test_reviewed_inline_syllables_keep_case_and_genuine_compound_hyphens(self):
        result, replacements = repair_reviewed_syllables("Geistes-Er-kenntnis und zu-nächst. Geistig-seelisch bleibt. be-wußtsein.")
        self.assertEqual(result, "Geistes-Erkenntnis und zunächst. Geistig-seelisch bleibt. bewußtsein.")
        self.assertEqual(sum(r["count"] for r in replacements), 3)

    def test_evidenced_split_repairs_preserve_compounds_and_verse_breaks(self):
        original = "Men-\nschen kennen geistig-\nseelischen Ein-\nund Ausatem.\n\nVers eins\nVers zwei"
        rebuilt = "Men- schen kennen geistig- seelischen Ein- und Ausatem.\n\nVers eins\nVers zwei"
        evidence = (Counter(menschen=20, geistigseelischen=3, einund=2),
                    Counter(menschen=2000, geistigseelischen=50, einund=20),
                    Counter({("men", "schen"): 20, ("geistig", "seelischen"): 1500, ("ein", "und"): 1}))
        result, changes = repair_words(original, rebuilt, evidence)
        self.assertEqual(result, "Menschen kennen geistig- seelischen Ein- und Ausatem.\n\nVers eins\nVers zwei")
        self.assertEqual(changes[0][1], 1)
        self.assertEqual(changes[0][4]["replacements"][0]["word"], "Menschen")

    def test_low_evidence_and_inline_hyphens_are_preserved(self):
        result, changes = repair_words("Sel-tenes und Men-schen", "Sel- tenes und Men-schen", (
            Counter(seltenes=1, menschen=10), Counter(seltenes=2, menschen=2000), Counter()))
        self.assertEqual(result, "Sel- tenes und Men-schen")
        self.assertEqual(changes, [])

    def test_discretionary_hyphens_join_their_own_wrapped_word(self):
        result, changes = repair_words("Geistes\u00ad\nwissenschaft", "Geistes\u00ad wissenschaft\nVers bleibt", (Counter(geisteswissenschaft=4), Counter(geisteswissenschaft=10), Counter()))
        self.assertEqual(result, "Geisteswissenschaft\nVers bleibt")
        self.assertEqual(changes[0][1], 1)
        result, _ = repair_words("un\u00ad\n\nunserer", "un\u00ad\n\nunserer", (Counter(), Counter(), Counter()))
        self.assertEqual(result, "un\n\nunserer")


class NotesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.report = self.root / "server/priv/proofreading"
        (self.report / "works").mkdir(parents=True)
        content = self.root / "server/priv/content"
        content.mkdir(parents=True)
        self.text = "Äußere Welt 🌍 und Freiheit."
        self.checksum = hashlib.sha256(self.text.encode()).hexdigest()
        self.work = {"id": "ga-040", "ga_number": "GA 040", "title": "Wahrspruchworte", "available": True}
        (self.report / "catalog.json").write_text(json.dumps({"works": [self.work]}))
        (self.report / "works/ga-040.json").write_text(json.dumps({"work": self.work, "changes": [], "flags": []}))
        (content / "ga-040.json").write_text(json.dumps({"passages": [{"id": "verse", "text": self.text, "checksum": self.checksum}]}))
        self.workspace = Workspace(self.root)

    def test_unicode_anchor_persists_after_restart_and_exports_per_ga(self):
        quote = "🌍 und Freiheit"
        start = len(self.text[:self.text.index("🌍")].encode("utf-16-le")) // 2
        end = start + len(quote.encode("utf-16-le")) // 2
        note = self.workspace.save_note({"work_id": "ga-040", "passage_id": "verse", "quote": quote,
            "start_offset": start, "end_offset": end, "body": "Vers prüfen.", "status": "open"})
        restarted = Workspace(self.root)
        self.assertEqual(restarted.notes("ga-040")["notes"][0], note)
        changed = restarted.save_note({"body": "Quelle verglichen.", "status": "resolved"}, note["id"])
        self.assertEqual(changed["quote"], quote)
        self.assertEqual(changed["checksum"], self.checksum)
        restarted.review("ga-040", "reviewed")
        exported, _, _ = restarted.export()
        self.assertEqual(json.loads(exported)["notes"][0]["status"], "resolved")
        markdown, _, _ = restarted.export("markdown")
        self.assertIn("GA 040 · Wahrspruchworte", markdown)
        self.assertIn("Quelle verglichen.", markdown)
        restarted.delete_note(note["id"])
        self.assertEqual(restarted.notes()["notes"], [])

    def test_forged_quotes_and_invalid_offsets_are_rejected(self):
        with self.assertRaises(ValueError):
            self.workspace.save_note({"work_id": "ga-040", "passage_id": "verse", "quote": "Fremder Satz", "body": "Prüfen"})
        with self.assertRaises(ValueError):
            self.workspace.save_note({"work_id": "ga-040", "passage_id": "verse", "quote": "Welt", "start_offset": 0, "end_offset": 4, "body": "Prüfen"})
        with self.assertRaises(ValueError):
            self.workspace.review("ga-040", "imaginary")

    def test_original_contents_inventory_is_forwarded_without_synthetic_numbers(self):
        path = self.root / "server/priv/content/ga-040.json"
        content = json.loads(path.read_text())
        entries = [
            {"id": "source-part", "title": "I. Teil", "level": 1,
             "passage_id": "verse", "start_offset": 0, "parent_id": None},
            {"id": "source-chapter", "title": "Vorrede", "level": 2,
             "passage_id": "verse", "start_offset": 0, "parent_id": "source-part"},
        ]
        content["table_of_contents"] = entries
        path.write_text(json.dumps(content))
        detail = self.workspace.work("ga-040")
        self.assertEqual(detail["table_of_contents"], entries)
        self.assertEqual(detail["passages"], content["passages"])

    def test_http_serves_reports_and_rejects_foreign_origin_writes(self):
        class QuietHandler(Handler):
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        server.workspace = self.workspace
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"
        with urlopen(base + "/api/proofreading/catalog", timeout=5) as response:
            self.assertEqual(json.load(response)["works"][0]["id"], "ga-040")
        body = json.dumps({"work_id": "ga-040", "body": "HTTP-Notiz"}).encode()
        request = Request(base + "/api/proofreading/notes", data=body,
                          headers={"Content-Type": "application/json", "Origin": base})
        with urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 201)
            self.assertEqual(json.load(response)["note"]["body"], "HTTP-Notiz")
        request = Request(base + "/api/proofreading/notes", data=body,
                          headers={"Content-Type": "application/json", "Origin": "http://unrelated.example"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=5)
        self.assertEqual(error.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
