#!/usr/bin/env python3
"""Freeze source-bound dramatic layout for the retained 1998 GA 014 EPUB.

Every input paragraph must exactly match a source-lines paragraph in the
hash-bound EPUB. The recipe consumes each retained character once, removes only
page-leading running heads, and records exact facsimile-reviewed verse repairs.
Source PDF indexes are evidence identities, not printed reader page anchors.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from finalize_library import read_json
from repair_source_structure import apply_passage_plan, sha, utf16

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = "658bfbcd00a8d0f2515b5c48d97ffe09d8052e6150cc3b7f21260eea541b8e7f"
NS = "{http://www.w3.org/1999/xhtml}"
PROSE_PLAYS = {"ga-014-pdf-outline-13-5", "ga-014-pdf-outline-122-13"}
MAJOR_TITLES = {
    "ga-014-pdf-outline-9-3": 2,
    "ga-014-pdf-outline-157-18": 1,
    "ga-014-pdf-outline-281-33": 1,
    "ga-014-pdf-outline-405-45": 1,
}
CAST_LISTS = {
    "ga-014-pdf-outline-11-4", "ga-014-pdf-outline-159-19",
    "ga-014-pdf-outline-283-34", "ga-014-pdf-outline-407-46",
}
GROUP_HEADS = {
    "Die Pforte der Einweihung", "Die Prüfung der Seele",
    "Der Hüter der Schwelle", "Der Seelen Erwachen",
}
SCENE_HEADS = {
    "Vorspiel", "Zwischenspiel", "Erstes Bild", "Zweites Bild",
    "Drittes Bild", "Viertes Bild", "Fünftes Bild", "Sechstes Bild",
    "Siebentes Bild", "Achtes Bild", "Neuntes Bild", "Zehntes Bild",
    "Elftes Bild", "Zwölftes Bild", "Dreizehntes Bild",
    "Vierzehntes Bild", "Fünfzehntes Bild", "Personen, Gestalten und Vorgänge",
}
# These are source spelling/OCR tokens; their wording is not repaired.
OTHER_LABELS = {"3.BÄUERIN*.", "FELIX BÄLDE*.", "HILARIUS GOTTGETREU, der Großmeister:"}
# Source small-cap glyphs sometimes OCR as lowercase umlauts or initial i.
# They remain exactly as transcribed; this only recognizes the speaker role.
LABEL_START = re.compile(r"^(?:i\.|[A-ZÄÖÜ0-9])[A-ZÄÖÜäöü0-9 .,*'«»\-]*?(?=:|\s*\()")
SCENE_TITLE = re.compile(r"^[A-ZÄÖÜ ]+ BILD$")
SOURCE_REVIEW = (
    "Retained 1998 GA 014 EPUB, SHA-256 " + SOURCE_SHA256 +
    "; embedded facsimile PDF pages 13, 14, 21, 118, 215 and 538 reviewed. "
    "Prose has justified physical wrapping; verse is indented in printed lines; "
    "speaker labels are capitals and parenthetical directions are prose. "
    "Exact continuation and stage-direction repairs have individual facsimile evidence; "
    "other OCR wording and uncertain punctuation are retained."
)
REPAIRS_PATH = ROOT / "tools/ga014_reviewed_repairs.json"


def reviewed_repairs():
    repairs = defaultdict(list)
    for repair in read_json(REPAIRS_PATH):
        if (not repair.get("old") or not repair.get("evidence")
                or SOURCE_SHA256 not in repair["evidence"]
                or not repair.get("pages")
                or any(f"source-page-{page}" not in repair["evidence"] for page in repair["pages"])):
            raise ValueError("GA 014 repair lacks exact facsimile evidence")
        repairs[repair["passage_id"]].append(repair)
    return repairs


def source_paragraphs(source):
    """Read the simple hash-bound page witness without a general HTML parser."""
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("The reviewed GA 014 source EPUB changed")
    result = defaultdict(list)
    with ZipFile(source) as archive:
        for member in archive.namelist():
            if not re.fullmatch(r"EPUB/chapter-\d+\.xhtml", member):
                continue
            root = ET.fromstring(archive.read(member))
            page = None
            for element in root.find(NS + "body"):
                if element.get("id", "").startswith("source-page-"):
                    page = int(element.get("id").rsplit("-", 1)[1])
                if element.tag != NS + "p":
                    continue
                if list(element) or element.get("class") != "source-lines" or page is None:
                    raise ValueError("Unexpected markup in the reviewed simple source witness")
                # The exact source class is white-space:pre-line. Only horizontal
                # whitespace collapses; each actual LF remains a source line.
                text = "\n".join(re.sub(r"[ \t\r\f]+", " ", line).strip()
                                 for line in (element.text or "").split("\n")).strip()
                result[text].append({"page": page, "member": member})
    return result


def lines_with_parts(passage, lookup, repairs=()):
    lines, omissions = [], []
    for block_index, block in enumerate(passage["text"].split("\n\n")):
        evidence = lookup.get(block, [])
        if len(evidence) != 1:
            raise ValueError("Paragraph does not match one exact source page: " + passage["id"])
        source = evidence[0]
        page, position = source["page"], 0
        for index, line in enumerate(block.split("\n")):
            end = position + len(line)
            part = {"block": block_index, "start": position, "end": end}
            is_head = index == 0 and (line in GROUP_HEADS or line in SCENE_HEADS)
            is_head |= index == 0 and page == 118 and line == "DiesPforte der Einweihung"
            if is_head:
                omissions.append({**part, "kind": "running_header", "text_sha256": sha(line),
                    "page": page, "source_member": source["member"],
                    "evidence": f"{SOURCE_REVIEW} First line of {source['member']} source-page-{page}; "
                        "repeated running head above the rule in the embedded facsimile. "
                        "page is the PDF source index, not a printed page label."})
            elif line.strip():
                if page == 122 and line == "in demselben Zimmer wie das VorspielSOPHIA:":
                    # The facsimile has a distinct Sophia label after the
                    # introduction. The OCR lost the whitespace and full stop;
                    # split only whitespace here, retaining all source letters.
                    cut = line.index("SOPHIA:")
                    lines.append({"text": line[:cut], "part": {**part, "end": position + cut}, **source})
                    lines.append({"text": line[cut:], "part": {**part, "start": position + cut}, **source})
                elif mixed := next((repair for repair in repairs
                                    if repair.get("mixed_stage_line") == line), None):
                    # A right-aligned verse continuation shares a physical row
                    # with the following stage cue. Keep both exact source slices.
                    prefix = mixed["stage_text"]
                    if not line.startswith(prefix + " "):
                        raise ValueError("Reviewed mixed stage/verse row changed")
                    suffix = line[len(prefix):].lstrip()
                    cut = len(line) - len(suffix)
                    lines.append({"text": suffix, "part": {**part, "start": position + cut}, **source})
                    lines.append({"text": prefix, "part": {**part, "end": position + len(prefix)}, **source})
                else:
                    lines.append({"text": line, "part": part, **source})
            position = end + 1
    return lines, omissions


def label_span(lines, index):
    """Recognize the reviewed capital speaker-label typography, retaining OCR."""
    text = lines[index]["text"]
    if text in OTHER_LABELS or text == "SINGEN DER KINDER":
        return index + 1, None
    if text == "DAS FOLGENDE ALS GEISTERSTIMME AUS DEN":
        if index + 1 >= len(lines) or lines[index + 1]["text"] != "HÖHEN :":
            raise ValueError("The exact reviewed two-line voice label changed")
        return index + 2, None
    match = LABEL_START.match(text)
    if not match:
        return None
    prefix = match[0]
    # A parenthetical scenic cue can wrap after the capital speaker name.
    end = index
    joined = text
    while ":" not in joined and end + 1 < len(lines) and end - index < 8:
        end += 1
        joined += "\n" + lines[end]["text"]
    if ":" not in joined:
        return None
    # A colon inside a parenthetical scenic instruction does not end the label.
    depth = 0
    colon_line, colon_position = None, None
    for li in range(index, end + 1):
        for ci, character in enumerate(lines[li]["text"]):
            depth += character == "("
            depth -= character == ")"
            if character == ":" and depth <= 0:
                colon_line, colon_position = li, ci
                break
        if colon_line is not None:
            break
    if colon_line is None:
        return None
    tail = lines[colon_line]["text"][colon_position + 1:]
    return colon_line + 1, colon_position + 1 if tail.strip() else None


def stage_span(lines, index):
    """Only a line-leading, closed parenthesis authorizes prose reflow."""
    text = lines[index]["text"]
    if not text.startswith("("):
        return None
    depth, end = 0, index
    while end < len(lines):
        fragment = lines[end]["text"]
        for character in fragment:
            depth += character == "("
            depth -= character == ")"
        if depth == 0 and ")" in fragment:
            if not fragment.rstrip().endswith((")", "):", ").")):
                return None  # Mixed dialogue/stage syntax stays source-literal.
            return end + 1
        if depth < 0 or end - index >= 20:
            return None
        end += 1
    return None


def passage_plan(passage, lookup, repairs=()):
    lines, omissions = lines_with_parts(passage, lookup, repairs)
    plan = {"input_sha256": sha(passage["text"]),
            "source_text_sha256": sha(passage.get("source_text", "")),
            "group_title": passage["metadata"].get("group_title", passage["title"]),
            "segments": [], "omitted_parts": omissions}
    segments = plan["segments"]
    residual = []

    def append(kind, selected, *, separate=False, level=None, role=None):
        if not selected:
            return
        parts = [line["part"] for line in selected]
        pages = list(dict.fromkeys(line["page"] for line in selected))
        if not separate and segments and segments[-1]["kind"] == kind and kind in {"verse", "prose"} and segments[-1].get("source_role") == role:
            segment = segments[-1]
            segment["parts"].extend(parts)
            segment["source_pdf_pages"] = list(dict.fromkeys(segment["source_pdf_pages"] + pages))
        else:
            segment = {"kind": kind, "parts": parts, "join": "\n" if kind == "verse" else " ",
                       "source_pdf_pages": pages, "source_evidence": SOURCE_REVIEW}
            if segments and (segments[-1]["kind"] == "attribution" or
                             segments[-1].get("source_role") == "parenthetical_stage_direction" and role == "spoken_lines"):
                # The printed speaker name and its speech are one dramatic
                # unit; source-defined verse lines remain contiguous below it.
                segment["separator"] = "\n"
            if level is not None:
                segment["level"] = level
            if role:
                segment["source_role"] = role
            segments.append(segment)

    pid = passage["id"]
    if pid in MAJOR_TITLES:
        count = MAJOR_TITLES[pid]
        append("heading", lines[:count], separate=True, level=1, role="source_title")
        append("verse", lines[count:], role="title_page_lines")
        return plan, residual
    if pid in CAST_LISTS:
        append("heading", lines[:1], separate=True, level=2, role="source_title")
        append("verse", lines[1:], role="source_cast_list_lines")
        return plan, residual

    index, has_speaker, body_mode = 0, False, "prose" if pid in PROSE_PLAYS else "verse"
    while index < len(lines):
        line = lines[index]
        text = line["text"]
        reviewed_stage = next((repair for repair in repairs
                                if repair.get("source_lines")
                                and [entry["text"] for entry in lines[index:index + len(repair["source_lines"])]]
                                == repair["source_lines"]), None)
        if reviewed_stage:
            end = index + len(reviewed_stage["source_lines"])
            speaker = reviewed_stage["kind"] == "speaker_label"
            append("attribution" if speaker else "prose", lines[index:end], separate=True,
                   role="speaker_label" if speaker else "parenthetical_stage_direction")
            if speaker:
                has_speaker = True
                body_mode = "prose" if pid in PROSE_PLAYS else "verse"
            index = end
            continue
        if SCENE_TITLE.fullmatch(text) or text in {"VORSPIEL", "ZWISCHENSPIEL", "ZEHNTE S BILD"}:
            append("heading", [line], separate=True, level=2, role="source_title")
            index += 1
            continue
        label = label_span(lines, index)
        if label:
            end, inline = label
            selected = deepcopy(lines[index:end])
            if inline is not None:
                original = lines[end - 1]
                selected[-1]["text"] = original["text"][:inline]
                selected[-1]["part"]["end"] = original["part"]["start"] + inline
                remainder = deepcopy(original)
                remainder["text"] = original["text"][inline:].lstrip()
                remainder["part"]["start"] = original["part"]["start"] + inline + len(original["text"][inline:]) - len(remainder["text"])
                lines.insert(end, remainder)
            append("attribution", selected, separate=True, role="speaker_label")
            has_speaker = True
            body_mode = "verse" if text == "SINGEN DER KINDER" else "prose" if pid in PROSE_PLAYS else "verse"
            index = end
            continue
        stage = stage_span(lines, index)
        if stage:
            append("prose", lines[index:stage], separate=True, role="parenthetical_stage_direction")
            index = stage
            continue
        kind = body_mode if has_speaker else "prose"
        append(kind, [line], role="spoken_lines" if has_speaker else "scene_introduction")
        if text.startswith(("{", "(")) and stage is None:
            residual.append({"passage_id": pid, "rule": "verse_overrun_review", "count": 1,
                             "label": "Überlange Verszeile am Druck prüfen", "excerpt": text,
                             "description": f"PDF-Quellseite {line['page']}: Unklare Klammer/OCR-Zeichen "
                                 "einer Bühnenanweisung ohne Vermutung beibehalten."})
        if kind == "verse" and ("[" in text or re.search(r"\w-\s*$", text)):
            residual.append({"passage_id": pid, "rule": "verse_overrun_review", "count": 1,
                             "label": "Überlange Verszeile am Druck prüfen", "excerpt": text,
                             "description": f"PDF-Quellseite {line['page']}: Gedruckter Versüberlauf/Klammer "
                                 "oder unklare Trennung am Zeilenende zur Kollation beibehalten."})
        index += 1
    return plan, residual


def build(payload, source):
    if payload["work_id"] != "ga-014" or payload["source_epub_sha256"] != SOURCE_SHA256:
        raise ValueError("This recipe builder is bound to the retained GA 014 edition")
    lookup = source_paragraphs(source)
    repairs = reviewed_repairs()
    recipe = {"schema_version": 1, "work_id": "ga-014", "offset_unit": "utf16",
              **{key: payload[key] for key in ("source_sha256", "source_epub_sha256", "source_url")},
              "review_scope": "dramatic_prose_verse_speaker_and_running_header_whitespace",
              "source_evidence": SOURCE_REVIEW,
              "source_page_identity": "PDF source indexes only; no printed-page reader anchors inferred",
              "table_of_contents": deepcopy(payload["table_of_contents"]),
              "passages": {}, "review_flags": [],
              "known_gaps": ["Vollständige OCR-Kollation bleibt offen; die erfassten Versüberläufe sind am Faksimile rekonstruiert.",
                             "Personenlisten behalten ihre Quellzeilen; kein neues Listenmodell wird eingeführt.",
                             "Weitere Wort- und Satzzeichenfehler außerhalb der geprüften Layoutstellen sind nicht vollständig kollationiert."]}
    for passage in payload["passages"]:
        passage_repairs = repairs.get(passage["id"], [])
        plan, flags = passage_plan(passage, lookup, passage_repairs)
        if passage_repairs:
            plan["edits"] = [{key: repair[key] for key in ("old", "new", "evidence", "kind", "pages")}
                             for repair in passage_repairs]
        probe = deepcopy(passage)
        apply_passage_plan(probe, plan, "recipe-generation")
        plan["output_sha256"] = sha(probe["text"])
        recipe["passages"][passage["id"]] = plan
        recipe["review_flags"].extend(flag for flag in flags if flag["excerpt"] in probe["text"])
    return recipe


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", type=Path, help="Exact post-outline, pre-readability payload")
    parser.add_argument("--source", type=Path, default=ROOT / "research/proofreading-sources/ga-014.epub")
    parser.add_argument("--output", type=Path, default=ROOT / "tools/ga014_structure.json")
    args = parser.parse_args()
    payload_path = args.payload or ROOT / "server/priv/content/ga-014.json.gz"
    payload = read_json(payload_path)
    if args.payload is None and payload.get("metadata", {}).get("source_layout"):
        payload_path = ROOT / "research/proofreading-ga014-baseline/content/ga-014.json.gz"
        report = read_json(ROOT / "server/priv/proofreading/works/ga-014.json")
        if hashlib.sha256(payload_path.read_bytes()).hexdigest() != report["work"].get("ga014_input_sha256"):
            raise ValueError("Preserved GA 014 recipe input differs from its correction ledger")
        payload = read_json(payload_path)
    recipe = build(payload, args.source)
    args.output.write_text(json.dumps(recipe, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"recipe": str(args.output), "passages": len(recipe["passages"]),
                      "segments": sum(len(p["segments"]) for p in recipe["passages"].values()),
                      "running_headers": sum(len(p["omitted_parts"]) for p in recipe["passages"].values()),
                      "review_flags": len(recipe["review_flags"])}))
