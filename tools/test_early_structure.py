#!/usr/bin/env python3
"""Regression checks for source outlines and their independent verifier."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from check_proofreading_samples import digest, inspect_source_outline, validate
from repair_early_structure import apply_plan


class EarlyStructureTests(unittest.TestCase):
    def fixture(self):
        texts = ("Vorworttext.", "📖\n\nEINSCHUB\n\nText *")
        passages = [{
            "id": f"ga-test-{index + 1}", "title": title, "text": text,
            "source_text": "Retained original: " + text,
            "checksum": digest(text.encode()), "ga_page": "S. 1",
            "metadata": {"page_numbers": [1], "page_marker_source": "original",
                         "annotations": []},
        } for index, (title, text) in enumerate(zip(("Vorwort", "1. I. Kapitel"), texts))]
        passages[1]["metadata"]["annotations"] = [
            {"id": "n1", "marker": "*", "text": "Original note", "start_offset": 19, "end_offset": 20}]
        prior = {"work_id": "ga-test", "title": "Book", "source_id": "source-test",
                 "source_epub_sha256": "a" * 64, "passages": passages}
        reading = [{"kind": "prose", "start_offset": 0, "end_offset": 2},
                   {"kind": "heading", "start_offset": 4, "end_offset": 12, "level": 2},
                   {"kind": "prose", "start_offset": 14, "end_offset": 20}]
        entries = [
            {"id": "ga-test-1", "title": "Vorwort", "level": 1, "passage_id": "ga-test-1",
             "start_offset": 0, "parent_id": None},
            {"id": "ga-test-2", "title": "I. Kapitel", "level": 1, "passage_id": "ga-test-2",
             "start_offset": 0, "parent_id": None},
            {"id": "ga-test-insertion", "title": "EINSCHUB", "level": 2, "passage_id": "ga-test-2",
             "start_offset": 4, "end_offset": 12, "parent_id": "ga-test-2"},
        ]
        plan = {"work_id": "ga-test", "edition": "Retained test edition",
                "source_identity": {"source_id": "source-test", "source_epub_sha256": "a" * 64},
                "evidence": [{"source": "Original edition contents and body"}],
                "passages": {p["id"]: {
                    "text_sha256": p["checksum"], "source_text_sha256": digest(p["source_text"].encode()),
                    "title": "Vorwort" if index == 0 else "I. Kapitel",
                } for index, p in enumerate(passages)}, "table_of_contents": entries}
        plan["passages"]["ga-test-2"]["reading_blocks"] = reading
        final = deepcopy(prior)
        final["passages"][1]["title"] = "I. Kapitel"
        final["passages"][1]["metadata"]["reading_blocks"] = deepcopy(reading)
        final["table_of_contents"] = deepcopy(entries)
        recipe_hash = digest(json.dumps(plan, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":")).encode())
        final["metadata"] = {"source_outline": {
            "recipe_sha256": recipe_hash, "offset_unit": "utf16",
            "scope": "original_headings_numbering_hierarchy_and_insertions",
            "edition": plan["edition"], "evidence": deepcopy(plan["evidence"]),
        }}
        events = {p["id"]: [{
            "passage_id": p["id"], "rule": "source_outline", "count": 1,
            "label": "Originale Überschriften, Nummerierung und Gliederung wiederhergestellt",
            "before_excerpt": p["title"],
            "after_excerpt": "\n".join(e["title"] for e in entries if e["passage_id"] == p["id"]),
            "recipe_sha256": recipe_hash, "text_unchanged": True,
        }] for p in passages}
        return prior, final, plan, events

    def test_exact_independent_projection_and_engine_idempotence(self):
        prior, final, plan, events = self.fixture()
        retained = deepcopy(prior)
        self.assertEqual(inspect_source_outline(prior, final, plan, events), ([], 2))
        applied, changes = apply_plan(prior, plan)
        self.assertEqual(applied, final)
        self.assertEqual(changes, [event for items in events.values() for event in items])
        repeated, changes = apply_plan(applied, plan)
        self.assertEqual(repeated, applied)
        self.assertEqual(changes, [])
        self.assertEqual(prior, retained)
        self.assertNotIn("reading_blocks", final["passages"][0]["metadata"])

    def test_edition_text_source_and_checksum_drift_are_rejected(self):
        mutations = [
            lambda p: p.update(source_epub_sha256="b" * 64),
            lambda p: p["passages"][1].update(text="Changed text"),
            lambda p: p["passages"][1].update(source_text="Changed source"),
            lambda p: p["passages"].reverse(),
        ]
        for mutate in mutations:
            prior, final, plan, events = self.fixture()
            mutate(prior)
            with self.subTest(mutation=mutate):
                self.assertTrue(inspect_source_outline(prior, final, plan, events)[0])
                with self.assertRaises(ValueError):
                    apply_plan(prior, plan)
        prior, final, plan, events = self.fixture()
        prior["passages"][0]["checksum"] = "c" * 64
        self.assertTrue(inspect_source_outline(prior, final, plan, events)[0])

    def test_invalid_heading_ids_parents_ranges_and_unicode_bounds_are_rejected(self):
        mutations = [
            lambda p: p["table_of_contents"][2].update(id="ga-test-2"),
            lambda p: p["table_of_contents"][2].update(parent_id="missing"),
            lambda p: p["table_of_contents"][2].update(level=1),
            lambda p: p["table_of_contents"][2].update(start_offset=20),
            lambda p: p["table_of_contents"][2].update(start_offset=1),
            lambda p: p["table_of_contents"][2].update(start_offset=True),
            lambda p: p["passages"]["ga-test-2"]["reading_blocks"][0].update(end_offset=1),
            lambda p: p["passages"]["ga-test-2"]["reading_blocks"][1].update(start_offset=0),
            lambda p: p["passages"]["ga-test-2"]["reading_blocks"].pop(),
        ]
        for mutate in mutations:
            prior, final, plan, events = self.fixture()
            mutate(plan)
            with self.subTest(mutation=mutate):
                self.assertTrue(inspect_source_outline(prior, final, plan, events)[0])
                with self.assertRaises(ValueError):
                    apply_plan(prior, plan)
        for end in (4, 21, True):
            prior, final, plan, events = self.fixture()
            plan["table_of_contents"][2]["end_offset"] = end
            self.assertTrue(inspect_source_outline(prior, final, plan, events)[0])

    def test_no_undeclared_text_pages_notes_metadata_or_document_changes(self):
        mutations = [
            lambda f: f["passages"][1].update(text=f["passages"][1]["text"] + " "),
            lambda f: f["passages"][1].update(source_text="Unreviewed source"),
            lambda f: f["passages"][1].update(checksum="d" * 64),
            lambda f: f["passages"][1].update(ga_page="S. 2"),
            lambda f: f["passages"][1]["metadata"]["annotations"][0].update(start_offset=18),
            lambda f: f["passages"][1]["metadata"].update(page_numbers=[2]),
            lambda f: f["passages"][1]["metadata"].update(unknown="Unreviewed"),
            lambda f: f["passages"][1]["metadata"]["reading_blocks"][1].update(level=3),
            lambda f: f.update(title="Different book"),
            lambda f: f["metadata"]["source_outline"].update(edition="Different edition"),
            lambda f: f["table_of_contents"][2].update(title="Invented title"),
        ]
        for mutate in mutations:
            prior, final, plan, events = self.fixture()
            mutate(final)
            with self.subTest(mutation=mutate):
                self.assertTrue(inspect_source_outline(prior, final, plan, events)[0])

    def test_missing_duplicate_or_forged_outline_ledger_is_rejected(self):
        mutations = [
            lambda e: e.pop("ga-test-1"),
            lambda e: e["ga-test-2"].append(deepcopy(e["ga-test-2"][0])),
            lambda e: e["ga-test-2"][0].update(recipe_sha256="e" * 64),
            lambda e: e["ga-test-2"][0].update(text_unchanged=False),
            lambda e: e["ga-test-2"][0].update(count=2),
        ]
        for mutate in mutations:
            prior, final, plan, events = self.fixture()
            mutate(events)
            self.assertTrue(inspect_source_outline(prior, final, plan, events)[0])

    def test_reviewed_dateline_continuation_and_group_metadata_are_exact(self):
        prior, final, plan, events = self.fixture()
        approved = {"source_dateline": "August 1924", "continuation_of": "ga-test-1",
                    "group_title": "Original group"}
        plan["passages"]["ga-test-2"].update(approved)
        final["passages"][1]["metadata"].update(approved)
        recipe_hash = digest(json.dumps(plan, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":")).encode())
        final["metadata"]["source_outline"]["recipe_sha256"] = recipe_hash
        for items in events.values():
            items[0]["recipe_sha256"] = recipe_hash
        self.assertEqual(inspect_source_outline(prior, final, plan, events), ([], 2))
        self.assertEqual(apply_plan(prior, plan)[0], final)
        for field in approved:
            altered = deepcopy(final)
            altered["passages"][1]["metadata"][field] = "Unreviewed value"
            self.assertTrue(inspect_source_outline(prior, altered, plan, events)[0])

    def test_full_source_title_can_use_a_retained_partial_body_heading(self):
        prior, final, plan, events = self.fixture()
        entry = plan["table_of_contents"][-1]
        entry.update(title="EINSCHUB, ursprüngliche Datierung", heading_text="EINSCHUB")
        final["table_of_contents"] = deepcopy(plan["table_of_contents"])
        recipe_hash = digest(json.dumps(plan, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":")).encode())
        final["metadata"]["source_outline"]["recipe_sha256"] = recipe_hash
        for pid, items in events.items():
            items[0]["recipe_sha256"] = recipe_hash
            items[0]["after_excerpt"] = "\n".join(e["title"] for e in plan["table_of_contents"]
                                                   if e["passage_id"] == pid)
        self.assertEqual(inspect_source_outline(prior, final, plan, events), ([], 2))
        self.assertEqual(apply_plan(prior, plan)[0], final)
        for invalid in ("Falscher Text", "", None, 4):
            altered = deepcopy(plan)
            altered["table_of_contents"][-1]["heading_text"] = invalid
            errors = inspect_source_outline(prior, final, altered, events)[0]
            self.assertTrue(any("heading label differs" in error for error in errors))

    def test_full_checker_requires_pre_outline_baseline_and_its_reported_hash(self):
        prior, final, plan, events = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            base, stage, outline = [Path(directory) / name for name in ("base", "stage", "outline")]
            def save(path, value):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value, ensure_ascii=False))
            for root, payload in ((base, prior), (stage, final), (outline, prior)):
                save(root / "content/ga-test.json", payload)
            def catalog(payload):
                return {"works": [{"id": "ga-test", "content_path": "content/ga-test.json",
                                   "passages": [{k: p[k] for k in ("id", "title", "checksum", "ga_page")}
                                                for p in payload["passages"]]}]}
            save(base / "library/catalog.json", catalog(prior))
            save(stage / "library/catalog.json", catalog(final))
            save(stage / "proofreading/catalog.json", {"generated_at": "test", "works": [{"id": "ga-test"}]})
            report_path = stage / "proofreading/works/ga-test.json"
            report = {"work": {
                "before_sha256": digest((base / "content/ga-test.json").read_bytes()),
                "after_sha256": digest((stage / "content/ga-test.json").read_bytes()),
                "outline_input_sha256": digest((outline / "content/ga-test.json").read_bytes()),
            }, "changes": [e for items in events.values() for e in items]}
            save(report_path, report)
            recipe_path = Path(directory) / "recipe.json"
            save(recipe_path, {"works": {"ga-test": plan}})
            def check():
                return validate(base, stage, outline_baseline=outline, outline_recipe=recipe_path)
            self.assertEqual(check()["status"], "passed")
            report["work"]["outline_input_sha256"] = "f" * 64
            save(report_path, report)
            self.assertTrue(any("Outline input hash" in p["error"] for p in check()["problems"]))
            (outline / "content/ga-test.json").unlink()
            self.assertTrue(any("Cannot independently validate source outline" in p["error"]
                                for p in check()["problems"]))


if __name__ == "__main__":
    unittest.main()
