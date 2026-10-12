#!/usr/bin/env python3
"""GA032 source-bound layout, inventory and staging regression checks."""
from copy import deepcopy
from collections import Counter
import gzip
import hashlib
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from build_ga032_recipe import BASELINE, RECIPE, REVIEW, SOURCE, build, check_source
from finalize_library import read_json, write_json
from repair_ga032_readability import apply_layout, stage
from repair_source_structure import sha, validate_layout


class GA032ReadabilityTests(unittest.TestCase):
    maxDiff = 1200

    @classmethod
    def setUpClass(cls):
        cls.before = read_json(BASELINE)
        cls.recipe = read_json(RECIPE)
        cls.review = read_json(REVIEW)
        cls.after, cls.changes = apply_layout(cls.before, cls.recipe)
        cls.passages = {p["id"]: p for p in cls.after["passages"]}

    def test_frozen_recipe_rebuilds_and_covers_all_retained_passages(self):
        self.assertEqual(build(self.before), self.recipe)
        self.assertEqual(len(self.before["passages"]), 57)
        self.assertEqual(len(self.changes), 57)
        self.assertEqual(list(self.recipe["passages"]), [p["id"] for p in self.before["passages"]])
        self.assertEqual(sum(len(p["source_parts"]) for p in self.review["passages"].values()), 1590)
        self.assertGreater(sum(len(p["metadata"]["reading_blocks"]) for p in self.after["passages"]), 500)

    def test_source_inventory_annotations_and_nonlayout_fields_are_exact(self):
        for before, after in zip(self.before["passages"], self.after["passages"]):
            self.assertEqual(before["id"], after["id"])
            self.assertEqual(before["source_text"], after["source_text"])
            self.assertEqual(before["source_member"], after["source_member"])
            self.assertEqual(before["source_label"], after["source_label"])
            expected_notes = deepcopy(before["metadata"]["annotations"])
            for repair in self.recipe.get("annotation_repairs", []):
                if repair["passage_id"] == before["id"]:
                    note = next(n for n in expected_notes if n["id"] == repair["annotation_id"])
                    self.assertEqual(note["text"], repair["before"])
                    note["text"] = repair["after"]
            self.assertEqual(expected_notes, after["metadata"]["annotations"])
            self.assertEqual(sha(after["text"]), after["checksum"])
            validate_layout(after)
        self.assertEqual(sum(len(p["metadata"]["annotations"]) for p in self.after["passages"]), 10)
        for field in ("work_id", "passage_count", "content_completeness", "proofing", "source_sha256", "source_epub_sha256"):
            self.assertEqual(self.before[field], self.after[field], field)

    def test_no_letter_inventory_changes_outside_exact_physical_seams(self):
        compact = lambda text: re.sub(r"\s", "", text)
        for before, after in zip(self.before["passages"], self.after["passages"]):
            expected = compact(before["text"])
            for omission in self.review["passages"][before["id"]].get("omissions", []):
                token = compact(before["text"][omission["start_codepoint"]:omission["end_codepoint"]])
                self.assertEqual(expected.count(token), 1)
                expected = expected.replace(token, "")
            for repair in self.recipe["passages"][before["id"]]["edits"]:
                old, new = compact(repair["old"]), compact(repair["new"])
                self.assertIn(old, expected)
                expected = expected.replace(old, new)
            self.assertEqual(expected, compact(after["text"]), before["id"])

    def test_printed_first_page_continuation_and_real_compounds_survive(self):
        first = self.after["passages"][0]["text"]
        self.assertIn("Wahl dessen ausspricht", first)
        self.assertNotIn("dessen\n\nausspricht", first)
        self.assertIn("Farbenharmonie", first)
        self.assertIn("Roh-Stoffliche", first)
        self.assertIn("\n\nWer überhaupt Augen", first)

    def test_verse_roles_and_complete_article_sections(self):
        verse_blocks = []
        for passage in self.after["passages"]:
            for block in passage["metadata"]["reading_blocks"]:
                if block["kind"] == "verse":
                    text = passage["text"].encode("utf-16-le")[2 * block["start_offset"]:2 * block["end_offset"]].decode("utf-16-le")
                    verse_blocks.append(text)
            sections = passage["metadata"].get("reading_sections", [])
            if sections:
                self.assertEqual(sections[0]["start_offset"], 0)
                self.assertEqual(sections[-1]["end_offset"], len(passage["text"].encode("utf-16-le")) // 2)
        self.assertTrue(verse_blocks)
        self.assertTrue(any("\n" in text for text in verse_blocks))
        self.assertGreater(len(self.after["table_of_contents"]), 57)
        self.assertTrue(all(page < 1000 for p in self.after["passages"] for page in p["metadata"]["page_numbers"]))

    def test_exact_year_literals_and_annotation_wraps_are_restored(self):
        repairs = [repair for p in self.recipe["passages"].values() for repair in p["edits"]
                   if repair.get("kind") == "literal_year_restoration"]
        self.assertEqual(len(repairs), 15)
        annotation_repairs = self.recipe["annotation_repairs"]
        self.assertEqual(len(annotation_repairs), 10)
        self.assertEqual(sum(r["before"].count("\n") for r in annotation_repairs), 40)
        for repair in annotation_repairs:
            self.assertNotIn("\n", repair["after"])
            self.assertEqual(re.sub(r"\s", "", repair["before"]), re.sub(r"\s", "", repair["after"]))
            self.assertEqual(repair["before"].count("↩"), repair["after"].count("↩"))
            note = next(n for n in self.passages[repair["passage_id"]]["metadata"]["annotations"] if n["id"] == repair["annotation_id"])
            self.assertEqual(note["text"], repair["after"])

    def test_exact_poetic_overruns_and_missing_prose_continuation(self):
        overruns = [repair for p in self.recipe["passages"].values() for repair in p["edits"]
                    if repair.get("kind") == "poetic_overrun"]
        self.assertEqual(len(overruns), 5)
        for repair in overruns:
            old = Counter(re.sub(r"\s", "", repair["old"]))
            new = Counter(re.sub(r"\s", "", repair["new"]))
            delta = old - new
            self.assertFalse(new - old)
            self.assertTrue(set(delta) <= {"[", "-"})
            self.assertTrue(repair.get("source_witnesses"))
        rose = self.passages["ga-032-doc-heading-8"]["text"]
        self.assertIn("Pulsschlag\nDes Seins:", rose)
        self.assertNotIn("Puls-\nDes", rose)
        modern = self.passages["ga-032-doc-heading-49"]["text"]
        self.assertIn("\nHier,\n", modern)
        self.assertIn("\nlaut\n", modern)
        self.assertIn("(Berlin 1899) enthalten:", modern)
        self.assertNotIn("(Berlin 1899) ent-", modern)
        stars = self.passages["ga-032-doc-heading-37"]["text"]
        self.assertIn("Ach, unsre leuchtenden Tage\nGlänzen wie ewige Sterne.\nAls Trost für künftige Klage\nGlüh'n sie aus goldner Ferne.\n\nNicht weinen, weil sie vorüber!\nLächeln, weil sie gewesen!\nUnd werden die Tage auch trüber,\nUnsere Sterne erlösen!", stars)
        fragments = [repair for p in self.recipe["passages"].values() for repair in p["edits"]
                     if repair.get("kind") == "pdf_fragment_restoration"]
        self.assertEqual(len(fragments), 1)
        self.assertEqual(fragments[0]["source_token"], "halten:")

    def test_idempotence_and_unreviewed_input_metadata_fail_closed(self):
        repeated, changes = apply_layout(self.after, self.recipe)
        self.assertEqual(repeated, self.after)
        self.assertEqual(changes, [])
        for mutation in ("text", "source_text", "inventory", "lost", "duplicate", "metadata", "output_metadata", "annotation"):
            before, recipe = deepcopy(self.before), deepcopy(self.recipe)
            pid = before["passages"][0]["id"]
            if mutation == "text": before["passages"][0]["text"] += " fremd"
            elif mutation == "source_text": before["passages"][0]["source_text"] += " fremd"
            elif mutation == "inventory": before["passages"].pop()
            elif mutation == "lost": recipe["passages"][pid]["segments"].pop()
            elif mutation == "duplicate": recipe["passages"][pid]["segments"].append(deepcopy(recipe["passages"][pid]["segments"][0]))
            elif mutation == "metadata":
                repair = recipe["metadata_repairs"][0]
                passage = next(p for p in before["passages"] if p["id"] == repair["passage_id"])
                field = next(iter(repair["before"]))
                if field == "page_numbers": passage["metadata"][field] = [999]
                else: passage[field] = "fremd"
            elif mutation == "annotation": before["passages"][0]["metadata"]["annotations"][0]["text"] += " fremd"
            else: recipe["passages"][pid]["output_metadata"]["title"] = "fremd"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                apply_layout(before, recipe)
        review = deepcopy(self.review)
        review["passages"][pid]["source_parts"][0]["source_paragraph_sha256"] = "wrong"
        with self.assertRaises(ValueError): check_source(SOURCE, review)
        review = deepcopy(self.review)
        review["passages"][pid]["starts"][0]["source_paragraph_sha256"] = "wrong"
        with self.assertRaises(ValueError): check_source(SOURCE, review)
        review = deepcopy(self.review)
        fragment = next(repair for p in review["passages"].values() for repair in p["edits"]
                        if repair.get("kind") == "pdf_fragment_restoration")
        fragment["pdf_raster_witness"]["crop_pixels_sha256"] = "wrong"
        with self.assertRaises(ValueError): check_source(SOURCE, review)

    def test_poetic_and_word_continuations_reject_character_changes(self):
        edits = [(pid, index) for pid, passage in self.review["passages"].items()
                 for index, repair in enumerate(passage.get("edits", []))
                 if repair.get("kind") == "poetic_overrun"]
        self.assertEqual(len(edits), 5)
        edits.append(next((pid, index) for pid, passage in self.review["passages"].items()
                          for index, repair in enumerate(passage.get("edits", []))
                          if repair.get("kind") == "physical_word_seam"))
        for pid, index in edits:
            review = deepcopy(self.review)
            repair = review["passages"][pid]["edits"][index]
            repair["new"] += "x"
            with self.subTest(passage_id=pid, old=repair["old"]), self.assertRaises(ValueError):
                check_source(SOURCE, review)

    def test_stage_separates_current_gzip_bytes_and_frozen_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, baseline, output = [Path(temporary) / name for name in ("root", "baseline", "stage")]
            for folder in ("content", "library", "proofreading/works"):
                (root / folder).mkdir(parents=True)
            original = root / "content/ga-032.json.gz"
            original.write_bytes(gzip.compress(gzip.decompress(BASELINE.read_bytes()), compresslevel=1, mtime=123))
            application_hash = hashlib.sha256(original.read_bytes()).hexdigest()
            protected = root / "content/ga-050.json.gz"
            protected.write_bytes(b"protected sentence-layer bytes")
            write_json(root / "proofreading/works/ga-032.json", {"work": {"after_sha256": application_hash, "checks": []}, "changes": []})
            write_json(root / "proofreading/catalog.json", {"generated_at": "unchanged"})
            write_json(root / "library/catalog.json", {"works": [{"id": "ga-032", "passages": [{"id": p["id"]} for p in self.before["passages"]]}]})
            with patch("proofread_library.complete_stage"), patch("repair_ga032_readability.verify"):
                stage(root, output, self.recipe, baseline)
            saved = baseline / "content/ga-032.json.gz"
            frozen_hash = hashlib.sha256(saved.read_bytes()).hexdigest()
            self.assertNotEqual(application_hash, frozen_hash)
            self.assertEqual(read_json(saved), self.before)
            report = read_json(output / "proofreading/works/ga-032.json")["work"]
            self.assertEqual(report["application_base_sha256"], application_hash)
            self.assertEqual(report["layout_input_sha256"], frozen_hash)
            self.assertEqual((output / "content/ga-050.json.gz").read_bytes(), protected.read_bytes())
            repeated = Path(temporary) / "repeat"
            with patch("proofread_library.complete_stage"), patch("repair_ga032_readability.verify"):
                self.assertEqual(stage(output, repeated, self.recipe, baseline), [])
            self.assertEqual(read_json(repeated / "content/ga-032.json.gz"), self.after)


if __name__ == "__main__":
    unittest.main()
