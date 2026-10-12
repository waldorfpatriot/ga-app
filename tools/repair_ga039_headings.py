#!/usr/bin/env python3
"""Stage frozen GA039 original letter prefixes, source restorations and headings."""
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
from repair_source_structure import validate_layout

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "tools/ga039_heading_review.json"
SOURCE = ROOT / "research/proofreading-sources/ga-039.epub"
BASELINE = ROOT / "research/proofreading-ga039-heading-baseline"
WORK_ID = "ga-039"
ORIGINAL_PASSAGE_COUNT = 102
MAIN_NUMBERS = tuple(str(number) for number in range(253, 652))
SUPPLEMENT_NUMBERS = ("74a", "74b", "637a", "637b")
RULE = "source_letter_headings"
LABEL = "GA 039: Originalbriefnummern und Briefüberschriften quellengebunden hergestellt"
RESTORATION_LABEL = "GA 039: im Import ausgelassenen Originalbrief quellengebunden wiederhergestellt"
CHECK = "GA 039: Originalbriefnummern, Briefköpfe und ausgelassene Originalbriefe an Originalquellen geprüft"
MARKER = "source_letter_heading_review"
_PREFIX = re.compile(r"[0-9IilOoSyjz$°^, .\-]+")
_NEW_PREFIX = re.compile(r"(\d{2,3}[ab]?)\.")
_BR = "\ufdd0"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(text):
    return digest(text.encode("utf-8"))


def object_digest(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


review_digest = object_digest


def utf16(text):
    return len(text.encode("utf-16-le")) // 2


def compact(text):
    return re.sub(r"\s+", " ", text).strip()


class SourceAtoms:
    """Read exact reviewed atoms; never search for a similar paragraph."""

    def __init__(self, source, expected_sha):
        source = Path(source)
        if digest(source.read_bytes()) != expected_sha:
            raise ValueError("GA039 original EPUB byte hash differs")
        self.archive = ZipFile(source)
        self.members = {}

    def close(self):
        self.archive.close()

    def atom(self, witness):
        member = witness.get("source_member")
        if member not in self.members:
            raw = self.archive.read(member)
            body = ET.fromstring(raw).find("{http://www.w3.org/1999/xhtml}body")
            if body is None:
                raise ValueError("GA039 original EPUB body is missing")
            self.members[member] = (digest(raw), body)
        checksum, body = self.members[member]
        if witness.get("member_sha256") != checksum:
            raise ValueError("GA039 original source member hash differs")
        index, path = witness.get("body_index"), witness.get("child_path", [])
        if type(index) is not int or not 0 <= index < len(body) or not isinstance(path, list):
            raise ValueError("GA039 invalid source atom selector")
        atom = body[index]
        for child in path:
            if type(child) is not int or not 0 <= child < len(atom):
                raise ValueError("GA039 invalid source child selector")
            atom = atom[child]
        raw = "".join(atom.itertext())
        if sha(raw) != witness.get("source_paragraph_sha256"):
            raise ValueError("GA039 original source atom hash differs")
        selected = witness.get("rawitertext_slice")
        if selected is not None:
            start, end = selected.get("start_codepoint"), selected.get("end_codepoint")
            if (member != "EPUB/chapter-0004.xhtml" or index != 218 or path not in ([], [0])
                    or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(raw)):
                raise ValueError("GA039 raw source slice is outside the two reviewed318/319 boundaries")
            part = raw[start:end]
            valid_header = path == [] and end == len(raw) and raw[:start].strip() == "Rudolf Steiner" and part.startswith("319.")
            valid_footer = path == [0] and start == 0 and part.strip() == "Rudolf Steiner" and raw[end:].lstrip().startswith("319.")
            if not (valid_header or valid_footer) or sha(part) != selected.get("text_sha256"):
                raise ValueError("GA039 exact original318/319 raw boundary differs")
            raw = part
        return atom, raw


def xml_text(atom):
    """Keep explicit BRs separate from physical XML formatting whitespace."""
    parts = [atom.text or ""]
    for child in atom:
        if child.tag.rsplit("}", 1)[-1].lower() == "br":
            parts.append(_BR)
        else:
            parts.append(xml_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def render_segment(atom, plan):
    mode = plan.get("mode", "paragraph")
    if plan.get("rawitertext_slice") is not None:
        selected = plan["rawitertext_slice"]
        raw = "".join(atom.itertext())
        if mode != "paragraph":
            raise ValueError("GA039 reviewed source footer slice requires prose whitespace collapse")
        return compact(raw[selected["start_codepoint"]:selected["end_codepoint"]])
    if mode == "literal":
        literal = atom.tag.rsplit("}", 1)[-1].lower() == "pre" or atom.get("{http://www.w3.org/XML/1998/namespace}space") == "preserve"
        if not literal and not plan.get("literal_css_witness"):
            raise ValueError("GA039 literal paragraph has no original whitespace witness")
        return xml_text(atom).replace(_BR, "\n").strip("\r\n")
    if mode not in ("paragraph", "br"):
        raise ValueError("GA039 unknown source paragraph mode")
    text = xml_text(atom)
    if _BR in text and mode != "br":
        raise ValueError("GA039 explicit original BR requires its semantic mode")
    if mode == "br":
        return "\n".join(compact(line) for line in text.split(_BR)).strip()
    return compact(text)


def restoration_passage(plan, atoms):
    if plan.get("source_join") != "double_newline" or not plan.get("source_segments"):
        raise ValueError("GA039 restoration has no exact original segment join")
    original_number = plan.get("original_number")
    if plan.get("id") != WORK_ID + "-source-letter-" + str(original_number):
        raise ValueError("GA039 restored passage ID differs from its original letter number")
    heading, raw_heading = atoms.atom(plan["heading_source_witness"])
    title = compact(raw_heading)
    if title != plan.get("source_title", plan.get("title")) or title != plan.get("title", title):
        raise ValueError("GA039 restoration title differs from its physical heading")
    source_parts, readable_parts, ordinals = [], [], []
    for segment in plan["source_segments"]:
        atom, raw = atoms.atom(segment)
        source_parts.append(raw)
        part = render_segment(atom, segment)
        marker = segment.get("list_marker")
        if marker is not None:
            ordinal = validate_list_marker(plan, segment, marker, atoms)
            ordinals.append(ordinal)
            part = f"{ordinal}. " + part
        readable_parts.append(part)
    if str(original_number) == "356" and sorted(ordinals) != [1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12]:
        raise ValueError("GA039 original letter356 list-marker inventory differs")
    source_text = "\n\n".join(source_parts).strip()
    text = "\n\n".join(part for part in readable_parts if part).strip()
    if source_text != plan.get("source_text") or sha(source_text) != plan.get("source_text_sha256"):
        raise ValueError("GA039 restored raw source join differs")
    if text != plan.get("input_text", plan.get("text", text)):
        raise ValueError("GA039 restored readable body differs from its source paragraphs")
    if (plan.get("input_title_sha256", sha(title)) != sha(title)
            or plan.get("input_text_sha256", sha(text)) != sha(text)):
        raise ValueError("GA039 restored input title/body hashes differ")
    return {"id": plan["id"], "title": title, "text": text, "source_text": source_text,
            "source_label": "Vorhandene GA-Arbeitsausgabe / Kutscherei", "source_member": plan["source_member"],
            "checksum": sha(text), "ga_page": None,
            "metadata": {"page_numbers": [], "page_marker_source": "reviewed_original_letter_source", "annotations": []}}


def validate_list_marker(plan, segment, marker, atoms):
    ordinal, index = marker.get("ordinal"), marker.get("item_index")
    parent_witness = marker.get("parent_source_witness")
    if (str(plan.get("original_number")) != "356" or type(ordinal) is not int
            or ordinal not in (1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12)
            or type(index) is not int or index < 0 or not isinstance(parent_witness, dict)
            or not marker.get("evidence") or not marker.get("pdf_raster_witnesses")
            or not marker.get("pdf_line_witnesses")):
        raise ValueError("GA039 original list marker is not a reviewed letter356 source ordinal")
    parent, _ = atoms.atom(parent_witness)
    prefix = parent_witness.get("child_path", []) + [index]
    if (parent.tag.rsplit("}", 1)[-1].lower() != "ol" or index >= len(parent)
            or parent[index].tag.rsplit("}", 1)[-1].lower() != "li"
            or segment.get("source_member") != parent_witness.get("source_member")
            or segment.get("body_index") != parent_witness.get("body_index")
            or segment.get("child_path", [])[:len(prefix)] != prefix):
        raise ValueError("GA039 ordinal differs from its exact original OL/LI identity")
    return ordinal


def validate_replacement(repair):
    field, old, new = repair.get("field"), repair.get("old"), repair.get("new")
    offset = repair.get("start_codepoint")
    if (field not in ("title", "text") or not isinstance(old, str) or not old or not isinstance(new, str)
            or old == new or type(offset) is not int or offset < 0
            or type(repair.get("count")) is not int or repair["count"] != 1
            or not repair.get("source_witnesses") or not repair.get("evidence")):
        raise ValueError("GA039 repair is not an evidenced exact heading replacement")
    if repair.get("kind") == "source_editorial_label":
        if field != "title" or offset != 0 or new != "Verzeichnis der Briefe" or repair.get("passage_id") != "ga-039-doc-heading-113":
            raise ValueError("GA039 editorial label repair is not the retained original directory fragment")
        return
    old_prefix, new_prefix = repair.get("old_prefix", old), repair.get("new_prefix", new)
    match = _NEW_PREFIX.fullmatch(new_prefix)
    if (not _PREFIX.fullmatch(old_prefix) or match is None
            or match[1] != str(repair.get("corrected_number"))
            or match[1] not in MAIN_NUMBERS + SUPPLEMENT_NUMBERS
            or not old.startswith(old_prefix) or new != new_prefix + old[len(old_prefix):]):
        raise ValueError("GA039 replacement changes more than an original letter prefix")


def check_source(review, source=None):
    atoms = SourceAtoms(SOURCE if source is None else source, review.get("source_epub_sha256"))
    try:
        for repair in review.get("repairs", []):
            validate_replacement(repair)
            raws = [atoms.atom(witness)[1] for witness in repair["source_witnesses"]]
            source_heading = compact(" ".join(raws))
            if repair.get("kind") == "source_editorial_label":
                if source_heading.casefold() != repair["new"].casefold():
                    raise ValueError("GA039 editorial label differs from its physical original heading")
            elif not source_heading.startswith(compact(repair["old"])):
                raise ValueError("GA039 repaired prefix is absent from its physical source heading")
        for heading in review.get("headings", []):
            witnesses = heading.get("source_witnesses")
            if not witnesses:
                raise ValueError("GA039 heading has no physical original source identity")
            source_heading = compact(" ".join(atoms.atom(witness)[1] for witness in witnesses))
            expected = heading.get("old_source_full_heading")
            if not isinstance(expected, str) or not expected or not source_heading.startswith(compact(expected)):
                raise ValueError("GA039 original physical heading identity differs")
            number = heading.get("original_number")
            if number is not None and str(heading.get("reviewed_original_number", number)) != str(number):
                raise ValueError("GA039 reviewed original number differs")
        for restoration in review.get("source_restorations", []):
            restoration_passage(restoration, atoms)
    except (BadZipFile, KeyError, TypeError, ET.ParseError) as error:
        raise ValueError("GA039 original source witnesses cannot be read") from error
    finally:
        atoms.close()
    for kind in ("doc", "pdf"):
        path = review.get("original_" + kind + "_path")
        if path and digest((ROOT / path).read_bytes()) != review.get("original_" + kind + "_sha256"):
            raise ValueError("GA039 original " + kind.upper() + " byte hash differs")


def check_inventory(payload, review, *, original):
    plans = review.get("input_passages")
    expected_ids = list(plans) if original else review.get("passage_order")
    if (review.get("work_id") != WORK_ID or payload.get("work_id") != WORK_ID
            or not isinstance(plans, dict) or len(plans) != ORIGINAL_PASSAGE_COUNT
            or any(payload.get(key) != review.get(key) for key in ("source_sha256", "source_epub_sha256"))
            or [passage.get("id") for passage in payload.get("passages", [])] != expected_ids):
        raise ValueError("GA039 original source or passage inventory differs")
    restored = {plan["id"]: plan for plan in review.get("source_restorations", [])}
    for passage in payload["passages"]:
        plan = plans.get(passage["id"])
        if plan is not None:
            text_sha = plan["input_text_sha256" if original else "output_text_sha256"]
            title_sha = plan["input_title_sha256" if original else "output_title_sha256"]
        elif not original and passage["id"] in restored:
            plan = restored[passage["id"]]
            text_sha, title_sha = plan["output_text_sha256"], plan["output_title_sha256"]
        else:
            raise ValueError("GA039 unreviewed restored passage")
        if (sha(passage["text"]) != text_sha or passage.get("checksum") != text_sha
                or sha(passage["title"]) != title_sha or sha(passage["source_text"]) != plan["source_text_sha256"]):
            raise ValueError("GA039 reviewed title/text/source checksum differs: " + passage["id"])
        if not original and object_digest(passage["metadata"]["reading_blocks"]) != plan["output_reading_blocks_sha256"]:
            raise ValueError("GA039 reviewed reading-block hash differs")
    if not original and object_digest(payload.get("table_of_contents")) != review.get("output_table_of_contents_sha256"):
        raise ValueError("GA039 reviewed original table-of-contents hash differs")


def apply_prefixes(passages, repairs):
    lookup = {passage["id"]: passage for passage in passages}
    seen, targets = set(), set()
    for repair in repairs:
        validate_replacement(repair)
        rid, pid = repair.get("id"), repair.get("passage_id")
        target = (pid, repair["field"], repair["start_codepoint"])
        if not isinstance(rid, str) or not rid or rid in seen or target in targets or pid not in lookup:
            raise ValueError("GA039 duplicate or unreviewed replacement identity")
        seen.add(rid); targets.add(target)
    # Coordinates always refer to frozen input, even after a shorter prefix.
    for repair in sorted(repairs, key=lambda item: (item["passage_id"], item["field"], -item["start_codepoint"])):
        passage, field = lookup[repair["passage_id"]], repair["field"]
        offset, old = repair["start_codepoint"], repair["old"]
        text = passage[field]
        if text[offset:offset + len(old)] != old or (offset and text[:offset][-2:] != "\n\n"):
            raise ValueError("GA039 exact prefix offset/physical heading boundary differs: " + repair["id"])
        if repair.get("kind") == "source_editorial_label" and text != old:
            raise ValueError("GA039 editorial metadata repair differs from the whole original title")
        passage[field] = text[:offset] + repair["new"] + text[offset + len(old):]
    for passage in passages:
        passage["checksum"] = sha(passage["text"])


def expanded_original(payload, review, atoms):
    originals = deepcopy(payload["passages"])
    restored = [restoration_passage(plan, atoms) for plan in review.get("source_restorations", [])]
    for passage in restored:
        passage["source_label"] = originals[0]["source_label"]
    original_ids = {passage["id"] for passage in originals}
    after = {}
    for plan, passage in zip(review.get("source_restorations", []), restored):
        if plan.get("after_existing_pid") not in original_ids or passage["id"] in original_ids:
            raise ValueError("GA039 restored source placement differs")
        after.setdefault(plan["after_existing_pid"], []).append(passage)
    result = []
    for passage in originals:
        result.append(passage)
        result.extend(after.get(passage["id"], []))
    ids = [passage["id"] for passage in result]
    if len(ids) != len(set(ids)) or ids != review.get("passage_order", ids):
        raise ValueError("GA039 restored source order differs")
    return result


def reading_blocks(text, headings):
    ranges = sorted((heading["start_codepoint"], heading["end_codepoint"]) for heading in headings if heading["field"] == "text")
    previous = 0
    for start, end in ranges:
        if type(start) is not int or type(end) is not int or not previous <= start < end <= len(text):
            raise ValueError("GA039 heading range overlaps or exceeds its original text")
        previous = end
    blocks = []
    def prose(start, end):
        for match in re.finditer(r"\S(?:.*?\S)?(?=\n\n|$)", text[start:end], flags=re.S):
            a, b = start + match.start(), start + match.end()
            blocks.append({"kind": "prose", "start_offset": utf16(text[:a]), "end_offset": utf16(text[:b])})
    cursor = 0
    for start, end in ranges:
        prose(cursor, start)
        blocks.append({"kind": "heading", "start_offset": utf16(text[:start]), "end_offset": utf16(text[:end]), "level": 1})
        cursor = end
    prose(cursor, len(text))
    return blocks


def render_outline(passages, review):
    lookup = {passage["id"]: passage for passage in passages}
    indices = {pid: index for index, pid in enumerate(lookup)}
    numbers, identities, positions, by_passage, toc = [], set(), [], {}, []
    for heading in review.get("headings", []):
        pid, field = heading.get("passage_id"), heading.get("field")
        hid, label = heading.get("id"), heading.get("label")
        start, end = heading.get("start_codepoint"), heading.get("end_codepoint")
        if (pid not in lookup or field not in ("title", "text") or not isinstance(hid, str) or not hid or hid in identities
                or not isinstance(label, str) or not label.strip() or type(start) is not int or type(end) is not int):
            raise ValueError("GA039 original heading identity/range differs")
        passage = lookup[pid]
        if field == "title":
            if start != 0 or end != 0 or label != passage["title"]:
                raise ValueError("GA039 title heading differs from its preserved passage title")
            offset = 0
        else:
            if (not 0 <= start < end <= len(passage["text"]) or passage["text"][start:end] != label
                    or (start and passage["text"][start - 2:start] != "\n\n")
                    or (end < len(passage["text"]) and passage["text"][end:end + 2] != "\n\n")):
                raise ValueError("GA039 body heading differs from its exact original paragraph")
            offset = utf16(passage["text"][:start])
        physical_label = compact(heading.get("old_source_full_heading", ""))
        for replacement in review.get("repairs", []):
            if replacement["passage_id"] != pid or replacement["field"] != field:
                continue
            if replacement.get("kind") == "source_editorial_label":
                physical_label = replacement["new"]
            elif str(replacement.get("corrected_number")) == str(heading.get("original_number")):
                old_prefix = compact(replacement.get("old_prefix", replacement["old"]))
                if not physical_label.startswith(old_prefix):
                    raise ValueError("GA039 heading prefix differs from its physical original identity")
                physical_label = replacement.get("new_prefix", replacement["new"]) + physical_label[len(old_prefix):]
        if compact(label) != physical_label:
            raise ValueError("GA039 heading changes non-prefix source text")
        number = heading.get("original_number")
        if number is not None:
            number = str(number)
            if not label.startswith(number + ".") or number not in MAIN_NUMBERS + SUPPLEMENT_NUMBERS:
                raise ValueError("GA039 source letter number differs from its heading label")
            numbers.append(number)
        elif label.casefold() not in {"nachtrag zu den briefen", "nachtrag zu briefe i", "verzeichnis der briefe"}:
            raise ValueError("GA039 unreviewed editorial heading label")
        identities.add(hid); positions.append((indices[pid], 0 if field == "title" else start + 1))
        by_passage.setdefault(pid, []).append(heading)
        toc.append({"id": hid, "title": label, "passage_id": pid, "start_offset": offset, "level": 1,
                    "parent_id": None, "source_role": "letter" if number is not None else "table_of_contents"})
    if (positions != sorted(positions) or len(numbers) != len(set(numbers))
            or set(numbers) != set(MAIN_NUMBERS + SUPPLEMENT_NUMBERS)
            or [number for number in numbers if number in MAIN_NUMBERS] != list(MAIN_NUMBERS)):
        raise ValueError("GA039 original letter inventory, heading count or physical order differs")
    if review.get("all_main_letter_headings") is not None:
        original_numbers = [str(heading.get("original_number")) for heading in review["all_main_letter_headings"]]
        if original_numbers != list(MAIN_NUMBERS):
            raise ValueError("GA039 physical main-letter source inventory differs")
    for passage in passages:
        passage.setdefault("metadata", {})["reading_blocks"] = reading_blocks(passage["text"], by_passage.get(passage["id"], []))
        validate_layout(passage)
    if review.get("table_of_contents", toc) != toc:
        raise ValueError("GA039 frozen table of contents differs from its physical headings")
    return toc, by_passage


def _apply_original(payload, review):
    check_inventory(payload, review, original=True)
    result = deepcopy(payload)
    atoms = SourceAtoms(SOURCE, review["source_epub_sha256"])
    try:
        result["passages"] = expanded_original(payload, review, atoms)
    finally:
        atoms.close()
    apply_prefixes(result["passages"], review["repairs"])
    toc, headings = render_outline(result["passages"], review)
    result["table_of_contents"] = toc
    result["passage_count"] = len(result["passages"])
    revision = review_digest(review)
    marker = {"review_sha256": revision, "source_epub_sha256": review["source_epub_sha256"]}
    result.setdefault("metadata", {})[MARKER] = marker
    old_lookup = {passage["id"]: passage for passage in payload["passages"]}
    restorations = {plan["id"]: plan for plan in review.get("source_restorations", [])}
    events = []
    for passage in result["passages"]:
        pid = passage["id"]
        replacements = [deepcopy(repair) for repair in review["repairs"] if repair["passage_id"] == pid]
        common = {"passage_id": pid, "input_sha256": sha(old_lookup[pid]["text"]) if pid in old_lookup else sha(""),
                  "output_sha256": passage["checksum"], "input_title_sha256": sha(old_lookup[pid]["title"]) if pid in old_lookup else sha(""),
                  "output_title_sha256": sha(passage["title"]), "source_text_sha256": sha(passage["source_text"]),
                  "input_reading_blocks_sha256": object_digest(old_lookup[pid].get("metadata", {}).get("reading_blocks", [])) if pid in old_lookup else object_digest([]),
                  "output_reading_blocks_sha256": object_digest(passage["metadata"]["reading_blocks"]),
                  "input_table_of_contents_sha256": object_digest(payload.get("table_of_contents", [])),
                  "output_table_of_contents_sha256": object_digest(toc), "heading_count": len(headings.get(pid, [])),
                  "replacements": replacements, "before_excerpt": old_lookup[pid]["text"][:600] if pid in old_lookup else "",
                  "after_excerpt": passage["text"][:600]}
        if pid in restorations:
            plan = restorations[pid]
            passage["metadata"]["source_letter_restoration"] = {**marker, "original_number": plan["original_number"], "source_member": plan["source_member"]}
            events.append({**common, "rule": "source_restoration", "label": RESTORATION_LABEL, "count": 1,
                           "restoration_id": pid, "source_segments": deepcopy(plan["source_segments"]),
                           "heading_source_witness": deepcopy(plan["heading_source_witness"])})
        elif passage != old_lookup[pid]:
            events.append({**common, "rule": RULE, "label": LABEL, "count": max(1, len(replacements))})
    check_inventory(result, review, original=False)
    return result, events


def apply_review(payload, review=None):
    review = read_json(REVIEW) if review is None else review
    check_source(review)
    marker = payload.get("metadata", {}).get(MARKER)
    if marker is not None:
        expected_marker = {"review_sha256": review_digest(review), "source_epub_sha256": review["source_epub_sha256"]}
        if marker != expected_marker:
            raise ValueError("GA039 rendered revision differs from the frozen review")
        original = read_json(content_file(BASELINE, WORK_ID))
        expected, _ = _apply_original(original, review)
        if payload != expected:
            raise ValueError("GA039 rendered title/text/outline or unchanged metadata differs")
        return deepcopy(payload), []
    return _apply_original(payload, review)


def preserve_baseline(payload, baseline=BASELINE):
    path = Path(baseline) / "content/ga-039.json.gz"
    if path.exists():
        if read_json(path) != payload:
            raise ValueError("GA039 preserved original heading input differs")
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
    application_hash = digest(path.read_bytes())
    detail = read_json(root / "proofreading/works/ga-039.json")
    if application_hash != detail["work"]["after_sha256"]:
        raise ValueError("GA039 content differs from its correction ledger")
    current = read_json(path)
    check_source(review)
    if current.get("metadata", {}).get(MARKER) is not None:
        input_path = content_file(baseline, WORK_ID)
        input_hash = digest(input_path.read_bytes())
        if input_hash != detail["work"].get("ga039_heading_input_sha256"):
            raise ValueError("GA039 preserved original byte hash differs from its ledger")
        expected, _ = _apply_original(read_json(input_path), review)
        if current != expected:
            raise ValueError("GA039 repeated stage differs from the retained original/review")
        corrected, changes = deepcopy(current), []
    else:
        corrected, changes = _apply_original(current, review)
        input_hash = preserve_baseline(current, baseline)
    catalog = read_json(root / "library/catalog.json")
    entry = next(work for work in catalog["works"] if work["id"] == WORK_ID)
    if ([summary["id"] for summary in entry["passages"]] != [p["id"] for p in current["passages"]]
            or any(summary.get("checksum") != passage["checksum"] or summary.get("title") != passage["title"]
                   for summary, passage in zip(entry["passages"], current["passages"]))):
        raise ValueError("GA039 catalog passage inventory/title/checksums differ")
    other_hashes = {p.relative_to(root): digest(p.read_bytes()) for p in (root / "content").iterdir() if p.is_file() and p != path}
    for folder in ("content", "library", "proofreading"):
        shutil.copytree(root / folder, output / folder)
    staged = content_file(output, WORK_ID)
    if changes:
        write_json(staged, corrected)
        entry["passages"] = [{key: passage.get(key) for key in ("id", "title", "ga_page", "source_label", "checksum")} for passage in corrected["passages"]]
        entry["catalog_passage_count"] = len(corrected["passages"])
        write_json(output / "library/catalog.json", catalog)
        detail["changes"].extend(deepcopy(changes))
        detail["work"].update(application_base_sha256=application_hash, ga039_heading_input_sha256=input_hash,
                              after_sha256=digest(staged.read_bytes()), passage_count=len(corrected["passages"]))
        detail["letter_heading_review"] = deepcopy(corrected["metadata"][MARKER])
        if CHECK not in detail["work"].setdefault("checks", []):
            detail["work"]["checks"].append(CHECK)
        write_json(output / "proofreading/works/ga-039.json", detail)
    previous_date = read_json(output / "proofreading/catalog.json").get("generated_at")
    complete_stage(output, generated_at=None if changes else previous_date)
    verify(output)
    if any(digest((output / relative).read_bytes()) != checksum for relative, checksum in other_hashes.items()):
        raise ValueError("GA039 stage would change another content file")
    if read_json(staged) != corrected:
        raise ValueError("GA039 stage completion changed unreviewed text or metadata")
    return changes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "server/priv")
    parser.add_argument("--review", type=Path, default=REVIEW)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    changes = stage(args.root, args.output, read_json(args.review), args.baseline)
    print(f"GA 039: {len(changes)} belegte Briefnummern-/Gliederungsereignisse in {args.output}")
