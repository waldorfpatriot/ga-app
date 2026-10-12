#!/usr/bin/env python3
"""Check the actual GA 014 dramatic repair against its retained source witness."""
from copy import deepcopy
import hashlib
from pathlib import Path
import re
import tempfile
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from finalize_library import read_json
from repair_ga014_readability import apply_layout, preserve_baseline, RULE
from repair_source_structure import sha, validate_layout

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research/proofreading-sources/ga-014.epub"
BASELINE = ROOT / "research/proofreading-ga014-baseline/content/ga-014.json.gz"


def block_text(passage, block):
    return passage["text"].encode("utf-16-le")[
        2 * block["start_offset"]:2 * block["end_offset"]
    ].decode("utf-16-le")


def source_slice(blocks, part):
    if type(part) is int:
        return blocks[part]
    return blocks[part["block"]][part.get("start", 0):part.get("end")]


def without_space(text):
    return re.sub(r"\s", "", text)


class GA014ReadabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recipe = read_json(ROOT / "tools/ga014_structure.json")
        cls.repairs = read_json(ROOT / "tools/ga014_reviewed_repairs.json")
        cls.before = read_json(BASELINE if BASELINE.exists() else ROOT / "server/priv/content/ga-014.json.gz")
        cls.after, cls.events = apply_layout(cls.before, cls.recipe)
        cls.originals = {p["id"]: p for p in cls.before["passages"]}
        cls.corrected = {p["id"]: p for p in cls.after["passages"]}

    def test_all_original_ids_sources_and_outline_are_preserved(self):
        self.assertEqual(len(self.before["passages"]), 59)
        for key in ("work_id", "source_sha256", "source_epub_sha256", "content_completeness"):
            self.assertEqual(self.after[key], self.before[key])
        self.assertEqual(self.after["table_of_contents"], self.before["table_of_contents"])
        self.assertEqual(self.after["metadata"]["source_outline"], self.before["metadata"]["source_outline"])
        self.assertEqual([p["id"] for p in self.after["passages"]], [p["id"] for p in self.before["passages"]])
        for passage in self.after["passages"]:
            original = self.originals[passage["id"]]
            self.assertEqual(passage["source_text"], original["source_text"])
            self.assertEqual(passage["title"], original["title"])
            self.assertEqual(passage["checksum"], sha(passage["text"]))
            validate_layout(passage)
        self.assertEqual(len(self.events), 59)
        self.assertTrue(all(event["rule"] == RULE for event in self.events))

    def test_only_exact_page_leading_running_heads_are_omitted(self):
        total = 0
        for pid, original in self.originals.items():
            plan = self.recipe["passages"][pid]
            blocks = original["text"].split("\n\n")
            kept = list(blocks)
            allowed_edits = [{key: edit[key] for key in ("old", "new")}
                             for edit in self.repairs if edit["passage_id"] == pid]
            self.assertEqual([{k: edit[k] for k in ("old", "new")} for edit in plan.get("edits", [])], allowed_edits)
            self.assertFalse(plan.get("typographic_dashes"))
            for omitted in plan["omitted_parts"]:
                self.assertEqual(omitted["kind"], "running_header")
                self.assertEqual(omitted["start"], 0)
                token = source_slice(blocks, omitted)
                self.assertEqual(token, blocks[omitted["block"]].split("\n", 1)[0])
                self.assertEqual(sha(token), omitted["text_sha256"])
                self.assertIn(f"source-page-{omitted['page']}", omitted["evidence"])
                self.assertIn(omitted["source_member"], omitted["evidence"])
                kept[omitted["block"]] = kept[omitted["block"]][omitted["end"]:]
                total += 1
            expected = without_space("\n\n".join(kept))
            for edit in (edit for edit in self.repairs if edit["passage_id"] == pid):
                for page in edit["pages"]:
                    self.assertIn(f"source-page-{page}", edit["evidence"])
                old = without_space(edit.get("source_old", edit["old"]))
                new = without_space(edit.get("source_new", edit["new"]))
                self.assertEqual(expected.count(old), 1, (pid, edit))
                expected = expected.replace(old, new)
            self.assertEqual(without_space(self.corrected[pid]["text"]), expected, pid)
        self.assertEqual(total, 484)
        # The source title remains while the repeated page furniture disappears.
        scene = self.corrected["ga-014-pdf-outline-21-6"]["text"]
        self.assertEqual(scene.count("ERSTES BILD"), 1)
        self.assertNotIn("Die Pforte der Einweihung", scene)
        self.assertNotIn("\nErstes Bild\n", scene)

    def test_actual_song_and_mystery_dialogue_keep_genuine_verse_lines(self):
        prelude = self.corrected["ga-014-pdf-outline-13-5"]
        song = "Der Sonne Licht durchflutet\nDes Raumes Weiten,\nDer Vögel Singen durchhallet"
        self.assertIn(song, prelude["text"])
        song_block = next(b for b in prelude["metadata"]["reading_blocks"] if song in block_text(prelude, b))
        self.assertEqual(song_block["kind"], "verse")
        self.assertEqual(len(block_text(prelude, song_block).splitlines()), 9)
        scene = self.corrected["ga-014-pdf-outline-21-6"]
        verse = "So nahe geht es mir, mein Freund,\nDaß ich dich welken seh' an Geist und Seele."
        self.assertIn(verse, scene["text"])
        maria = next(b for b in scene["metadata"]["reading_blocks"] if verse in block_text(scene, b))
        self.assertEqual(maria["kind"], "verse")
        self.assertIn("Und fruchtlos sehen muß ich auch das schöne Band,\nDas zehen Jahre uns vereint.", block_text(scene, maria))
        self.assertNotIn("[Band,", scene["text"])

    def test_reviewed_verse_repair_requires_its_exact_original_context(self):
        recipe = deepcopy(self.recipe)
        recipe["passages"]["ga-014-pdf-outline-21-6"]["edits"][0]["old"] = "A different unreviewed verse"
        with self.assertRaises(ValueError):
            apply_layout(self.before, recipe)

    def test_all_collated_overruns_are_complete_and_directions_have_correct_roles(self):
        self.assertEqual(self.recipe["review_flags"], [])
        for passage in self.after["passages"]:
            self.assertNotIn("[", passage["text"], passage["id"])
        for repair in self.repairs:
            passage = self.corrected[repair["passage_id"]]
            self.assertEqual(passage["text"].count(repair["new"]), 1, repair)
            original_context = repair.get("source_old", repair["old"])
            if original_context not in repair["new"]:
                self.assertNotIn(original_context, passage["text"])
            if repair.get("source_lines"):
                block = next(b for b in passage["metadata"]["reading_blocks"]
                             if repair["new"] in block_text(passage, b))
                self.assertEqual(block["kind"], "attribution" if repair["kind"] == "speaker_label" else "prose")
                self.assertNotIn("\n", block_text(passage, block))
        # Printed continuation marks can occur above their parent verse, and
        # damaged OCR can lose a whole word while merging the following verse.
        scene = self.corrected["ga-014-pdf-outline-21-6"]["text"]
        self.assertIn("Von Sehergaben durch mich selbst;\nDoch oft, wenn Rätselfragen mich gewaltig quälen,", scene)
        self.assertIn("Ich bin es selbst.\nErkenntnis schmiedet an dich verderblich Ungeheuer",
                      self.corrected["ga-014-pdf-outline-58-7"]["text"])
        self.assertIn("Du gabst mir Kraft, das Menschenleben darzustellen.\nIch konnte schildern, was die Menschen",
                      self.corrected["ga-014-pdf-outline-148-17"]["text"])
        mixed = self.corrected["ga-014-pdf-outline-370-42"]
        self.assertIn("klagen, weinen.\n\n(Geht schnell ab.)", mixed["text"])
        direction = next(b for b in mixed["metadata"]["reading_blocks"]
                         if block_text(mixed, b) == "(Geht schnell ab.)")
        self.assertEqual(direction["kind"], "prose")

    def test_actual_spoken_prose_settings_and_stage_directions_reflow(self):
        prelude = self.corrected["ga-014-pdf-outline-13-5"]
        greeting = "Sei mir gegrüßt, meine liebe Sophie. Ich störe dich doch nicht."
        self.assertIn(greeting, prelude["text"])
        self.assertNotIn("Ich störe dich\ndoch nicht.", prelude["text"])
        greeting_block = next(b for b in prelude["metadata"]["reading_blocks"] if greeting in block_text(prelude, b))
        self.assertEqual(greeting_block["kind"], "prose")
        scene = self.corrected["ga-014-pdf-outline-21-6"]
        setting = next(b for b in scene["metadata"]["reading_blocks"] if block_text(scene, b).startswith("Zimmer in rosenrotem Grundton"))
        self.assertEqual(setting["kind"], "prose")
        self.assertIn("eine jede verweilt noch einige Zeit", block_text(scene, setting))
        self.assertNotIn("\n", block_text(scene, setting))
        fourth = self.corrected["ga-014-pdf-outline-77-9"]
        stage = next(b for b in fourth["metadata"]["reading_blocks"] if block_text(fourth, b).startswith("(Lucifer und Ahriman verschwinden."))
        self.assertEqual(stage["kind"], "prose")
        self.assertIn("Geist der Elemente mit Capesius", block_text(fourth, stage))
        self.assertNotIn("\n", block_text(fourth, stage))
        # Every reviewed prose span is free of physical line wrapping.
        for passage in self.after["passages"]:
            for block in passage["metadata"]["reading_blocks"]:
                if block["kind"] in {"prose", "attribution", "heading"}:
                    self.assertNotIn("\n", block_text(passage, block))

    def test_continuation_across_source_pages_has_no_artificial_stanza(self):
        scene = self.corrected["ga-014-pdf-outline-21-6"]
        seam = "Was Sonnenlicht und Luft,\nDie Körper überflutend\nUnd offenbarend Daseinsrätsel,"
        self.assertIn(seam, scene["text"])
        index, block = next((i, b) for i, b in enumerate(scene["metadata"]["reading_blocks"]) if seam in block_text(scene, b))
        self.assertEqual(block["kind"], "verse")
        self.assertEqual(self.recipe["passages"][scene["id"]]["segments"][index]["source_pdf_pages"][:2], [21, 22])
        # PDF indexes are witness identities; they are never invented printed pages.
        for passage in self.after["passages"]:
            original = self.originals[passage["id"]]
            self.assertEqual(passage["ga_page"], original["ga_page"])
            self.assertEqual(passage["metadata"]["page_numbers"], original["metadata"]["page_numbers"])
            self.assertEqual(passage["metadata"].get("page_anchors"), original["metadata"].get("page_anchors"))

    def test_speaker_labels_remain_attached_and_fused_source_label_is_split(self):
        prelude = self.corrected["ga-014-pdf-outline-13-5"]["text"]
        self.assertIn("SINGEN DER KINDER\n(Sophia begleitet auf dem Klavier):\nDer Sonne Licht durchflutet", prelude)
        self.assertIn("ESTELLA:\nSei mir gegrüßt, meine liebe Sophie.", prelude)
        self.assertIn("MARIA:\nSo nahe geht es mir, mein Freund,", self.corrected["ga-014-pdf-outline-21-6"]["text"])
        interlude = self.corrected["ga-014-pdf-outline-122-13"]
        self.assertIn("in demselben Zimmer wie das Vorspiel.\n\nSOPHIA:\nMeine liebe Estella", interlude["text"])
        self.assertNotIn("VorspielSOPHIA:", interlude["text"])
        sophia = next(b for b in interlude["metadata"]["reading_blocks"] if block_text(interlude, b) == "SOPHIA:")
        self.assertEqual(sophia["kind"], "attribution")

    def test_recipe_slices_belong_to_exact_retained_epub_pages(self):
        if not SOURCE.exists():
            self.skipTest("Local retained GA 014 EPUB witness is not available")
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), self.recipe["source_epub_sha256"])
        witness = {}
        ns = "{http://www.w3.org/1999/xhtml}"
        with ZipFile(SOURCE) as archive:
            for member in archive.namelist():
                if not re.fullmatch(r"EPUB/chapter-\d+\.xhtml", member):
                    continue
                page = None
                for node in ET.fromstring(archive.read(member)).find(ns + "body"):
                    if node.get("id", "").startswith("source-page-"):
                        page = int(node.get("id").rsplit("-", 1)[1])
                    if node.tag == ns + "p" and node.get("class") == "source-lines":
                        text = "\n".join(re.sub(r"[ \t\r\f]+", " ", line).strip() for line in (node.text or "").split("\n")).strip()
                        self.assertNotIn(text, witness, "The source witness must identify a unique page paragraph")
                        witness[text] = {"page": page, "member": member}
        for pid, original in self.originals.items():
            blocks = original["text"].split("\n\n")
            source_pages = [witness[block] for block in blocks]
            plan = self.recipe["passages"][pid]
            self.assertEqual(plan["source_text_sha256"], sha(original["source_text"]))
            for segment in plan["segments"]:
                pages = list(dict.fromkeys(source_pages[part if type(part) is int else part["block"]]["page"] for part in segment["parts"]))
                self.assertEqual(segment["source_pdf_pages"], pages)
                self.assertIn(self.recipe["source_epub_sha256"], segment["source_evidence"])
            for omitted in plan["omitted_parts"]:
                self.assertEqual(omitted["page"], source_pages[omitted["block"]]["page"])
                self.assertEqual(omitted["source_member"], source_pages[omitted["block"]]["member"])

    def test_idempotence_and_edition_or_retained_source_drift_fail_closed(self):
        again, changes = apply_layout(self.after, self.recipe)
        self.assertEqual(again, self.after)
        self.assertEqual(changes, [])
        for version in (self.before, self.after):
            for mutation in ("edition", "text", "source_text", "id", "sequence"):
                payload = deepcopy(version)
                if mutation == "edition":
                    payload["source_epub_sha256"] = "unreviewed edition"
                elif mutation in {"text", "source_text"}:
                    payload["passages"][0][mutation] += " changed"
                elif mutation == "id":
                    payload["passages"][0]["id"] += "-unknown"
                else:
                    payload["passages"].reverse()
                with self.subTest(structured=version is self.after, mutation=mutation), self.assertRaises(ValueError):
                    apply_layout(payload, self.recipe)

    def test_unevidenced_or_expanded_omissions_are_rejected(self):
        pid = "ga-014-pdf-outline-13-5"
        for mutation in ("hash", "evidence", "page", "extent", "kind", "lost", "overlap"):
            recipe = deepcopy(self.recipe)
            plan = recipe["passages"][pid]
            omitted = plan["omitted_parts"][0]
            if mutation == "hash":
                omitted["text_sha256"] = "incorrect"
            elif mutation == "evidence":
                omitted["evidence"] = ""
            elif mutation == "page":
                omitted["page"] = 0
            elif mutation == "extent":
                omitted["end"] += 8
            elif mutation == "kind":
                omitted["kind"] = "arbitrary_text"
            elif mutation == "lost":
                plan["segments"].pop(0)
            else:
                plan["segments"].append(deepcopy(plan["segments"][0]))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                apply_layout(self.before, recipe)

    def test_baseline_preservation_refuses_overwriting_a_different_source(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = Path(directory)
            first_hash = preserve_baseline(self.before, baseline)
            self.assertEqual(preserve_baseline(self.before, baseline), first_hash)
            changed = deepcopy(self.before)
            changed["passages"][0]["source_text"] += " unreviewed"
            with self.assertRaises(ValueError):
                preserve_baseline(changed, baseline)
            self.assertEqual(read_json(baseline / "content/ga-014.json.gz"), self.before)


if __name__ == "__main__":
    unittest.main()
