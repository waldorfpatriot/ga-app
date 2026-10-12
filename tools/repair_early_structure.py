#!/usr/bin/env python3
"""Restore the reviewed original outline of GA 001–026 without moving text.

The portable recipe binds every heading to the retained edition, passage IDs,
text checksums and UTF-16 offsets. Import containers need not be chapters:
empty parent headings and internal insertions are separate contents entries.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

from finalize_library import content_file, read_json, write_json, verify
from repair_source_structure import utf16, validate_layout

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "tools/ga001_026_structure.json"
BASELINE = ROOT / "research/proofreading-outline-baseline"


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode("utf-8")).hexdigest()


def revision(plan):
    return digest(json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def preserve_baseline(payload, baseline=BASELINE):
    path = baseline / "content" / (payload["work_id"] + (".json" if payload["work_id"] in {"ga-003", "ga-004", "ga-009", "ga-010", "ga-013"} else ".json.gz"))
    if path.exists():
        if read_json(path) != payload:
            raise ValueError("Preserved pre-outline content differs: " + payload["work_id"])
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, payload)
    return digest(path.read_bytes())


def validate_outline(payload, entries):
    passages = {p["id"]: p for p in payload["passages"]}
    seen = {}
    for entry in entries:
        passage = passages.get(entry["passage_id"])
        if passage is None or not entry["id"] or entry["id"] in seen or not entry["title"].strip():
            raise ValueError("Invalid or duplicate original heading")
        if type(entry["level"]) is not int or not 1 <= entry["level"] <= 6:
            raise ValueError("Invalid original heading level")
        offset = entry["start_offset"]
        if type(offset) is not int or not 0 <= offset < utf16(passage["text"]):
            raise ValueError("Original heading target is outside its passage")
        try:
            passage["text"].encode("utf-16-le")[:2 * offset].decode("utf-16-le")
        except UnicodeDecodeError as error:
            raise ValueError("Original heading target splits a surrogate") from error
        parent = entry["parent_id"]
        if parent is not None and (parent not in seen or seen[parent]["level"] >= entry["level"]):
            raise ValueError("Original parent must precede and contain its child")
        seen[entry["id"]] = entry


def apply_plan(payload, plan):
    if payload["work_id"] != plan["work_id"]:
        raise ValueError("Outline recipe identity differs")
    for key, value in plan["source_identity"].items():
        if payload.get(key) != value:
            raise ValueError("Outline edition/hash differs: " + payload["work_id"])
    if list(plan["passages"]) != [p["id"] for p in payload["passages"]]:
        raise ValueError("Outline recipe passage sequence differs")
    result = deepcopy(payload)
    recipe_hash = revision(plan)
    for passage in result["passages"]:
        section = plan["passages"][passage["id"]]
        if digest(passage["text"]) != section["text_sha256"] or digest(passage.get("source_text", "")) != section["source_text_sha256"]:
            raise ValueError("Original outline anchors require reviewed text: " + passage["id"])
        passage["title"] = section["title"]
        metadata = passage.setdefault("metadata", {})
        for key in ("reading_blocks", "group_title", "continuation_of", "source_dateline"):
            if key in section:
                metadata[key] = deepcopy(section[key])
        validate_layout(passage)
    result["table_of_contents"] = deepcopy(plan["table_of_contents"])
    result.setdefault("metadata", {})["source_outline"] = {
        "recipe_sha256": recipe_hash, "offset_unit": "utf16",
        "scope": "original_headings_numbering_hierarchy_and_insertions",
        "edition": plan.get("edition"), "evidence": plan["evidence"],
    }
    validate_outline(result, result["table_of_contents"])
    changes = []
    if result != payload:
        for old, new in zip(payload["passages"], result["passages"]):
            old_entries = [e for e in payload.get("table_of_contents", []) if e["passage_id"] == old["id"]]
            new_entries = [e for e in result["table_of_contents"] if e["passage_id"] == new["id"]]
            if old != new or old_entries != new_entries:
                changes.append({
                    "passage_id": new["id"], "rule": "source_outline", "count": 1,
                    "label": "Originale Überschriften, Nummerierung und Gliederung wiederhergestellt",
                    "before_excerpt": old["title"],
                    "after_excerpt": "\n".join(e["title"] for e in new_entries),
                    "recipe_sha256": recipe_hash, "text_unchanged": True,
                })
    return result, changes


def stage(root, output, recipe, baseline=BASELINE):
    from proofread_library import complete_stage
    if output.exists():
        raise ValueError("Choose a fresh stage")
    for folder in ("content", "library", "proofreading"):
        shutil.copytree(root / folder, output / folder)
    catalog = read_json(output / "library/catalog.json")
    total = 0
    for work_id, plan in recipe["works"].items():
        path = content_file(output, work_id)
        old = read_json(path)
        detail_path = output / "proofreading/works" / (work_id + ".json")
        detail = read_json(detail_path)
        if digest(path.read_bytes()) != detail["work"]["after_sha256"]:
            raise ValueError("Current payload differs from its correction ledger: " + work_id)
        baseline_path = baseline / "content" / path.name
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        previous = old.get("metadata", {}).get("source_outline")
        source = old
        if previous:
            if not baseline_path.exists() or digest(baseline_path.read_bytes()) != detail["work"].get("outline_input_sha256"):
                raise ValueError("Revising an outline requires its preserved, checked input: " + work_id)
            source = read_json(baseline_path)
        new, changes = apply_plan(source, plan)
        if work_id == "ga-014" and old.get("metadata", {}).get("source_layout"):
            # A repeated outline pass must retain the later dramatic layout.
            # Its frozen input guards a changed outline/edition for review.
            from repair_ga014_readability import apply_layout, BASELINE as dramatic_baseline
            dramatic_path = content_file(dramatic_baseline, work_id)
            if (digest(dramatic_path.read_bytes()) != detail["work"].get("ga014_input_sha256")
                    or read_json(dramatic_path) != new):
                raise ValueError("Changed GA 014 outline requires a matching reviewed dramatic layout input")
            new, _ = apply_layout(new)
        if new == old:
            continue
        if not previous:
            if baseline_path.exists() and baseline_path.read_bytes() != path.read_bytes():
                raise ValueError("Preserved pre-outline payload differs: " + work_id)
            baseline_path.write_bytes(path.read_bytes())
        else:
            detail.setdefault("outline_history", []).append({
                "recipe_sha256": previous["recipe_sha256"], "result_sha256": digest(path.read_bytes()),
                "changes": [event for event in detail["changes"] if event["rule"] == "source_outline"],
            })
        old_hash = digest(path.read_bytes())
        write_json(path, new)
        detail["changes"] = [event for event in detail["changes"] if event["rule"] != "source_outline"] + changes
        detail["work"].update(application_base_sha256=old_hash,
                              outline_input_sha256=digest(baseline_path.read_bytes()),
                              after_sha256=digest(path.read_bytes()))
        check = "Originale Nummerierung und Kapitelhierarchie am Quellenbestand geprüft; Buchtext und Notizanker unverändert"
        if check not in detail["work"]["checks"]:
            detail["work"]["checks"].append(check)
        detail["outline_review"] = {"recipe_sha256": revision(plan), "findings": plan.get("findings", []), "known_gaps": plan.get("known_gaps", [])}
        write_json(detail_path, detail)
        work = next(w for w in catalog["works"] if w["id"] == work_id)
        summaries = {s["id"]: s for s in work["passages"]}
        for passage in new["passages"]:
            summaries[passage["id"]]["title"] = passage["title"]
        total += len(changes)
    write_json(output / "library/catalog.json", catalog)
    previous_date = read_json(output / "proofreading/catalog.json").get("generated_at")
    complete_stage(output, generated_at=None if total else previous_date)
    verify(output)
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "server/priv")
    parser.add_argument("--recipe", type=Path, default=RECIPE)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    count = stage(args.root, args.output, read_json(args.recipe), args.baseline)
    if args.apply:
        from proofread_library import apply_stage
        apply_stage(args.root, args.output)
    print(json.dumps({"changed_passages": count, "stage": str(args.output)}))
