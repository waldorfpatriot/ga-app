#!/usr/bin/env python3
"""Independently check the frozen GA 050+ sentence-boundary repair layer.

This validator reads retained inputs, the portable recipe and the final payloads.
It does not import or invoke the sentence repair implementation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "research/proofreading-sentence-baseline"
RECIPE = ROOT / "tools/ga050_plus_sentence_breaks.json"
PAGE_LABELS = ROOT / "tools/ga050_plus_page_labels.json"
VERIFIED_FURNITURE_KINDS = {"source_verified_page_label", "page_label", "source_verified_page_furniture"}


def read(path: Path) -> dict:
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def content_file(root: Path, work_id: str) -> Path:
    for extension in (".json.gz", ".json"):
        path = root / "content" / (work_id + extension)
        if path.is_file():
            return path
    raise FileNotFoundError(f"Missing retained content: {work_id} in {root}")


def sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


@lru_cache(maxsize=1)
def reviewed_page_labels() -> dict:
    """Index the separately reviewed, exact source page-label deletions."""
    records = read(PAGE_LABELS)
    if not isinstance(records, list):
        raise ValueError("Reviewed page-label list has an invalid schema")
    indexed = {}
    for record in records:
        key = tuple(record[k] for k in ("work_id", "passage_id", "start", "end", "text", "input_sha256"))
        if key in indexed:
            raise ValueError("Reviewed page-label list includes a duplicate deletion")
        indexed[key] = record
    return indexed


def safe_header(work_id: str, text: str, record: dict | None = None) -> bool:
    """Allow only the independently identified running-head/page-number forms."""
    text = text.strip()
    if record and record.get("kind") in VERIFIED_FURNITURE_KINDS:
        evidence = record.get("evidence")
        if not isinstance(evidence, list) or not evidence or any(
            not isinstance(item, dict)
            or not isinstance(item.get("source_member"), str) or not item["source_member"]
            or not isinstance(item.get("source_excerpt"), str) or not item["source_excerpt"]
            for item in evidence
        ):
            return False
        if record["kind"] in {"source_verified_page_label", "page_label"}:
            return bool(re.fullmatch(r"\d{1,4}", text))
        return work_id == "ga-301" and bool(re.fullmatch(
            r"DIE ERNEUERUNG DER PÄDAGOGISCH-DIDAKTISCHEN KUNST\nErster Vortrag\n_{5,}\n[23]", text))
    names = {
        "ga-101": "Mythen und Sagen Okkulte Zeichen und Symbole",
        "ga-103": "Das Johannes-Evangelium",
        "ga-104": "Die Apokalypse des Johannes",
        "ga-265": "Zur Geschichte und aus den Inhalten der Esot. Schule 19041914",
    }
    if work_id in names:
        number = int(work_id[3:])
        title = re.escape(names[work_id])
        if work_id == "ga-101":
            title = r"Myt(?:\n\nhen|hen) und Sagen Okkulte Zeichen und Symbole"
        elif work_id == "ga-104":
            title += r"(?: Ergänzungen)?"
        elif work_id == "ga-265":
            title = r"Zur Geschichte und aus den Inhalten der (?:Esot\.|Esoterischen) Schule 19041914"
        return bool(re.fullmatch(rf"GA {number} {title}\nSeite \d{{1,4}}(?: \[vakat\])?(?:\n_{{5,}})?", text))
    if work_id == "ga-323":
        return bool(re.fullmatch(r"GA 323 - 1983 - Seite \d{1,4}\nIII\. Naturwissenschaftlicher Kurs", text))
    if work_id == "ga-337b":
        return text.isdigit() and (125 <= int(text) <= 264 or text == "46")
    titles = {
        "ga-195": "WELTSILVESTER UND NEUJAHRSGEDANKEN",
        "ga-301": "DIE ERNEUERUNG DER PÄDAGOGISCH-DIDAKTISCHEN KUNST",
    }
    if work_id in titles:
        return bool(re.fullmatch(re.escape(titles[work_id]) + r"\n(?:[A-Za-zÄÖÜäöüß ]+Vortrag|Fragenbeantwortungen)\n_{5,}", text))
    return False


def inspect_sentence_layer(prior: dict, final: dict, recipe: dict,
                           events: dict | None = None) -> tuple[list[str], dict]:
    """Reconstruct every recorded edit and verify protected literal fragments."""
    errors = []
    counts = Counter()
    work_id = prior.get("work_id")
    if recipe.get("work_id") != work_id or prior.get("source_epub_sha256") != recipe.get("source_epub_sha256"):
        return ["Sentence recipe differs from retained edition identity"], dict(counts)
    if [p["id"] for p in prior["passages"]] != [p["id"] for p in final["passages"]]:
        return ["Sentence layer changed passage IDs/order"], dict(counts)
    if {k: v for k, v in prior.items() if k != "passages"} != {k: v for k, v in final.items() if k != "passages"}:
        errors.append("Sentence layer changed non-passage document data")
    originals = {p["id"]: p for p in prior["passages"]}
    corrected = {p["id"]: p for p in final["passages"]}
    if set(recipe["passages"]) - set(originals):
        errors.append("Sentence recipe includes an unknown passage")
    projected = {}
    expected_events = {}
    expected_final = deepcopy(prior)
    expected_passages = {p["id"]: p for p in expected_final["passages"]}
    bridge_titles = {b["right_id"]: b["right_title"] for b in recipe.get("bridges", []) if "right_title" in b}
    for passage_id, before in originals.items():
        after = corrected[passage_id]
        if {k: v for k, v in before.items() if k not in {"text", "checksum", "title"}} != {k: v for k, v in after.items() if k not in {"text", "checksum", "title"}}:
            errors.append(f"{passage_id}: sentence layer changed source_text/pages/annotations or other metadata")
        if after.get("title") != bridge_titles.get(passage_id, before.get("title")):
            errors.append(f"{passage_id}: title differs from exact reviewed section-boundary title")
        if before.get("checksum") != sha(before["text"]) or after.get("checksum") != sha(after["text"]):
            errors.append(f"{passage_id}: input/result checksum mismatch")
        plan = recipe["passages"].get(passage_id)
        if plan is None:
            bridge_ids = {b[key] for b in recipe.get("bridges", []) for key in ("left_id", "right_id")}
            if before != after and passage_id not in bridge_ids:
                errors.append(f"{passage_id}: passage changed without a sentence recipe")
            continue
        text = before["text"]
        if sha(text) != plan.get("text_sha256") or sha(before.get("source_text", "")) != plan.get("source_text_sha256"):
            errors.append(f"{passage_id}: recipe input/source hash mismatch")
            continue
        headers = plan.get("removed_headers", [])
        cursor, kept = 0, []
        valid = True
        for header in headers:
            start, end = header.get("start"), header.get("end")
            if type(start) is not int or type(end) is not int or not cursor <= start < end <= len(text) or text[start:end] != header.get("text"):
                errors.append(f"{passage_id}: invalid, reordered or changed exact running header")
                valid = False
                break
            if not safe_header(work_id, header["text"], header):
                errors.append(f"{passage_id}: running header is not an independently allowed safe form: {header['text'][:120]!r}")
            if header.get("kind") in VERIFIED_FURNITURE_KINDS:
                try:
                    key = (work_id, passage_id, start, end, header["text"], sha(text))
                    reviewed = reviewed_page_labels().get(key)
                    if reviewed is None or reviewed.get("source_evidence") != header.get("evidence"):
                        errors.append(f"{passage_id}: page furniture differs from separately reviewed exact source evidence")
                except (ValueError, FileNotFoundError, KeyError, TypeError) as error:
                    errors.append(f"{passage_id}: cannot verify reviewed page furniture: {error}")
            kept.append(text[cursor:start])
            kept.append("\ufdd5")
            cursor = end
        if not valid:
            continue
        kept.append(text[cursor:])
        headerless = re.sub(r"\n*\ufdd5\n*", "\n\n", "".join(kept)).strip() if headers else text
        if sha(headerless) != plan.get("headerless_sha256"):
            errors.append(f"{passage_id}: headerless recipe hash mismatch")
        gaps = list(re.finditer(r"\n+", headerless))
        joins = plan.get("joins", [])
        if not isinstance(joins, list) or any(type(i) is not int for i in joins) or joins != sorted(set(joins)) or any(i < 0 or i >= len(gaps) for i in joins):
            errors.append(f"{passage_id}: invalid or duplicate newline ordinal")
            continue
        # Captured gap tokens alternate with ordinary text. Replacing tokens
        # provides an independent linear-time projection for very long works.
        tokens = re.split(r"(\n+)", headerless)
        for ordinal in joins:
            tokens[2 * ordinal + 1] = " "
        rebuilt = "".join(tokens)
        if sha(rebuilt) != plan.get("result_sha256"):
            errors.append(f"{passage_id}: independently reconstructed sentence result differs")
        if re.sub(r"\s", "", headerless) != re.sub(r"\s", "", rebuilt):
            errors.append(f"{passage_id}: sentence layer changed letters, spelling or punctuation")
        projected[passage_id] = (headerless, gaps, set(joins), rebuilt)
        expected_passages[passage_id].update(text=rebuilt, checksum=sha(rebuilt))
        changed = text != rebuilt
        if changed:
            expected_events[passage_id] = (len(joins), len(headers), len(joins) + len(headers))
        counts["passages"] += changed
        counts["joined_boundaries"] += len(joins)
        counts["removed_headers"] += len(headers)
    bridge_events = Counter()
    bridge_moves = defaultdict(list)
    local_texts = {pid: p["text"] for pid, p in expected_passages.items()}
    restored_titles = defaultdict(list)
    for bridge in recipe.get("bridges", []):
        left_id, right_id = bridge["left_id"], bridge["right_id"]
        ordered_ids = list(originals)
        if left_id not in originals or right_id not in originals or ordered_ids.index(right_id) != ordered_ids.index(left_id) + 1:
            errors.append("Section boundary recipe does not connect adjacent original passages")
            continue
        left, right = expected_passages[left_id], expected_passages[right_id]
        prefix = bridge["right_prefix"]
        if not isinstance(prefix, str) or not right["text"].startswith(prefix):
            errors.append(f"{right_id}: section continuation differs from reviewed prefix")
            continue
        title = originals[right_id]["title"] if bridge.get("restore_right_title") else ""
        if title:
            restored_titles[right_id].append(title)
        continuation = (title + " " + prefix).strip() if title else prefix
        if not continuation:
            errors.append(f"{right_id}: empty section continuation")
            continue
        left["text"] = left["text"] + " " + continuation
        right["text"] = right["text"][len(prefix):].lstrip()
        bridge_moves[right_id].append((left_id, prefix))
        if "right_title" in bridge:
            right["title"] = bridge["right_title"]
        if not right["text"]:
            errors.append(f"{right_id}: section boundary repair emptied a passage")
        for p in (left, right):
            p["checksum"] = sha(p["text"])
            bridge_events[p["id"]] += 1
        counts["section_boundary_repairs"] += 1
    conserved_input = "".join("".join(restored_titles[pid]) + local_texts[pid] for pid in originals)
    conserved_result = "".join(expected_passages[pid]["text"] for pid in originals)
    if re.sub(r"\s", "", conserved_input) != re.sub(r"\s", "", conserved_result):
        errors.append("Section-boundary layer did not conserve work text including exact restored source titles")
    for passage_id, expected in expected_passages.items():
        if expected != corrected[passage_id]:
            errors.append(f"{passage_id}: independent complete sentence/section result differs")
        signature = recipe.get("final_passages", {}).get(passage_id)
        if signature is not None and any(expected[key] != signature.get(key) for key in ("checksum", "title")):
            errors.append(f"{passage_id}: final frozen passage signature differs")
    for region in recipe.get("protected_regions", []):
        passage_id = region["passage_id"]
        original = originals.get(passage_id)
        if original is None:
            errors.append(f"{passage_id}: protected region references an unknown passage")
            continue
        text = original["text"]
        a, b = region["start_codepoint"], region["end_codepoint"]
        if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(text) or sha(text) != region.get("text_sha256") or sha(text[a:b]) != region.get("fragment_sha256"):
            errors.append(f"{passage_id}: protected source extent or hash differs")
            continue
        if passage_id not in projected:
            if text != corrected[passage_id]["text"]:
                errors.append(f"{passage_id}: protected passage was changed without checked projection")
            counts["protected_regions"] += 1
            continue
        headerless, gaps, joins, rebuilt = projected[passage_id]
        left, right = region["headerless_start"], region["headerless_end"]
        if type(left) is not int or type(right) is not int or not 0 <= left < right <= len(headerless):
            errors.append(f"{passage_id}: invalid headerless protected extent")
            continue
        fragment = headerless[left:right]
        if fragment.strip("\n") != text[a:b].strip("\n"):
            errors.append(f"{passage_id}: protected source fragment changed during header removal")
        if any(gaps[i].start() <= right and gaps[i].end() >= left for i in joins):
            errors.append(f"{passage_id}: recorded join overlaps protected verse/layout region or its separating boundary")
        shift = sum(len(gaps[i][0]) - 1 for i in joins if gaps[i].end() <= left)
        if rebuilt[left - shift:right - shift] != fragment:
            errors.append(f"{passage_id}: protected literal text/linebreaks changed")
        if fragment not in expected_passages[passage_id]["text"]:
            moved_intact = any(
                right - shift <= len(prefix)
                and prefix[left - shift:right - shift] == fragment
                and fragment in expected_passages[target]["text"]
                for target, prefix in bridge_moves[passage_id]
            )
            if not moved_intact:
                errors.append(f"{passage_id}: section-boundary move affected protected verse/layout fragment")
        counts["protected_regions"] += 1
    if events is not None:
        actual_events = {pid: [event for event in items if event.get("rule") == "prose_sentence_breaks"] for pid, items in events.items()}
        actual_events = {pid: items for pid, items in actual_events.items() if items}
        if set(actual_events) != set(expected_events):
            errors.append("Sentence correction ledger passage inventory differs")
        for passage_id, expected in expected_events.items():
            items = actual_events.get(passage_id, [])
            if len(items) != 1 or tuple(items[0].get(k) for k in ("joined_boundaries", "running_headers_removed", "count")) != expected:
                errors.append(f"{passage_id}: sentence ledger counts differ from recorded edits")
        recorded_bridges = {pid: [e for e in items if e.get("rule") == "sentence_section_boundary"] for pid, items in events.items()}
        recorded_bridges = {pid: items for pid, items in recorded_bridges.items() if items}
        if {pid: len(items) for pid, items in recorded_bridges.items()} != dict(bridge_events):
            errors.append("Section-boundary correction ledger inventory/counts differ")
        if any(e.get("count") != 1 or e.get("section_boundary_repairs") != 1 for items in recorded_bridges.values() for e in items):
            errors.append("Section-boundary correction ledger contains an invalid event")
    counts["works"] = int(bool(expected_events or bridge_events))
    return errors, dict(counts)


def validate(baseline: Path, stage: Path, recipe_path: Path) -> dict:
    if not (stage / "proofreading/catalog.json").is_file():
        raise ValueError("Stage is incomplete: proofreading/catalog.json does not exist. No validation claimed.")
    recipe = read(recipe_path)
    if recipe.get("schema_version") != 1:
        raise ValueError("Unsupported sentence recipe schema")
    catalog = {w["id"]: w for w in read(stage / "library/catalog.json")["works"]}
    errors, totals, work_results = [], Counter(), []
    for work_id, plan in recipe["works"].items():
        source_path = content_file(baseline, work_id)
        prior, final = read(source_path), read(content_file(stage, work_id))
        ledger = read(stage / "proofreading/works" / (work_id + ".json"))
        events = defaultdict(list)
        for event in ledger["changes"]:
            events[event["passage_id"]].append(event)
        problems, counts = inspect_sentence_layer(prior, final, plan, events)
        if sha(source_path.read_bytes()) != ledger["work"].get("sentence_input_sha256"):
            problems.append("Sentence input file hash differs from retained baseline")
        if sha(content_file(stage, work_id).read_bytes()) != ledger["work"]["after_sha256"]:
            problems.append("Final payload hash differs from correction ledger")
        summaries = {p["id"]: p for p in catalog[work_id]["passages"]}
        if list(summaries) != [p["id"] for p in final["passages"]]:
            problems.append("Catalog sentence passage IDs/order differ")
        for p in final["passages"]:
            if summaries.get(p["id"], {}).get("checksum") != sha(p["text"]):
                problems.append(f"{p['id']}: catalog checksum differs from final text")
            if any(summaries.get(p["id"], {}).get(key) != p.get(key) for key in ("title", "ga_page")):
                problems.append(f"{p['id']}: catalog title/page differs from final passage")
        totals.update(counts)
        work_results.append({"work_id": work_id, "status": "failed" if problems else "passed", **counts})
        errors.extend({"work_id": work_id, "detail": problem} for problem in problems)
    return {"status": "failed" if errors else "passed", "summary": dict(totals), "problems": errors, "works": work_results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--stage", type=Path, default=Path("/tmp/ga050-plus-sentence-stage"))
    parser.add_argument("--recipe", type=Path, default=RECIPE)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    try:
        report = validate(args.baseline, args.stage, args.recipe)
    except (ValueError, FileNotFoundError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
    if args.json_output:
        args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("status", "summary", "problems")}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["status"] == "passed" else 1)
