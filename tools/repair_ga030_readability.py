#!/usr/bin/env python3
"""Stage exact GA030 source restorations, original contents and prose layout."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil

from build_ga030_recipe import ROOT, SOURCE, RECIPE, REVIEW, augment_original, check_source, render_without_annotation_changes
from finalize_library import content_file, read_json, write_json, verify
from repair_source_structure import recipe_digest, sha, validate_layout

BASELINE = ROOT / "research/proofreading-layout-baseline"
CHECK = "GA 030: Originalinhalt, Einführung, Autorenanmerkungen, Herausgeberhinweise, Register und echte Absätze quellengebunden geprüft"


def apply_layout(payload, recipe=None):
    recipe = recipe or read_json(RECIPE)
    revision = recipe_digest(recipe)
    if payload.get("metadata", {}).get("source_layout", {}).get("recipe_sha256") == revision:
        if [p["id"] for p in payload["passages"]] != list(recipe["passages"]):
            raise ValueError("GA030 restored inventory changed")
        for passage in payload["passages"]:
            plan = recipe["passages"][passage["id"]]
            if sha(passage["text"]) != plan["output_sha256"] or sha(passage.get("source_text", "")) != plan["source_text_sha256"]:
                raise ValueError("GA030 rendered text/source drift")
            validate_layout(passage)
        return deepcopy(payload), []
    augmented = augment_original(payload, recipe)
    result, changes = render_without_annotation_changes(augmented, recipe)
    for addition in recipe["source_additions"]:
        changes.append({"passage_id":addition["passage_id"], "rule":"source_restoration", "count":1,
                        "label":"Exakt belegten Originalquellentext wiederhergestellt", "addition_id":addition["id"],
                        "source_text_sha256":addition["source_text_sha256"], "text_sha256":addition["text_sha256"],
                        "before_excerpt":"", "after_excerpt":addition["text"][:440], "evidence":addition["evidence"]})
    result["metadata"]["source_layout"].update(source_epub_sha256=recipe["source_epub_sha256"],
        source_restoration_count=len(recipe["source_additions"]), original_passage_ids=list(recipe["original_passages"]))
    result["content_completeness"] = "complete"
    result["proofing"]["restored_sections"] = [{"id":a["id"], "passage_id":a["passage_id"],
        "source_role":a.get("source_role", "author"), "evidence":a["evidence"]} for a in recipe["source_additions"]]
    result["proofing"]["known_source_gaps"] = deepcopy(recipe["known_gaps"])
    return result, changes


def stage(root, output, recipe=None, baseline=BASELINE):
    from proofread_library import complete_stage, preserve_layout_baseline
    recipe = recipe or read_json(RECIPE)
    review = read_json(REVIEW)
    if recipe["source_evidence"]["review_sha256"] != recipe_digest(review):
        raise ValueError("GA030 recipe differs from its frozen source review")
    for key in ("source_additions", "original_passages", "original_metadata_repairs", "proofing_repairs", "known_gaps", "review_flags"):
        if recipe.get(key) != review.get(key):
            raise ValueError("GA030 exact source restoration review differs: " + key)
    check_source(SOURCE, review)
    if output.exists(): raise ValueError("Choose a fresh stage; existing results are retained")
    path = content_file(root, "ga-030")
    current_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    detail = read_json(root / "proofreading/works/ga-030.json")
    if current_hash != detail["work"]["after_sha256"]:
        raise ValueError("GA030 content differs from its saved correction ledger")
    current = read_json(path)
    revision = current.get("metadata", {}).get("source_layout", {}).get("recipe_sha256")
    source = current
    if revision:
        source_path = content_file(baseline, "ga-030")
        input_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if input_hash != detail["work"].get("layout_input_sha256"):
            raise ValueError("GA030 original restoration input hash differs")
        source = read_json(source_path)
        if [(p["id"],p["source_text"]) for p in source["passages"]] != [(p["id"],p["source_text"]) for p in current["passages"] if p["id"] in recipe["original_passages"]]:
            raise ValueError("GA030 retained original source/inventory differs")
        if revision == recipe_digest(recipe):
            apply_layout(current, recipe)
            payload, changes = current, []
        else:
            payload, changes = apply_layout(source, recipe)
            previous = [c for c in detail["changes"] if c["rule"] in ("source_layout", "source_restoration")]
            detail.setdefault("structure_history", []).append({"recipe_sha256":revision,"result_sha256":current_hash,"changes":previous})
            detail["changes"] = [c for c in detail["changes"] if c["rule"] not in ("source_layout", "source_restoration")]
    else:
        payload, changes = apply_layout(source, recipe)
        input_hash = preserve_layout_baseline(source, baseline)
    for folder in ("content", "library", "proofreading"):
        shutil.copytree(root/folder, output/folder)
    staged = content_file(output, "ga-030")
    write_json(staged, payload)
    catalog_path = output / "library/catalog.json"
    catalog = read_json(catalog_path)
    work = next(w for w in catalog["works"] if w["id"] == "ga-030")
    work["passages"] = [{k:p.get(k) for k in ("id","title","ga_page","source_label","checksum")} for p in payload["passages"]]
    work["catalog_passage_count"] = len(payload["passages"])
    work["content_completeness"] = payload["content_completeness"]
    write_json(catalog_path, catalog)
    detail["changes"].extend(changes)
    if changes:
        detail["work"]["application_base_sha256"] = current_hash
        detail["work"]["layout_input_sha256"] = input_hash
    detail["work"].update(after_sha256=hashlib.sha256(staged.read_bytes()).hexdigest(), passage_count=len(payload["passages"]))
    if CHECK not in detail["work"].setdefault("checks", []): detail["work"]["checks"].append(CHECK)
    write_json(output / "proofreading/works/ga-030.json", detail)
    for filename in ("import-report.json", "recovery-import-report.json"):
        report_path = output / "library" / filename
        if report_path.exists():
            report = read_json(report_path)
            for row in report.get("works", []):
                if row["id"] == "ga-030": row["passage_count"] = len(payload["passages"])
            if "passage_count" in report: report["passage_count"] = sum(r.get("passage_count",0) for r in report.get("works",[]))
            write_json(report_path, report)
    complete_stage(output, generated_at=None if changes else read_json(output/"proofreading/catalog.json").get("generated_at"))
    verify(output)
    return changes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=ROOT/"server/priv")
    parser.add_argument("--recipe",type=Path,default=RECIPE)
    parser.add_argument("--baseline",type=Path,default=BASELINE)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    changes=stage(args.root,args.output,read_json(args.recipe),args.baseline)
    print(f"GA030: {len(changes)} layout/restoration events staged in {args.output}")
