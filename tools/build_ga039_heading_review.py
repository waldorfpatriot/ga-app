#!/usr/bin/env python3
"""Freeze deterministic GA039 output hashes and offsets from a source audit."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

from finalize_library import content_file, read_json, write_json
import repair_ga039_headings as repair

ROOT = repair.ROOT
AUDIT = ROOT / "research/proofreading-ga039-source-audit.json"


def shifted_offset(pid, field, offset, repairs):
    return offset + sum(len(item["new"]) - len(item["old"]) for item in repairs
                        if item["passage_id"] == pid and item["field"] == field and item["start_codepoint"] < offset)


def build_review(payload, audit):
    review = deepcopy(audit)
    review["source_audit_sha256"] = repair.object_digest(audit)
    review.update(work_id=repair.WORK_ID, source_sha256=payload["source_sha256"], source_epub_sha256=payload["source_epub_sha256"])
    if audit.get("source_epub_sha256") != payload["source_epub_sha256"]:
        raise ValueError("GA039 source audit belongs to a different EPUB")
    plans = {}
    for passage in payload["passages"]:
        plans[passage["id"]] = {"input_text_sha256": repair.sha(passage["text"]),
            "input_title_sha256": repair.sha(passage["title"]), "source_text_sha256": repair.sha(passage["source_text"])}
    if audit.get("input_passages") is not None and audit["input_passages"] != plans:
        raise ValueError("GA039 source audit original text/title/source inventory differs")
    review["input_passages"] = plans
    for kind in ("doc", "pdf"):
        source_path = review.get("sources", {}).get(kind + "_path")
        if source_path:
            review["original_" + kind + "_path"] = source_path
            review["original_" + kind + "_sha256"] = review["source_" + kind + "_sha256"]
    atoms = repair.SourceAtoms(repair.SOURCE, review["source_epub_sha256"])
    try:
        passages = repair.expanded_original(payload, review, atoms)
    finally:
        atoms.close()
    review["passage_order"] = [passage["id"] for passage in passages]
    original_headings = {str(item["original_number"]): item for item in review.get("all_main_letter_headings", []) + review.get("supplement_headings", [])}
    # The audit freezes input positions; the review freezes resulting positions.
    for heading in review["headings"]:
        pid, field = heading["passage_id"], heading["field"]
        heading["input_start_codepoint"] = heading["start_codepoint"]
        heading["input_end_codepoint"] = heading["end_codepoint"]
        original = original_headings.get(str(heading.get("original_number")))
        if original is not None and original.get("old_source_full_heading"):
            heading["old_source_full_heading"] = original["old_source_full_heading"]
            for key in ("pdf_line_witnesses", "pdf_raster_witnesses", "printed_prefix_transcription", "number_visually_verified"):
                if key in original:
                    heading[key] = deepcopy(original[key])
        elif not heading.get("old_source_full_heading"):
            atoms = repair.SourceAtoms(repair.SOURCE, review["source_epub_sha256"])
            try:
                heading["old_source_full_heading"] = repair.compact(" ".join(atoms.atom(witness)[1] for witness in heading["source_witnesses"]))
            finally:
                atoms.close()
        if field == "title":
            heading["start_codepoint"] = heading["end_codepoint"] = 0
        else:
            heading["start_codepoint"] = shifted_offset(pid, field, heading["start_codepoint"], review["repairs"])
            heading["end_codepoint"] = shifted_offset(pid, field, heading["end_codepoint"], review["repairs"])
    restored_inputs = {passage["id"]: deepcopy(passage) for passage in passages if passage["id"] not in plans}
    repair.apply_prefixes(passages, review["repairs"])
    lookup = {passage["id"]: passage for passage in passages}
    for heading in review["headings"]:
        passage = lookup[heading["passage_id"]]
        heading["label"] = passage["title"] if heading["field"] == "title" else passage["text"][heading["start_codepoint"]:heading["end_codepoint"]]
    review.pop("table_of_contents", None)
    toc, _ = repair.render_outline(passages, review)
    review["table_of_contents"] = toc
    review["output_table_of_contents_sha256"] = repair.object_digest(toc)
    for passage in passages:
        if passage["id"] in plans:
            plan = plans[passage["id"]]
            plan.update(output_text_sha256=repair.sha(passage["text"]), output_title_sha256=repair.sha(passage["title"]),
                        output_reading_blocks_sha256=repair.object_digest(passage["metadata"]["reading_blocks"]))
    for plan in review.get("source_restorations", []):
        passage = lookup[plan["id"]]
        original = restored_inputs[plan["id"]]
        plan.update(title=original["title"], text=original["text"], source_title=original["title"],
                    input_title_sha256=repair.sha(original["title"]), input_text_sha256=repair.sha(original["text"]),
                    output_title_sha256=repair.sha(passage["title"]), output_text_sha256=repair.sha(passage["text"]),
                    output_reading_blocks_sha256=repair.object_digest(passage["metadata"]["reading_blocks"]))
    review["source_restoration_count"] = len(review.get("source_restorations", []))
    review["letter_heading_count"] = sum(heading.get("original_number") is not None for heading in review["headings"])
    repair.check_source(review)
    repair._apply_original(payload, review)
    return review


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "server/priv")
    parser.add_argument("--audit", type=Path, default=AUDIT)
    parser.add_argument("--output", type=Path, default=repair.REVIEW)
    args = parser.parse_args()
    review = build_review(read_json(content_file(args.root, repair.WORK_ID)), read_json(args.audit))
    if args.output.exists() and read_json(args.output) != review:
        raise ValueError("Existing GA039 review differs; retain it before freezing a changed review")
    write_json(args.output, review)
    print(f"GA039: {review['letter_heading_count']} Originalbriefköpfe, {review['source_restoration_count']} Quellenrestaurationen eingefroren")
