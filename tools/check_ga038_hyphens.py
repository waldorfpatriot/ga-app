#!/usr/bin/env python3
"""Independently verify the narrow, frozen GA038 word-hyphen layer."""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "tools/ga038_hyphen_review.json"
SOURCE = ROOT / "research/proofreading-sources/ga-038.epub"
BASELINE = ROOT / "research/proofreading-ga038-hyphen-baseline"
RULE = "source_hyphen_repair"
LABEL = "GA 038: belegte physische Worttrennungen quellengebunden geschlossen"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stable_hash(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def word_spans(text, literal):
    return list(re.finditer(r"(?<![\w-])" + re.escape(literal) + r"(?![\w-])", text))


def inspect_replacement(repair):
    old, new, kind = repair.get("old"), repair.get("new"), repair.get("kind")
    if kind == "source_word_continuation":
        allowed = {("ga-038-doc-heading-10", "hin-", "hinlenkten?"): (66, "lenkten?"),
                   ("ga-038-doc-heading-51", "unterzubrin-", "unterzubringen sein."): (189, "gen sein.")}
        selected = allowed.get((repair.get("passage_id"), old, new))
        witness = repair.get("continuation_witness", {})
        if (not selected or repair.get("field") != "text" or type(repair.get("count")) is not int
                or repair["count"] != 1 or not repair.get("evidence")
                or witness.get("page") != selected[0] or witness.get("missing_text") != selected[1]
                or witness.get("reviewed") is not True):
            raise ValueError("GA038 continuation is outside its two original printed exceptions")
        return
    source_glyph_literals = {"Philo-s[ophischen]": "Philos[ophischen]",
                            "Anerken-\n\nnun§": "Anerkennun§",
                            r"j\t-chivarbeit": r"j\tchivarbeit"}
    literal_glyphs = source_glyph_literals.get(old) == new
    if (repair.get("field") != "text" or not isinstance(old, str) or not isinstance(new, str)
            or old == new or "-" not in old or type(repair.get("count")) is not int
            or repair["count"] < 1 or not repair.get("evidence")
            or not literal_glyphs and (not re.fullmatch(r"[^\W\d_]+(?:-\s*[^\W\d_]+)+", old)
                or not re.fullmatch(r"[^\W\d_]+(?:-[^\W\d_]+)*", new))):
        raise ValueError("GA038 repair exceeds one exact source word")
    compact = re.sub(r"\s", "", old)
    if kind == "physical_gap_after_lexical_hyphen":
        if "\n" not in old or compact != new or new not in {"National-Literatur", "Ja-Falle"}:
            raise ValueError("GA038 genuine compound hyphen must remain unchanged")
        return
    if kind == "historical_ck_hyphen":
        if len(re.findall(r"k-\s*k", old)) != 1:
            raise ValueError("GA038 historical ck seam is not its exact k-k pair")
        compact = re.sub(r"k-k", "ck", compact)
    elif kind != "physical_word_hyphen":
        raise ValueError("GA038 unreviewed word correction kind")
    if any(part.casefold() in {"und", "oder", "bis", "sowie", "bzw", "beziehungsweise"}
           for part in compact.split("-")[1:]):
        raise ValueError("GA038 repair would consume a genuine complementary hyphen")
    cursor = 0
    for char in compact:
        if cursor < len(new) and char == new[cursor]:
            cursor += 1
        elif char != "-":
            raise ValueError("GA038 seam changes source letters or hyphen positions")
    if cursor != len(new) or len(new) >= len(re.sub(r"\s", "", old)):
        raise ValueError("GA038 repair adds characters or removes no physical hyphen")


def printed_word(repair, pair):
    before, after = [line["text"] for line in pair["lines"]]
    old = re.sub(r"\s", "", repair["old"])
    right = after.split()[0].rstrip(',.;:!?»”")')
    prefixes = [old[:index+1] for index, char in enumerate(old) if char == "-"]
    if old == r"j\t-chivarbeit":
        prefixes = ["Ar-"]
    for prefix in prefixes:
        pattern = r"(?<!\w)" + r"\s*".join(re.escape(char) for char in prefix) + r"\s*$"
        found = re.search(pattern, before, re.IGNORECASE)
        if found:
            value = re.sub(r"\s", "", found.group()) + right
            if value.casefold() in old.casefold() or old == r"j\t-chivarbeit" and value == "Ar-chivarbeit":
                return value
    raise ValueError("GA038 physical printed seam is not in its exact source word")


def inspect_printed_pairs(repair, review, pdf):
    from check_essay_layout import original_page_lines, original_page_raster
    rasters = repair.get("pdf_raster_witnesses", [])
    pairs = repair.get("pdf_line_pair_witnesses", [])
    continuation = repair.get("kind") == "source_word_continuation"
    if not rasters or not pairs and not continuation:
        raise ValueError("GA038 word lacks a printed line pair and original scan pixels")
    for witness in rasters:
        page = witness["pdf_page"]
        width, height, pixels = original_page_raster(pdf, review["original_pdf_sha256"], page)
        if (witness.get("original_pdf_sha256") != review["original_pdf_sha256"]
                or witness.get("page_index") != page - 1 or witness.get("original_page_mode") != "1"
                or witness.get("original_page_size") != [width, height]
                or witness.get("visible_page_pixels_sha256") != digest(pixels)):
            raise ValueError("GA038 original printed raster identity differs")
    if continuation:
        witness = repair["continuation_witness"]
        previous = witness["previous_line"]
        lines = original_page_lines(pdf, review["original_pdf_sha256"], witness["page"])
        position = previous["line_index"]
        box = previous["bbox_pt"]
        missing = witness["missing_line_bbox_pt"]
        if (pairs or previous["pdf_page"] != witness["page"]
                or position < 0 or position >= len(lines)
                or lines[position][0] != previous["text"]
                or len(box) != 4 or any(abs(a-b) > .002 for a,b in zip(lines[position][1], box))
                or not previous["text"].endswith(repair["old"])
                or len(missing) != 4 or missing[1] <= box[3]
                or missing[2] <= missing[0] or missing[3] <= missing[1]
                or witness["missing_text"] in [text for text, _ in lines]
                or repair["source_pdf_pages"] != [witness["page"]]
                or {item["pdf_page"] for item in rasters} != {witness["page"]}):
            raise ValueError("GA038 omitted continuation is outside its exact printed source line")
        return
    represented_pages = set()
    for pair in pairs:
        if len(pair.get("lines", [])) != 2:
            raise ValueError("GA038 printed seam has more than two exact physical lines")
        found = []
        for line in pair["lines"]:
            page = line["pdf_page"]
            lines = original_page_lines(pdf, review["original_pdf_sha256"], page)
            box = line.get("bbox_pt", [])
            matches = [index for index, (text, bbox) in enumerate(lines)
                       if text == line.get("text") and len(box) == 4
                       and all(abs(a - b) < .002 for a, b in zip(bbox, box))]
            if len(matches) != 1:
                raise ValueError("GA038 physical line text or bounding box differs")
            found.append((page, matches[0], lines))
            represented_pages.add(page)
        first, second = found
        if first[0] == second[0]:
            if second[1] != first[1] + 1:
                raise ValueError("GA038 printed source lines are not consecutive")
        elif second[0] == first[0] + 1:
            omitted = [text for text, _ in first[2][first[1] + 1:] + second[2][:second[1]]]
            if any(not re.fullmatch(r"\s*\d+\s*", text) for text in omitted):
                raise ValueError("GA038 cross-page seam skips original author text")
        else:
            raise ValueError("GA038 physical seam jumps original pages")
        printed = printed_word(repair, pair)
        if printed != pair.get("printed_hyphen_word"):
            raise ValueError("GA038 printed word differs from the two line ends")
    if (set(repair.get("source_pdf_pages", [])) != represented_pages
            or represented_pages != {item["pdf_page"] for item in rasters}):
        raise ValueError("GA038 exact printed page witnesses differ")


def inspect_ga038_hyphens(prior, final, review, events, source=SOURCE):
    """Project only reviewed literal seams, using XML/Poppler rather than the writer."""
    if (prior.get("work_id") != "ga-038" or review.get("work_id") != "ga-038"
            or any(prior.get(key) != review.get(key) for key in ("source_sha256", "source_epub_sha256"))
            or digest(source.read_bytes()) != review["source_epub_sha256"]):
        raise ValueError("GA038 exact original edition byte identity differs")
    for prefix in ("original_doc", "original_pdf"):
        path = Path(review[prefix + "_path"])
        if not path.is_absolute():
            path = ROOT / path
        if digest(path.read_bytes()) != review[prefix + "_sha256"]:
            raise ValueError("GA038 original DOC/PDF bytes differ")
    if review["original_doc_sha256"] != review["source_sha256"]:
        raise ValueError("GA038 original DOC is not the imported original")
    pdf = Path(review["original_pdf_path"])
    if not pdf.is_absolute():
        pdf = ROOT / pdf
    plans = review["input_passages"]
    if [p["id"] for p in prior["passages"]] != list(plans):
        raise ValueError("GA038 original passage inventory or ordering differs")
    for passage in prior["passages"]:
        plan = plans[passage["id"]]
        if (digest(passage["text"].encode()) != plan["input_sha256"]
                or passage["checksum"] != plan["input_sha256"]
                or digest(passage["source_text"].encode()) != plan["source_text_sha256"]):
            raise ValueError("GA038 frozen input/source paragraph checksum differs")
    expected = deepcopy(prior)
    by_id = {p["id"]: p for p in expected["passages"]}
    grouped = defaultdict(list)
    selected = set()
    with ZipFile(source) as archive:
        bodies = {}
        for repair in review["repairs"]:
            inspect_replacement(repair)
            pid, rid = repair["passage_id"], repair["id"]
            if pid not in by_id or rid in selected:
                raise ValueError("GA038 repeated repair or foreign passage")
            selected.add(rid)
            raw_parts = []
            for witness in repair["source_witnesses"]:
                member = witness["source_member"]
                if member not in bodies:
                    data = archive.read(member)
                    bodies[member] = digest(data), ET.fromstring(data).find("{*}body")
                checksum, body = bodies[member]
                if checksum != witness["member_sha256"]:
                    raise ValueError("GA038 exact original source member differs")
                atom = body[witness["body_index"]]
                for index in witness.get("child_path", []):
                    atom = atom[index]
                raw = "".join(atom.itertext())
                if digest(raw.encode()) != witness["source_paragraph_sha256"]:
                    raise ValueError("GA038 exact original source paragraph differs")
                raw_parts.append(raw)
            original_context = " ".join(" ".join(raw.split()) for raw in raw_parts)
            if (not raw_parts or not word_spans(original_context, " ".join(repair["old"].split()))
                    or not word_spans(" ".join(by_id[pid]["source_text"].split()), " ".join(repair["old"].split()))):
                raise ValueError("GA038 source word is outside its retained original passage")
            inspect_printed_pairs(repair, review, pdf)
            passage = by_id[pid]
            spans = word_spans(passage["text"], repair["old"])
            if len(spans) != repair["count"]:
                raise ValueError("GA038 literal occurrence count differs")
            for match in reversed(spans):
                passage["text"] = passage["text"][:match.start()] + repair["new"] + passage["text"][match.end():]
            grouped[pid].append(repair)
    expected_events = {}
    prior_by_id = {p["id"]: p for p in prior["passages"]}
    for passage in expected["passages"]:
        pid = passage["id"]
        passage["checksum"] = digest(passage["text"].encode())
        if passage["checksum"] != plans[pid]["output_sha256"]:
            raise ValueError("GA038 projected output differs from its frozen checksum")
        if pid in grouped:
            before = prior_by_id[pid]
            expected_events[pid] = [{"passage_id": pid, "rule": RULE, "label": LABEL,
                "count": sum(r["count"] for r in grouped[pid]),
                "input_sha256": digest(before["text"].encode()), "output_sha256": passage["checksum"],
                "before_excerpt": before["text"][:600], "after_excerpt": passage["text"][:600],
                "replacements": grouped[pid]}]
    expected.setdefault("metadata", {})["source_hyphen_review"] = {
        "review_sha256": stable_hash(review), "source_epub_sha256": review["source_epub_sha256"]}
    actual_events = {pid: [dict(event, passage_id=pid) for event in items if event["rule"] == RULE]
                     for pid, items in events.items() if any(event["rule"] == RULE for event in items)}
    if actual_events != expected_events:
        raise ValueError("GA038 exact word-seam correction ledger differs")
    if final != expected:
        return ["GA038 corrected reading text or retained original metadata differs"], 0
    return [], sum(r["count"] for r in review["repairs"])
