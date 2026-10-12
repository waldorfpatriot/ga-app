#!/usr/bin/env python3
"""Use GA 026's reviewed original INHALT labels without changing its text.

The retained contents prefix, EPUB, passage inventory and existing body targets
must match the frozen review. Only the GA 026 navigation labels and corresponding
title/group metadata change; the original body headings remain their witnesses.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from finalize_library import read_json
from repair_early_structure import ROOT, apply_plan, digest, validate_outline

REVIEW = ROOT / "tools/ga026_contents_review.json"
RECIPE = ROOT / "tools/ga001_026_structure.json"
PAYLOAD = ROOT / "server/priv/content/ga-026.json.gz"
SOURCE = ROOT / "research/proofreading-sources/ga-026.epub"
NS = "{http://www.w3.org/1999/xhtml}"


def folded(text):
    return re.sub(r"\s+", " ", text).strip()


def navigation_title(row):
    label = row["original_contents_label"]
    if row["leitsaetze_range"] and row["leitsaetze_range"] != [1, 61]:
        label = row["original_main_title"] + " (LS %d bis %d)" % tuple(row["leitsaetze_range"])
    return label


def validate_source(review, source):
    if digest(source.read_bytes()) != review["source_identity"]["source_epub_sha256"]:
        raise ValueError("GA 026 original contents source EPUB changed")
    with ZipFile(source) as archive:
        front = ET.fromstring(archive.read("EPUB/chapter-0001.xhtml")).find(NS + "body")
        if not any(folded("".join(node.itertext())) == "INHALT" for node in front):
            raise ValueError("Original INHALT heading is missing")
        body = ET.fromstring(archive.read("EPUB/chapter-0002.xhtml")).find(NS + "body")
        expected = [folded(line) for row in review["main_rows"][1:]
                    for line in row["raw_source_paragraphs"]]
        observed = [folded("".join(node.itertext())) for node in body if node.tag == NS + "p"]
        if observed[:len(expected)] != expected:
            raise ValueError("Reviewed contents rows differ from the retained EPUB")
        if not any(node.tag == NS + "h1" and folded("".join(node.itertext())) == "Vorbemerkung"
                   for node in body):
            raise ValueError("Original Vorbemerkung contents label is missing")


def build(recipe, payload, review, source=SOURCE):
    if payload["work_id"] != "ga-026" or review["work_id"] != "ga-026":
        raise ValueError("This contents review is bound to GA 026")
    if any(payload.get(key) != value for key, value in review["source_identity"].items()):
        raise ValueError("GA 026 reviewed source identity differs")
    validate_source(review, source)
    result = deepcopy(recipe)
    plan = result["works"]["ga-026"]
    if plan["source_identity"] != review["source_identity"]:
        raise ValueError("GA 026 outline edition differs")
    frozen = review["preserved_passage_plan"]
    if list(frozen) != list(plan["passages"]) or list(frozen) != [p["id"] for p in payload["passages"]]:
        raise ValueError("GA 026 passage inventory/order differs from contents review")
    passages = {p["id"]: p for p in payload["passages"]}
    for pid, preserved in frozen.items():
        section = plan["passages"][pid]
        if {key: value for key, value in section.items() if key not in {"title", "group_title"}} != preserved:
            raise ValueError("GA 026 original body anchor metadata changed: " + pid)
        if (digest(passages[pid]["text"]) != preserved["text_sha256"]
                or digest(passages[pid].get("source_text", "")) != preserved["source_text_sha256"]):
            raise ValueError("GA 026 retained text/source changed: " + pid)
    anchor = review["contents_anchor"]
    start, end = anchor["source_range"]
    prefix = passages[anchor["passage_id"]]["text"].encode("utf-16-le")[2 * start:2 * end].decode("utf-16-le")
    if start != 0 or end != 2494 or digest(prefix) != anchor["text_sha256"]:
        raise ValueError("GA 026 retained contents prefix differs from the reviewed range")
    rows = review["main_rows"]
    if len(rows) != 35 or [row["order"] for row in rows] != list(range(1, 36)):
        raise ValueError("Original GA 026 contents must have 35 ordered main entries")
    for row in rows:
        label = folded(" ".join(row["raw_source_paragraphs"]))
        match = re.search(r"\(LS (\d+) bis (\d+)\)?$", label)
        expected_range = [int(match[1]), int(match[2])] if match else [1, 61] if label == "Leitsätze 1-61" else None
        expected_title = label[:match.start()].strip() if match else label
        if (row["original_contents_label"] != label or row["original_main_title"] != expected_title
                or row["leitsaetze_range"] != expected_range):
            raise ValueError("GA 026 navigation label/range differs from original contents row")
    covered = [number for row in rows if row["leitsaetze_range"]
               for number in range(row["leitsaetze_range"][0], row["leitsaetze_range"][1] + 1)]
    if covered != list(range(1, 186)):
        raise ValueError("Original GA 026 contents ranges must cover Leitsätze 1–185 once")
    original = deepcopy(review["original_body_outline"])
    mains = [entry for entry in original if entry["level"] == 1]
    if [entry["id"] for entry in mains] != [row["current_navigation_id"] for row in rows]:
        raise ValueError("Reviewed original main targets are out of order")
    titles = {}
    for entry, row in zip(mains, rows):
        if (entry["passage_id"] != row["passage_id"]
                or entry["start_offset"] != row["current_start_offset"]):
            raise ValueError("Reviewed original contents target differs")
        if "end_offset" in entry:
            entry.setdefault("heading_text", entry["title"])
        entry["title"] = navigation_title(row)
        entry["source_evidence"] += "; original INHALT DOC paragraph indexes " + ", ".join(
            str(index) for index in row["doc_paragraph_indexes_zero_based"]) + " govern label and LS range"
        if row["leitsaetze_range"]:
            entry["leitsaetze_range"] = row["leitsaetze_range"]
        titles[entry["id"]] = entry["title"]
    # Main rows above reference copies from original; rebuild by stable ID so
    # all 62 subordinate entries remain byte-for-byte values from the review.
    updated = {entry["id"]: entry for entry in mains}
    contents = [{"id": anchor["id"], "title": anchor["title"], "level": 1,
                 "passage_id": anchor["passage_id"], "start_offset": anchor["start_offset"],
                 "parent_id": None, "source_role": anchor["source_role"],
                 "source_range": anchor["source_range"], "source_evidence": anchor["evidence"]}]
    contents.extend(updated.get(entry["id"], entry) for entry in original)
    parent_ids = {entry["parent_id"] for entry in original if entry["parent_id"]}
    for entry in contents[1:]:
        section = plan["passages"][entry["passage_id"]]
        if entry["level"] == 1 and entry["start_offset"] == 0 and entry["id"] not in parent_ids:
            section["title"] = entry["title"]
        if entry["parent_id"] and "group_title" in section:
            section["group_title"] = titles[entry["parent_id"]]
    # The container includes Inhalt and the author preface. Its title remains
    # Vorbemerkung; the selected contents-role entry supplies the UI caption.
    plan["passages"][anchor["passage_id"]]["title"] = "Vorbemerkung"
    plan["table_of_contents"] = contents
    finding = "Original INHALT supplies 35 main labels and LS ranges; its retained prefix is independently selectable as Inhalt. All 62 subordinate body headings remain unchanged."
    if finding not in plan["findings"]:
        plan["findings"].append(finding)
    plan["known_gaps"] = [{**gap, "reason": "Original source contents remain in the first text container and are separately navigable as Inhalt at offset 0; Vorbemerkung begins at offset 2494. Original body characters and offsets remain unchanged."}
                          if gap.get("passage_id") == anchor["passage_id"] and gap.get("source_range") == [0, 2494]
                          else gap for gap in plan["known_gaps"]]
    review_evidence = {"path": "tools/ga026_contents_review.json", "sha256": digest(
        (json.dumps(review, ensure_ascii=False, indent=2) + "\n").encode()), "kind": "original_contents_label_review"}
    plan["evidence"] = [item for item in plan["evidence"] if item.get("kind") != review_evidence["kind"]] + [review_evidence]
    validate_outline(payload, contents)
    apply_plan(payload, plan)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, default=REVIEW)
    parser.add_argument("--recipe", type=Path, default=RECIPE)
    parser.add_argument("--payload", type=Path, default=PAYLOAD)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=RECIPE)
    args = parser.parse_args()
    result = build(read_json(args.recipe), read_json(args.payload), read_json(args.review), args.source)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"work_id": "ga-026", "contents": len(result["works"]["ga-026"]["table_of_contents"])}))
