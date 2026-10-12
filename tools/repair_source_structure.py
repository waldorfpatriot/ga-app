#!/usr/bin/env python3
"""Apply reviewed, edition-bound layout evidence without guessing at poetry.

Recipes describe source paragraph slices, their semantic role and explicit
evidenced text repairs. The engine is work-independent and standard-library
only. Source-layout acquisition lives in source_layout.py; uncertainty belongs
in review flags rather than an automatic correction. Offsets are UTF-16 for
the native reader, browser selections and EPUB exports.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import shutil

from finalize_library import content_file, read_json, write_json, normalize_text, verify

ROOT = Path(__file__).resolve().parents[1]
KINDS = {"heading", "verse", "prose", "attribution", "note"}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utf16(text):
    return len(text.encode("utf-16-le")) // 2


def recipe_digest(recipe):
    return sha(json.dumps(recipe, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def slice_part(blocks, part):
    if type(part) is int:
        return part, 0, len(blocks[part])
    index = part["block"]
    return index, part.get("start", 0), part.get("end", len(blocks[index]))


def page_position(raw, rendered, position):
    """Carry a source boundary through whitespace and evidenced text repairs."""
    if type(position) is not int or not 0 <= position <= len(raw):
        raise ValueError("Invalid source page position")
    if raw == rendered:
        while position < len(rendered) and rendered[position].isspace():
            position += 1
        return utf16(rendered[:position])
    translated = len(rendered)
    for tag, old_start, old_end, new_start, new_end in SequenceMatcher(None, raw, rendered, autojunk=False).get_opcodes():
        if old_start <= position < old_end:
            if tag == "equal":
                translated = new_start + position - old_start
            else:
                if old_start < position and raw[old_start:old_end].strip():
                    raise ValueError("Page boundary falls inside a lexical repair; explicit review required")
                translated = new_start
            break
    while translated < len(rendered) and rendered[translated].isspace():
        translated += 1
    return utf16(rendered[:translated])


def validate_layout(passage):
    """Reject overlaps, lost text, surrogate splits and bad note/page anchors."""
    text, metadata = passage["text"], passage.get("metadata", {})
    boundaries, position = {0: 0}, 0
    for index, character in enumerate(text, 1):
        position += utf16(character)
        boundaries[position] = index
    previous = 0
    for block in metadata.get("reading_blocks", []):
        start, end = block["start_offset"], block["end_offset"]
        if block["kind"] not in KINDS or start not in boundaries or end not in boundaries or not previous <= start < end:
            raise ValueError("Invalid reading block: " + passage["id"])
        if text[boundaries[previous]:boundaries[start]].strip():
            raise ValueError("Unclassified reading text: " + passage["id"])
        if block["kind"] == "heading" and not 1 <= block.get("level", 2) <= 6:
            raise ValueError("Invalid heading level")
        previous = end
    if metadata.get("reading_blocks") and text[boundaries[previous]:].strip():
        raise ValueError("Unclassified final text: " + passage["id"])
    sections = metadata.get("reading_sections", [])
    if not isinstance(sections, list) or any(not isinstance(section, dict) for section in sections):
        raise ValueError("Invalid independent work section inventory")
    block_starts = {block["start_offset"] for block in metadata.get("reading_blocks", [])}
    block_ends = {block["end_offset"] for block in metadata.get("reading_blocks", [])}
    previous, seen = 0, set()
    for section in sections:
        start, end = section.get("start_offset"), section.get("end_offset")
        if (not isinstance(section.get("id"), str) or not section["id"] or section["id"] in seen
                or not isinstance(section.get("title"), str) or not section["title"].strip()
                or section.get("label_kind") not in ("source_title", "incipit")
                or type(start) is not int or type(end) is not int
                or start not in block_starts or end not in block_ends or not previous <= start < end
                or text[boundaries[previous]:boundaries[start]].strip()):
            raise ValueError("Invalid independent work section: " + passage["id"])
        first = next(block for block in metadata["reading_blocks"] if block["start_offset"] == start)
        source_label = text[boundaries[start]:boundaries[first["end_offset"]]].split("\n", 1)[0]
        if section["label_kind"] == "incipit":
            if first["kind"] != "verse" or section["title"] != source_label:
                raise ValueError("Work incipit differs from its actual first verse")
        elif not (start == 0 and section["title"] == passage["title"] or
                  first["kind"] == "heading" and section["title"] == source_label):
            raise ValueError("Work title differs from its source heading")
        seen.add(section["id"])
        previous = end
    if sections and text[boundaries[previous]:].strip():
        raise ValueError("Unclassified final work section: " + passage["id"])
    for note in metadata.get("annotations", []):
        if "start_offset" not in note and "end_offset" not in note:
            continue
        start, end = note.get("start_offset"), note.get("end_offset")
        if start not in boundaries or end not in boundaries or not start < end or text[boundaries[start]:boundaries[end]] != note["marker"]:
            raise ValueError("Invalid footnote reference: " + passage["id"])
    previous_page, previous_offset = 0, 0
    for anchor in metadata.get("page_anchors", []):
        if type(anchor.get("page")) is not int or anchor["page"] < 1 or anchor.get("start_offset") not in boundaries:
            raise ValueError("Invalid page anchor: " + passage["id"])
        if anchor["page"] <= previous_page or anchor["start_offset"] < previous_offset:
            raise ValueError("Source pages or their text anchors are out of order: " + passage["id"])
        previous_page, previous_offset = anchor["page"], anchor["start_offset"]


def apply_passage_plan(passage, plan, revision):
    before = passage["text"]
    if plan.get("source_text_sha256") and sha(passage.get("source_text", "")) != plan["source_text_sha256"]:
        raise ValueError("Retained source differs from reviewed layout: " + passage["id"])
    if sha(before) == plan.get("output_sha256") and passage.get("metadata", {}).get("structure_revision") == revision:
        validate_layout(passage)
        return []
    if sha(before) != plan["input_sha256"]:
        raise ValueError("Unreviewed text/edition drift: " + passage["id"])
    original = before.split("\n\n")
    coverage = [[0] * len(block) for block in original]
    pieces, separators, layout, anchors, edits = [], [], [], [], []
    repair_counts = {repair["old"]: 0 for repair in plan.get("edits", [])}
    offset = 0

    def consume(part):
        index = part if type(part) is int else part["block"]
        if type(index) is not int or not 0 <= index < len(original):
            raise ValueError("Invalid source block: " + passage["id"])
        index, start, end = slice_part(original, part)
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(original[index]):
            raise ValueError("Invalid source slice: " + passage["id"])
        for character in range(start, end):
            coverage[index][character] += 1
        return original[index][start:end]

    for omitted in plan.get("omitted_parts", []):
        token = consume(omitted)
        exact_furniture = (omitted.get("kind") in {"running_header", "page_footer"}
                           and sha(token) == omitted.get("text_sha256"))
        if (not (exact_furniture or re.fullmatch(r"[\d '\"’.,]+", token))
                or not omitted.get("evidence") or type(omitted.get("page")) is not int
                or omitted["page"] < 1):
            raise ValueError("Only exact, evidenced page furniture may be omitted")
        edits.append({"original": token, "word": "", "count": 1, "evidence": omitted["evidence"], "page": omitted["page"]})
    for segment in plan["segments"]:
        kind, join = segment["kind"], segment.get("join", "\n")
        separator = segment.get("separator", "\n\n") if pieces else ""
        if kind not in KINDS or join not in {" ", "\n"} or separator not in {"", "\n", "\n\n"}:
            raise ValueError("Invalid semantic source segment")
        parts = [consume(part) for part in segment["parts"]]
        preserve_lines = segment.get("preserve_lines", False)
        if preserve_lines and kind not in {"verse", "note"}:
            raise ValueError("Preserved physical lines require a reviewed verse or source list")
        rendered = join.join(re.sub(r"\s*\n\s*", " ", part) if kind in {"prose", "heading", "attribution", "note"} and not preserve_lines else part for part in parts)
        raw = rendered
        page_positions = []
        for cue in segment.get("page_evidence", []):
            part_index, position = cue.get("part_index", 0), cue.get("start_codepoint", 0)
            if type(part_index) is not int or not 0 <= part_index < len(parts) or type(position) is not int or not 0 <= position < len(parts[part_index]):
                raise ValueError("Invalid source page slice")
            transform = (lambda text: re.sub(r"\s*\n\s*", " ", text)) if kind != "verse" and not preserve_lines else (lambda text: text)
            prefix = join.join(transform(part) for part in parts[:part_index])
            point = len(prefix) + (len(join) if part_index else 0) + len(transform(parts[part_index][:position]))
            page_positions.append(point)
        for repair in plan.get("edits", []):
            if not repair.get("old") or not repair.get("evidence"):
                raise ValueError("A lexical repair requires an exact source token and evidence")
            if repair.get("kind") == "source_heading_restoration":
                if not segment["parts"]:
                    continue
                first = segment["parts"][0]
                block = first if type(first) is int else first["block"]
                point = sum(len(value) + 2 for value in original[:block]) + (0 if type(first) is int else first.get("start", 0))
                if kind != "heading" or point != repair.get("heading_start_codepoint"):
                    continue
            pattern = re.compile(r"(?<!\w)" + re.escape(repair["old"]) + r"(?!\w)") if repair.get("match_word_boundaries") else None
            count = len(pattern.findall(rendered)) if pattern else rendered.count(repair["old"])
            if count:
                repair_counts[repair["old"]] += count
                if not repair.get("evidence"):
                    raise ValueError("A lexical repair requires source evidence")
                rendered = pattern.sub(lambda _:repair["new"], rendered) if pattern else rendered.replace(repair["old"], repair["new"])
                edits.append({"original": repair["old"], "word": repair["new"], "count": count, "evidence": repair["evidence"]})
        if plan.get("typographic_dashes"):
            rendered, count = re.subn(r"(?<!\S)-(?!\S)", "–", rendered)
            if count:
                edits.append({"original": "-", "word": "–", "count": count, "evidence": plan["typographic_dashes"]})
        # This normalization is performed before building any anchored offsets.
        rendered, inline_pages = normalize_text(rendered)
        if inline_pages:
            raise ValueError("Unreviewed inline page marker in source segment")
        if not rendered:
            continue
        offset += len(separator)
        start = offset
        offset += utf16(rendered)
        block = {"kind": kind, "start_offset": start, "end_offset": offset}
        if kind == "heading":
            block["level"] = segment.get("level", 2)
        if segment.get("poem_start"):
            block["poem_start"] = True
        layout.append(block)
        for page in segment.get("pages", []):
            anchors.append({"page": page, "start_offset": start, "source": "original_doc_page_footer"})
        for cue, position in zip(segment.get("page_evidence", []), page_positions):
            anchors.append({"page": cue["page"], "start_offset": start + page_position(raw, rendered, position), "source": cue.get("source", "original_doc_page_footer"), "confidence": cue["confidence"], "source_section": cue["source_section"]})
        pieces.append(rendered)
        separators.append(separator)
    if any(count == 0 for count in repair_counts.values()):
        missing = [token for token,count in repair_counts.items() if not count]
        raise ValueError("Reviewed repair no longer matches its exact source context: " + passage["id"] + " " + repr(missing))
    for index, block in enumerate(original):
        if any(count != 1 and not char.isspace() for char, count in zip(block, coverage[index])):
            raise ValueError(f"Lost or duplicated source characters: {passage['id']} block {index}")
    text = "".join(separator + piece for separator, piece in zip(separators, pieces))
    if plan.get("output_sha256") and sha(text) != plan["output_sha256"]:
        raise ValueError("Reviewed output checksum mismatch: " + passage["id"])
    passage["text"], passage["checksum"] = text, sha(text)
    if plan.get("title"):
        passage["title"] = plan["title"]
    metadata = passage.setdefault("metadata", {})
    metadata.update(reading_blocks=layout, group_title=plan["group_title"], structure_revision=revision)
    if plan.get("sections"):
        if len(layout) != len(plan["segments"]):
            raise ValueError("Empty segments cannot anchor independent works")
        sections, previous_segment = [], 0
        for index, section in enumerate(plan["sections"]):
            start, end = section.get("start_segment"), section.get("end_segment")
            if (type(start) is not int or type(end) is not int or start != previous_segment
                    or not start < end <= len(layout) or not section.get("evidence")):
                raise ValueError("Independent work sections require complete, evidenced segment ranges")
            sections.append({"id": passage["id"] if not index else f"{passage['id']}-section-{index + 1}",
                             "title": section["title"], "label_kind": section["label_kind"],
                             "start_offset": layout[start]["start_offset"], "end_offset": layout[end - 1]["end_offset"]})
            previous_segment = end
        if previous_segment != len(layout):
            raise ValueError("Independent work sections do not cover the whole passage")
        metadata["reading_sections"] = sections
    if anchors:
        # Consecutive blocks on one page need a single navigation anchor.
        metadata["page_anchors"] = []
        for anchor in anchors:
            if not metadata["page_anchors"] or metadata["page_anchors"][-1]["page"] != anchor["page"]:
                metadata["page_anchors"].append(anchor)
        pages = list(dict.fromkeys(a["page"] for a in anchors))
        metadata["page_numbers"] = pages
        metadata["page_marker_source"] = plan.get("page_marker_source", "source_bound_original_doc_page_footers")
        passage["ga_page"] = f"S. {min(pages)}" if len(pages) == 1 else f"S. {min(pages)}–{max(pages)}"
    for note in metadata.get("annotations", []):
        definition = plan.get("annotations", {}).get(note["id"])
        if not definition:
            raise ValueError("Unreviewed source note: " + note["id"])
        note.setdefault("source_text", note["text"])
        note["text"] = definition["text"]
        context = definition["reference_context"]
        if text.count(context) != 1:
            raise ValueError("Ambiguous footnote reference: " + note["id"])
        context_start = text.index(context)
        marker_start = context_start + context.rindex(note["marker"])
        note["start_offset"] = utf16(text[:marker_start])
        note["end_offset"] = note["start_offset"] + utf16(note["marker"])
    validate_layout(passage)
    return [{"passage_id": passage["id"], "rule": "source_layout", "label": "Quellengebundene Gliederung, Versabsätze und Metadaten wiederhergestellt", "count": 1,
             "before_excerpt": before[:440], "after_excerpt": text[:440], "replacements": edits, "layout_blocks": len(layout)}]


def build_toc(payload):
    toc, group_id = [], None
    for passage in payload["passages"]:
        group = passage["metadata"]["group_title"]
        if not toc or group != next(entry["title"] for entry in toc if entry["id"] == group_id):
            group_id = f"{payload['work_id']}-part-{sum(e['level'] == 1 for e in toc) + 1}"
            toc.append({"id": group_id, "title": group, "level": 1, "passage_id": passage["id"], "start_offset": 0, "parent_id": None})
        sections = passage["metadata"].get("reading_sections") or [{"id": passage["id"], "title": passage["title"], "start_offset": 0, "end_offset": utf16(passage["text"])}]
        for section in sections:
            toc.append({"id": section["id"], "title": section["title"], "level": 2, "passage_id": passage["id"], "start_offset": section["start_offset"], "parent_id": group_id})
            parents = {1: group_id, 2: section["id"]}
            headings = []
            for index, block in enumerate(passage["metadata"]["reading_blocks"]):
                if block["kind"] != "heading" or not section["start_offset"] <= block["start_offset"] < section["end_offset"]:
                    continue
                text = passage["text"].encode("utf-16-le")[2 * block["start_offset"]:2 * block["end_offset"]].decode("utf-16-le")
                if passage["metadata"].get("reading_sections") and block["start_offset"] == section["start_offset"] and text == section["title"]:
                    continue
                headings.append((index, block, text))
            minimum = min((block.get("level", 2) for _, block, _ in headings), default=1)
            for index, block, text in headings:
                level = block.get("level", 2) - minimum + 3 if passage["metadata"].get("reading_sections") else block.get("level", 2) + 2
                parent = parents[max(p for p in parents if p < level)]
                identifier = f"{passage['id']}-heading-{index + 1}"
                toc.append({"id": identifier, "title": text, "level": level, "passage_id": passage["id"], "start_offset": block["start_offset"], "parent_id": parent})
                parents = {key: value for key, value in parents.items() if key < level}
                parents[level] = identifier
    payload["table_of_contents"] = toc


def apply_recipe(payload, recipe):
    """Return an independent corrected payload and auditable per-passage events."""
    if payload["work_id"] != recipe["work_id"] or any(payload.get(key) != recipe[key] for key in ("source_sha256", "source_epub_sha256")):
        raise ValueError("Source identity/hash differs from the reviewed layout recipe")
    if list(recipe["passages"]) != [p["id"] for p in payload["passages"]]:
        raise ValueError("Layout recipe does not cover the exact original passage sequence")
    result, changes = deepcopy(payload), []
    revision = recipe_digest(recipe)
    for passage in result["passages"]:
        changes.extend(apply_passage_plan(passage, recipe["passages"][passage["id"]], revision))
    build_toc(result)
    if "table_of_contents" in recipe:
        from repair_early_structure import validate_outline
        result["table_of_contents"] = deepcopy(recipe["table_of_contents"])
        validate_outline(result, result["table_of_contents"])
    result.setdefault("metadata", {})["source_layout"] = {"recipe_sha256": revision, "source_sha256": recipe["source_sha256"], "source_url": recipe["source_url"], "offset_unit": "utf16", "review_scope": "structure_and_evidenced_repairs"}
    return result, changes


def stage(root, output, recipe, layout_baseline=None, preserved_input_sha256=None):
    from proofread_library import complete_stage
    if output.exists():
        raise ValueError("Choose a fresh stage; existing results are retained")
    for folder in ("content", "library", "proofreading"):
        shutil.copytree(root / folder, output / folder)
    path = content_file(output, recipe["work_id"])
    detail_path = output / "proofreading/works" / (recipe["work_id"] + ".json")
    detail = read_json(detail_path)
    current = read_json(path)
    current_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    previous_revision = current.get("metadata", {}).get("source_layout", {}).get("recipe_sha256")
    source = current
    baseline_hash = detail["work"].get("layout_input_sha256", detail["work"].get("application_base_sha256"))
    if preserved_input_sha256 is not None:
        baseline = content_file(layout_baseline or ROOT / "research/proofreading-layout-baseline", recipe["work_id"])
        actual_input_hash = hashlib.sha256(baseline.read_bytes()).hexdigest()
        if actual_input_hash != preserved_input_sha256 or read_json(baseline) != source:
            raise ValueError("Preserved layout input hash/payload differs from the supplied baseline")
        baseline_hash = actual_input_hash
    if previous_revision and previous_revision != recipe_digest(recipe):
        if current_hash != detail["work"]["after_sha256"]:
            raise ValueError("Structured content differs from its saved ledger; revision refused")
        baseline = content_file(layout_baseline or ROOT / "research/proofreading-layout-baseline", recipe["work_id"])
        baseline_hash = hashlib.sha256(baseline.read_bytes()).hexdigest()
        source = read_json(baseline)
        if list((p["id"],p.get("source_text")) for p in source["passages"]) != list((p["id"],p.get("source_text")) for p in current["passages"]):
            raise ValueError("Revision baseline does not preserve the current original source and passage inventory")
        if detail["work"].get("layout_input_sha256", detail["work"].get("application_base_sha256")) != baseline_hash:
            raise ValueError("Revision baseline hash differs from the preserved structural input")
        superseded = [event for event in detail["changes"] if event["rule"] == "source_layout"]
        detail.setdefault("structure_history", []).append({"recipe_sha256":previous_revision,"result_sha256":current_hash,"changes":superseded})
        detail["changes"] = [event for event in detail["changes"] if event["rule"] != "source_layout"]
    payload, changes = apply_recipe(source, recipe)
    write_json(path, payload)
    catalog_path = output / "library/catalog.json"
    catalog = read_json(catalog_path)
    work = next(w for w in catalog["works"] if w["id"] == payload["work_id"])
    for summary, passage in zip(work["passages"], payload["passages"]):
        summary.update(title=passage["title"], checksum=passage["checksum"], ga_page=passage["ga_page"])
    write_json(catalog_path, catalog)
    detail["changes"].extend(changes)
    if changes:
        detail["work"]["application_base_sha256"] = hashlib.sha256(content_file(root, recipe["work_id"]).read_bytes()).hexdigest()
        detail["work"]["layout_input_sha256"] = baseline_hash or detail["work"]["application_base_sha256"]
    detail["work"]["after_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    check = "Quellengebundene Gliederung vollständig; UTF-16-Anker und Fußnoten geprüft"
    if check not in detail["work"].setdefault("checks", []):
        detail["work"]["checks"].append(check)
    write_json(detail_path, detail)
    generated_at = None if changes else read_json(output / "proofreading/catalog.json").get("generated_at")
    complete_stage(output, generated_at=generated_at)
    verify(output)
    return changes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, default=ROOT / "tools/ga040_structure.json")
    parser.add_argument("--root", type=Path, default=ROOT / "server/priv")
    parser.add_argument("--layout-baseline", type=Path, default=ROOT / "research/proofreading-layout-baseline")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    changes = stage(args.root, args.output, read_json(args.recipe), args.layout_baseline)
    if args.apply:
        from proofread_library import apply_stage
        apply_stage(args.root, args.output)
    print(json.dumps({"work": read_json(args.recipe)["work_id"], "changed_passages": len(changes), "stage": str(args.output)}, ensure_ascii=False))
