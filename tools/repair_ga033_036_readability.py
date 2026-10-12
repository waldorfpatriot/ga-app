#!/usr/bin/env python3
"""Stage the four source-reviewed essay volumes together before application."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from importlib import import_module
from pathlib import Path
import shutil

from finalize_library import content_file, read_json, write_json, verify
from repair_source_structure import recipe_digest

ROOT = Path(__file__).resolve().parents[1]
WORK_IDS = ("ga-033", "ga-034", "ga-035", "ga-036")
BASELINE = ROOT / "research/proofreading-layout-baseline"


def stage(root, output, baseline=BASELINE):
    from proofread_library import complete_stage, preserve_layout_baseline
    if output.exists():
        raise ValueError("Choose a fresh stage; existing results are retained")
    prepared = []
    for work_id in WORK_IDS:
        code = work_id.replace("-", "")
        builder = import_module("build_" + code + "_recipe")
        wrapper = import_module("repair_" + code + "_readability")
        recipe, review = read_json(builder.RECIPE), read_json(builder.REVIEW)
        if recipe["source_evidence"]["review_sha256"] != recipe_digest(review):
            raise ValueError(work_id + ": frozen review differs from its recipe")
        for key in ("metadata_repairs", "annotation_repairs", "known_gaps", "review_flags"):
            if recipe.get(key, []) != review.get(key, []):
                raise ValueError(work_id + ": original review contract differs: " + key)
        builder.check_source(builder.SOURCE, review)
        current_path = content_file(root, work_id)
        current_hash = hashlib.sha256(current_path.read_bytes()).hexdigest()
        current = read_json(current_path)
        detail = read_json(root / "proofreading/works" / (work_id + ".json"))
        if current_hash != detail["work"]["after_sha256"]:
            raise ValueError(work_id + ": content differs from its saved correction ledger")
        previous_revision = current.get("metadata", {}).get("source_layout", {}).get("recipe_sha256")
        if previous_revision:
            baseline_path = content_file(baseline, work_id)
            input_hash = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
            if input_hash != detail["work"].get("layout_input_sha256"):
                raise ValueError(work_id + ": original layout input hash differs")
            source = read_json(baseline_path)
            original_ids = {passage["id"] for passage in source["passages"]}
            if [(p["id"], p["source_text"]) for p in source["passages"]] != [
                    (p["id"], p["source_text"]) for p in current["passages"] if p["id"] in original_ids]:
                raise ValueError(work_id + ": retained passage/source inventory differs")
            if previous_revision == recipe_digest(recipe):
                payload, changes = wrapper.apply_layout(current, recipe)
            else:
                payload, changes = wrapper.apply_layout(source, recipe)
                superseded = [event for event in detail["changes"] if event["rule"] == "source_layout"]
                detail.setdefault("structure_history", []).append({"recipe_sha256": previous_revision,
                    "result_sha256": current_hash, "changes": superseded})
                detail["changes"] = [event for event in detail["changes"] if event["rule"] != "source_layout"]
        else:
            payload, changes = wrapper.apply_layout(current, recipe)
            input_hash = preserve_layout_baseline(current, baseline)
        prepared.append((work_id, current_hash, input_hash, payload, changes, detail, wrapper.CHECK))
    for folder in ("content", "library", "proofreading"):
        shutil.copytree(root / folder, output / folder)
    catalog_path = output / "library/catalog.json"
    catalog = read_json(catalog_path)
    totals = {}
    for work_id, current_hash, input_hash, payload, changes, detail, check in prepared:
        path = content_file(output, work_id)
        write_json(path, payload)
        work = next(work for work in catalog["works"] if work["id"] == work_id)
        if [p["id"] for p in work["passages"]] != [p["id"] for p in payload["passages"]]:
            if work_id != "ga-033" or [p["id"] for p in payload["passages"] if p["id"] !=
                    "ga-033-schopenhauer-bibliographisches"] != [p["id"] for p in work["passages"]]:
                raise ValueError(work_id + ": catalog passage inventory/order differs")
            work["passages"] = [{key: passage.get(key) for key in
                                ("id", "title", "ga_page", "source_label", "checksum")}
                               for passage in payload["passages"]]
            work["catalog_passage_count"] = len(payload["passages"])
            work["content_completeness"] = payload.get("content_completeness")
        for summary, passage in zip(work["passages"], payload["passages"]):
            summary.update(title=passage["title"], ga_page=passage["ga_page"], checksum=passage["checksum"])
        detail["changes"].extend(deepcopy(changes))
        if changes:
            detail["work"].update(application_base_sha256=current_hash, layout_input_sha256=input_hash)
        detail["work"]["after_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        detail["work"]["passage_count"] = len(payload["passages"])
        if check not in detail["work"].setdefault("checks", []):
            detail["work"]["checks"].append(check)
        write_json(output / "proofreading/works" / (work_id + ".json"), detail)
        totals[work_id] = len(changes)
    write_json(catalog_path, catalog)
    complete_stage(output, generated_at=None if any(totals.values()) else
                   read_json(output / "proofreading/catalog.json").get("generated_at"))
    verify(output)
    return totals


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "server/priv")
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.root, args.output, args.baseline))
