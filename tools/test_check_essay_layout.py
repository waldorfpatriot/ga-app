"""Negative checks for the source-bound essay and front-contents guards."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import test_check_proofreading_samples as fixtures
from check_essay_layout import (inspect_essay_annotation_recovery, inspect_essay_recovery, inspect_ga045_doc_boundary, inspect_ga045_internal_seam, inspect_ga045_page_seam,
                               inspect_essay_word_repair, inspect_pdf_witnesses, inspect_reviewed_essay_layout)
from check_proofreading_samples import digest, inspect_source_layout, source_boundary_offset
from repair_source_structure import page_position


class EssaySourceValidationTests(unittest.TestCase):
    def test_ga045_page_word_seam_requires_both_endpoints_and_footer(self):
        left, right = "Auf einer Berges-", "höhe steht der Mensch."
        records = [{"index": 0, "text": left},
                   {"index": 1, "text": "27", "is_page_footer": True, "footer_page": 27},
                   {"index": 2, "text": right}]
        origin = lambda i: {"source_doc_paragraph_index": i,
                            "source_doc_paragraph_sha256": digest(records[i]['text'].encode())}
        repair = {"old": "Berges- höhe", "new": "Bergeshöhe", "kind": "physical_word_seam",
                  "match_word_boundaries": True, "physical_page_seam": True,
                  "source_contains_exact_physical_lf": False,
                  "source_doc_witnesses": [origin(0), origin(2)],
                  "source_doc_page_footer": origin(1) | {"page": 27}}
        inspect_essay_word_repair(repair, [left, right], "ga-045-doc-heading-1", {}, records)
        for changed in (repair | {"source_doc_page_footer": origin(1) | {"page": 28}},
                        repair | {"source_doc_witnesses": [origin(0), origin(1)]}):
            with self.assertRaises(ValueError):
                inspect_ga045_page_seam(changed, [left, right], records)
        with self.assertRaises(ValueError):
            inspect_ga045_page_seam(repair, [left + ' Another sentence.', right], records)
        with self.assertRaises(ValueError):
            inspect_ga045_page_seam(repair, [left, right], records[:1])

    def test_ga045_paragraph_boundary_cannot_move_into_a_printed_line(self):
        text = "  Anfang des\nursprünglichen Absatzes."
        records = [{"index": 0, "text": text}]
        start = {"source_doc_paragraph_index": 0, "source_doc_paragraph_sha256": digest(text.encode()),
                 "canonical_anchor": "Anfang des\nursprünglichen"}
        inspect_ga045_doc_boundary(start, records)
        with self.assertRaises(ValueError):
            inspect_ga045_doc_boundary(start | {"canonical_anchor": "ursprünglichen Absatzes"}, records)
        with self.assertRaises(ValueError):
            inspect_ga045_doc_boundary(start | {"source_doc_paragraph_sha256": "changed"}, records)

    def ga045_seam(self):
        raw = "Das Ich-\nMenschen Erleben."
        records = [{"index": 0, "text": raw}]
        repair = {"kind": "physical_word_seam", "old": "Ich- Menschen", "new": "Ich-Menschen",
                  "match_word_boundaries": True, "source_contains_exact_physical_lf": True,
                  "source_doc_witnesses": [{"source_doc_paragraph_index": 0,
                                           "source_doc_paragraph_sha256": digest(raw.encode())}]}
        return repair, raw, records

    def test_ga045_word_seam_binds_both_literal_line_endings(self):
        repair, raw, records = self.ga045_seam()
        inspect_essay_word_repair(repair, [raw], "ga-045-doc-heading-1", {}, records)
        with self.assertRaises(ValueError):
            inspect_essay_word_repair(repair, [raw], "ga-035-doc-heading-1", {}, records)
        for changed in (repair | {"new": "Ich-Wesen"}, repair | {"match_word_boundaries": False},
                        repair | {"source_contains_exact_physical_lf": False},
                        repair | {"source_doc_witnesses": []}):
            with self.assertRaises(ValueError):
                inspect_ga045_internal_seam(changed, [raw], records)

    def test_ga045_word_seam_rejects_whitespace_and_doc_hash_substitution(self):
        repair, raw, records = self.ga045_seam()
        with self.assertRaises(ValueError):
            inspect_ga045_internal_seam(repair, [raw.replace("\n", " ")], records)
        with self.assertRaises(ValueError):
            inspect_ga045_internal_seam(repair, [raw], [{"index": 0, "text": raw.replace("\n", " ")}])
        with self.assertRaises(ValueError):
            inspect_ga045_internal_seam(repair, [raw], [{"index": 0, "text": raw + raw}])
        with self.assertRaises(ValueError):
            inspect_ga045_internal_seam(repair, [raw], None)

    def test_ga045_word_seam_rejects_duplicate_original_occurrences(self):
        repair, raw, records = self.ga045_seam()
        with self.assertRaises(ValueError):
            inspect_ga045_internal_seam(repair, [raw, raw], records)
        duplicated = repair | {"source_doc_witnesses": repair["source_doc_witnesses"] * 2}
        with self.assertRaises(ValueError):
            inspect_ga045_internal_seam(duplicated, [raw], records)

    def test_identical_page_boundaries_preserve_unicode_and_skip_source_whitespace(self):
        text = "😀 A\nB"
        for point, expected in ((0, 0), (1, 3), (2, 3), (3, 5), (4, 5), (5, 6)):
            self.assertEqual(page_position(text, text, point), expected)
            self.assertEqual(source_boundary_offset(text, text, point), expected)

    def fixture(self, directory):
        helper = fixtures.SourceLayoutValidationTests()
        prior, final, recipe, events, source, path = helper.ga032_fixture(directory)
        review = json.loads(path.read_text())
        prior, final, recipe, events, review = [
            json.loads(json.dumps(item).replace("ga-032", "ga-035"))
            for item in (prior, final, recipe, events, review)]
        helper.bind_ga032_fixture(recipe, final, review, path)
        return prior, final, recipe, events, source, path

    def inspect(self, values):
        return inspect_reviewed_essay_layout(*values, inspect_source_layout)

    def test_complete_source_projection_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.fixture(directory)
            untouched = deepcopy(values[:4])
            self.assertEqual(self.inspect(values), ([], 2))
            self.assertEqual(values[:4], untouched)

    def test_rejects_changed_source_bytes_and_raw_source(self):
        for change in ("archive", "source_text"):
            with tempfile.TemporaryDirectory() as directory:
                values = self.fixture(directory)
                if change == "archive":
                    values[4].write_bytes(values[4].read_bytes() + b"different-source")
                else:
                    values[0]["passages"][0]["source_text"] += "added"
                with self.assertRaises(ValueError):
                    self.inspect(values)

    def test_rejects_changed_annotations_and_flat_source_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.fixture(directory)
            values[1]["passages"][0]["metadata"]["annotations"][0]["text"] = "Changed note"
            self.assertTrue(self.inspect(values)[0])
        with tempfile.TemporaryDirectory() as directory:
            values = self.fixture(directory)
            values[2]["passages"]["ga-035-1"]["edits"][0]["new"] = "Different spelling"
            with self.assertRaises(ValueError):
                self.inspect(values)

    def test_word_seam_cannot_change_letters_or_leave_its_source_context(self):
        repair = {"kind": "physical_word_seam", "old": "Welt- anschauung", "new": "Weltanschauung",
                  "match_word_boundaries": True}
        inspect_essay_word_repair(repair, ["Zur Welt-", "anschauung."], "ga-035-1", {})
        for field, value in (("new", "Weltbetrachtung"), ("match_word_boundaries", False)):
            with self.assertRaises(ValueError):
                inspect_essay_word_repair(repair | {field: value}, ["Zur Welt-", "anschauung."], "ga-035-1", {})
        with self.assertRaises(ValueError):
            inspect_essay_word_repair(repair, ["Other text", "anschauung."], "ga-035-1", {})

    def test_printed_seam_joins_its_two_lines_despite_the_reading_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "original.pdf"
            source.write_bytes(b"Bound original source")
            review = {"work_id": "ga-036", "original_pdf_path": str(source), "original_pdf_sha256": digest(source.read_bytes())}
            first, second = [0., 0., 10., 1.], [0., 2., 10., 3.]
            repair = {"old": "Welt- anschauung", "pdf_line_pair_witnesses": [{"pdf_page": 1,
                "pdf_line_before": "Die Welt-", "pdf_line_after": "anschauung.",
                "line_before_bbox": first, "line_after_bbox": second}]}
            with patch("check_essay_layout.original_page_lines", return_value=[("Die Welt-", first), ("anschauung.", second)]):
                inspect_pdf_witnesses(repair, review)
                with self.assertRaises(ValueError):
                    inspect_pdf_witnesses(repair | {"old": "Welt- betrachtung"}, review)

    def test_contents_restoration_cannot_change_an_essay(self):
        repair = {"kind": "source_contents_restoration", "old": "old", "new": "Original contents", "count": 1}
        witness = {"source_role": "table_of_contents", "restored_contents_text": "Original contents"}
        inspect_essay_word_repair(repair, ["Exact contents witness"], "ga-036-doc-heading-1", witness)
        for pid, source_role in (("ga-036-doc-heading-2", witness), ("ga-036-doc-heading-1", {}),
                                 ("ga-035-doc-heading-1", witness)):
            with self.assertRaises(ValueError):
                inspect_essay_word_repair(repair, ["Exact contents witness"], pid, source_role)

    def test_heading_restoration_requires_its_exact_heading_boundary(self):
        repair = {"kind": "source_heading_restoration", "old": "1840-i%71", "new": "1840–1871",
                  "heading_start_codepoint": 5, "source_pdf_pages": [23]}
        witness = {"starts": [{"kind": "heading", "start_codepoint": 5, "canonical_anchor": "1840-i%71"}]}
        inspect_essay_word_repair(repair, ["1840-i%71"], "ga-033-doc-heading-3", witness)
        for changes in ({"heading_start_codepoint": 4}, {"new": "A\nB"}, {"source_pdf_pages": []}):
            with self.assertRaises(ValueError):
                inspect_essay_word_repair(repair | changes, ["1840-i%71"], "ga-033-doc-heading-3", witness)
        witness["starts"][0]["kind"] = "prose"
        with self.assertRaises(ValueError):
            inspect_essay_word_repair(repair, ["1840-i%71"], "ga-033-doc-heading-3", witness)

    def navigation_fixture(self, directory):
        values = self.fixture(directory)
        prior, final, recipe, events, source, path = values
        review = json.loads(path.read_text())
        start = review["passages"]["ga-035-1"]["starts"][1]
        start["toc_target"] = "printed-heading"
        row = {"id": "printed-essay", "title": "TITLE", "level": 1,
               "parent_id": None, "target": "printed-heading"}
        witness = {key: start[key] for key in ("source_member", "body_index", "child_path", "source_paragraph_sha256")}
        review["original_table_of_contents"] = [{"text": "TITLE", "printed_page": 12}]
        review["original_toc_target_review"] = [{"toc_id": "printed-essay", "target": "printed-heading",
            "level": 1, "parent_id": None, "source_witness": witness}]
        review["table_of_contents"] = [row]
        recipe["table_of_contents"] = [{key: value for key, value in row.items() if key != "target"} |
                                       {"passage_id": "ga-035-1", "start_offset": 5}]
        final["table_of_contents"] = deepcopy(recipe["table_of_contents"])
        fixtures.SourceLayoutValidationTests().bind_ga032_fixture(recipe, final, review, path)
        return values

    def test_original_navigation_requires_a_printed_entry_for_every_article(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.navigation_fixture(directory)
            self.assertEqual(self.inspect(values), ([], 2))
            prior, final, recipe, events, source, path = values
            review = json.loads(path.read_text())
            review["table_of_contents"].append(review["table_of_contents"][0] | {"id": "false-signature", "title": "Author signature"})
            recipe["table_of_contents"].append(recipe["table_of_contents"][0] | {"id": "false-signature", "title": "Author signature"})
            final["table_of_contents"] = deepcopy(recipe["table_of_contents"])
            fixtures.SourceLayoutValidationTests().bind_ga032_fixture(recipe, final, review, path)
            with self.assertRaisesRegex(ValueError, "extra navigation article"):
                self.inspect(values)

    def test_navigation_cannot_flatten_a_reviewed_child(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.navigation_fixture(directory)
            prior, final, recipe, events, source, path = values
            review = json.loads(path.read_text())
            review["original_toc_target_review"][0]["level"] = 2
            fixtures.SourceLayoutValidationTests().bind_ga032_fixture(recipe, final, review, path)
            with self.assertRaisesRegex(ValueError, "hierarchy differs"):
                self.inspect(values)

    def recovery_fixture(self, directory):
        member = "EPUB/chapter-0008.xhtml"
        parts = ["Unselected"] * 19 + ["Bibliographisches und Textbehandlung"] + ["Original author paragraph " + str(i) for i in range(5)]
        xml = ('<html xmlns="http://www.w3.org/1999/xhtml"><body>' +
               ''.join('<p>' + text + '</p>' for text in parts) + '</body></html>').encode()
        source = Path(directory) / "ga033.epub"
        with ZipFile(source, "w") as archive:
            archive.writestr(member, xml)
        author = {"member": member, "heading": "Bibliographisches und Textbehandlung", "id": None}
        old = {"id": "ga-033-doc-heading-17", "title": "JEAN PAUL", "text": "Old retained text",
               "source_text": "Old retained source", "source_label": "Original"}
        prior = {"work_id": "ga-033", "passages": [old], "passage_count": 1,
                 "proofing": {"excluded_sections": [{"heading": "Editor A"}, author, {"heading": "Editor B"}]}}
        text = "\n\n".join(parts[19:25])
        addition = {"id": "restore-original", "kind": "passage", "passage_id": "ga-033-schopenhauer-bibliographisches",
            "title": "Bibliographisches und Textbehandlung", "source_role": "author", "evidence": "Original printed subsection",
            "source_segments": [{"source_member": member, "body_indices": list(range(19, 25)), "member_sha256": digest(xml)}],
            "source_pdf_pages": [265, 266, 267, 268], "source_text": text, "text": text,
            "source_text_sha256": digest(text.encode()), "text_sha256": digest(text.encode()),
            "insert_before_passage_id": old["id"]}
        review = {"source_additions": [addition], "original_passages": {old["id"]: {
            "input_sha256": digest(old["text"].encode()), "source_text_sha256": digest(old["source_text"].encode())}},
            "proofing_repairs": {"excluded_sections": {"before": deepcopy(prior["proofing"]["excluded_sections"]),
            "after": [row for row in prior["proofing"]["excluded_sections"] if row != author],
            "archive_as": "source_import_excluded_sections", "evidence": "Exact restored import exclusion"}}}
        event = {"passage_id": addition["passage_id"], "rule": "source_restoration", "count": 1,
            "label": "Exakt belegten Originalquellentext wiederhergestellt", "addition_id": addition["id"],
            "source_text_sha256": addition["source_text_sha256"], "text_sha256": addition["text_sha256"],
            "before_excerpt": "", "after_excerpt": text[:440], "evidence": addition["evidence"]}
        return prior, deepcopy(review), review, {addition["passage_id"]: [event]}, source

    def test_restoration_is_exactly_the_omitted_author_subsection(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.recovery_fixture(directory)
            original = deepcopy(values[0])
            restored = inspect_essay_recovery(*values)
            self.assertEqual(values[0], original)
            self.assertEqual([row["id"] for row in restored["passages"]],
                             ["ga-033-schopenhauer-bibliographisches", "ga-033-doc-heading-17"])
            self.assertEqual(restored["proofing"]["source_import_excluded_sections"], original["proofing"]["excluded_sections"])
            for field, changed in (("source_pdf_pages", [265, 266, 267, 269]), ("text", "Added unproven words")):
                tampered = self.recovery_fixture(directory)
                tampered[1]["source_additions"][0][field] = changed
                tampered[2]["source_additions"][0][field] = changed
                with self.assertRaises(ValueError):
                    inspect_essay_recovery(*tampered)

    def annotation_fixture(self, directory, heading_references=False):
        source = Path(directory) / "ga036.epub"
        specs = {"EPUB/chapter-0006.xhtml": [(66, 12, 63)],
                 "EPUB/chapter-0009.xhtml": [(27, 6, 24), (41, 5, 37), (110, 4, 105), (127, 3, 125)]}
        members, passages, additions, events = {}, [], [], {}
        heading_ids = {12: "ga-036-doc-heading-35", 6: "ga-036-doc-heading-47",
                       5: "ga-036-doc-heading-48", 4: "ga-036-doc-heading-52", 3: "ga-036-doc-heading-53"}
        with ZipFile(source, "w") as archive:
            for member, notes in specs.items():
                elements = ["<p>Original paragraph</p>"] * (max(item[0] for item in notes) + 1)
                pid = "ga-036-author-" + str(len(passages))
                source_parts = []
                for index, number, reference_index in notes:
                    if heading_references:
                        pid = heading_ids[number]
                    name, reference_id = "footnote-recovered-" + str(number), "noteref-recovered-" + str(number)
                    elements[reference_index] = '<p>Article<a role="doc-noteref" id="' + reference_id + '" href="#' + name + '">*</a></p>'
                    if heading_references:
                        elements[reference_index] = elements[reference_index].replace('<p>', '<h2>').replace('</p>', '</h2>')
                    raw = "\n* Original author note " + str(number) + "\ncontinued. ↩"
                    elements[index] = '<aside role="doc-footnote" id="' + name + '">' + raw + '</aside>'
                    reference = {"source_member": member, "body_index": reference_index,
                        "source_paragraph_sha256": digest(b"Article*"), "reference_id": reference_id}
                    source_parts.append({key: value for key, value in reference.items() if key != "reference_id"})
                    if heading_references:
                        reference["source_heading_witness"] = deepcopy(source_parts[-1])
                        passages.append({"id": pid, "title": "Article*", "metadata": {"annotations": []}, "source_parts": []})
                    addition = {"id": "restore-note-" + str(number), "kind": "annotation", "passage_id": pid,
                        "annotation_id": member + "#" + name, "marker": "*", "source_text": raw, "text": raw.strip(),
                        "source_text_sha256": digest(raw.encode()), "text_sha256": digest(raw.strip().encode()),
                        "source_reference": reference, "evidence": "Exact omitted author note",
                        "source_segments": [{"source_member": member, "body_indices": [index]}]}
                    additions.append(addition)
                    events.setdefault(pid, []).append({"passage_id": pid, "rule": "source_restoration", "count": 1,
                        "label": "Exakt belegten Originalquellentext wiederhergestellt", "addition_id": addition["id"],
                        "source_text_sha256": addition["source_text_sha256"], "text_sha256": addition["text_sha256"],
                        "before_excerpt": "", "after_excerpt": raw.strip()[:440], "evidence": addition["evidence"]})
                xml = ('<html xmlns="http://www.w3.org/1999/xhtml"><body>' + ''.join(elements) + '</body></html>').encode()
                archive.writestr(member, xml)
                members[member] = digest(xml)
                for addition in additions:
                    if addition["source_segments"][0]["source_member"] == member:
                        addition["source_segments"][0]["member_sha256"] = digest(xml)
                if not heading_references:
                    passages.append({"id": pid, "metadata": {"annotations": []}, "source_parts": source_parts})
        prior = {"work_id": "ga-036", "passages": [{key: value for key, value in p.items() if key != "source_parts"} for p in passages]}
        review = {"source_members": members, "passages": {p["id"]: {"source_parts": p["source_parts"]} for p in passages},
                  "annotation_additions": additions}
        return prior, deepcopy(review), review, events, source

    def test_missing_note_title_links_require_the_exact_original_h2_and_title(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.annotation_fixture(directory, heading_references=True)
            result = inspect_essay_annotation_recovery(*values)
            self.assertEqual(sum(len(p["metadata"]["annotations"]) for p in result["passages"]), 5)
            values[0]["passages"][0]["title"] = "Different title*"
            with self.assertRaisesRegex(ValueError, "exact imported original heading"):
                inspect_essay_annotation_recovery(*values)

    def test_missing_notes_require_their_exact_source_link_and_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.annotation_fixture(directory)
            original = deepcopy(values[0])
            result = inspect_essay_annotation_recovery(*values)
            self.assertEqual(values[0], original)
            self.assertEqual(sum(len(p["metadata"]["annotations"]) for p in result["passages"]), 5)
            for kind in ("marker", "reference", "ledger"):
                bad = self.annotation_fixture(directory)
                if kind == "ledger":
                    next(iter(bad[3].values()))[0]["after_excerpt"] = "Different note"
                else:
                    for collection in (bad[1], bad[2]):
                        addition = collection["annotation_additions"][0]
                        if kind == "marker":
                            addition["marker"] = "2"
                        else:
                            addition["source_reference"]["body_index"] = 62
                with self.assertRaises(ValueError):
                    inspect_essay_annotation_recovery(*bad)


if __name__ == "__main__":
    unittest.main()
