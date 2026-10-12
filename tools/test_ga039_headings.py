#!/usr/bin/env python3
"""Focused source, numbering, UTF-16 and staging guards for GA039 headings."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from finalize_library import read_json, write_json
from build_ga039_heading_review import build_review
import repair_ga039_headings as repair


class GA039HeadingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "original.epub"
        self.baseline = self.root / "baseline"
        self.member = "EPUB/chapter-0001.xhtml"
        xml = ('<html xmlns="http://www.w3.org/1999/xhtml"><body>'
               '<h2>253- AN PAULINE SPECHT</h2>'
               '<p>😀 Ein Brief nennt 254 und das Jahr 1920.\nPhysische Quellzeile.</p>'
               '<p>2 54. AN RICHARD SPECHT</p><p>Ein unveränderter Körper.</p>'
               '<h2>255- AN ANNA EUNIKE</h2>'
               '<p>Erste physische\nQuellzeile <br/>zweite echte BR-Zeile.</p>'
               '<h2>256. AN ROSA MAYREDER</h2><p>Weiterer Briefkörper.</p>'
               '<p>74a. AUS EINEM BRIEF MORIZ ZITTERS AN RUDOLF STEINER</p>'
               '<p>74b. AN MORIZ ZITTER</p><p>637a. K. AUGUST MÜLLER AN RUDOLF STEINER</p>'
               '<p>637b. AN K. AUGUST MÜLLER</p>'
               '<h2>VERZEICHNIS DER BRIEFE</h2></body></html>').encode()
        with ZipFile(self.source, "w") as archive:
            archive.writestr(self.member, xml)
        self.body = ET.fromstring(xml).find("{http://www.w3.org/1999/xhtml}body")
        self.member_sha = repair.digest(xml)
        self.addCleanup(patch.stopall)
        patch.object(repair, "SOURCE", self.source).start()
        patch.object(repair, "BASELINE", self.baseline).start()
        patch.object(repair, "ORIGINAL_PASSAGE_COUNT", 3).start()
        patch.object(repair, "MAIN_NUMBERS", ("253", "254", "255", "256")).start()
        first_text = "😀 Ein Brief nennt 254 und das Jahr 1920. Physische Quellzeile.\n\n2 54. AN RICHARD SPECHT\n\nEin unveränderter Körper."
        supplement = ["74a. AUS EINEM BRIEF MORIZ ZITTERS AN RUDOLF STEINER", "74b. AN MORIZ ZITTER",
                      "637a. K. AUGUST MÜLLER AN RUDOLF STEINER", "637b. AN K. AUGUST MÜLLER"]
        second_text = "Weiterer Briefkörper.\n\n" + "\n\n".join(supplement)
        self.before = {"work_id": "ga-039", "title": "Briefe, Bd. 2", "source_sha256": "original-doc-sha",
                       "source_epub_sha256": repair.digest(self.source.read_bytes()), "passage_count": 3,
                       "metadata": {"unchanged": [1, 2]}, "content_completeness": "complete",
                       "passages": [self.passage("ga-039-doc-heading-2", "253- AN PAULINE SPECHT", first_text),
                                    self.passage("ga-039-doc-heading-3", "256. AN ROSA MAYREDER", second_text),
                                    self.passage("ga-039-doc-heading-113", "1920 645. An Richard Teschner Dornach, 27. Februar 1914", "Brief\n\nSeite\n\n1920 645 476")]}
        first, second, directory = self.before["passages"]
        restore_raw = "".join(self.body[5].itertext()).strip()
        restored = {"id": "ga-039-source-letter-255", "original_number": "255", "after_existing_pid": first["id"],
                    "title": "255- AN ANNA EUNIKE", "source_title": "255- AN ANNA EUNIKE", "source_member": self.member,
                    "heading_source_witness": self.witness(4), "source_segments": [{**self.witness(5), "mode": "br"}],
                    "source_join": "double_newline", "source_text": restore_raw, "source_text_sha256": repair.sha(restore_raw),
                    "text": "Erste physische Quellzeile\nzweite echte BR-Zeile."}
        repairs = [self.replacement("prefix-253", first["id"], "253-", "253.", 0, 0),
                   self.replacement("prefix-255", restored["id"], "255-", "255.", 0, 4),
                   self.replacement("prefix-254", first["id"], "2 54.", "254.", first_text.index("2 54."), 2, field="text"),
                   {"id": "directory", "passage_id": directory["id"], "field": "title", "start_codepoint": 0,
                    "old": directory["title"], "new": "Verzeichnis der Briefe", "count": 1, "kind": "source_editorial_label",
                    "source_witnesses": [self.witness(12)], "source_pdf_pages": [1], "evidence": "Belegtes Originalverzeichnis"}]
        headings = [self.heading(first, "title", "253", 0), self.heading(first, "text", "254", 2),
                    self.heading({"id": restored["id"], "title": restored["title"]}, "title", "255", 4),
                    self.heading(second, "title", "256", 6)]
        headings += [self.heading(second, "text", number, index) for number, index in zip(repair.SUPPLEMENT_NUMBERS, range(8, 12))]
        headings.append({"id": "directory", "passage_id": directory["id"], "field": "title", "start_codepoint": 0,
                         "end_codepoint": 0, "original_number": None, "label": "Verzeichnis der Briefe",
                         "old_source_full_heading": "VERZEICHNIS DER BRIEFE", "source_witnesses": [self.witness(12)]})
        self.audit = {"work_id": "ga-039", "source_epub_sha256": self.before["source_epub_sha256"],
                      "repairs": repairs, "source_restorations": [restored], "headings": headings,
                      "all_main_letter_headings": [{"original_number": number} for number in repair.MAIN_NUMBERS]}
        self.review = build_review(self.before, self.audit)
        repair.preserve_baseline(self.before, self.baseline)

    def witness(self, index):
        return {"source_member": self.member, "body_index": index, "child_path": [],
                "member_sha256": self.member_sha, "source_paragraph_sha256": repair.sha("".join(self.body[index].itertext()))}

    @staticmethod
    def passage(pid, title, text):
        return {"id": pid, "title": title, "text": text, "source_text": "Raw " + text,
                "checksum": repair.sha(text), "ga_page": None, "source_member": "original",
                "source_label": "Vorhandene GA-Arbeitsausgabe / Kutscherei",
                "metadata": {"page_numbers": [], "annotations": [{"id": "n", "marker": "*", "text": "Unveränderte Anmerkung"}]}}

    def replacement(self, rid, pid, old, new, offset, source_index, field="title"):
        return {"id": rid, "passage_id": pid, "field": field, "start_codepoint": offset, "old": old, "new": new,
                "count": 1, "corrected_number": new[:-1], "source_witnesses": [self.witness(source_index)],
                "source_pdf_pages": [1], "evidence": "Am Original gedruckte Briefnummer"}

    def heading(self, passage, field, number, source_index):
        label = "".join(self.body[source_index].itertext())
        start = passage["text"].index(label) if field == "text" else 0
        return {"id": "letter-" + number, "passage_id": passage["id"], "field": field,
                "start_codepoint": start, "end_codepoint": start + len(label) if field == "text" else 0,
                "label": label, "original_number": number, "old_source_full_heading": label,
                "source_witnesses": [self.witness(source_index)]}

    def test_exact_source_merge_prefixes_preserve_references_and_sources(self):
        original = deepcopy(self.before)
        after, events = repair.apply_review(self.before, self.review)
        self.assertEqual(self.before, original)
        self.assertEqual([p["id"] for p in after["passages"]], [original["passages"][0]["id"], "ga-039-source-letter-255", original["passages"][1]["id"], original["passages"][2]["id"]])
        first = after["passages"][0]
        self.assertEqual(first["text"], original["passages"][0]["text"].replace("2 54.", "254."))
        self.assertEqual(first["title"], "253. AN PAULINE SPECHT")
        self.assertIn("254 und das Jahr 1920", first["text"])
        for before in original["passages"]:
            final = next(p for p in after["passages"] if p["id"] == before["id"])
            self.assertEqual(before["source_text"], final["source_text"])
            self.assertEqual({k: v for k, v in before.items() if k not in ("title", "text", "checksum", "metadata")},
                             {k: v for k, v in final.items() if k not in ("title", "text", "checksum", "metadata")})
            self.assertEqual(before["metadata"], {k: v for k, v in final["metadata"].items() if k != "reading_blocks"})
        self.assertEqual(after["passages"][1]["title"], "255. AN ANNA EUNIKE")
        self.assertEqual(after["passages"][1]["text"], "Erste physische Quellzeile\nzweite echte BR-Zeile.")
        self.assertEqual(after["passages"][-1]["title"], "Verzeichnis der Briefe")
        self.assertEqual(len(events), 4)
        self.assertEqual([e["rule"] for e in events], [repair.RULE, "source_restoration", repair.RULE, repair.RULE])
        self.assertEqual(events[0]["replacements"], [self.review["repairs"][0], self.review["repairs"][2]])
        self.assertEqual(events[1]["replacements"], [self.review["repairs"][1]])

    def test_utf16_navigation_and_body_headings_are_independent_from_container_titles(self):
        after, _ = repair.apply_review(self.before, self.review)
        first = after["passages"][0]
        toc = next(e for e in after["table_of_contents"] if e["id"] == "letter-254")
        cp = first["text"].index("254. AN RICHARD SPECHT")
        self.assertEqual(toc["start_offset"], cp + 1)
        blocks = first["metadata"]["reading_blocks"]
        self.assertEqual([b["kind"] for b in blocks], ["prose", "heading", "prose"])
        self.assertEqual(blocks[1]["start_offset"], toc["start_offset"])
        self.assertEqual(len(after["table_of_contents"]), 9)
        self.assertEqual([h["original_number"] for h in self.review["headings"] if h["original_number"] is not None], list(repair.MAIN_NUMBERS + repair.SUPPLEMENT_NUMBERS))

    def test_idempotence_rebuilds_all_unchanged_metadata_from_baseline(self):
        after, _ = repair.apply_review(self.before, self.review)
        again, changes = repair.apply_review(after, self.review)
        self.assertEqual(again, after); self.assertEqual(changes, [])
        mutations = [lambda p: p["passages"][0]["metadata"]["annotations"][0].update(text="Fremde Anmerkung"),
                     lambda p: p["passages"][0]["metadata"]["reading_blocks"][0].update(end_offset=1),
                     lambda p: p["table_of_contents"][0].update(title="Fremder Titel"),
                     lambda p: p["passages"][1].update(source_text="Fremder Rohtext"),
                     lambda p: p["metadata"].update(unchanged=[])]
        for mutate in mutations:
            bad = deepcopy(after); mutate(bad)
            with self.assertRaises(ValueError): repair.apply_review(bad, self.review)

    def test_wrong_numbers_offsets_counts_hashes_and_header_identities_are_rejected(self):
        mutations = [lambda r: r["repairs"][0].update(count=True), lambda r: r["repairs"][0].update(count=2),
                     lambda r: r["repairs"][0].update(new="254.", corrected_number="254"),
                     lambda r: r["repairs"][0].update(old="253- AN", new="253."),
                     lambda r: r["repairs"][0].update(start_codepoint=1),
                     lambda r: r["repairs"][0]["source_witnesses"][0].update(body_index=1),
                     lambda r: r["headings"].pop(1), lambda r: r["headings"][1].update(original_number="255"),
                     lambda r: r["headings"][1].update(end_codepoint=9999),
                     lambda r: r["source_restorations"][0].update(after_existing_pid="foreign"),
                     lambda r: r["source_restorations"][0]["source_segments"][0].update(source_paragraph_sha256="wrong"),
                     lambda r: r["source_restorations"][0].update(text="Geänderter Briefkörper"),
                     lambda r: r["input_passages"]["ga-039-doc-heading-2"].update(input_title_sha256="wrong"),
                     lambda r: r.update(source_epub_sha256="wrong")]
        for mutate in mutations:
            bad = deepcopy(self.review); mutate(bad)
            with self.subTest(mutate=mutate):
                with self.assertRaises(ValueError): repair.apply_review(self.before, bad)

    def test_explicit_breaks_and_literal_modes_do_not_invent_paragraphs(self):
        atom = ET.fromstring('<p>XML\nFormatierung <span>mit\nText</span><br/>Echte Zeile</p>')
        self.assertEqual(repair.render_segment(atom, {"mode": "br"}), "XML Formatierung mit Text\nEchte Zeile")
        with self.assertRaises(ValueError): repair.render_segment(atom, {"mode": "paragraph"})
        with self.assertRaises(ValueError): repair.render_segment(atom, {"mode": "literal"})
        self.assertEqual(repair.render_segment(ET.fromstring('<pre>Ein\n  Literal</pre>'), {"mode": "literal"}), "Ein\n  Literal")

    def test_only_exact_reviewed318_319_atom_slices_are_allowed(self):
        member = "EPUB/chapter-0004.xhtml"
        xml = ('<html xmlns="http://www.w3.org/1999/xhtml"><body>' + '<p />' * 218 +
               '<p><span>Rudolf Steiner <br/>319. </span><span>an die Cotta\'sche Buchhandlung</span></p>' +
               '</body></html>').encode()
        source = self.root / "slice.epub"
        with ZipFile(source, "w") as archive: archive.writestr(member, xml)
        body = ET.fromstring(xml).find("{http://www.w3.org/1999/xhtml}body")
        raw = "".join(body[218].itertext()); start = raw.index("319.")
        witness = {"source_member": member, "body_index": 218, "child_path": [], "member_sha256": repair.digest(xml),
                   "source_paragraph_sha256": repair.sha(raw),
                   "rawitertext_slice": {"start_codepoint": start, "end_codepoint": len(raw), "text_sha256": repair.sha(raw[start:])}}
        atoms = repair.SourceAtoms(source, repair.digest(source.read_bytes()))
        self.addCleanup(atoms.close)
        self.assertTrue(atoms.atom(witness)[1].startswith("319."))
        footer = deepcopy(witness); footer["child_path"] = [0]
        raw_footer = "".join(body[218][0].itertext())
        footer["source_paragraph_sha256"] = repair.sha(raw_footer)
        footer["rawitertext_slice"] = {"start_codepoint": 0, "end_codepoint": start, "text_sha256": repair.sha(raw_footer[:start])}
        atom, selected = atoms.atom(footer)
        self.assertEqual(selected.strip(), "Rudolf Steiner")
        self.assertEqual(repair.render_segment(atom, {**footer, "mode": "paragraph"}), "Rudolf Steiner")
        for mutate in (lambda w: w["rawitertext_slice"].update(start_codepoint=start + 1),
                       lambda w: w["rawitertext_slice"].update(text_sha256="wrong"),
                       lambda w: w.update(source_member=self.member)):
            bad = deepcopy(witness); mutate(bad)
            with self.assertRaises((ValueError, KeyError)): atoms.atom(bad)

    def test356_list_marker_is_bound_to_its_original_ol_li_selector(self):
        xml = '<html xmlns="http://www.w3.org/1999/xhtml"><body><ol><li>Erster Punkt</li><li>Zweiter Punkt</li></ol></body></html>'.encode()
        source = self.root / "list.epub"
        with ZipFile(source, "w") as archive: archive.writestr(self.member, xml)
        ol = ET.fromstring(xml).find("{http://www.w3.org/1999/xhtml}body")[0]
        parent = {"source_member": self.member, "body_index": 0, "child_path": [], "member_sha256": repair.digest(xml),
                  "source_paragraph_sha256": repair.sha("".join(ol.itertext()))}
        segment = {**parent, "child_path": [0], "source_paragraph_sha256": repair.sha("".join(ol[0].itertext()))}
        marker = {"ordinal": 1, "item_index": 0, "parent_source_witness": parent,
                  "pdf_raster_witnesses": [{"original_pdf_sha256": "a" * 64}], "pdf_line_witnesses": [{"text": "1."}], "evidence": "Originalscan"}
        atoms = repair.SourceAtoms(source, repair.digest(source.read_bytes())); self.addCleanup(atoms.close)
        self.assertEqual(repair.validate_list_marker({"original_number": "356"}, segment, marker, atoms), 1)
        for mutate in (lambda m: m.update(ordinal=4), lambda m: m.update(item_index=1), lambda m: m.update(pdf_raster_witnesses=[])):
            bad = deepcopy(marker); mutate(bad)
            with self.assertRaises(ValueError): repair.validate_list_marker({"original_number": "356"}, segment, bad, atoms)
        with self.assertRaises(ValueError): repair.validate_list_marker({"original_number": "355"}, segment, marker, atoms)

    def stage_input(self):
        priv = self.root / "priv"
        for name in ("content", "library", "proofreading/works"):
            (priv / name).mkdir(parents=True)
        other = deepcopy(self.before); other.update(work_id="ga-038", passage_count=1)
        other["passages"] = [self.passage("other", "Anderer Band", "Ein anderer Band.")]
        works = []
        for payload in (self.before, other):
            wid = payload["work_id"]; path = priv / "content" / (wid + ".json.gz")
            write_json(path, payload)
            works.append({"id": wid, "content_path": "content/" + path.name,
                          "passages": [{k: p[k] for k in ("id", "title", "ga_page", "checksum")} for p in payload["passages"]]})
            write_json(priv / "proofreading/works" / (wid + ".json"),
                       {"work": {"id": wid, "available": True, "after_sha256": repair.digest(path.read_bytes()),
                                 "before_sha256": repair.digest(path.read_bytes()), "newlines_removed": 0,
                                 "passage_count": len(payload["passages"]), "checks": []}, "changes": [], "flags": []})
        write_json(priv / "library/catalog.json", {"works": works})
        write_json(priv / "proofreading/catalog.json", {"generated_at": "original-date"})
        return priv

    def test_fresh_stage_distinguishes_baseline_and_application_bytes(self):
        priv = self.stage_input(); original = (priv / "content/ga-039.json.gz").read_bytes()
        other = (priv / "content/ga-038.json.gz").read_bytes()
        baseline_path = self.baseline / "content/ga-039.json.gz"
        variant = bytearray(baseline_path.read_bytes()); variant[9] ^= 1; baseline_path.write_bytes(variant)
        with redirect_stdout(io.StringIO()):
            events = repair.stage(priv, self.root / "stage", self.review, self.baseline)
        self.assertEqual((priv / "content/ga-039.json.gz").read_bytes(), original)
        self.assertEqual((self.root / "stage/content/ga-038.json.gz").read_bytes(), other)
        detail = read_json(self.root / "stage/proofreading/works/ga-039.json")
        self.assertEqual(detail["work"]["application_base_sha256"], repair.digest(original))
        self.assertEqual(detail["work"]["ga039_heading_input_sha256"], repair.digest(bytes(variant)))
        self.assertEqual(detail["changes"], events)
        with redirect_stdout(io.StringIO()):
            changes = repair.stage(self.root / "stage", self.root / "repeat", self.review, self.baseline)
        self.assertEqual(changes, [])
        self.assertEqual((self.root / "repeat/content/ga-039.json.gz").read_bytes(), (self.root / "stage/content/ga-039.json.gz").read_bytes())
        with self.assertRaises(ValueError): repair.stage(priv, self.root / "stage", self.review, self.baseline)
        variant[9] ^= 2; baseline_path.write_bytes(variant)
        with self.assertRaises(ValueError): repair.stage(self.root / "stage", self.root / "drift", self.review, self.baseline)
        self.assertFalse((self.root / "drift").exists())


class GA039ActualReviewTests(unittest.TestCase):
    def test_actual_frozen_review_preserves_all_original_containers(self):
        baseline = repair.BASELINE / "content/ga-039.json.gz"
        if not repair.REVIEW.exists() or not baseline.exists():
            self.skipTest("GA039 source review and baseline are not frozen yet")
        review, before = read_json(repair.REVIEW), read_json(baseline)
        after, events = repair.apply_review(before, review)
        self.assertEqual(len(before["passages"]), 102)
        self.assertEqual(len(after["passages"]), 143)
        self.assertEqual(review["letter_heading_count"], 403)
        self.assertEqual(len([e for e in events if e["rule"] == "source_restoration"]), 41)
        original_ids = [p["id"] for p in before["passages"]]
        self.assertEqual([p["id"] for p in after["passages"] if p["id"] in original_ids], original_ids)
        for old in before["passages"]:
            final = next(p for p in after["passages"] if p["id"] == old["id"])
            self.assertEqual(old["source_text"], final["source_text"])
        title = next(p["title"] for p in after["passages"] if p["id"] == "ga-039-doc-heading-55")
        self.assertTrue(title.startswith("452. "))
        again, events = repair.apply_review(after, review)
        self.assertEqual(again, after); self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
