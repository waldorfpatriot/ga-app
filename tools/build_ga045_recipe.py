#!/usr/bin/env python3
"""Freeze GA045 layout from the retained original DOC/EPUB witnesses.

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
SOURCE = ROOT / "research/proofreading-sources/ga-045.epub"
SOURCE_PDF = ROOT / "research/proofreading-sources/ga-045-original.pdf"
BASELINE = ROOT / "research/proofreading-layout-baseline/content/ga-045.json.gz"
REVIEW = ROOT / "tools/ga045_layout_review.json"
RECIPE = ROOT / "tools/ga045_structure.json"


def source_element(archive, witness):
    cache = getattr(archive, "_ga045_body_cache", None)
    if cache is None:
        cache = archive._ga045_body_cache = {}
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


def recovered_reading_text(element):
    """Reconstruct imported physical lines, skipping only invented backlinks."""
    marker = "\ufdd0"
    def collect(node):
        parts = [node.text or ""]
        for child in node:
            if child.get("role") != "doc-backlink":
                parts.append(marker if child.tag.rsplit("}", 1)[-1] == "br" else collect(child))
            parts.append(child.tail or "")
        return "".join(parts)
    text = re.sub(r"[ \t\r\n\f]+", " ", collect(element))
    return re.sub(" *" + marker + " *", "\n", text).strip()


def validate_source_addition(review, source=SOURCE):
    additions = review.get("source_additions", [])
    if len(additions) != 1:
        raise ValueError("GA045 requires its one exact omitted main paragraph")
    addition = additions[0]
    member, index = "EPUB/chapter-0002.xhtml", 46
    span = [{"source_member": member, "body_indices": [index], "member_sha256": review["source_evidence"]["source_members"][member]
             if "source_evidence" in review else review["source_members"][member]}]
    with ZipFile(source) as archive:
        element = source_element(archive, {"source_member": member, "body_index": index})
        raw, text = "".join(element.itertext()), recovered_reading_text(element)
    doc_path = review.get("source_layout_path", "research/proofreading-sources/ga-045-doc-layout.json")
    record = read_json(ROOT / doc_path)["paragraphs"][218]
    if (addition.get("id") != "ga045-restored-main-paragraph-59" or addition.get("kind") != "text"
            or addition.get("passage_id") != "ga-045-doc-heading-4" or addition.get("source_segments") != span
            or addition.get("source_text") != raw or addition.get("text") != text
            or addition.get("source_text_sha256") != sha(raw) or addition.get("text_sha256") != sha(text)
            or addition.get("source_doc_paragraph_index") != 218
            or addition.get("source_doc_paragraph_sha256") != sha(record["text"])
            or element.get("id") != "footnote-recovered-9" or element.get("role") != "doc-footnote"
            or not addition.get("evidence")):
        raise ValueError("GA045 restoration differs from its exact original main paragraph")
    # The EPUB mislabeled a full-size main paragraph as a footnote. The original
    # DOC contains the same words/physical lines, without that generated backlink.
    if " ".join(record["text"].split()) != " ".join(text.split()):
        raise ValueError("GA045 restored main paragraph differs from original DOC")


def augment_original(payload, recipe):
    result = deepcopy(payload)
    identities = {p["id"]: {"input_sha256": sha(p["text"]), "source_text_sha256": sha(p["source_text"]),
                            "title": p["title"]} for p in result["passages"]}
    if identities != recipe.get("original_passages"):
        raise ValueError("GA045 exact original passage identities differ")
    validate_source_addition(recipe)
    addition = recipe["source_additions"][0]
    passage = next(p for p in result["passages"] if p["id"] == addition["passage_id"])
    position = addition["position_codepoint"]
    before, after = passage["text"][:position], passage["text"][position:]
    if (type(position) is not int or not 0 < position < len(passage["text"])
            or not before.endswith(addition["preceding_anchor"])
            or not after.startswith(addition["following_anchor"])
            or not before.endswith("\n\n") or not after.startswith('Der «Ich-Mensch» und der «astralische Mensch» stellen')):
        raise ValueError("GA045 restored paragraph differs from its exact source position")
    passage["text"] = before + addition["text"] + "\n\n" + after
    passage["checksum"] = sha(passage["text"])
    passage["metadata"]["source_restorations"] = [addition["id"]]
    return result


def check_source(source, review, pdf=SOURCE_PDF):
    for kind in ("original_doc", "original_pdf", "source_layout"):
        path = ROOT / review[kind + "_path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != review[kind + "_sha256"]:
            raise ValueError("GA045 source document/layout byte identity changed: " + kind)
    if hashlib.sha256(source.read_bytes()).hexdigest() != review["source_epub_sha256"]:
        raise ValueError("GA045 reviewed EPUB changed")
    validate_source_addition(review, source)
    layout = read_json(ROOT / review["source_layout_path"])
    records = layout["paragraphs"]
    with ZipFile(source) as archive:
        for member, checksum in review["source_members"].items():
            if hashlib.sha256(archive.read(member)).hexdigest() != checksum:
                raise ValueError("GA045 original EPUB member changed")
        for passage in review["passages"].values():
            parts = passage.get("source_parts", [])
            if not parts:
                raise ValueError("GA045 exact source reconstruction is missing")
            raw = []
            for part in parts:
                value = "".join(source_element(archive, part).itertext())
                if sha(value) != part["source_paragraph_sha256"]:
                    raise ValueError("GA045 original source paragraph changed")
                raw.append(value)
            if sha("\n\n".join(raw)) != passage["source_text_sha256"]:
                raise ValueError("GA045 exact source reconstruction differs")
            for witness in passage["starts"]:
                value = "".join(source_element(archive, witness).itertext())
                if not witness.get("evidence") or sha(value) != witness["source_paragraph_sha256"]:
                    raise ValueError("GA045 source boundary lacks its exact original witness")
                record = records[witness["source_doc_paragraph_index"]]
                if sha(record["text"]) != witness["source_doc_paragraph_sha256"]:
                    raise ValueError("GA045 source DOC boundary changed")
                point = witness.get("source_doc_start_codepoint", 0)
                if type(point) is not int or not 0 <= point < len(record["text"]):
                    raise ValueError("GA045 invalid original DOC boundary position")
                if point and (record["text"][point - 1] != "\n" or witness["kind"] != "note"
                              or record["text"][point:] not in {"Hier bricht der Text ab.", "Es wird vorausgesetzt:"}):
                    raise ValueError("GA045 internal boundary exceeds exact source editorial/list line")
                from source_layout import normalized
                anchor = normalized(witness["canonical_anchor"])
                original = normalized(record["text"][point:])
                if anchor and not (original.startswith(anchor) or anchor.startswith(original)):
                    raise ValueError("GA045 source DOC paragraph anchor differs")
            for repair in passage.get("edits", []):
                origins = []
                for witness in repair["source_witnesses"]:
                    value = "".join(source_element(archive, witness).itertext())
                    if sha(value) != witness["source_paragraph_sha256"]:
                        raise ValueError("GA045 source word seam changed")
                    origins.append(value)
                match = re.fullmatch(r"([A-Za-zÄÖÜäöüß]+)-\s+([A-Za-zÄÖÜäöüß]+)", repair["old"])
                if (repair.get("kind") != "physical_word_seam" or not match
                        or repair.get("match_word_boundaries") is not True
                        or repair["new"] not in {match[1] + match[2], match[1] + "-" + match[2]}):
                    raise ValueError("GA045 reflow changes original word characters")
                if repair.get("source_contains_exact_physical_lf"):
                    seam = re.compile(re.escape(match[1]) + r"-\s*\n\s*" + re.escape(match[2]) + r"(?![A-Za-zÄÖÜäöüß])")
                    if not origins or any(not seam.search(value) for value in origins):
                        raise ValueError("GA045 seam lacks its actual original physical line end")
                    doc_origins = repair["source_doc_witnesses"]
                    if not doc_origins:
                        raise ValueError("GA045 seam lacks source DOC evidence")
                    for origin in doc_origins:
                        record = records[origin["source_doc_paragraph_index"]]
                        if sha(record["text"]) != origin["source_doc_paragraph_sha256"] or not seam.search(record["text"]):
                            raise ValueError("GA045 seam differs from the exact original DOC line")
                elif len(origins) != 2 or " ".join(repair["old"].split()) not in " ".join("\n\n".join(origins).split()):
                    raise ValueError("GA045 page seam lacks both original source fragments")
                if repair.get("physical_page_seam"):
                    doc_origins = repair.get("source_doc_witnesses", [])
                    if len(doc_origins) != 2:
                        raise ValueError("GA045 page seam lacks both exact DOC paragraphs")
                    left, right = [records[origin["source_doc_paragraph_index"]] for origin in doc_origins]
                    if (right["index"] != left["index"] + 2
                            or any(sha(record["text"]) != origin["source_doc_paragraph_sha256"]
                                   for record, origin in zip((left, right), doc_origins))
                            or not left["text"].rstrip().endswith(match[1] + "-")
                            or not right["text"].lstrip().startswith(match[2])):
                        raise ValueError("GA045 page seam differs from exact source DOC word fragments")
                    footer = records[left["index"] + 1]
                    witness = repair.get("source_doc_page_footer", {})
                    if (not footer["is_page_footer"] or witness.get("source_doc_paragraph_index") != footer["index"]
                            or witness.get("source_doc_paragraph_sha256") != sha(footer["text"])
                            or witness.get("page") != footer["footer_page"]):
                        raise ValueError("GA045 page seam lacks its exact intervening printed footer")


def parts_between(text, begin, end):
    parts, offset = [], 0
    for index, block in enumerate(text.split("\n\n")):
        left, right = max(begin, offset), min(end, offset + len(block))
        if left < right and text[left:right].strip():
            parts.append({"block": index, "start": left - offset, "end": right - offset})
        offset += len(block) + 2
    if not parts:
        raise ValueError("Empty GA045 reviewed source span")
    return parts


def apply_metadata_repairs(payload, repairs, *, repeated=False):
    if repairs:
        raise ValueError("GA045 reflow does not replace original metadata")


def apply_annotation_repairs(payload, repairs, *, repeated=False):
    if repairs:
        raise ValueError("GA045 reflow does not replace original annotations")


def build(payload, source=SOURCE, review=None, pdf=SOURCE_PDF):
    review = review or read_json(REVIEW)
    check_source(source, review, pdf)
    if (payload["work_id"] != "ga-045" or any(payload.get(k) != review[k] for k in ("source_sha256", "source_epub_sha256"))
            or [p["id"] for p in payload["passages"]] != list(review["passages"])):
        raise ValueError("GA045 reviewed source/passage inventory changed")
    recipe = {"schema_version": 1, "work_id": "ga-045", "offset_unit": "utf16",
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
    original_payload = deepcopy(payload)
    recipe["source_additions"] = deepcopy(review["source_additions"])
    recipe["original_passages"] = deepcopy(review["original_passages"])
    payload = augment_original(payload, recipe)
    repaired = deepcopy(payload)
    apply_metadata_repairs(repaired, recipe["metadata_repairs"])
    apply_annotation_repairs(repaired, recipe["annotation_repairs"])
    targets = {}
    for original, passage in zip(payload["passages"], repaired["passages"]):
        pid, text = passage["id"], passage["text"]
        witness = review["passages"][pid]
        if (sha(text) != witness["input_sha256"] or sha(passage["source_text"]) != witness["source_text_sha256"]
                or original["title"] != witness["title"]):
            raise ValueError("GA045 original reading/source/title drift: " + pid)
        starts = witness["starts"]
        if (not starts or starts[0]["start_codepoint"] != 0
                or sorted({s["start_codepoint"] for s in starts}) != [s["start_codepoint"] for s in starts]):
            raise ValueError("GA045 reviewed boundaries are ambiguous: " + pid)
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
                    raise ValueError("GA045 exact page furniture must occupy one slice")
                plan["omitted_parts"].append(slices[0] | {k: deepcopy(v) for k, v in omitted.items()
                    if k not in {"start_codepoint", "end_codepoint"}})
        for index, start in enumerate(starts):
            begin = start["start_codepoint"]
            end = starts[index + 1]["start_codepoint"] if index + 1 < len(starts) else len(text)
            if not 0 <= begin < end <= len(text) or not text[begin:].startswith(start["canonical_anchor"]):
                raise ValueError("GA045 exact canonical boundary changed: " + pid)
            spans = [(begin, end)]
            line_starts = start.get("line_starts", [])
            if line_starts:
                if (start["kind"] not in {"verse", "note"}
                        or sorted(set(line_starts)) != line_starts
                        or any(type(position) is not int or not begin < position < end for position in line_starts)):
                    raise ValueError("GA045 preserved line boundaries require exact ordered verse/list positions")
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
                raise ValueError("GA045 article sections must cover the retained passage from its beginning")
            plan["sections"] = []
            for number, index in enumerate(section_starts):
                end = section_starts[number + 1] if number + 1 < len(section_starts) else len(starts)
                block = preview["metadata"]["reading_blocks"][index]
                heading = preview["text"].encode("utf-16-le")[block["start_offset"] * 2:block["end_offset"] * 2].decode("utf-16-le").split("\n", 1)[0]
                title = passage["title"] if not number else heading
                if number and block["kind"] != "heading":
                    raise ValueError("GA045 independent article requires its original heading")
                plan["sections"].append({"start_segment": index, "end_segment": end, "title": starts[index].get("section_title", title),
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
    from repair_ga045_readability import apply_layout
    apply_layout(original_payload, recipe)
    return recipe


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=BASELINE if BASELINE.exists() else ROOT / "server/priv/content/ga-045.json.gz")
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--pdf", type=Path, default=SOURCE_PDF)
    parser.add_argument("--review", type=Path, default=REVIEW)
    parser.add_argument("--output", type=Path, default=RECIPE)
    args = parser.parse_args()
    result = build(read_json(args.input), args.source, read_json(args.review), args.pdf)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"GA045: {len(result['passages'])} passages; {sum(len(p['segments']) for p in result['passages'].values())} reviewed blocks")
