#!/usr/bin/env python3
"""Extract portable paragraph-layout evidence from a source DOCX.

This helper never repairs reading text. It records spacing, explicit source
page/section breaks and cautiously identified printed page labels, then maps
existing reading blocks in source order. A small paragraph gap alone cannot
decide whether text is poetry, prose or a caption; proposed joins still require
the caller's reviewed content classification. The evidence JSON can be retained
so rebuilding readers does not require Word/LibreOffice conversion at runtime.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import re
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NORMALIZE = re.compile(r"[^a-zäöü0-9]")
FOOTER = re.compile(r"^[\"'‘’]?([0-9]{1,3})\.?$")


def normalized(text: str) -> str:
    """Whitespace/punctuation-insensitive matching, never a text replacement."""
    return NORMALIZE.sub("", text.casefold().replace("ß", "ss"))


def normalized_character_positions(text: str) -> tuple[str, list[int]]:
    """Map every matching character back to an unchanged codepoint offset."""
    parts, offsets = [], []
    for position, character in enumerate(text):
        fragment = normalized(character)
        parts.append(fragment)
        offsets.extend([position] * len(fragment))
    return "".join(parts), offsets


def source_page_starts(text: str, match: list[int], records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Locate page starts in a reading block only at verified character bounds.

    Printed pages can split words that have already been dehyphenated. Lengths
    of the normalized source paragraphs still identify that interior character.
    A page split inside one casefold expansion has no codepoint boundary and
    cannot be represented exactly. Leading source punctuation must match too.
    """
    target, positions = normalized_character_positions(text)
    source = "".join(normalized(records[index]["text"]) for index in match)
    if source != target:
        raise ValueError("Page starts require an exact normalized block match")
    output, warnings, previous_section, previous_text, consumed = [], [], None, "", 0
    for index in match:
        record = records[index]
        fragment, source_positions = normalized_character_positions(record["text"])
        section = record["source_section"]
        if section != previous_section and fragment:
            cue = {"source_section": section, "source_paragraph_index": index}
            if consumed and positions[consumed - 1] == positions[consumed]:
                warnings.append({**cue, "reason": "boundary_inside_normalization_expansion"})
            else:
                start = positions[consumed]
                # Account for an opening quote or other source punctuation.
                # Whitespace can have been reflowed, but punctuation cannot be
                # silently invented, dropped or assigned to the previous page.
                prefix = "".join(record["text"][:source_positions[0]].split())
                cursor, prefix_matches = start, True
                for character in reversed(prefix):
                    while cursor and text[cursor - 1].isspace():
                        cursor -= 1
                    if not cursor or text[cursor - 1] != character:
                        prefix_matches = False
                        break
                    cursor -= 1
                if prefix_matches and prefix and consumed:
                    # An identical quote belonging to the previous paragraph
                    # must not be borrowed as a missing new opening quote.
                    _, previous_positions = normalized_character_positions(previous_text)
                    trailing = "".join(previous_text[previous_positions[-1] + 1:].split())
                    gap = "".join(text[positions[consumed - 1] + 1:start].split())
                    prefix_matches = gap == trailing + prefix
                if not prefix_matches:
                    warnings.append({**cue, "reason": "leading_source_punctuation_has_no_exact_reading_match"})
                else:
                    output.append({**cue, "start_codepoint": cursor, "confidence": "exact_normalized_source_character_boundary"})
        consumed += len(fragment)
        previous_section = section
        if fragment:
            previous_text = record["text"]
    return output, warnings


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paragraph_text(element: ET.Element) -> str:
    parts = []
    def visit(child):
        # Drawing/textbox text is a separate layout object. Including it here
        # can append a page footer to a verse, often twice (Choice + Fallback).
        if child.tag in {W + "drawing", W + "pict", W + "txbxContent"}:
            return
        if child.tag == W + "t":
            parts.append(child.text or "")
        elif child.tag == W + "br":
            if child.get(W + "type") != "page":
                parts.append("\n")
        elif child.tag == W + "tab":
            parts.append("\t")
        for descendant in child:
            visit(descendant)
    visit(element)
    return "".join(parts)


def properties(element: ET.Element | None) -> dict:
    result = {}
    if element is None:
        return result
    for name, attrs in {
        "spacing": ("before", "after", "line", "lineRule"),
        "ind": ("start", "end", "firstLine", "hanging"),
        "jc": ("val",),
    }.items():
        node = element.find(W + name)
        if node is not None:
            for attr in attrs:
                if node.get(W + attr) is not None:
                    result[name + "_" + attr] = node.get(W + attr)
    page_break = element.find(W + "pageBreakBefore")
    if page_break is not None:
        result["page_break_before"] = page_break.get(W + "val", "1") not in {"0", "false", "off"}
    return result


def extract_layout(docx: Path) -> list[dict]:
    with ZipFile(docx) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
        styles_xml = ET.fromstring(archive.read("word/styles.xml")) if "word/styles.xml" in archive.namelist() else ET.Element("styles")
    styles = {}
    for style in styles_xml.findall(W + "style"):
        based = style.find(W + "basedOn")
        styles[style.get(W + "styleId")] = {
            "parent": based.get(W + "val") if based is not None else None,
            "properties": properties(style.find(W + "pPr")),
        }

    def inherited(style_id: str | None, seen=frozenset()) -> dict:
        if not style_id or style_id in seen or style_id not in styles:
            return {}
        style = styles[style_id]
        return inherited(style["parent"], seen | {style_id}) | style["properties"]

    body = document.find(W + "body")
    if body is None:
        raise ValueError("Source DOCX has no document body")
    # Top-level source paragraphs preserve the source's original paragraph
    # indices. Table paragraphs are outside this mapping scope; textbox labels
    # are recorded separately from the paragraph's reading text.
    records, section, pending_page_break = [], 0, False
    for index, paragraph in enumerate(body.findall(W + "p")):
        ppr = paragraph.find(W + "pPr")
        style = ppr.find(W + "pStyle") if ppr is not None else None
        style_id = style.get(W + "val") if style is not None else None
        prop = inherited(style_id) | properties(ppr)
        explicit_before = pending_page_break or prop.get("page_break_before", False)
        if explicit_before and records:
            section += 1
        text = paragraph_text(paragraph)
        section_node = ppr.find(W + "sectPr") if ppr is not None else None
        section_type = section_node.find(W + "type") if section_node is not None else None
        section_end = section_type.get(W + "val", "nextPage") if section_type is not None else "nextPage" if section_node is not None else None
        page_after = section_end in {"nextPage", "oddPage", "evenPage"}
        run_breaks = paragraph.findall(".//" + W + "br")
        run_page_break = any(br.get(W + "type") == "page" for br in run_breaks)
        before = int(prop.get("spacing_before", "0"))
        after = int(prop.get("spacing_after", "0"))
        footer_match = FOOTER.fullmatch(text.strip())
        # Numbered poetry, numbered lists and short numeric headings are not
        # footers merely because they contain a number. Require layout evidence.
        is_footer = bool(footer_match and (page_after or prop.get("jc_val") == "center") and (before >= 500 or page_after))
        record = {
            "index": index, "text": text, "source_section": section,
            "paragraph_style": style_id,
            "space_before_twips": before, "space_after_twips": after,
            "indent_start_twips": int(prop.get("ind_start", "0")),
            "indent_first_line_twips": int(prop.get("ind_firstLine", "0")),
            "alignment": prop.get("jc_val"),
            "explicit_page_break_before": bool(explicit_before),
            "section_break_after": section_end,
            "run_page_break": run_page_break,
            "is_page_footer": is_footer,
            "footer_raw": text.strip() if is_footer else None,
            "footer_page": int(footer_match[1]) if is_footer and text.strip().removesuffix(".").isdigit() else None,
            "footnote_reference_ids": [node.get(W + "id") for node in paragraph.findall(".//" + W + "footnoteReference")],
        }
        drawing_text = []
        for textbox in paragraph.findall(".//" + W + "txbxContent"):
            for nested in textbox.findall(W + "p"):
                label = paragraph_text(nested).strip()
                if label and label not in drawing_text:
                    drawing_text.append(label)
        record["drawing_text"] = drawing_text
        record["drawing_numeric_label_candidates"] = [label for label in drawing_text if label.isdigit() and 1 <= len(label) <= 3]
        records.append(record)
        # DOC sections after a paragraph are page boundaries even when the
        # paragraph is a verse line and has no printed page label.
        if page_after:
            section += 1
        pending_page_break = run_page_break and not page_after
    return records


def toc_page_anchors(records: list[dict]) -> list[dict]:
    """Use explicit TOC page numbers only when the body title matches exactly."""
    opening = next((r for r in records if r["text"].strip().casefold() in {"inhalt", "inhaltsverzeichnis", "contents"}), None)
    if opening is None:
        return []
    toc_section = opening["source_section"]
    toc = [r for r in records if r["index"] > opening["index"] and r["source_section"] == toc_section]
    last_toc = toc[-1]["index"] if toc else opening["index"]
    anchors, pending = [], []
    for record in toc:
        text = record["text"].strip()
        match = re.search(r"(?:\s|\t)([0-9]{1,3})\s*$", text)
        if not match:
            pending.append(text)
            continue
        title = " ".join(pending + [text[:match.start()].strip()])
        pending.clear()
        title_norm = normalized(title)
        candidates = [r for r in records if r["index"] > last_toc and normalized(r["text"]) == title_norm]
        if candidates:
            # Repeated title leaves (e.g. title then text proper) belong to the
            # first occurrence listed by the original table of contents.
            target = candidates[0]
            anchors.append({"source_section": target["source_section"], "page": int(match[1]), "confidence": "observed_toc_exact_body_title", "toc_paragraph_index": record["index"], "body_paragraph_index": target["index"], "title": title})
    return anchors


def extract_tables(docx: Path, records: list[dict]) -> list[dict]:
    """Keep table/diagram text and row order separate from body paragraphs."""
    with ZipFile(docx) as archive:
        body = ET.fromstring(archive.read("word/document.xml")).find(W + "body")
    tables, previous_index = [], -1
    for child in body:
        if child.tag == W + "p":
            previous_index += 1
        elif child.tag == W + "tbl":
            previous = records[previous_index] if previous_index >= 0 else None
            section = previous["source_section"] if previous else 0
            if previous and (previous["section_break_after"] in {"nextPage", "oddPage", "evenPage"} or previous["run_page_break"]):
                section += 1
            table = {"index": len(tables), "after_source_paragraph_index": previous_index, "source_section": section, "paragraphs": []}
            for row_index, row in enumerate(child.findall(W + "tr")):
                for cell_index, cell in enumerate(row.findall(W + "tc")):
                    for paragraph_index, paragraph in enumerate(cell.findall(W + "p")):
                        table["paragraphs"].append({"row_index": row_index, "cell_index": cell_index, "paragraph_index": paragraph_index, "text": paragraph_text(paragraph), "direct_properties": properties(paragraph.find(W + "pPr"))})
            tables.append(table)
    return tables


def map_non_paragraph_blocks(payload: dict, passages: list[dict], tables: list[dict]) -> list[dict]:
    """Find exact table matches bounded by neighbouring paragraph matches."""
    matches = []
    for passage, mapped in zip(payload["passages"], passages):
        for block_index, (text, block) in enumerate(zip(passage["text"].split("\n\n"), mapped["blocks"])):
            if block["source_paragraph_indices"]:
                continue
            previous = next((b for b in reversed(mapped["blocks"][:block_index]) if b["source_paragraph_indices"]), None)
            following = next((b for b in mapped["blocks"][block_index + 1:] if b["source_paragraph_indices"]), None)
            left = previous["source_paragraph_indices"][-1] if previous else -1
            right = following["source_paragraph_indices"][0] if following else float("inf")
            candidates = [t for t in tables if left <= t["after_source_paragraph_index"] < right and normalized(" ".join(p["text"] for p in t["paragraphs"])) == normalized(text)]
            if len(candidates) == 1:
                table = candidates[0]
                matches.append({"passage_id": passage["id"], "block_index": block_index, "source_table_index": table["index"], "source_section": table["source_section"], "confidence": "exact_normalized_source_table_in_order"})
    return matches


def page_cues(records: list[dict], toc_anchors: list[dict] | None = None) -> dict[int, dict]:
    anchors = {}
    confidence = {}
    conflicts = {}
    def add_anchor(section: int, page: int, method: str):
        previous = anchors.get(section)
        if previous is not None and previous != page:
            conflicts.setdefault(section, set()).update((previous, page))
        anchors[section] = page
        confidence[section] = method
    for anchor in toc_anchors or []:
        add_anchor(anchor["source_section"], anchor["page"], anchor["confidence"])
    for record in records:
        page = record["footer_page"]
        if page is not None:
            add_anchor(record["source_section"], page, "observed_footer")
    for section in conflicts:
        del anchors[section]
    sections = sorted({record["source_section"] for record in records})
    cues = {}
    for section in sections:
        if section in conflicts:
            cues[section] = {"page": None, "confidence": "conflicting_observed_labels", "observed_pages": sorted(conflicts[section])}
            continue
        if section in anchors:
            cues[section] = {"page": anchors[section], "confidence": confidence[section]}
            continue
        left = [(s, p) for s, p in anchors.items() if s < section]
        right = [(s, p) for s, p in anchors.items() if s > section]
        if left and right:
            ls, lp = max(left)
            rs, rp = min(right)
            # Infer only inside an interval whose two independently observed
            # printed footers prove the same section/page offset. Never assume
            # a document-wide offset; source DOCs can omit unnumbered leaves.
            if lp - ls == rp - rs and not any(ls < conflict < rs for conflict in conflicts):
                cues[section] = {"page": section + lp - ls, "confidence": "inferred_between_consistent_footers", "anchors": [lp, rp]}
                continue
        cues[section] = {"page": None, "confidence": "unresolved"}
    return cues


def map_blocks(payload: dict, records: list[dict]) -> list[dict]:
    norms = [normalized(record["text"]) for record in records]
    cursor, output = 0, []
    for passage in payload["passages"]:
        mapped = []
        for block_index, text in enumerate(passage["text"].split("\n\n")):
            target = normalized(text)
            match = None
            for start in range(cursor, len(records)):
                if not target or not norms[start] or not target.startswith(norms[start]):
                    continue
                combined, used = "", []
                for end in range(start, min(start + 100, len(records))):
                    record = records[end]
                    if record["is_page_footer"] and end == start and norms[end] == target:
                        match = [end]
                        break
                    if record["is_page_footer"] or not norms[end]:
                        continue
                    # Footnotes recovered into the source body can intervene
                    # between verse paragraphs. They remain source evidence.
                    if record["text"].lstrip().startswith("*") and not target.startswith(combined + norms[end]):
                        continue
                    combined += norms[end]
                    used.append(end)
                    if combined == target:
                        match = used
                        break
                    if not target.startswith(combined):
                        break
                if match:
                    break
            entry = {"block_index": block_index, "opening": text.splitlines()[0][:100] if text else "", "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "source_paragraph_indices": match or [], "confidence": "exact_normalized_source_order" if match else "unmatched"}
            if match:
                entry["source_sections"] = sorted({records[index]["source_section"] for index in match})
                first = records[match[0]]
                entry["space_before_twips"] = first["space_before_twips"]
                entry["indent_start_twips"] = first["indent_start_twips"]
                entry["source_page_starts"], page_start_warnings = source_page_starts(text, match, records)
                if page_start_warnings:
                    entry["source_page_start_warnings"] = page_start_warnings
                previous = next((b for b in reversed(mapped) if b["source_paragraph_indices"]), None)
                if previous:
                    before_index = previous["source_paragraph_indices"][-1]
                    span = records[before_index:match[0]]
                    entry["page_break_since_previous"] = any(p["section_break_after"] in {"nextPage", "oddPage", "evenPage"} or p["run_page_break"] for p in span) or first["explicit_page_break_before"]
                    entry["printed_page_footers_since_previous"] = [p["footer_raw"] for p in span if p["is_page_footer"]]
                    gap = first["space_before_twips"] + records[before_index]["space_after_twips"]
                    entry["small_gap_join_candidate"] = bool(not entry["page_break_since_previous"] and gap <= 100 and all(not p["text"].strip() for p in records[before_index + 1:match[0]]))
                cursor = match[-1] + 1
            mapped.append(entry)
        output.append({"id": passage["id"], "title": passage["title"], "blocks": mapped})
    return output


def compact_evidence(result: dict) -> dict:
    """Retain verifiable layout and matches without duplicating source prose."""
    compact = copy.deepcopy(result)
    compact["representation"] = "portable_layout_evidence_without_source_text"
    for record in compact["paragraphs"]:
        text = record.pop("text")
        record["text_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        record["text_length"] = len(text)
        record["drawing_text_sha256"] = [hashlib.sha256(text.encode()).hexdigest() for text in record.pop("drawing_text", [])]
    for table in compact.get("tables", []):
        for paragraph in table["paragraphs"]:
            text = paragraph.pop("text")
            paragraph["text_sha256"] = hashlib.sha256(text.encode()).hexdigest()
            paragraph["text_length"] = len(text)
    unmatched = []
    for passage in compact.get("passages", []):
        for block in passage["blocks"]:
            block.pop("opening", None)
            if not block["source_paragraph_indices"]:
                table = next((t for t in compact.get("non_paragraph_matches", []) if t["passage_id"] == passage["id"] and t["block_index"] == block["block_index"]), None)
                unmatched.append({"passage_id": passage["id"], "block_index": block["block_index"], "reason": "matched_source_table_outside_paragraph_mapping" if table else "no_exact_source_paragraph_match; source_graphics_or_text_need_review", **({"source_table_index": table["source_table_index"]} if table else {})})
    compact["unmatched_blocks"] = unmatched
    return compact


class SourceLayoutTests(unittest.TestCase):
    def test_page_offset_is_local_and_requires_two_anchors(self):
        records = [{"source_section": s, "footer_page": p} for s, p in [(1, 5), (2, None), (3, 7), (4, None), (5, 10)]]
        cues = page_cues(records)
        self.assertEqual(cues[2]["page"], 6)
        self.assertIsNone(cues[4]["page"])

    def test_exact_mapping_is_monotone_and_preserves_verse_breaks(self):
        records = [{"index": i, "text": t, "source_section": 0, "is_page_footer": False, "space_before_twips": 0, "space_after_twips": 0, "indent_start_twips": 0, "explicit_page_break_before": False, "section_break_after": None, "run_page_break": False, "footer_raw": None} for i, t in enumerate(["Wesen reiht", "Unvergängliche,\nJenseits", "Andere Zeile"])]
        payload = {"passages": [{"id": "test", "title": "Verse", "text": "Wesen reiht\n\nUnvergängliche,\nJenseits\n\nAndere Zeile"}]}
        mapped = map_blocks(payload, records)[0]["blocks"]
        self.assertEqual([b["source_paragraph_indices"] for b in mapped], [[0], [1], [2]])
        self.assertTrue(mapped[1]["small_gap_join_candidate"])
        records[0]["section_break_after"] = "nextPage"
        self.assertFalse(map_blocks(payload, records)[0]["blocks"][1]["small_gap_join_candidate"])

    def test_drawing_footer_does_not_pollute_parent_verse_or_duplicate(self):
        element = ET.fromstring(f'<w:p xmlns:w="{W[1:-1]}"><w:r><w:t>Vers</w:t></w:r><w:r><w:drawing><w:txbxContent><w:p><w:r><w:t>226</w:t></w:r></w:p></w:txbxContent></w:drawing></w:r></w:p>')
        self.assertEqual(paragraph_text(element), "Vers")

    def test_toc_anchor_requires_an_exact_title(self):
        records = [{"index": i, "source_section": section, "text": text} for i, section, text in [(0, 0, "INHALT"), (1, 0, "Gedichte\t7"), (2, 0, "Verse\t8"), (3, 1, "GEDICHTE"), (4, 2, "Verse und Prosa")]]
        anchors = toc_page_anchors(records)
        self.assertEqual([(a["source_section"], a["page"]) for a in anchors], [(1, 7)])

    def test_contradictory_observed_page_labels_are_not_inferred_through(self):
        records = [{"source_section": s, "footer_page": p} for s, p in [(1, 5), (2, None), (3, 7), (4, None), (5, 9)]]
        cues = page_cues(records, [{"source_section": 3, "page": 8, "confidence": "observed_toc_exact_body_title"}])
        self.assertEqual(cues[3]["confidence"], "conflicting_observed_labels")
        self.assertIsNone(cues[2]["page"])
        self.assertIsNone(cues[4]["page"])

    def test_compact_evidence_retains_hashes_and_layout_without_source_text(self):
        result = {"paragraphs": [{"index": 7, "text": "Source prose", "space_before_twips": 20, "drawing_text": ["226"], "drawing_numeric_label_candidates": ["226"]}], "passages": [{"id": "test", "blocks": [{"block_index": 0, "opening": "Source prose", "text_sha256": "block-hash", "source_paragraph_indices": [7]}, {"block_index": 1, "opening": "Diagram", "source_paragraph_indices": []}]}]}
        compact = compact_evidence(result)
        self.assertEqual(result["paragraphs"][0]["text"], "Source prose")
        self.assertNotIn("text", compact["paragraphs"][0])
        self.assertEqual(compact["paragraphs"][0]["space_before_twips"], 20)
        self.assertEqual(compact["paragraphs"][0]["text_sha256"], hashlib.sha256(b"Source prose").hexdigest())
        self.assertNotIn("opening", compact["passages"][0]["blocks"][0])
        self.assertEqual(compact["unmatched_blocks"][0]["block_index"], 1)

    def test_table_matching_is_bounded_by_source_order(self):
        payload = {"passages": [{"id": "test", "text": "Title\n\nOne Two\n\nEnd"}]}
        passages = [{"blocks": [{"source_paragraph_indices": [4]}, {"source_paragraph_indices": []}, {"source_paragraph_indices": [7]}]}]
        table = {"index": 0, "after_source_paragraph_index": 5, "source_section": 2, "paragraphs": [{"text": "One"}, {"text": "Two"}]}
        self.assertEqual(map_non_paragraph_blocks(payload, passages, [table])[0]["source_table_index"], 0)
        table["after_source_paragraph_index"] = 8
        self.assertEqual(map_non_paragraph_blocks(payload, passages, [table]), [])

    def test_page_start_can_be_inside_a_dehyphenated_word(self):
        text = "besonders betont werden, daß es gilt."
        records = [{"text": "besonders betont wer-", "source_section": 37}, {"text": "den, daß es gilt.", "source_section": 38}]
        starts, warnings = source_page_starts(text, [0, 1], records)
        self.assertEqual(warnings, [])
        self.assertEqual(starts[1]["start_codepoint"], text.index("den,"))
        self.assertEqual(text[starts[1]["start_codepoint"]:], "den, daß es gilt.")

    def test_page_start_includes_exact_source_opening_punctuation(self):
        text = 'Ende. «Neuer Absatz»'
        records = [{"text": "Ende.", "source_section": 1}, {"text": '\t«Neuer Absatz»', "source_section": 2}]
        starts, warnings = source_page_starts(text, [0, 1], records)
        self.assertEqual(warnings, [])
        self.assertEqual(starts[1]["start_codepoint"], text.index("«"))
        records[1]["text"] = "\t[Neuer Absatz]"
        starts, warnings = source_page_starts(text, [0, 1], records)
        self.assertEqual(len(starts), 1)
        self.assertEqual(warnings[0]["reason"], "leading_source_punctuation_has_no_exact_reading_match")

    def test_page_start_inside_casefold_expansion_is_unresolved(self):
        records = [{"text": "Mas-", "source_section": 1}, {"text": "se", "source_section": 2}]
        starts, warnings = source_page_starts("Maße", [0, 1], records)
        self.assertEqual(len(starts), 1)
        self.assertEqual(warnings[0]["reason"], "boundary_inside_normalization_expansion")

    def test_a_previous_page_quote_cannot_stand_in_for_a_missing_opening_quote(self):
        records = [{"text": 'End"', "source_section": 1}, {"text": '"Next"', "source_section": 2}]
        starts, warnings = source_page_starts('End"Next"', [0, 1], records)
        self.assertEqual(len(starts), 1)
        self.assertEqual(len(warnings), 1)
        text = 'End" "Next"'
        starts, warnings = source_page_starts(text, [0, 1], records)
        self.assertEqual(warnings, [])
        self.assertEqual(starts[1]["start_codepoint"], text.index('"Next'))

    def test_character_offsets_are_codepoints_and_preserve_surrogate_characters(self):
        text = "😀 Ende. Neu"
        records = [{"text": "😀 Ende.", "source_section": 1}, {"text": "Neu", "source_section": 2}]
        starts, warnings = source_page_starts(text, [0, 1], records)
        self.assertEqual(warnings, [])
        self.assertEqual(starts[1]["start_codepoint"], text.index("Neu"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docx", type=Path)
    parser.add_argument("--source-doc", type=Path)
    parser.add_argument("--source-url")
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true", help="Persist hashes and layout/mapping evidence without full paragraph text or reading-block openings")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        unittest.main(argv=[__file__])
        return
    if not args.docx or not args.output:
        parser.error("--docx and --output are required")
    records = extract_layout(args.docx)
    tables = extract_tables(args.docx, records)
    toc_anchors = toc_page_anchors(records)
    result = {"schema_version": 1, "method": "source_docx_layout_evidence", "conversion_docx_sha256": sha256(args.docx), "source_doc_sha256": sha256(args.source_doc) if args.source_doc else None, "source_url": args.source_url, "interpretation": "Paragraph spacing and explicit page breaks are source evidence. Small-gap joins require a reviewed prose/verse classification. Inferred pages are marked separately from observed labels. Table paragraphs retain their separate row/cell order.", "paragraphs": records, "tables": tables, "toc_page_anchors": toc_anchors, "page_cues": page_cues(records, toc_anchors)}
    if args.payload:
        data = args.payload.read_bytes()
        payload = json.loads(gzip.decompress(data) if args.payload.suffix == ".gz" else data)
        if args.source_doc and payload.get("source_sha256") and payload["source_sha256"] != result["source_doc_sha256"]:
            raise ValueError("Original source DOC hash does not match retained reading provenance")
        result["work_id"] = payload.get("work_id")
        result["reading_payload_sha256"] = sha256(args.payload)
        result["passages"] = map_blocks(payload, records)
        result["non_paragraph_matches"] = map_non_paragraph_blocks(payload, result["passages"], tables)
        result["mapping_summary"] = {"blocks": sum(len(p["blocks"]) for p in result["passages"]), "matched": sum(bool(b["source_paragraph_indices"]) for p in result["passages"] for b in p["blocks"]), "matched_non_paragraph": len(result["non_paragraph_matches"])}
    if args.compact:
        result = compact_evidence(result)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "source_doc_sha256": result["source_doc_sha256"], "mapping_summary": result.get("mapping_summary")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
