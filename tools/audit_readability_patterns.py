#!/usr/bin/env python3
"""Read-only readability inventory of the GA reader payloads.

Counts are leads for proofreading, not a claim that each match is an error.
In particular, real compound hyphens, repeated quotations, verse line breaks,
dates, and font-dependent symbols must not be removed by a blanket regex.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys


LETTERS = "A-Za-zÄÖÜäöüß"
WORD = re.compile(rf"[{LETTERS}]+")
HYPHEN_PAIR = re.compile(rf"\b([{LETTERS}]{{2,}})-([ \t\n]*)([{LETTERS}]{{2,}})\b")
CONNECTORS = {"und", "oder", "bzw", "beziehungsweise", "bis", "sowie"}
COMPOUND_PREFIXES = {
    "geistig", "göttlich", "physisch", "sinnlich", "seelisch", "leiblich",
    "körperlich", "politisch", "sozial", "ich", "christus", "äther", "geist",
    "erden", "archiv",
}
# Reviewed syllabic forms, included to give reproducible, intelligible examples.
# This audit does not replace them. Capitalization and complete token boundaries
# remain available to a downstream correction pipeline.
REVIEWED_SYLLABLE_PAIRS = {
    ("men", "schen"), ("wer", "den"), ("das", "jenige"), ("kön", "nen"),
    ("eigent", "lich"), ("son", "dern"), ("mensch", "lichen"),
    ("ent", "wickelung"), ("da", "durch"), ("physi", "schen"),
    ("entwicke", "lung"), ("ha", "ben"), ("kom", "men"),
    ("bewußt", "sein"), ("be", "wußtsein"), ("phy", "sischen"),
    ("mensch", "heit"), ("wesen", "heiten"), ("zwi", "schen"),
    ("den", "ken"), ("gei", "stigen"), ("zu", "nächst"),
    ("wissen", "schaft"), ("er", "kenntnis"), ("wirk", "lich"),
    ("müs", "sen"), ("bei", "spiel"), ("die", "ser"),
}
PATTERNS = {
    "soft_hyphen": re.compile("\u00ad"),
    "soft_hyphen_before_whitespace": re.compile("\u00ad\\s+"),
    "hard_hyphen_linebreak": re.compile(rf"[{LETTERS}]+-\s*\n\s*[a-zäöüß]+"),
    "hyphen_space": re.compile(rf"[{LETTERS}]+- +[a-zäöüß]+"),
    "illustration_placeholder": re.compile(r"#Bild[^\n]*", re.I),
    "font_dependent_symbol": re.compile(r"[\ue000-\uf8ff]"),
    "replacement_character": re.compile("\ufffd"),
    "mojibake": re.compile(r"Ã[\u0080-\u00bf]|Â[\u0080-\u00bf]|â[\u0080-\u00bf]"),
    "source_macro": re.compile(r"#(?:SE\d|TI\b|TX\b|BI\b|LI\b|IR\b|HY\b|MU\b)"),
    "word_field": re.compile(r"PAGE\s+\\\*\s+MERGEFORMAT"),
    "publisher_page_footer": re.compile(
        r"Copyright\s+Rudolf\s+Steiner\s+Nach[a-zäöüß-]*[^\n]{0,160}", re.I
    ),
    "isbn": re.compile(r"ISBN[^\n]{0,100}"),
    "standalone_number": re.compile(r"(?m)^\s*[0-9]{1,4}\s*$"),
    "spaced_letters": re.compile(
        rf"(?<!\w)(?:[{LETTERS}] ){{5,}}[{LETTERS}](?!\w)"
    ),
}


def source_family(document: dict) -> str:
    if document.get("source_file", "").endswith(".txt"):
        return "archive_doc"
    if document.get("source_label", "").startswith("Wiedergewonnene"):
        return "recovered_epub"
    return "existing_epub"


def load_documents(content_dir: Path):
    for path in sorted(content_dir.glob("ga-*.json*")):
        if path.suffix not in {".json", ".gz"}:
            continue
        raw = path.read_bytes()
        data = gzip.decompress(raw) if path.suffix == ".gz" else raw
        yield path, json.loads(data), hashlib.sha256(raw).hexdigest()


def context_sample(passage: dict, text: str, start: int, end: int) -> dict:
    return {
        "passage_id": passage["id"],
        "passage_title": passage.get("title", ""),
        "source_member": passage.get("source_member"),
        "ga_page": passage.get("ga_page"),
        "offset": start,
        "match": text[start:end],
        "context": text[max(0, start - 65):min(len(text), end + 100)],
    }


def audit(content_dir: Path, field: str = "text", sample_limit: int = 3) -> dict:
    documents = list(load_documents(content_dir))
    word_counts: Counter = Counter()
    word_works: dict[str, set[str]] = defaultdict(set)
    pair_counts: Counter = Counter()
    pair_line_counts: Counter = Counter()
    pair_samples: dict[tuple[str, str], dict] = {}
    per_work = []
    for path, document, payload_digest in documents:
        work_id = document["work_id"]
        counts: Counter = Counter()
        samples: dict[str, list] = defaultdict(list)
        candidate_pairs: Counter = Counter()
        characters = 0
        for passage in document.get("passages", []):
            text = passage.get(field, "")
            characters += len(text)
            for key, pattern in PATTERNS.items():
                for match in pattern.finditer(text):
                    counts[key] += 1
                    if len(samples[key]) < sample_limit:
                        samples[key].append(context_sample(passage, text, match.start(), match.end()))
            normalized = text.replace("\u00ad", "")
            for token in WORD.findall(normalized):
                token = token.lower()
                word_counts[token] += 1
                word_works[token].add(work_id)
            for match in HYPHEN_PAIR.finditer(normalized):
                left, gap, right = match.groups()
                pair = (left.lower(), right.lower())
                pair_counts[pair] += 1
                if "\n" in gap:
                    pair_line_counts[pair] += 1
                if pair in REVIEWED_SYLLABLE_PAIRS:
                    counts["reviewed_syllable_split"] += 1
                    if len(samples["reviewed_syllable_split"]) < sample_limit:
                        samples["reviewed_syllable_split"].append(
                            context_sample(passage, normalized, match.start(), match.end())
                        )
                candidate_pairs[pair] += 1
                if pair not in pair_samples:
                    pair_samples[pair] = {
                        "work_id": work_id,
                        **context_sample(passage, normalized, match.start(), match.end()),
                    }
            # Only identical neighboring long paragraphs are inventoried here;
            # repeats elsewhere are often quotations or deliberate repetition.
            paragraphs = re.split(r"\n[ \t]*\n", text)
            previous = None
            cursor = 0
            for paragraph in paragraphs:
                canonical = re.sub(r"\s+", " ", paragraph).strip()
                if len(canonical) >= 120 and canonical == previous:
                    counts["adjacent_duplicate_paragraph"] += 1
                    if len(samples["adjacent_duplicate_paragraph"]) < sample_limit:
                        offset = text.find(paragraph, cursor)
                        samples["adjacent_duplicate_paragraph"].append(
                            context_sample(passage, text, offset, offset + len(paragraph))
                        )
                previous = canonical
                cursor = max(cursor, text.find(paragraph, cursor) + len(paragraph))
        per_work.append({
            "work_id": work_id,
            "title": document.get("title", ""),
            "source_family": source_family(document),
            "payload_file": str(path),
            "payload_sha256": payload_digest,
            "passages": len(document.get("passages", [])),
            "characters": characters,
            "counts": dict(sorted(counts.items())),
            "samples": dict(sorted(samples.items())),
            "_candidate_pairs": candidate_pairs,
        })
    lexical_candidates = []
    for pair, count in pair_counts.items():
        joined = "".join(pair)
        joined_count = word_counts[joined]
        if joined_count < 15 or len(word_works[joined]) < 2:
            continue
        reasons = []
        if pair[1] in CONNECTORS:
            reasons.append("suspended_compound_connector")
        if pair[0] in COMPOUND_PREFIXES:
            reasons.append("established_compound_prefix")
        if joined_count < count * 10:
            reasons.append("hyphen_form_common_relative_to_joined_word")
        lexical_candidates.append({
            "split": "-".join(pair), "joined": joined,
            "matches": count, "matches_with_linebreak": pair_line_counts[pair],
            "joined_attestations": joined_count,
            "joined_attestation_works": len(word_works[joined]),
            "reviewed_syllable_pair": pair in REVIEWED_SYLLABLE_PAIRS,
            "preserve_or_review_reasons": reasons,
            "sample": pair_samples[pair],
        })
    lexical_candidates.sort(key=lambda item: (-item["matches"], item["split"]))
    # Avoid making a ~30,000-item vocabulary a per-work reader download. The
    # leading candidates are available globally; exact warning contexts above
    # are bounded per category per GA.
    for work in per_work:
        del work["_candidate_pairs"]
    all_keys = set(PATTERNS) | {"reviewed_syllable_split", "adjacent_duplicate_paragraph"}
    summary = {
        key: {
            "matches": sum(work["counts"].get(key, 0) for work in per_work),
            "works": sum(bool(work["counts"].get(key, 0)) for work in per_work),
        }
        for key in sorted(all_keys)
    }
    return {
        "audit_version": 1,
        "field": field,
        "work_count": len(per_work),
        "passage_count": sum(work["passages"] for work in per_work),
        "source_families": dict(Counter(work["source_family"] for work in per_work)),
        "interpretation": "Matches are proofreading leads; no documents were modified.",
        "summary": summary,
        "lexical_candidate_count": len(lexical_candidates),
        "lexical_candidates": lexical_candidates[:150],
        "works": per_work,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content-dir", type=Path, default=Path("server/priv/content"))
    parser.add_argument("--field", choices=["text", "source_text"], default="text")
    parser.add_argument("--samples-per-pattern", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.content_dir, args.field, max(0, args.samples_per_pattern))
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
        print(json.dumps({"output": str(args.output), "work_count": report["work_count"],
                          "passage_count": report["passage_count"], "summary": report["summary"]},
                         ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(serialized)


if __name__ == "__main__":
    main()
