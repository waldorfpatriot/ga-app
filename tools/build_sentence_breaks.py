#!/usr/bin/env python3
"""Freeze reviewed GA 050+ verse/structure exceptions and prose boundaries.

Inputs are codepoint protection ranges checked against the exact current text.
Application uses the resulting frozen recipe, never these editorial heuristics.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from finalize_library import content_file, read_json
from repair_sentence_breaks import ROOT, RECIPE, GAPS, digest, strip_headers, apply_plan


def running_heads(work_id, text):
    patterns = []
    if work_id in {"ga-101", "ga-103", "ga-104", "ga-265"}:
        number = int(work_id[3:])
        patterns.append(rf"(?m)^GA {number}[^\n]*\nSeite \d{{1,4}}(?: \[vakat\])?(?:\n_+)?")
        if work_id == "ga-101":
            patterns.append(r"(?m)^GA 101 Myt\n\nhen und Sagen Okkulte Zeichen und Symbole\nSeite 019")
    if work_id in {"ga-195", "ga-301"}:
        title = ("WELTSILVESTER UND NEUJAHRSGEDANKEN" if work_id == "ga-195"
                 else "DIE ERNEUERUNG DER PÄDAGOGISCH-DIDAKTISCHEN KUNST")
        patterns.append(rf"(?m)^{title}\n(?:[^\n]*Vortrag|Fragenbeantwortungen)\n_{{20,}}")
    if work_id == "ga-323":
        patterns.append(r"(?m)^GA 323 - 1983 - Seite \d{1,4}\nIII\. Naturwissenschaftlicher Kurs")
    if work_id == "ga-337b":
        patterns.append(r"(?m)^(?:1[2-9]\d|2[0-5]\d|26[0-4]|46)$")
    found = sorted((m.start(), m.end(), m[0]) for pattern in patterns for m in re.finditer(pattern, text))
    return [{"start": start, "end": end, "text": value} for start, end, value in found]


def terminal(left, right):
    trimmed = left.rstrip('»”’"\')]}› ')
    if re.search(r"\b(?:z|B|bzw|d|h|u|a|Dr|Prof|Nr|S|Bd|vgl|ca|geb|gest|sog|resp|ff|Jh|Chr)\.$", trimmed):
        return False
    if re.search(r"\d{1,4}\.$", trimmed) and re.match(r"^(?:bis|oder|und|vorchrist|nachchrist|Jahrhundert|Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\b", right):
        return False
    if re.match(r"^[a-zäöüß]", right) and re.search(r"(?:\b(?:usw|etc)|\b[A-ZÄÖÜ])\.$", trimmed):
        return False
    if trimmed.endswith((".", "!", "?", "…", "...")):
        # A full stop inside a quoted clause need not finish the surrounding
        # sentence: „... .» sagte er“ / „... ?» und ...“.
        if left.rstrip().endswith(('»', '”', '"')) and re.match(r"^[a-zäöüß]", right):
            return False
        return True
    return False


def structural_line(line):
    line = line.strip()
    if not line:
        return False
    letters = re.sub(r"[^a-zA-ZäöüÄÖÜß]", "", line)
    if letters and letters.isupper() and len(letters) > 3:
        return True
    if re.fullmatch(r"[#*_=\-–—\d .,;:/()\[\]IVXLCDM]+", line):
        return True
    if re.match(r"^(?:#Bild|Tafel\s+\d|Abbildung\s+\d)", line):
        return True
    if re.fullmatch(r"(?:(?:[\wÄÖÜäöüß.-]+(?:[ -][\wÄÖÜäöüß.-]+){0,3}),\s+)?(?:[A-ZÄÖÜa-zäöüß]+,\s+)?\d{1,2}\.\s*(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+\d{4}[.,]?(?:\s+(?:vormittags|nachmittags|abends|morgens|\d{1,2}\s*Uhr))?", line):
        return True
    return False


def classify(text, protected, passage_id=None):
    spans = []
    for start, end in sorted(protected):
        if spans and start <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(end, spans[-1][1]))
        else:
            spans.append((start, end))
    starts = [a for a, _ in spans]
    # Explicit protected boundaries include the separating gaps at either edge.
    def protected_gap(gap):
        i = bisect_right(starts, gap.end()) - 1
        return i >= 0 and spans[i][1] >= gap.start()

    joins = []
    kept = Counter()
    suspect = []
    for i, gap in enumerate(GAPS.finditer(text)):
        a = text[max(0, gap.start() - 500):gap.start()]
        b = text[gap.end():gap.end() + 500]
        left = a.rsplit("\n", 1)[-1]
        right = b.split("\n", 1)[0]
        if protected_gap(gap):
            kept["reviewed_verse_or_structure"] += 1
        elif structural_line(left) or structural_line(right):
            kept["heading_date_or_notation"] += 1
        elif re.match(r"^(?:\d+[.)]\s|[a-z]\)\s|(?:Frage|Antwort|Rudolf Steiner|Dr\. [A-ZÄÖÜ][^:]{0,50}):)", right):
            kept["list_or_speaker"] += 1
        elif ((passage_id == "ga-130-doc-heading-7" and left.endswith("so.") and right.startswith("müssen wir"))
              or (passage_id == "ga-150-doc-heading-3" and left.endswith("wenn wir.") and right.startswith("durch den Tod"))):
            joins.append(i)
        elif terminal(left, right):
            kept["sentence_end"] += 1
        else:
            joins.append(i)
            if len(left) < 100 and len(right) < 100:
                suspect.append({"boundary": i, "left": left, "right": right, "context": a[-220:] + "\\n" + b[:220]})
    return joins, dict(kept), suspect


def build(root, protections, continuations=(), page_labels=()):
    grouped = defaultdict(list)
    for entry in protections:
        grouped[entry["passage_id"]].append(entry)
    extra_labels = defaultdict(list)
    for label in page_labels:
        extra_labels[label["passage_id"]].append(label)
    catalog = read_json(root / "library/catalog.json")
    recipe = {"schema_version": 1, "scope": "GA 050 aufwärts, alle vorhandenen deutschen Lesetexte",
              "offset_unit": "codepoints_in_preserved_input", "boundary_unit": "newline_run_ordinal_after_header_removal",
              "policy": "Nur eingefrorene Satzfortsetzungen verbinden; geprüfte Verse, Tabellen, Listen, Notationen und Überschriften erhalten.",
              "works": {}}
    summary = Counter()
    suspicious = []
    for work in catalog["works"]:
        match = re.match(r"ga-(\d+)", work["id"])
        if not match or int(match[1]) < 50:
            continue
        summary["catalog_works"] += 1
        if not work.get("content_path"):
            summary["unavailable_works"] += 1
            continue
        payload = read_json(content_file(root, work["id"]))
        summary["available_works"] += 1
        plan = {"work_id": work["id"], "source_epub_sha256": payload.get("source_epub_sha256"),
                "passages": {}, "protected_regions": []}
        for passage in payload["passages"]:
            summary["audited_passages"] += 1
            text = passage["text"]
            headers = running_heads(work["id"], text)
            for label in extra_labels.get(passage["id"], []):
                if digest(text) != label["input_sha256"] or text[label["start"]:label["end"]] != label["text"]:
                    raise ValueError("Reviewed page number differs from original input")
                headers.append({"start": label["start"], "end": label["end"], "text": label["text"],
                                "kind": "source_verified_page_label" if label["text"].isdigit() else "source_verified_page_furniture",
                                "evidence": label.get("source_evidence", label.get("evidence")),
                                "reason": label.get("reason", "Am Quellenbestand geprüfte Druckseitenzahl")})
            headers.sort(key=lambda h: h["start"])
            merged_headers = []
            for header in headers:
                if merged_headers and header["start"] < merged_headers[-1]["end"]:
                    if header["end"] <= merged_headers[-1]["end"]:
                        continue
                    if header["start"] == merged_headers[-1]["start"]:
                        merged_headers[-1] = header
                        continue
                    raise ValueError("Reviewed page furniture ranges partially overlap")
                merged_headers.append(header)
            headers = merged_headers
            cleaned = strip_headers(text, headers)
            if not cleaned:
                # A standalone source/header container is not an interrupted
                # sentence and must not become an advertised empty section.
                headers, cleaned = [], text
            regions = []
            for region in grouped.get(passage["id"], []):
                pieces = [(region["start_codepoint"], region["end_codepoint"])]
                for header in headers:
                    pieces = [(a, b) for start, end in pieces for a, b in
                              ((start, min(end, header["start"])), (max(start, header["end"]), end)) if a < b]
                for start, end in pieces:
                    if text[start:end].strip():
                        regions.append({**region, "start_codepoint": start, "end_codepoint": end})
            protected = []
            # Locate the exact retained protected fragment after page furniture
            # removal; the original coordinates remain in the recipe's evidence.
            for region in regions:
                if digest(text) != region["text_sha256"]:
                    raise ValueError("Protected region input differs: " + passage["id"])
                start, end = region["start_codepoint"], region["end_codepoint"]
                fragment = text[start:end]
                fragment_cleaned = strip_headers(fragment, running_heads(work["id"], fragment))
                old_prefix = strip_headers(text[:start], [h for h in headers if h["end"] <= start])
                expected_start = len(old_prefix)
                positions = [m.start() for m in re.finditer(re.escape(fragment_cleaned), cleaned)]
                if not positions:
                    raise ValueError("Protected fragment missing after header removal: " + passage["id"])
                where = min(positions, key=lambda pos: abs(pos - expected_start))
                protected.append((where, where + len(fragment_cleaned)))
                plan["protected_regions"].append({**region, "fragment_sha256": digest(fragment),
                                                   "headerless_start": where, "headerless_end": where + len(fragment_cleaned)})
            joins, kept, suspects = classify(cleaned, protected, passage["id"])
            summary.update({"kept_" + k: v for k, v in kept.items()})
            selected = set(joins)
            result = GAPS.sub(lambda m, counter=iter(range(cleaned.count('\n') + 1)): " " if next(counter) in selected else m[0], cleaned)
            if result != text:
                first = next((i for i, (a, b) in enumerate(zip(text, result)) if a != b), min(len(text), len(result)))
                plan["passages"][passage["id"]] = {
                    "text_sha256": digest(text), "source_text_sha256": digest(passage.get("source_text", "")),
                    "headerless_sha256": digest(cleaned), "result_sha256": digest(result),
                    "removed_headers": headers, "joins": joins,
                    "before_excerpt": text[max(0, first - 100):first + 330],
                    "after_excerpt": result[max(0, first - 100):first + 330],
                }
                summary["changed_passages"] += 1
                summary["joined_boundaries"] += len(joins)
                summary["removed_headers"] += len(headers)
            for s in suspects:
                suspicious.append({"work_id": work["id"], "passage_id": passage["id"], **s})
        bridges = [c for c in continuations if c["work_id"] == work["id"]]
        if bridges:
            original_map = {p["id"]: p for p in payload["passages"]}
            local, _ = apply_plan(payload, plan)
            local_map = {p["id"]: p for p in local["passages"]}
            plan["bridges"] = []
            for bridge in bridges:
                left, right = original_map[bridge["left_id"]], original_map[bridge["right_id"]]
                if digest(left["text"]) != bridge["left_text_sha256"] or digest(right["text"]) != bridge["right_text_sha256"] or right["title"] != bridge["right_original_title"]:
                    raise ValueError("Section continuation input differs from reviewed source")
                original_prefix = right["text"][:bridge["end_codepoint"]]
                # Locate the same visible source characters after local reflow,
                # keeping verse separators literal inside a transferred prefix.
                required = len(re.sub(r"\s", "", original_prefix))
                lexical, end = 0, 0
                normalized = local_map[right["id"]]["text"]
                while lexical < required and end < len(normalized):
                    lexical += not normalized[end].isspace()
                    end += 1
                prefix = normalized[:end]
                if re.sub(r"\s", "", original_prefix) != re.sub(r"\s", "", prefix):
                    raise ValueError("Section continuation source character sequence differs")
                frozen = {**bridge, "right_prefix": prefix}
                plan["bridges"].append(frozen)
            final, _ = apply_plan(payload, plan)
            plan["final_passages"] = {p["id"]: {"checksum": p["checksum"], "title": p["title"]} for p in final["passages"]}
            summary["section_boundaries_repaired"] += len(bridges)
        recipe["works"][work["id"]] = plan
        summary["changed_works"] += bool(plan["passages"])
    recipe["summary"] = dict(summary)
    return recipe, suspicious


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "server/priv")
    parser.add_argument("--protected", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, default=RECIPE)
    parser.add_argument("--suspects", type=Path, default=Path("/tmp/ga-sentence-short-joins.json"))
    parser.add_argument("--continuations", type=Path, default=ROOT / "tools/ga050_plus_section_continuations.json")
    parser.add_argument("--page-labels", type=Path, default=ROOT / "tools/ga050_plus_page_labels.json")
    args = parser.parse_args()
    protections = [entry for path in args.protected for entry in read_json(path)["ranges"]]
    continuations = read_json(args.continuations)["continuations"] if args.continuations.exists() else []
    page_labels = read_json(args.page_labels) if args.page_labels.exists() else []
    recipe, suspects = build(args.root, protections, continuations, page_labels)
    args.output.write_text(json.dumps(recipe, ensure_ascii=False, separators=(",", ":")) + "\n")
    args.suspects.write_text(json.dumps(suspects, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(recipe["summary"], ensure_ascii=False))
    print(f"Short continuation samples for review: {len(suspects)}")
