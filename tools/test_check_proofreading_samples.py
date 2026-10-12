#!/usr/bin/env python3
"""Exercise the independent layout verifier, including intentional tampering."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from check_proofreading_samples import (GA032_PDF, crop_mono_raster, digest, inspect_ga030_recovery,
    inspect_ga032_layout, inspect_ga032_pdf_fragment, inspect_ga032_word_repair,
    inspect_source_layout, pbm_raster, utf16_length, validate)


class SourceLayoutValidationTests(unittest.TestCase):
    def fixture(self):
        original = "A-\nbc\n\nTITLE\n\nVerse 😀 *\n\n'12"
        corrected = "Abc\n\nTITLE\n\nVerse 😀 *"
        pid = "ga-test-1"
        prior = {
            "work_id": "ga-test", "source_sha256": "a" * 64,
            "source_epub_sha256": "b" * 64, "title": "Book",
            "passages": [{"id": pid, "title": "Reader", "text": original,
                          "source_text": "Immutable source", "checksum": digest(original.encode()),
                          "ga_page": "S. 10", "metadata": {
                              "page_numbers": [10], "page_marker_source": "original",
                              "annotations": [{"id": "n", "marker": "*", "text": "Old note"}]}}]}
        recipe = {
            "schema_version": 1, "work_id": "ga-test", "offset_unit": "utf16",
            "source_sha256": "a" * 64, "source_epub_sha256": "b" * 64,
            "source_url": "https://example.com/source.doc", "passages": {pid: {
                "input_sha256": digest(original.encode()), "output_sha256": digest(corrected.encode()),
                "group_title": "Group", "segments": [
                    {"kind": "prose", "parts": [0], "join": " "},
                    {"kind": "heading", "parts": [1], "join": " ", "level": 1},
                    {"kind": "verse", "parts": [2], "join": "\n", "pages": [12]}],
                "edits": [{"old": "A- bc", "new": "Abc", "evidence": "Printed wrap"}],
                "omitted_parts": [{"block": 3, "page": 12, "evidence": "Page footer"}],
                "annotations": {"n": {"text": "Definition", "reference_context": "Verse 😀 *"}}}}}
        revision = digest(json.dumps(recipe, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode())
        final = deepcopy(prior)
        passage = final["passages"][0]
        passage.update(text=corrected, checksum=digest(corrected.encode()), ga_page="S. 12")
        passage["metadata"] = {
            "page_numbers": [12], "page_marker_source": "source_bound_original_doc_page_footers",
            "annotations": [{"id": "n", "marker": "*", "source_text": "Old note", "text": "Definition",
                             "start_offset": 21, "end_offset": 22}],
            "reading_blocks": [{"kind": "prose", "start_offset": 0, "end_offset": 3},
                               {"kind": "heading", "start_offset": 5, "end_offset": 10, "level": 1},
                               {"kind": "verse", "start_offset": 12, "end_offset": 22}],
            "page_anchors": [{"page": 12, "start_offset": 12, "source": "original_doc_page_footer"}],
            "group_title": "Group", "structure_revision": revision}
        final["metadata"] = {"source_layout": {
            "recipe_sha256": revision, "source_sha256": "a" * 64,
            "source_url": recipe["source_url"], "offset_unit": "utf16",
            "review_scope": "structure_and_evidenced_repairs"}}
        final["table_of_contents"] = [
            {"id": "ga-test-part-1", "title": "Group", "level": 1, "passage_id": pid,
             "start_offset": 0, "parent_id": None},
            {"id": pid, "title": "Reader", "level": 2, "passage_id": pid,
             "start_offset": 0, "parent_id": "ga-test-part-1"},
            {"id": "ga-test-1-heading-2", "title": "TITLE", "level": 3, "passage_id": pid,
             "start_offset": 5, "parent_id": pid}]
        events = {pid: [{"rule": "source_layout", "count": 1, "layout_blocks": 3,
                         "replacements": [{"original": "'12", "word": "", "count": 1,
                                           "evidence": "Page footer", "page": 12},
                                          {"original": "A- bc", "word": "Abc", "count": 1,
                                           "evidence": "Printed wrap"}]}]}
        return prior, final, recipe, events

    def test_exact_projection_and_utf16_notes(self):
        prior, final, recipe, events = self.fixture()
        untouched = deepcopy(prior)
        self.assertEqual(inspect_source_layout(prior, final, recipe, events), ([], 2))
        self.assertEqual(prior, untouched)

    def section_fixture(self):
        prior, final, recipe, events = self.fixture()
        pid = "ga-test-1"
        recipe["passages"][pid]["sections"] = [
            {"title": "Reader", "label_kind": "source_title", "start_segment": 0, "end_segment": 1, "evidence": "Original passage title"},
            {"title": "TITLE", "label_kind": "source_title", "start_segment": 1, "end_segment": 2, "evidence": "Original heading"},
            {"title": "Verse 😀 *", "label_kind": "incipit", "start_segment": 2, "end_segment": 3, "evidence": "Exact opening verse"}]
        revision = digest(json.dumps(recipe, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode())
        meta = final["passages"][0]["metadata"]
        meta["structure_revision"] = revision
        final["metadata"]["source_layout"]["recipe_sha256"] = revision
        meta["reading_sections"] = [
            {"id": pid, "title": "Reader", "label_kind": "source_title", "start_offset": 0, "end_offset": 3},
            {"id": pid + "-section-2", "title": "TITLE", "label_kind": "source_title", "start_offset": 5, "end_offset": 10},
            {"id": pid + "-section-3", "title": "Verse 😀 *", "label_kind": "incipit", "start_offset": 12, "end_offset": 22}]
        final["table_of_contents"] = [final["table_of_contents"][0]] + [
            {"id": section["id"], "title": section["title"], "level": 2,
             "passage_id": pid, "start_offset": section["start_offset"], "parent_id": "ga-test-part-1"}
            for section in meta["reading_sections"]]
        return prior, final, recipe, events

    def test_section_siblings_have_exact_labels_and_deduplicated_headings(self):
        self.assertEqual(inspect_source_layout(*self.section_fixture()), ([], 2))

    def test_section_metadata_ids_labels_ranges_and_toc_tampering_are_rejected(self):
        for mutate in (lambda f: f["passages"][0]["metadata"]["reading_sections"][1].update(id="ga-test-1"),
                       lambda f: f["passages"][0]["metadata"]["reading_sections"][2].update(title="Invented"),
                       lambda f: f["passages"][0]["metadata"]["reading_sections"][2].update(label_kind="source_title"),
                       lambda f: f["passages"][0]["metadata"]["reading_sections"][2].update(end_offset=19),
                       lambda f: f["passages"][0]["metadata"]["reading_sections"].pop(),
                       lambda f: f["table_of_contents"][2].update(parent_id="ga-test-1")):
            prior, final, recipe, events = self.section_fixture()
            mutate(final)
            self.assertTrue(inspect_source_layout(prior, final, recipe, events)[0])

    def test_section_input_ranges_and_source_labels_must_be_valid(self):
        mutations = [
            (lambda s: s[0].update(start_segment=1), "segment range"),
            (lambda s: s[1].update(start_segment=0), "overlap"),
            (lambda s: s[2].update(end_segment=4), "segment range"),
            (lambda s: s[0].update(start_segment=False), "segment range"),
            (lambda s: s[2].update(title="Invented"), "incipit differs"),
            (lambda s: s[1].update(title="Invented"), "no original heading"),
            (lambda s: s[1].pop("evidence"), "source evidence"),
            (lambda s: s.pop(), "final visible text"),
            (lambda s: s.clear(), "full nonempty passage")]
        for mutate, diagnostic in mutations:
            prior, final, recipe, events = self.section_fixture()
            mutate(recipe["passages"]["ga-test-1"]["sections"])
            self.assertTrue(any(diagnostic in e for e in inspect_source_layout(prior, final, recipe, events)[0]), diagnostic)

    def test_internal_heading_remains_under_its_own_section(self):
        prior, final, recipe, events = self.section_fixture()
        sections = recipe["passages"]["ga-test-1"]["sections"]
        sections[0]["end_segment"] = 2
        del sections[1]
        meta = final["passages"][0]["metadata"]
        meta["reading_sections"][0]["end_offset"] = 10
        del meta["reading_sections"][1]
        meta["reading_sections"][1]["id"] = "ga-test-1-section-2"
        revision = digest(json.dumps(recipe, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode())
        meta["structure_revision"] = revision
        final["metadata"]["source_layout"]["recipe_sha256"] = revision
        final["table_of_contents"][2] = {
            "id": "ga-test-1-heading-2", "title": "TITLE", "level": 3, "passage_id": "ga-test-1",
            "start_offset": 5, "parent_id": "ga-test-1"}
        final["table_of_contents"][3]["id"] = "ga-test-1-section-2"
        self.assertEqual(inspect_source_layout(prior, final, recipe, events), ([], 2))

    def test_section_label_cannot_be_taken_from_a_later_block(self):
        for title, kind, diagnostic in (("TITLE", "source_title", "no original heading"),
                                        ("Verse 😀 *", "incipit", "incipit differs")):
            prior, final, recipe, events = self.fixture()
            recipe["passages"]["ga-test-1"]["sections"] = [{
                "title": title, "label_kind": kind, "start_segment": 0, "end_segment": 3,
                "evidence": "A later source label is not the actual section opening"}]
            self.assertTrue(any(diagnostic in e for e in inspect_source_layout(prior, final, recipe, events)[0]))

    def hierarchy_fixture(self, chunks, spans, expected_children):
        """Build source ranges; expected hierarchy is supplied explicitly."""
        pid = "ga-test-1"
        text = "\n\n".join(value for _, value, _ in chunks)
        prior = {"work_id": "ga-test", "source_sha256": "a" * 64,
                 "source_epub_sha256": "b" * 64, "title": "Book",
                 "passages": [{"id": pid, "title": spans[0][0], "text": text,
                               "source_text": text, "checksum": digest(text.encode()), "metadata": {}}]}
        reading, segments, offset = [], [], 0
        for index, (kind, value, level) in enumerate(chunks):
            start = offset + (2 if index else 0)
            offset = start + utf16_length(value)
            block = {"kind": kind, "start_offset": start, "end_offset": offset}
            segment = {"kind": kind, "parts": [index], "join": "\n" if kind == "verse" else " "}
            if kind == "heading":
                block["level"] = segment["level"] = level
            reading.append(block)
            segments.append(segment)
        plan = {"input_sha256": digest(text.encode()), "output_sha256": digest(text.encode()),
                "group_title": "Seelenkalender", "segments": segments,
                "sections": [{"title": title, "label_kind": "source_title", "start_segment": first,
                              "end_segment": end, "evidence": "Original source heading"}
                             for title, first, end in spans]}
        recipe = {"schema_version": 1, "work_id": "ga-test", "offset_unit": "utf16",
                  "source_sha256": "a" * 64, "source_epub_sha256": "b" * 64,
                  "source_url": "https://example.com/source.doc", "passages": {pid: plan}}
        revision = digest(json.dumps(recipe, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode())
        final = deepcopy(prior)
        sections = [{"id": pid if not index else f"{pid}-section-{index + 1}", "title": title,
                     "label_kind": "source_title", "start_offset": reading[first]["start_offset"],
                     "end_offset": reading[end - 1]["end_offset"]}
                    for index, (title, first, end) in enumerate(spans)]
        final["passages"][0]["metadata"] = {
            "reading_blocks": reading, "reading_sections": sections, "group_title": "Seelenkalender",
            "structure_revision": revision}
        final["metadata"] = {"source_layout": {
            "recipe_sha256": revision, "source_sha256": "a" * 64, "source_url": recipe["source_url"],
            "offset_unit": "utf16", "review_scope": "structure_and_evidenced_repairs"}}
        toc = [{"id": "ga-test-part-1", "title": "Seelenkalender", "level": 1,
                "passage_id": pid, "start_offset": 0, "parent_id": None}]
        for index, section in enumerate(sections):
            toc.append({"id": section["id"], "title": section["title"], "level": 2,
                        "passage_id": pid, "start_offset": section["start_offset"], "parent_id": "ga-test-part-1"})
            for owner, block_index, level, parent_block in expected_children:
                if owner == index:
                    toc.append({"id": f"{pid}-heading-{block_index + 1}", "title": chunks[block_index][1],
                                "level": level, "passage_id": pid, "start_offset": reading[block_index]["start_offset"],
                                "parent_id": section["id"] if parent_block is None else f"{pid}-heading-{parent_block + 1}"})
        final["table_of_contents"] = toc
        return prior, final, recipe, {pid: [{"rule": "source_layout", "count": 1, "layout_blocks": len(reading), "replacements": []}]}

    def test_calendar_prefaces_and_seasons_are_siblings_with_dates_and_numbers_below(self):
        chunks = [("prose", "Text des ersten Vorworts.", None),
                  ("heading", "VORWORT ZUR ZWEITEN AUSGABE", 1),
                  ("prose", "Text des zweiten Vorworts.", None),
                  ("heading", "FRÜHLING", 1), ("heading", "Erste Woche 1.–6. April", 2),
                  ("heading", "1", 3), ("verse", "Frühlingsvers\nZweite Zeile", None),
                  ("heading", "SOMMER", 1), ("heading", "Sommerwoche", 2),
                  ("heading", "2", 3), ("verse", "Sommervers\nZweite Zeile", None),
                  ("heading", "HERBST", 1), ("heading", "Herbstwoche", 2),
                  ("heading", "3", 3), ("verse", "Herbstvers\nZweite Zeile", None),
                  ("heading", "WINTER", 1), ("heading", "Winterwoche", 3),
                  ("heading", "4", 4), ("verse", "Wintervers\nZweite Zeile", None)]
        spans = [("VORWORT ZUR ERSTEN AUSGABE", 0, 1), ("VORWORT ZUR ZWEITEN AUSGABE", 1, 3),
                 ("FRÜHLING", 3, 7), ("SOMMER", 7, 11), ("HERBST", 11, 15), ("WINTER", 15, 19)]
        children = [(2, 4, 3, None), (2, 5, 4, 4), (3, 8, 3, None), (3, 9, 4, 8),
                    (4, 12, 3, None), (4, 13, 4, 12), (5, 16, 3, None), (5, 17, 4, 16)]
        prior, final, recipe, events = self.hierarchy_fixture(chunks, spans, children)
        self.assertEqual(inspect_source_layout(prior, final, recipe, events), ([], 0))
        siblings = [entry for entry in final["table_of_contents"] if entry["level"] == 2]
        self.assertEqual(len(siblings), 6)
        self.assertEqual({entry["parent_id"] for entry in siblings}, {"ga-test-part-1"})
        final["table_of_contents"][2].update(level=3, parent_id="ga-test-1")
        self.assertTrue(inspect_source_layout(prior, final, recipe, events)[0])

    def test_j_and_b_are_direct_children_even_with_original_heading_level_two(self):
        chunks = [("heading", "J", 2), ("verse", "Erster Spruch\nZweite Zeile", None),
                  ("heading", "B", 2), ("verse", "Zweiter Spruch\nZweite Zeile", None)]
        args = self.hierarchy_fixture(chunks, [("DIE VIER SPRÜCHE DER SÄULENWEISHEIT", 0, 4)],
                                      [(0, 0, 3, None), (0, 2, 3, None)])
        self.assertEqual(inspect_source_layout(*args), ([], 0))

    def test_source_and_arbitrary_metadata_changes_are_rejected(self):
        for mutate in (lambda p: p.update(source_text="Changed source"),
                       lambda p: p["metadata"].update(unapproved="New metadata"),
                       lambda p: p.update(title="Unreviewed title")):
            prior, final, recipe, events = self.fixture()
            mutate(final["passages"][0])
            self.assertTrue(inspect_source_layout(prior, final, recipe, events)[0])

    def test_ledger_count_evidence_and_missing_event_are_rejected(self):
        for mutate in (lambda e: e["ga-test-1"][0]["replacements"][1].update(count=2),
                       lambda e: e["ga-test-1"][0]["replacements"][1].update(evidence="Invented"),
                       lambda e: e.update({"ga-test-1": []})):
            prior, final, recipe, events = self.fixture()
            mutate(events)
            self.assertTrue(inspect_source_layout(prior, final, recipe, events)[0])

    def test_bad_note_page_and_toc_anchors_are_rejected(self):
        for mutate in (lambda f: f["passages"][0]["metadata"]["annotations"][0].update(start_offset=20),
                       lambda f: f["passages"][0]["metadata"]["page_anchors"][0].update(start_offset=13),
                       lambda f: f["table_of_contents"][-1].update(parent_id="Missing parent")):
            prior, final, recipe, events = self.fixture()
            mutate(final)
            self.assertTrue(inspect_source_layout(prior, final, recipe, events)[0])

    def test_frozen_input_output_and_source_hashes_are_required(self):
        for mutate in (lambda r: r.update(source_sha256="c" * 64),
                       lambda r: r["passages"]["ga-test-1"].update(input_sha256="c" * 64),
                       lambda r: r["passages"]["ga-test-1"].update(output_sha256="c" * 64)):
            prior, final, recipe, events = self.fixture()
            mutate(recipe)
            self.assertTrue(inspect_source_layout(prior, final, recipe, events)[0])

    def test_evidenced_dashes_preserve_compound_hyphens(self):
        prior, final, recipe, events = self.fixture()
        old, new = prior["passages"][0], final["passages"][0]
        old["text"] = old["text"].replace("\n\n'12", " - Christus-Impuls\n\n'12")
        new["text"] += " – Christus-Impuls"
        old["checksum"] = digest(old["text"].encode())
        new["checksum"] = digest(new["text"].encode())
        plan = recipe["passages"]["ga-test-1"]
        plan.update(input_sha256=old["checksum"], output_sha256=new["checksum"],
                    typographic_dashes="Printed standalone dash")
        revision = digest(json.dumps(recipe, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode())
        new["metadata"]["structure_revision"] = revision
        new["metadata"]["reading_blocks"][-1]["end_offset"] = utf16_length(new["text"])
        final["metadata"]["source_layout"]["recipe_sha256"] = revision
        events["ga-test-1"][0]["replacements"].append(
            {"original": "-", "word": "–", "count": 1, "evidence": "Printed standalone dash"})
        self.assertEqual(inspect_source_layout(prior, final, recipe, events), ([], 3))
        new["text"] = new["text"].replace("Christus-Impuls", "ChristusImpuls")
        self.assertTrue(inspect_source_layout(prior, final, recipe, events)[0])

    def test_source_pages_inside_joined_parts_and_after_unicode(self):
        prior, final, recipe, events = self.fixture()
        plan = recipe["passages"]["ga-test-1"]
        plan["segments"][0]["parts"] = [0, 1]
        del plan["segments"][1]
        cue = lambda page, part, point, section: {
            "page": page, "part_index": part, "start_codepoint": point,
            "confidence": "confirmed", "source_section": section}
        plan["segments"][0]["page_evidence"] = [cue(10, 0, 0, 1), cue(11, 0, 3, 1), cue(12, 1, 0, 1)]
        plan["segments"][1].pop("pages")
        plan["segments"][1]["page_evidence"] = [cue(13, 0, 8, 2)]
        passage = final["passages"][0]
        passage["text"] = "Abc TITLE\n\nVerse 😀 *"
        passage["checksum"] = digest(passage["text"].encode())
        passage["ga_page"] = "S. 10–13"
        plan["output_sha256"] = passage["checksum"]
        revision = digest(json.dumps(recipe, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode())
        meta = passage["metadata"]
        meta.update(page_numbers=[10, 11, 12, 13], structure_revision=revision,
                    reading_blocks=[{"kind": "prose", "start_offset": 0, "end_offset": 9},
                                    {"kind": "verse", "start_offset": 11, "end_offset": 21}],
                    page_anchors=[{"page": page, "start_offset": offset, "source": "original_doc_page_footer",
                                   "confidence": "confirmed", "source_section": section}
                                  for page, offset, section in ((10, 0, 1), (11, 1, 1), (12, 4, 1), (13, 20, 2))])
        meta["annotations"][0].update(start_offset=20, end_offset=21)
        final["metadata"]["source_layout"]["recipe_sha256"] = revision
        final["table_of_contents"].pop()
        events["ga-test-1"][0]["layout_blocks"] = 2
        self.assertEqual(inspect_source_layout(prior, final, recipe, events), ([], 2))
        # A source boundary inside the removed lexical hyphen needs review.
        plan["segments"][0]["page_evidence"][1]["start_codepoint"] = 2
        errors = inspect_source_layout(prior, final, recipe, events)[0]
        self.assertTrue(any("inside a lexical repair" in error for error in errors))

    def test_invalid_source_page_slices_are_rejected(self):
        for part_index, point in ((-1, 0), (1, 0), (0, -1), (0, 5), (True, 0), (0, True)):
            prior, final, recipe, events = self.fixture()
            recipe["passages"]["ga-test-1"]["segments"][0]["page_evidence"] = [{
                "page": 10, "part_index": part_index, "start_codepoint": point,
                "confidence": "confirmed", "source_section": 1}]
            errors = inspect_source_layout(prior, final, recipe, events)[0]
            self.assertTrue(any("invalid source page slice" in error for error in errors))

    def test_omissions_cannot_remove_prose_and_slices_cannot_overlap(self):
        for mutate in (lambda p: p["omitted_parts"][0].update(block=2),
                       lambda p: p["segments"][0]["parts"].append(0)):
            prior, final, recipe, events = self.fixture()
            mutate(recipe["passages"]["ga-test-1"])
            self.assertTrue(inspect_source_layout(prior, final, recipe, events)[0])

    def test_corpus_validator_requires_preserved_layout_baseline(self):
        prior, final, recipe, events = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            base, stage, layout = [Path(directory) / name for name in ("base", "stage", "layout")]

            def save(path, data):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data, ensure_ascii=False))

            for root, payload in ((base, prior), (stage, final), (layout, prior)):
                save(root / "content/ga-test.json", payload)
            catalog = lambda payload: {"works": [{"id": "ga-test", "content_path": "content/ga-test.json",
                                                  "passages": [{key: p[key] for key in ("id", "title", "checksum", "ga_page")}
                                                               for p in payload["passages"]]}]}
            save(base / "library/catalog.json", catalog(prior))
            save(stage / "library/catalog.json", catalog(final))
            save(stage / "proofreading/catalog.json", {"generated_at": "test", "works": [{"id": "ga-test"}]})
            save(stage / "proofreading/works/ga-test.json", {"work": {
                "before_sha256": digest((base / "content/ga-test.json").read_bytes()),
                "after_sha256": digest((stage / "content/ga-test.json").read_bytes()),
                "application_base_sha256": digest((layout / "content/ga-test.json").read_bytes())},
                "changes": [{**event, "passage_id": pid} for pid, items in events.items() for event in items]})
            recipe_path = Path(directory) / "recipe.json"
            save(recipe_path, recipe)
            self.assertEqual(validate(base, stage, layout, recipe_path)["status"], "passed")
            report_path = stage / "proofreading/works/ga-test.json"
            report = json.loads(report_path.read_text())
            report["work"].update(layout_input_sha256=report["work"]["application_base_sha256"],
                                  application_base_sha256="a" * 64)
            save(report_path, report)
            self.assertEqual(validate(base, stage, layout, recipe_path)["status"], "passed")
            report["work"]["layout_input_sha256"] = "b" * 64
            save(report_path, report)
            self.assertTrue(any("Layout input hash" in p["error"]
                                for p in validate(base, stage, layout, recipe_path)["problems"]))
            (layout / "content/ga-test.json").unlink()
            result = validate(base, stage, layout, recipe_path)
            self.assertEqual(result["status"], "failed")
            self.assertTrue(any("Cannot independently validate" in p["error"] for p in result["problems"]))

    def ga027_stage_fixture(self, directory, work_id="ga-027"):
        prior, final, recipe, events = self.fixture()
        prior, final, recipe, events = [
            json.loads(json.dumps(value).replace("ga-test", work_id))
            for value in (prior, final, recipe, events)]
        revision = digest(json.dumps(recipe, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode())
        final["metadata"]["source_layout"]["recipe_sha256"] = revision
        final["passages"][0]["metadata"]["structure_revision"] = revision
        base, stage, layout = [Path(directory) / name for name in ("base", "stage", "layout")]

        def save(path, data):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False))

        for root, payload in ((base, prior), (stage, final), (layout, prior)):
            save(root / "content" / (work_id + ".json"), payload)
        catalog = lambda payload: {"works": [{
            "id": work_id, "content_path": "content/" + work_id + ".json",
            "passages": [{key: p[key] for key in ("id", "title", "checksum", "ga_page")}
                         for p in payload["passages"]]}]}
        save(base / "library/catalog.json", catalog(prior))
        save(stage / "library/catalog.json", catalog(final))
        save(stage / "proofreading/catalog.json", {"generated_at": "test", "works": [{"id": work_id}]})
        save(stage / "proofreading/works" / (work_id + ".json"), {"work": {
            "before_sha256": digest((base / "content" / (work_id + ".json")).read_bytes()),
            "after_sha256": digest((stage / "content" / (work_id + ".json")).read_bytes()),
            "layout_input_sha256": digest((layout / "content" / (work_id + ".json")).read_bytes())},
            "changes": [{**event, "passage_id": pid} for pid, items in events.items() for event in items]})
        ga027_recipe = Path(directory) / (work_id.replace("-", "") + ".json")
        save(ga027_recipe, recipe)
        unrelated_recipe = Path(directory) / "ga040.json"
        save(unrelated_recipe, {"work_id": "ga-040"})
        return base, stage, layout, unrelated_recipe, ga027_recipe

    def test_ga030_selects_its_own_recipe_and_requires_preserved_layout_input(self):
        with tempfile.TemporaryDirectory() as directory:
            base, stage, layout, generic, ga030 = self.ga027_stage_fixture(directory, "ga-030")
            self.assertEqual(validate(base, stage, layout, generic, ga030_recipe=ga030)["status"], "passed")
            result = validate(base, stage, layout, generic, ga030_recipe=generic)
            self.assertTrue(any("No edition-bound recipe" in p["error"] for p in result["problems"]))
            (layout / "content/ga-030.json").unlink()
            result = validate(base, stage, layout, generic, ga030_recipe=ga030)
            self.assertTrue(any("Cannot independently validate source layout" in p["error"]
                                for p in result["problems"]))

    def test_ga030_rejects_retained_source_and_layout_byte_hash_tampering(self):
        for tamper in ("source", "layout_bytes", "source_text"):
            with tempfile.TemporaryDirectory() as directory:
                base, stage, layout, generic, ga030 = self.ga027_stage_fixture(directory, "ga-030")
                if tamper == "source":
                    recipe = json.loads(ga030.read_text())
                    recipe["source_epub_sha256"] = "c" * 64
                    ga030.write_text(json.dumps(recipe))
                elif tamper == "layout_bytes":
                    path = layout / "content/ga-030.json"
                    path.write_text(json.dumps(json.loads(path.read_text()), indent=2))
                else:
                    path = stage / "content/ga-030.json"
                    payload = json.loads(path.read_text())
                    payload["passages"][0]["source_text"] = "Tampered source"
                    path.write_text(json.dumps(payload))
                self.assertEqual(validate(base, stage, layout, generic, ga030_recipe=ga030)["status"], "failed")

    def ga030_recovery_fixture(self, directory):
        original_ids = ["ga-030-doc-heading-3", "ga-030-doc-heading-4", "ga-030-doc-heading-5"]
        prior = {"work_id": "ga-030", "passage_count": 3, "passages": [
            {"id": pid, "title": "Original", "text": "terisiert Ende" if index == 2 else "Original text",
             "source_text": "Immutable source " + pid, "source_label": "Edition", "metadata": {"annotations": []}}
            for index, pid in enumerate(original_ids)]}
        member = "EPUB/chapter-0001.xhtml"
        xml = ('<html xmlns="http://www.w3.org/1999/xhtml"><body>'
               '<p>Intro <span>😀</span><br/>second line</p>'
               '<p>1. Note<br/>prefix</p><p>* exact note</p></body></html>').encode()
        source = Path(directory) / "source.epub"
        with ZipFile(source, "w") as archive:
            archive.writestr(member, xml)
        additions = []
        for kind, index, raw, text in (("passage", 0, "Intro 😀second line", "Intro 😀\nsecond line"),
                                       ("text", 1, "1. Noteprefix", "1. Note\nprefix"),
                                       ("annotation", 2, "* exact note", "* exact note")):
            addition = {"id": "addition-" + kind, "kind": kind,
                        "passage_id": "ga-030-introduction" if kind == "passage" else original_ids[2],
                        "source_segments": [{"source_member": member, "body_indices": [index], "member_sha256": digest(xml)}],
                        "source_text": raw, "text": text, "source_text_sha256": digest(raw.encode()),
                        "text_sha256": digest(text.encode()), "evidence": "Reviewed original page"}
            if kind == "passage":
                addition.update(title="Introduction", source_role="author", insert_before_passage_id=original_ids[0])
            elif kind == "text":
                addition.update(position_codepoint=0, following_anchor="terisiert")
            else:
                addition.update(annotation_id="source#new-note", marker="*")
            additions.append(addition)
        identities = {p["id"]: {"input_sha256": digest(p["text"].encode()),
                                 "source_text_sha256": digest(p["source_text"].encode())} for p in prior["passages"]}
        review = {"source_additions": additions, "original_passages": identities, "known_gaps": [],
                  "review_flags": [], "source_members": {member: digest(xml)}}
        recipe = {**deepcopy(review), "source_epub_sha256": digest(source.read_bytes())}
        recipe["source_evidence"] = {"review_sha256": digest(json.dumps(review, ensure_ascii=False, sort_keys=True,
                                                                       separators=(",", ":")).encode())}
        review_path = Path(directory) / "review.json"
        review_path.write_text(json.dumps(review, ensure_ascii=False))
        events = {}
        for a in additions:
            events.setdefault(a["passage_id"], []).append({"rule": "source_restoration", "count": 1,
                "label": "Exakt belegten Originalquellentext wiederhergestellt", "addition_id": a["id"],
                "source_text_sha256": a["source_text_sha256"], "text_sha256": a["text_sha256"],
                "before_excerpt": "", "after_excerpt": a["text"][:440], "evidence": a["evidence"]})
        return prior, recipe, events, source, review_path

    def test_ga030_exact_epub_restorations_retain_old_sources_and_bind_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            prior, recipe, events, source, review = self.ga030_recovery_fixture(directory)
            untouched = deepcopy(prior)
            result = inspect_ga030_recovery(prior, recipe, events, source, review)
            self.assertEqual(prior, untouched)
            self.assertEqual([p["id"] for p in result["passages"]], ["ga-030-introduction"] + list(recipe["original_passages"]))
            self.assertEqual(result["passage_count"], 4)
            self.assertEqual(result["passages"][0]["source_text"], "Intro 😀second line")
            self.assertEqual(result["passages"][0]["text"], "Intro 😀\nsecond line")
            self.assertEqual(result["passages"][-1]["text"], "1. Note\nprefix\n\nterisiert Ende")
            for old, restored in zip(prior["passages"], result["passages"][1:]):
                self.assertEqual(old["source_text"], restored["source_text"])
            self.assertEqual(result["passages"][-1]["metadata"]["annotations"][0]["source_text"], "* exact note")

    def bind_ga030_fixture(self, recipe, source, review_path, xml=None):
        member = next(iter(recipe["source_members"]))
        if xml is not None:
            with ZipFile(source, "w") as archive:
                archive.writestr(member, xml)
            recipe["source_members"][member] = digest(xml)
            for addition in recipe["source_additions"]:
                for segment in addition["source_segments"]:
                    segment["member_sha256"] = digest(xml)
        review = json.loads(review_path.read_text())
        for key in ("source_members", "source_additions", "original_passages", "original_metadata_repairs", "proofing_repairs"):
            if key in recipe:
                review[key] = deepcopy(recipe[key])
        review_path.write_text(json.dumps(review, ensure_ascii=False))
        recipe["source_epub_sha256"] = digest(source.read_bytes())
        recipe["source_evidence"]["review_sha256"] = digest(json.dumps(review, ensure_ascii=False, sort_keys=True,
                                                                     separators=(",", ":")).encode())
        events = {}
        for a in recipe["source_additions"]:
            events.setdefault(a["passage_id"], []).append({"rule": "source_restoration", "count": 1,
                "label": "Exakt belegten Originalquellentext wiederhergestellt", "addition_id": a["id"],
                "source_text_sha256": a["source_text_sha256"], "text_sha256": a["text_sha256"],
                "before_excerpt": "", "after_excerpt": a["text"][:440], "evidence": a["evidence"]})
        return events

    def test_ga030_restored_annotation_backlink_tail_and_physical_word_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            prior, recipe, _, source, review = self.ga030_recovery_fixture(directory)
            with ZipFile(source) as archive:
                xml = archive.read(next(iter(recipe["source_members"])))
            xml = xml.replace(b"* exact note", '* Auffas-<br/>sung<a role="doc-backlink">↩</a> tail'.encode())
            addition = recipe["source_additions"][2]
            addition.update(source_text="* Auffas-sung↩ tail", text="* Auffassung tail",
                            reading_edits=[{"old": "Auffas-\nsung", "new": "Auffassung", "count": 1, "evidence": "Printed footnote"}])
            addition.update(source_text_sha256=digest(addition["source_text"].encode()), text_sha256=digest(addition["text"].encode()))
            events = self.bind_ga030_fixture(recipe, source, review, xml)
            result = inspect_ga030_recovery(prior, recipe, events, source, review)
            note = result["passages"][-1]["metadata"]["annotations"][0]
            self.assertEqual(note["text"], "* Auffassung tail")
            self.assertEqual(note["source_text"], "* Auffas-sung↩ tail")
            self.assertEqual(note["source_restoration"]["reading_edits"], addition["reading_edits"])
            for field, value in (("count", 2), ("new", "Invented word"), ("old", "Missing-\nword")):
                changed = deepcopy(recipe)
                changed["source_additions"][2]["reading_edits"][0][field] = value
                rebound = self.bind_ga030_fixture(changed, source, review)
                with self.assertRaises(ValueError):
                    inspect_ga030_recovery(prior, changed, rebound, source, review)

    def test_ga030_exact_bracket_year_and_source_page_metadata_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            prior, recipe, _, source, review = self.ga030_recovery_fixture(directory)
            member = next(iter(recipe["source_members"]))
            with ZipFile(source) as archive:
                xml = archive.read(member)
            xml = xml.replace(b"</body>", b"<p>Before [1895] after</p></body>")
            pid = prior["passages"][1]["id"]
            prior["passages"][1]["ga_page"] = "S. 1895"
            prior["passages"][1]["metadata"]["page_numbers"] = [1895]
            recipe["source_additions"].append({"id": "restored-year", "kind": "text", "passage_id": pid,
                "source_segments": [{"source_member": member, "body_indices": [3], "member_sha256": digest(xml)}],
                "source_token": "[1895]", "reading_rendering": "literal_bracket_year_as_digits",
                "source_text": "[1895]", "source_text_sha256": digest(b"[1895]"),
                "text": " 1895", "text_sha256": digest(b" 1895"), "evidence": "Printed prose year",
                "position_codepoint": 0, "following_anchor": "Original text"})
            recipe["original_metadata_repairs"] = [{"passage_id": pid,
                "before": {"ga_page": "S. 1895", "page_numbers": [1895]}, "after": {"ga_page": None, "page_numbers": []},
                "source_token": "[1895]", "source_member": member, "body_index": 3,
                "source_paragraph_sha256": digest(b"Before [1895] after"), "printed_page": 183, "evidence": "Printed prose year"}]
            events = self.bind_ga030_fixture(recipe, source, review, xml)
            result = inspect_ga030_recovery(prior, recipe, events, source, review)
            passage = next(p for p in result["passages"] if p["id"] == pid)
            self.assertEqual(passage["text"], " 1895\n\nOriginal text")
            self.assertIsNone(passage["ga_page"])
            self.assertEqual(passage["metadata"]["page_numbers"], [])
            for value in (184, True, None):
                changed = deepcopy(recipe)
                changed["original_metadata_repairs"][0]["printed_page"] = value
                rebound = self.bind_ga030_fixture(changed, source, review)
                with self.assertRaises(ValueError):
                    inspect_ga030_recovery(prior, changed, rebound, source, review)

    def test_ga030_restored_editorial_exclusion_archive_is_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            prior, recipe, _, source, review = self.ga030_recovery_fixture(directory)
            prior["proofing"] = {"excluded_sections": [{"heading": "HINWEISE DES HERAUSGEBERS"}]}
            recipe["proofing_repairs"] = {"excluded_sections": {"before": deepcopy(prior["proofing"]["excluded_sections"]),
                "after": [], "archive_as": "source_import_excluded_sections", "evidence": "Restored editorial original"}}
            events = self.bind_ga030_fixture(recipe, source, review)
            result = inspect_ga030_recovery(prior, recipe, events, source, review)
            self.assertEqual(result["proofing"], {"excluded_sections": [], "source_import_excluded_sections": prior["proofing"]["excluded_sections"]})
            for field, value in (("after", ["Unreviewed"]), ("before", []), ("archive_as", "other")):
                changed = deepcopy(recipe)
                changed["proofing_repairs"]["excluded_sections"][field] = value
                rebound = self.bind_ga030_fixture(changed, source, review)
                with self.assertRaises(ValueError):
                    inspect_ga030_recovery(prior, changed, rebound, source, review)

    def test_ga030_literal_word_boundaries_bind_overlapping_reviewed_words(self):
        prior, final, recipe, events = [json.loads(json.dumps(value).replace("ga-test", "ga-030"))
                                       for value in self.fixture()]
        pid = "ga-030-1"
        old, new = prior["passages"][0], final["passages"][0]
        old["text"] = old["text"].replace("A-\nbc", "theoso-\nphisch theoso-\nphischen")
        new["text"] = new["text"].replace("Abc", "theosophisch theosophischen")
        old["checksum"], new["checksum"] = digest(old["text"].encode()), digest(new["text"].encode())
        plan = recipe["passages"][pid]
        plan.update(input_sha256=old["checksum"], output_sha256=new["checksum"], edits=[
            {"old": "theoso- phisch", "new": "theosophisch", "match_word_boundaries": True, "evidence": "Exact first source word"},
            {"old": "theoso- phischen", "new": "theosophischen", "match_word_boundaries": True, "evidence": "Exact second source word"}])
        delta = utf16_length("theosophisch theosophischen") - 3
        meta = new["metadata"]
        meta["reading_blocks"][0]["end_offset"] += delta
        for block in meta["reading_blocks"][1:]:
            block["start_offset"] += delta
            block["end_offset"] += delta
        for anchor in meta["page_anchors"]:
            anchor["start_offset"] += delta
        meta["annotations"][0]["start_offset"] += delta
        meta["annotations"][0]["end_offset"] += delta
        for entry in final["table_of_contents"]:
            if entry["start_offset"]:
                entry["start_offset"] += delta
        revision = digest(json.dumps(recipe, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
        meta["structure_revision"] = final["metadata"]["source_layout"]["recipe_sha256"] = revision
        replacements = events[pid][0]["replacements"]
        replacements[-1:] = [{"original": e["old"], "word": e["new"], "count": 1, "evidence": e["evidence"]} for e in plan["edits"]]
        self.assertEqual(inspect_source_layout(prior, final, recipe, events), ([], 3))
        for flag in (False, "true", 1):
            changed = deepcopy(recipe)
            for edit in changed["passages"][pid]["edits"]:
                edit["match_word_boundaries"] = flag
            self.assertTrue(inspect_source_layout(prior, final, changed, events)[0])

    def test_ga030_restoration_source_inventory_and_ledger_tampering_fail(self):
        for mutate in (lambda p, r, e, s: p["passages"].reverse(),
                       lambda p, r, e, s: p["passages"][1].update(source_text="Changed original source"),
                       lambda p, r, e, s: r["source_evidence"].update(review_sha256="0" * 64),
                       lambda p, r, e, s: r["source_additions"][0].update(source_text="Invented introduction"),
                       lambda p, r, e, s: e["ga-030-introduction"][0].update(count=2),
                       lambda p, r, e, s: e["ga-030-introduction"].append(deepcopy(e["ga-030-introduction"][0])),
                       lambda p, r, e, s: s.write_bytes(s.read_bytes() + b"byte drift")):
            with tempfile.TemporaryDirectory() as directory:
                prior, recipe, events, source, review = self.ga030_recovery_fixture(directory)
                mutate(prior, recipe, events, source)
                with self.assertRaises(ValueError):
                    inspect_ga030_recovery(prior, recipe, events, source, review)

    def test_ga030_restoration_rejects_edited_witnesses_and_invalid_insertions_even_when_review_rebound(self):
        for mutate in (lambda r: r["source_additions"][0].update(source_text="Invented introduction"),
                       lambda r: r["source_additions"][1].update(source_segments=deepcopy(r["source_additions"][0]["source_segments"])),
                       lambda r: r["source_additions"][1].update(position_codepoint=999),
                       lambda r: r["source_additions"][1].update(following_anchor="Wrong seam")):
            with tempfile.TemporaryDirectory() as directory:
                prior, recipe, events, source, review_path = self.ga030_recovery_fixture(directory)
                mutate(recipe)
                review = json.loads(review_path.read_text())
                review["source_additions"] = deepcopy(recipe["source_additions"])
                review_path.write_text(json.dumps(review, ensure_ascii=False))
                recipe["source_evidence"]["review_sha256"] = digest(json.dumps(review, ensure_ascii=False, sort_keys=True,
                                                                             separators=(",", ":")).encode())
                with self.assertRaises(ValueError):
                    inspect_ga030_recovery(prior, recipe, events, source, review_path)

    def test_explicit_note_lines_are_preserved_without_relaxing_prose_or_verse(self):
        prior, final, recipe, events = self.fixture()
        pid = "ga-test-1"
        for payload in (prior, final):
            passage = payload["passages"][0]
            passage["text"] = passage["text"].replace("Verse 😀", "Verse\n😀")
            passage["checksum"] = digest(passage["text"].encode())
        plan = recipe["passages"][pid]
        plan.update(input_sha256=digest(prior["passages"][0]["text"].encode()),
                    output_sha256=digest(final["passages"][0]["text"].encode()))
        plan["segments"][2].update(kind="note", preserve_lines=True)
        plan["annotations"]["n"]["reference_context"] = "Verse\n😀 *"
        final["passages"][0]["metadata"]["reading_blocks"][2]["kind"] = "note"
        revision = digest(json.dumps(recipe, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
        final["metadata"]["source_layout"]["recipe_sha256"] = revision
        final["passages"][0]["metadata"]["structure_revision"] = revision
        self.assertEqual(inspect_source_layout(prior, final, recipe, events), ([], 2))
        for kind, flag in (("prose", True), ("verse", True), ("note", "true"), ("note", False)):
            edited = deepcopy(recipe)
            edited["passages"][pid]["segments"][2].update(kind=kind, preserve_lines=flag)
            self.assertTrue(inspect_source_layout(prior, final, edited, events)[0])

    def test_ga032_monochrome_original_raster_parser_and_crop(self):
        width, height, pixels = pbm_raster(b"P4\n# embedded original scan\n9 2\n\x80\x80\x00\x00")
        self.assertEqual((width, height, pixels), (9, 2, b"\x7f\x00\xff\x80"))
        self.assertEqual(crop_mono_raster(width, height, pixels, [1, 0, 9, 2]), b"\xfe\xff")
        # The first binary byte can itself be whitespace; never skip it as a header.
        self.assertEqual(pbm_raster(b"P4\n8 1\n\x20"), (8, 1, b"\xdf"))
        for data in (b"P1\n8 1\n\x20", b"P4\n8 1\n", b"P4\n0 1\n", b"P4\n# unterminated"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                pbm_raster(data)
        for box in ([0, 0, 10, 1], [True, 0, 8, 1], [2, 0, 1, 1], [0, 0, 1]):
            with self.subTest(box=box), self.assertRaises(ValueError):
                crop_mono_raster(width, height, pixels, box)

    @unittest.skipUnless(GA032_PDF.exists() and shutil.which("pdfimages"), "Original GA032 raster source unavailable")
    def test_ga032_pdf_only_fragment_exact_pixels_and_tamper(self):
        checksum = "1155b523ddfece69a51a2c75a29f752a2c48742fad1eae03509835e8f6ac6bd7"
        witness = {"pdf_page": 451, "page_index": 450, "xobject_name": "/Im0", "width": 2483, "height": 3302,
            "decoded_stream_sha256": "669fe1686b81eafdb1bacd2685ce9b19bcc784b34d168f95ae7460f66683b2b6",
            "crop_box_pixels": [290, 2070, 2400, 2270], "crop_mode": "1",
            "crop_pixels_sha256": "b08d2ad799c4469d72dc082eac92a671bdaa1610ded9c734963c28e095234e2b",
            "visually_verified_text": ["Rolf Wolfgang Martens «Befreite Flügel» (Berlin 1899) ent-", "halten:"],
            "extracted_text_layer_omits_fragment": True, "source_token": "halten:"}
        repair = {"old": "(Berlin 1899) ent-", "new": "(Berlin 1899) enthalten:", "source_token": "halten:",
                  "source_pdf_page": 451, "original_pdf_sha256": checksum, "pdf_raster_witness": witness}
        review = {"original_pdf_sha256": checksum}
        inspect_ga032_pdf_fragment(repair, review)
        for mutate in (lambda r: r.update(new="(Berlin 1899) entfalten:"),
                       lambda r: r.update(source_pdf_page=450),
                       lambda r: r.update(original_pdf_sha256="0" * 64),
                       lambda r: r["pdf_raster_witness"].update(crop_box_pixels=[0, 0, 10, 10]),
                       lambda r: r["pdf_raster_witness"].update(crop_pixels_sha256="0" * 64),
                       lambda r: r["pdf_raster_witness"].update(visually_verified_text=["invented", "halten:"])):
            changed = deepcopy(repair)
            mutate(changed)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                inspect_ga032_pdf_fragment(changed, review)
        def changed_raster(command, **kwargs):
            # Same PDF identity and dimensions, but a different actual extracted raster.
            Path(command[-1] + "-000.pbm").write_bytes(b"P4\n2483 3302\n" + b"\x00" * (311 * 3302))
        with patch("check_proofreading_samples.subprocess.run", changed_raster), self.assertRaises(ValueError):
            inspect_ga032_pdf_fragment(repair, review)
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory) / "changed.pdf"
            altered.write_bytes(GA032_PDF.read_bytes() + b"\n")
            with self.assertRaises(ValueError):
                inspect_ga032_pdf_fragment(repair, review, altered)

    def test_ga032_source_word_seams_preserve_spelling_and_compound_dash(self):
        for old, new in (("Farben- harmonie", "Farbenharmonie"),
                         ("romanti- sehen", "romantisehen"),
                         ("Weltanschauungs- Robinsonaden", "Weltanschauungs-Robinsonaden")):
            repair = {"kind": "physical_word_seam", "old": old, "new": new, "match_word_boundaries": True}
            parts = old.split(" ", 1)
            inspect_ga032_word_repair(repair, parts)
            for changed in (dict(repair, new="corrected wording"), dict(repair, match_word_boundaries=False)):
                with self.assertRaises(ValueError):
                    inspect_ga032_word_repair(changed, parts)
            for bad_parts in ([old], ["another", "source"]):
                with self.assertRaises(ValueError):
                    inspect_ga032_word_repair(repair, bad_parts)

    def test_ga032_all_five_original_poetic_overruns_are_exact(self):
        pairs = [
            ("Puls-\nDes Seins: die Krankheit und das Laster, [schlag", "Pulsschlag\nDes Seins: die Krankheit und das Laster,"),
            ("jegliches\nDas uns zürn Hohn sie geschaffen, [Blendwerk,", "jegliches Blendwerk,\nDas uns zürn Hohn sie geschaffen,"),
            ("hinter vergletscherten\nhinter Wüsten aus Nacht und Nichts [Ursonnen,", "hinter vergletscherten Ursonnen,\nhinter Wüsten aus Nacht und Nichts"),
            ("sich immer wieder\nMaikaterbart!» [sträubenden", "sich immer wieder sträubenden\nMaikaterbart!»"),
            ("schimmerndes\nEntrüstet\n[Wiesenblümchen", "schimmerndes Wiesenblümchen\nEntrüstet"),
        ]
        for old, new in pairs:
            repair = {"kind": "poetic_overrun", "old": old, "new": new}
            parts = old.split("\n", 1)
            with self.subTest(old=old):
                inspect_ga032_word_repair(repair, parts)
                # Explicit source line positions may put the bracketed overflow on its own row.
                wrapped = dict(repair, old=old.replace(" [", " \n["))
                inspect_ga032_word_repair(wrapped, parts)
                for changed in (dict(repair, new=new.replace("\n", " ")),
                                dict(repair, new=new + "zusätzlich"), dict(repair, new=old)):
                    with self.assertRaises(ValueError):
                        inspect_ga032_word_repair(changed, parts)
                with self.assertRaises(ValueError):
                    inspect_ga032_word_repair(repair, ["unrelated", "source"])

    def ga032_fixture(self, directory):
        prior, final, recipe, events = [json.loads(json.dumps(value).replace("ga-test", "ga-032"))
                                       for value in self.fixture()]
        pid, member = "ga-032-1", "EPUB/chapter-0001.xhtml"
        old, new = prior["passages"][0], final["passages"][0]
        raw = old["text"].split("\n\n")
        xml = ('<html xmlns="http://www.w3.org/1999/xhtml"><body>' +
               ''.join('<p>' + text + '</p>' for text in raw) + '</body></html>').encode()
        source = Path(directory) / "ga032.epub"
        with ZipFile(source, "w") as archive:
            archive.writestr(member, xml)
        checksum = digest(source.read_bytes())
        prior["source_epub_sha256"] = final["source_epub_sha256"] = recipe["source_epub_sha256"] = checksum
        proofing = {"source_members": [{"member": member, "sha256": digest(xml)}]}
        prior["proofing"] = deepcopy(proofing)
        final["proofing"] = deepcopy(proofing)
        old["source_text"] = new["source_text"] = old["text"]
        new["metadata"]["annotations"] = deepcopy(old["metadata"]["annotations"])
        source_parts = [{"source_member": member, "body_index": i, "child_path": [],
                         "source_paragraph_sha256": digest(text.encode())} for i, text in enumerate(raw)]
        recipe["passages"][pid]["edits"][0].update(kind="physical_word_seam", match_word_boundaries=True,
            source_witnesses=deepcopy(source_parts[:2]), **source_parts[0])
        starts, offset = [], 0
        for i, text in enumerate(raw[:3]):
            start = source_parts[i] | {"start_codepoint": offset, "canonical_anchor": text,
                "kind": ("prose", "heading", "verse")[i], "evidence": "Original source paragraph"}
            if i == 1:
                start["level"] = 1
            if i == 2:
                start["page_anchor"] = 12
            starts.append(start)
            offset += len(text) + 2
        omitted = source_parts[3] | {"start_codepoint": len(old["text"]) - len(raw[3]),
            "end_codepoint": len(old["text"]), "kind": "page_footer", "page": 12,
            "text_sha256": digest(raw[3].encode()), "evidence": "Page footer"}
        plan = recipe["passages"][pid]
        plan.pop("annotations")
        plan["source_text_sha256"] = digest(old["source_text"].encode())
        note_digest = digest(json.dumps(old["metadata"]["annotations"], ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode())
        plan.update(annotations_input_sha256=note_digest, annotations_output_sha256=note_digest)
        for i, segment in enumerate(plan["segments"]):
            segment.update(parts=[{"block": i, "start": 0, "end": len(raw[i])}],
                           evidence=starts[i]["evidence"], source_pdf_pages=[])
        plan["omitted_parts"] = [{"block": 3, "start": 0, "end": len(raw[3])} |
                                {k: v for k, v in omitted.items() if k not in {"start_codepoint", "end_codepoint"}}]
        plan["output_metadata"] = {"title": new["title"], "ga_page": new["ga_page"], "page_numbers": [12]}
        review = {"work_id": "ga-032", "source_sha256": prior["source_sha256"], "source_epub_sha256": checksum,
            "source_members": {member: digest(xml)}, "method": "Exact source fixture", "known_gaps": [],
            "review_flags": [], "metadata_repairs": [], "passages": {pid: {
                "input_sha256": plan["input_sha256"], "source_text_sha256": plan["source_text_sha256"],
                "title": old["title"], "group_title": "Group", "source_parts": source_parts,
                "starts": starts, "omissions": [omitted], "edits": deepcopy(plan["edits"])}}}
        recipe.update(known_gaps=[], review_flags=[], metadata_repairs=[])
        path = Path(directory) / "ga032-review.json"
        self.bind_ga032_fixture(recipe, final, review, path)
        return prior, final, recipe, events, source, path

    def bind_ga032_fixture(self, recipe, final, review, path):
        path.write_text(json.dumps(review, ensure_ascii=False))
        recipe["source_evidence"] = {"review_sha256": digest(json.dumps(review, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode()), "method": review["method"], "source_members": deepcopy(review["source_members"])}
        revision = digest(json.dumps(recipe, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
        final["metadata"]["source_layout"]["recipe_sha256"] = revision
        final["metadata"]["source_layout"].update(source_epub_sha256=recipe["source_epub_sha256"],
            review_sha256=recipe["source_evidence"]["review_sha256"], source_evidence=deepcopy(recipe["source_evidence"]))
        for p in final["passages"]:
            p["metadata"]["structure_revision"] = revision

    def test_ga032_complete_source_projection_preserves_annotations(self):
        with tempfile.TemporaryDirectory() as directory:
            prior, final, recipe, events, source, review = self.ga032_fixture(directory)
            untouched = deepcopy(prior)
            self.assertEqual(inspect_ga032_layout(prior, final, recipe, events, source, review), ([], 2))
            self.assertEqual(prior, untouched)
            self.assertEqual(final["passages"][0]["metadata"]["annotations"], prior["passages"][0]["metadata"]["annotations"])
            frozen = json.loads(review.read_text())
            for kind in (None, "unreviewed_replacement"):
                changed_review, changed_recipe = deepcopy(frozen), deepcopy(recipe)
                edit = changed_review["passages"]["ga-032-1"]["edits"][0]
                if kind is None:
                    edit.pop("kind")
                else:
                    edit["kind"] = kind
                changed_recipe["passages"]["ga-032-1"]["edits"] = deepcopy(changed_review["passages"]["ga-032-1"]["edits"])
                self.bind_ga032_fixture(changed_recipe, final, changed_review, review)
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    inspect_ga032_layout(prior, final, changed_recipe, events, source, review)
            self.bind_ga032_fixture(recipe, final, frozen, review)
            for mutate in (lambda f: f["passages"][0].update(source_text="Changed source"),
                           lambda f: f["passages"][0]["metadata"]["annotations"][0].update(text="Changed note"),
                           lambda f: f["passages"][0]["metadata"]["reading_blocks"][0].update(end_offset=2),
                           lambda f: f["passages"][0].update(title="Changed heading"),
                           lambda f: f["metadata"]["source_layout"].update(review_sha256="0" * 64)):
                changed = deepcopy(final)
                mutate(changed)
                self.assertTrue(inspect_ga032_layout(prior, changed, recipe, events, source, review)[0])

    def test_ga032_source_recipe_and_rebound_review_tampering_fail(self):
        for mutation in ("source_bytes", "member_hash", "duplicate_part", "missing_part", "nested_path", "source_hash", "segment", "anchor", "omission", "edit"):
            with tempfile.TemporaryDirectory() as directory:
                prior, final, recipe, events, source, path = self.ga032_fixture(directory)
                review = json.loads(path.read_text())
                witness, plan = review["passages"]["ga-032-1"], recipe["passages"]["ga-032-1"]
                if mutation == "source_bytes":
                    source.write_bytes(source.read_bytes() + b"drift")
                elif mutation == "member_hash":
                    review["source_members"][next(iter(review["source_members"]))] = "0" * 64
                elif mutation == "duplicate_part":
                    witness["source_parts"].append(deepcopy(witness["source_parts"][0]))
                elif mutation == "missing_part":
                    witness["source_parts"].pop()
                elif mutation == "nested_path":
                    witness["source_parts"][0]["child_path"] = [0]
                elif mutation == "source_hash":
                    witness["source_parts"][0]["source_paragraph_sha256"] = "0" * 64
                elif mutation == "segment":
                    plan["segments"][0]["parts"][0]["end"] -= 1
                elif mutation == "anchor":
                    witness["starts"][0]["canonical_anchor"] = "Wrong anchor"
                elif mutation == "omission":
                    plan["omitted_parts"][0]["body_index"] = 2
                else:
                    plan["edits"][0]["new"] = "Invented word"
                self.bind_ga032_fixture(recipe, final, review, path)
                with self.assertRaises(ValueError):
                    inspect_ga032_layout(prior, final, recipe, events, source, path)

    def test_ga032_source_metadata_repair_and_ledger_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            prior, final, recipe, events, source, path = self.ga032_fixture(directory)
            review = json.loads(path.read_text())
            repair = deepcopy(review["passages"]["ga-032-1"]["source_parts"][1]) | {
                "passage_id": "ga-032-1", "before": {"title": "Reader"}, "after": {"title": "TITLE"}, "evidence": "Original heading"}
            review["metadata_repairs"] = [repair]
            recipe["metadata_repairs"] = deepcopy(review["metadata_repairs"])
            final["passages"][0]["title"] = "TITLE"
            final["table_of_contents"][1]["title"] = "TITLE"
            recipe["passages"]["ga-032-1"]["output_metadata"]["title"] = "TITLE"
            events["ga-032-1"][0]["metadata_replacements"] = [repair]
            self.bind_ga032_fixture(recipe, final, review, path)
            self.assertEqual(inspect_ga032_layout(prior, final, recipe, events, source, path), ([], 2))
            changed = deepcopy(events)
            changed["ga-032-1"][0]["metadata_replacements"][0]["after"]["title"] = "Invented"
            self.assertTrue(inspect_ga032_layout(prior, final, recipe, changed, source, path)[0])
            frozen = deepcopy(review)
            for after in ({"title": "Invented"}, {"ga_page": "S. 1899"},
                          {"ga_page": None, "page_numbers": []}):
                invalid = deepcopy(frozen)
                bad = invalid["metadata_repairs"][0]
                bad["after"] = after
                bad["before"] = {field: prior["passages"][0]["metadata"][field]
                                  if field == "page_numbers" else prior["passages"][0][field] for field in after}
                changed_recipe = deepcopy(recipe)
                changed_recipe["metadata_repairs"] = invalid["metadata_repairs"]
                self.bind_ga032_fixture(changed_recipe, final, invalid, path)
                with self.subTest(after=after), self.assertRaises(ValueError):
                    inspect_ga032_layout(prior, final, changed_recipe, events, source, path)
            self.bind_ga032_fixture(recipe, final, frozen, path)
            review["metadata_repairs"][0]["before"]["title"] = "Wrong prior value"
            recipe["metadata_repairs"] = deepcopy(review["metadata_repairs"])
            self.bind_ga032_fixture(recipe, final, review, path)
            with self.assertRaises(ValueError):
                inspect_ga032_layout(prior, final, recipe, events, source, path)

    def test_ga032_full_validator_selects_review_and_separate_layout_byte_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            prior, final, recipe, events, source, review = self.ga032_fixture(directory)
            base, stage, layout = [Path(directory) / name for name in ("base", "stage", "layout")]
            def save(path, value, **kwargs):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value, ensure_ascii=False, **kwargs))
            for root, payload in ((base, prior), (stage, final)):
                save(root / "content/ga-032.json", payload)
                save(root / "library/catalog.json", {"works": [{"id": "ga-032", "content_path": "content/ga-032.json",
                    "passages": [{k: p[k] for k in ("id", "title", "checksum", "ga_page")} for p in payload["passages"]]}]})
            save(layout / "content/ga-032.json", prior, indent=2)
            save(stage / "proofreading/catalog.json", {"generated_at": "test", "works": [{"id": "ga-032"}]})
            report = {"work": {"before_sha256": digest((base / "content/ga-032.json").read_bytes()),
                "application_base_sha256": digest((base / "content/ga-032.json").read_bytes()),
                "layout_input_sha256": digest((layout / "content/ga-032.json").read_bytes()),
                "after_sha256": digest((stage / "content/ga-032.json").read_bytes())},
                "changes": [dict(e, passage_id=pid) for pid, items in events.items() for e in items]}
            report_path = stage / "proofreading/works/ga-032.json"
            save(report_path, report)
            recipe_path = Path(directory) / "ga032.json"
            save(recipe_path, recipe)
            args = {"ga032_recipe": recipe_path, "ga032_source": source, "ga032_review": review}
            result = validate(base, stage, layout, **args)
            self.assertEqual(result["status"], "passed", result["problems"])
            self.assertNotEqual(report["work"]["layout_input_sha256"], report["work"]["application_base_sha256"])
            foreign = Path(directory) / "foreign.json"
            save(foreign, {"work_id": "ga-040"})
            result = validate(base, stage, layout, **dict(args, ga032_recipe=foreign))
            self.assertTrue(any("No edition-bound recipe" in p["error"] for p in result["problems"]))
            for checksum in (None, report["work"]["application_base_sha256"]):
                if checksum is None:
                    report["work"].pop("layout_input_sha256")
                else:
                    report["work"]["layout_input_sha256"] = checksum
                save(report_path, report)
                result = validate(base, stage, layout, **args)
                self.assertTrue(any("Layout input hash" in p["error"] for p in result["problems"]))

    def test_ga032_reviewed_true_line_boundaries_and_invalid_line_slices(self):
        with tempfile.TemporaryDirectory() as directory:
            prior, final, recipe, events, source, path = self.ga032_fixture(directory)
            review = json.loads(path.read_text())
            witness = review["passages"]["ga-032-1"]
            start = witness["starts"][2]
            start["line_starts"] = [start["start_codepoint"] + 6]
            plan = recipe["passages"]["ga-032-1"]
            plan["segments"][2]["parts"] = [{"block": 2, "start": 0, "end": 6}, {"block": 2, "start": 6, "end": 9}]
            final["passages"][0]["text"] = final["passages"][0]["text"].replace("Verse ", "Verse\n")
            final["passages"][0]["checksum"] = plan["output_sha256"] = digest(final["passages"][0]["text"].encode())
            self.bind_ga032_fixture(recipe, final, review, path)
            self.assertEqual(inspect_ga032_layout(prior, final, recipe, events, source, path), ([], 2))
            for points in ([True], [start["start_codepoint"]], [999], start["line_starts"] * 2):
                changed = deepcopy(review)
                changed["passages"]["ga-032-1"]["starts"][2]["line_starts"] = points
                self.bind_ga032_fixture(recipe, final, changed, path)
                with self.assertRaises(ValueError):
                    inspect_ga032_layout(prior, final, recipe, events, source, path)

    def test_ga032_annotation_whitespace_exception_is_source_bound_and_preserves_backlink(self):
        with tempfile.TemporaryDirectory() as directory:
            prior, final, recipe, events, source, path = self.ga032_fixture(directory)
            review = json.loads(path.read_text())
            member = next(iter(review["source_members"]))
            with ZipFile(source) as archive:
                xml = archive.read(member)
            before = "* alpha\nbeta ↩"
            xml = xml.replace(b"</body>", ('<p role="doc-footnote" id="fn-1">' + before + '</p></body>').encode())
            with ZipFile(source, "w") as archive:
                archive.writestr(member, xml)
            source_sha = digest(source.read_bytes())
            prior["source_epub_sha256"] = final["source_epub_sha256"] = recipe["source_epub_sha256"] = review["source_epub_sha256"] = source_sha
            review["source_members"][member] = digest(xml)
            for payload in (prior, final):
                payload["proofing"]["source_members"][0]["sha256"] = digest(xml)
            aid = member + "#fn-1"
            note = {"id": aid, "marker": "*", "text": before, "custom": "unchanged"}
            prior["passages"][0]["metadata"]["annotations"] = [deepcopy(note)]
            final["passages"][0]["metadata"]["annotations"] = [dict(note, text="* alpha beta ↩")]
            repair = {"passage_id": "ga-032-1", "annotation_id": aid, "marker": "*", "before": before,
                "after": "* alpha beta ↩", "source_member": member, "body_index": 4,
                "source_paragraph_sha256": digest(before.encode()), "evidence": "Original prose note lines"}
            recipe["annotation_repairs"] = review["annotation_repairs"] = [repair]
            events["ga-032-1"][0]["annotation_replacements"] = [deepcopy(repair)]
            plan = recipe["passages"]["ga-032-1"]
            for key, notes in (("input", [note]), ("output", [dict(note, text="* alpha beta ↩")])):
                plan["annotations_" + key + "_sha256"] = digest(json.dumps(notes, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
            self.bind_ga032_fixture(recipe, final, review, path)
            self.assertEqual(inspect_ga032_layout(prior, final, recipe, events, source, path), ([], 2))
            for field, value in (("after", "* alpha BETA ↩"), ("after", "* alpha beta"), ("marker", "**"), ("body_index", 3)):
                changed_review, changed_recipe = deepcopy(review), deepcopy(recipe)
                changed_review["annotation_repairs"][0][field] = value
                changed_recipe["annotation_repairs"] = deepcopy(changed_review["annotation_repairs"])
                self.bind_ga032_fixture(changed_recipe, final, changed_review, path)
                with self.assertRaises(ValueError):
                    inspect_ga032_layout(prior, final, changed_recipe, events, source, path)
            self.bind_ga032_fixture(recipe, final, review, path)
            changed = deepcopy(events)
            changed["ga-032-1"][0]["annotation_replacements"] = []
            self.assertTrue(inspect_ga032_layout(prior, final, recipe, changed, source, path)[0])

    def test_ga032_literal_year_restoration_preserves_all_other_wording(self):
        with tempfile.TemporaryDirectory() as directory:
            prior, final, recipe, events, source, path = self.ga032_fixture(directory)
            review = json.loads(path.read_text())
            member = next(iter(review["source_members"]))
            with ZipFile(source) as archive:
                xml = archive.read(member)
            xml = xml.replace(b"A-\nbc", b"Before [1895] after")
            with ZipFile(source, "w") as archive:
                archive.writestr(member, xml)
            source_sha = digest(source.read_bytes())
            prior["source_epub_sha256"] = final["source_epub_sha256"] = recipe["source_epub_sha256"] = review["source_epub_sha256"] = source_sha
            review["source_members"][member] = digest(xml)
            for payload in (prior, final):
                payload["proofing"]["source_members"][0]["sha256"] = digest(xml)
                payload["passages"][0]["source_text"] = payload["passages"][0]["source_text"].replace("A-\nbc", "Before [1895] after")
            old, new = prior["passages"][0], final["passages"][0]
            old["text"] = old["text"].replace("A-\nbc", "Before after")
            new["text"] = new["text"].replace("Abc", "Before 1895 after")
            old["checksum"], new["checksum"] = digest(old["text"].encode()), digest(new["text"].encode())
            plan, witness = recipe["passages"]["ga-032-1"], review["passages"]["ga-032-1"]
            for obj in (plan, witness):
                obj["input_sha256"] = old["checksum"]
                obj["source_text_sha256"] = digest(old["source_text"].encode())
            witness["source_parts"][0]["source_paragraph_sha256"] = digest(b"Before [1895] after")
            witness["starts"][0].update(source_paragraph_sha256=digest(b"Before [1895] after"), canonical_anchor="Before after")
            for start in witness["starts"][1:]:
                start["start_codepoint"] += 7
            for field in ("start_codepoint", "end_codepoint"):
                witness["omissions"][0][field] += 7
            plan["segments"][0]["parts"][0]["end"] = 12
            repair = {"old": "Before after", "new": "Before 1895 after", "kind": "literal_year_restoration",
                "source_token": "[1895]", "source_member": member, "body_index": 0,
                "source_paragraph_sha256": digest(b"Before [1895] after"), "evidence": "Original prose year"}
            plan["edits"] = witness["edits"] = [repair]
            plan["output_sha256"] = new["checksum"]
            delta = len("Before 1895 after") - 3
            new["metadata"]["reading_blocks"][0]["end_offset"] += delta
            for block in new["metadata"]["reading_blocks"][1:]:
                block["start_offset"] += delta
                block["end_offset"] += delta
            new["metadata"]["page_anchors"][0]["start_offset"] += delta
            for row in final["table_of_contents"]:
                if row["start_offset"]:
                    row["start_offset"] += delta
            events["ga-032-1"][0]["replacements"][-1] = {"original": repair["old"], "word": repair["new"], "count": 1, "evidence": repair["evidence"]}
            self.bind_ga032_fixture(recipe, final, review, path)
            self.assertEqual(inspect_ga032_layout(prior, final, recipe, events, source, path), ([], 2))
            for field, value in (("new", "Before 1895 invented after"), ("new", "Before after 1895"),
                                 ("source_token", "[1896]"), ("body_index", 1)):
                changed_review, changed_recipe = deepcopy(review), deepcopy(recipe)
                changed_review["passages"]["ga-032-1"]["edits"][0][field] = value
                changed_recipe["passages"]["ga-032-1"]["edits"] = deepcopy(changed_review["passages"]["ga-032-1"]["edits"])
                self.bind_ga032_fixture(changed_recipe, final, changed_review, path)
                with self.assertRaises(ValueError):
                    inspect_ga032_layout(prior, final, changed_recipe, events, source, path)

    def test_ga032_original_contents_and_article_sections_cannot_be_rebound(self):
        with tempfile.TemporaryDirectory() as directory:
            prior, final, recipe, events, source, path = self.ga032_fixture(directory)
            review = json.loads(path.read_text())
            starts = review["passages"]["ga-032-1"]["starts"]
            starts[0].update(section_start=True, toc_target="reader")
            starts[1].update(section_start=True, toc_target="title")
            plan = recipe["passages"]["ga-032-1"]
            plan["sections"] = [
                {"start_segment": 0, "end_segment": 1, "title": "Reader", "label_kind": "source_title", "evidence": starts[0]["evidence"]},
                {"start_segment": 1, "end_segment": 3, "title": "TITLE", "label_kind": "source_title", "evidence": starts[1]["evidence"]}]
            final["passages"][0]["metadata"]["reading_sections"] = [
                {"id": "ga-032-1", "title": "Reader", "label_kind": "source_title", "start_offset": 0, "end_offset": 3},
                {"id": "ga-032-1-section-2", "title": "TITLE", "label_kind": "source_title", "start_offset": 5, "end_offset": 22}]
            review["table_of_contents"] = [
                {"id": "toc-reader", "title": "Reader", "level": 1, "parent_id": None, "target": "reader"},
                {"id": "toc-title", "title": "TITLE", "level": 1, "parent_id": None, "target": "title"}]
            recipe["table_of_contents"] = [{k: v for k, v in row.items() if k != "target"} |
                {"passage_id": "ga-032-1", "start_offset": offset}
                for row, offset in zip(review["table_of_contents"], (0, 5))]
            final["table_of_contents"] = deepcopy(recipe["table_of_contents"])
            self.bind_ga032_fixture(recipe, final, review, path)
            self.assertEqual(inspect_ga032_layout(prior, final, recipe, events, source, path), ([], 2))
            for mutation in ("contents", "sections", "group"):
                changed, changed_final = deepcopy(recipe), deepcopy(final)
                if mutation == "contents":
                    changed["table_of_contents"][0]["title"] = "Invented"
                    changed_final["table_of_contents"] = deepcopy(changed["table_of_contents"])
                elif mutation == "sections":
                    changed["passages"]["ga-032-1"]["sections"][0]["end_segment"] = 2
                else:
                    changed["passages"]["ga-032-1"]["group_title"] = "Invented group"
                self.bind_ga032_fixture(changed, changed_final, review, path)
                with self.assertRaises(ValueError):
                    inspect_ga032_layout(prior, changed_final, changed, events, source, path)

    def test_ga027_selects_its_own_recipe_and_requires_preserved_layout_input(self):
        with tempfile.TemporaryDirectory() as directory:
            base, stage, layout, generic, ga027 = self.ga027_stage_fixture(directory)
            result = validate(base, stage, layout, generic, ga027_recipe=ga027)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["summary"]["source_layout_passages"], 1)
            # The generic GA040 recipe cannot stand in for the retained GA027 edition.
            result = validate(base, stage, layout, generic, ga027_recipe=generic)
            self.assertTrue(any("No edition-bound recipe" in p["error"] for p in result["problems"]))
            (layout / "content/ga-027.json").unlink()
            result = validate(base, stage, layout, generic, ga027_recipe=ga027)
            self.assertTrue(any("Cannot independently validate source layout" in p["error"]
                                for p in result["problems"]))

    def test_ga027_rejects_recipe_source_identity_and_report_input_hash_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            base, stage, layout, generic, ga027 = self.ga027_stage_fixture(directory)
            recipe = json.loads(ga027.read_text())
            recipe["source_epub_sha256"] = "c" * 64
            ga027.write_text(json.dumps(recipe))
            result = validate(base, stage, layout, generic, ga027_recipe=ga027)
            self.assertTrue(any("retained source identity" in p["error"] for p in result["problems"]))
        with tempfile.TemporaryDirectory() as directory:
            base, stage, layout, generic, ga027 = self.ga027_stage_fixture(directory)
            path = stage / "proofreading/works/ga-027.json"
            report = json.loads(path.read_text())
            report["work"]["layout_input_sha256"] = "c" * 64
            path.write_text(json.dumps(report))
            result = validate(base, stage, layout, generic, ga027_recipe=ga027)
            self.assertTrue(any("Layout input hash" in p["error"] for p in result["problems"]))

    def test_ga027_layout_hash_binds_preserved_bytes_separately_from_application_input(self):
        with tempfile.TemporaryDirectory() as directory:
            base, stage, layout, generic, ga027 = self.ga027_stage_fixture(directory)
            preserved = layout / "content/ga-027.json"
            application_hash = digest(preserved.read_bytes())
            payload = json.loads(preserved.read_text())
            preserved.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
            preserved_hash = digest(preserved.read_bytes())
            self.assertNotEqual(application_hash, preserved_hash)
            self.assertEqual(json.loads(preserved.read_text()), payload)
            path = stage / "proofreading/works/ga-027.json"
            report = json.loads(path.read_text())
            report["work"].update(application_base_sha256=application_hash,
                                  layout_input_sha256=preserved_hash)
            path.write_text(json.dumps(report))
            self.assertEqual(validate(base, stage, layout, generic, ga027_recipe=ga027)["status"], "passed")
            self.assertEqual(json.loads(path.read_text())["work"]["application_base_sha256"], application_hash)
            # Equal decoded content does not excuse binding the wrong witness bytes.
            report["work"]["layout_input_sha256"] = application_hash
            path.write_text(json.dumps(report))
            result = validate(base, stage, layout, generic, ga027_recipe=ga027)
            self.assertTrue(any("Layout input hash" in p["error"] for p in result["problems"]))

    def test_ga027_table_column_reordering_cannot_drop_or_duplicate_source_content(self):
        pid = "ga-027-source-heading-20"
        original, corrected = "Harn statt Hämatin\n47\n21", "47 21 Harn statt Hämatin"
        prior = {"work_id": "ga-027", "source_sha256": "a" * 64,
                 "source_epub_sha256": "b" * 64, "title": "Book",
                 "passages": [{"id": pid, "title": "TYPISCHE HEILMITTEL", "text": original,
                               "source_text": original, "checksum": digest(original.encode()), "metadata": {}}]}
        plan = {"input_sha256": digest(original.encode()), "output_sha256": digest(corrected.encode()),
                "group_title": "Book", "segments": [{"kind": "note", "join": " ", "parts": [
                    {"block": 0, "start": original.index("47"), "end": original.index("47") + 2},
                    {"block": 0, "start": original.index("21"), "end": original.index("21") + 2},
                    {"block": 0, "start": 0, "end": len("Harn statt Hämatin")}]}]}
        toc = [{"id": pid, "title": "TYPISCHE HEILMITTEL", "level": 1,
                "passage_id": pid, "start_offset": 0, "parent_id": None}]
        recipe = {"schema_version": 1, "work_id": "ga-027", "offset_unit": "utf16",
                  "source_sha256": "a" * 64, "source_epub_sha256": "b" * 64,
                  "source_url": "https://example.com/ga-027.epub", "passages": {pid: plan},
                  "table_of_contents": toc}
        revision = digest(json.dumps(recipe, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode())
        final = deepcopy(prior)
        final["passages"][0].update(text=corrected, checksum=digest(corrected.encode()), metadata={
            "reading_blocks": [{"kind": "note", "start_offset": 0, "end_offset": len(corrected)}],
            "group_title": "Book", "structure_revision": revision})
        final.update(table_of_contents=toc, metadata={"source_layout": {
            "recipe_sha256": revision, "source_sha256": "a" * 64, "source_url": recipe["source_url"],
            "offset_unit": "utf16", "review_scope": "structure_and_evidenced_repairs"}})
        events = {pid: [{"rule": "source_layout", "count": 1, "layout_blocks": 1, "replacements": []}]}
        self.assertEqual(inspect_source_layout(prior, final, recipe, events), ([], 0))
        for parts in (plan["segments"][0]["parts"][:-1], plan["segments"][0]["parts"] * 2):
            tampered = deepcopy(recipe)
            tampered["passages"][pid]["segments"][0]["parts"] = parts
            errors = inspect_source_layout(prior, final, tampered, events)[0]
            self.assertTrue(any("lost or duplicated source characters" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
