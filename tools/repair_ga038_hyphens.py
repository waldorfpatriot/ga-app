#!/usr/bin/env python3
"""Apply only frozen, source-evidenced GA038 word-seam corrections."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from finalize_library import content_file, read_json, write_json, verify

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "tools/ga038_hyphen_review.json"
SOURCE = ROOT / "research/proofreading-sources/ga-038.epub"
BASELINE = ROOT / "research/proofreading-ga038-hyphen-baseline"
WORK_ID = "ga-038"
RULE = "source_hyphen_repair"
LABEL = "GA 038: belegte physische Worttrennungen quellengebunden geschlossen"
CHECK = "GA 038: exakte Wortfugen an Originalquellen geprüft; echte Bindestriche und Absätze erhalten"
_CONTINUATIONS = {
    ("ga-038-doc-heading-10", "hin-", "hinlenkten?", 66, "lenkten?"),
    ("ga-038-doc-heading-51", "unterzubrin-", "unterzubringen sein.", 189, "gen sein."),
}
# Imported word fragments can retain bracketed expansions or OCR glyphs such
# as § and a literal backslash. Keep those glyphs exactly; whitespace is only
# allowed immediately after the reviewed physical hyphen.
_OLD_WORD = re.compile(r"[^\s-]+(?:-\s*[^\s-]+)+", re.UNICODE)
_NEW_WORD = re.compile(r"[^\s-]+(?:-[^\s-]+)*", re.UNICODE)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(text):
    return digest(text.encode("utf-8"))


def review_digest(review):
    return sha(json.dumps(review, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def word_pattern(literal):
    # A reviewed word cannot also match the middle of another compound.
    return re.compile(r"(?<![\w-])" + re.escape(literal) + r"(?![\w-])", re.UNICODE)


def validate_replacement(repair):
    old, new = repair.get("old"), repair.get("new")
    kind = repair.get("kind", "physical_word_hyphen")
    if kind == "source_word_continuation":
        witness = repair.get("continuation_witness")
        if not isinstance(witness, dict):
            raise ValueError("GA038 source continuation has no typed original witness")
        key = (repair.get("passage_id"), old, new, witness.get("page"), witness.get("missing_text"))
        previous = witness.get("previous_line", {})
        if (key not in _CONTINUATIONS or repair.get("field") != "text"
                or type(repair.get("count")) is not int or repair["count"] != 1
                or witness.get("reviewed") is not True or not repair.get("evidence")
                or not isinstance(previous, dict) or previous.get("pdf_page") != witness["page"]
                or not isinstance(previous.get("text"), str) or not previous["text"].rstrip().endswith(old)
                or not repair.get("pdf_raster_witnesses")
                or repair.get("pdf_line_pair_witnesses") != []):
            raise ValueError("GA038 continuation differs from the two reviewed original fragments")
        for raster in repair["pdf_raster_witnesses"]:
            if (raster.get("pdf_page") != witness["page"]
                    or raster.get("page_index") != witness["page"] - 1
                    or raster.get("original_page_mode") != "1"
                    or not re.fullmatch(r"[a-f0-9]{64}", raster.get("original_pdf_sha256", ""))
                    or not re.fullmatch(r"[a-f0-9]{64}", raster.get("visible_page_pixels_sha256", ""))
                    or not isinstance(raster.get("original_page_size"), list)
                    or len(raster["original_page_size"]) != 2
                    or any(type(size) is not int or size <= 0 for size in raster["original_page_size"])):
                raise ValueError("GA038 continuation raster witness differs")
        return
    if (repair.get("field") != "text" or not isinstance(old, str) or not isinstance(new, str)
            or old == new or not _OLD_WORD.fullmatch(old) or not _NEW_WORD.fullmatch(new)
            or type(repair.get("count")) is not int or repair["count"] <= 0
            or not repair.get("evidence")
            or kind not in {"physical_word_hyphen", "historical_ck_hyphen", "physical_gap_after_lexical_hyphen"}):
        raise ValueError("GA038 repair is not an evidenced exact word seam")
    if kind == "physical_gap_after_lexical_hyphen" and (
            "\n" not in old or new != re.sub(r"\s", "", old)
            or new not in {"National-Literatur", "Ja-Falle"}):
        raise ValueError("GA038 lexical-hyphen gap is not one of the two reviewed physical LF cases")
    # Compare the positions of every hyphen between the unchanged letters.
    # This permits dropping a physical hyphen and retaining a genuine one,
    # including National-Lite-ratur -> National-Literatur, without reordering.
    def letters_and_hyphens(text):
        letters, hyphens = [], []
        for char in text:
            if char == "-":
                hyphens.append(len(letters))
            elif not char.isspace():
                letters.append(char)
        return "".join(letters), hyphens
    old_letters, old_hyphens = letters_and_hyphens(old)
    new_letters, new_hyphens = letters_and_hyphens(new)
    if kind == "historical_ck_hyphen":
        historical = re.compile(r"k-\s*k")
        if len(historical.findall(old)) != 1:
            raise ValueError("GA038 historical ck repair requires exactly one k-k source seam")
        old_letters = letters_and_hyphens(historical.sub("ck", old))[0]
    if old_letters != new_letters or any(pos not in old_hyphens for pos in new_hyphens):
        raise ValueError("GA038 word seam changes letters or adds/moves a hyphen")


def check_source(review, source=None):
    """Bind every literal to the actual EPUB bytes and selected original atom."""
    source = Path(source) if source is not None else SOURCE
    if digest(source.read_bytes()) != review.get("source_epub_sha256"):
        raise ValueError("GA038 original EPUB byte hash differs")
    try:
        with ZipFile(source) as archive:
            members = {}
            for repair in review["repairs"]:
                validate_replacement(repair)
                witnesses = repair.get("source_witnesses")
                if not isinstance(witnesses, list) or not witnesses:
                    raise ValueError("GA038 repair has no original source witness")
                originals = []
                for witness in witnesses:
                    member = witness.get("source_member")
                    if member not in members:
                        raw_member = archive.read(member)
                        body = ET.fromstring(raw_member).find("{http://www.w3.org/1999/xhtml}body")
                        if body is None:
                            raise ValueError("GA038 original EPUB body is missing")
                        members[member] = (digest(raw_member), body)
                    member_hash, body = members[member]
                    if witness.get("member_sha256", member_hash) != member_hash:
                        raise ValueError("GA038 source member hash differs")
                    index, path = witness.get("body_index"), witness.get("child_path", [])
                    if type(index) is not int or not 0 <= index < len(body) or not isinstance(path, list):
                        raise ValueError("GA038 invalid original source selector")
                    atom = body[index]
                    for child in path:
                        if type(child) is not int or not 0 <= child < len(atom):
                            raise ValueError("GA038 invalid source child selector")
                        atom = atom[child]
                    raw = "".join(atom.itertext())
                    if sha(raw) != witness.get("source_paragraph_sha256"):
                        raise ValueError("GA038 source paragraph hash differs")
                    originals.append(raw)
                source_context = re.sub(r"\s+", " ", " ".join(originals))
                old_context = re.sub(r"\s+", " ", repair["old"])
                if not word_pattern(old_context).search(source_context):
                    raise ValueError("GA038 reviewed word is absent from its source witnesses")
    except (BadZipFile, KeyError, TypeError, ET.ParseError) as error:
        raise ValueError("GA038 original EPUB witness cannot be read") from error
    for kind in ("doc", "pdf"):
        if review.get("original_" + kind + "_path"):
            original = ROOT / review["original_" + kind + "_path"]
            checksum = review.get("original_" + kind + "_sha256")
            if digest(original.read_bytes()) != checksum:
                raise ValueError("GA038 original " + kind.upper() + " byte hash differs")


def check_inventory(payload, review, *, original):
    plans = review.get("input_passages")
    if (review.get("work_id") != WORK_ID or payload.get("work_id") != WORK_ID
            or not isinstance(plans, dict) or not plans
            or any(payload.get(key) != review.get(key) for key in ("source_sha256", "source_epub_sha256"))
            or [p.get("id") for p in payload.get("passages", [])] != list(plans)):
        raise ValueError("GA038 original source or passage inventory differs")
    for passage in payload["passages"]:
        plan = plans[passage["id"]]
        expected = plan["input_sha256" if original else "output_sha256"]
        if (sha(passage["text"]) != expected or passage.get("checksum") != expected
                or sha(passage["source_text"]) != plan["source_text_sha256"]):
            raise ValueError("GA038 reviewed passage checksum/source differs: " + passage["id"])
    seen = set()
    for repair in review.get("repairs", []):
        rid = repair.get("id")
        if (not isinstance(rid, str) or not rid or rid in seen
                or repair.get("passage_id") not in plans):
            raise ValueError("GA038 repair ID or passage differs")
        seen.add(rid)
    if not seen:
        raise ValueError("GA038 frozen review contains no repairs")


def _apply_original(payload, review):
    check_inventory(payload, review, original=True)
    result = deepcopy(payload)
    events = []
    for passage in result["passages"]:
        before = passage["text"]
        replacements = []
        for repair in review["repairs"]:
            if repair["passage_id"] != passage["id"]:
                continue
            pattern = word_pattern(repair["old"])
            if len(pattern.findall(passage["text"])) != repair["count"]:
                raise ValueError("GA038 exact word-seam count differs: " + repair["id"])
            passage["text"] = pattern.sub(lambda match: repair["new"], passage["text"])
            replacements.append(deepcopy(repair))
        passage["checksum"] = sha(passage["text"])
        if replacements:
            events.append({"passage_id": passage["id"], "rule": RULE, "label": LABEL,
                "count": sum(repair["count"] for repair in replacements),
                "input_sha256": sha(before), "output_sha256": passage["checksum"],
                "before_excerpt": before[:600], "after_excerpt": passage["text"][:600],
                "replacements": replacements})
    check_inventory(result, review, original=False)
    result.setdefault("metadata", {})["source_hyphen_review"] = {
        "review_sha256": review_digest(review), "source_epub_sha256": review["source_epub_sha256"]}
    return result, events


def apply_review(payload, review=None):
    review = read_json(REVIEW) if review is None else review
    check_source(review)
    marker = payload.get("metadata", {}).get("source_hyphen_review")
    expected_marker = {"review_sha256": review_digest(review),
                       "source_epub_sha256": review["source_epub_sha256"]}
    if marker is not None:
        if marker != expected_marker:
            raise ValueError("GA038 rendered revision differs from the frozen review")
        # Rebuild from the retained original to protect titles, annotations,
        # pages and all unrelated metadata as well as the corrected text.
        baseline = content_file(BASELINE, WORK_ID)
        original = read_json(baseline)
        expected, _ = _apply_original(original, review)
        if payload != expected:
            raise ValueError("GA038 rendered text or unchanged metadata differs")
        return deepcopy(payload), []
    return _apply_original(payload, review)


def preserve_baseline(payload, baseline=BASELINE):
    path = Path(baseline) / "content/ga-038.json.gz"
    if path.exists():
        if read_json(path) != payload:
            raise ValueError("GA038 preserved hyphen input differs")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, payload)
    return digest(path.read_bytes())


def stage(root, output, review=None, baseline=BASELINE):
    from proofread_library import complete_stage
    root, output, baseline = Path(root), Path(output), Path(baseline)
    review = read_json(REVIEW) if review is None else review
    if output.exists():
        raise ValueError("Choose a fresh stage; existing results are retained")
    path = content_file(root, WORK_ID)
    old_hash = digest(path.read_bytes())
    detail = read_json(root / "proofreading/works/ga-038.json")
    if old_hash != detail["work"]["after_sha256"]:
        raise ValueError("GA038 content differs from its correction ledger")
    current = read_json(path)
    if current.get("metadata", {}).get("source_hyphen_review") is not None:
        input_path = content_file(baseline, WORK_ID)
        input_hash = digest(input_path.read_bytes())
        if input_hash != detail["work"].get("ga038_hyphen_input_sha256"):
            raise ValueError("GA038 preserved input byte hash differs from its ledger")
        check_source(review)
        expected, _ = _apply_original(read_json(input_path), review)
        if current != expected:
            raise ValueError("GA038 repeated stage differs from the retained original/review")
        corrected, changes = deepcopy(current), []
    else:
        corrected, changes = apply_review(current, review)
        input_hash = preserve_baseline(current, baseline)
    catalog = read_json(root / "library/catalog.json")
    entry = next(work for work in catalog["works"] if work["id"] == WORK_ID)
    if ([summary["id"] for summary in entry["passages"]] != [p["id"] for p in current["passages"]]
            or any(summary.get("checksum") != passage["checksum"]
                   for summary, passage in zip(entry["passages"], current["passages"]))):
        raise ValueError("GA038 catalog passage inventory/checksums differ")
    other_hashes = {p.relative_to(root): digest(p.read_bytes())
                    for p in (root / "content").iterdir() if p.is_file() and p != path}
    for folder in ("content", "library", "proofreading"):
        shutil.copytree(root / folder, output / folder)
    staged = content_file(output, WORK_ID)
    if changes:
        write_json(staged, corrected)
        for summary, passage in zip(entry["passages"], corrected["passages"]):
            summary["checksum"] = passage["checksum"]
        write_json(output / "library/catalog.json", catalog)
        detail["changes"].extend(deepcopy(changes))
        detail["work"].update(application_base_sha256=old_hash,
            ga038_hyphen_input_sha256=input_hash, after_sha256=digest(staged.read_bytes()))
        detail["hyphen_review"] = deepcopy(corrected["metadata"]["source_hyphen_review"])
        if CHECK not in detail["work"].setdefault("checks", []):
            detail["work"]["checks"].append(CHECK)
        write_json(output / "proofreading/works/ga-038.json", detail)
    previous_date = read_json(output / "proofreading/catalog.json").get("generated_at")
    complete_stage(output, generated_at=None if changes else previous_date)
    verify(output)
    if any(digest((output / relative).read_bytes()) != checksum for relative, checksum in other_hashes.items()):
        raise ValueError("GA038 stage would change another content file")
    if read_json(staged) != corrected:
        raise ValueError("GA038 stage completion changed unreviewed text or metadata")
    return changes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "server/priv")
    parser.add_argument("--review", type=Path, default=REVIEW)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    changes = stage(args.root, args.output, read_json(args.review), args.baseline)
    print(f"GA 038: {sum(event['count'] for event in changes)} Wortfugen in {args.output} korrigiert")
