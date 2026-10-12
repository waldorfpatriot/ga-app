#!/usr/bin/env python3
"""Apply the reviewed GA 014 dramatic layout after its original-outline pass.

The frozen recipe retains verse lines, reflows prose and stage directions, and
removes exact running heads evidenced at PDF page boundaries. Keep a separate
post-outline input so earlier correction layers remain independently auditable.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil

from finalize_library import content_file, read_json, write_json, verify
from repair_source_structure import apply_recipe, recipe_digest

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "tools/ga014_structure.json"
BASELINE = ROOT / "research/proofreading-ga014-baseline"
RULE = "ga014_readability"
LABEL = "GA 014: Versdialoge, Prosareden und Regieanweisungen quellengebunden gesetzt"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def preserve_baseline(payload, baseline=BASELINE):
    path = baseline / "content/ga-014.json.gz"
    if path.exists():
        if read_json(path) != payload:
            raise ValueError("GA 014 readability input differs; preserve a new reviewed edition separately")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, payload)
    return digest(path.read_bytes())


def apply_layout(payload, recipe=None):
    recipe = recipe or read_json(RECIPE)
    corrected, changes = apply_recipe(payload, recipe)
    originals = {p["id"]: p for p in payload["passages"]}
    passages = {p["id"]: p for p in corrected["passages"]}
    for change in changes:
        pid = change["passage_id"]
        change.update(rule=RULE, label=LABEL,
                      newlines_before=originals[pid]["text"].count("\n"),
                      newlines_after=passages[pid]["text"].count("\n"))
    return corrected, changes


def stage(root, output, recipe=None, baseline=BASELINE):
    from proofread_library import complete_stage
    recipe = recipe or read_json(RECIPE)
    if output.exists():
        raise ValueError("Choose a fresh stage; existing results are retained")
    for folder in ("content", "library", "proofreading"):
        shutil.copytree(root / folder, output / folder)
    path = content_file(output, "ga-014")
    detail_path = output / "proofreading/works/ga-014.json"
    detail = read_json(detail_path)
    old_hash = digest(path.read_bytes())
    if old_hash != detail["work"]["after_sha256"]:
        raise ValueError("GA 014 differs from its saved correction ledger")
    current = read_json(path)
    previous_revision = current.get("metadata", {}).get("source_layout", {}).get("recipe_sha256")
    source = current
    if previous_revision and previous_revision != recipe_digest(recipe):
        baseline_path = content_file(baseline, "ga-014")
        if digest(baseline_path.read_bytes()) != detail["work"].get("ga014_input_sha256"):
            raise ValueError("GA 014 revision baseline differs from its saved correction ledger")
        if detail.get("readability_review", {}).get("recipe_sha256") != previous_revision:
            raise ValueError("GA 014 current layout revision differs from its saved correction ledger")
        source = read_json(baseline_path)
        if ([(p["id"], p.get("source_text")) for p in source["passages"]]
                != [(p["id"], p.get("source_text")) for p in current["passages"]]):
            raise ValueError("GA 014 revision would change the original source or passage inventory")
    corrected, changes = apply_layout(source, recipe)
    if changes:
        input_hash = preserve_baseline(source, baseline)
        if previous_revision and previous_revision != recipe_digest(recipe):
            detail.setdefault("readability_history", []).append({
                "recipe_sha256": previous_revision, "result_sha256": old_hash,
                "changes": [change for change in detail["changes"] if change["rule"] == RULE],
                "review": detail.get("readability_review"),
            })
            detail["changes"] = [change for change in detail["changes"] if change["rule"] != RULE]
        write_json(path, corrected)
        detail["changes"].extend(changes)
        detail["work"].update(application_base_sha256=old_hash,
                              ga014_input_sha256=input_hash,
                              after_sha256=digest(path.read_bytes()))
        detail["readability_review"] = {
            "recipe_sha256": recipe_digest(recipe),
            "evidence": recipe.get("source_evidence", recipe.get("evidence", [])),
            "known_gaps": recipe.get("known_gaps", []),
        }
        check = "GA 014: Druckseitenköpfe entfernt; Prosa, Regieanweisungen und Verszeilen getrennt am Faksimile geprüft"
        if check not in detail["work"]["checks"]:
            detail["work"]["checks"].append(check)
        catalog_path = output / "library/catalog.json"
        catalog = read_json(catalog_path)
        work = next(w for w in catalog["works"] if w["id"] == "ga-014")
        summaries = {p["id"]: p for p in work["passages"]}
        for passage in corrected["passages"]:
            summaries[passage["id"]].update(title=passage["title"], checksum=passage["checksum"], ga_page=passage["ga_page"])
        write_json(catalog_path, catalog)
        write_json(detail_path, detail)
    previous_date = read_json(output / "proofreading/catalog.json").get("generated_at")
    complete_stage(output, generated_at=None if changes else previous_date)
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
    print(f"GA 014: {len(changes)} sections corrected in {args.output}")
