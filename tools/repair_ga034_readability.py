#!/usr/bin/env python3
"""Stage the complete source-reviewed GA034 paragraph and verse repair."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil

from build_ga034_recipe import ROOT, SOURCE, REVIEW, RECIPE, apply_metadata_repairs, apply_annotation_repairs, check_source, augment_original
from finalize_library import content_file, read_json, write_json, verify
from repair_source_structure import apply_recipe, recipe_digest, sha, validate_layout

BASELINE = ROOT / "research/proofreading-layout-baseline"
CHECK = "GA 034: sämtliche erhaltenen Absätze, Artikelüberschriften, Verszeilen und physischen Fugen an Originalquellen geprüft"


def assert_output_metadata(passage, plan):
    actual = {"title": passage["title"], "ga_page": passage["ga_page"],
              "page_numbers": passage["metadata"]["page_numbers"]}
    if actual != plan["output_metadata"]:
        raise ValueError("GA034 rendered source metadata drift: " + passage["id"])


def apply_layout(payload, recipe=None):
    recipe = recipe or read_json(RECIPE)
    revision = recipe_digest(recipe)
    repeated = payload.get("metadata", {}).get("source_layout", {}).get("recipe_sha256") == revision
    if (payload["work_id"] != recipe["work_id"]
            or [p["id"] for p in payload["passages"]] != list(recipe["passages"])
            or any(payload.get(key) != recipe[key] for key in ("source_sha256", "source_epub_sha256"))):
        raise ValueError("GA034 original source/passage inventory drift")
    work = deepcopy(payload) if repeated else augment_original(payload, recipe)
    for passage in work["passages"]:
        plan = recipe["passages"].get(passage["id"])
        if plan is None or recipe_digest(passage["metadata"]["annotations"]) != plan[
                "annotations_output_sha256" if repeated else "annotations_input_sha256"]:
            raise ValueError("GA034 original/rendered annotation inventory drift: " + passage["id"])
    if repeated:
        if [p["id"] for p in work["passages"]] != list(recipe["passages"]):
            raise ValueError("GA034 retained passage sequence changed")
        for passage in work["passages"]:
            plan = recipe["passages"][passage["id"]]
            if sha(passage["text"]) != plan["output_sha256"] or sha(passage["source_text"]) != plan["source_text_sha256"]:
                raise ValueError("GA034 rendered text/source drift")
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
    if recipe.get("source_additions"):
        result["metadata"]["source_layout"].update(source_restoration_count=len(recipe["source_additions"]), original_passage_ids=list(recipe["original_passages"]))
        if not repeated:
            for addition in recipe["source_additions"]:
                changes.append({"passage_id": addition["passage_id"], "rule": "source_restoration", "count": 1,
                    "label": "Exakt belegten Originalquellentext wiederhergestellt", "addition_id": addition["id"],
                    "source_text_sha256": addition["source_text_sha256"], "text_sha256": addition["text_sha256"],
                    "before_excerpt": "", "after_excerpt": addition["text"][:440], "evidence": addition["evidence"]})
    return result, changes



if __name__ == "__main__":
    import json
    parser = argparse.ArgumentParser(description="Preview the source-reviewed GA034 reading repair")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result, changes = apply_layout(read_json(args.input))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"GA034: {len(result['passages'])} passages; {len(changes)} evidenced events")
