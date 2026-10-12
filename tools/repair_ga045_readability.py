#!/usr/bin/env python3
"""Stage the source-reviewed GA045 paragraph, list and word-seam repair."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil

from build_ga045_recipe import ROOT, SOURCE, REVIEW, RECIPE, apply_metadata_repairs, apply_annotation_repairs, check_source, augment_original
from finalize_library import content_file, read_json, write_json, verify
from repair_source_structure import apply_recipe, recipe_digest, sha, validate_layout

BASELINE = ROOT / "research/proofreading-layout-baseline"
CHECK = "GA 045: erhaltene Absätze, Varianten, Listen, Schemata und physische Wortfugen an Original-DOC und EPUB geprüft"


def assert_output_metadata(passage, plan):
    actual = {"title": passage["title"], "ga_page": passage["ga_page"],
              "page_numbers": passage["metadata"]["page_numbers"]}
    if actual != plan["output_metadata"]:
        raise ValueError("GA045 rendered source metadata drift: " + passage["id"])


def apply_layout(payload, recipe=None):
    recipe = recipe or read_json(RECIPE)
    revision = recipe_digest(recipe)
    repeated = payload.get("metadata", {}).get("source_layout", {}).get("recipe_sha256") == revision
    if (payload["work_id"] != recipe["work_id"]
            or [p["id"] for p in payload["passages"]] != list(recipe["passages"])
            or any(payload.get(key) != recipe[key] for key in ("source_sha256", "source_epub_sha256"))):
        raise ValueError("GA045 original source/passage inventory drift")
    work = deepcopy(payload) if repeated else augment_original(payload, recipe)
    for passage in work["passages"]:
        plan = recipe["passages"].get(passage["id"])
        if plan is None or recipe_digest(passage["metadata"]["annotations"]) != plan[
                "annotations_output_sha256" if repeated else "annotations_input_sha256"]:
            raise ValueError("GA045 original/rendered annotation inventory drift: " + passage["id"])
    if repeated:
        if [p["id"] for p in work["passages"]] != list(recipe["passages"]):
            raise ValueError("GA045 retained passage sequence changed")
        for passage in work["passages"]:
            plan = recipe["passages"][passage["id"]]
            if sha(passage["text"]) != plan["output_sha256"] or sha(passage["source_text"]) != plan["source_text_sha256"]:
                raise ValueError("GA045 rendered text/source drift")
            assert_output_metadata(passage, plan)
            validate_layout(passage)
    else:
        apply_metadata_repairs(work, recipe.get("metadata_repairs", []))
    # Detach annotations from the generic engine. Only separately reviewed,
    # exact physical whitespace repairs may change their imported text.
    annotations = {p["id"]: p["metadata"].pop("annotations", []) for p in work["passages"]}
    result, changes = apply_recipe(work, recipe)
    for passage in result["passages"]:
        passage["metadata"]["annotations"] = annotations[passage["id"]]
        assert_output_metadata(passage, recipe["passages"][passage["id"]])
        validate_layout(passage)
    apply_annotation_repairs(result, recipe.get("annotation_repairs", []), repeated=repeated)
    for event in changes:
        metadata_repairs = [deepcopy(repair) for repair in recipe.get("metadata_repairs", [])
                            if repair["passage_id"] == event["passage_id"]]
        if metadata_repairs:
            event["metadata_replacements"] = metadata_repairs
        annotation_repairs = [deepcopy(repair) for repair in recipe.get("annotation_repairs", [])
                              if repair["passage_id"] == event["passage_id"]]
        if annotation_repairs:
            event["annotation_replacements"] = annotation_repairs
        fragments = [deepcopy(repair) for repair in recipe["passages"][event["passage_id"]]["edits"]
                     if repair.get("kind") == "pdf_fragment_restoration"]
        if fragments:
            event["source_fragment_restorations"] = fragments
    result["metadata"]["source_layout"].update(source_epub_sha256=recipe["source_epub_sha256"],
        review_sha256=recipe["source_evidence"]["review_sha256"],
        source_evidence=deepcopy(recipe["source_evidence"]))
    result["metadata"]["source_layout"].update(source_restoration_count=len(recipe["source_additions"]),
        original_passage_ids=list(recipe["original_passages"]))
    if not repeated:
        for addition in recipe["source_additions"]:
            changes.append({"passage_id": addition["passage_id"], "rule": "source_restoration", "count": 1,
                "label": "Exakt belegten Originalquellentext wiederhergestellt", "addition_id": addition["id"],
                "source_text_sha256": addition["source_text_sha256"], "text_sha256": addition["text_sha256"],
                "before_excerpt": "", "after_excerpt": addition["text"][:440], "evidence": addition["evidence"]})
    return result, changes


def stage(root, output, recipe=None, baseline=BASELINE):
    from proofread_library import complete_stage, preserve_layout_baseline
    recipe = recipe or read_json(RECIPE)
    review = read_json(REVIEW)
    if recipe["source_evidence"]["review_sha256"] != recipe_digest(review):
        raise ValueError("GA045 recipe differs from its frozen source review")
    for key in ("metadata_repairs", "annotation_repairs"):
        if recipe.get(key, []) != review.get(key, []):
            raise ValueError("GA045 original metadata/annotation review differs: " + key)
    check_source(SOURCE, review)
    if output.exists():
        raise ValueError("Choose a fresh stage; existing results are retained")
    current_path = content_file(root, "ga-045")
    current_hash = hashlib.sha256(current_path.read_bytes()).hexdigest()
    detail = read_json(root / "proofreading/works/ga-045.json")
    if current_hash != detail["work"]["after_sha256"]:
        raise ValueError("GA045 content differs from its saved correction ledger")
    current = read_json(current_path)
    previous_revision = current.get("metadata", {}).get("source_layout", {}).get("recipe_sha256")
    if previous_revision:
        baseline_path = content_file(baseline, "ga-045")
        input_hash = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
        if input_hash != detail["work"].get("layout_input_sha256"):
            raise ValueError("GA045 preserved original layout input hash differs")
        source = read_json(baseline_path)
        annotation_projection = deepcopy(source)
        if previous_revision == recipe_digest(recipe):
            apply_annotation_repairs(annotation_projection, recipe.get("annotation_repairs", []))
        else:
            old_annotation_repairs = [repair for event in detail["changes"] if event["rule"] == "source_layout"
                                      for repair in event.get("annotation_replacements", [])]
            apply_annotation_repairs(annotation_projection, old_annotation_repairs)
        if [(p["id"], p["source_text"], p["metadata"]["annotations"]) for p in annotation_projection["passages"]] != [
                (p["id"], p["source_text"], p["metadata"]["annotations"]) for p in current["passages"]]:
            raise ValueError("GA045 original source/passage/annotation inventory changed")
        if previous_revision == recipe_digest(recipe):
            payload, changes = apply_layout(current, recipe)
        else:
            payload, changes = apply_layout(source, recipe)
            superseded = [c for c in detail["changes"] if c["rule"] == "source_layout"]
            detail.setdefault("structure_history", []).append({"recipe_sha256": previous_revision,
                "result_sha256": current_hash, "changes": superseded})
            detail["changes"] = [c for c in detail["changes"] if c["rule"] != "source_layout"]
    else:
        payload, changes = apply_layout(current, recipe)
        input_hash = preserve_layout_baseline(current, baseline)
    for folder in ("content", "library", "proofreading"):
        shutil.copytree(root / folder, output / folder)
    staged = content_file(output, "ga-045")
    write_json(staged, payload)
    catalog_path = output / "library/catalog.json"
    catalog = read_json(catalog_path)
    work = next(w for w in catalog["works"] if w["id"] == "ga-045")
    if [p["id"] for p in work["passages"]] != [p["id"] for p in payload["passages"]]:
        raise ValueError("GA045 catalog passage sequence changed")
    for summary, passage in zip(work["passages"], payload["passages"]):
        summary.update(title=passage["title"], ga_page=passage["ga_page"], checksum=passage["checksum"])
    write_json(catalog_path, catalog)
    detail["changes"].extend(changes)
    if changes:
        detail["work"]["application_base_sha256"] = current_hash
        detail["work"]["layout_input_sha256"] = input_hash
    detail["work"]["after_sha256"] = hashlib.sha256(staged.read_bytes()).hexdigest()
    if CHECK not in detail["work"].setdefault("checks", []):
        detail["work"]["checks"].append(CHECK)
    write_json(output / "proofreading/works/ga-045.json", detail)
    complete_stage(output, generated_at=None if changes else read_json(output / "proofreading/catalog.json").get("generated_at"))
    verify(output)
    return changes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "server/priv")
    parser.add_argument("--recipe", type=Path, default=RECIPE)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    changes = stage(args.root, args.output, read_json(args.recipe), args.baseline)
    print(f"GA045: {len(changes)} recorded layout/restoration changes in {args.output}")
