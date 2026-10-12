#!/usr/bin/env python3
"""Build GA030 from frozen original-DOC layout and exact EPUB restorations.

Acquisition is recorded in ga030_layout_review.json. Rebuilding needs only the
retained three-passage baseline and hash-bound EPUB, never live downloads or
sentence/paragraph guesses. Every augmented input character is consumed once.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile

from lxml import etree

from finalize_library import read_json, normalize_text
from import_library import text_of, drop
from repair_source_structure import apply_recipe, sha, recipe_digest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research/proofreading-sources/ga-030.epub"
BASELINE = ROOT / "research/proofreading-layout-baseline/content/ga-030.json.gz"
REVIEW = ROOT / "tools/ga030_layout_review.json"
RECIPE = ROOT / "tools/ga030_structure.json"
ORIGINAL_IDS = ["ga-030-doc-heading-3", "ga-030-doc-heading-4", "ga-030-doc-heading-5"]


def source_parts(archive, addition):
    raw, reading = [], []
    for span in addition.get("source_segments") or [addition]:
        data = archive.read(span["source_member"])
        if hashlib.sha256(data).hexdigest() != span["member_sha256"]:
            raise ValueError("GA030 restored source member changed")
        body = etree.fromstring(data).find("{*}body")
        for index in span["body_indices"]:
            element = body[index]
            raw.append("".join(element.itertext()))
            clean = deepcopy(element)
            for anchor in list(clean.iter()):
                if anchor.get("role") == "doc-backlink":
                    drop(anchor)
            reading.append(text_of(clean))
    raw, reading = "\n\n".join(raw), "\n\n".join(reading)
    if "source_token" in addition:
        token = addition["source_token"]
        if (addition["kind"] != "text" or token != "[1895]" or addition.get("reading_rendering") != "literal_bracket_year_as_digits"
                or raw.count(token) != 1 or reading.count(token) != 1):
            raise ValueError("Unreviewed GA030 literal year rendering")
        return token, " 1895"
    for repair in addition.get("reading_edits", []):
        if (addition["kind"] != "annotation" or not repair.get("old")
                or not repair.get("evidence") or reading.count(repair["old"]) != repair["count"]):
            raise ValueError("Unreviewed GA030 annotation word seam")
        reading = reading.replace(repair["old"], repair["new"])
    return raw, reading


def check_source(source, review):
    if hashlib.sha256(source.read_bytes()).hexdigest() != review["source_epub_sha256"]:
        raise ValueError("GA030 reviewed EPUB changed")
    with ZipFile(source) as archive:
        for addition in review["source_additions"]:
            raw, text = source_parts(archive, addition)
            if (raw != addition["source_text"] or sha(raw) != addition["source_text_sha256"]
                    or text != addition["text"] or sha(text) != addition["text_sha256"]):
                raise ValueError("GA030 exact source addition changed: " + addition["id"])
        for member, checksum in review["source_members"].items():
            if hashlib.sha256(archive.read(member)).hexdigest() != checksum:
                raise ValueError("GA030 reviewed layout member changed")
        witnesses = [repair for repair in review.get("original_metadata_repairs", [])]
        for passage in review["passages"].values():
            witnesses.extend(passage["starts"])
            witnesses.extend(passage.get("omissions", []))
        for start in witnesses:
            if not start.get("source_member"):
                continue
            body = etree.fromstring(archive.read(start["source_member"])).find("{*}body")
            element = body[start["body_index"]]
            if sha("".join(element.itertext())) != start["source_paragraph_sha256"]:
                raise ValueError("GA030 exact paragraph witness changed")


def augment_original(payload, recipe):
    """Restore only explicitly identified source spans into the saved input."""
    if [p["id"] for p in payload["passages"]] != ORIGINAL_IDS:
        raise ValueError("GA030 restoration requires the exact original three-passage inventory")
    result = deepcopy(payload)
    passages = {p["id"]: p for p in result["passages"]}
    for pid, identity in recipe["original_passages"].items():
        passage = passages[pid]
        if (sha(passage["text"]) != identity["input_sha256"]
                or sha(passage.get("source_text", "")) != identity["source_text_sha256"]):
            raise ValueError("GA030 original input/source drift: " + pid)
    for repair in recipe.get("original_metadata_repairs", []):
        passage = passages[repair["passage_id"]]
        actual = {"ga_page":passage["ga_page"], "page_numbers":passage["metadata"]["page_numbers"]}
        if (actual != repair["before"] or repair["before"] != {"ga_page":"S. 1895","page_numbers":[1895]}
                or repair["after"] != {"ga_page":None,"page_numbers":[]}
                or repair["source_token"] != "[1895]" or not repair["evidence"]):
            raise ValueError("GA030 exact year/page metadata repair differs")
        passage["ga_page"] = repair["after"]["ga_page"]
        passage["metadata"]["page_numbers"] = deepcopy(repair["after"]["page_numbers"])
    for field, repair in recipe.get("proofing_repairs", {}).items():
        proofing = result["proofing"]
        if (field != "excluded_sections" or repair["archive_as"] != "source_import_excluded_sections"
                or proofing.get(field) != repair["before"] or repair["after"] != []
                or repair["archive_as"] in proofing or not repair["evidence"]):
            raise ValueError("GA030 restored editorial import exclusions differ")
        proofing[repair["archive_as"]] = deepcopy(repair["before"])
        proofing[field] = deepcopy(repair["after"])
    inserts = {}
    for addition in recipe["source_additions"]:
        if (sha(addition["source_text"]) != addition["source_text_sha256"]
                or sha(addition["text"]) != addition["text_sha256"] or not addition["evidence"]):
            raise ValueError("GA030 source addition identity/evidence differs")
        pid = addition["passage_id"]
        if addition["kind"] == "passage":
            if pid in passages:
                raise ValueError("Duplicate GA030 restored passage")
            text = addition["text"]
            passage = {"id": pid, "title": addition["title"], "source_label": payload["passages"][0]["source_label"],
                       "source_member": addition["source_segments"][0]["source_member"],
                       "text": text, "source_text": addition["source_text"], "checksum": sha(text), "ga_page": None,
                       "metadata": {"page_numbers": [], "page_marker_source": "epub_source_page_labels",
                                    "annotations": [], "source_role": addition["source_role"],
                                    "source_restoration": {k: deepcopy(addition[k]) for k in
                                        ("id", "source_segments", "source_text_sha256", "text_sha256", "evidence")}}}
            if addition.get("insert_before_passage_id"):
                index = next(i for i,p in enumerate(result["passages"]) if p["id"] == addition["insert_before_passage_id"])
                result["passages"].insert(index, passage)
            else:
                result["passages"].append(passage)
            passages[pid] = passage
        elif addition["kind"] == "text":
            inserts.setdefault(pid, []).append(addition)
        elif addition["kind"] == "annotation":
            annotations = passages[pid]["metadata"].setdefault("annotations", [])
            if any(a["id"] == addition["annotation_id"] for a in annotations):
                raise ValueError("GA030 restored annotation is already present")
            annotations.append({"id": addition["annotation_id"], "marker": addition["marker"],
                                "text": addition["text"], "source_text": addition["source_text"],
                                "source_restoration": {k: deepcopy(addition[k]) for k in
                                    ("id", "source_segments", "source_text_sha256", "text_sha256", "evidence", "reading_edits") if k in addition}})
        else:
            raise ValueError("Unknown GA030 source restoration kind")
    for pid, additions in inserts.items():
        before = passages[pid]["text"]
        positions = [a["position_codepoint"] for a in additions]
        if len(set(positions)) != len(positions):
            raise ValueError("Ambiguous GA030 insertion position")
        for addition in sorted(additions, key=lambda a:a["position_codepoint"], reverse=True):
            position = addition["position_codepoint"]
            if type(position) is not int or not 0 <= position <= len(before):
                raise ValueError("Invalid GA030 source insertion")
            if before[position:position+len(addition["following_anchor"])] != addition["following_anchor"]:
                raise ValueError("GA030 restored fragment anchor changed")
            before = before[:position] + addition["text"] + "\n\n" + before[position:]
        passages[pid]["text"] = before
        passages[pid]["checksum"] = sha(before)
        passages[pid]["metadata"]["source_restorations"] = [a["id"] for a in additions]
    result["passage_count"] = len(result["passages"])
    return result


def parts_between(text, begin, end):
    parts, offset = [], 0
    for index, block in enumerate(text.split("\n\n")):
        left, right = max(begin, offset), min(end, offset + len(block))
        if left < right and text[left:right].strip():
            parts.append({"block": index, "start": left-offset, "end": right-offset})
        offset += len(block)+2
    if not parts:
        raise ValueError("Empty GA030 reviewed source span")
    return parts


def render_without_annotation_changes(payload, recipe):
    work = deepcopy(payload)
    annotations = {p["id"]: p["metadata"].pop("annotations", []) for p in work["passages"]}
    result, changes = apply_recipe(work, recipe)
    for passage in result["passages"]:
        passage["metadata"]["annotations"] = annotations[passage["id"]]
    return result, changes


def build(payload, source=SOURCE, review=None):
    review = review or read_json(REVIEW)
    check_source(source, review)
    if payload["work_id"] != "ga-030" or any(payload.get(k) != review[k] for k in ("source_sha256", "source_epub_sha256")):
        raise ValueError("GA030 reviewed source edition changed")
    recipe = {"schema_version": 1, "work_id": "ga-030", "offset_unit": "utf16",
              "source_sha256": payload["source_sha256"], "source_epub_sha256": payload["source_epub_sha256"],
              "source_url": payload["source_url"], "source_additions": deepcopy(review["source_additions"]),
              "original_passages": deepcopy(review["original_passages"]),
              "original_metadata_repairs": deepcopy(review.get("original_metadata_repairs", [])),
              "proofing_repairs": deepcopy(review.get("proofing_repairs", {})),
              "source_evidence": {"review_sha256": recipe_digest(review), "method": review["method"],
                                  "original_doc_sha256": review["original_doc_sha256"],
                                  "original_pdf_sha256": review["original_pdf_sha256"]},
              "known_gaps": deepcopy(review["known_gaps"]), "review_flags": deepcopy(review["review_flags"]),
              "passages": {}}
    augmented = augment_original(payload, recipe)
    if [p["id"] for p in augmented["passages"]] != list(review["passages"]):
        raise ValueError("GA030 augmented passage inventory differs")
    targets = {}
    for passage in augmented["passages"]:
        pid, text = passage["id"], passage["text"]
        witness = review["passages"][pid]
        if sha(text) != witness["input_sha256"]:
            raise ValueError("GA030 augmented reading input changed: " + pid)
        starts = witness["starts"]
        if starts[0]["start_codepoint"] != 0 or sorted({s["start_codepoint"] for s in starts}) != [s["start_codepoint"] for s in starts]:
            raise ValueError("GA030 reviewed boundaries are ambiguous")
        plan = {"input_sha256": sha(text), "source_text_sha256": sha(passage["source_text"]),
                "group_title": witness["group_title"], "segments": [], "edits": witness.get("edits", [])}
        omissions = witness.get("omissions", [])
        if omissions:
            plan["omitted_parts"] = []
            for omitted in omissions:
                parts = parts_between(text, omitted["start_codepoint"], omitted["end_codepoint"])
                if len(parts) != 1:
                    raise ValueError("GA030 exact page footer must occupy one source slice")
                plan["omitted_parts"].append(parts[0] | {"kind":"page_footer", "page":omitted["page"],
                    "text_sha256":omitted["text_sha256"], "evidence":omitted["evidence"],
                    "source_member":omitted["source_member"], "body_index":omitted["body_index"],
                    "source_paragraph_sha256":omitted["source_paragraph_sha256"]})
        for index, start in enumerate(starts):
            begin = start["start_codepoint"]
            end = starts[index+1]["start_codepoint"] if index+1<len(starts) else len(text)
            if not text[begin:].startswith(start["canonical_anchor"]):
                raise ValueError("GA030 exact canonical boundary changed")
            spans = [(begin,end)]
            for omitted in omissions:
                left,right = omitted["start_codepoint"],omitted["end_codepoint"]
                spans = [
                    piece for l,r in spans for piece in
                    ([(l,r)] if right<=l or left>=r else [(l,min(r,left)),(max(l,right),r)]) if piece[0]<piece[1]]
            parts = [part for l,r in spans if text[l:r].strip() for part in parts_between(text,l,r)]
            segment = {"kind": start["kind"], "parts": parts,
                       "join": start.get("join", "\n" if start["kind"] == "verse" else " "),
                       "evidence": start["evidence"], "source_pdf_pages": [start["page"]] if start.get("page") else []}
            if start["kind"] == "heading": segment["level"] = 2
            if start.get("preserve_lines"): segment["preserve_lines"] = True
            if start.get("page"):
                # Reviewed paragraph starts are exact printed-page targets.
                segment["pages"] = [start["page"]]
            plan["segments"].append(segment)
        preview = deepcopy(passage)
        preview["metadata"].pop("annotations", None)
        from repair_source_structure import apply_passage_plan
        apply_passage_plan(preview, plan, "preview")
        section_starts = [index for index,start in enumerate(starts) if start.get("toc_target")]
        if section_starts and section_starts[0] == 0:
            plan["sections"] = []
            for number,index in enumerate(section_starts):
                end = section_starts[number+1] if number+1<len(section_starts) else len(starts)
                block = preview["metadata"]["reading_blocks"][index]
                actual = preview["text"].encode("utf-16-le")[2*block["start_offset"]:2*block["end_offset"]].decode("utf-16-le").split("\n",1)[0]
                title = passage["title"] if not number else actual
                if number and block["kind"] != "heading":
                    raise ValueError("An independent GA030 article requires its actual source heading")
                plan["sections"].append({"start_segment":index,"end_segment":end,"title":title,
                    "label_kind":"source_title","evidence":starts[index]["evidence"]})
        plan["output_sha256"] = sha(preview["text"])
        recipe["passages"][pid] = plan
        for index, start in enumerate(starts):
            if start.get("toc_target"):
                targets[start["toc_target"]] = (pid,preview["metadata"]["reading_blocks"][index]["start_offset"])
    toc = []
    for row in review["table_of_contents"]:
        pid, offset = targets[row["target"]]
        toc.append({k: deepcopy(v) for k,v in row.items() if k != "target"} | {"passage_id":pid,"start_offset":offset})
    recipe["table_of_contents"] = toc
    # The same immutable inputs must render and validate immediately.
    render_without_annotation_changes(augmented, recipe)
    return recipe


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=BASELINE)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--review", type=Path, default=REVIEW)
    parser.add_argument("--output", type=Path, default=RECIPE)
    args = parser.parse_args()
    result = build(read_json(args.input), args.source, read_json(args.review))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(f"GA030: {len(result['passages'])} passages; {sum(len(p['segments']) for p in result['passages'].values())} reviewed blocks; {len(result['table_of_contents'])} contents entries")
