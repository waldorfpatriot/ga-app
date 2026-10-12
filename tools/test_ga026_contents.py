#!/usr/bin/env python3
"""Verify GA 026 original contents labels against the retained source and body."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from build_ga026_contents import build, navigation_title, REVIEW, RECIPE, PAYLOAD, SOURCE
from check_proofreading_samples import inspect_source_outline
from finalize_library import read_json
from repair_early_structure import apply_plan, digest


class GA026ContentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = read_json(REVIEW)
        cls.recipe = read_json(RECIPE)
        cls.before = read_json(PAYLOAD)
        cls.built = build(cls.recipe, cls.before, cls.review)
        cls.plan = cls.built["works"]["ga-026"]
        cls.after, cls.changes = apply_plan(cls.before, cls.plan)

    def test_original_main_labels_order_ranges_and_subordinate_targets(self):
        entries = self.plan["table_of_contents"]
        self.assertEqual(len(entries), 98)
        mains = [entry for entry in entries[1:] if entry["level"] == 1]
        self.assertEqual(len(mains), 35)
        self.assertEqual([entry["title"] for entry in mains],
                         [navigation_title(row) for row in self.review["main_rows"]])
        self.assertEqual([entry["id"] for entry in mains],
                         [row["current_navigation_id"] for row in self.review["main_rows"]])
        covered = [n for entry in mains if entry.get("leitsaetze_range")
                   for n in range(entry["leitsaetze_range"][0], entry["leitsaetze_range"][1] + 1)]
        self.assertEqual(covered, list(range(1, 186)))
        original_children = [entry for entry in self.review["original_body_outline"] if entry["level"] > 1]
        children = [entry for entry in entries if entry["level"] > 1]
        self.assertEqual(len(children), 62)
        self.assertEqual(children, original_children)
        self.assertIn("Aphorismen aus einem am 24. August in London gehaltenen Mitgliedervortrag (LS 88 bis 102)",
                      [entry["title"] for entry in mains])
        self.assertIn("Fortsetzung der zweiten Betrachtung: (LS 131 bis 133)",
                      [entry["title"] for entry in mains])

    def test_inhalt_and_preface_are_distinct_original_targets(self):
        contents, preface = self.plan["table_of_contents"][:2]
        self.assertEqual((contents["title"], contents["source_role"], contents["start_offset"]),
                         ("Inhalt", "table_of_contents", 0))
        self.assertEqual(contents["source_range"], [0, 2494])
        self.assertEqual((preface["title"], preface["start_offset"]), ("Vorbemerkung", 2494))
        self.assertEqual(contents["passage_id"], preface["passage_id"])
        self.assertEqual(self.after["passages"][0]["title"], "Vorbemerkung")
        prefix = self.after["passages"][0]["text"].encode("utf-16-le")[:2 * 2494].decode("utf-16-le")
        self.assertEqual(digest(prefix), self.review["contents_anchor"]["text_sha256"])
        # The one source delimiter defect is normalized in navigation only.
        self.assertIn("Mitgliedervortrag (LS 88 bis 102\n\n", prefix)

    def test_partial_heading_spans_keep_exact_body_witnesses(self):
        by_id = {entry["id"]: entry for entry in self.plan["table_of_contents"]}
        passages = {passage["id"]: passage for passage in self.after["passages"]}
        checked = 0
        for original in self.review["original_body_outline"]:
            if "end_offset" not in original:
                continue
            entry = by_id[original["id"]]
            for key in ("start_offset", "end_offset"):
                self.assertEqual(entry.get(key), original.get(key))
            self.assertEqual(entry.get("heading_text", entry["title"]),
                             original.get("heading_text", original["title"]))
            passage = passages[entry["passage_id"]]
            observed = passage["text"].encode("utf-16-le")[2 * entry["start_offset"]:2 * entry["end_offset"]].decode("utf-16-le")
            self.assertEqual(" ".join(observed.split()), " ".join(entry.get("heading_text", entry["title"]).split()))
            checked += 1
        self.assertGreaterEqual(checked, 5)

    def test_all_body_source_checksum_page_and_annotation_fields_are_unchanged(self):
        self.assertEqual(len(self.before["passages"]), 97)
        self.assertEqual([p["id"] for p in self.before["passages"]],
                         [p["id"] for p in self.after["passages"]])
        for before, after in zip(self.before["passages"], self.after["passages"]):
            protected_before, protected_after = deepcopy(before), deepcopy(after)
            protected_before.pop("title")
            protected_after.pop("title")
            protected_before["metadata"].pop("group_title", None)
            protected_after["metadata"].pop("group_title", None)
            self.assertEqual(protected_before, protected_after, before["id"])
        self.assertEqual(sum("source_dateline" in p["metadata"] for p in self.after["passages"]), 71)
        self.assertEqual(sum("continuation_of" in p["metadata"] for p in self.after["passages"]), 2)
        by_id = {entry["id"]: entry for entry in self.plan["table_of_contents"]}
        for entry in self.plan["table_of_contents"]:
            if entry["parent_id"]:
                section = self.plan["passages"][entry["passage_id"]]
                if "group_title" in section:
                    self.assertEqual(section["group_title"], by_id[entry["parent_id"]]["title"])

    def test_independent_outline_verifier_accepts_new_titles_and_original_body_spans(self):
        events = {}
        for change in self.changes:
            events.setdefault(change["passage_id"], []).append(change)
        errors, _ = inspect_source_outline(self.before, self.after, self.plan, events)
        self.assertEqual(errors, [])

    def test_rebuild_and_application_are_idempotent_and_other_24_plans_unchanged(self):
        self.assertEqual(build(self.built, self.after, self.review), self.built)
        again, events = apply_plan(self.after, self.plan)
        self.assertEqual(again, self.after)
        self.assertEqual(events, [])
        for work_id in self.recipe["works"]:
            if work_id != "ga-026":
                self.assertEqual(self.built["works"][work_id], self.recipe["works"][work_id], work_id)

    def test_source_text_inventory_prefix_and_range_drift_fail_closed(self):
        for mutation in ("edition", "text", "source_text", "id", "order"):
            payload = deepcopy(self.before)
            if mutation == "edition":
                payload["source_epub_sha256"] = "unknown edition"
            elif mutation in {"text", "source_text"}:
                payload["passages"][0][mutation] += " changed"
            elif mutation == "id":
                payload["passages"][0]["id"] += "-changed"
            else:
                payload["passages"].reverse()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                build(self.recipe, payload, self.review)
        for mutation in ("prefix", "range", "label"):
            review = deepcopy(self.review)
            if mutation == "prefix":
                review["contents_anchor"]["text_sha256"] = "changed"
            elif mutation == "range":
                review["main_rows"][2]["leitsaetze_range"] = [62, 69]
            else:
                review["main_rows"][2]["original_main_title"] = "Unreviewed title"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                build(self.recipe, self.before, review)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "changed.epub"
            source.write_bytes(SOURCE.read_bytes() + b"changed")
            with self.assertRaises(ValueError):
                build(self.recipe, self.before, self.review, source)


if __name__ == "__main__":
    unittest.main()
