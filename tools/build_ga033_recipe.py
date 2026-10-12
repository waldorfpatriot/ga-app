#!/usr/bin/env python3
"""Build GA033's reviewed contents, paragraphs and the omitted author subsection.

Every boundary is a frozen original-source observation. No punctuation, sentence
length or paragraph-length rule classifies the reading text.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from functools import lru_cache
import logging
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from build_ga032_recipe import (source_element, parts_between, apply_metadata_repairs,
    apply_annotation_repairs, annotation_reading_text)
from finalize_library import read_json
from repair_source_structure import apply_passage_plan, recipe_digest, sha

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research/proofreading-sources/ga-033.epub"
SOURCE_PDF = ROOT / "research/proofreading-sources/ga-033-original.pdf"
BASELINE = ROOT / "research/proofreading-layout-baseline/content/ga-033.json.gz"
REVIEW = ROOT / "tools/ga033_layout_review.json"
RECIPE = ROOT / "tools/ga033_structure.json"
ADDED_ID = "ga-033-schopenhauer-bibliographisches"


@lru_cache(maxsize=2)
def original_reader(path, checksum):
    from pypdf import PdfReader
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    return PdfReader(path)


@lru_cache(maxsize=96)
def original_raster(path, checksum, number):
    """Check native scan pixels; the independent checker uses Poppler instead."""
    item = original_reader(path, checksum).pages[number - 1].images[0]
    image = item.image
    raw = image.tobytes()
    visible = bytearray(raw)
    width, height = image.size
    if image.mode == "1" and width % 8:
        stride = (width + 7) // 8
        mask = (255 << (8 - width % 8)) & 255
        for row in range(height):
            visible[(row + 1) * stride - 1] &= mask
    return {"xobject_name": item.name, "original_page_size": [width, height],
            "original_page_mode": image.mode,
            "original_page_pixels_sha256": hashlib.sha256(raw).hexdigest(),
            "visible_page_pixels_sha256": hashlib.sha256(visible).hexdigest()}


def check_rasters(pdf, review, repair):
    for witness in repair.get("pdf_raster_witnesses", []):
        page = witness.get("pdf_page")
        if (type(page) is not int or page < 1 or witness.get("page_index") != page - 1
                or witness.get("original_pdf_sha256") != review["original_pdf_sha256"]
                or witness.get("original_page_mode") != "1"):
            raise ValueError("GA033 printed repair has an invalid exact raster contract")
        actual = original_raster(str(pdf), review["original_pdf_sha256"], page)
        if any(witness.get(key) != value for key, value in actual.items()):
            raise ValueError("GA033 original printed repair pixels differ")


def source_reading_text(element):
    marker = "\uE000"
    def collect(node):
        parts = [node.text or ""]
        for child in node:
            if child.get("role") != "doc-backlink":
                parts.append(marker if child.tag.rsplit("}", 1)[-1] == "br" else collect(child))
            parts.append(child.tail or "")
        return "".join(parts)
    text = re.sub(r"[ \t\r\n\f]+", " ", collect(element))
    return re.sub(" *" + marker + " *", "\n", text).strip()


def check_source(source, review, pdf=SOURCE_PDF):
    if hashlib.sha256(source.read_bytes()).hexdigest() != review["source_epub_sha256"]:
        raise ValueError("GA033 reviewed EPUB changed")
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != review["original_pdf_sha256"]:
        raise ValueError("GA033 original printed source changed")
    for kind in ("original_doc", "source_layout"):
        path = Path(review[kind + "_path"])
        if not path.is_absolute():
            path = ROOT / path
        if hashlib.sha256(path.read_bytes()).hexdigest() != review[kind + "_sha256"]:
            raise ValueError("GA033 original document/layout witness changed")
    with ZipFile(source) as archive:
        for member, checksum in review["source_members"].items():
            if hashlib.sha256(archive.read(member)).hexdigest() != checksum:
                raise ValueError("GA033 reviewed member changed: " + member)
        for passage in review["passages"].values():
            atoms = []
            witnesses = list(passage["source_parts"]) + list(passage["starts"])
            for repair in passage.get("edits", []):
                witnesses.extend(repair.get("source_witnesses", []))
            for witness in witnesses:
                if sha("".join(source_element(archive, witness).itertext())) != witness["source_paragraph_sha256"]:
                    raise ValueError("GA033 exact original paragraph changed")
            for witness in passage["source_parts"]:
                atoms.append("".join(source_element(archive, witness).itertext()))
            if sha("\n\n".join(atoms)) != passage["source_text_sha256"]:
                raise ValueError("GA033 complete raw source reconstruction differs")
        for repair in review.get("metadata_repairs", []) + review.get("annotation_repairs", []):
            check_rasters(pdf, review, repair)
            for witness in repair.get("source_witnesses", []) or [repair]:
                if sha("".join(source_element(archive, witness).itertext())) != witness["source_paragraph_sha256"]:
                    raise ValueError("GA033 original metadata/annotation witness changed")
        additions = review["source_additions"]
        if len(additions) != 1:
            raise ValueError("GA033 only the single omitted author subsection may be restored")
        addition = additions[0]
        member = "EPUB/chapter-0008.xhtml"
        if (addition["kind"] != "passage" or addition["id"] != ADDED_ID or addition["passage_id"] != ADDED_ID
                or addition["source_role"] != "author" or addition["source_pdf_pages"] != [265, 266, 267, 268]
                or addition["insert_before_passage_id"] != "ga-033-doc-heading-17"
                or addition["source_segments"] != [{"source_member": member, "body_indices": list(range(19, 25)),
                    "member_sha256": review["source_members"][member]}]):
            raise ValueError("GA033 restoration exceeds its exact original source span")
        body = ET.fromstring(archive.read(member)).find("{*}body")
        raw = "\n\n".join("".join(body[index].itertext()) for index in range(19, 25))
        text = "\n\n".join(source_reading_text(body[index]) for index in range(19, 25))
        if (raw != addition["source_text"] or text != addition["text"]
                or sha(raw) != addition["source_text_sha256"] or sha(text) != addition["text_sha256"]):
            raise ValueError("GA033 exact original addition changed")
        for pid, passage in review["passages"].items():
            for repair in passage.get("edits", []):
                check_rasters(pdf, review, repair)
                if repair["kind"] == "physical_word_seam":
                    old, new = [re.sub(r"\s", "", repair[field]) for field in ("old", "new")]
                    if (not repair.get("match_word_boundaries") or new != old
                            and not any(new == old[:i] + old[i + 1:] for i, c in enumerate(old) if c == "-")):
                        raise ValueError("GA033 physical word seam changes original letters")
                elif repair["kind"] == "source_contents_restoration":
                    rows = repair.get("original_contents_rows", [])
                    printed = ("BIOGRAPHISCHE SKIZZEN" if passage["title"] == "BIOGRAPHISCHE SKIZZEN"
                               else "VIER BIOGRAPHIEN") + "\n\n" + "\n".join(row["display_text"] for row in rows)
                    if (pid not in {"ga-033-doc-heading-1", "ga-033-doc-heading-2"}
                            or passage.get("source_role") != "table_of_contents" or not rows
                            or repair["new"] != passage["restored_contents_text"] or repair["new"] != printed
                            or any(row not in review["original_contents_rows"] for row in rows)):
                        raise ValueError("GA033 contents restoration exceeds its frozen original rows")
                elif repair["kind"] == "source_heading_restoration":
                    matches = [s for s in passage["starts"] if s["kind"] == "heading"
                               and s["start_codepoint"] == repair["heading_start_codepoint"]]
                    if len(matches) != 1 or not matches[0]["canonical_anchor"].startswith(repair["old"]):
                        raise ValueError("GA033 heading restoration exceeds its exact source boundary")
                else:
                    raise ValueError("GA033 unknown reading repair")


def augment_original(payload, recipe):
    original = recipe["original_passages"]
    if [p["id"] for p in payload["passages"]] != list(original):
        raise ValueError("GA033 restoration requires the exact original 15 containers")
    work = deepcopy(payload)
    for p in work["passages"]:
        witness = original[p["id"]]
        if sha(p["text"]) != witness["input_sha256"] or sha(p["source_text"]) != witness["source_text_sha256"]:
            raise ValueError("GA033 retained original reading/source drift")
    repair = recipe["proofing_repairs"]["excluded_sections"]
    excluded = work["proofing"]["excluded_sections"]
    author = {"member": "EPUB/chapter-0008.xhtml", "heading": "Bibliographisches und Textbehandlung", "id": None}
    if (excluded != repair["before"] or excluded.count(author) != 1
            or repair["after"] != [item for item in excluded if item != author]
            or repair["archive_as"] != "source_import_excluded_sections"):
        raise ValueError("GA033 exact restored import exclusion differs")
    work["proofing"][repair["archive_as"]] = deepcopy(excluded)
    work["proofing"]["excluded_sections"] = deepcopy(repair["after"])
    addition = recipe["source_additions"][0]
    passage = {"id": addition["passage_id"], "title": addition["title"],
        "source_label": work["passages"][0]["source_label"], "source_member": addition["source_segments"][0]["source_member"],
        "text": addition["text"], "source_text": addition["source_text"], "checksum": sha(addition["text"]), "ga_page": None,
        "metadata": {"page_numbers": [], "page_marker_source": "epub_source_page_labels", "annotations": [],
        "source_role": "author", "source_restoration": {k: deepcopy(addition[k]) for k in
            ("id", "source_segments", "source_text_sha256", "text_sha256", "evidence")}}}
    index = next(i for i, p in enumerate(work["passages"]) if p["id"] == addition["insert_before_passage_id"])
    work["passages"].insert(index, passage)
    work["passage_count"] = len(work["passages"])
    return work

def build(payload, source=SOURCE, review=None, pdf=SOURCE_PDF):
    review = review or read_json(REVIEW)
    check_source(source, review, pdf)
    payload = augment_original(payload, review)
    if (payload["work_id"] != "ga-033" or any(payload.get(k) != review[k] for k in ("source_sha256", "source_epub_sha256"))
            or [p["id"] for p in payload["passages"]] != list(review["passages"])):
        raise ValueError("GA033 reviewed source/passage inventory changed")
    recipe = {"schema_version": 1, "work_id": "ga-033", "offset_unit": "utf16",
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
    for key in ("original_passages", "source_additions", "proofing_repairs"):
        recipe[key] = deepcopy(review[key])
    repaired = deepcopy(payload)
    apply_metadata_repairs(repaired, recipe["metadata_repairs"])
    apply_annotation_repairs(repaired, recipe["annotation_repairs"])
    targets = {}
    for original, passage in zip(payload["passages"], repaired["passages"]):
        pid, text = passage["id"], passage["text"]
        witness = review["passages"][pid]
        if (sha(text) != witness["input_sha256"] or sha(passage["source_text"]) != witness["source_text_sha256"]
                or original["title"] != witness["title"]):
            raise ValueError("GA033 original reading/source/title drift: " + pid)
        starts = witness["starts"]
        if (not starts or starts[0]["start_codepoint"] != 0
                or sorted({s["start_codepoint"] for s in starts}) != [s["start_codepoint"] for s in starts]):
            raise ValueError("GA033 reviewed boundaries are ambiguous: " + pid)
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
                    raise ValueError("GA033 exact page furniture must occupy one slice")
                plan["omitted_parts"].append(slices[0] | {k: deepcopy(v) for k, v in omitted.items()
                    if k not in {"start_codepoint", "end_codepoint"}})
        for index, start in enumerate(starts):
            begin = start["start_codepoint"]
            end = starts[index + 1]["start_codepoint"] if index + 1 < len(starts) else len(text)
            if not 0 <= begin < end <= len(text) or not text[begin:].startswith(start["canonical_anchor"]):
                raise ValueError("GA033 exact canonical boundary changed: " + pid)
            spans = [(begin, end)]
            line_starts = start.get("line_starts", [])
            if line_starts:
                if (start["kind"] not in {"verse", "note"}
                        or sorted(set(line_starts)) != line_starts
                        or any(type(position) is not int or not begin < position < end for position in line_starts)):
                    raise ValueError("GA033 preserved line boundaries require exact ordered verse/list positions")
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
                raise ValueError("GA033 article sections must cover the retained passage from its beginning")
            plan["sections"] = []
            for number, index in enumerate(section_starts):
                end = section_starts[number + 1] if number + 1 < len(section_starts) else len(starts)
                block = preview["metadata"]["reading_blocks"][index]
                heading = preview["text"].encode("utf-16-le")[block["start_offset"] * 2:block["end_offset"] * 2].decode("utf-16-le").split("\n", 1)[0]
                title = starts[index].get("section_title", passage["title"] if not number else heading)
                if number and block["kind"] != "heading":
                    raise ValueError("GA033 independent article requires its original heading")
                plan["sections"].append({"start_segment": index, "end_segment": end, "title": title,
                                         "label_kind": starts[index].get("label_kind", "source_title"), "evidence": starts[index]["evidence"]})
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
    from repair_ga033_readability import apply_layout
    original_payload = deepcopy(payload)
    original_payload["passages"] = [p for p in payload["passages"] if p["id"] in review["original_passages"]]
    original_payload["passage_count"] = len(original_payload["passages"])
    original_payload["proofing"].pop("source_import_excluded_sections", None)
    original_payload["proofing"]["excluded_sections"] = deepcopy(review["proofing_repairs"]["excluded_sections"]["before"])
    apply_layout(original_payload, recipe)
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
    print(f"GA033: {len(result['passages'])} passages; {sum(len(p['segments']) for p in result['passages'].values())} reviewed blocks")
