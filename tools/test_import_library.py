#!/usr/bin/env python3
"""Source-fidelity regressions for the EPUB-to-native adapter (requires lxml)."""
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from import_library import canonical_id, read_epub, text_of
from lxml import etree


class EPUBImportTests(unittest.TestCase):
    def epub(self, bodies, stylesheet=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "source.epub"
        with ZipFile(path, "w") as archive:
            archive.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="EPUB/package.opf"/></rootfiles></container>')
            manifest = ''.join(f'<item id="c{i}" href="chapter-{i}.xhtml"/>' for i in range(len(bodies)))
            spine = ''.join(f'<itemref idref="c{i}"/>' for i in range(len(bodies)))
            archive.writestr("EPUB/package.opf", f'<package><manifest>{manifest}</manifest><spine>{spine}</spine></package>')
            if stylesheet is not None:
                archive.writestr("EPUB/styles.css", stylesheet)
            for i, body in enumerate(bodies):
                head = '<head><link rel="stylesheet" href="styles.css"/></head>' if stylesheet is not None else ''
                archive.writestr(f"EPUB/chapter-{i}.xhtml", f'<html xmlns="http://www.w3.org/1999/xhtml">{head}<body>{body}</body></html>')
        return path

    def test_original_prose_survives_notes_pages_and_spine_continuations(self):
        path = self.epub([
            '<p>Verlag und ISBN</p><h2 id="one">Erster Vortrag</h2>'
            '<p>Äußere Welt<span data-page-label="15" data-page-kind="page">15</span> und Freiheit. '
            '<a href="#author">(1)</a><a href="#editorial">(2)</a>'
            '<a href="#editorial" data-note-ref-kind="quotation">Dieser Originalsatz bleibt.</a></p>'
            '<p id="author" role="doc-footnote">(1) Eine Anmerkung des Autors.</p>'
            '<p id="editorial" role="doc-footnote" data-note-editorial="true">Moderne Herausgebernotiz.</p>'
            '<p>Unverändert nach den Anmerkungen.</p>',
            '<h2 class="continuation-heading">Fortsetzung</h2><p>Fortsetzung ohne neues Kapitel.</p>'
            '<h2 id="notes">Hinweise</h2><p>Verlagsapparat.</p>',
        ])
        passages, audit = read_epub(path, "ga-120", "Karma")
        self.assertEqual(len(passages), 1)
        passage = passages[0]
        self.assertIn("Äußere Welt und Freiheit.", passage["text"])
        self.assertIn("Dieser Originalsatz bleibt.", passage["text"])
        self.assertIn("Fortsetzung ohne neues Kapitel.", passage["text"])
        self.assertNotIn("Moderne Herausgebernotiz", passage["text"])
        self.assertNotIn("Verlag", passage["text"])
        self.assertNotIn("(2)", passage["text"])
        self.assertEqual(passage["metadata"]["page_numbers"], [15])
        self.assertEqual(passage["metadata"]["annotations"][0]["marker"], "(1)")
        self.assertIn("Unverändert nach den Anmerkungen.", passage["source_text"])
        self.assertNotIn("Moderne Herausgebernotiz", passage["source_text"])
        self.assertTrue(audit["excluded_sections"])

    def test_exact_start_keeps_unheaded_author_preface_and_skips_named_third_party(self):
        path = self.epub([
            '<h2 id="marie">Vorwort von Marie Steiner</h2><p>Fremdes Vorwort.</p>'
            '<p>AUS DER VORREDE ZUR FÜNFTEN AUFLAGE<br/>Steiners eigener Text.</p>'
            '<h2 id="imagination">Die Imagination</h2><p>Original.</p>'
            '<p>Aus dem Nachwort von Marie Steiner (1931)</p><p>Fremdes Nachwort.</p>',
        ])
        passages, _ = read_epub(path, "ga-012", "Stufen", {"start_text": "AUS DER VORREDE ZUR FÜNFTEN AUFLAGE", "exclude_texts": ["Aus dem Nachwort von Marie Steiner (1931)"]})
        text = "\n".join(p["text"] for p in passages)
        self.assertIn("Steiners eigener Text.", text)
        self.assertIn("Original.", text)
        self.assertNotIn("Fremdes", text)

    def test_collapsed_source_macros_preserve_the_first_original_sentence(self):
        element = etree.fromstring('<p>#G272-1959-SE001 - Title #TI VORWORT #TX Äußere Erkenntnis bleibt. #SE272-002 Weiter.</p>')
        self.assertEqual(text_of(element), "Äußere Erkenntnis bleibt. Weiter.")

    def test_html_source_wrapping_is_not_a_verse_break(self):
        element = etree.fromstring(
            '<p xmlns="http://www.w3.org/1999/xhtml">\n'
            '<span>So\nfinde im Niedergang<br/>\n</span>'
            '<span>Und\nin des Todes Nacht<br/>\n</span>'
            '<span>Der\nSchöpfung neuen Anfang,</span></p>'
        )
        self.assertEqual(
            text_of(element),
            "So finde im Niedergang\nUnd in des Todes Nacht\nDer Schöpfung neuen Anfang,",
        )
        # Extraction must leave the source tree untouched for provenance.
        self.assertIn("So\nfinde", "".join(element.itertext()))

    def test_paragraphs_and_stanzas_keep_distinct_boundaries(self):
        path = self.epub([
            '<h2 id="verse">Wintersonnenwende</h2>'
            '<p>So\nfinde im Niedergang<br/>\nUnd\nin des Todes Nacht</p>'
            '<p>Die\nHöhen laß offenbaren<br/>\nDer\nGötter ewiges Wort;</p>',
        ])
        passages, _ = read_epub(path, "ga-040", "Wahrspruchworte")
        self.assertEqual(passages[0]["id"], "ga-040-verse")
        self.assertEqual(
            passages[0]["text"],
            "So finde im Niedergang\nUnd in des Todes Nacht\n\n"
            "Die Höhen laß offenbaren\nDer Götter ewiges Wort;",
        )
        self.assertIn("So\nfinde", passages[0]["source_text"])

    def test_preserves_literal_pre_xml_space_and_inline_css(self):
        for markup in (
            '<pre>  Erste  Zeile\n    Zweite\n\n\nDritte  </pre>',
            '<p xml:space="preserve">  Erste  Zeile\n    Zweite\n\n\nDritte  </p>',
            '<p style="white-space: pre-wrap">  Erste  Zeile\n    Zweite\n\n\nDritte  </p>',
        ):
            with self.subTest(markup=markup):
                self.assertEqual(text_of(etree.fromstring(markup)), "  Erste  Zeile\n    Zweite\n\n\nDritte  ")
        element = etree.fromstring(
            '<p>Normal\n<span style="white-space: pre">  wörtlich\n  eingerückt</span>'
            '<span>\nweiter.</span></p>'
        )
        self.assertEqual(text_of(element), "Normal   wörtlich\n  eingerückt weiter.")

    def test_pre_line_collapses_spaces_but_preserves_lines(self):
        element = etree.fromstring('<p style="white-space: pre-line"> Eine  Zeile\n  Zweite  Zeile </p>')
        self.assertEqual(text_of(element), "Eine Zeile\nZweite Zeile")

    def test_block_inherits_whitespace_and_can_reset_it(self):
        root = etree.fromstring(
            '<div style="white-space: pre-wrap"><p>  A\n    B  </p>'
            '<p style="white-space: normal">  A\n    B  </p></div>'
        )
        self.assertEqual(text_of(root[0]), "  A\n    B  ")
        self.assertEqual(text_of(root[1]), "A B")

    def test_full_passage_preserves_pre_indentation_and_tidy_page_removal(self):
        path = self.epub([
            '<h2 id="literal">Wörtlicher Satz</h2>'
            '<pre>  Erste  Zeile\n    Zweite\n\n\nDritte  </pre>'
            '<p>[15] Normaler [16] Text. [17]</p>',
        ])
        passages, _ = read_epub(path, "ga-040", "Wahrspruchworte")
        self.assertEqual(
            passages[0]["text"],
            "  Erste  Zeile\n    Zweite\n\n\nDritte  \n\nNormaler Text.",
        )
        self.assertEqual(passages[0]["metadata"]["page_numbers"], [15, 16, 17])

    def test_source_lines_stylesheet_preserves_lines_and_css_specificity(self):
        path = self.epub([
            '<h2 id="verse">Gedicht</h2>'
            '<p class="source-lines">Erste  Zeile\n   Zweite Zeile</p>'
            '<p id="prose" class="source-lines">Normaler\nFließtext.</p>'
            '<p class="source-lines" style="white-space:normal">Inline\nFließtext.</p>',
        ], stylesheet='.source-lines {white-space:pre-line} p#prose {white-space:normal}')
        passages, audit = read_epub(path, "ga-040", "Wahrspruchworte")
        self.assertEqual(passages[0]["text"], "Erste Zeile\nZweite Zeile\n\nNormaler Fließtext.\n\nInline Fließtext.")
        self.assertNotIn("whitespace_warnings", audit)

    def test_tag_css_inheritance_and_important_precedence(self):
        path = self.epub([
            '<h2 id="verse">Gedicht</h2>'
            '<p>  Erste\n  Zweite  </p>'
            '<p class="collapse" style="white-space:pre-wrap">Normaler\nText.</p>'
            '<p class="collapse" style="white-space:pre-wrap !important">  Wörtlich\n  Weiter </p>',
        ], stylesheet='body {white-space:pre-wrap} .collapse {white-space:normal !important}')
        passages, audit = read_epub(path, "ga-040", "Wahrspruchworte")
        self.assertEqual(passages[0]["text"], "  Erste\n  Zweite  \n\nNormaler Text.\n\n  Wörtlich\n  Weiter ")
        self.assertNotIn("whitespace_warnings", audit)

    def test_unsupported_whitespace_selector_is_reported(self):
        path = self.epub(['<h2 id="one">Text</h2><p>Ein\nSatz.</p>'], stylesheet='p:first-child {white-space:pre-line}')
        _, audit = read_epub(path, "ga-040", "Wahrspruchworte")
        self.assertIn("nicht unterstützter white-space-Selektor", audit["whitespace_warnings"][0])

    def test_source_macro_header_lines_remain_separate_until_removed(self):
        element = etree.fromstring('<p>#G272-1959-SE001 - Title\nÄußere Erkenntnis\nbleibt.</p>')
        self.assertEqual(text_of(element), "Äußere Erkenntnis bleibt.")
        element = etree.fromstring('<p style="white-space:pre-line">#G272-1959-SE001 - Title\nÄußere Erkenntnis\nbleibt.</p>')
        self.assertEqual(text_of(element), "Äußere Erkenntnis\nbleibt.")

    def test_page_macro_stops_at_explicit_or_preserved_line_boundary(self):
        for markup, expected in (
            ('<p>#SE561<br/>§ 3 bleibt.</p>', "§ 3 bleibt."),
            ('<p>#SE260a-s646<br/>August 1924 bleibt.</p>', "August 1924 bleibt."),
            ('<p style="white-space:pre-line">#SE561\n§ 3 bleibt.</p>', "§ 3 bleibt."),
            ('<p>#SE561<span xml:space="preserve">August 1924 bleibt.</span></p>', "August 1924 bleibt."),
        ):
            with self.subTest(markup=markup):
                self.assertEqual(text_of(etree.fromstring(markup)), expected)

    def test_ids_preserve_numeric_parts_and_art_catalog_rows(self):
        self.assertEqual(canonical_id("38/1"), "ga-038-1")
        self.assertEqual(canonical_id("1a-e"), "ga-001a-e")
        self.assertEqual(canonical_id("K 1–10; 57", "ga-k-1-10-57"), "ga-k-1-10-57")
        with self.assertRaises(ValueError):
            canonical_id("../1")


if __name__ == "__main__":
    unittest.main()
