#!/usr/bin/env python3
"""Apply edition-bound prose joins for GA 050+, retaining reviewed verse gaps.

The portable recipe records newline ordinals and exact running-head removals.
It never guesses again during application, and retains an immutable input for
independent comparison with every earlier proofreading layer.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil

from finalize_library import content_file, read_json, write_json, verify

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "tools/ga050_plus_sentence_breaks.json"
BASELINE = ROOT / "research/proofreading-sentence-baseline"
RULE = "prose_sentence_breaks"
LABEL = "GA 050+: Satzfortsetzungen verbunden; Verse und strukturierte Zeilen erhalten"
GAPS = re.compile(r"\n+")


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def strip_headers(text, headers):
    if not headers:
        return text
    cursor = 0
    pieces = []
    for header in headers:
        start, end = header["start"], header["end"]
        if not cursor <= start < end <= len(text) or text[start:end] != header["text"]:
            raise ValueError("Running head differs from reviewed exact source")
        pieces.extend((text[cursor:start], "\ufdd5"))
        cursor = end
    pieces.append(text[cursor:])
    # Collapse only the gap created by a removed page label. Other stanza
    # separators, including three or more newlines, remain literal source text.
    return re.sub(r"\n*\ufdd5\n*", "\n\n", "".join(pieces)).strip()


def transform(text, plan):
    if digest(text) != plan["text_sha256"]:
        raise ValueError("Sentence repair requires the frozen input text")
    text = strip_headers(text, plan.get("removed_headers", []))
    if digest(text) != plan["headerless_sha256"]:
        raise ValueError("Headerless text differs from reviewed input")
    matches = list(GAPS.finditer(text))
    joins = plan["joins"]
    if joins != sorted(set(joins)) or any(type(i) is not int or not 0 <= i < len(matches) for i in joins):
        raise ValueError("Invalid or repeated sentence-boundary ordinal")
    selected = set(joins)
    pieces = []
    cursor = 0
    for i, match in enumerate(matches):
        if i in selected:
            pieces.extend((text[cursor:match.start()], " "))
            cursor = match.end()
    pieces.append(text[cursor:])
    result = "".join(pieces)
    if digest(result) != plan["result_sha256"]:
        raise ValueError("Sentence repair result differs from frozen recipe")
    return result


def apply_plan(payload, plan):
    if payload["work_id"] != plan["work_id"] or payload.get("source_epub_sha256") != plan["source_epub_sha256"]:
        raise ValueError("Sentence repair edition identity differs")
    result = deepcopy(payload)
    if plan.get("final_passages") and all(
            p["checksum"] == plan["final_passages"][p["id"]]["checksum"]
            and p["title"] == plan["final_passages"][p["id"]]["title"]
            for p in payload["passages"]):
        return result, []
    originals = {p["id"]: p for p in payload["passages"]}
    if set(plan["passages"]) - set(originals):
        raise ValueError("Sentence recipe contains an unknown passage")
    changes = []
    for passage in result["passages"]:
        recipe = plan["passages"].get(passage["id"])
        if recipe is None:
            continue
        old = originals[passage["id"]]
        if digest(old.get("source_text", "")) != recipe["source_text_sha256"]:
            raise ValueError("Retained source differs from sentence recipe")
        if old["checksum"] == recipe["result_sha256"]:
            continue
        text = transform(old["text"], recipe)
        # Only exactly recorded navigation furniture may remove visible text.
        expected = strip_headers(old["text"], recipe.get("removed_headers", []))
        if re.sub(r"\s", "", expected) != re.sub(r"\s", "", text):
            raise ValueError("Sentence repair changed spelling or punctuation")
        passage.update(text=text, checksum=digest(text))
        changes.append({
            "passage_id": passage["id"], "rule": RULE, "label": LABEL,
            "count": len(recipe["joins"]) + len(recipe.get("removed_headers", [])),
            "joined_boundaries": len(recipe["joins"]),
            "running_headers_removed": len(recipe.get("removed_headers", [])),
            "newlines_before": old["text"].count("\n"), "newlines_after": text.count("\n"),
            "before_excerpt": recipe["before_excerpt"], "after_excerpt": recipe["after_excerpt"],
        })
    passages = {p["id"]: p for p in result["passages"]}
    for bridge in plan.get("bridges", []):
        left, right = passages[bridge["left_id"]], passages[bridge["right_id"]]
        prefix = bridge["right_prefix"]
        if not right["text"].startswith(prefix):
            raise ValueError("Section continuation differs from reviewed leading text")
        restored_title = originals[right["id"]]["title"] if bridge.get("restore_right_title") else ""
        continuation = " ".join(part for part in (restored_title, prefix) if part)
        if not continuation:
            raise ValueError("Section continuation contains no source text")
        old_texts = {p["id"]: p["text"] for p in (left, right)}
        left["text"] += " " + continuation
        right["text"] = right["text"][len(prefix):].lstrip()
        if "right_title" in bridge:
            right["title"] = bridge["right_title"]
        for p in (left, right):
            if not p["text"].strip():
                raise ValueError("Section continuation would empty a reading passage")
            p["checksum"] = digest(p["text"])
            changes.append({"passage_id": p["id"], "rule": "sentence_section_boundary",
                            "label": "Satzfortsetzung an fehlerhafter Abschnittsgrenze wiederhergestellt",
                            "count": 1, "section_boundary_repairs": 1,
                            "before_excerpt": old_texts[p["id"]][-400:] if p is left else old_texts[p["id"]][:400],
                            "after_excerpt": p["text"][-400:] if p is left else p["text"][:400]})
    if plan.get("final_passages") and any(
            p["checksum"] != plan["final_passages"][p["id"]]["checksum"]
            or p["title"] != plan["final_passages"][p["id"]]["title"]
            for p in result["passages"]):
        raise ValueError("Section repair differs from frozen final passage signatures")
    return result, changes


def preserve_baseline(payload, baseline=BASELINE):
    path = baseline / "content" / (payload["work_id"] + ".json.gz")
    if path.exists():
        if read_json(path) != payload:
            raise ValueError("Preserved pre-sentence text differs; keep a separate edition baseline")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, payload)
    return digest(path.read_bytes())


def stage(root, output, recipe, baseline=BASELINE):
    from proofread_library import complete_stage
    if output.exists():
        raise ValueError("Choose a fresh stage; previous results are preserved")
    for folder in ("content", "library", "proofreading"):
        shutil.copytree(root / folder, output / folder)
    previous_date = read_json(output / "proofreading/catalog.json").get("generated_at")
    (output / "proofreading/catalog.json").unlink()
    catalog_path = output / "library/catalog.json"
    catalog = read_json(catalog_path)
    work_map = {w["id"]: w for w in catalog["works"]}
    counts = Counter()
    for work_id, plan in recipe["works"].items():
        path = content_file(output, work_id)
        detail_path = output / "proofreading/works" / (work_id + ".json")
        detail = read_json(detail_path)
        current_hash = digest(path.read_bytes())
        if current_hash != detail["work"]["after_sha256"]:
            raise ValueError("Working content differs from saved correction ledger: " + work_id)
        payload = read_json(path)
        corrected, changes = apply_plan(payload, plan)
        if changes:
            input_hash = preserve_baseline(payload, baseline)
            write_json(path, corrected)
            detail["changes"].extend(changes)
            detail["work"].update(application_base_sha256=current_hash,
                                  sentence_input_sha256=input_hash,
                                  after_sha256=digest(path.read_bytes()))
            detail["sentence_review"] = {"recipe_sha256": digest(json.dumps(plan, ensure_ascii=False, sort_keys=True)),
                                         "protected_regions": plan.get("protected_regions", [])}
            check = "GA 050+: Satzgrenzen geprüft; lyrische, tabellarische und sonstige bewusst strukturierte Umbrüche erhalten"
            if check not in detail["work"]["checks"]:
                detail["work"]["checks"].append(check)
            summaries = {p["id"]: p for p in work_map[work_id]["passages"]}
            for p in corrected["passages"]:
                summaries[p["id"]].update(checksum=p["checksum"], title=p["title"])
            write_json(detail_path, detail)
        counts["works"] += bool(changes)
        counts["passages"] += len({c["passage_id"] for c in changes})
        counts["joined_boundaries"] += sum(c.get("joined_boundaries", 0) for c in changes)
        counts["removed_headers"] += sum(c.get("running_headers_removed", 0) for c in changes)
        counts["section_boundary_repairs"] += sum(c.get("section_boundary_repairs", 0) for c in changes) // 2
    write_json(catalog_path, catalog)
    complete_stage(output, generated_at=None if counts["works"] else previous_date)
    verify(output)
    return dict(counts)


def apply_verified_stage(root, output, recipe, baseline=BASELINE, recipe_path=RECIPE):
    """Apply this band range while preserving simultaneous earlier-band edits."""
    from check_sentence_breaks import validate
    from proofread_library import complete_stage
    checked = validate(baseline, output, recipe_path)
    if checked["status"] != "passed":
        raise ValueError("Sentence stage did not pass independent validation")
    verify(output)
    targets = []
    for work_id, plan in recipe["works"].items():
        source = content_file(output, work_id)
        current = content_file(root, work_id)
        detail_path = output / "proofreading/works" / (work_id + ".json")
        detail = read_json(detail_path)
        if digest(source.read_bytes()) != detail["work"]["after_sha256"]:
            raise ValueError("Sentence stage changed after validation")
        # The baseline is serialized anew with deterministic gzip; its file
        # hash can differ even when the preserved payload is identical. Check
        # the original working file's recorded bytes, not the cache container.
        if digest(current.read_bytes()) not in {detail["work"]["application_base_sha256"], detail["work"]["after_sha256"]}:
            raise ValueError("Working volume changed during sentence review: " + work_id)
        targets.append((work_id, source, current, detail_path))
    catalog_path = root / "library/catalog.json"
    catalog = read_json(catalog_path)
    works = {w["id"]: w for w in catalog["works"]}
    counts = {}
    for work_id, source, current, detail_path in targets:
        if current.read_bytes() != source.read_bytes():
            temporary = current.with_name(current.name + ".sentence-tmp")
            shutil.copyfile(source, temporary)
            temporary.replace(current)
        detail_target = root / "proofreading/works" / detail_path.name
        temporary = detail_target.with_name(detail_target.name + ".sentence-tmp")
        shutil.copyfile(detail_path, temporary)
        temporary.replace(detail_target)
        payload = read_json(source)
        summaries = {p["id"]: p for p in works[work_id]["passages"]}
        for p in payload["passages"]:
            summaries[p["id"]].update(checksum=p["checksum"], title=p["title"])
        counts[work_id] = sum(len(p["text"]) for p in payload["passages"])
    write_json(catalog_path, catalog)
    for filename in ("import-report.json", "recovery-import-report.json"):
        path = root / "library" / filename
        if path.exists():
            imported = read_json(path)
            for w in imported.get("works", []):
                if w["id"] in counts:
                    w["character_count"] = counts[w["id"]]
            write_json(path, imported)
    complete_stage(root, generated_at=read_json(output / "proofreading/catalog.json")["generated_at"])
    return checked["summary"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "server/priv")
    parser.add_argument("--recipe", type=Path, default=RECIPE)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apply-stage", type=Path)
    args = parser.parse_args()
    if args.apply_stage:
        print(json.dumps(apply_verified_stage(args.root, args.apply_stage, read_json(args.recipe), args.baseline, args.recipe), ensure_ascii=False))
    elif args.output:
        print(json.dumps(stage(args.root, args.output, read_json(args.recipe), args.baseline), ensure_ascii=False))
    else:
        parser.error("Provide --output for a staged repair or --apply-stage for the verified result")
