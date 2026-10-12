#!/usr/bin/env python3
"""Regression checks for incomplete loose-body extraction and reviewed scope."""
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from import_library import read_epub
from import_recovered_volumes import ROOT, adapted_epub, clean_image_placeholders, preserve_loose_text


class RecoveryImportTests(unittest.TestCase):
    def test_image_placeholders_do_not_leak_into_reader_prose(self):
        self.assertEqual(clean_image_placeholders("Vorher\n#Bild s. 41a\n\nNachher"), "Vorher\n\nNachher")
        self.assertEqual(clean_image_placeholders("#Bildnisse sind beschrieben."), "#Bildnisse sind beschrieben.")

    def test_bare_body_prose_and_inline_text_survive(self):
        body = etree.fromstring(b'<body xmlns="http://www.w3.org/1999/xhtml">Opening<h1>Lecture</h1><p>First paragraph</p>Second paragraph<br/>Third paragraph<div>Fourth paragraph<em>Emphasis</em>Final words</div></body>')
        original = "".join(body.itertext())
        preserve_loose_text(body)
        self.assertEqual("".join(body.itertext()), original)
        paragraphs = ["".join(p.itertext()) for p in body.findall('.//{*}p')]
        for text in ["Opening", "Second paragraph", "Third paragraph", "Fourth paragraph", "Emphasis", "Final words"]:
            self.assertIn(text, paragraphs)

    def test_actual_seventh_lecture_reaches_its_final_paragraph(self):
        source = ROOT / "research/unavailable-recovery/education-art/ga-293/GA293.epub"
        if not source.exists():
            self.skipTest("Download recovery sources first")
        with tempfile.TemporaryDirectory() as scratch:
            adapted = Path(scratch) / "ga-293.epub"
            adapted_epub(source, adapted)
            passages, _ = read_epub(adapted, "ga-293", "GA 293", {
                "start": "content18.xhtml#",
                "exclude": ["content220.xhtml#", "content225.xhtml#"],
            })
        self.assertEqual(len(passages), 15)
        self.assertTrue(passages[6]["text"].endswith("zum Erziehen übergeben werden."))
        self.assertGreater(len(passages[6]["text"]), 30000)
        self.assertEqual(len({p["checksum"] for p in passages}), 15)
        self.assertFalse(any("«Allgemeine Menschenkunde», diesen Titel" in p["text"] for p in passages))
        self.assertFalse(any("ANMERKUNGEN ZU DIESER AUSGABE" in p["title"] for p in passages))


if __name__ == "__main__":
    unittest.main()
