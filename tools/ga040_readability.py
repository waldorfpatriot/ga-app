#!/usr/bin/env python3
"""Reflow only source-reviewed prose in GA 040, preserving its mixed verses.

Call after source-aware extraction and evidenced word dehyphenation. These
boundaries were checked against the SHA-bound 1991 source EPUB; they are not a
general detector for poetry. The caller must verify the EPUB provenance first.
Run this file with --self-test for the focused boundary/guard regressions.
"""
from __future__ import annotations

import argparse
import re
import unittest


PREFIXES = {
    "ga-040-doc-heading-2": ("Mit der Welt und ihrem", "FRÜHLING", "1 Wenn aus den Weltenweiten"),
    "ga-040-doc-heading-6": ("Ich möchte nur vorausbemerken", "PLANETENTANZ", "Es leuchtet die Sonne -"),
}
WHOLE_PROSE = {
    "ga-040-doc-heading-5": "Von den Dichtungen",
    "ga-040-doc-heading-7": "Die «Wahrspruchworte - Richtspruchworte»",
    "ga-040-doc-heading-28": "Die Sprüche und Widmungen sind",
    "ga-040-doc-heading-40": "Das handgeschriebene Originalmanuskript",
    "ga-040-doc-heading-41": "Die Ideenwelt ist der Urquell",
}
SINGLE_NEWLINE = re.compile(r"(?<!\n)\n(?!\n)")
CALENDAR_HEADING = re.compile(
    r"^(?:(?:Erste|Zweite|Dritte|Vierte|Fünfte)\b.*-Woche\b|"
    r"(?:Oster|Johanni|Michaeli|Weihe-Nacht)-Stimmung\b|Frühling-Erwartung\b)"
)
CALENDAR_START = re.compile(r"^(5 2|[1-9]\d?) (?=[A-ZÄÖÜ])")
# Bound source's 52 complete poems; rendered 1998 pages 23, 34 and 48
# corroborate contiguous stanza lines, separated from dates and other poems.
CALENDAR_LINE_COUNTS = (
    8, 7, 7, 8, 7, 7, 7, 8, 7, 8, 6, 7, 6, 6, 7, 5, 6, 6,
    6, 5, 5, 7, 8, 6, 7, 6, 6, 7, 6, 8, 7, 5, 6, 6, 6, 6,
    6, 7, 6, 5, 6, 6, 6, 5, 8, 7, 5, 6, 6, 7, 6, 7,
)


def reflow_confirmed_ga040_prose(passage_id: str, text: str) -> tuple[str, int]:
    """Return readable prose and the number of printed line wraps removed.

    Real paragraph boundaries (double LF) and all text after the mixed-section
    verse heading remain exactly as received. Fail closed if a reviewed source
    boundary or opening has changed, rather than reflowing an unknown edition.
    """
    if passage_id in PREFIXES:
        opening, heading, verse_opening = PREFIXES[passage_id]
        if not SINGLE_NEWLINE.sub(" ", text).startswith(opening):
            raise ValueError(f"GA 040 prose opening changed: {passage_id}")
        boundary = f"\n\n{heading}\n\n"
        if text.count(boundary) != 1:
            raise ValueError(f"GA 040 prose/verse boundary changed: {passage_id}")
        prose, separator, verse = text.partition(boundary)
        if verse_opening not in verse[:400]:
            raise ValueError(f"GA 040 first verse changed: {passage_id}")
        reflowed, count = SINGLE_NEWLINE.subn(" ", prose)
        return reflowed + separator + verse, count
    if passage_id in WHOLE_PROSE:
        if not SINGLE_NEWLINE.sub(" ", text).startswith(WHOLE_PROSE[passage_id]):
            raise ValueError(f"GA 040 prose opening changed: {passage_id}")
        return SINGLE_NEWLINE.subn(" ", text)
    return text, 0


def join_confirmed_calendar_stanzas(passage_id: str, text: str) -> tuple[str, int]:
    """Remove blank lines inside the 52 reviewed weekly calendar stanzas.

    Keep each existing verse LF, each date/season heading and each inter-poem
    boundary. The source alternates <p> per verse with <br> inside stanzas.
    Recognize the source OCR numeral '5 2' without changing its text.
    """
    if passage_id != "ga-040-doc-heading-2":
        return text, 0
    boundary = "\n\nFRÜHLING\n\n"
    if text.count(boundary) != 1:
        raise ValueError("GA 040 calendar start changed")
    preface, separator, calendar = text.partition(boundary)
    result, poem_parts, numbers, seasons = [], [], [], []
    current = None
    changed, headings = 0, 0

    def flush():
        nonlocal current, changed
        if current is None:
            return
        poem = "\n".join(poem_parts)
        if len(poem.splitlines()) != CALENDAR_LINE_COUNTS[current - 1]:
            raise ValueError(f"GA 040 calendar verse extent changed: {current}")
        result.append(poem)
        changed += len(poem_parts) - 1
        poem_parts.clear()
        current = None

    for block in calendar.split("\n\n"):
        season = block in {"SOMMER", "HERBST", "WINTER"}
        date = bool(CALENDAR_HEADING.match(block)) and "\n" not in block
        if season or date:
            flush()
            result.append(block)
            if season:
                seasons.append(block)
            else:
                headings += 1
            continue
        start = CALENDAR_START.match(block)
        if start:
            number = int(start[1].replace(" ", ""))
            if current is not None or number != len(numbers) + 1 or number > 52:
                raise ValueError("GA 040 calendar poem order changed")
            numbers.append(number)
            current = number
        elif current is None:
            raise ValueError("GA 040 unknown text between calendar poems")
        poem_parts.append(block)
    flush()
    if numbers != list(range(1, 53)) or headings != 52 or seasons != ["SOMMER", "HERBST", "WINTER"]:
        raise ValueError("GA 040 calendar structure changed")
    return preface + separator + "\n\n".join(result), changed


class GA040ProseTests(unittest.TestCase):
    def test_prefaces_reflow_but_seasonal_verse_and_paragraphs_survive(self):
        text = ("Mit der Welt und ihrem\nZeitenwandel verbunden.\n\n"
                "VORWORT ZUR ZWEITEN AUSGABE 1918\n\nEin zweiter\nAbsatz.\n\n"
                "FRÜHLING\n\nOster-Stimmung\n\n1 Wenn aus den Weltenweiten\n\n"
                "Die Sonne spricht\nZum Menschensinn")
        result, count = reflow_confirmed_ga040_prose("ga-040-doc-heading-2", text)
        self.assertEqual(count, 2)
        self.assertIn("Mit der Welt und ihrem Zeitenwandel verbunden.\n\n", result)
        self.assertEqual(result.split("\n\nFRÜHLING\n\n")[1], text.split("\n\nFRÜHLING\n\n")[1])
        self.assertEqual(reflow_confirmed_ga040_prose("ga-040-doc-heading-2", result), (result, 0))

    def test_talk_reflows_but_planetary_poems_survive(self):
        text = ("Ich möchte nur vorausbemerken\neinige Worte.\n\nEin weiterer\nAbsatz.\n\n"
                "PLANETENTANZ\n\nEs leuchtet die Sonne -\nWas traget ihr Strahlen\n\nZWÖLF STIMMUNGEN")
        result, count = reflow_confirmed_ga040_prose("ga-040-doc-heading-6", text)
        self.assertEqual(count, 2)
        self.assertEqual(result.split("\n\nPLANETENTANZ\n\n")[1], text.split("\n\nPLANETENTANZ\n\n")[1])

    def test_credo_is_prose_and_unreviewed_verse_is_untouched(self):
        text = "Die Ideenwelt ist der Urquell\nund das Prinzip.\n\nEin neuer\nAbsatz."
        self.assertEqual(reflow_confirmed_ga040_prose("ga-040-doc-heading-41", text),
                         ("Die Ideenwelt ist der Urquell und das Prinzip.\n\nEin neuer Absatz.", 2))
        self.assertEqual(reflow_confirmed_ga040_prose("ga-040-doc-heading-37", "Ich schaue\nin die Welt"),
                         ("Ich schaue\nin die Welt", 0))

    def test_missing_duplicate_boundary_or_changed_opening_fails_closed(self):
        for text in ("Mit der Welt und ihrem Text ohne Grenze.",
                     "Anderes Vorwort\n\nFRÜHLING\n\n1 Wenn aus den Weltenweiten",
                     "Mit der Welt und ihrem Text\n\nFRÜHLING\n\n1 Wenn aus den Weltenweiten\n\nFRÜHLING\n\nAndere Verse"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                reflow_confirmed_ga040_prose("ga-040-doc-heading-2", text)


class GA040CalendarTests(unittest.TestCase):
    def fixture(self):
        blocks = ["Vorwort bleibt\nmit Originalumbruch.", "FRÜHLING"]
        for number, lines in enumerate(CALENDAR_LINE_COUNTS, 1):
            if number in {14, 27, 36}:
                blocks.append({14: "SOMMER", 27: "HERBST", 36: "WINTER"}[number])
            blocks.append("Erste März-Woche 2.-8. März")
            label = "5 2" if number == 52 else str(number)
            poem = [label + " Musterzeile"] + [f"Zeile {line}" for line in range(2, lines + 1)]
            # Alternate p-per-line and explicit br, as in the source EPUB.
            blocks.extend(poem if number % 2 else ["\n".join(poem)])
        return "\n\n".join(blocks)

    def test_complete_calendar_joins_only_internal_stanza_blanks(self):
        before = self.fixture()
        after, count = join_confirmed_calendar_stanzas("ga-040-doc-heading-2", before)
        self.assertGreater(count, 0)
        self.assertIn("1 Musterzeile\nZeile 2\nZeile 3", after)
        self.assertIn("\n\nErste März-Woche 2.-8. März\n\n2 Musterzeile", after)
        self.assertIn("5 2 Musterzeile", after)
        self.assertTrue(after.startswith("Vorwort bleibt\nmit Originalumbruch.\n\nFRÜHLING\n\n"))
        self.assertEqual(re.sub(r"\s", "", before), re.sub(r"\s", "", after))
        self.assertEqual(join_confirmed_calendar_stanzas("ga-040-doc-heading-2", after), (after, 0))

    def test_incomplete_reordered_or_extended_calendar_fails_closed(self):
        before = self.fixture()
        for text in (before[:before.index("\n\n5 2 Musterzeile")], before.replace("5 2 Musterzeile", "51 Musterzeile"),
                     before.replace("1 Musterzeile\n\nZeile 2", "1 Musterzeile\n\nNeue Zeile\n\nZeile 2")):
            with self.subTest(text=text[-80:]), self.assertRaises(ValueError):
                join_confirmed_calendar_stanzas("ga-040-doc-heading-2", text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args()
    if arguments.self_test:
        unittest.main(argv=[__file__])
    else:
        parser.print_help()
