#!/usr/bin/env python3
"""Freeze reviewed GA 001–026 heading evidence into a portable outline recipe.

Inputs are explicit source-review JSON files, never a guessed numbering rule.
The resulting recipe needs no EPUB, Word, network or private notes to replay.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re

from finalize_library import content_file, read_json
from repair_early_structure import ROOT, digest, validate_outline
from repair_source_structure import utf16, validate_layout


def reading_blocks(text, entries):
    """Classify only reviewed headings; retain all original body characters."""
    encoded = text.encode("utf-16-le")
    ranges = {}
    for entry in entries:
        start = entry["start_offset"]
        fragment = encoded[2 * start:].decode("utf-16-le")
        heading = entry.get("heading_text", entry["title"])
        end = entry.get("end_offset")
        if end is None and fragment.startswith(heading):
            end = start + utf16(heading)
        if end is None:
            continue  # Source heading is outside this stable text container.
        observed = encoded[2 * start:2 * end].decode("utf-16-le")
        if observed.strip() != heading.strip():
            # Some source headings have explicit line feeds; the title folds
            # that whitespace, while its original text remains untouched.
            if re.sub(r"\s+", " ", observed).strip() != re.sub(r"\s+", " ", heading).strip():
                raise ValueError("Reviewed heading span differs from text: " + entry["id"])
        key = (start, end)
        ranges[key] = min(ranges.get(key, 6), entry["level"])
    if not ranges:
        return None
    headings = sorted((start, end, level) for (start, end), level in ranges.items())
    blocks, cursor = [], 0
    for start, end, level in headings:
        if start < cursor:
            raise ValueError("Reviewed body headings overlap")
        if encoded[2 * cursor:2 * start].decode("utf-16-le").strip():
            blocks.append({"kind": "prose", "start_offset": cursor, "end_offset": start})
        blocks.append({"kind": "heading", "level": level, "start_offset": start, "end_offset": end})
        cursor = end
    if encoded[2 * cursor:].decode("utf-16-le").strip():
        blocks.append({"kind": "prose", "start_offset": cursor, "end_offset": utf16(text)})
    return blocks


def build(review, root):
    recipe = {"schema_version": 1, "scope": "ga-001-through-ga-026", "offset_unit": "utf16", "works": {},
              "unavailable": [{"work_id": "ga-019", "reason": "No retained reader text or source edition in the current catalog."}]}
    for work in review["volumes"]:
        work_id = work["work_id"]
        if work_id == "ga-019":
            recipe["unavailable"][0]["findings"] = work.get("known_gaps", [])
            continue
        payload = read_json(content_file(root, work_id))
        entries = deepcopy(work["table_of_contents"])
        validate_outline(payload, entries)
        evidence = []
        for source in work["sources"]:
            source_record = source if isinstance(source, dict) else {"path": source}
            source_name = source_record["path"]
            source_path = Path(source_name)
            if not source_path.is_absolute():
                source_path = ROOT / source_path
            checksum = digest(source_path.read_bytes())
            if source_record.get("sha256") and source_record["sha256"] != checksum:
                raise ValueError("Reviewed source evidence has changed")
            if source_path.is_relative_to(ROOT):
                source_name = str(source_path.relative_to(ROOT))
            evidence.append({"path": source_name, "sha256": checksum, **({"kind": source_record["kind"]} if "kind" in source_record else {})})
        plan = {"work_id": work_id, "edition": work.get("edition"), "evidence": evidence,
                "source_identity": {k: payload.get(k) for k in ("source_id", "source_url", "source_sha256", "source_epub_sha256")},
                "passages": {}, "table_of_contents": entries,
                "findings": work.get("findings", work.get("notes", [])), "known_gaps": work.get("known_gaps", [])}
        by_id = {entry["id"]: entry for entry in entries}
        parent_ids = {entry["parent_id"] for entry in entries if entry["parent_id"]}
        for passage in payload["passages"]:
            anchored = [e for e in entries if e["passage_id"] == passage["id"]]
            own = next((e for e in anchored if e["id"] == passage["id"] and e["start_offset"] == 0), None)
            if own is None:
                # The outline has its own stable IDs; a parent and its first
                # child can legitimately jump to the same text position.
                own = next((e for e in anchored if e["start_offset"] == 0 and e["id"] not in parent_ids), None)
                if own is None:
                    own = next((e for e in reversed(anchored) if e["start_offset"] == 0), None)
            title = work.get("title_updates", {}).get(passage["id"], own["title"] if own else passage["title"])
            section = {"text_sha256": digest(passage["text"]), "source_text_sha256": digest(passage.get("source_text", "")), "title": title}
            if passage["id"] in work.get("dateline_updates", {}):
                section["source_dateline"] = work["dateline_updates"][passage["id"]]
            if title != passage["title"] and re.fullmatch(r"\([^)]*\d{4}\)", passage["title"]):
                section["source_dateline"] = passage["title"]
            layout = reading_blocks(passage["text"], anchored)
            if layout:
                section["reading_blocks"] = layout
            if own and own["parent_id"]:
                section["group_title"] = by_id[own["parent_id"]]["title"]
            if passage["id"] in work.get("continuations", {}):
                section["continuation_of"] = work["continuations"][passage["id"]]
            for continuation in work.get("continuation_passages", []):
                if continuation["passage_id"] == passage["id"]:
                    section["continuation_of"] = continuation["continues_passage_id"]
            plan["passages"][passage["id"]] = section
            test_passage = deepcopy(passage)
            if layout:
                test_passage.setdefault("metadata", {})["reading_blocks"] = layout
                validate_layout(test_passage)
        recipe["works"][work_id] = plan
    recipe["works"] = dict(sorted(recipe["works"].items()))
    expected = {f"ga-{i:03}" for i in range(1, 27)} - {"ga-019"}
    if set(recipe["works"]) != expected:
        raise ValueError("The reviewed recipe must cover all 25 available volumes")
    return recipe


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, action="append", required=True)
    parser.add_argument("--root", type=Path, default=ROOT / "server/priv")
    parser.add_argument("--output", type=Path, default=ROOT / "tools/ga001_026_structure.json")
    args = parser.parse_args()
    review = {"volumes": [w for path in args.audit for w in read_json(path)["volumes"]]}
    recipe = build(review, args.root)
    args.output.write_text(json.dumps(recipe, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"works": len(recipe["works"]), "headings": sum(len(w["table_of_contents"]) for w in recipe["works"].values())}))
