#!/usr/bin/env python3
"""Freeze GA032 layout from the reviewed original DOC/EPUB/PDF witnesses.

Every paragraph, heading and verse boundary is an explicit source observation.
Rebuilding consumes the exact retained reading input; it never guesses from a
short line, a sentence ending or the length of a paragraph.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from finalize_library import read_json
from repair_source_structure import apply_passage_plan, recipe_digest, sha

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research/proofreading-sources/ga-032.epub"
SOURCE_PDF = ROOT / "research/proofreading-sources/ga-032-original.pdf"
BASELINE = ROOT / "research/proofreading-layout-baseline/content/ga-032.json.gz"
REVIEW = ROOT / "tools/ga032_layout_review.json"
RECIPE = ROOT / "tools/ga032_structure.json"


def source_element(archive, witness):
    cache = getattr(archive, "_ga032_body_cache", None)
    if cache is None:
        cache = archive._ga032_body_cache = {}
    member = witness["source_member"]
    if member not in cache:
        cache[member] = ET.fromstring(archive.read(member)).find("{*}body")
    body = cache[member]
    element = body[witness["body_index"]]
    if "child_index" in witness:
        element = element[witness["child_index"]]
    for index in witness.get("child_path", []):
        element = element[index]
    return element


def check_pdf_fragment(pdf, review, repair):
    """Verify the exact reviewed bitmap when the PDF's OCR omitted a word."""
    if (hashlib.sha256(pdf.read_bytes()).hexdigest() != review["original_pdf_sha256"]
            or repair["original_pdf_sha256"] != review["original_pdf_sha256"]):
        raise ValueError("GA032 original PDF fragment witness changed")
    if (repair["old"] != "(Berlin 1899) ent-" or repair["new"] != "(Berlin 1899) enthalten:"
            or repair["source_token"] != "halten:" or repair["source_pdf_page"] != 451):
        raise ValueError("GA032 PDF fragment restoration exceeds its exact reviewed continuation")
    from pypdf import PdfReader
    witness = repair["pdf_raster_witness"]
    if (witness["pdf_page"] != 451 or witness["page_index"] != 450
            or witness["source_token"] != "halten:" or not witness["extracted_text_layer_omits_fragment"]
            or witness["visually_verified_text"][-1] != "halten:"):
        raise ValueError("GA032 PDF fragment lacks its exact visible page/token selector")
    page = PdfReader(pdf).pages[witness["page_index"]]
    raster = page["/Resources"]["/XObject"][witness["xobject_name"]].get_object()
    if (raster["/Width"] != witness["width"] or raster["/Height"] != witness["height"]
            or hashlib.sha256(raster.get_data()).hexdigest() != witness["decoded_stream_sha256"]
            or len(page.images) != 1):
        raise ValueError("GA032 exact original PDF image changed")
    image = page.images[0].image
    box = witness["crop_box_pixels"]
    if (len(box) != 4 or any(type(value) is not int for value in box)
            or not 0 <= box[0] < box[2] <= image.width or not 0 <= box[1] < box[3] <= image.height):
        raise ValueError("GA032 invalid reviewed PDF raster crop")
    crop = image.crop(box)
    if crop.mode != witness["crop_mode"] or hashlib.sha256(crop.tobytes()).hexdigest() != witness["crop_pixels_sha256"]:
        raise ValueError("GA032 exact visible source fragment crop changed")


def check_source(source, review, pdf=SOURCE_PDF):
    if hashlib.sha256(source.read_bytes()).hexdigest() != review["source_epub_sha256"]:
        raise ValueError("GA032 reviewed EPUB changed")
    with ZipFile(source) as archive:
        for member, checksum in review["source_members"].items():
            if hashlib.sha256(archive.read(member)).hexdigest() != checksum:
                raise ValueError("GA032 reviewed source member changed: " + member)
        witnesses = list(review.get("metadata_repairs", [])) + list(review.get("annotation_repairs", []))
        witnesses.extend(origin for repair in review.get("metadata_repairs", [])
                         for origin in repair.get("source_witnesses", []))
        for passage in review["passages"].values():
            witnesses.extend(passage["starts"])
            witnesses.extend(passage.get("omissions", []))
            witnesses.extend(repair for repair in passage.get("edits", []) if repair.get("source_member"))
            source_parts = passage.get("source_parts", [])
            if not source_parts:
                raise ValueError("GA032 retained source lacks a complete paragraph reconstruction")
            raw_parts = []
            for witness in source_parts:
                raw = "".join(source_element(archive, witness).itertext())
                if sha(raw) != witness["source_paragraph_sha256"]:
                    raise ValueError("GA032 exact retained source paragraph changed")
                raw_parts.append(raw)
            if sha("\n\n".join(raw_parts)) != passage["source_text_sha256"]:
                raise ValueError("GA032 retained original source reconstruction differs")
            for span in passage.get("source_segments", []):
                data = archive.read(span["source_member"])
                if hashlib.sha256(data).hexdigest() != span["member_sha256"]:
                    raise ValueError("GA032 exact source segment member changed")
                body = ET.fromstring(data).find("{*}body")
                for index, checksum in span.get("body_sha256", {}).items():
                    if sha("".join(body[int(index)].itertext())) != checksum:
                        raise ValueError("GA032 exact retained source paragraph changed")
        for witness in witnesses:
            if not witness.get("source_member") or not witness.get("source_paragraph_sha256"):
                raise ValueError("GA032 boundary lacks an exact original paragraph witness")
            if sha("".join(source_element(archive, witness).itertext())) != witness["source_paragraph_sha256"]:
                raise ValueError("GA032 exact paragraph witness changed")
        for repair in review.get("annotation_repairs", []):
            raw = "".join(source_element(archive, repair).itertext())
            if raw.strip() != repair["before"] or annotation_reading_text(repair["before"]) != repair["after"]:
                raise ValueError("GA032 annotation repair differs from its exact physical source wraps")
        for passage in review["passages"].values():
            for repair in passage.get("edits", []):
                if repair.get("source_witnesses"):
                    raw_parts = []
                    for witness in repair["source_witnesses"]:
                        raw = "".join(source_element(archive, witness).itertext())
                        if sha(raw) != witness["source_paragraph_sha256"]:
                            raise ValueError("GA032 exact physical seam witness changed")
                        raw_parts.append(raw)
                    if " ".join(repair["old"].split()) not in " ".join("\n\n".join(raw_parts).split()):
                        raise ValueError("GA032 physical seam token has no exact source context")
                if repair.get("kind") == "physical_word_seam":
                    old, new = [re.sub(r"\s", "", repair[field]) for field in ("old", "new")]
                    if new != old and not any(new == old[:index] + old[index + 1:]
                                               for index, char in enumerate(old) if char == "-"):
                        raise ValueError("GA032 physical seam changes original source characters")
                if repair.get("kind") == "poetic_overrun":
                    old, new = [Counter(re.sub(r"\s", "", repair[field])) for field in ("old", "new")]
                    if not repair.get("source_witnesses") or new - old or not set(old - new) <= {"[", "-"}:
                        raise ValueError("GA032 poetic continuation changes original source characters")
                if repair.get("kind") != "literal_year_restoration":
                    if repair.get("kind") == "pdf_fragment_restoration":
                        check_pdf_fragment(pdf, review, repair)
                    continue
                token = repair.get("source_token", "")
                if not re.fullmatch(r"\[18\d\d\]|\[190[012]\]", token):
                    raise ValueError("GA032 literal restoration requires an exact source year")
                raw = "".join(source_element(archive, repair).itertext())
                year = token[1:-1]
                if token not in raw or repair["new"].count(year) != repair["old"].count(year) + 1:
                    raise ValueError("GA032 restored year has no exact original literal witness")
                positions = [match.start() for match in re.finditer(re.escape(year), repair["new"])]
                if not any(" ".join((repair["new"][:position] + repair["new"][position + len(year):]).split())
                           == " ".join(repair["old"].split()) for position in positions):
                    raise ValueError("GA032 literal repair changes more than its single original year")


def parts_between(text, begin, end):
    parts, offset = [], 0
    for index, block in enumerate(text.split("\n\n")):
        left, right = max(begin, offset), min(end, offset + len(block))
        if left < right and text[left:right].strip():
            parts.append({"block": index, "start": left - offset, "end": right - offset})
        offset += len(block) + 2
    if not parts:
        raise ValueError("Empty GA032 reviewed source span")
    return parts


def apply_metadata_repairs(payload, repairs, *, repeated=False):
    passages = {p["id"]: p for p in payload["passages"]}
    for repair in repairs:
        passage = passages[repair["passage_id"]]
        before, after = repair["before"], repair["after"]
        if (set(before) != set(after) or not set(before) <= {"title", "ga_page", "page_numbers"}
                or not before or not repair.get("evidence")):
            raise ValueError("GA032 metadata repair lacks an exact reviewed contract")
        for field in before:
            actual = passage["metadata"].get(field) if field == "page_numbers" else passage.get(field)
            if actual != (after if repeated else before)[field]:
                raise ValueError("GA032 original/rendered metadata drift: " + passage["id"] + " " + field)
            if not repeated:
                if field == "page_numbers":
                    passage["metadata"][field] = deepcopy(after[field])
                else:
                    passage[field] = deepcopy(after[field])


def annotation_reading_text(text):
    if "\n\n" in text:
        raise ValueError("GA032 annotation paragraph breaks require separate review")
    return re.sub(r"\s*\n\s*", " ", text)


def apply_annotation_repairs(payload, repairs, *, repeated=False):
    passages = {p["id"]: p for p in payload["passages"]}
    seen = set()
    for repair in repairs:
        key = (repair["passage_id"], repair["annotation_id"])
        if key in seen or not repair.get("evidence") or annotation_reading_text(repair["before"]) != repair["after"]:
            raise ValueError("GA032 annotation repair lacks an exact whitespace contract")
        seen.add(key)
        matching = [note for note in passages[repair["passage_id"]]["metadata"]["annotations"]
                    if note["id"] == repair["annotation_id"]]
        if (len(matching) != 1 or matching[0]["marker"] != repair["marker"]
                or matching[0]["text"] != repair["after" if repeated else "before"]):
            raise ValueError("GA032 original/rendered annotation drift: " + repair["annotation_id"])
        if not repeated:
            matching[0]["text"] = repair["after"]


def build(payload, source=SOURCE, review=None, pdf=SOURCE_PDF):
    review = review or read_json(REVIEW)
    check_source(source, review, pdf)
    if (payload["work_id"] != "ga-032" or any(payload.get(k) != review[k] for k in ("source_sha256", "source_epub_sha256"))
            or [p["id"] for p in payload["passages"]] != list(review["passages"])):
        raise ValueError("GA032 reviewed source/passage inventory changed")
    recipe = {"schema_version": 1, "work_id": "ga-032", "offset_unit": "utf16",
              "source_sha256": payload["source_sha256"], "source_epub_sha256": payload["source_epub_sha256"],
              "source_url": payload["source_url"], "metadata_repairs": deepcopy(review.get("metadata_repairs", [])),
              "annotation_repairs": deepcopy(review.get("annotation_repairs", [])),
              "source_evidence": {"review_sha256": recipe_digest(review), "method": review["method"],
                                  "source_members": deepcopy(review["source_members"])},
              "known_gaps": deepcopy(review.get("known_gaps", [])),
              "review_flags": deepcopy(review.get("review_flags", [])), "passages": {}}
    for key in ("original_doc_sha256", "original_pdf_sha256", "source_layout_sha256"):
        if key in review:
            recipe["source_evidence"][key] = review[key]
    repaired = deepcopy(payload)
    apply_metadata_repairs(repaired, recipe["metadata_repairs"])
    apply_annotation_repairs(repaired, recipe["annotation_repairs"])
    targets = {}
    for original, passage in zip(payload["passages"], repaired["passages"]):
        pid, text = passage["id"], passage["text"]
        witness = review["passages"][pid]
        if (sha(text) != witness["input_sha256"] or sha(passage["source_text"]) != witness["source_text_sha256"]
                or original["title"] != witness["title"]):
            raise ValueError("GA032 original reading/source/title drift: " + pid)
        starts = witness["starts"]
        if (not starts or starts[0]["start_codepoint"] != 0
                or sorted({s["start_codepoint"] for s in starts}) != [s["start_codepoint"] for s in starts]):
            raise ValueError("GA032 reviewed boundaries are ambiguous: " + pid)
        plan = {"input_sha256": sha(text), "source_text_sha256": sha(passage["source_text"]),
                "group_title": witness.get("group_title", passage["title"]), "segments": [],
                "edits": deepcopy(witness.get("edits", [])),
                "annotations_input_sha256": recipe_digest(original["metadata"]["annotations"]),
                "annotations_output_sha256": recipe_digest(passage["metadata"]["annotations"])}
        if witness.get("page_marker_source"):
            plan["page_marker_source"] = witness["page_marker_source"]
        if witness.get("omissions"):
            plan["omitted_parts"] = []
            for omitted in witness["omissions"]:
                slices = parts_between(text, omitted["start_codepoint"], omitted["end_codepoint"])
                if len(slices) != 1:
                    raise ValueError("GA032 exact page furniture must occupy one slice")
                plan["omitted_parts"].append(slices[0] | {k: deepcopy(v) for k, v in omitted.items()
                    if k not in {"start_codepoint", "end_codepoint"}})
        for index, start in enumerate(starts):
            begin = start["start_codepoint"]
            end = starts[index + 1]["start_codepoint"] if index + 1 < len(starts) else len(text)
            if not 0 <= begin < end <= len(text) or not text[begin:].startswith(start["canonical_anchor"]):
                raise ValueError("GA032 exact canonical boundary changed: " + pid)
            spans = [(begin, end)]
            line_starts = start.get("line_starts", [])
            if line_starts:
                if (start["kind"] not in {"verse", "note"}
                        or sorted(set(line_starts)) != line_starts
                        or any(type(position) is not int or not begin < position < end for position in line_starts)):
                    raise ValueError("GA032 preserved line boundaries require exact ordered verse/list positions")
                points = [begin] + line_starts + [end]
                spans = list(zip(points, points[1:]))
            for omitted in witness.get("omissions", []):
                left, right = omitted["start_codepoint"], omitted["end_codepoint"]
                spans = [piece for l, r in spans for piece in
                         ([(l, r)] if right <= l or left >= r else [(l, min(r, left)), (max(l, right), r)])
                         if piece[0] < piece[1]]
            parts = [part for left, right in spans if text[left:right].strip()
                     for part in parts_between(text, left, right)]
            segment = {"kind": start["kind"], "parts": parts,
                       "join": start.get("join", "\n" if start["kind"] == "verse" else " "),
                       "evidence": start["evidence"],
                       "source_pdf_pages": deepcopy(start.get("source_pdf_pages", [start["page"]] if start.get("page") else []))}
            if start["kind"] == "heading":
                segment["level"] = start.get("level", 2)
            for field in ("preserve_lines", "poem_start", "separator", "page_evidence"):
                if field in start:
                    segment[field] = deepcopy(start[field])
            if start.get("page_anchor"):
                segment["pages"] = [start["page_anchor"]]
            plan["segments"].append(segment)
        preview = deepcopy(passage)
        preview["metadata"].pop("annotations", None)
        apply_passage_plan(preview, plan, "preview")
        section_starts = [index for index, start in enumerate(starts) if start.get("section_start")]
        if section_starts:
            if section_starts[0] != 0:
                raise ValueError("GA032 article sections must cover the retained passage from its beginning")
            plan["sections"] = []
            for number, index in enumerate(section_starts):
                end = section_starts[number + 1] if number + 1 < len(section_starts) else len(starts)
                block = preview["metadata"]["reading_blocks"][index]
                heading = preview["text"].encode("utf-16-le")[block["start_offset"] * 2:block["end_offset"] * 2].decode("utf-16-le").split("\n", 1)[0]
                title = passage["title"] if not number else heading
                if number and block["kind"] != "heading":
                    raise ValueError("GA032 independent article requires its original heading")
                plan["sections"].append({"start_segment": index, "end_segment": end, "title": title,
                                         "label_kind": "source_title", "evidence": starts[index]["evidence"]})
        plan["output_sha256"] = sha(preview["text"])
        plan["output_metadata"] = {"title": preview["title"], "ga_page": preview["ga_page"],
                                   "page_numbers": deepcopy(preview["metadata"]["page_numbers"])}
        recipe["passages"][pid] = plan
        for index, start in enumerate(starts):
            if start.get("toc_target"):
                targets[start["toc_target"]] = (pid, preview["metadata"]["reading_blocks"][index]["start_offset"])
    if "table_of_contents" in review:
        recipe["table_of_contents"] = []
        for row in review["table_of_contents"]:
            pid, offset = targets[row["target"]]
            recipe["table_of_contents"].append({k: deepcopy(v) for k, v in row.items() if k != "target"}
                                                | {"passage_id": pid, "start_offset": offset})
    from repair_ga032_readability import apply_layout
    apply_layout(payload, recipe)
    return recipe


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=BASELINE)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--pdf", type=Path, default=SOURCE_PDF)
    parser.add_argument("--review", type=Path, default=REVIEW)
    parser.add_argument("--output", type=Path, default=RECIPE)
    args = parser.parse_args()
    result = build(read_json(args.input), args.source, read_json(args.review), args.pdf)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"GA032: {len(result['passages'])} passages; {sum(len(p['segments']) for p in result['passages'].values())} reviewed blocks")
