#!/usr/bin/env python3
"""Render only the source-bound GA033 layout; the caller owns corpus staging."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

from build_ga033_recipe import (ROOT, SOURCE, RECIPE, REVIEW, BASELINE, augment_original,
    apply_metadata_repairs, apply_annotation_repairs, check_source)
from finalize_library import read_json, write_json
from repair_source_structure import apply_recipe, recipe_digest, sha, validate_layout

CHECK = "GA 033: Originalinhalt, Absätze, Verse, Fugen und Schopenhauer-Unterabschnitt quellengebunden geprüft"


def assert_output_metadata(passage, plan):
    actual = {"title": passage["title"], "ga_page": passage["ga_page"], "page_numbers": passage["metadata"]["page_numbers"]}
    if actual != plan["output_metadata"]:
        raise ValueError("GA033 rendered source metadata drift")


def apply_layout(payload, recipe=None):
    recipe = recipe or read_json(RECIPE)
    revision = recipe_digest(recipe)
    if any(payload.get(k) != recipe[k] for k in ("work_id", "source_sha256", "source_epub_sha256")):
        raise ValueError("GA033 original source identity drift")
    repeated = payload.get("metadata", {}).get("source_layout", {}).get("recipe_sha256") == revision
    if repeated:
        if [p["id"] for p in payload["passages"]] != list(recipe["passages"]):
            raise ValueError("GA033 rendered passage inventory drift")
        if payload.get("table_of_contents") != recipe.get("table_of_contents"):
            raise ValueError("GA033 rendered original contents drift")
        for passage in payload["passages"]:
            plan = recipe["passages"][passage["id"]]
            if sha(passage["text"]) != plan["output_sha256"] or sha(passage["source_text"]) != plan["source_text_sha256"]:
                raise ValueError("GA033 rendered reading/source drift")
            assert_output_metadata(passage, plan)
            if recipe_digest(passage["metadata"]["annotations"]) != plan["annotations_output_sha256"]:
                raise ValueError("GA033 rendered annotation drift")
            validate_layout(passage)
        return deepcopy(payload), []
    work = augment_original(payload, recipe)
    apply_metadata_repairs(work, recipe.get("metadata_repairs", []))
    annotations = {p["id"]: p["metadata"].pop("annotations") for p in work["passages"]}
    result, changes = apply_recipe(work, recipe)
    for passage in result["passages"]:
        passage["metadata"]["annotations"] = annotations[passage["id"]]
        assert_output_metadata(passage, recipe["passages"][passage["id"]])
        validate_layout(passage)
    apply_annotation_repairs(result, recipe.get("annotation_repairs", []))
    for event in changes:
        for key, label in (("metadata_repairs", "metadata_replacements"), ("annotation_repairs", "annotation_replacements")):
            repairs = [deepcopy(r) for r in recipe.get(key, []) if r["passage_id"] == event["passage_id"]]
            if repairs:
                event[label] = repairs
    for a in recipe["source_additions"]:
        changes.append({"passage_id": a["passage_id"], "rule": "source_restoration", "count": 1,
            "label": "Exakt belegten Originalquellentext wiederhergestellt", "addition_id": a["id"],
            "source_text_sha256": a["source_text_sha256"], "text_sha256": a["text_sha256"],
            "before_excerpt": "", "after_excerpt": a["text"][:440], "evidence": a["evidence"]})
    result["metadata"]["source_layout"].update(source_epub_sha256=recipe["source_epub_sha256"],
        review_sha256=recipe["source_evidence"]["review_sha256"], source_evidence=deepcopy(recipe["source_evidence"]),
        source_restoration_count=1, original_passage_ids=list(recipe["original_passages"]))
    return result, changes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=BASELINE)
    parser.add_argument("--recipe", type=Path, default=RECIPE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--events", type=Path)
    args = parser.parse_args()
    check_source(SOURCE, read_json(REVIEW))
    result, changes = apply_layout(read_json(args.input), read_json(args.recipe))
    write_json(args.output, result)
    if args.events:
        write_json(args.events, changes)
    print(f"GA033: {len(result['passages'])} passages; {len(changes)} source-bound events")
