#!/usr/bin/env python3
"""Stage the GA027 facsimile-reviewed prose paragraph and page-seam repair."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

from finalize_library import content_file, read_json
from repair_source_structure import apply_recipe, stage as stage_recipe

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "tools/ga027_structure.json"
BASELINE = ROOT / "research/proofreading-layout-baseline"
CHECK = "GA 027: Absatzanfänge, fortlaufende Seitenfugen, Fußnote und Anhangstabelle am Originalfaksimile geprüft"


def apply_layout(payload, recipe=None):
    return apply_recipe(payload, recipe or read_json(RECIPE))


def stage(root, output, recipe=None, baseline=BASELINE):
    from proofread_library import preserve_layout_baseline
    recipe = recipe or read_json(RECIPE)
    path = content_file(root, "ga-027")
    detail = read_json(root / "proofreading/works/ga-027.json")
    if hashlib.sha256(path.read_bytes()).hexdigest() != detail["work"]["after_sha256"]:
        raise ValueError("GA027 content differs from its saved correction ledger")
    payload = read_json(path)
    revision = payload.get("metadata", {}).get("source_layout", {}).get("recipe_sha256")
    input_hash = None
    if not revision:
        # Apply once before preserving the baseline so drift cannot create a
        # misleading witness. The stage engine repeats its exact coverage check.
        apply_layout(payload, recipe)
        input_hash = preserve_layout_baseline(payload, baseline)
    return stage_recipe(root, output, recipe, baseline, preserved_input_sha256=input_hash)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "server/priv")
    parser.add_argument("--recipe", type=Path, default=RECIPE)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    changes = stage(args.root, args.output, read_json(args.recipe), args.baseline)
    print(f"GA027: {len(changes)} passages corrected in {args.output}")
