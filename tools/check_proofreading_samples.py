#!/usr/bin/env python3
"""Independently validate a completed GA proofreading stage against its baseline.

Uses only the standard library, does not invoke the correction functions, and
never modifies payloads. Historical repairs retain their strict character and
corpus checks. Edition-bound layout repairs are checked separately against a
preserved pre-layout payload, exact recipe slices, frozen hashes and metadata.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from difflib import SequenceMatcher
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
LETTERS = "A-Za-zÄÖÜäöüß"
TARGETS = [
    "ga-001", "ga-002", "ga-030", "ga-014", "ga-027", "ga-040", "ga-040a",
    "ga-159", "ga-259", "ga-260a", "ga-264", "ga-083", "ga-120",
    "ga-319", "ga-343", "ga-293", "ga-294", "ga-296", "ga-299",
    "ga-003", "ga-004", "ga-009", "ga-010", "ga-013",
]
CONNECTORS = {"und", "oder", "bis", "sowie", "beziehungsweise", "bzw"}
PREFIXES = {
    "geistig", "göttlich", "physisch", "sinnlich", "seelisch", "leiblich",
    "körperlich", "politisch", "sozial", "ich", "christus", "äther", "geist",
    "erden", "archiv",
}
REVIEWED = {
    ("zu", "nächst"), ("er", "kenntnis"), ("be", "wußtsein"),
    ("men", "schen"), ("wer", "den"), ("kön", "nen"),
    ("eigent", "lich"), ("son", "dern"), ("mensch", "lichen"),
    ("physi", "schen"), ("gei", "stigen"), ("das", "jenige"),
    ("ent", "wickelung"), ("mensch", "heit"),
}
LETTER_SET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÄÖÜäöüß\u00ad")
AFTER_HYPHEN = re.compile(rf"([ \t\r\n\u00a0]*)([{LETTERS}\u00ad]+)")
RAW_TOKEN = re.compile(rf"[{LETTERS}\u00ad]+")
NEXT_WORD_PART = re.compile(rf"-([ \t\r\n\u00a0]*)([{LETTERS}\u00ad]+)")
APPROVED_OCR = {"fiir": "für", "dafi": "daß", "grofien": "großen",
                "erfiillt": "erfüllt", "iiber": "über", "miissen": "müssen"}
LAYOUT_BASELINE = ROOT / "research/proofreading-layout-baseline"
LAYOUT_RECIPE = ROOT / "tools/ga040_structure.json"
OUTLINE_BASELINE = ROOT / "research/proofreading-outline-baseline"
OUTLINE_RECIPE = ROOT / "tools/ga001_026_structure.json"
GA014_BASELINE = ROOT / "research/proofreading-ga014-baseline"
GA014_RECIPE = ROOT / "tools/ga014_structure.json"
GA027_RECIPE = ROOT / "tools/ga027_structure.json"
GA030_RECIPE = ROOT / "tools/ga030_structure.json"
GA030_REVIEW = ROOT / "tools/ga030_layout_review.json"
GA030_SOURCE = ROOT / "research/proofreading-sources/ga-030.epub"
GA032_RECIPE = ROOT / "tools/ga032_structure.json"
GA032_REVIEW = ROOT / "tools/ga032_layout_review.json"
GA032_SOURCE = ROOT / "research/proofreading-sources/ga-032.epub"
GA032_PDF = ROOT / "research/proofreading-sources/ga-032-original.pdf"
GA038_BASELINE = ROOT / "research/proofreading-ga038-hyphen-baseline"
GA038_REVIEW = ROOT / "tools/ga038_hyphen_review.json"
GA038_SOURCE = ROOT / "research/proofreading-sources/ga-038.epub"
GA039_BASELINE = ROOT / "research/proofreading-ga039-heading-baseline"
GA039_REVIEW = ROOT / "tools/ga039_heading_review.json"
GA039_SOURCE = ROOT / "research/proofreading-sources/ga-039.epub"
SENTENCE_BASELINE = ROOT / "research/proofreading-sentence-baseline"
SENTENCE_RECIPE = ROOT / "tools/ga050_plus_sentence_breaks.json"


def read(path: Path) -> dict:
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def content_file(root: Path, work_id: str) -> Path:
    for suffix in (".json", ".json.gz"):
        path = root / "content" / (work_id + suffix)
        if path.exists():
            return path
    raise FileNotFoundError(work_id)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inspect_ga030_recovery(prior: dict, recipe: dict, events: dict,
                           source: Path = GA030_SOURCE,
                           review_path: Path = GA030_REVIEW) -> dict:
    """Reconstruct frozen additions directly from the EPUB, without repair code."""
    original_ids = ["ga-030-doc-heading-3", "ga-030-doc-heading-4", "ga-030-doc-heading-5"]
    if [p["id"] for p in prior["passages"]] != original_ids or list(recipe["original_passages"]) != original_ids:
        raise ValueError("GA030 restoration original passage inventory/order differs")
    review = read(review_path)
    revision = digest(json.dumps(review, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")).encode())
    if recipe.get("source_evidence", {}).get("review_sha256") != revision:
        raise ValueError("GA030 restoration review identity differs")
    for key in ("source_additions", "original_passages", "known_gaps", "review_flags"):
        if recipe.get(key) != review.get(key):
            raise ValueError("GA030 restoration recipe differs from frozen review: " + key)
    if recipe.get("original_metadata_repairs", []) != review.get("original_metadata_repairs", []):
        raise ValueError("GA030 original metadata repairs differ from frozen review")
    if recipe.get("proofing_repairs", {}) != review.get("proofing_repairs", {}):
        raise ValueError("GA030 proofing repairs differ from frozen review")
    if digest(source.read_bytes()) != recipe["source_epub_sha256"]:
        raise ValueError("GA030 restored EPUB byte hash differs")
    result = deepcopy(prior)
    passages = {p["id"]: p for p in result["passages"]}
    for pid, identity in recipe["original_passages"].items():
        p = passages[pid]
        if (digest(p["text"].encode()) != identity["input_sha256"]
                or digest(p["source_text"].encode()) != identity["source_text_sha256"]):
            raise ValueError("GA030 retained original text/source differs: " + pid)

    def reading_text(element):
        # This edition uses collapsible XML whitespace plus explicit <br>.
        # Reject unsupported literal modes instead of silently changing them.
        marker = "\ufdd0"
        def collect(node):
            if (node.tag.rsplit("}", 1)[-1] == "pre"
                    or node.get("{http://www.w3.org/XML/1998/namespace}space") == "preserve"
                    or "white-space" in node.get("style", "")):
                raise ValueError("Unsupported GA030 restored literal whitespace mode")
            parts = [node.text or ""]
            for child in node:
                if child.get("role") != "doc-backlink":
                    parts.append(marker if child.tag.rsplit("}", 1)[-1] == "br" else collect(child))
                parts.append(child.tail or "")
            return "".join(parts)
        text = re.sub(r"[ \t\r\n\f]+", " ", collect(element))
        return re.sub(" *" + marker + " *", "\n", text).strip()

    additions, selected, identities, expected_events, inserts = recipe["source_additions"], set(), set(), {}, defaultdict(list)
    with ZipFile(source) as archive:
        for member, checksum in review["source_members"].items():
            if digest(archive.read(member)) != checksum:
                raise ValueError("GA030 layout member byte hash differs: " + member)
        for pid, plan in recipe.get("passages", {}).items():
            witness = review["passages"][pid]
            if plan.get("edits", []) != witness.get("edits", []):
                raise ValueError("GA030 layout edits differ from frozen review: " + pid)
            omissions = witness.get("omissions", [])
            actual_omissions = plan.get("omitted_parts", [])
            if len(omissions) != len(actual_omissions):
                raise ValueError("GA030 footer inventory differs from frozen review: " + pid)
            for omitted, part in zip(omissions, actual_omissions):
                keys = ("page", "text_sha256", "evidence", "source_member", "body_index", "source_paragraph_sha256")
                if part.get("kind") != "page_footer" or any(part.get(k) != omitted.get(k) for k in keys):
                    raise ValueError("GA030 footer witness differs from frozen review: " + pid)
                body = ET.fromstring(archive.read(part["source_member"])).find("{http://www.w3.org/1999/xhtml}body")
                raw = "".join(body[part["body_index"]].itertext())
                if digest(raw.encode()) != part["source_paragraph_sha256"]:
                    raise ValueError("GA030 footer source paragraph differs: " + pid)
        for addition in additions:
            if not addition.get("id") or addition["id"] in identities or not addition.get("evidence"):
                raise ValueError("GA030 restoration identity/evidence is missing or duplicated")
            identities.add(addition["id"])
            raw, text = [], []
            for span in addition["source_segments"]:
                data = archive.read(span["source_member"])
                if digest(data) != span["member_sha256"]:
                    raise ValueError("GA030 restored source member byte hash differs")
                body = ET.fromstring(data).find("{http://www.w3.org/1999/xhtml}body")
                for index in span["body_indices"]:
                    key = (span["source_member"], index)
                    if type(index) is not int or not 0 <= index < len(body) or key in selected:
                        raise ValueError("GA030 restoration source slice invalid or duplicated")
                    selected.add(key)
                    element = body[index]
                    raw.append("".join(element.itertext()))
                    text.append(reading_text(element))
            raw, text = "\n\n".join(raw), "\n\n".join(text)
            if "source_token" in addition:
                token = addition["source_token"]
                if (addition["kind"] != "text" or token != "[1895]"
                        or addition.get("reading_rendering") != "literal_bracket_year_as_digits"
                        or raw.count(token) != 1 or text.count(token) != 1):
                    raise ValueError("GA030 literal year restoration witness/rendering differs")
                raw, text = token, " 1895"
            for repair in addition.get("reading_edits", []):
                match = re.fullmatch(rf"([{LETTERS}]+)-\n([{LETTERS}]+)", repair.get("old", ""))
                if (addition["kind"] != "annotation" or not match or repair.get("new") != "".join(match.groups())
                        or not repair.get("evidence") or type(repair.get("count")) is not int
                        or repair["count"] < 1 or text.count(repair["old"]) != repair["count"]):
                    raise ValueError("GA030 restored annotation physical word seam differs")
                text = text.replace(repair["old"], repair["new"])
            if (raw != addition["source_text"] or text != addition["text"]
                    or digest(raw.encode()) != addition["source_text_sha256"]
                    or digest(text.encode()) != addition["text_sha256"]):
                raise ValueError("GA030 exact restored source/text differs: " + addition["id"])
            pid = addition["passage_id"]
            proof = {k: deepcopy(addition[k]) for k in
                     ("id", "source_segments", "source_text_sha256", "text_sha256", "evidence")}
            if addition["kind"] == "passage":
                if pid in passages:
                    raise ValueError("GA030 restored passage ID is duplicated")
                p = {"id": pid, "title": addition["title"], "source_label": prior["passages"][0]["source_label"],
                     "source_member": addition["source_segments"][0]["source_member"],
                     "text": text, "source_text": raw, "checksum": digest(text.encode()), "ga_page": None,
                     "metadata": {"page_numbers": [], "page_marker_source": "epub_source_page_labels",
                                  "annotations": [], "source_role": addition["source_role"], "source_restoration": proof}}
                before_id = addition.get("insert_before_passage_id")
                index = next(i for i, item in enumerate(result["passages"]) if item["id"] == before_id) if before_id else len(result["passages"])
                result["passages"].insert(index, p)
                passages[pid] = p
            elif addition["kind"] == "text":
                if pid not in original_ids:
                    raise ValueError("GA030 text restoration targets a non-original passage")
                inserts[pid].append(addition)
            elif addition["kind"] == "annotation":
                if "reading_edits" in addition:
                    proof["reading_edits"] = deepcopy(addition["reading_edits"])
                notes = passages[pid]["metadata"].setdefault("annotations", [])
                if any(note["id"] == addition["annotation_id"] for note in notes):
                    raise ValueError("GA030 restored annotation ID is duplicated")
                notes.append({"id": addition["annotation_id"], "marker": addition["marker"],
                              "text": text, "source_text": raw, "source_restoration": proof})
            else:
                raise ValueError("Unknown GA030 source restoration kind")
            expected_events[addition["id"]] = {"passage_id": pid, "rule": "source_restoration", "count": 1,
                "label": "Exakt belegten Originalquellentext wiederhergestellt", "addition_id": addition["id"],
                "source_text_sha256": addition["source_text_sha256"], "text_sha256": addition["text_sha256"],
                "before_excerpt": "", "after_excerpt": text[:440], "evidence": addition["evidence"]}
    actual = [dict(event, passage_id=pid) for pid, items in events.items() for event in items
              if event["rule"] == "source_restoration"]
    if len(actual) != len(expected_events) or {e.get("addition_id"): e for e in actual} != expected_events:
        raise ValueError("GA030 restoration ledger differs from exact additions")
    for pid, items in inserts.items():
        before = passages[pid]["text"]
        positions = [a["position_codepoint"] for a in items]
        if len(set(positions)) != len(positions):
            raise ValueError("GA030 restoration insertion positions are duplicated")
        for a in sorted(items, key=lambda a: a["position_codepoint"], reverse=True):
            position = a["position_codepoint"]
            if (type(position) is not int or not 0 <= position <= len(before)
                    or not a.get("following_anchor") or before[position:position + len(a["following_anchor"])] != a["following_anchor"]):
                raise ValueError("GA030 restored fragment insertion anchor differs")
            before = before[:position] + a["text"] + "\n\n" + before[position:]
        passages[pid]["text"] = before
        passages[pid]["checksum"] = digest(before.encode())
        passages[pid]["metadata"]["source_restorations"] = [a["id"] for a in items]
    for repair in recipe.get("original_metadata_repairs", []):
        if (repair.get("passage_id") != original_ids[1]
                or repair.get("source_token") != "[1895]"
                or repair.get("printed_page") != 183
                or repair.get("before") != {"ga_page": "S. 1895", "page_numbers": [1895]}
                or repair.get("after") != {"ga_page": None, "page_numbers": []}
                or not repair.get("evidence")):
            raise ValueError("GA030 literal year metadata repair contract differs")
        p = passages[repair["passage_id"]]
        if {"ga_page": p.get("ga_page"), "page_numbers": p["metadata"].get("page_numbers")} != repair["before"]:
            raise ValueError("GA030 original year metadata differs")
        with ZipFile(source) as archive:
            body = ET.fromstring(archive.read(repair["source_member"])).find("{http://www.w3.org/1999/xhtml}body")
            raw = "".join(body[repair["body_index"]].itertext())
        if digest(raw.encode()) != repair["source_paragraph_sha256"] or raw.count("[1895]") != 1:
            raise ValueError("GA030 literal year metadata source differs")
        p["ga_page"] = None
        p["metadata"]["page_numbers"] = []
    for field, repair in recipe.get("proofing_repairs", {}).items():
        if (field != "excluded_sections" or repair.get("archive_as") != "source_import_excluded_sections"
                or repair.get("after") != [] or not repair.get("evidence")
                or result.get("proofing", {}).get(field) != repair.get("before")
                or repair["archive_as"] in result["proofing"]):
            raise ValueError("GA030 restored editorial import exclusion metadata differs")
        result["proofing"][repair["archive_as"]] = deepcopy(repair["before"])
        result["proofing"][field] = []
    result["passage_count"] = len(result["passages"])
    return result


def inspect_ga030_layout(prior: dict, final: dict, recipe: dict, events: dict,
                        source: Path = GA030_SOURCE,
                        review_path: Path = GA030_REVIEW) -> tuple[list[str], int]:
    augmented = inspect_ga030_recovery(prior, recipe, events, source, review_path)
    errors = []
    expected_proofing = deepcopy(augmented["proofing"])
    expected_proofing["restored_sections"] = [{"id": a["id"], "passage_id": a["passage_id"],
        "source_role": a.get("source_role", "author"), "evidence": a["evidence"]}
        for a in recipe["source_additions"]]
    expected_proofing["known_source_gaps"] = deepcopy(recipe["known_gaps"])
    if final.get("proofing") != expected_proofing:
        errors.append("GA030 source restoration proofing metadata differs")
    if final.get("content_completeness") != prior.get("content_completeness"):
        errors.append("GA030 source completeness/gap status differs")
    projected_final = deepcopy(final)
    projected_final["proofing"] = deepcopy(augmented["proofing"])
    projected_final["content_completeness"] = augmented["content_completeness"]
    layout = projected_final.get("metadata", {}).get("source_layout", {})
    extra = {"source_epub_sha256": recipe["source_epub_sha256"],
             "source_restoration_count": len(recipe["source_additions"]),
             "original_passage_ids": list(recipe["original_passages"])}
    for key, value in extra.items():
        if layout.get(key) != value:
            errors.append("GA030 source-layout restoration metadata differs: " + key)
        layout.pop(key, None)
    final_by_id = {p["id"]: p for p in projected_final["passages"]}
    for passage in augmented["passages"]:
        pid = passage["id"]
        notes = passage["metadata"].pop("annotations", [])
        final_passage = final_by_id.get(pid)
        if final_passage is None:
            continue  # The strict generic inventory check reports this.
        if final_passage["metadata"].pop("annotations", []) != notes:
            errors.append(pid + ": retained/restored annotation inventory/source text differs")
    layout_errors, repairs = inspect_source_layout(augmented, projected_final, recipe, events)
    return errors + layout_errors, repairs


def pbm_raster(data: bytes) -> tuple[int, int, bytes]:
    """Decode Poppler's monochrome PBM into white-one pixels, padding zero."""
    tokens, offset = [], 0
    while len(tokens) < 3:
        while offset < len(data) and data[offset] in b" \t\r\n":
            offset += 1
        if offset < len(data) and data[offset] == 35:
            newline = data.find(b"\n", offset)
            if newline < 0:
                raise ValueError("Incomplete PBM comment")
            offset = newline + 1
            continue
        end = offset
        while end < len(data) and data[end] not in b" \t\r\n":
            end += 1
        if end == offset:
            raise ValueError("Incomplete PBM header")
        tokens.append(data[offset:end])
        offset = end
    if tokens[0] != b"P4" or offset >= len(data) or data[offset] not in b" \t\r\n":
        raise ValueError("Invalid monochrome PBM header")
    offset += 2 if data[offset:offset + 2] == b"\r\n" else 1
    width, height = int(tokens[1]), int(tokens[2])
    stride = (width + 7) // 8
    if width < 1 or height < 1 or len(data) - offset != stride * height:
        raise ValueError("PBM raster dimensions or data differ")
    raster = bytearray(value ^ 255 for value in data[offset:])
    if width % 8:
        mask = 255 << (8 - width % 8) & 255
        for row in range(height):
            raster[(row + 1) * stride - 1] &= mask
    return width, height, bytes(raster)


def crop_mono_raster(width: int, height: int, raster: bytes, box: list[int]) -> bytes:
    if (len(box) != 4 or any(type(value) is not int for value in box)
            or not 0 <= box[0] < box[2] <= width or not 0 <= box[1] < box[3] <= height):
        raise ValueError("Invalid original raster crop")
    stride, crop_stride = (width + 7) // 8, (box[2] - box[0] + 7) // 8
    result = bytearray(crop_stride * (box[3] - box[1]))
    for y in range(box[1], box[3]):
        for x in range(box[0], box[2]):
            bit = raster[y * stride + x // 8] >> (7 - x % 8) & 1
            result[(y - box[1]) * crop_stride + (x - box[0]) // 8] |= bit << (7 - (x - box[0]) % 8)
    return bytes(result)


def inspect_ga032_pdf_fragment(repair: dict, review: dict, pdf: Path = GA032_PDF) -> None:
    """Independently extract the printed fragment with Poppler, not recipe code."""
    checksum = "1155b523ddfece69a51a2c75a29f752a2c48742fad1eae03509835e8f6ac6bd7"
    if (digest(pdf.read_bytes()) != checksum or review.get("original_pdf_sha256") != checksum
            or repair.get("original_pdf_sha256") != checksum):
        raise ValueError("GA032 exact original PDF fragment source changed")
    expected = {
        "pdf_page": 451, "page_index": 450, "xobject_name": "/Im0", "width": 2483, "height": 3302,
        "decoded_stream_sha256": "669fe1686b81eafdb1bacd2685ce9b19bcc784b34d168f95ae7460f66683b2b6",
        "crop_box_pixels": [290, 2070, 2400, 2270], "crop_mode": "1",
        "crop_pixels_sha256": "b08d2ad799c4469d72dc082eac92a671bdaa1610ded9c734963c28e095234e2b",
        "visually_verified_text": ["Rolf Wolfgang Martens «Befreite Flügel» (Berlin 1899) ent-", "halten:"],
        "extracted_text_layer_omits_fragment": True, "source_token": "halten:",
    }
    if (repair.get("old") != "(Berlin 1899) ent-" or repair.get("new") != "(Berlin 1899) enthalten:"
            or repair.get("source_token") != "halten:" or repair.get("source_pdf_page") != 451
            or repair.get("pdf_raster_witness") != expected):
        raise ValueError("GA032 fragment exceeds its uniquely reviewed printed continuation")
    with tempfile.TemporaryDirectory(prefix="ga032-independent-raster-") as temporary:
        prefix = Path(temporary) / "image"
        try:
            subprocess.run(["pdfimages", "-f", "451", "-l", "451", str(pdf), str(prefix)],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (OSError, subprocess.CalledProcessError) as error:
            raise ValueError("Cannot independently read GA032 original PDF raster") from error
        images = list(Path(temporary).glob("image-*"))
        if len(images) != 1 or images[0].suffix != ".pbm":
            raise ValueError("GA032 original PDF page has an unexpected image inventory")
        width, height, raster = pbm_raster(images[0].read_bytes())
    # Poppler normalizes unused row bits; bind all visible pixels independently.
    if ((width, height) != (2483, 3302)
            or digest(raster) != "016931073d834c3df3ff77bf7fbdc9ba84c0b8d1e60a6040ad4fe277189138d0"
            or digest(crop_mono_raster(width, height, raster, expected["crop_box_pixels"]))
               != expected["crop_pixels_sha256"]):
        raise ValueError("GA032 independently extracted printed fragment pixels changed")


def inspect_ga032_word_repair(repair: dict, raw_parts: list[str]) -> None:
    """Keep physical joins and the five printed verse overruns within their witnesses."""
    if repair.get("kind") in {"physical_word_seam", "poetic_overrun"}:
        if len(raw_parts) < 2:
            raise ValueError("GA032 physical seam lacks both original source parts")
        context = " ".join(" ".join(raw.split()) for raw in raw_parts)
        if " ".join(repair["old"].split()) not in context:
            raise ValueError("GA032 physical seam lacks its exact original word/verse context")
    if repair.get("kind") == "physical_word_seam":
        match = re.fullmatch(r"([" + LETTERS + r"]+)-\s+([" + LETTERS + r"]+)", repair["old"])
        if (not match or repair.get("match_word_boundaries") is not True
                or repair["new"] not in {match[1] + match[2], match[1] + "-" + match[2]}):
            raise ValueError("GA032 word seam alters original letters or punctuation")
    if repair.get("kind") == "poetic_overrun":
        exact_overruns = {
            "Puls-\nDes Seins: die Krankheit und das Laster, [schlag":
                "Pulsschlag\nDes Seins: die Krankheit und das Laster,",
            "jegliches\nDas uns zürn Hohn sie geschaffen, [Blendwerk,":
                "jegliches Blendwerk,\nDas uns zürn Hohn sie geschaffen,",
            "hinter vergletscherten\nhinter Wüsten aus Nacht und Nichts [Ursonnen,":
                "hinter vergletscherten Ursonnen,\nhinter Wüsten aus Nacht und Nichts",
            "sich immer wieder\nMaikaterbart!» [sträubenden":
                "sich immer wieder sträubenden\nMaikaterbart!»",
            "schimmerndes\nEntrüstet\n[Wiesenblümchen":
                "schimmerndes Wiesenblümchen\nEntrüstet",
        }
        exact_overruns = {" ".join(old.split()): new for old, new in exact_overruns.items()}
        if exact_overruns.get(" ".join(repair["old"].split())) != repair.get("new"):
            raise ValueError("GA032 poetic overflow exceeds its exact printed continuation")


def inspect_ga032_layout(prior: dict, final: dict, recipe: dict, events: dict,
                        source: Path = GA032_SOURCE,
                        review_path: Path = GA032_REVIEW,
                        pdf: Path = GA032_PDF) -> tuple[list[str], int]:
    """Bind every retained GA032 source and boundary to its frozen EPUB review."""
    review = read(review_path)
    revision = digest(json.dumps(review, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    if recipe.get("source_evidence", {}).get("review_sha256") != revision:
        raise ValueError("GA032 source review identity differs")
    for key in ("work_id", "source_sha256", "source_epub_sha256"):
        if prior.get(key) != recipe.get(key) or recipe.get(key) != review.get(key):
            raise ValueError("GA032 retained source identity differs: " + key)
    if digest(source.read_bytes()) != review["source_epub_sha256"]:
        raise ValueError("GA032 original EPUB byte hash differs")
    pids = [p["id"] for p in prior["passages"]]
    if list(review["passages"]) != pids or list(recipe["passages"]) != pids:
        raise ValueError("GA032 source passage inventory/order differs")
    for key in ("metadata_repairs", "annotation_repairs", "known_gaps", "review_flags"):
        if recipe.get(key, []) != review.get(key, []):
            raise ValueError("GA032 recipe differs from frozen source review: " + key)
    source_evidence = {"review_sha256": revision, "method": review["method"],
                       "source_members": review["source_members"]}
    for key in ("original_doc_sha256", "original_pdf_sha256", "source_layout_sha256"):
        if key in review:
            source_evidence[key] = review[key]
    if recipe["source_evidence"] != source_evidence:
        raise ValueError("GA032 complete source evidence differs from frozen review")
    retained_members = {m["member"]: m["sha256"] for m in prior["proofing"]["source_members"]}
    if retained_members != review["source_members"]:
        raise ValueError("GA032 source-member inventory differs from retained import")
    expected, projected = deepcopy(prior), deepcopy(final)
    expected_by_id = {p["id"]: p for p in expected["passages"]}
    final_by_id = {p["id"]: p for p in projected["passages"]}
    checked_events = deepcopy(events)
    selected, prior_position = set(), None
    member_order = {member: index for index, member in enumerate(review["source_members"])}

    def source_parts(text, begin, end):
        parts, offset = [], 0
        for index, block in enumerate(text.split("\n\n")):
            left, right = max(begin, offset), min(end, offset + len(block))
            if left < right and text[left:right].strip():
                parts.append({"block": index, "start": left - offset, "end": right - offset})
            offset += len(block) + 2
        return parts

    with ZipFile(source) as archive:
        bodies = {}
        for member, checksum in review["source_members"].items():
            data = archive.read(member)
            if digest(data) != checksum:
                raise ValueError("GA032 original member byte hash differs: " + member)
            bodies[member] = ET.fromstring(data).find("{http://www.w3.org/1999/xhtml}body")

        def original(witness):
            member, index = witness["source_member"], witness["body_index"]
            if member not in bodies or type(index) is not int or not 0 <= index < len(bodies[member]):
                raise ValueError("GA032 invalid original body witness")
            element = bodies[member][index]
            path = ([witness["child_index"]] if "child_index" in witness else []) + witness.get("child_path", [])
            for child in path:
                if type(child) is not int or not 0 <= child < len(element):
                    raise ValueError("GA032 invalid original nested source witness")
                element = element[child]
            raw = "".join(element.itertext())
            if digest(raw.encode()) != witness["source_paragraph_sha256"]:
                raise ValueError("GA032 original paragraph witness differs")
            if not witness.get("evidence") and witness not in source_reconstruction:
                raise ValueError("GA032 reviewed boundary/repair lacks source evidence")
            return raw, (member_order[member], index, tuple(path))

        source_reconstruction = [part for p in review["passages"].values() for part in p["source_parts"]]
        for passage in prior["passages"]:
            pid, text = passage["id"], passage["text"]
            witness, plan = review["passages"][pid], recipe["passages"][pid]
            if (digest(text.encode()) != witness["input_sha256"] or witness["input_sha256"] != plan["input_sha256"]
                    or digest(passage["source_text"].encode()) != witness["source_text_sha256"]
                    or witness["source_text_sha256"] != plan["source_text_sha256"] or passage["title"] != witness["title"]):
                raise ValueError("GA032 retained text/source/title differs: " + pid)
            raw_parts = []
            for part in witness["source_parts"]:
                raw, position = original(part)
                if position in selected or prior_position is not None and position <= prior_position:
                    raise ValueError("GA032 original source reconstruction loses order or repeats text")
                selected.add(position)
                prior_position = position
                raw_parts.append(raw)
            if "\n\n".join(raw_parts) != passage["source_text"]:
                raise ValueError("GA032 retained source_text cannot be reconstructed exactly: " + pid)
            starts, omissions = witness["starts"], witness.get("omissions", [])
            if (not starts or starts[0]["start_codepoint"] != 0
                    or [s["start_codepoint"] for s in starts] != sorted({s["start_codepoint"] for s in starts})):
                raise ValueError("GA032 source paragraph boundaries are ambiguous: " + pid)
            if plan.get("edits", []) != witness.get("edits", []):
                raise ValueError("GA032 word repairs differ from frozen review: " + pid)
            for repair in witness.get("edits", []):
                if not repair.get("old") or not repair.get("evidence"):
                    raise ValueError("GA032 word repair lacks exact literal/evidence")
                if repair.get("kind") not in {"physical_word_seam", "literal_year_restoration", "poetic_overrun", "pdf_fragment_restoration"}:
                    raise ValueError("GA032 source repair has an unknown or missing reviewed kind")
                if "source_member" in repair or "source_paragraph_sha256" in repair:
                    original(repair)
                for origin in repair.get("source_witnesses", []):
                    original(dict(origin, evidence=repair["evidence"]))
                inspect_ga032_word_repair(repair, [original(dict(origin, evidence=repair["evidence"]))[0]
                                                   for origin in repair.get("source_witnesses", [])])
                if repair.get("kind") == "pdf_fragment_restoration":
                    raw, _ = original(repair)
                    if repair["old"] not in " ".join(raw.split()):
                        raise ValueError("GA032 restored fragment lacks its retained source word context")
                    inspect_ga032_pdf_fragment(repair, review, pdf)
                if repair.get("kind") == "literal_year_restoration":
                    raw, _ = original(repair)
                    token = repair.get("source_token", "")
                    match = re.fullmatch(r"\[(18\d{2}|190[0-2])\]", token)
                    if not match or raw.count(token) != 1:
                        raise ValueError("GA032 literal year lacks an exact original token")
                    year = match.group(1)
                    if " ".join(repair["new"].split()) not in " ".join(raw.replace(token, year).split()):
                        raise ValueError("GA032 literal year is not restored at its exact original word position")
                    occurrences = list(re.finditer(r"(?<!\d)" + year + r"(?!\d)", repair["new"]))
                    if not any(" ".join((repair["new"][:m.start()] + repair["new"][m.end():]).split())
                               == " ".join(repair["old"].split()) for m in occurrences):
                        raise ValueError("GA032 literal year repair changes additional source wording")
            expected_omissions = []
            for omission in omissions:
                original(omission)
                slices = source_parts(text, omission["start_codepoint"], omission["end_codepoint"])
                if len(slices) != 1:
                    raise ValueError("GA032 page furniture is not one exact retained source slice")
                expected_omissions.append(slices[0] | {k: deepcopy(v) for k, v in omission.items()
                    if k not in {"start_codepoint", "end_codepoint"}})
            if plan.get("omitted_parts", []) != expected_omissions:
                raise ValueError("GA032 page furniture differs from frozen source review: " + pid)
            segments = []
            for index, start in enumerate(starts):
                original(start)
                begin = start["start_codepoint"]
                end = starts[index + 1]["start_codepoint"] if index + 1 < len(starts) else len(text)
                if not 0 <= begin < end <= len(text) or not text[begin:].startswith(start["canonical_anchor"]):
                    raise ValueError("GA032 exact retained paragraph anchor differs: " + pid)
                line_starts = start.get("line_starts", [])
                if (line_starts and (start["kind"] not in {"verse", "note"}
                        or line_starts != sorted(set(line_starts))
                        or any(type(point) is not int or not begin < point < end for point in line_starts))):
                    raise ValueError("GA032 true source line boundaries are invalid")
                points = [begin] + line_starts + [end]
                spans = list(zip(points, points[1:]))
                for omission in omissions:
                    left, right = omission["start_codepoint"], omission["end_codepoint"]
                    spans = [piece for l, r in spans for piece in
                        ([(l, r)] if right <= l or left >= r else [(l, min(r, left)), (max(l, right), r)]) if piece[0] < piece[1]]
                parts = [part for l, r in spans if text[l:r].strip() for part in source_parts(text, l, r)]
                segment = {"kind": start["kind"], "parts": parts,
                    "join": start.get("join", "\n" if start["kind"] == "verse" else " "), "evidence": start["evidence"],
                    "source_pdf_pages": deepcopy(start.get("source_pdf_pages", [start["page"]] if start.get("page") else []))}
                if start["kind"] == "heading":
                    segment["level"] = start.get("level", 2)
                for field in ("preserve_lines", "poem_start", "separator", "page_evidence"):
                    if field in start:
                        segment[field] = deepcopy(start[field])
                if start.get("page_anchor"):
                    segment["pages"] = [start["page_anchor"]]
                segments.append(segment)
            if plan["segments"] != segments:
                raise ValueError("GA032 complete layout slices differ from frozen source boundaries: " + pid)
        repaired_fields = set()
        for repair in recipe.get("metadata_repairs", []):
            raw, _ = original(repair)
            pid, before, after = repair["passage_id"], repair["before"], repair["after"]
            if not before or set(before) != set(after) or not set(before) <= {"title", "ga_page", "page_numbers"}:
                raise ValueError("GA032 source metadata repair has an invalid field contract")
            passage = expected_by_id[pid]
            if "title" in after:
                origins = repair.get("source_witnesses", [])
                title = " ".join(" ".join(original(dict(origin, evidence=repair["evidence"]))[0].split())
                                 for origin in origins) if origins else " ".join(raw.split())
                rendered_title = after["title"]
                if pid == "ga-032-doc-heading-21":
                    rendered_title = rendered_title.replace(" — Einleitung", " Einleitung")
                if " ".join(rendered_title.split()) != title:
                    raise ValueError("GA032 restored metadata title differs from its complete original heading")
            if set(after) & {"ga_page", "page_numbers"} and not {"ga_page", "page_numbers"} <= set(after):
                raise ValueError("GA032 source page repair omits its exact paired metadata fields")
            if "page_numbers" in after:
                if (after["page_numbers"] != [] or after.get("ga_page") is not None
                        or not before["page_numbers"]
                        or any(type(year) is not int or year < 1800 or year > 1902
                               or f"[{year}]" not in passage["source_text"] for year in before["page_numbers"])):
                    raise ValueError("GA032 page metadata repair exceeds its genuine source-year mistakes")
            for field, value in before.items():
                actual = passage["metadata"].get(field) if field == "page_numbers" else passage.get(field)
                if actual != value or (pid, field) in repaired_fields:
                    raise ValueError("GA032 source metadata repair changes an unexpected field value")
                repaired_fields.add((pid, field))
                (passage["metadata"] if field == "page_numbers" else passage)[field] = deepcopy(after[field])
        repaired_annotations = set()
        for repair in recipe.get("annotation_repairs", []):
            raw, _ = original(repair)
            pid, aid = repair["passage_id"], repair["annotation_id"]
            element = bodies[repair["source_member"]][repair["body_index"]]
            if ((pid, aid) in repaired_annotations or "#" not in aid
                    or aid.split("#", 1)[0] != repair["source_member"]
                    or element.get("id") != aid.split("#", 1)[1] or element.get("role") != "doc-footnote"
                    or not isinstance(repair.get("before"), str) or "\n\n" in repair["before"]
                    or raw.strip() != repair["before"]
                    or re.sub(r"\s*\n\s*", " ", repair["before"]) != repair.get("after")):
                raise ValueError("GA032 annotation repair changes unreviewed source wording or structure")
            matches = [note for note in expected_by_id[pid]["metadata"].get("annotations", []) if note["id"] == aid]
            if len(matches) != 1 or matches[0]["marker"] != repair["marker"] or matches[0]["text"] != repair["before"]:
                raise ValueError("GA032 annotation repair differs from original inventory/text")
            repaired_annotations.add((pid, aid))
            matches[0]["text"] = repair["after"]
        for pid, passage in expected_by_id.items():
            if recipe["passages"][pid]["group_title"] != review["passages"][pid].get("group_title", passage["title"]):
                raise ValueError("GA032 source group title differs from frozen review: " + pid)
    errors = []
    original_by_id = {p["id"]: p for p in prior["passages"]}
    for pid, passage in expected_by_id.items():
        actual = final_by_id.get(pid)
        if actual is None:
            continue
        notes = passage["metadata"].pop("annotations", [])
        plan = recipe["passages"][pid]
        canonical = lambda value: digest(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                                   separators=(",", ":")).encode())
        if (plan.get("annotations_input_sha256") != canonical(original_by_id[pid]["metadata"].get("annotations", []))
                or plan.get("annotations_output_sha256") != canonical(notes)):
            errors.append(pid + ": frozen original/projected annotation byte hashes differ")
        if actual["metadata"].pop("annotations", []) != notes:
            errors.append(pid + ": original annotation inventory/source text changed")
        output_metadata = {"title": actual["title"], "ga_page": actual.get("ga_page"),
                           "page_numbers": actual["metadata"].get("page_numbers")}
        if plan.get("output_metadata") != output_metadata:
            errors.append(pid + ": frozen output title/page metadata differs")
        witness = review["passages"][pid]
        section_starts = [index for index, start in enumerate(witness["starts"]) if start.get("section_start")]
        sections = []
        if section_starts and section_starts[0] != 0:
            raise ValueError("GA032 source article sections omit retained initial text")
        for number, index in enumerate(section_starts):
            end = section_starts[number + 1] if number + 1 < len(section_starts) else len(witness["starts"])
            block = actual["metadata"]["reading_blocks"][index]
            encoded = actual["text"].encode("utf-16-le")
            heading = encoded[2 * block["start_offset"]:2 * block["end_offset"]].decode("utf-16-le").split("\n", 1)[0]
            if number and block["kind"] != "heading":
                raise ValueError("GA032 source article lacks its original heading")
            sections.append({"start_segment": index, "end_segment": end,
                "title": passage["title"] if not number else heading,
                "label_kind": "source_title", "evidence": witness["starts"][index]["evidence"]})
        if plan.get("sections", []) != sections:
            raise ValueError("GA032 source article sections differ from frozen review")
        metadata_repairs = [r for r in recipe.get("metadata_repairs", []) if r["passage_id"] == pid]
        annotation_repairs = [r for r in recipe.get("annotation_repairs", []) if r["passage_id"] == pid]
        fragments = [r for r in plan.get("edits", []) if r.get("kind") == "pdf_fragment_restoration"]
        for event in checked_events.get(pid, []):
            if event["rule"] == "source_layout":
                if event.get("metadata_replacements", []) != metadata_repairs:
                    errors.append(pid + ": source metadata repair ledger differs")
                event.pop("metadata_replacements", None)
                if event.get("annotation_replacements", []) != annotation_repairs:
                    errors.append(pid + ": annotation whitespace repair ledger differs")
                event.pop("annotation_replacements", None)
                if event.get("source_fragment_restorations", []) != fragments:
                    errors.append(pid + ": printed fragment restoration ledger differs")
                event.pop("source_fragment_restorations", None)
    if ("table_of_contents" in recipe) != ("table_of_contents" in review):
        raise ValueError("GA032 original contents are not bound to frozen source review")
    if "table_of_contents" in review:
        targets = {}
        for pid, witness in review["passages"].items():
            for index, start in enumerate(witness["starts"]):
                if start.get("toc_target"):
                    if start["toc_target"] in targets:
                        raise ValueError("GA032 original contents target is duplicated")
                    targets[start["toc_target"]] = (pid, index)
        toc = []
        for row in review["table_of_contents"]:
            if "source_heading_witness" in row:
                raw, _ = original(dict(row["source_heading_witness"], evidence="Original printed contents division"))
                if (raw.strip() != row["title"] or row["title"] not in {"I", "II", "III"}
                        or row["level"] != 1 or row["parent_id"] is not None):
                    raise ValueError("GA032 contents division differs from its exact original heading")
            pid, index = targets[row["target"]]
            target = final_by_id[pid]["metadata"]["reading_blocks"][index]["start_offset"]
            toc.append({k: deepcopy(v) for k, v in row.items() if k != "target"} | {"passage_id": pid, "start_offset": target})
        if recipe["table_of_contents"] != toc:
            raise ValueError("GA032 original contents titles/targets differ from frozen source review")
    layout = projected.get("metadata", {}).get("source_layout", {})
    extra = {"source_epub_sha256": recipe["source_epub_sha256"], "review_sha256": revision,
             "source_evidence": source_evidence}
    for key, value in extra.items():
        if layout.get(key) != value:
            errors.append("GA032 source-layout provenance differs: " + key)
        layout.pop(key, None)
    layout_errors, repairs = inspect_source_layout(expected, projected, recipe, checked_events)
    return errors + layout_errors, repairs


def evidence(baseline: Path, works: list[dict]):
    occurrences = Counter()
    work_counts = Counter()
    hyphenated = Counter()
    for work in works:
        if not work.get("content_path"):
            continue
        document = read(content_file(baseline, work["id"]))
        seen = set()
        for passage in document["passages"]:
            text = passage["text"].replace("\u00ad", "")
            tokens = re.findall(rf"\b[{LETTERS}]{{3,}}\b", text)
            occurrences.update(token.lower() for token in tokens)
            seen.update(token.lower() for token in tokens)
            hyphenated.update(
                (match[1].lower(), match[2].lower())
                for match in re.finditer(rf"\b([{LETTERS}]+)-\s*([{LETTERS}]+)\b", text)
            )
        work_counts.update(seen)
    return occurrences, work_counts, hyphenated


def compare_characters(before: str, after: str, allowed_ocr: dict | None = None,
                       ocr_edits: list | None = None,
                       allowed_splits: set | None = None) -> tuple[list[dict], list[dict], str | None]:
    """Align exact non-whitespace characters, permitting only hyphen deletion.

    Unlike calling the repair code again, this checks what the staged result
    actually did. It records original positions, so a word replacement cannot
    hide a letter edit behind a broadly normalized comparison.
    """
    i = j = 0
    hard = []
    soft = []
    while True:
        while i < len(before) and before[i].isspace():
            i += 1
        while j < len(after) and after[j].isspace():
            j += 1
        if i < len(before) and before[i] == "\u00ad":
            soft.append({"before_offset": i, "after_offset": j, "kind": "soft_hyphen"})
            i += 1
            continue
        if i == len(before) and j == len(after):
            return hard, soft, None
        if i >= len(before) or j >= len(after):
            return hard, soft, f"Unexpected text suffix at original {i}, corrected {j}"
        # Accept only an approved full-token substitution recorded for this
        # exact passage. Test it before matching an unchanged initial letter.
        old_boundary = i == 0 or not (before[i - 1].isalnum() or before[i - 1] == "_")
        new_boundary = j == 0 or not (after[j - 1].isalnum() or after[j - 1] == "_")
        if allowed_ocr and old_boundary and new_boundary:
            raw_token = RAW_TOKEN.match(before, i)
            if raw_token:
                original = raw_token[0].replace("\u00ad", "")
                end = raw_token.end()
                composed_hard = []
                while True:
                    replacement = allowed_ocr.get(original)
                    end_boundary = end == len(before) or not (before[end].isalnum() or before[end] == "_")
                    new_end = j + len(replacement) if replacement else j
                    new_end_boundary = new_end == len(after) or (new_end < len(after) and not (after[new_end].isalnum() or after[new_end] == "_"))
                    if replacement and end_boundary and new_end_boundary and after.startswith(replacement, j):
                        break
                    next_part = NEXT_WORD_PART.match(before, end)
                    if not next_part:
                        replacement = None
                        break
                    right = next_part[2].replace("\u00ad", "")
                    if (original, right) not in (allowed_splits or set()):
                        replacement = None
                        break
                    composed_hard.append({"before_offset": end, "after_offset": j,
                                          "kind": "hard_hyphen", "left": original,
                                          "right": right, "gap": next_part[1]})
                    original += right
                    end = next_part.end()
                    if len(original) > max(map(len, allowed_ocr)):
                        replacement = None
                        break
                if replacement:
                    if ocr_edits is not None:
                        ocr_edits.append({"before_offset": i, "after_offset": j, "kind": "reviewed_ocr",
                                          "original": original, "word": replacement})
                    hard.extend(composed_hard)
                    soft.extend({"before_offset": offset, "after_offset": j, "kind": "soft_hyphen"}
                                for offset in range(i, end) if before[offset] == "\u00ad")
                    i = end
                    j = new_end
                    continue
        if before[i] == after[j]:
            i += 1
            j += 1
            continue
        if before[i] == "-":
            left_start = i
            while left_start > 0 and before[left_start - 1] in LETTER_SET:
                left_start -= 1
            left_word = before[left_start:i].replace("\u00ad", "")
            right = AFTER_HYPHEN.match(before, i + 1)
            right_word = right[2].replace("\u00ad", "") if right else ""
            if left_word and right and right_word and right_word[0] == after[j]:
                hard.append({"before_offset": i, "after_offset": j, "kind": "hard_hyphen",
                             "left": left_word, "right": right_word, "gap": right[1]})
                i += 1
                continue
        return hard, soft, f"Character mismatch at original {i} ({before[i]!r}), corrected {j} ({after[j]!r})"


def sample(before: str, after: str, edit: dict) -> dict:
    old = edit["before_offset"]
    new = edit["after_offset"]
    return {**edit,
            "before": before[max(0, old - 90):old + 150],
            "after": after[max(0, new - 90):new + 150]}


def utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def source_boundary_offset(before: str, after: str, boundary: int) -> int:
    """Project a reviewed source boundary using exact matching spans.

    Unmatched lexical interiors cannot be guessed. Whitespace collapses map to
    the next visible character; UTF-16 conversion happens after this alignment.
    This uses matching spans independently of the application engine's opcodes.
    """
    if type(boundary) is not int or not 0 <= boundary <= len(before):
        raise ValueError("invalid source page boundary")
    if before == after:
        while boundary < len(after) and after[boundary].isspace():
            boundary += 1
        return utf16_length(after[:boundary])
    old_end = new_end = 0
    projected = len(after)
    for span in SequenceMatcher(None, before, after, autojunk=False).get_matching_blocks():
        if old_end <= boundary < span.a:
            if boundary > old_end and before[old_end:span.a].strip():
                raise ValueError("source page boundary falls inside a lexical repair")
            projected = new_end
            break
        if span.a <= boundary < span.a + span.size:
            projected = span.b + boundary - span.a
            break
        old_end, new_end = span.a + span.size, span.b + span.size
    while projected < len(after) and after[projected].isspace():
        projected += 1
    return utf16_length(after[:projected])


def inspect_source_layout(prior: dict, final: dict, recipe: dict,
                          events: dict) -> tuple[list[str], int]:
    """Independently project exact reviewed slices; never call repair code.

    The pre-layout bytes still undergo the original strict corpus validator.
    This second leg accepts no implicit metadata changes or unrecorded spelling
    allowance: projected text must match both the frozen output hash and every
    final byte, and its explicit repair ledger must match the source recipe.
    """
    errors, repair_count = [], 0
    if recipe.get("schema_version") != 1 or recipe.get("offset_unit") != "utf16":
        return ["Unsupported source-layout recipe schema/offset unit"], 0
    if prior.get("work_id") != recipe.get("work_id") or any(
        prior.get(key) != recipe.get(key) for key in ("source_sha256", "source_epub_sha256")
    ):
        return ["Source-layout recipe does not match retained source identity"], 0
    if list(recipe["passages"]) != [p["id"] for p in prior["passages"]]:
        return ["Source-layout recipe passage inventory/order differs"], 0
    layout_ids = {pid for pid, items in events.items()
                  if any(item["rule"] == "source_layout" for item in items)}
    if layout_ids != set(recipe["passages"]):
        return ["Source-layout ledger passage inventory differs from recipe"], 0
    if [p["id"] for p in final["passages"]] != [p["id"] for p in prior["passages"]]:
        return ["Source-layout final passage inventory/order differs"], 0
    revision = digest(json.dumps(recipe, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")).encode())
    expected = deepcopy(prior)
    kinds = {"heading", "verse", "prose", "attribution", "note"}
    for passage in expected["passages"]:
        pid = passage["id"]
        plan = recipe["passages"][pid]
        if digest(passage["text"].encode()) != plan.get("input_sha256"):
            errors.append(f"{pid}: pre-layout text differs from frozen recipe input")
            continue
        if plan.get("source_text_sha256") and digest(passage.get("source_text", "").encode()) != plan["source_text_sha256"]:
            errors.append(f"{pid}: retained source differs from frozen recipe input")
            continue
        blocks = passage["text"].split("\n\n")
        covered = [[0] * len(block) for block in blocks]

        def take(part):
            index = part if type(part) is int else part["block"]
            if type(index) is not int or not 0 <= index < len(blocks):
                raise ValueError("invalid source block")
            start = 0 if type(part) is int else part.get("start", 0)
            end = len(blocks[index]) if type(part) is int else part.get("end", len(blocks[index]))
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(blocks[index]):
                raise ValueError("invalid source slice")
            for position in range(start, end):
                covered[index][position] += 1
            return blocks[index][start:end]

        texts, separators, reading, anchors, replacements, segment_ranges = [], [], [], [], [], []
        applied_edits = Counter()
        try:
            for omitted in plan.get("omitted_parts", []):
                token = take(omitted)
                header = (omitted.get("kind") == "running_header"
                          or (recipe.get("work_id") in {"ga-030", "ga-032", "ga-033", "ga-034", "ga-035", "ga-036", "ga-045"} and omitted.get("kind") == "page_footer"))
                header = (header
                          and digest(token.encode()) == omitted.get("text_sha256"))
                if (not (header or re.fullmatch(r"[\d '\"’.,]+", token))
                        or not omitted.get("evidence") or type(omitted.get("page")) is not int
                        or omitted["page"] < 1):
                    raise ValueError("omission is not exact, evidenced page furniture")
                replacements.append({"original": token, "word": "", "count": 1,
                                     "evidence": omitted["evidence"], "page": omitted["page"]})
            offset = 0
            for segment in plan["segments"]:
                kind, join = segment["kind"], segment.get("join", "\n")
                separator = segment.get("separator", "\n\n") if texts else ""
                if kind not in kinds or join not in {" ", "\n"} or separator not in {"", "\n", "\n\n"}:
                    raise ValueError("invalid semantic source segment")
                preserve_lines = segment.get("preserve_lines", False)
                if type(preserve_lines) is not bool or (preserve_lines and kind != "note"):
                    raise ValueError("literal note lines require an explicit valid note segment")
                source_parts = [take(part) for part in segment["parts"]]
                def transform(part):
                    return re.sub(r"\s*\n\s*", " ", part) if kind != "verse" and not preserve_lines else part
                parts = [transform(part) for part in source_parts]
                text = joined_source = join.join(parts)
                source_page_points = []
                for cue in segment.get("page_evidence", []):
                    part_index, point = cue.get("part_index", 0), cue.get("start_codepoint", 0)
                    if (type(part_index) is not int or not 0 <= part_index < len(source_parts)
                            or type(point) is not int or not 0 <= point < len(source_parts[part_index])):
                        raise ValueError("invalid source page slice")
                    source_page_points.append(len(join.join(parts[:part_index]))
                                              + (len(join) if part_index else 0)
                                              + len(transform(source_parts[part_index][:point])))
                for edit in plan.get("edits", []):
                    if not edit.get("old") or not edit.get("evidence"):
                        raise ValueError("lexical edit lacks an exact old anchor/evidence")
                    if edit.get("kind") == "source_heading_restoration":
                        if not segment["parts"]:
                            continue
                        first = segment["parts"][0]
                        block_index = first if type(first) is int else first["block"]
                        point = sum(len(value) + 2 for value in blocks[:block_index]) + (0 if type(first) is int else first.get("start", 0))
                        if kind != "heading" or point != edit.get("heading_start_codepoint"):
                            continue
                    bounded = edit.get("match_word_boundaries", False)
                    if type(bounded) is not bool or (bounded and recipe.get("work_id") not in {"ga-030", "ga-032", "ga-033", "ga-034", "ga-035", "ga-036", "ga-045"}):
                        raise ValueError("invalid edition-bound literal word repair")
                    pattern = re.compile(r"(?<!\w)" + re.escape(edit["old"]) + r"(?!\w)") if bounded else None
                    count = len(pattern.findall(text)) if pattern else text.count(edit["old"])
                    if count:
                        applied_edits[edit["old"]] += count
                        replacements.append({"original": edit["old"], "word": edit["new"],
                                             "count": count, "evidence": edit["evidence"]})
                        text = pattern.sub(lambda _: edit["new"], text) if pattern else text.replace(edit["old"], edit["new"])
                if plan.get("typographic_dashes"):
                    if not isinstance(plan["typographic_dashes"], str):
                        raise ValueError("typographic dash repair lacks source evidence")
                    text, count = re.subn(r"(?<!\S)-(?!\S)", "–", text)
                    if count:
                        replacements.append({"original": "-", "word": "–", "count": count,
                                             "evidence": plan["typographic_dashes"]})
                if re.search(r"\[\d{1,4}\]", text):
                    raise ValueError("unreviewed inline page marker")
                text = re.sub(r"[ \t]{2,}", " ", text)
                text = re.sub(r"^[ \t]+|[ \t]+$", "", text, flags=re.M).strip()
                if not text:
                    segment_ranges.append(None)
                    continue
                offset += len(separator)
                start, offset = offset, offset + utf16_length(text)
                block = {"kind": kind, "start_offset": start, "end_offset": offset}
                if kind == "heading":
                    block["level"] = segment.get("level", 2)
                    if type(block["level"]) is not int or not 1 <= block["level"] <= 6:
                        raise ValueError("invalid heading level")
                if segment.get("poem_start"):
                    block["poem_start"] = True
                reading.append(block)
                segment_ranges.append((start, offset))
                for page in segment.get("pages", []):
                    anchors.append({"page": page, "start_offset": start,
                                    "source": "original_doc_page_footer"})
                for cue, point in zip(segment.get("page_evidence", []), source_page_points):
                    anchors.append({"page": cue["page"],
                                    "start_offset": start + source_boundary_offset(joined_source, text, point),
                                    "source": cue.get("source", "original_doc_page_footer"), "confidence": cue["confidence"],
                                    "source_section": cue["source_section"]})
                texts.append(text)
                separators.append(separator)
            if any(not applied_edits[edit["old"]] for edit in plan.get("edits", [])):
                raise ValueError("approved lexical edit no longer matches its source context")
            if any(count != 1 and not char.isspace() for block, counts in zip(blocks, covered)
                   for char, count in zip(block, counts)):
                raise ValueError("lost or duplicated source characters")
            projected = "".join(separator + text for separator, text in zip(separators, texts))
            if not plan.get("output_sha256") or digest(projected.encode()) != plan["output_sha256"]:
                raise ValueError("projected text differs from frozen recipe output")
            passage.update(text=projected, checksum=digest(projected.encode()))
            if plan.get("title"):
                passage["title"] = plan["title"]
            meta = passage.setdefault("metadata", {})
            meta.update(reading_blocks=reading, group_title=plan["group_title"], structure_revision=revision)
            if "sections" in plan:
                sections = plan["sections"]
                if not isinstance(sections, list) or not sections:
                    raise ValueError("reading sections must cover the full nonempty passage")
                if len(reading) != len(segment_ranges):
                    raise ValueError("empty segments cannot anchor reading sections")
                encoded = projected.encode("utf-16-le")
                section_end, projected_sections = 0, []
                for index, section in enumerate(sections):
                    first, last = section["start_segment"], section["end_segment"]
                    if (type(first) is not int or type(last) is not int
                            or not 0 <= first < last <= len(segment_ranges)
                            or segment_ranges[first] is None or segment_ranges[last - 1] is None):
                        raise ValueError("invalid reading section segment range")
                    start, end = segment_ranges[first][0], segment_ranges[last - 1][1]
                    if start < section_end or encoded[2 * section_end:2 * start].decode("utf-16-le").strip():
                        raise ValueError("reading sections overlap or omit visible text")
                    title, label_kind = section["title"], section["label_kind"]
                    if not isinstance(title, str) or not title.strip() or not section.get("evidence"):
                        raise ValueError("reading section title lacks source evidence")
                    within = [b for b in reading if start <= b["start_offset"] and b["end_offset"] <= end]
                    first_block = within[0]
                    first_line = encoded[2 * first_block["start_offset"]:2 * first_block["end_offset"]].decode("utf-16-le").split("\n", 1)[0]
                    if label_kind == "incipit":
                        if first_block["kind"] != "verse" or title != first_line:
                            raise ValueError("reading section incipit differs from first verse line")
                    elif label_kind == "source_title":
                        if not (first_block["kind"] == "heading" and title == first_line
                                or index == 0 and start == 0 and title == passage["title"]):
                            raise ValueError("reading section source title has no original heading")
                    else:
                        raise ValueError("invalid reading section label kind")
                    projected_sections.append({"id": pid if index == 0 else f"{pid}-section-{index + 1}",
                                               "title": title, "label_kind": label_kind,
                                               "start_offset": start, "end_offset": end})
                    section_end = end
                if encoded[2 * section_end:].decode("utf-16-le").strip():
                    raise ValueError("reading sections omit final visible text")
                meta["reading_sections"] = projected_sections
            if anchors:
                if any(type(a["page"]) is not int or a["page"] < 1 for a in anchors):
                    raise ValueError("invalid source page anchor")
                meta["page_anchors"] = [anchor for i, anchor in enumerate(anchors)
                                        if i == 0 or anchor["page"] != anchors[i - 1]["page"]]
                pages = list(dict.fromkeys(a["page"] for a in anchors))
                meta.update(page_numbers=pages, page_marker_source=plan.get("page_marker_source", "source_bound_original_doc_page_footers"))
                passage["ga_page"] = f"S. {min(pages)}" if len(pages) == 1 else f"S. {min(pages)}–{max(pages)}"
            if set(plan.get("annotations", {})) != {note["id"] for note in meta.get("annotations", [])}:
                raise ValueError("footnote definition inventory differs from original notes")
            for note in meta.get("annotations", []):
                definition = plan["annotations"][note["id"]]
                note.setdefault("source_text", note["text"])
                note["text"] = definition["text"]
                context = definition["reference_context"]
                if projected.count(context) != 1 or not note["marker"] or note["marker"] not in context:
                    raise ValueError("missing or ambiguous footnote reference")
                start = projected.index(context) + context.rindex(note["marker"])
                note.update(start_offset=utf16_length(projected[:start]),
                            end_offset=utf16_length(projected[:start]) + utf16_length(note["marker"]))
            logged = [event for event in events[pid] if event["rule"] == "source_layout"]
            if len(logged) != 1 or logged[0].get("count") != 1 or logged[0].get("layout_blocks") != len(reading):
                raise ValueError("missing, duplicated or inconsistent layout ledger event")
            if logged[0].get("replacements", []) != replacements:
                raise ValueError("layout ledger replacements differ from approved recipe/counts")
            repair_count += sum(item["count"] for item in replacements)
        except (KeyError, TypeError, ValueError, IndexError) as error:
            errors.append(f"{pid}: source-layout verification failed: {error}")
    toc, group_id, last_group = [], None, None
    for passage in expected["passages"]:
        meta = passage.get("metadata", {})
        if "reading_blocks" not in meta or "group_title" not in meta:
            continue
        group = meta["group_title"]
        if group != last_group:
            group_id = f"{prior['work_id']}-part-{sum(e['level'] == 1 for e in toc) + 1}"
            toc.append(dict(id=group_id, title=group, level=1, passage_id=passage["id"], start_offset=0, parent_id=None))
            last_group = group
        encoded = passage["text"].encode("utf-16-le")
        sections = meta.get("reading_sections", [{"id": passage["id"], "title": passage["title"],
                                                  "start_offset": 0, "end_offset": len(encoded) // 2}])
        for section in sections:
            toc.append(dict(id=section["id"], title=section["title"], level=2, passage_id=passage["id"],
                            start_offset=section["start_offset"], parent_id=group_id))
            parents = {1: group_id, 2: section["id"]}
            headings = []
            for index, block in enumerate(meta["reading_blocks"]):
                if block["kind"] != "heading" or not section["start_offset"] <= block["start_offset"] < section["end_offset"]:
                    continue
                title = encoded[2 * block["start_offset"]:2 * block["end_offset"]].decode("utf-16-le")
                if "reading_sections" in meta and title == section["title"] and block["start_offset"] == section["start_offset"]:
                    continue
                headings.append((index, block, title))
            first_heading_level = min((block.get("level", 2) for _, block, _ in headings), default=0)
            for index, block, title in headings:
                level = (block.get("level", 2) - first_heading_level + 3
                         if "reading_sections" in meta else block.get("level", 2) + 2)
                identifier = f"{passage['id']}-heading-{index + 1}"
                toc.append(dict(id=identifier, title=title, level=level, passage_id=passage["id"],
                                start_offset=block["start_offset"], parent_id=parents[max(p for p in parents if p < level)]))
                parents = {key: value for key, value in parents.items() if key < level}
                parents[level] = identifier
    expected["table_of_contents"] = toc
    if "table_of_contents" in recipe:
        toc = deepcopy(recipe["table_of_contents"])
        passages = {p["id"]: p for p in expected["passages"]}
        seen = {}
        for entry in toc:
            try:
                target = passages[entry["passage_id"]]["text"].encode("utf-16-le")
                offset, level = entry["start_offset"], entry["level"]
                if (not entry["id"] or entry["id"] in seen or not entry["title"].strip()
                        or type(offset) is not int or not 0 <= offset < len(target) // 2
                        or type(level) is not int or not 1 <= level <= 6
                        or entry["parent_id"] is not None and (entry["parent_id"] not in seen
                            or seen[entry["parent_id"]]["level"] >= level)):
                    raise ValueError("invalid frozen original contents target")
                target[:2 * offset].decode("utf-16-le")
                seen[entry["id"]] = entry
            except (KeyError, TypeError, ValueError, UnicodeDecodeError) as error:
                errors.append(f"Source-layout original contents verification failed: {error}")
        expected["table_of_contents"] = toc
    expected.setdefault("metadata", {})["source_layout"] = {
        "recipe_sha256": revision, "source_sha256": recipe["source_sha256"],
        "source_url": recipe["source_url"], "offset_unit": "utf16", "review_scope": "structure_and_evidenced_repairs"}
    for key in set(expected) | set(final):
        if key == "passages":
            for a, b in zip(expected[key], final[key]):
                if a != b:
                    fields = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
                    errors.append(f"{a['id']}: final layout projection differs in {', '.join(fields)}")
        elif expected.get(key) != final.get(key):
            errors.append(f"Final layout projection differs in document {key}")
    return errors, repair_count


def inspect_source_outline(prior: dict, final: dict, plan: dict,
                           events: dict) -> tuple[list[str], int]:
    """Check metadata-only outlines independently of their application engine.

    Frozen edition and text identities gate a complete expected-document
    comparison. Only the reviewed titles, optional reading blocks/group data,
    contents and outline provenance may differ; pages, notes, source text and
    every other field remain byte-for-byte values from the retained input.
    """
    errors = []
    try:
        if prior.get("work_id") != plan.get("work_id"):
            raise ValueError("outline work identity differs")
        identity = plan["source_identity"]
        if not isinstance(identity, dict) or not identity:
            raise ValueError("outline lacks a frozen source identity")
        if any(prior.get(key) != value for key, value in identity.items()):
            raise ValueError("outline edition/hash differs from retained input")
        prior_ids = [p["id"] for p in prior["passages"]]
        if len(set(prior_ids)) != len(prior_ids) or list(plan["passages"]) != prior_ids:
            raise ValueError("outline recipe passage inventory/order differs")
        if [p["id"] for p in final["passages"]] != prior_ids:
            raise ValueError("outline final passage inventory/order differs")
        recipe_hash = digest(json.dumps(plan, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":")).encode())
        expected = deepcopy(prior)
        boundaries = {}
        for passage in expected["passages"]:
            pid, text = passage["id"], passage["text"]
            section = plan["passages"][pid]
            if digest(text.encode()) != section["text_sha256"]:
                raise ValueError(f"{pid}: pre-outline text differs from frozen input")
            if digest(passage.get("source_text", "").encode()) != section["source_text_sha256"]:
                raise ValueError(f"{pid}: pre-outline source text differs from frozen input")
            if passage.get("checksum") != digest(text.encode()):
                raise ValueError(f"{pid}: retained text checksum differs")
            title = section["title"]
            if not isinstance(title, str) or not title.strip():
                raise ValueError(f"{pid}: empty reviewed passage title")
            passage["title"] = title
            meta = passage.setdefault("metadata", {})
            for key in ("reading_blocks", "group_title", "continuation_of", "source_dateline"):
                if key in section:
                    meta[key] = deepcopy(section[key])
            points, offset = {0: 0}, 0
            for index, character in enumerate(text, 1):
                offset += utf16_length(character)
                points[offset] = index
            boundaries[pid] = points
            reading = meta.get("reading_blocks", [])
            if not isinstance(reading, list):
                raise ValueError(f"{pid}: reading blocks must be a list")
            previous = 0
            for block in reading:
                start, end = block.get("start_offset"), block.get("end_offset")
                if (block.get("kind") not in {"heading", "verse", "prose", "attribution", "note"}
                        or type(start) is not int or type(end) is not int
                        or start not in points or end not in points or not previous <= start < end
                        or text[points[previous]:points[start]].strip()):
                    raise ValueError(f"{pid}: invalid, overlapping or unanchored reading block")
                if block["kind"] == "heading" and (type(block.get("level", 2)) is not int
                                                       or not 1 <= block.get("level", 2) <= 6):
                    raise ValueError(f"{pid}: invalid reading heading level")
                previous = end
            if reading and text[points[previous]:].strip():
                raise ValueError(f"{pid}: reading blocks omit final visible text")
        entries = plan["table_of_contents"]
        if not isinstance(entries, list) or not entries:
            raise ValueError("outline contents must be a nonempty list")
        seen = {}
        expected_passages = {passage["id"]: passage for passage in expected["passages"]}
        for entry in entries:
            pid, identifier = entry["passage_id"], entry["id"]
            if (pid not in boundaries or not isinstance(identifier, str) or not identifier
                    or identifier in seen or not isinstance(entry["title"], str)
                    or not entry["title"].strip()):
                raise ValueError("invalid or duplicate original heading")
            level, start = entry["level"], entry["start_offset"]
            points = boundaries[pid]
            if type(level) is not int or not 1 <= level <= 6:
                raise ValueError("invalid original heading level")
            if type(start) is not int or start not in points or start == max(points):
                raise ValueError("original heading target is outside its passage or splits a surrogate")
            if "end_offset" in entry:
                end = entry["end_offset"]
                if type(end) is not int or end not in points or end <= start:
                    raise ValueError("original heading range is invalid or splits a surrogate")
                passage = expected_passages[pid]
                label = passage["text"][points[start]:points[end]]
                heading_text = entry.get("heading_text", entry["title"])
                if (not isinstance(heading_text, str) or not heading_text.strip()
                        or " ".join(label.split()) != " ".join(heading_text.split())):
                    raise ValueError("original internal heading label differs from its exact text range")
                if not any(block["kind"] == "heading" and block["start_offset"] == start
                           and block["end_offset"] == end
                           for block in passage.get("metadata", {}).get("reading_blocks", [])):
                    raise ValueError("original internal heading lacks its matching reading block")
            parent = entry["parent_id"]
            if parent is not None and (parent not in seen or seen[parent]["level"] >= level):
                raise ValueError("original heading parent is missing, follows its child or has an invalid level")
            seen[identifier] = entry
        expected["table_of_contents"] = deepcopy(entries)
        expected.setdefault("metadata", {})["source_outline"] = {
            "recipe_sha256": recipe_hash, "offset_unit": "utf16",
            "scope": "original_headings_numbering_hierarchy_and_insertions",
            "edition": plan.get("edition"), "evidence": plan["evidence"],
        }
        expected_events = {}
        for before, after in zip(prior["passages"], expected["passages"]):
            pid = before["id"]
            old_entries = [entry for entry in prior.get("table_of_contents", []) if entry["passage_id"] == pid]
            new_entries = [entry for entry in entries if entry["passage_id"] == pid]
            if before != after or old_entries != new_entries:
                expected_events[pid] = [{
                    "passage_id": pid, "rule": "source_outline", "count": 1,
                    "label": "Originale Überschriften, Nummerierung und Gliederung wiederhergestellt",
                    "before_excerpt": before["title"],
                    "after_excerpt": "\n".join(entry["title"] for entry in new_entries),
                    "recipe_sha256": recipe_hash, "text_unchanged": True,
                }]
        actual_events = {pid: [event for event in items if event.get("rule") == "source_outline"]
                         for pid, items in events.items()
                         if any(event.get("rule") == "source_outline" for event in items)}
        if actual_events != expected_events:
            errors.append("Source-outline ledger inventory/counts/evidence differ from the reviewed plan")
        for key in set(expected) | set(final):
            if key == "passages":
                for before, after in zip(expected[key], final[key]):
                    if before != after:
                        fields = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
                        errors.append(f"{before['id']}: final outline projection differs in {', '.join(fields)}")
            elif expected.get(key) != final.get(key):
                errors.append(f"Final outline projection differs in document {key}")
        return errors, len(expected_events)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as error:
        return [f"Source-outline verification failed: {error}"], 0


def validate(baseline: Path, stage: Path, layout_baseline: Path = LAYOUT_BASELINE,
             layout_recipe: Path = LAYOUT_RECIPE,
             outline_baseline: Path = OUTLINE_BASELINE,
             outline_recipe: Path = OUTLINE_RECIPE,
             ga014_baseline: Path = GA014_BASELINE,
             ga014_recipe: Path = GA014_RECIPE,
             sentence_baseline: Path = SENTENCE_BASELINE,
             sentence_recipe: Path = SENTENCE_RECIPE,
             ga027_recipe: Path = GA027_RECIPE,
             ga030_recipe: Path = GA030_RECIPE,
             ga030_source: Path = GA030_SOURCE,
             ga030_review: Path = GA030_REVIEW,
             ga032_recipe: Path = GA032_RECIPE,
             ga032_source: Path = GA032_SOURCE,
             ga032_review: Path = GA032_REVIEW,
             ga032_pdf: Path = GA032_PDF,
             ga038_baseline: Path = GA038_BASELINE,
             ga038_review: Path = GA038_REVIEW,
             ga038_source: Path = GA038_SOURCE,
             ga039_baseline: Path = GA039_BASELINE,
             ga039_review: Path = GA039_REVIEW,
             ga039_source: Path = GA039_SOURCE) -> dict:
    completed = stage / "proofreading/catalog.json"
    if not completed.exists():
        raise ValueError("Stage is incomplete: proofreading/catalog.json does not exist. No validation claimed.")
    catalog = read(baseline / "library/catalog.json")
    final_catalog = read(stage / "library/catalog.json")
    reports = read(completed)
    expected = catalog["works"]
    if [work["id"] for work in expected] != [work["id"] for work in final_catalog["works"]]:
        raise ValueError("Catalog work IDs or ordering changed")
    if {work["id"] for work in reports["works"]} != {work["id"] for work in expected}:
        raise ValueError("Per-GA report inventory does not match the baseline catalog")
    occurrences, work_counts, hyphenated = evidence(baseline, expected)
    problems = []
    work_results = []
    totals = Counter()
    preserved_compounds = Counter()
    calendar_result = None
    sentence_data = None
    for work in expected:
        work_id = work["id"]
        if not work.get("content_path"):
            continue
        old_file = content_file(baseline, work_id)
        new_file = content_file(stage, work_id)
        old = read(old_file)
        new = read(new_file)
        change_report = read(stage / "proofreading/works" / (work_id + ".json"))
        events = defaultdict(list)
        for event in change_report["changes"]:
            events[event["passage_id"]].append(event)
        errors = []
        historical_new = new
        restored_layout = False
        expected_final_ids = [p["id"] for p in old["passages"]]
        has_ga039_headings = (
            any(event["rule"] == "source_letter_headings" for event in change_report["changes"])
            or bool(new.get("metadata", {}).get("source_letter_heading_review")))
        if has_ga039_headings:
            try:
                if work_id != "ga-039":
                    raise ValueError("GA039 original letter-heading layer appears in another work")
                from check_ga039_headings import inspect_ga039_headings
                prior_file = content_file(ga039_baseline, work_id)
                prior = read(prior_file)
                if digest(prior_file.read_bytes()) != change_report["work"].get("ga039_heading_input_sha256"):
                    raise ValueError("GA039 heading input hash differs from retained original")
                heading_errors, heading_counts = inspect_ga039_headings(
                    prior, historical_new, read(ga039_review), events, ga039_source)
                errors.extend(heading_errors)
                totals.update(heading_counts)
                historical_new = prior
                expected_final_ids = [p["id"] for p in new["passages"]]
                restored_layout = True
            except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
                errors.append(f"Cannot independently validate GA039 original letter headings: {error}")
        has_ga038_hyphens = (
            any(event["rule"] == "source_hyphen_repair" for event in change_report["changes"])
            or bool(new.get("metadata", {}).get("source_hyphen_review"))
        )
        if has_ga038_hyphens:
            try:
                if work_id != "ga-038":
                    raise ValueError("GA 038 word-hyphen layer appears in another work")
                from check_ga038_hyphens import inspect_ga038_hyphens
                prior_file = content_file(ga038_baseline, work_id)
                prior = read(prior_file)
                if digest(prior_file.read_bytes()) != change_report["work"].get("ga038_hyphen_input_sha256"):
                    errors.append("GA 038 hyphen input hash differs from preserved pre-hyphen payload")
                hyphen_errors, hyphen_count = inspect_ga038_hyphens(
                    prior, historical_new, read(ga038_review), events, ga038_source)
                errors.extend(hyphen_errors)
                totals["ga038_source_hyphens_repaired"] += hyphen_count
                historical_new = prior
            except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
                errors.append(f"Cannot independently validate GA 038 word hyphens: {error}")
        has_sentence = any(event["rule"] in {"prose_sentence_breaks", "sentence_section_boundary"} for event in change_report["changes"])
        if has_sentence:
            try:
                from check_sentence_breaks import inspect_sentence_layer
                sentence_final = historical_new
                prior_file = content_file(sentence_baseline, work_id)
                historical_new = read(prior_file)
                if digest(prior_file.read_bytes()) != change_report["work"].get("sentence_input_sha256"):
                    errors.append("Sentence input hash differs from preserved pre-sentence payload")
                if sentence_data is None:
                    sentence_data = read(sentence_recipe)
                sentence_plan = sentence_data["works"][work_id]
                sentence_errors, sentence_counts = inspect_sentence_layer(historical_new, sentence_final, sentence_plan, events)
                errors.extend(sentence_errors)
                totals.update({"sentence_" + key: value for key, value in sentence_counts.items()})
            except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
                errors.append(f"Cannot independently validate sentence boundaries: {error}")
        has_ga014 = any(event["rule"] == "ga014_readability" for event in change_report["changes"])
        if has_ga014:
            try:
                dramatic_final = historical_new
                prior_file = content_file(ga014_baseline, work_id)
                historical_new = read(prior_file)
                if digest(prior_file.read_bytes()) != change_report["work"].get("ga014_input_sha256"):
                    errors.append("GA 014 input hash differs from preserved post-outline payload")
                dramatic_events = defaultdict(list)
                for pid, items in events.items():
                    dramatic_events[pid] = [dict(item, rule="source_layout") for item in items if item["rule"] == "ga014_readability"]
                dramatic_recipe = read(ga014_recipe)
                dramatic_errors, repairs = inspect_source_layout(historical_new, dramatic_final, dramatic_recipe, dramatic_events)
                errors.extend(dramatic_errors)
                totals["ga014_readability_passages"] += len(dramatic_recipe["passages"])
                header_count = sum(len(plan.get("omitted_parts", [])) for plan in dramatic_recipe["passages"].values())
                totals["ga014_running_headers_removed"] += header_count
                totals["ga014_source_repairs"] += repairs - header_count
                for plan in dramatic_recipe["passages"].values():
                    for repair in plan.get("edits", []):
                        key = ("ga014_verse_overruns_repaired" if repair.get("kind") == "verse_overrun"
                               else "ga014_stage_cues_repaired" if repair.get("kind") in {"stage_direction", "speaker_label", "stage_parenthesis"}
                               else "ga014_prose_word_splits_repaired" if repair.get("kind") == "prose_word_split"
                               else "ga014_punctuation_repaired")
                        totals[key] += 1
            except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
                errors.append(f"Cannot independently validate GA 014 readability: {error}")
        has_outline = (any(event["rule"] == "source_outline" for event in change_report["changes"])
                       or bool(new.get("metadata", {}).get("source_outline")))
        has_layout = any(event["rule"] == "source_layout" for event in change_report["changes"])
        if has_outline:
            try:
                outline_final = historical_new
                prior_file = content_file(outline_baseline, work_id)
                historical_new = read(prior_file)
                plan = read(outline_recipe)["works"][work_id]
                if digest(prior_file.read_bytes()) != change_report["work"].get("outline_input_sha256"):
                    errors.append("Outline input hash differs from preserved pre-outline payload")
                outline_errors, outline_passages = inspect_source_outline(historical_new, outline_final, plan, events)
                errors.extend(outline_errors)
                totals["source_outline_works"] += 1
                totals["source_outline_passages"] += outline_passages
                totals["source_outline_headings"] += len(plan["table_of_contents"])
            except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
                errors.append(f"Cannot independently validate source outline: {error}")
        if has_layout:
            try:
                prior_file = content_file(layout_baseline, work_id)
                layout_final = historical_new
                historical_new = read(prior_file)
                recipe_path = {"ga-027": ga027_recipe, "ga-030": ga030_recipe, "ga-032": ga032_recipe}.get(work_id, layout_recipe)
                if work_id in {"ga-033", "ga-034", "ga-035", "ga-036", "ga-045"}:
                    recipe_path = ROOT / "tools" / (work_id.replace("-", "") + "_structure.json")
                recipe = read(recipe_path)
                if recipe.get("work_id") != work_id:
                    raise ValueError("No edition-bound recipe for this layout work")
                layout_input = change_report["work"].get("layout_input_sha256")
                if work_id not in {"ga-027", "ga-030", "ga-032", "ga-033", "ga-034", "ga-035", "ga-036", "ga-045"} and layout_input is None:
                    layout_input = change_report["work"].get("application_base_sha256")
                if digest(prior_file.read_bytes()) != layout_input:
                    errors.append("Layout input hash differs from preserved pre-layout payload")
                if work_id == "ga-030" and "source_additions" in recipe:
                    layout_errors, repairs = inspect_ga030_layout(historical_new, layout_final, recipe, events,
                                                                 ga030_source, ga030_review)
                    restored_layout = True
                    expected_final_ids = list(recipe["passages"])
                    totals["source_restored_items"] += len(recipe["source_additions"])
                    totals["source_restored_passages"] += sum(a["kind"] == "passage" for a in recipe["source_additions"])
                elif work_id == "ga-032":
                    layout_errors, repairs = inspect_ga032_layout(historical_new, layout_final, recipe, events,
                                                                 ga032_source, ga032_review, ga032_pdf)
                elif work_id in {"ga-033", "ga-034", "ga-035", "ga-036", "ga-045"}:
                    from check_essay_layout import inspect_reviewed_essay_layout
                    layout_errors, repairs = inspect_reviewed_essay_layout(historical_new, layout_final, recipe, events,
                        ROOT / "research/proofreading-sources" / (work_id + ".epub"),
                        ROOT / "tools" / (work_id.replace("-", "") + "_layout_review.json"), inspect_source_layout)
                    if recipe.get("source_additions"):
                        restored_layout = True
                        expected_final_ids = list(recipe["passages"])
                        totals["source_restored_items"] += len(recipe["source_additions"])
                        totals["source_restored_passages"] += sum(item["kind"] == "passage" for item in recipe["source_additions"])
                    if recipe.get("annotation_additions"):
                        restored_layout = True
                        expected_final_ids = list(recipe["passages"])
                        totals["source_restored_items"] += len(recipe["annotation_additions"])
                else:
                    layout_errors, repairs = inspect_source_layout(historical_new, layout_final, recipe, events)
                errors.extend(layout_errors)
                totals["source_layout_passages"] += len(recipe["passages"])
                totals["source_layout_evidenced_repairs"] += repairs
            except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
                errors.append(f"Cannot independently validate source layout: {error}")
        if expected_final_ids != [p["id"] for p in new["passages"]]:
            errors.append("Passage IDs/order changed")
        if [p["id"] for p in old["passages"]] != [p["id"] for p in historical_new["passages"]]:
            errors.append("Preserved pre-layout passage IDs/order changed")
        old_document = {key: value for key, value in old.items() if key != "passages"}
        new_document = {key: value for key, value in historical_new.items() if key != "passages"}
        if old_document != new_document:
            errors.append("Non-passage document data changed")
        if digest(old_file.read_bytes()) != change_report["work"]["before_sha256"]:
            errors.append("Reported baseline payload hash does not match")
        if digest(new_file.read_bytes()) != change_report["work"]["after_sha256"]:
            errors.append("Reported corrected payload hash does not match")
        final_summaries = {p["id"]: p for w in final_catalog["works"] if w["id"] == work_id
                           for p in w["passages"]}
        final_passages = {p["id"]: p for p in new["passages"]}
        if restored_layout:
            catalog_work = next(w for w in final_catalog["works"] if w["id"] == work_id)
            if ([p["id"] for p in catalog_work["passages"]] != expected_final_ids
                    or catalog_work.get("catalog_passage_count") != len(expected_final_ids)
                    or catalog_work.get("content_completeness") != new.get("content_completeness")):
                errors.append("GA030 restored catalog passage inventory/count/completeness differs")
            for pid in expected_final_ids:
                p = final_passages.get(pid)
                if p is None:
                    continue
                if any(final_summaries.get(pid, {}).get(key) != p.get(key)
                       for key in ("title", "ga_page", "source_label", "checksum")):
                    errors.append(pid + ": restored catalog summary differs from final payload")
        if not restored_layout and any(event["rule"] == "source_restoration"
                                       for items in events.values() for event in items):
            errors.append("Source restoration ledger requires independently verified GA030 additions")
        changed_samples = []
        deleted_pairs = Counter()
        for index, (before, after) in enumerate(zip(old["passages"], historical_new["passages"])):
            passage_id = before["id"]
            final_after = final_passages.get(passage_id)
            if final_after is None:
                errors.append(passage_id + ": final passage is missing")
                continue
            old_metadata = {key: value for key, value in before.items() if key not in {"text", "checksum"}}
            new_metadata = {key: value for key, value in after.items() if key not in {"text", "checksum"}}
            if old_metadata != new_metadata:
                errors.append(f"{passage_id}: source_text/title/pages/annotations or other metadata changed")
            if after["checksum"] != digest(after["text"].encode()):
                errors.append(f"{passage_id}: pre-layout payload checksum mismatch")
            actual_checksum = digest(final_after["text"].encode())
            if final_after["checksum"] != actual_checksum:
                errors.append(f"{passage_id}: payload checksum mismatch")
            if final_summaries.get(passage_id, {}).get("checksum") != actual_checksum:
                errors.append(f"{passage_id}: catalog checksum mismatch")
            if (has_layout or has_outline or has_ga014 or has_sentence or has_ga038_hyphens or has_ga039_headings) and any(final_summaries.get(passage_id, {}).get(key) != final_after.get(key)
                                  for key in ("title", "ga_page")):
                errors.append(f"{passage_id}: catalog layout title/page differs from final payload")
            recorded_ocr = Counter()
            approved_for_passage = {}
            allowed_splits = set()
            for event in events[passage_id]:
                if event["rule"] in {"source_layout", "source_outline", "ga014_readability", "prose_sentence_breaks", "sentence_section_boundary", "source_restoration", "source_hyphen_repair", "source_letter_headings"}:
                    continue
                if event["rule"] == "reviewed_ocr":
                    for replacement in event.get("replacements", []):
                        original = replacement.get("original")
                        corrected = replacement.get("word")
                        if APPROVED_OCR.get(original) != corrected:
                            errors.append(f"{passage_id}: unapproved OCR substitution {original!r} → {corrected!r}")
                            continue
                        approved_for_passage[original] = corrected
                        recorded_ocr[(original, corrected)] += replacement["count"]
                    if sum(replacement.get("count", 0) for replacement in event.get("replacements", [])) != event["count"]:
                        errors.append(f"{passage_id}: OCR event count differs from replacement counts")
                else:
                    for replacement in event.get("replacements", []):
                        parts = replacement.get("split", "").split("- / ")
                        if len(parts) == 2:
                            allowed_splits.add(tuple(parts))
            ocr_edits = []
            hard, soft, error = compare_characters(before["text"], after["text"], approved_for_passage, ocr_edits, allowed_splits)
            if error:
                errors.append(f"{passage_id}: {error}")
            totals["passages"] += 1
            totals["soft_hyphens_removed"] += len(soft)
            totals["hard_hyphens_removed"] += len(hard)
            totals["reviewed_ocr_substitutions"] += len(ocr_edits)
            if Counter((edit["original"], edit["word"]) for edit in ocr_edits) != recorded_ocr:
                errors.append(f"{passage_id}: actual OCR substitutions differ from documented replacements")
            if before["text"] != final_after["text"]:
                totals["changed_passages"] += 1
            recorded_hard = Counter()
            documented_hard_count = 0
            for event in events[passage_id]:
                if event["rule"] in {"reviewed_ocr", "source_layout", "source_outline", "ga014_readability", "prose_sentence_breaks", "sentence_section_boundary", "source_restoration", "source_hyphen_repair", "source_letter_headings"}:
                    continue
                replacements = event.get("replacements", [])
                if replacements:
                    documented_hard_count += event["count"]
                    for replacement in replacements:
                        split = replacement.get("split", "")
                        parts = split.split("- / ") if "- / " in split else split.split("-")
                        if len(parts) != 2:
                            errors.append(f"{passage_id}: unparsable documented replacement {split!r}")
                            continue
                        pair = tuple(parts)
                        recorded_hard[pair] += replacement["count"]
                        token = "".join(pair).lower()
                        baseline_pair = tuple(part.lower() for part in pair)
                        if event["rule"] == "attested_dehyphenation":
                            if work_counts[token] < 2 or occurrences[token] < max(10, 20 * hyphenated[baseline_pair]):
                                errors.append(f"{passage_id}: inferred merge fails independent corpus evidence: {pair}")
                        elif baseline_pair not in REVIEWED:
                            errors.append(f"{passage_id}: undocumented allowlist merge: {pair}")
            actual_hard = Counter((edit["left"], edit["right"]) for edit in hard)
            if actual_hard != recorded_hard or len(hard) != documented_hard_count:
                errors.append(f"{passage_id}: deleted hyphen pairs/counts differ from documented replacements")
            soft_count = sum(event["count"] for event in events[passage_id] if event["rule"] == "soft_hyphen")
            if len(soft) != soft_count:
                errors.append(f"{passage_id}: removed soft-hyphen count differs from documented event")
            for edit in hard:
                left, right = edit["left"], edit["right"]
                deleted_pairs[(left, right)] += 1
                if right.lower() in CONNECTORS or left.lower() in PREFIXES or (right[0].isupper() and (left.lower(), right.lower()) not in REVIEWED):
                    errors.append(f"{passage_id}: meaningful compound/hanging compound merged: {left}-{right}")
                if "\n" not in edit["gap"] and (left.lower(), right.lower()) not in REVIEWED:
                    errors.append(f"{passage_id}: inferred hard merge lacked an original linebreak: {left}-{right}")
            for expression in (r"geistig-[ \t\n]*seelisch", r"Christus-[ \t\n]*Impuls",
                               r"Ich-[ \t\n]*Organisation", r"\bDenk-[ \t\n]*und\b"):
                before_count = len(re.findall(expression, before["text"].replace("\u00ad", ""), re.I))
                after_count = len(re.findall(expression, after["text"].replace("\u00ad", ""), re.I))
                preserved_compounds[expression] += after_count
                if after_count < before_count:
                    errors.append(f"{passage_id}: protected compound counts changed for {expression}")
            passage_edits = sorted(hard + soft + ocr_edits, key=lambda edit: edit["before_offset"])
            for edit_index in sorted({0, len(passage_edits) // 2, len(passage_edits) - 1}) if passage_edits else []:
                edit = passage_edits[edit_index]
                changed_samples.append({"passage_id": passage_id, "passage_index": index,
                                        **sample(before["text"], after["text"], edit)})
        if work_id == "ga-040":
            calendar_passage = next(p for p in historical_new["passages"] if p["id"] == "ga-040-doc-heading-2")
            boundaries = calendar_passage["text"].split("\n\nFRÜHLING\n\n")
            if len(boundaries) != 2:
                errors.append("Reviewed calendar boundary missing or duplicated")
            else:
                poems = [block for block in boundaries[1].split("\n\n")
                         if re.match(r"^(?:5 2|[1-9]\d?) (?=[A-ZÄÖÜ])", block)]
                numbers = [re.match(r"^(5 2|[1-9]\d?) ", poem)[1].replace(" ", "") for poem in poems]
                if numbers != [str(number) for number in range(1, 53)]:
                    errors.append("Calendar stanza numbers/order differ from all 52 reviewed weeks")
                if any(not 5 <= len(poem.splitlines()) <= 8 for poem in poems):
                    errors.append("Calendar has a split/incomplete or merged stanza")
                calendar_result = {"stanzas": len(poems), "numbers_in_order": numbers == [str(number) for number in range(1, 53)],
                                   "line_counts": [len(poem.splitlines()) for poem in poems],
                                   "samples": [poems[index] for index in (0, 25, 51) if index < len(poems)],
                                   "source_layout_checked": has_layout}
        if errors:
            problems.extend({"work_id": work_id, "error": error} for error in errors)
        selected = []
        if changed_samples:
            for index in sorted({0, len(changed_samples) // 2, len(changed_samples) - 1}):
                selected.append(changed_samples[index])
        passage_samples = []
        if work_id in TARGETS:
            for index in sorted({0, len(new["passages"]) // 2, len(new["passages"]) - 1}):
                passage = new["passages"][index]
                passage_samples.append({"position": "beginning" if index == 0 else "end" if index == len(new["passages"]) - 1 else "middle",
                                        "passage_id": passage["id"], "title": passage["title"],
                                        "excerpt": passage["text"][:650]})
        work_results.append({"work_id": work_id, "title": new["title"],
                             "passages": len(new["passages"]), "status": "passed" if not errors else "failed",
                             "hard_hyphens_removed": sum(deleted_pairs.values()),
                             "hard_hyphen_pairs": [{"split": left + "- / " + right, "count": count}
                                                   for (left, right), count in sorted(deleted_pairs.items())],
                             "changed_samples": selected, "passage_samples": passage_samples})
    totals["works"] = len(work_results)
    totals["works_with_changed_splits"] = sum(bool(work["changed_samples"]) for work in work_results)
    return {"status": "passed" if not problems else "failed", "baseline": str(baseline), "stage": str(stage),
            "generated_at": reports["generated_at"], "summary": dict(totals),
            "problems": problems, "protected_compounds": dict(preserved_compounds),
            "ga040_calendar": calendar_result, "works": work_results}


def markdown(report: dict) -> str:
    lines = ["# Independent sample validation", "", f"Stage: `{report['stage']}`", "",
             f"Result: **{report['status'].upper()}**. {report['summary']['works']} available GAs and "
             f"{report['summary']['passages']} passages compared with the preserved baseline.", "",
             f"Verified {report['summary']['soft_hyphens_removed']:,} soft-hyphen removals, "
             f"{report['summary']['hard_hyphens_removed']:,} documented hard-hyphen joins, and "
             f"{report['summary']['reviewed_ocr_substitutions']:,} approved OCR substitutions. "
             f"{report['summary']['changed_passages']:,} passages changed. "
             + ("No unexpected changes were found." if report["status"] == "passed" else "Issues are listed below."), "",
             "The validator compares actual staged characters and metadata independently; it does not rerun the correction functions. "
             "It checks original source text, passage identity/order, pages, annotations, other payload fields, checksums, report counts, "
             "lexical evidence, and protected compounds. Only whitespace, explicitly documented hyphen deletions, and six source-approved "
             "case-sensitive full-token OCR maps are accepted for historical repairs: fiir→für, dafi→daß, grofien→großen, "
             "erfiillt→erfüllt, iiber→über, miissen→müssen. Source layout uses a separately preserved pre-layout baseline, "
             "exact edition-bound recipe slices and frozen input/output hashes. Its full spelling ledger, paragraph classification, "
             "TOC hierarchy, source-page anchors and footnote definitions/references must match the independent projection exactly.", ""]
    if report["problems"]:
        lines.extend(["## Issues", ""])
        lines.extend(f"- {item['work_id']}: {item['error']}" for item in report["problems"])
        lines.append("")
    if report["summary"].get("source_layout_passages"):
        lines.extend([f"Source layout: {report['summary']['source_layout_passages']} passages checked against exact recipes; "
                      f"{report['summary']['source_layout_evidenced_repairs']} explicitly evidenced replacements/footer removals "
                      "also checked against their per-passage ledgers.", ""])
    if report["summary"].get("source_outline_works"):
        lines.extend([f"Original outlines: {report['summary']['source_outline_works']} works, "
                      f"{report['summary']['source_outline_headings']} anchored headings and "
                      f"{report['summary']['source_outline_passages']} changed passage outlines checked against "
                      "their retained editions, frozen text hashes and exact metadata recipes. "
                      "Text, source text, IDs, checksums, pages and annotations must remain unchanged.", ""])
    if report.get("ga040_calendar"):
        calendar = report["ga040_calendar"]
        lines.extend([f"GA 40 calendar: {calendar['stanzas']} contiguous weekly stanzas; numbers 1–52 remain in order. "
                      "Each stanza has 5–8 physical verse lines. Poems 1, 26 and 52 were inspected. "
                      + ("The final numbered headings and approved `5 2` → `52` spacing repair also passed the source-layout projection."
                         if calendar.get("source_layout_checked") else "The source numeral `5 2` is retained."), ""])
    lines.extend(["## Representative samples", "",
                  "Beginning/middle/end passages are included for writings, poetry/drama, lectures, high soft-hyphen volumes, recovered EPUBs, "
                  "and the five core editions. Changed-word samples below give exact original/corrected contexts. "
                  "Automated preservation and these samples do not replace a complete manual source collation.", ""])
    sampled_changes = sum(work["work_id"] in TARGETS and bool(work["changed_samples"]) for work in report["works"])
    lines.extend([f"Changed-word contexts cover {sampled_changes} requested representative GAs. "
                  "GAs without a word correction still have beginning/middle/end passage and preservation checks.", ""])
    for work in report["works"]:
        if work["work_id"] not in TARGETS:
            continue
        lines.extend([f"### {work['work_id']} — {work['title']}", "",
                      f"{work['status']}; {work['passages']} passages; {work['hard_hyphens_removed']} hard-hyphen joins.", ""])
        for selected in work["passage_samples"]:
            lines.extend([f"- {selected['position']}: `{selected['passage_id']}` — {selected['title']}"])
        lines.append("")
        for selected in work["changed_samples"]:
            lines.extend([f"`{selected['passage_id']}` ({selected['kind']})", "", "Before:", "", "```text",
                          selected["before"], "```", "", "After:", "", "```text", selected["after"], "```", ""])
        if not work["changed_samples"]:
            lines.extend(["No word-split correction occurred in this GA; beginning/middle/end payload samples and preservation checks were included.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "research/proofreading-baseline")
    parser.add_argument("--stage", type=Path, default=Path("/tmp/ga-proofreading-complete"))
    parser.add_argument("--layout-baseline", type=Path, default=LAYOUT_BASELINE)
    parser.add_argument("--layout-recipe", type=Path, default=LAYOUT_RECIPE)
    parser.add_argument("--outline-baseline", type=Path, default=OUTLINE_BASELINE)
    parser.add_argument("--outline-recipe", type=Path, default=OUTLINE_RECIPE)
    parser.add_argument("--ga014-baseline", type=Path, default=GA014_BASELINE)
    parser.add_argument("--ga014-recipe", type=Path, default=GA014_RECIPE)
    parser.add_argument("--ga027-recipe", type=Path, default=GA027_RECIPE)
    parser.add_argument("--ga030-recipe", type=Path, default=GA030_RECIPE)
    parser.add_argument("--ga030-source", type=Path, default=GA030_SOURCE)
    parser.add_argument("--ga030-review", type=Path, default=GA030_REVIEW)
    parser.add_argument("--ga032-recipe", type=Path, default=GA032_RECIPE)
    parser.add_argument("--ga032-source", type=Path, default=GA032_SOURCE)
    parser.add_argument("--ga032-review", type=Path, default=GA032_REVIEW)
    parser.add_argument("--ga032-pdf", type=Path, default=GA032_PDF)
    parser.add_argument("--ga038-baseline", type=Path, default=GA038_BASELINE)
    parser.add_argument("--ga038-review", type=Path, default=GA038_REVIEW)
    parser.add_argument("--ga038-source", type=Path, default=GA038_SOURCE)
    parser.add_argument("--sentence-baseline", type=Path, default=SENTENCE_BASELINE)
    parser.add_argument("--sentence-recipe", type=Path, default=SENTENCE_RECIPE)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()
    try:
        report = validate(args.baseline, args.stage, args.layout_baseline, args.layout_recipe,
                          args.outline_baseline, args.outline_recipe, args.ga014_baseline, args.ga014_recipe,
                          args.sentence_baseline, args.sentence_recipe, args.ga027_recipe, args.ga030_recipe,
                          args.ga030_source, args.ga030_review, args.ga032_recipe, args.ga032_source, args.ga032_review,
                          args.ga032_pdf, args.ga038_baseline, args.ga038_review, args.ga038_source)
    except (ValueError, FileNotFoundError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
    if args.json_output:
        args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "summary", "problems")}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
