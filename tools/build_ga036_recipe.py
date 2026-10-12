#!/usr/bin/env python3
"""Freeze GA036 layout from the reviewed original DOC/EPUB/PDF witnesses.

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
SOURCE = ROOT / "research/proofreading-sources/ga-036.epub"
SOURCE_PDF = ROOT / "research/proofreading-sources/ga-036-original.pdf"
BASELINE = ROOT / "research/proofreading-layout-baseline/content/ga-036.json.gz"
REVIEW = ROOT / "tools/ga036_layout_review.json"
RECIPE = ROOT / "tools/ga036_structure.json"


def source_element(archive, witness):
    cache = getattr(archive, "_ga036_body_cache", None)
    if cache is None:
        cache = archive._ga036_body_cache = {}
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


def check_source(source, review, pdf=SOURCE_PDF):
    for kind in ("original_doc", "original_pdf", "source_layout"):
        if hashlib.sha256((ROOT / review[kind + "_path"]).read_bytes()).hexdigest() != review[kind + "_sha256"]:
            raise ValueError("GA036 original source/layout byte identity changed: " + kind)
    if hashlib.sha256(source.read_bytes()).hexdigest() != review["source_epub_sha256"]:
        raise ValueError("GA036 reviewed EPUB changed")
    with ZipFile(source) as archive:
        for member, checksum in review["source_members"].items():
            if hashlib.sha256(archive.read(member)).hexdigest() != checksum:
                raise ValueError("GA036 reviewed source member changed: " + member)
        witnesses = list(review.get("metadata_repairs", [])) + list(review.get("annotation_repairs", []))
        witnesses.extend(origin for repair in review.get("metadata_repairs", [])
                         for origin in repair.get("source_witnesses", []))
        for passage in review["passages"].values():
            witnesses.extend(passage["starts"])
            witnesses.extend(passage.get("omissions", []))
            witnesses.extend(repair for repair in passage.get("edits", []) if repair.get("source_member"))
            source_parts = passage.get("source_parts", [])
            if not source_parts:
                raise ValueError("GA036 retained source lacks a complete paragraph reconstruction")
            raw_parts = []
            for witness in source_parts:
                raw = "".join(source_element(archive, witness).itertext())
                if sha(raw) != witness["source_paragraph_sha256"]:
                    raise ValueError("GA036 exact retained source paragraph changed")
                raw_parts.append(raw)
            if sha("\n\n".join(raw_parts)) != passage["source_text_sha256"]:
                raise ValueError("GA036 retained original source reconstruction differs")
            for span in passage.get("source_segments", []):
                data = archive.read(span["source_member"])
                if hashlib.sha256(data).hexdigest() != span["member_sha256"]:
                    raise ValueError("GA036 exact source segment member changed")
                body = ET.fromstring(data).find("{*}body")
                for index, checksum in span.get("body_sha256", {}).items():
                    if sha("".join(body[int(index)].itertext())) != checksum:
                        raise ValueError("GA036 exact retained source paragraph changed")
        for witness in witnesses:
            if not witness.get("source_member") or not witness.get("source_paragraph_sha256"):
                raise ValueError("GA036 boundary lacks an exact original paragraph witness")
            if sha("".join(source_element(archive, witness).itertext())) != witness["source_paragraph_sha256"]:
                raise ValueError("GA036 exact paragraph witness changed")
        for repair in review.get("annotation_repairs", []):
            raw = "".join(source_element(archive, repair).itertext())
            if raw.strip() != repair["before"] or annotation_reading_text(repair["before"]) != repair["after"]:
                raise ValueError("GA036 annotation repair differs from its exact physical source wraps")
        validate_annotation_additions(review, archive)
        for passage in review["passages"].values():
            for repair in passage.get("edits", []):
                if repair.get("source_witnesses"):
                    raw_parts = []
                    for witness in repair["source_witnesses"]:
                        raw = "".join(source_element(archive, witness).itertext())
                        if sha(raw) != witness["source_paragraph_sha256"]:
                            raise ValueError("GA036 exact physical seam witness changed")
                        raw_parts.append(raw)
                    if repair.get("kind") == "physical_word_seam" and " ".join(repair["old"].split()) not in " ".join("\n\n".join(raw_parts).split()):
                        raise ValueError("GA036 physical seam token has no exact source context")
                if repair.get("kind") == "physical_word_seam":
                    old, new = [re.sub(r"\s", "", repair[field]) for field in ("old", "new")]
                    if new != old and not any(new == old[:index] + old[index + 1:]
                                               for index, char in enumerate(old) if char == "-"):
                        raise ValueError("GA036 physical seam changes original source characters")
                if repair.get("kind") not in {"physical_word_seam", "literal_year_restoration", "source_contents_restoration", "source_heading_restoration"}:
                    raise ValueError("Unknown or missing source-reviewed word repair kind")
                if repair.get("kind") == "source_contents_restoration" and repair["new"] != passage.get("restored_contents_text"):
                    raise ValueError("GA036 original contents replacement differs from frozen rows")
                if repair.get("kind") == "source_heading_restoration" and repair["new"] != " ".join(" ".join(raw.split()) for raw in raw_parts):
                    raise ValueError("GA036 group heading differs from exact original source paragraphs")
                if repair.get("kind") != "literal_year_restoration":
                    continue
                token = repair.get("source_token", "")
                if not re.fullmatch(r"\[18\d\d\]|\[190[012]\]", token):
                    raise ValueError("GA036 literal restoration requires an exact source year")
                raw = "".join(source_element(archive, repair).itertext())
                year = token[1:-1]
                if token not in raw or repair["new"].count(year) != repair["old"].count(year) + 1:
                    raise ValueError("GA036 restored year has no exact original literal witness")
                positions = [match.start() for match in re.finditer(re.escape(year), repair["new"])]
                if not any(" ".join((repair["new"][:position] + repair["new"][position + len(year):]).split())
                           == " ".join(repair["old"].split()) for position in positions):
                    raise ValueError("GA036 literal repair changes more than its single original year")
    from check_essay_layout import inspect_pdf_witnesses
    for passage in review["passages"].values():
        for repair in passage.get("edits", []):
            inspect_pdf_witnesses(repair, review)


def validate_annotation_additions(review, archive):
    selectors = {(6, 66): (12, 63, 35), (9, 27): (6, 24, 47), (9, 41): (5, 37, 48),
                 (9, 110): (4, 105, 52), (9, 127): (3, 125, 53)}
    additions = review.get("annotation_additions", [])
    if len(additions) != 5:
        raise ValueError("GA036 requires exactly the five reviewed omitted author notes")
    seen = set()
    for addition in additions:
        spans = addition["source_segments"]
        if len(spans) != 1 or len(spans[0]["body_indices"]) != 1:
            raise ValueError("GA036 author-note addition exceeds one original element")
        span = spans[0]
        member, index = span["source_member"], span["body_indices"][0]
        key = (int(re.search(r"chapter-(\d+)", member)[1]), index)
        if key not in selectors or key in seen or span["member_sha256"] != review["source_members"][member]:
            raise ValueError("GA036 author-note source selector changed or repeated")
        seen.add(key)
        number, reference_index, pnum = selectors[key]
        element = source_element(archive, {"source_member": member, "body_index": index})
        raw = "".join(element.itertext())
        reference = addition["source_reference"]
        heading = source_element(archive, {"source_member": member, "body_index": reference_index})
        heading_hash = sha("".join(heading.itertext()))
        expected_heading = {"source_member": member, "body_index": reference_index,
                            "source_paragraph_sha256": heading_hash}
        links = [a for a in heading.findall(".//{*}a") if a.get("id") == "noteref-recovered-" + str(number)]
        if (addition["kind"] != "annotation" or addition["passage_id"] != "ga-036-doc-heading-" + str(pnum)
                or addition["annotation_id"] != member + "#footnote-recovered-" + str(number)
                or addition["marker"] != "*" or element.get("role") != "doc-footnote"
                or element.get("id") != "footnote-recovered-" + str(number)
                or addition["source_text"] != raw or addition["text"] != raw.strip()
                or addition["source_text_sha256"] != sha(raw) or addition["text_sha256"] != sha(raw.strip())
                or reference.get("source_heading_witness") != expected_heading
                or reference.get("reference_id") != "noteref-recovered-" + str(number)
                or any(reference.get(k) != v for k, v in expected_heading.items())
                or heading.tag.rsplit("}", 1)[-1] != "h2"
                or "".join(heading.itertext()) != review["passages"][addition["passage_id"]]["title"]
                or len(links) != 1 or links[0].get("role") != "doc-noteref"
                or not links[0].get("href", "").endswith("#" + element.get("id"))
                or "".join(links[0].itertext()) != "*" or not addition.get("evidence")):
            raise ValueError("GA036 exact author-note/marked-title witness changed")


def augment_annotations(payload, recipe, source=SOURCE):
    """Restore only frozen original notes in their original source order."""
    result = deepcopy(payload)
    passages = {p["id"]: p for p in result["passages"]}
    with ZipFile(source) as archive:
        order = {member: i for i, member in enumerate(recipe["source_evidence"]["source_members"])}
        for addition in recipe.get("annotation_additions", []):
            notes = passages[addition["passage_id"]]["metadata"]["annotations"]
            if any(note["id"] == addition["annotation_id"] for note in notes):
                raise ValueError("GA036 restored annotation already exists")
            proof = {k: deepcopy(addition[k]) for k in ("id", "source_segments", "source_text_sha256", "text_sha256", "evidence")}
            notes.append({"id": addition["annotation_id"], "marker": addition["marker"],
                          "text": addition["text"], "source_text": addition["source_text"], "source_restoration": proof})
        def position(note):
            member, identifier = note["id"].split("#", 1)
            body = ET.fromstring(archive.read(member)).find("{*}body")
            indices = [i for i, element in enumerate(body) if element.get("id") == identifier]
            if len(indices) != 1:
                raise ValueError("GA036 annotation source order is ambiguous")
            return order[member], indices[0]
        for original, passage in zip(payload["passages"], result["passages"]):
            notes = passage["metadata"]["annotations"]
            notes.sort(key=position)
            ids = [n["id"] for n in original["metadata"]["annotations"]]
            if [n["id"] for n in notes if n["id"] in ids] != ids:
                raise ValueError("GA036 original relative annotation order changed")
    return result


def parts_between(text, begin, end):
    parts, offset = [], 0
    for index, block in enumerate(text.split("\n\n")):
        left, right = max(begin, offset), min(end, offset + len(block))
        if left < right and text[left:right].strip():
            parts.append({"block": index, "start": left - offset, "end": right - offset})
        offset += len(block) + 2
    if not parts:
        raise ValueError("Empty GA036 reviewed source span")
    return parts


def apply_metadata_repairs(payload, repairs, *, repeated=False):
    passages = {p["id"]: p for p in payload["passages"]}
    for repair in repairs:
        passage = passages[repair["passage_id"]]
        before, after = repair["before"], repair["after"]
        if (set(before) != set(after) or not set(before) <= {"title", "ga_page", "page_numbers"}
                or not before or not repair.get("evidence")):
            raise ValueError("GA036 metadata repair lacks an exact reviewed contract")
        for field in before:
            actual = passage["metadata"].get(field) if field == "page_numbers" else passage.get(field)
            if actual != (after if repeated else before)[field]:
                raise ValueError("GA036 original/rendered metadata drift: " + passage["id"] + " " + field)
            if not repeated:
                if field == "page_numbers":
                    passage["metadata"][field] = deepcopy(after[field])
                else:
                    passage[field] = deepcopy(after[field])


def annotation_reading_text(text):
    if "\n\n" in text:
        raise ValueError("GA036 annotation paragraph breaks require separate review")
    return re.sub(r"\s*\n\s*", " ", text)


def apply_annotation_repairs(payload, repairs, *, repeated=False):
    passages = {p["id"]: p for p in payload["passages"]}
    seen = set()
    for repair in repairs:
        key = (repair["passage_id"], repair["annotation_id"])
        if key in seen or not repair.get("evidence") or annotation_reading_text(repair["before"]) != repair["after"]:
            raise ValueError("GA036 annotation repair lacks an exact whitespace contract")
        seen.add(key)
        matching = [note for note in passages[repair["passage_id"]]["metadata"]["annotations"]
                    if note["id"] == repair["annotation_id"]]
        if (len(matching) != 1 or matching[0]["marker"] != repair["marker"]
                or matching[0]["text"] != repair["after" if repeated else "before"]):
            raise ValueError("GA036 original/rendered annotation drift: " + repair["annotation_id"])
        if not repeated:
            matching[0]["text"] = repair["after"]


def build(payload, source=SOURCE, review=None, pdf=SOURCE_PDF):
    review = review or read_json(REVIEW)
    check_source(source, review, pdf)
    if (payload["work_id"] != "ga-036" or any(payload.get(k) != review[k] for k in ("source_sha256", "source_epub_sha256"))
            or [p["id"] for p in payload["passages"]] != list(review["passages"])):
        raise ValueError("GA036 reviewed source/passage inventory changed")
    recipe = {"schema_version": 1, "work_id": "ga-036", "offset_unit": "utf16",
              "source_sha256": payload["source_sha256"], "source_epub_sha256": payload["source_epub_sha256"],
              "source_url": payload["source_url"], "metadata_repairs": deepcopy(review.get("metadata_repairs", [])),
              "annotation_repairs": deepcopy(review.get("annotation_repairs", [])),
              "annotation_additions": deepcopy(review.get("annotation_additions", [])),
              "source_evidence": {"review_sha256": recipe_digest(review), "method": review["method"],
                                  "source_members": deepcopy(review["source_members"])},
              "known_gaps": deepcopy(review.get("known_gaps", [])),
              "review_flags": deepcopy(review.get("review_flags", [])), "passages": {}}
    for key in ("original_doc_sha256", "original_pdf_sha256", "source_layout_sha256"):
        if key in review:
            recipe["source_evidence"][key] = review[key]
    augmented = augment_annotations(payload, recipe)
    repaired = deepcopy(augmented)
    apply_metadata_repairs(repaired, recipe["metadata_repairs"])
    apply_annotation_repairs(repaired, recipe["annotation_repairs"])
    targets = {}
    for original, passage in zip(augmented["passages"], repaired["passages"]):
        pid, text = passage["id"], passage["text"]
        witness = review["passages"][pid]
        if (sha(text) != witness["input_sha256"] or sha(passage["source_text"]) != witness["source_text_sha256"]
                or original["title"] != witness["title"]):
            raise ValueError("GA036 original reading/source/title drift: " + pid)
        starts = witness["starts"]
        if (not starts or starts[0]["start_codepoint"] != 0
                or sorted({s["start_codepoint"] for s in starts}) != [s["start_codepoint"] for s in starts]):
            raise ValueError("GA036 reviewed boundaries are ambiguous: " + pid)
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
                    raise ValueError("GA036 exact page furniture must occupy one slice")
                plan["omitted_parts"].append(slices[0] | {k: deepcopy(v) for k, v in omitted.items()
                    if k not in {"start_codepoint", "end_codepoint"}})
        for index, start in enumerate(starts):
            begin = start["start_codepoint"]
            end = starts[index + 1]["start_codepoint"] if index + 1 < len(starts) else len(text)
            if not 0 <= begin < end <= len(text) or not text[begin:].startswith(start["canonical_anchor"]):
                raise ValueError("GA036 exact canonical boundary changed: " + pid)
            spans = [(begin, end)]
            line_starts = start.get("line_starts", [])
            if line_starts:
                if (start["kind"] not in {"verse", "note"}
                        or sorted(set(line_starts)) != line_starts
                        or any(type(position) is not int or not begin < position < end for position in line_starts)):
                    raise ValueError("GA036 preserved line boundaries require exact ordered verse/list positions")
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
                raise ValueError("GA036 article sections must cover the retained passage from its beginning")
            plan["sections"] = []
            for number, index in enumerate(section_starts):
                end = section_starts[number + 1] if number + 1 < len(section_starts) else len(starts)
                block = preview["metadata"]["reading_blocks"][index]
                heading = preview["text"].encode("utf-16-le")[block["start_offset"] * 2:block["end_offset"] * 2].decode("utf-16-le").split("\n", 1)[0]
                title = passage["title"] if not number else heading
                if number and block["kind"] != "heading":
                    raise ValueError("GA036 independent article requires its original heading")
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
    from repair_ga036_readability import apply_layout
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
    print(f"GA036: {len(result['passages'])} passages; {sum(len(p['segments']) for p in result['passages'].values())} reviewed blocks")
