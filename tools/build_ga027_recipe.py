#!/usr/bin/env python3
"""Freeze GA027 paragraph layout from the reviewed1991 facsimile witness.

Only reviewed paragraph starts/standalone lines determine boundaries. The
recipe consumes every retained source character once, joins physical wraps,
reorders exact table cells and repairs six explicitly verified page seams.
"""
from __future__ import annotations
import argparse
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
REVIEW = ROOT / "tools/ga027_layout_review.json"
SOURCE = ROOT / "research/proofreading-sources/ga-027.epub"
BASELINE = ROOT / "research/proofreading-layout-baseline/content/ga-027.json.gz"
RECIPE = ROOT / "tools/ga027_structure.json"
NS = "{http://www.w3.org/1999/xhtml}"


def check_source(source, review):
    if hashlib.sha256(source.read_bytes()).hexdigest() != review["source_epub_sha256"]:
        raise ValueError("GA027 reviewed EPUB changed")
    pages = {}
    with ZipFile(source) as archive:
        for member in archive.namelist():
            if not re.fullmatch(r"EPUB/chapter-\d+\.xhtml", member):
                continue
            page = None
            for element in ET.fromstring(archive.read(member)).find(NS + "body"):
                if element.get("id", "").startswith("source-page-"):
                    page = int(element.get("id").rsplit("-", 1)[1])
                if element.tag == NS + "p" and element.get("class") == "source-lines":
                    if list(element) or page is None:
                        raise ValueError("Unexpected source markup")
                    pages[page] = element.text or ""
        for number, identity in review["pages"].items():
            page = int(number)
            if (sha(pages[page]) != identity["text_sha256"]
                    or hashlib.sha256(archive.read(identity["image_member"])).hexdigest() != identity["image_sha256"]):
                raise ValueError("GA027 source page/scan changed")
            root = ET.fromstring(archive.read(identity["member"]))
            if root.find(f".//*[@id='{identity['source_page_id']}']") is None:
                raise ValueError("GA027 source page identity changed")
    for plan in review["passages"].values():
        for start in plan["starts"]:
            actual = pages[start["page"]].splitlines()[start["source_line"]].strip()
            if actual != start["source_line_text"] or not actual.startswith(start["anchor"]):
                raise ValueError("GA027 reviewed source start drift")
    return pages


def parts_between(text, begin, end):
    """Translate one exact source span to the engine's paragraph-local slices."""
    result, offset = [], 0
    for index, block in enumerate(text.split("\n\n")):
        left, right = max(begin, offset), min(end, offset + len(block))
        if left < right and text[left:right].strip():
            result.append({"block": index, "start": left - offset, "end": right - offset})
        offset += len(block) + 2
    if not result:
        raise ValueError("Empty reviewed source span")
    return result


def table_segments(text, table):
    old = table["old"]
    if text.count(old) != 1:
        raise ValueError("GA027 correction-table input drift")
    base = text.index(old)
    lines, positions, position = old.splitlines(), [], base
    for line in lines:
        positions.append((position, position + len(line)))
        position += len(line) + 1

    def take(first, last=None):
        return parts_between(text, positions[first][0], positions[first if last is None else last][1])

    segments = [
        {"kind": "note", "parts": take(0, 1), "join": " ", "separator": "\n"},
        {"kind": "note", "parts": take(2, 3), "join": " ", "separator": "\n"},
    ]
    for index, row in enumerate(table["rows"]):
        if (lines[18 + index] != row["page"] or lines[30 + index] != row["line"]
                or lines[4 + index] != row["description"]):
            raise ValueError("GA027 reviewed table cell mismatch")
        segments.append({"kind": "note", "parts": take(18 + index) + take(30 + index) + take(4 + index),
                         "join": " ", "separator": "\n"})
    segments.append({"kind": "note", "parts": take(16, 17), "join": " ", "separator": "\n\n"})
    for segment in segments:
        segment["source_pdf_pages"] = [140]
        segment["evidence"] = table["evidence"]
    return base, base + len(old), segments


def build(payload, source=SOURCE, review=None):
    review = review or read_json(REVIEW)
    check_source(source, review)
    if (payload["work_id"] != review["work_id"]
            or any(payload.get(key) != review[key] for key in ("source_sha256", "source_epub_sha256"))
            or list(review["passages"]) != [p["id"] for p in payload["passages"]]):
        raise ValueError("GA027 reviewed source/passage inventory drift")
    recipe = {"schema_version": 1, "offset_unit": "utf16", "work_id": payload["work_id"], "source_sha256": payload["source_sha256"],
              "source_epub_sha256": payload["source_epub_sha256"], "source_url": payload["source_url"],
              "source_evidence": {"review_sha256": sha(json.dumps(review, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
                                  "method": review["method"], "pages": review["pages"]},
              "known_gaps": review["known_gaps"], "review_flags": [], "passages": {}, "table_of_contents": []}
    for original in payload["passages"]:
        pid, text = original["id"], original["text"]
        reviewed = review["passages"][pid]
        if (sha(text) != reviewed["input_sha256"] or sha(original.get("source_text", "")) != reviewed["source_text_sha256"]
                or original["title"] != reviewed["title"]):
            raise ValueError("GA027 unreviewed input text/source/title drift: " + pid)
        starts = deepcopy(reviewed["starts"])
        if pid == review["table"]["passage_id"]:
            table_start, table_end, table = table_segments(text, review["table"])
            starts.append({"start_codepoint": table_start, "kind": "table", "page": 140})
            starts.sort(key=lambda row: row["start_codepoint"])
        if starts[0]["start_codepoint"] != 0 or len({row["start_codepoint"] for row in starts}) != len(starts):
            raise ValueError("GA027 ambiguous first/duplicate paragraph boundary")
        plan = {"input_sha256": sha(text), "source_text_sha256": reviewed["source_text_sha256"],
                "group_title": original["title"], "segments": [], "edits": []}
        for index, start in enumerate(starts):
            begin = start["start_codepoint"]
            end = starts[index + 1]["start_codepoint"] if index + 1 < len(starts) else len(text)
            if not 0 <= begin < end <= len(text):
                raise ValueError("GA027 invalid reviewed paragraph boundary")
            if start["kind"] == "table":
                if text[table_end:end].strip():
                    raise ValueError("GA027 unconsumed table continuation")
                plan["segments"].extend(table)
                continue
            # Exact source prefix must still begin at this canonical position;
            # only physical whitespace differs between retained OCR and input.
            prefix = re.sub(r"\s+", " ", text[begin:begin + len(start["anchor"]) + 20])
            if not prefix.startswith(" ".join(start["anchor"].split())):
                raise ValueError("GA027 canonical paragraph anchor drift")
            segment = {"kind": start["kind"], "parts": parts_between(text, begin, end), "join": " ",
                       "source_pdf_pages": [start["page"]],
                       "evidence": f"Reviewed1991facsimile source-page-{start['page']} source line{start['source_line']}: {start['kind']} start; original indentation/standalone placement."}
            if start["kind"] == "heading":
                segment["level"] = 2
            plan["segments"].append(segment)
        plan["edits"] = [{key: repair[key] for key in ("old", "new", "evidence")}
                         for repair in review["word_seams"] if repair["passage_id"] == pid]
        rendered = deepcopy(original)
        apply_passage_plan(rendered, plan, "preview")
        plan["output_sha256"] = sha(rendered["text"])
        recipe["passages"][pid] = plan
        recipe["table_of_contents"].append({"id": pid, "title": original["title"], "level": 1,
                                             "passage_id": pid, "start_offset": 0, "parent_id": None})
    return recipe


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=BASELINE)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--review", type=Path, default=REVIEW)
    parser.add_argument("--output", type=Path, default=RECIPE)
    args = parser.parse_args()
    recipe = build(read_json(args.input), args.source, read_json(args.review))
    args.output.write_text(json.dumps(recipe, ensure_ascii=False, indent=2) + "\n")
    print(f"GA027: {len(recipe['passages'])} passages; {sum(len(p['segments']) for p in recipe['passages'].values())} reviewed blocks")
