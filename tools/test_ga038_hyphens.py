#!/usr/bin/env python3
"""Focused guards for frozen GA038 hyphen corrections and fresh stages."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from finalize_library import read_json, write_json
import repair_ga038_hyphens as repair


class GA038HyphenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "original.epub"
        self.baseline = self.root / "baseline"
        xml = ('<html xmlns="http://www.w3.org/1999/xhtml"><body>'
               '<p>\nNational-Lite-ratur und Thea-\ntern; schik-ken, entwik-keln.</p>'
               '<p>National-\n\nLiteratur und Ja-\nFalle.</p>'
               '<p>Eine Ausgabe hin-\nMit hochachtungsvollstem Gruß.</p>'
               '<p>Eine Arbeit unterzubrin-\nEin weiterer Absatz.</p>'
               '</body></html>').encode()
        self.member = "EPUB/chapter-0001.xhtml"
        with ZipFile(self.source, "w") as archive:
            archive.writestr(self.member, xml)
        atom = ET.fromstring(xml).find("{http://www.w3.org/1999/xhtml}body")[0]
        self.witness = {"source_member": self.member, "body_index": 0, "child_path": [],
            "source_paragraph_sha256": repair.sha("".join(atom.itertext())),
            "member_sha256": repair.digest(xml)}
        text = "National-Lite-ratur und National-Literatur.\n\nGeist- und Kulturleben. Thea- tern."
        self.before = {"work_id": "ga-038", "source_sha256": "original-doc-sha",
            "source_epub_sha256": repair.digest(self.source.read_bytes()),
            "title": "Originaltitel", "metadata": {"unchanged": {"nested": [1, 2]}},
            "content_completeness": "complete", "passage_count": 2,
            "passages": [self.passage("ga-038-doc-heading-73", text),
                         self.passage("ga-038-doc-heading-74", "Unveränderter Absatz.\n\nNoch ein Absatz.")]}
        self.review = self.make_review(self.before, [self.entry("national", "National-Lite-ratur", "National-Literatur"),
                                                   self.entry("theater", "Thea- tern", "Theatern")])
        repair.preserve_baseline(self.before, self.baseline)
        self.addCleanup(patch.stopall)
        patch.object(repair, "SOURCE", self.source).start()
        patch.object(repair, "BASELINE", self.baseline).start()

    @staticmethod
    def passage(pid, text):
        return {"id": pid, "title": "Belegter Titel", "text": text, "source_text": "Original " + text,
                "checksum": repair.sha(text), "ga_page": "S. 1", "source_member": "original",
                "metadata": {"page_numbers": [1], "page_marker_source": "original",
                             "annotations": [{"id": "note", "marker": "*", "text": "Eine\nFußnote ↩"}]}}

    def entry(self, rid, old, new, *, kind="physical_word_hyphen"):
        return {"id": rid, "passage_id": "ga-038-doc-heading-73", "field": "text",
                "kind": kind, "old": old, "new": new, "count": 1,
                "source_witnesses": [deepcopy(self.witness)],
                "source_pdf_pages": [12], "evidence": "Originaldruck: exakt belegte physische Worttrennung"}

    def make_review(self, before, entries):
        plans = {}
        for passage in before["passages"]:
            text = passage["text"]
            for entry in entries:
                if entry["passage_id"] == passage["id"]:
                    text = repair.word_pattern(entry["old"]).sub(lambda match: entry["new"], text)
            plans[passage["id"]] = {"input_sha256": repair.sha(passage["text"]),
                "source_text_sha256": repair.sha(passage["source_text"]), "output_sha256": repair.sha(text)}
        return {"work_id": "ga-038", "source_sha256": before["source_sha256"],
                "source_epub_sha256": before["source_epub_sha256"], "input_passages": plans, "repairs": entries}

    def test_exact_inline_and_physical_seams_preserve_other_content(self):
        original = deepcopy(self.before)
        after, events = repair.apply_review(self.before, self.review)
        self.assertEqual(self.before, original)
        self.assertIn("National-Literatur und National-Literatur.", after["passages"][0]["text"])
        self.assertIn("\n\nGeist- und Kulturleben. Theatern.", after["passages"][0]["text"])
        for before, final in zip(self.before["passages"], after["passages"]):
            self.assertEqual({k:v for k,v in before.items() if k not in ("text", "checksum")},
                             {k:v for k,v in final.items() if k not in ("text", "checksum")})
            self.assertEqual(final["text"].count("\n\n"), before["text"].count("\n\n"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["rule"], "source_hyphen_repair")
        self.assertEqual(events[0]["count"], 2)
        self.assertEqual(events[0]["replacements"], self.review["repairs"])
        self.assertEqual(events[0]["input_sha256"], self.before["passages"][0]["checksum"])
        self.assertEqual(events[0]["output_sha256"], after["passages"][0]["checksum"])

    def test_word_boundaries_do_not_match_other_compounds_or_longer_words(self):
        pattern = repair.word_pattern("National-Lite-ratur")
        self.assertEqual(len(pattern.findall("National-Lite-ratur, National-Lite-ratur!")), 2)
        for text in ("VorNational-Lite-ratur", "National-Lite-raturen", "Andere-National-Lite-ratur"):
            self.assertFalse(pattern.search(text))

    def test_double_application_requires_and_preserves_original_metadata(self):
        after, _ = repair.apply_review(self.before, self.review)
        again, events = repair.apply_review(after, self.review)
        self.assertEqual(again, after)
        self.assertEqual(events, [])
        for mutate in (lambda p:p["passages"][0].update(title="Fremder Titel"),
                       lambda p:p["passages"][0]["metadata"].update(page_numbers=[999]),
                       lambda p:p["passages"][0]["metadata"]["annotations"][0].update(text="Fremde Fußnote"),
                       lambda p:p["metadata"].update(unchanged={})):
            bad = deepcopy(after); mutate(bad)
            with self.assertRaises(ValueError): repair.apply_review(bad, self.review)

    def test_wrong_counts_inventory_checksums_and_sources_are_rejected(self):
        for mutation in (lambda r:r["repairs"][0].update(count=2),
                         lambda r:r["repairs"][0].update(count=True),
                         lambda r:r["repairs"][0].update(passage_id="foreign"),
                         lambda r:r["repairs"][1].update(id="national"),
                         lambda r:r.update(source_epub_sha256="wrong"),
                         lambda r:r.update(source_sha256="wrong"),
                         lambda r:r["repairs"][0]["source_witnesses"][0].update(source_paragraph_sha256="wrong"),
                         lambda r:r["repairs"][0]["source_witnesses"][0].update(member_sha256="wrong"),
                         lambda r:r["input_passages"]["ga-038-doc-heading-74"].update(output_sha256="wrong")):
            bad = deepcopy(self.review); mutation(bad)
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError): repair.apply_review(self.before, bad)
        for mutation in (lambda p:p["passages"].reverse(),
                         lambda p:p["passages"][1].update(checksum="wrong"),
                         lambda p:p["passages"][0].update(source_text="changed")):
            bad = deepcopy(self.before); mutation(bad)
            with self.assertRaises(ValueError): repair.apply_review(bad, self.review)

    def test_only_original_literal_can_be_repaired_and_letters_cannot_change(self):
        for old, new in (("National-Lite-ratur", "National-Literaturen"),
                         ("National-Lite-ratur", "NationalLiteraturZ"),
                         ("National-Lite-ratur", "NationaL-Literatur"),
                         ("National-Lite-ratur", "National-Lit-eratur"),
                         ("Foreign-Wort", "ForeignWort")):
            bad = deepcopy(self.review);bad["repairs"][0].update(old=old,new=new)
            with self.assertRaises(ValueError): repair.apply_review(self.before, bad)

    def test_original_ocr_glyphs_are_retained_without_spelling_changes(self):
        for old,new in (("Philo-s[ophischen]","Philos[ophischen]"),
                        ("Anerken-\n\nnun§","Anerkennun§"),("j\\t-chivarbeit","j\\tchivarbeit")):
            repair.validate_replacement(self.entry("glyphs",old,new))
        for old,new in (("Philo-s[ophischen]","Philosophischen"),
                        ("Anerken-\n\nnun§","Anerkennung"),("j\\t-chivarbeit","Archivarbeit")):
            with self.assertRaises(ValueError):repair.validate_replacement(self.entry("glyphs",old,new))

    def test_historical_ck_exception_is_exactly_one_k_k_seam(self):
        before = deepcopy(self.before)
        before["passages"][0].update(text="schik-ken und entwik-keln.")
        before["passages"][0]["checksum"] = repair.sha(before["passages"][0]["text"])
        entries = [self.entry("ck1", "schik-ken", "schicken", kind="historical_ck_hyphen"),
                   self.entry("ck2", "entwik-keln", "entwickeln", kind="historical_ck_hyphen")]
        review = self.make_review(before, entries)
        final, _ = repair.apply_review(before, review)
        self.assertEqual(final["passages"][0]["text"], "schicken und entwickeln.")
        for old, new, kind in (("schik-ken", "schicken", "physical_word_hyphen"),
                               ("schik-ken", "schikken", "historical_ck_hyphen"),
                               ("schik-ken", "schiCken", "historical_ck_hyphen"),
                               ("National-Lite-ratur", "National-Literatur", "historical_ck_hyphen"),
                               ("schik-kenschik-ken", "schickenschicken", "historical_ck_hyphen")):
            with self.assertRaises(ValueError): repair.validate_replacement(self.entry("bad",old,new,kind=kind))

    def test_only_two_lexical_hyphen_gaps_keep_their_exact_hyphen(self):
        kind="physical_gap_after_lexical_hyphen"
        for old,new in (("National-\n\nLiteratur","National-Literatur"),("Ja-\nFalle","Ja-Falle")):
            repair.validate_replacement(self.entry("gap",old,new,kind=kind))
            self.assertEqual(repair.word_pattern(old).sub(lambda match:new,old),new)
        for old,new in (("National- Literatur","National-Literatur"),
                        ("National-\nLiteratur","NationalLiteratur"),
                        ("Ja-\nFalle","Ja-Fällen"),
                        ("Geist-\nWesen","Geist-Wesen")):
            with self.assertRaises(ValueError):repair.validate_replacement(self.entry("gap",old,new,kind=kind))
        with ZipFile(self.source) as archive:
            atom=ET.fromstring(archive.read(self.member)).find("{http://www.w3.org/1999/xhtml}body")[1]
        witness=deepcopy(self.witness);witness.update(body_index=1,source_paragraph_sha256=repair.sha("".join(atom.itertext())))
        before=deepcopy(self.before)
        text="Erster Absatz.\n\nNational-\n\nLiteratur und Ja-\nFalle.\n\nLetzter Absatz."
        before["passages"][0].update(text=text,checksum=repair.sha(text))
        entries=[self.entry("national-gap","National-\n\nLiteratur","National-Literatur",kind=kind),
                 self.entry("ja-gap","Ja-\nFalle","Ja-Falle",kind=kind)]
        for entry in entries:entry["source_witnesses"]=[witness]
        after,_=repair.apply_review(before,self.make_review(before,entries))
        self.assertEqual(after["passages"][0]["text"],"Erster Absatz.\n\nNational-Literatur und Ja-Falle.\n\nLetzter Absatz.")

    def continuation_entry(self,pid,old,new,page,missing,index):
        entry=self.entry("continuation-"+str(page),old,new,kind="source_word_continuation")
        with ZipFile(self.source) as archive:
            atom=ET.fromstring(archive.read(self.member)).find("{http://www.w3.org/1999/xhtml}body")[index]
        witness=deepcopy(self.witness);witness.update(body_index=index,source_paragraph_sha256=repair.sha("".join(atom.itertext())))
        entry.update(passage_id=pid,source_witnesses=[witness],pdf_line_pair_witnesses=[],
            continuation_witness={"page":page,"missing_text":missing,"reviewed":True,
                "previous_line":{"pdf_page":page,"line_index":31,"text":"Belegte Druckvorzeile "+old,
                                 "bbox_pt":[80,650,500,664]},
                "missing_line_bbox_pt":[80,665,140,680],"hand_transcribed_lines":["Belegte Druckvorzeile "+old,missing]},
            pdf_raster_witnesses=[{"pdf_page":page,"page_index":page-1,"original_pdf_sha256":"a"*64,
                                  "original_page_mode":"1","original_page_size":[2483,3302],
                                  "visible_page_pixels_sha256":"b"*64}])
        return entry

    def test_two_missing_original_continuations_preserve_sources_and_paragraphs(self):
        before=deepcopy(self.before)
        before["passages"]=[self.passage("ga-038-doc-heading-10","Eine Ausgabe hin-\n\nMit hochachtungsvollstem Gruß."),
                            self.passage("ga-038-doc-heading-51","Eine Arbeit unterzubrin-\n\nEin weiterer Absatz.")]
        entries=[self.continuation_entry("ga-038-doc-heading-10","hin-","hinlenkten?",66,"lenkten?",2),
                 self.continuation_entry("ga-038-doc-heading-51","unterzubrin-","unterzubringen sein.",189,"gen sein.",3)]
        review=self.make_review(before,entries)
        after,events=repair.apply_review(before,review)
        self.assertEqual(after["passages"][0]["text"],"Eine Ausgabe hinlenkten?\n\nMit hochachtungsvollstem Gruß.")
        self.assertEqual(after["passages"][1]["text"],"Eine Arbeit unterzubringen sein.\n\nEin weiterer Absatz.")
        for a,b in zip(before["passages"],after["passages"]):
            self.assertEqual(a["source_text"],b["source_text"])
            self.assertEqual(a["metadata"],b["metadata"])
            self.assertEqual(a["text"].count("\n\n"),b["text"].count("\n\n"))
        self.assertEqual(len(events),2)
        with tempfile.TemporaryDirectory() as tmp:
            baseline=Path(tmp);repair.preserve_baseline(before,baseline)
            with patch.object(repair,"BASELINE",baseline):
                again,changes=repair.apply_review(after,review)
            self.assertEqual(again,after);self.assertEqual(changes,[])

    def test_missing_continuation_guard_rejects_any_other_addition_or_witness(self):
        original=self.continuation_entry("ga-038-doc-heading-10","hin-","hinlenkten?",66,"lenkten?",2)
        mutations=(lambda e:e.update(passage_id="ga-038-doc-heading-51"),
                   lambda e:e.update(old="her-"),lambda e:e.update(new="hinlenken?"),
                   lambda e:e.update(count=2),lambda e:e.update(field="source_text"),
                   lambda e:e["continuation_witness"].update(page=67),
                   lambda e:e["continuation_witness"].update(missing_text="lenken?"),
                   lambda e:e["continuation_witness"].update(reviewed=False),
                   lambda e:e["continuation_witness"]["previous_line"].update(text="Eine fremde Druckzeile"),
                   lambda e:e.update(pdf_line_pair_witnesses=[{}]),lambda e:e.update(pdf_raster_witnesses=[]),
                   lambda e:e["pdf_raster_witnesses"][0].update(pdf_page=67))
        for mutate in mutations:
            bad=deepcopy(original);mutate(bad)
            with self.assertRaises(ValueError):repair.validate_replacement(bad)

    def stage_input(self):
        priv = self.root / "priv"
        for name in ("content", "library", "proofreading/works"):
            (priv / name).mkdir(parents=True)
        payloads = [deepcopy(self.before)]
        other = deepcopy(self.before);other.update(work_id="ga-039",passage_count=1)
        other["passages"] = [self.passage("other", "Ein anderer Band.")];payloads.append(other)
        works = []
        for payload in payloads:
            wid = payload["work_id"];path=priv / "content" / (wid + ".json.gz")
            write_json(path,payload)
            works.append({"id":wid,"content_path":"content/"+path.name,
                "passages":[{k:p[k] for k in ("id","title","ga_page","checksum")} for p in payload["passages"]]})
            write_json(priv / "proofreading/works" / (wid+".json"),
                {"work":{"id":wid,"available":True,"after_sha256":repair.digest(path.read_bytes()),
                         "before_sha256":repair.digest(path.read_bytes()),"newlines_removed":0,
                         "passage_count":len(payload["passages"]),"checks":[]},"changes":[],"flags":[]})
        write_json(priv / "library/catalog.json",{"works":works})
        write_json(priv / "proofreading/catalog.json",{"generated_at":"original-date"})
        return priv

    def test_fresh_stage_hashes_catalog_and_other_band_preservation(self):
        priv = self.stage_input();output=self.root / "stage"
        before = (priv / "content/ga-038.json.gz").read_bytes()
        other = (priv / "content/ga-039.json.gz").read_bytes()
        # Identical JSON can have different gzip headers; the retained input
        # byte hash must never replace the current application's byte hash.
        baseline_path=self.baseline / "content/ga-038.json.gz"
        gzip_bytes=bytearray(baseline_path.read_bytes());gzip_bytes[9]^=1
        baseline_path.write_bytes(gzip_bytes)
        with redirect_stdout(io.StringIO()):
            events = repair.stage(priv,output,self.review,self.baseline)
        self.assertEqual((priv / "content/ga-038.json.gz").read_bytes(), before)
        self.assertEqual((output / "content/ga-039.json.gz").read_bytes(), other)
        payload=read_json(output / "content/ga-038.json.gz")
        detail=read_json(output / "proofreading/works/ga-038.json")
        self.assertEqual(detail["work"]["application_base_sha256"],repair.digest(before))
        self.assertEqual(detail["work"]["ga038_hyphen_input_sha256"],repair.digest((self.baseline / "content/ga-038.json.gz").read_bytes()))
        self.assertNotEqual(detail["work"]["application_base_sha256"],detail["work"]["ga038_hyphen_input_sha256"])
        self.assertEqual(detail["work"]["after_sha256"],repair.digest((output / "content/ga-038.json.gz").read_bytes()))
        self.assertEqual(detail["changes"],events)
        catalog=read_json(output / "library/catalog.json")
        self.assertEqual([p["checksum"] for p in catalog["works"][0]["passages"]],[p["checksum"] for p in payload["passages"]])
        with redirect_stdout(io.StringIO()):
            repeated=repair.stage(output,self.root / "repeat",self.review,self.baseline)
        self.assertEqual(repeated,[])
        self.assertEqual((output / "content/ga-038.json.gz").read_bytes(),(self.root / "repeat/content/ga-038.json.gz").read_bytes())
        with self.assertRaises(ValueError): repair.stage(priv,output,self.review,self.baseline)
        gzip_bytes[9]^=2;baseline_path.write_bytes(gzip_bytes)
        with self.assertRaises(ValueError):repair.stage(output,self.root / "baseline-drift",self.review,self.baseline)
        self.assertFalse((self.root / "baseline-drift").exists())

    def test_ledger_and_preserved_baseline_byte_guards(self):
        priv=self.stage_input();path=priv / "proofreading/works/ga-038.json"
        d=read_json(path);d["work"]["after_sha256"]="wrong";write_json(path,d)
        with self.assertRaises(ValueError): repair.stage(priv,self.root / "bad",self.review,self.baseline)
        self.assertFalse((self.root / "bad").exists())
        with self.assertRaises(ValueError): repair.preserve_baseline({"foreign":True},self.baseline)


class GA038ActualReviewTests(unittest.TestCase):
    def test_frozen_actual_review_preserves_sources_and_is_idempotent(self):
        if not repair.REVIEW.exists() or not (repair.BASELINE / "content/ga-038.json.gz").exists():
            self.skipTest("Original GA038 review/baseline is not frozen yet")
        review=read_json(repair.REVIEW);before=read_json(repair.BASELINE / "content/ga-038.json.gz")
        after,events=repair.apply_review(before,review)
        self.assertEqual(len(before["passages"]),49)
        self.assertEqual([p["id"] for p in before["passages"]],[p["id"] for p in after["passages"]])
        for original,final in zip(before["passages"],after["passages"]):
            self.assertEqual({k:v for k,v in original.items() if k not in ("text","checksum")},
                             {k:v for k,v in final.items() if k not in ("text","checksum")})
        self.assertEqual(sum(e["count"] for e in events),sum(r["count"] for r in review["repairs"]))
        self.assertNotIn("National-Lite-ratur",next(p for p in after["passages"] if p["id"]=="ga-038-doc-heading-73")["text"])
        again,events=repair.apply_review(after,review)
        self.assertEqual(again,after);self.assertEqual(events,[])


if __name__ == "__main__":
    unittest.main()
