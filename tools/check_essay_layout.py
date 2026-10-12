#!/usr/bin/env python3
"""Independently bind reviewed prose layout to retained original sources.

Source witnesses and offsets are reconstructed here without importing builders
or repair functions. The generic independent renderer is supplied by the caller.
"""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile

WORK_IDS = frozenset({"ga-033", "ga-034", "ga-035", "ga-036", "ga-045"})
FRONT_IDS = {"ga-033": {"ga-033-doc-heading-1", "ga-033-doc-heading-2"},
             "ga-034": {"ga-034-doc-heading-1", "ga-034-doc-heading-2"},
             "ga-035": set(), "ga-036": {"ga-036-doc-heading-1"}, "ga-045": set()}
LETTERS = "A-Za-zÄÖÜäöüß"
ROOT = Path(__file__).resolve().parents[1]
GA034_NOTE_JOINS = {
    "EPUB/chapter-0003.xhtml#sup-note-2": ([90], {"überwirk lichen": "überwirklichen", "Erschei nungen": "Erscheinungen", "Natur wissenschaft": "Naturwissenschaft"}),
    "EPUB/chapter-0003.xhtml#sup-note-3": ([90, 91], {"naturwissenschaft liche": "naturwissenschaftliche", "Trag weite": "Tragweite"}),
    "EPUB/chapter-0003.xhtml#sup-note-4": ([91], {"anthroposophi- schen": "anthroposophischen", "Ge heimlehre": "Geheimlehre"}),
    "EPUB/chapter-0004.xhtml#footnote-recovered-2": ([107], {"Wissen schaftlichkeit": "Wissenschaftlichkeit", "Auseinander setzungen": "Auseinandersetzungen", "wider sprechen": "widersprechen", "ge sehen": "gesehen"}),
    "EPUB/chapter-0012.xhtml#footnote-recovered-5": ([345], {"Emp findungswesen": "Empfindungswesen", "das selbe": "dasselbe", "Bio logen": "Biologen", "Empfin dung": "Empfindung"}),
    "EPUB/chapter-0012.xhtml#footnote-recovered-7": ([345], {"Geisteswissen schaft": "Geisteswissenschaft", "Geistes wissenschaft": "Geisteswissenschaft"}),
    "EPUB/chapter-0012.xhtml#footnote-recovered-8": ([345, 346], {"Zahn wechsel": "Zahnwechsel"}),
}
GA034_NOTE_IDS = frozenset(GA034_NOTE_JOINS) | frozenset({
    "EPUB/chapter-0002.xhtml#footnote-recovered-1", "EPUB/chapter-0008.xhtml#sup-note-1",
    "EPUB/chapter-0012.xhtml#footnote-recovered-3", "EPUB/chapter-0012.xhtml#footnote-recovered-4",
    "EPUB/chapter-0012.xhtml#footnote-recovered-6"})


def digest(value):
    return hashlib.sha256(value).hexdigest()


def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


@lru_cache(maxsize=96)
def original_page_raster(pdf, checksum, page):
    from check_proofreading_samples import pbm_raster
    with tempfile.TemporaryDirectory(prefix="essay-original-raster-") as temporary:
        prefix = Path(temporary) / "original"
        try:
            subprocess.run(["pdfimages", "-f", str(page), "-l", str(page), str(pdf), str(prefix)],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (OSError, subprocess.CalledProcessError) as error:
            raise ValueError("Cannot independently extract original printed pixels") from error
        files = list(Path(temporary).glob("original-*"))
        if len(files) != 1 or files[0].suffix != ".pbm":
            raise ValueError("Printed source witness has an unexpected original image inventory")
        return pbm_raster(files[0].read_bytes())


@lru_cache(maxsize=96)
def original_page_lines(pdf, checksum, page):
    try:
        result = subprocess.run(["pdftotext", "-f", str(page), "-l", str(page), "-bbox-layout", str(pdf), "-"],
                                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("Cannot independently extract printed source line geometry") from error
    root = ET.fromstring(result.stdout)
    return [(" ".join("".join(word.itertext()) for word in line),
             [float(line.get(key)) for key in ("xMin", "yMin", "xMax", "yMax")])
            for line in root.findall(".//{*}line")]


def inspect_pdf_witnesses(repair, review):
    rasters = repair.get("pdf_raster_witnesses", [])
    pairs = repair.get("pdf_line_pair_witnesses", [])
    if not rasters and not pairs:
        return
    path = Path(review.get("original_pdf_path", "research/proofreading-sources/" + review["work_id"] + "-original.pdf"))
    if not path.is_absolute():
        path = ROOT / path
    checksum = digest(path.read_bytes())
    if checksum != review["original_pdf_sha256"]:
        raise ValueError("Printed repair witness original PDF byte identity differs")
    for witness in rasters:
        page = witness.get("pdf_page")
        if (type(page) is not int or page < 1 or witness.get("page_index") != page - 1
                or witness.get("original_pdf_sha256") != checksum or witness.get("original_page_mode") != "1"
                or not witness.get("visible_page_pixels_sha256")):
            raise ValueError("Original printed raster witness lacks its exact page/visible pixel contract")
        width, height, raster = original_page_raster(path, checksum, page)
        if (witness.get("original_page_size") != [width, height]
                or witness["visible_page_pixels_sha256"] != digest(raster)):
            raise ValueError("Independently extracted original printed pixels differ")
    for witness in pairs:
        lines = original_page_lines(path, checksum, witness["pdf_page"])
        matches = [index for index, (text, box) in enumerate(lines)
                   if text == witness.get("pdf_line_before") and
                   all(abs(a - b) < .002 for a, b in zip(box, witness.get("line_before_bbox", [])))]
        if len(matches) != 1 or len(witness.get("line_before_bbox", [])) != 4:
            raise ValueError("Printed seam first line is not its exact original text/bounding box")
        index = matches[0] + 1
        if (index >= len(lines) or lines[index][0] != witness.get("pdf_line_after")
                or len(witness.get("line_after_bbox", [])) != 4
                or any(abs(a - b) >= .002 for a, b in zip(lines[index][1], witness["line_after_bbox"]))):
            raise ValueError("Printed seam continuation is not the next exact original line")
        left = re.search(r"([" + LETTERS + r"]+-)$", lines[index - 1][0])
        right = re.match(r"([" + LETTERS + r"]+)", lines[index][0])
        if not left or not right or left[1] + right[1] != re.sub(r"\s+", "", repair.get("old", "")):
            raise ValueError("Printed word seam differs from its two physical source line ends")


def inspect_essay_recovery(prior, recipe, review, events, source):
    """Reconstruct only GA033's six omitted Schopenhauer source paragraphs."""
    additions = recipe.get("source_additions", [])
    if not additions:
        annotation_ids = {addition["id"] for addition in recipe.get("annotation_additions", [])}
        if any(event["rule"] == "source_restoration" and event.get("addition_id") not in annotation_ids
               for items in events.values() for event in items):
            raise ValueError("Unexpected source restoration ledger")
        return deepcopy(prior)
    if prior["work_id"] == "ga-045":
        return inspect_ga045_text_recovery(prior, recipe, review, events, source)
    if prior["work_id"] == "ga-034":
        return inspect_ga034_text_recovery(prior, recipe, review, events, source)
    if (prior["work_id"] != "ga-033" or len(additions) != 1
            or additions != review.get("source_additions")
            or recipe.get("original_passages") != review.get("original_passages")):
        raise ValueError("Restoration exceeds the single omitted GA033 author subsection")
    identities = {p["id"]: {"input_sha256": digest(p["text"].encode()),
        "source_text_sha256": digest(p["source_text"].encode())} for p in prior["passages"]}
    if recipe["original_passages"] and all("title" in row for row in recipe["original_passages"].values()):
        for passage in prior["passages"]:
            identities[passage["id"]]["title"] = passage["title"]
    if recipe["original_passages"] != identities:
        raise ValueError("Restoration original passage identities differ")
    addition = additions[0]
    pid, member = "ga-033-schopenhauer-bibliographisches", "EPUB/chapter-0008.xhtml"
    spans = addition.get("source_segments", [])
    if (addition.get("kind") != "passage" or addition.get("passage_id") != pid
            or addition.get("source_role") != "author" or len(spans) != 1
            or spans[0].get("source_member") != member
            or spans[0].get("body_indices") != list(range(19, 25))
            or not addition.get("evidence") or not addition.get("id")
            or addition.get("reading_edits")
            or addition.get("source_pdf_pages") != [265, 266, 267, 268]):
        raise ValueError("Restoration exceeds the exact omitted Schopenhauer source span")
    marker = "\uE000"

    def reading_text(element):
        def collect(node):
            parts = [node.text or ""]
            for child in node:
                if child.get("role") != "doc-backlink":
                    parts.append(marker if child.tag.rsplit("}", 1)[-1] == "br" else collect(child))
                parts.append(child.tail or "")
            return "".join(parts)
        text = re.sub(r"[ \t\r\n\f]+", " ", collect(element))
        return re.sub(" *" + marker + " *", "\n", text).strip()

    with ZipFile(source) as archive:
        data = archive.read(member)
        if digest(data) != spans[0].get("member_sha256"):
            raise ValueError("Restored member byte identity differs")
        body = ET.fromstring(data).find("{http://www.w3.org/1999/xhtml}body")
        raw = "\n\n".join("".join(body[index].itertext()) for index in range(19, 25))
        text = "\n\n".join(reading_text(body[index]) for index in range(19, 25))
    if (addition.get("source_text") != raw or addition.get("text") != text
            or addition.get("source_text_sha256") != digest(raw.encode())
            or addition.get("text_sha256") != digest(text.encode())
            or " ".join(addition.get("title", "").split()).casefold()
                != "bibliographisches und textbehandlung"):
        raise ValueError("Restored text/title is not the exact original subsection")
    before_id = addition.get("insert_before_passage_id")
    if before_id not in identities or before_id != "ga-033-doc-heading-17":
        raise ValueError("Restoration differs from its original position before Jean Paul")
    expected_event = {"passage_id": pid, "rule": "source_restoration", "count": 1,
        "label": "Exakt belegten Originalquellentext wiederhergestellt", "addition_id": addition["id"],
        "source_text_sha256": addition["source_text_sha256"], "text_sha256": addition["text_sha256"],
        "before_excerpt": "", "after_excerpt": text[:440], "evidence": addition["evidence"]}
    actual = [dict(event, passage_id=key) for key, items in events.items() for event in items
              if event["rule"] == "source_restoration"]
    if actual != [expected_event]:
        raise ValueError("Exact author subsection restoration ledger differs")
    result = deepcopy(prior)
    repairs = recipe.get("proofing_repairs", {})
    if repairs != review.get("proofing_repairs", {}) or set(repairs) != {"excluded_sections"}:
        raise ValueError("Restoration lacks its exact original import-exclusion update")
    repair = repairs["excluded_sections"]
    excluded = result["proofing"].get("excluded_sections", [])
    author = {"member": member, "heading": "Bibliographisches und Textbehandlung", "id": None}
    if (repair.get("before") != excluded or excluded.count(author) != 1
            or repair.get("after") != [row for row in excluded if row != author]
            or repair.get("archive_as") != "source_import_excluded_sections" or not repair.get("evidence")
            or "source_import_excluded_sections" in result["proofing"]):
        raise ValueError("Restoration import exclusions exceed the one restored author subsection")
    result["proofing"]["source_import_excluded_sections"] = deepcopy(excluded)
    result["proofing"]["excluded_sections"] = deepcopy(repair["after"])
    proof = {key: deepcopy(addition[key]) for key in
             ("id", "source_segments", "source_text_sha256", "text_sha256", "evidence")}
    passage = {"id": pid, "title": addition["title"], "source_label": prior["passages"][0]["source_label"],
        "source_member": member, "text": text, "source_text": raw, "checksum": digest(text.encode()),
        "ga_page": None, "metadata": {"page_numbers": [], "page_marker_source": "epub_source_page_labels",
        "annotations": [], "source_role": "author", "source_restoration": proof}}
    index = next(index for index, passage in enumerate(result["passages"]) if passage["id"] == before_id)
    result["passages"].insert(index, passage)
    result["passage_count"] = len(result["passages"])
    return result


def inspect_ga034_text_recovery(prior, recipe, review, events, source):
    additions = recipe["source_additions"]
    identities = {p["id"]: {"input_sha256": digest(p["text"].encode()),
        "source_text_sha256": digest(p["source_text"].encode())} for p in prior["passages"]}
    if recipe.get("original_passages") and all("title" in row for row in recipe["original_passages"].values()):
        for passage in prior["passages"]:
            identities[passage["id"]]["title"] = passage["title"]
    if (len(additions) != 1 or additions != review.get("source_additions")
            or recipe.get("original_passages") != identities or review.get("original_passages") != identities):
        raise ValueError("GA034 restoration exceeds its one falsely imported prose heading")
    addition = additions[0]
    member, checksum = "EPUB/chapter-0010.xhtml", "11014b7127eb2ec4431c8c0ae6d730e69a306277989605c626363e744b70d7d4"
    expected_span = [{"source_member": member, "body_indices": [56], "member_sha256": checksum}]
    pid = "ga-034-doc-heading-9"
    target = next(passage for passage in prior["passages"] if passage["id"] == pid)
    if (addition.get("kind") != "text" or addition.get("passage_id") != pid
            or addition.get("source_segments") != expected_span or addition.get("source_pdf_pages") != [303]
            or addition.get("position_codepoint") != len(target["text"])
            or addition.get("preceding_anchor") != "Vorur-" or not target["text"].endswith("Vorur-")
            or not addition.get("id") or not addition.get("evidence")):
        raise ValueError("GA034 prose restoration differs from its exact final word seam/source selector")
    with ZipFile(source) as archive:
        data = archive.read(member)
        if digest(data) != checksum:
            raise ValueError("GA034 restored paragraph source member changed")
        element = ET.fromstring(data).find("{*}body")[56]
        raw = "".join(element.itertext())
    raw_hash = "2798f8e19366783de2ba8643ad1bc5db857a9b41a1280b88be7fc134f267af62"
    title = next(passage for passage in prior["passages"] if passage["id"] == "ga-034-doc-heading-10")["title"]
    if (digest(raw.encode()) != raw_hash or raw != title or addition.get("source_text") != raw
            or addition.get("text") != raw or addition.get("source_text_sha256") != raw_hash
            or addition.get("text_sha256") != raw_hash or element.tag.rsplit("}", 1)[-1] != "h2"):
        raise ValueError("GA034 recovered prose is not the exact author sentence mistaken for a title")
    expected_event = {"passage_id": pid, "rule": "source_restoration", "count": 1,
        "label": "Exakt belegten Originalquellentext wiederhergestellt", "addition_id": addition["id"],
        "source_text_sha256": raw_hash, "text_sha256": raw_hash, "before_excerpt": "",
        "after_excerpt": raw[:440], "evidence": addition["evidence"]}
    actual = [dict(event, passage_id=key) for key, items in events.items() for event in items if event["rule"] == "source_restoration"]
    if actual != [expected_event]:
        raise ValueError("GA034 author paragraph restoration ledger differs")
    result = deepcopy(prior)
    target = next(passage for passage in result["passages"] if passage["id"] == pid)
    target["text"] += "\n\n" + raw
    target["checksum"] = digest(target["text"].encode())
    target["metadata"]["source_restorations"] = [addition["id"]]
    return result


def inspect_ga045_text_recovery(prior, recipe, review, events, source):
    """Restore only the main paragraph falsely classified as source note nine."""
    identities = {p["id"]: {"input_sha256": digest(p["text"].encode()),
        "source_text_sha256": digest(p["source_text"].encode()), "title": p["title"]}
        for p in prior["passages"]}
    additions = recipe.get("source_additions", [])
    if (len(additions) != 1 or additions != review.get("source_additions")
            or identities != recipe.get("original_passages") or identities != review.get("original_passages")):
        raise ValueError("GA045 restoration exceeds its one omitted original main paragraph")
    addition = additions[0]
    pid, member = "ga-045-doc-heading-4", "EPUB/chapter-0002.xhtml"
    member_hash = "c2b6ba81c9eeef0c27ed006bdc15043a2018140e49557563f9e78f6b28e4a970"
    raw_hash = "c38db1cb287dceb4c1a6aa1db6208f5aa31985c38060e89fb2943717342a08fc"
    text_hash = "6e0e6dee3fac16f1e81d07865cf269ce19a09b96c249395b77b5c7ccacaddc50"
    target = next(p for p in prior["passages"] if p["id"] == pid)
    point = 15268
    if (addition.get("kind") != "text" or addition.get("passage_id") != pid
            or addition.get("id") != "ga045-restored-main-paragraph-59"
            or addition.get("source_segments") != [{"source_member": member, "body_indices": [46], "member_sha256": member_hash}]
            or addition.get("position_codepoint") != point
            or addition.get("preceding_anchor") != target["text"][point - 140:point]
            or addition.get("following_anchor") != target["text"][point:point + 140]
            or not target["text"][:point].endswith("\n\n")
            or not target["text"][point:].startswith("Der «Ich-Mensch» und der «astralische Mensch»")
            or addition.get("source_doc_paragraph_index") != 218
            or addition.get("source_doc_paragraph_sha256") != text_hash
            or not addition.get("evidence")):
        raise ValueError("GA045 restoration differs from its original paragraph and insertion position")
    with ZipFile(source) as archive:
        data = archive.read(member)
        if digest(data) != member_hash:
            raise ValueError("GA045 restored paragraph has a different EPUB member")
        element = ET.fromstring(data).find("{*}body")[46]
    raw = "".join(element.itertext())
    if (element.get("id") != "footnote-recovered-9" or element.get("role") != "doc-footnote"
            or digest(raw.encode()) != raw_hash):
        raise ValueError("GA045 recovered paragraph has different original source characters")
    pieces, removed = [], []
    def visit(node):
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "a" and node.get("role") == "doc-backlink":
            removed.append((node.get("href"), "".join(node.itertext())))
            return
        if tag == "br":
            pieces.append("\0")
            return
        if node.text:
            pieces.append(node.text)
        for child in node:
            visit(child)
            if child.tail:
                pieces.append(child.tail)
    visit(element)
    text = "\n".join(" ".join(line.split()) for line in "".join(pieces).split("\0")).strip()
    layout_path = Path(review["source_layout_path"])
    if not layout_path.is_absolute():
        layout_path = ROOT / layout_path
    if digest(layout_path.read_bytes()) != review["source_layout_sha256"]:
        raise ValueError("GA045 restoration original DOC layout changed")
    document_layout = read(layout_path)
    record = document_layout["paragraphs"][218]
    if (document_layout["source_doc_sha256"] != review["original_doc_sha256"]
            or record["index"] != 218 or record["text"] != text
            or digest(text.encode()) != text_hash
            or removed != [("chapter-9999.xhtml#noteref-recovered-9", " ↩")]
            or addition.get("source_text") != raw or addition.get("text") != text
            or addition.get("source_text_sha256") != raw_hash or addition.get("text_sha256") != text_hash):
        raise ValueError("GA045 recovery changes the original DOC paragraph or more than its spurious backlink")
    expected_event = {"passage_id": pid, "rule": "source_restoration", "count": 1,
        "label": "Exakt belegten Originalquellentext wiederhergestellt", "addition_id": addition["id"],
        "source_text_sha256": raw_hash, "text_sha256": text_hash, "before_excerpt": "",
        "after_excerpt": text[:440], "evidence": addition["evidence"]}
    actual = [dict(event, passage_id=key) for key, items in events.items() for event in items
              if event["rule"] == "source_restoration"]
    if actual != [expected_event]:
        raise ValueError("GA045 restored main paragraph ledger differs from its exact source")
    result = deepcopy(prior)
    target = next(p for p in result["passages"] if p["id"] == pid)
    target["text"] = target["text"][:point] + text + "\n\n" + target["text"][point:]
    target["checksum"] = digest(target["text"].encode())
    target["metadata"]["source_restorations"] = [addition["id"]]
    return result


def inspect_essay_annotation_recovery(prior, recipe, review, events, source):
    additions = recipe.get("annotation_additions", [])
    if not additions:
        return prior
    if prior["work_id"] != "ga-036" or additions != review.get("annotation_additions"):
        raise ValueError("Annotation restoration differs from its exact GA036 source review")
    selectors = {("EPUB/chapter-0006.xhtml", 66): (12, 63),
        ("EPUB/chapter-0009.xhtml", 27): (6, 24), ("EPUB/chapter-0009.xhtml", 41): (5, 37),
        ("EPUB/chapter-0009.xhtml", 110): (4, 105), ("EPUB/chapter-0009.xhtml", 127): (3, 125)}
    if len(additions) != len(selectors):
        raise ValueError("Annotation restoration exceeds the five omitted GA036 author notes")
    result = deepcopy(prior)
    passages = {passage["id"]: passage for passage in result["passages"]}
    selected, expected_events = set(), []
    member_order = {member: index for index, member in enumerate(review["source_members"])}
    with ZipFile(source) as archive:
        bodies = {}
        for member, checksum in review["source_members"].items():
            data = archive.read(member)
            if digest(data) != checksum:
                raise ValueError("Annotation original member byte identity differs")
            bodies[member] = ET.fromstring(data).find("{*}body")
        for addition in additions:
            spans = addition.get("source_segments", [])
            if addition.get("kind") != "annotation" or len(spans) != 1 or len(spans[0].get("body_indices", [])) != 1:
                raise ValueError("Annotation addition exceeds one exact original footnote element")
            member, index = spans[0]["source_member"], spans[0]["body_indices"][0]
            key = member, index
            if key not in selectors or key in selected or spans[0].get("member_sha256") != review["source_members"][member]:
                raise ValueError("Annotation restoration uses a different or duplicate original note")
            selected.add(key)
            number, reference_index = selectors[key]
            element = bodies[member][index]
            aid = member + "#footnote-recovered-" + str(number)
            raw = "".join(element.itertext())
            pid = addition["passage_id"]
            if (element.get("role") != "doc-footnote" or element.get("id") != aid.split("#", 1)[1]
                    or addition.get("annotation_id") != aid or addition.get("marker") != "*"
                    or addition.get("source_text") != raw or addition.get("text") != raw.strip()
                    or addition.get("source_text_sha256") != digest(raw.encode())
                    or addition.get("text_sha256") != digest(raw.strip().encode())
                    or not addition.get("id") or not addition.get("evidence") or pid not in passages):
                raise ValueError("Restored annotation is not the exact omitted original note")
            reference = addition.get("source_reference", {})
            paragraph = bodies[member][reference_index]
            reference_hash = digest("".join(paragraph.itertext()).encode())
            retained_reference = any(part.get("source_member") == member and part.get("body_index") == reference_index
                                     and part.get("source_paragraph_sha256") == reference_hash
                                     for part in review["passages"][pid]["source_parts"])
            heading_witness = reference.get("source_heading_witness")
            heading_ids = {("EPUB/chapter-0006.xhtml", 63): "ga-036-doc-heading-35",
                           ("EPUB/chapter-0009.xhtml", 24): "ga-036-doc-heading-47",
                           ("EPUB/chapter-0009.xhtml", 37): "ga-036-doc-heading-48",
                           ("EPUB/chapter-0009.xhtml", 105): "ga-036-doc-heading-52",
                           ("EPUB/chapter-0009.xhtml", 125): "ga-036-doc-heading-53"}
            if heading_witness is not None:
                if (heading_witness != {"source_member": member, "body_index": reference_index,
                                        "source_paragraph_sha256": reference_hash}
                        or heading_ids.get((member, reference_index)) != pid
                        or paragraph.tag.rsplit("}", 1)[-1] != "h2"
                        or "".join(paragraph.itertext()) != passages[pid]["title"]):
                    raise ValueError("Restored note title reference differs from its exact imported original heading")
                retained_reference = True
            if (reference.get("source_member") != member or reference.get("body_index") != reference_index
                    or reference.get("source_paragraph_sha256") != reference_hash
                    or reference.get("reference_id") != "noteref-recovered-" + str(number)
                    or not retained_reference):
                raise ValueError("Restored note reference is outside its retained original author passage")
            links = [link for link in paragraph.findall(".//{*}a")
                     if link.get("id") == reference["reference_id"]]
            if (len(links) != 1 or links[0].get("role") != "doc-noteref"
                    or not links[0].get("href", "").endswith("#" + element.get("id"))
                    or "".join(links[0].itertext()) != "*"):
                raise ValueError("Restored original footnote link/marker differs")
            notes = passages[pid]["metadata"]["annotations"]
            if any(note["id"] == aid for note in notes):
                raise ValueError("Restored footnote already exists in the retained inventory")
            proof = {field: deepcopy(addition[field]) for field in
                     ("id", "source_segments", "source_text_sha256", "text_sha256", "evidence")}
            notes.append({"id": aid, "marker": "*", "text": raw.strip(), "source_text": raw, "source_restoration": proof})
            expected_events.append({"passage_id": pid, "rule": "source_restoration", "count": 1,
                "label": "Exakt belegten Originalquellentext wiederhergestellt", "addition_id": addition["id"],
                "source_text_sha256": addition["source_text_sha256"], "text_sha256": addition["text_sha256"],
                "before_excerpt": "", "after_excerpt": raw.strip()[:440], "evidence": addition["evidence"]})

        def note_position(note):
            member, identifier = note["id"].split("#", 1)
            indices = [index for index, element in enumerate(bodies[member]) if element.get("id") == identifier]
            if len(indices) != 1:
                raise ValueError("Original annotation order has an ambiguous source identity")
            return member_order[member], indices[0]

        for passage in result["passages"]:
            original_notes = next(item for item in prior["passages"] if item["id"] == passage["id"])["metadata"]["annotations"]
            notes = passage["metadata"]["annotations"]
            notes.sort(key=note_position)
            if [note["id"] for note in notes if note["id"] in {old["id"] for old in original_notes}] != [old["id"] for old in original_notes]:
                raise ValueError("Restoration changes existing annotation relative order")
    actual_events = [dict(event, passage_id=pid) for pid, items in events.items() for event in items
                     if event["rule"] == "source_restoration"]
    if sorted(actual_events, key=lambda event: event["addition_id"]) != sorted(expected_events, key=lambda event: event["addition_id"]):
        raise ValueError("Original annotation restoration ledger differs")
    return result


def inspect_ga045_doc_boundary(start, doc_records):
    index = start.get("source_doc_paragraph_index")
    if type(index) is not int or not 0 <= index < len(doc_records):
        raise ValueError("GA045 boundary has no exact original DOC paragraph")
    record = doc_records[index]
    text = record.get("text", "")
    if record.get("index") != index or digest(text.encode()) != start.get("source_doc_paragraph_sha256"):
        raise ValueError("GA045 paragraph boundary differs from its original DOC text")
    point = start.get("source_doc_start_codepoint", 0)
    if type(point) is not int or not 0 <= point < len(text):
        raise ValueError("GA045 DOC semantic boundary has an invalid character offset")
    if point:
        terminal = (start.get("kind") == "note" and start.get("canonical_anchor") == "Hier bricht der Text ab.")
        list_intro = (start.get("kind") == "note" and start.get("canonical_anchor") == "Es wird vorausgesetzt:")
        if not (terminal or list_intro) or text[point - 1] != "\n":
            raise ValueError("GA045 DOC internal boundary is not an evidenced editorial line or list introduction")
    normalize = lambda value: re.sub(r"[^a-zäöü0-9]", "", value.casefold().replace("ß", "ss"))
    anchor = normalize(start.get("canonical_anchor", ""))
    original = normalize(text[point:])
    # A source page may end before the canonical anchor's final word. Both
    # prefixes must still begin at the exact retained DOC paragraph boundary.
    if anchor and (not original or not (original.startswith(anchor) or anchor.startswith(original))):
        raise ValueError("GA045 paragraph starts at a different original DOC text position")


def inspect_ga045_internal_seam(repair, raw_parts, doc_records):
    """Check the retained edition's literal line seam in both DOC and EPUB."""
    match = re.fullmatch(r"([" + LETTERS + r"]+)-\s+([" + LETTERS + r"]+)", repair.get("old", ""))
    if (not match or repair.get("match_word_boundaries") is not True
            or repair.get("source_contains_exact_physical_lf") is not True
            or repair.get("new") not in {match[1] + match[2], match[1] + "-" + match[2]}
            or not raw_parts or not doc_records):
        raise ValueError("GA045 internal word seam lacks its exact physical-line contract")
    # A newline in each source witness is required. Merely finding an already
    # joined spelling in the source cannot authorize removing a real hyphen.
    pattern = re.compile(r"(?<!\w)" + re.escape(match[1]) + r"-[ \t]*\n[ \t]*"
                         + re.escape(match[2]) + r"(?!\w)")
    if not all(pattern.search(raw) for raw in raw_parts):
        raise ValueError("GA045 internal seam is not a literal EPUB line ending")
    origins = repair.get("source_doc_witnesses")
    if origins is None:
        origins = [{key: repair.get(key) for key in
                    ("source_doc_paragraph_index", "source_doc_paragraph_sha256")}]
    if not origins:
        raise ValueError("GA045 internal seam lacks its original DOC paragraphs")
    selected = set()
    doc_count = 0
    for origin in origins:
        index = origin.get("source_doc_paragraph_index")
        if type(index) is not int or index in selected or not 0 <= index < len(doc_records):
            raise ValueError("GA045 internal seam has an invalid original DOC paragraph")
        selected.add(index)
        record = doc_records[index]
        text = record.get("text", "")
        if (record.get("index") != index or digest(text.encode()) != origin.get("source_doc_paragraph_sha256")
                or not pattern.search(text)):
            raise ValueError("GA045 internal seam differs from its hash-bound DOC line ending")
        doc_count += len(pattern.findall(text))
    source_count = sum(len(pattern.findall(raw)) for raw in raw_parts)
    if doc_count != source_count:
        raise ValueError("GA045 internal seam loses or repeats an original occurrence")


def inspect_ga045_page_seam(repair, raw_parts, doc_records):
    match = re.fullmatch(r"([" + LETTERS + r"]+)-\s+([" + LETTERS + r"]+)", repair.get("old", ""))
    origins, footer = repair.get("source_doc_witnesses", []), repair.get("source_doc_page_footer", {})
    if (not match or not doc_records or len(origins) != 2 or len(raw_parts) != 2
            or repair.get("source_contains_exact_physical_lf") is not False
            or repair.get("physical_page_seam") is not True):
        raise ValueError("GA045 page seam lacks its two original paragraphs and intervening footer")
    records = []
    for origin in origins + [footer]:
        index = origin.get("source_doc_paragraph_index")
        if type(index) is not int or not 0 <= index < len(doc_records):
            raise ValueError("GA045 page seam has an invalid original paragraph index")
        record = doc_records[index]
        if record.get("index") != index or digest(record.get("text", "").encode()) != origin.get("source_doc_paragraph_sha256"):
            raise ValueError("GA045 page seam differs from its original DOC paragraph")
        records.append(record)
    left, right, page = records
    if (left["index"] + 1 != page["index"] or page["index"] + 1 != right["index"]
            or page.get("is_page_footer") is not True or type(footer.get("page")) is not int
            or page.get("footer_page") != footer["page"]
            or not left["text"].rstrip().endswith(match[1] + "-")
            or not re.match(re.escape(match[2]) + r"(?!\w)", right["text"].lstrip())
            or not raw_parts[0].rstrip().endswith(match[1] + "-")
            or not re.match(re.escape(match[2]) + r"(?!\w)", raw_parts[1].lstrip())):
        raise ValueError("GA045 word fragments are not consecutive original page endpoints")


def inspect_essay_word_repair(repair, raw_parts, pid, witness, doc_records=None):
    kind = repair.get("kind")
    if kind == "physical_word_seam":
        if pid.startswith("ga-045-") and repair.get("physical_page_seam") is True:
            inspect_ga045_page_seam(repair, raw_parts, doc_records)
        if pid.startswith("ga-045-") and repair.get("source_contains_exact_physical_lf") is True:
            inspect_ga045_internal_seam(repair, raw_parts, doc_records)
            return
        exact_restored_seams = {"Frauen-städt": "Frauenstädt", "Schopen-hauerschen": "Schopenhauerschen",
                                "Gwin-ners": "Gwinners"}
        if pid == "ga-033-schopenhauer-bibliographisches" and repair["old"] in exact_restored_seams:
            if (repair.get("new") != exact_restored_seams[repair["old"]]
                    or repair.get("match_word_boundaries") is not True or not raw_parts
                    or not any(repair["old"] in raw for raw in raw_parts)
                    or not repair.get("pdf_line_pair_witnesses") or not repair.get("source_pdf_pages")):
                raise ValueError("Restored Schopenhauer word seam exceeds its exact printed word")
            return
        match = re.fullmatch(r"([" + LETTERS + r"]+)-\s+([" + LETTERS + r"]+)", repair["old"])
        context = " ".join(" ".join(raw.split()) for raw in raw_parts)
        original_internal_seam = (pid == "ga-036-doc-heading-37" and repair["old"] == "um- zusehn"
            and repair.get("new") == "umzusehn" and repair.get("source_member") == "EPUB/chapter-0006.xhtml"
            and repair.get("body_index") == 127
            and repair.get("source_paragraph_sha256") == "6810711c552f655d2d87d957909e3190505a1b6592872a6a4a564a5ce6d49a1d"
            and len(raw_parts) == 1 and raw_parts[0].count("um-\nzusehn") == 1
            and digest(raw_parts[0].encode()) == repair["source_paragraph_sha256"]
            and repair.get("source_contains_exact_physical_lf") is True
            and repair.get("source_pdf_pages") == [194]
            and len(repair.get("pdf_line_pair_witnesses", [])) == 1
            and len(repair.get("pdf_raster_witnesses", [])) == 1)
        if ((len(raw_parts) < 2 and not original_internal_seam) or " ".join(repair["old"].split()) not in context
                or not match or repair.get("match_word_boundaries") is not True
                or repair["new"] not in {match[1] + match[2], match[1] + "-" + match[2]}):
            raise ValueError("Physical word repair changes original source letters or lacks both source lines")
    elif kind == "source_contents_restoration":
        work_id = "-".join(pid.split("-")[:2])
        if (pid not in FRONT_IDS[work_id] or witness.get("source_role") != "table_of_contents"
                or not raw_parts or not isinstance(repair.get("new"), str) or not repair["new"].strip()
                or repair.get("match_word_boundaries", False)
                or repair.get("count", 1) != 1
                or repair["new"] != witness.get("restored_contents_text")):
            raise ValueError("Contents restoration exceeds an exact retained front-container witness")
    elif kind == "source_heading_restoration":
        point = repair.get("heading_start_codepoint")
        starts = [start for start in witness["starts"] if start["kind"] == "heading" and start["start_codepoint"] == point]
        if (len(starts) != 1 or not raw_parts or not repair.get("source_pdf_pages")
                or not repair.get("new", "").strip() or "\n" in repair["new"]
                or not starts[0]["canonical_anchor"].startswith(repair["old"])):
            raise ValueError("Heading restoration exceeds its exact original heading boundary")
    elif kind != "literal_year_restoration":
        raise ValueError("Unknown or missing source repair kind")


def inspect_reviewed_essay_layout(prior: dict, final: dict, recipe: dict, events: dict,
                                  source: Path, review_path: Path,
                                  inspect_source_layout) -> tuple[list[str], int]:
    """Bind every retained paragraph and boundary to its frozen source review."""
    if prior.get("work_id") not in WORK_IDS:
        raise ValueError("Source-bound essay checker received a different edition")
    review = read(review_path)
    for kind in ("original_doc", "original_pdf", "source_layout"):
        path_key, hash_key = kind + "_path", kind + "_sha256"
        if path_key in review:
            original_path = Path(review[path_key])
            if not original_path.is_absolute():
                original_path = ROOT / original_path
            if digest(original_path.read_bytes()) != review.get(hash_key):
                raise ValueError("Original source document/layout byte identity differs: " + kind)
    doc_records = None
    if prior.get("work_id") == "ga-045":
        layout_path = Path(review["source_layout_path"])
        if not layout_path.is_absolute():
            layout_path = ROOT / layout_path
        document_layout = read(layout_path)
        if (not isinstance(document_layout, dict)
                or document_layout.get("source_doc_sha256") != review.get("original_doc_sha256")):
            raise ValueError("GA045 paragraph layout belongs to a different source DOC")
        doc_records = document_layout.get("paragraphs")
        if not isinstance(doc_records, list):
            raise ValueError("GA045 original DOC layout has an invalid paragraph inventory")
    revision = digest(json.dumps(review, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    if recipe.get("source_evidence", {}).get("review_sha256") != revision:
        raise ValueError("GA033–036 source review identity differs")
    for key in ("work_id", "source_sha256", "source_epub_sha256"):
        if prior.get(key) != recipe.get(key) or recipe.get(key) != review.get(key):
            raise ValueError("GA033–036 retained source identity differs: " + key)
    if digest(source.read_bytes()) != review["source_epub_sha256"]:
        raise ValueError("GA033–036 original EPUB byte hash differs")
    prior = inspect_essay_recovery(prior, recipe, review, events, source)
    prior = inspect_essay_annotation_recovery(prior, recipe, review, events, source)
    pids = [p["id"] for p in prior["passages"]]
    if list(review["passages"]) != pids or list(recipe["passages"]) != pids:
        raise ValueError("GA033–036 source passage inventory/order differs")
    for key in ("metadata_repairs", "annotation_repairs", "known_gaps", "review_flags"):
        if recipe.get(key, []) != review.get(key, []):
            raise ValueError("GA033–036 recipe differs from frozen source review: " + key)
    source_evidence = {"review_sha256": revision, "method": review["method"],
                       "source_members": review["source_members"]}
    for key in ("original_doc_sha256", "original_pdf_sha256", "source_layout_sha256"):
        if key in review:
            source_evidence[key] = review[key]
    if recipe["source_evidence"] != source_evidence:
        raise ValueError("GA033–036 complete source evidence differs from frozen review")
    retained_members = {m["member"]: m["sha256"] for m in prior["proofing"]["source_members"]}
    if retained_members != review["source_members"]:
        raise ValueError("GA033–036 source-member inventory differs from retained import")
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
                raise ValueError("GA033–036 original member byte hash differs: " + member)
            bodies[member] = ET.fromstring(data).find("{http://www.w3.org/1999/xhtml}body")

        def original(witness):
            member, index = witness["source_member"], witness["body_index"]
            if member not in bodies or type(index) is not int or not 0 <= index < len(bodies[member]):
                raise ValueError("GA033–036 invalid original body witness")
            element = bodies[member][index]
            path = ([witness["child_index"]] if "child_index" in witness else []) + witness.get("child_path", [])
            for child in path:
                if type(child) is not int or not 0 <= child < len(element):
                    raise ValueError("GA033–036 invalid original nested source witness")
                element = element[child]
            raw = "".join(element.itertext())
            if digest(raw.encode()) != witness["source_paragraph_sha256"]:
                raise ValueError("GA033–036 original paragraph witness differs")
            if not witness.get("evidence") and witness not in source_reconstruction:
                raise ValueError("GA033–036 reviewed boundary/repair lacks source evidence")
            return raw, (member_order[member], index, tuple(path))

        source_reconstruction = [part for p in review["passages"].values() for part in p["source_parts"]]
        for passage in prior["passages"]:
            pid, text = passage["id"], passage["text"]
            witness, plan = review["passages"][pid], recipe["passages"][pid]
            if (digest(text.encode()) != witness["input_sha256"] or witness["input_sha256"] != plan["input_sha256"]
                    or digest(passage["source_text"].encode()) != witness["source_text_sha256"]
                    or witness["source_text_sha256"] != plan["source_text_sha256"] or passage["title"] != witness["title"]):
                raise ValueError("GA033–036 retained text/source/title differs: " + pid)
            raw_parts = []
            for part in witness["source_parts"]:
                raw, position = original(part)
                if position in selected or prior_position is not None and position <= prior_position:
                    raise ValueError("GA033–036 original source reconstruction loses order or repeats text")
                selected.add(position)
                prior_position = position
                raw_parts.append(raw)
            if "\n\n".join(raw_parts) != passage["source_text"]:
                raise ValueError("GA033–036 retained source_text cannot be reconstructed exactly: " + pid)
            starts, omissions = witness["starts"], witness.get("omissions", [])
            if (not starts or starts[0]["start_codepoint"] != 0
                    or [s["start_codepoint"] for s in starts] != sorted({s["start_codepoint"] for s in starts})):
                raise ValueError("GA033–036 source paragraph boundaries are ambiguous: " + pid)
            if plan.get("edits", []) != witness.get("edits", []):
                raise ValueError("GA033–036 word repairs differ from frozen review: " + pid)
            for repair in witness.get("edits", []):
                if not repair.get("old") or not repair.get("evidence"):
                    raise ValueError("GA033–036 word repair lacks exact literal/evidence")
                if repair.get("kind") not in {"physical_word_seam", "literal_year_restoration", "source_contents_restoration", "source_heading_restoration"}:
                    raise ValueError("GA033–036 source repair has an unknown or missing reviewed kind")
                if "source_member" in repair or "source_paragraph_sha256" in repair:
                    original(repair)
                for origin in repair.get("source_witnesses", []):
                    original(dict(origin, evidence=repair["evidence"]))
                raw_origins = [original(dict(origin, evidence=repair["evidence"]))[0]
                               for origin in repair.get("source_witnesses", [])]
                inspect_essay_word_repair(repair, raw_origins, pid, witness, doc_records)
                inspect_pdf_witnesses(repair, review)
                if repair.get("kind") == "literal_year_restoration":
                    raw, _ = original(repair)
                    token = repair.get("source_token", "")
                    match = re.fullmatch(r"\[(1[89]\d{2})\]", token)
                    if not match or raw.count(token) != 1:
                        raise ValueError("GA033–036 literal year lacks an exact original token")
                    year = match.group(1)
                    if " ".join(repair["new"].split()) not in " ".join(raw.replace(token, year).split()):
                        raise ValueError("GA033–036 literal year is not restored at its exact original word position")
                    occurrences = list(re.finditer(r"(?<!\d)" + year + r"(?!\d)", repair["new"]))
                    if not any(" ".join((repair["new"][:m.start()] + repair["new"][m.end():]).split())
                               == " ".join(repair["old"].split()) for m in occurrences):
                        raise ValueError("GA033–036 literal year repair changes additional source wording")
            expected_omissions = []
            for omission in omissions:
                original(omission)
                inspect_pdf_witnesses(omission, review)
                slices = source_parts(text, omission["start_codepoint"], omission["end_codepoint"])
                if len(slices) != 1:
                    raise ValueError("GA033–036 page furniture is not one exact retained source slice")
                expected_omissions.append(slices[0] | {k: deepcopy(v) for k, v in omission.items()
                    if k not in {"start_codepoint", "end_codepoint"}})
            if plan.get("omitted_parts", []) != expected_omissions:
                raise ValueError("GA033–036 page furniture differs from frozen source review: " + pid)
            segments = []
            for index, start in enumerate(starts):
                original(start)
                if doc_records is not None:
                    inspect_ga045_doc_boundary(start, doc_records)
                begin = start["start_codepoint"]
                end = starts[index + 1]["start_codepoint"] if index + 1 < len(starts) else len(text)
                if not 0 <= begin < end <= len(text) or not text[begin:].startswith(start["canonical_anchor"]):
                    raise ValueError("GA033–036 exact retained paragraph anchor differs: " + pid)
                line_starts = start.get("line_starts", [])
                if (line_starts and (start["kind"] not in {"verse", "note"}
                        or line_starts != sorted(set(line_starts))
                        or any(type(point) is not int or not begin < point < end for point in line_starts))):
                    raise ValueError("GA033–036 true source line boundaries are invalid")
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
                raise ValueError("GA033–036 complete layout slices differ from frozen source boundaries: " + pid)
        repaired_fields = set()
        for repair in recipe.get("metadata_repairs", []):
            raw, _ = original(repair)
            inspect_pdf_witnesses(repair, review)
            pid, before, after = repair["passage_id"], repair["before"], repair["after"]
            if not before or set(before) != set(after) or not set(before) <= {"title", "ga_page", "page_numbers"}:
                raise ValueError("GA033–036 source metadata repair has an invalid field contract")
            passage = expected_by_id[pid]
            if "title" in after:
                origins = repair.get("source_witnesses", [])
                title = " ".join(" ".join(original(dict(origin, evidence=repair["evidence"]))[0].split())
                                 for origin in origins) if origins else " ".join(raw.split())
                rendered_title = after["title"]
                if repair.get("kind") == "source_contents_restoration":
                    if review["passages"][pid].get("source_role") != "table_of_contents" or not rendered_title.startswith("Inhalt"):
                        raise ValueError("Contents metadata repair exceeds its reviewed front container")
                elif " ".join(rendered_title.split()) != title:
                    raise ValueError("Restored metadata title differs from its complete original heading")
            if set(after) & {"ga_page", "page_numbers"} and not {"ga_page", "page_numbers"} <= set(after):
                raise ValueError("GA033–036 source page repair omits its exact paired metadata fields")
            if "page_numbers" in after:
                if (after["page_numbers"] != [] or after.get("ga_page") is not None
                        or not before["page_numbers"]
                        or any(type(year) is not int or year < 1800 or year > 1999
                               or f"[{year}]" not in passage["source_text"] for year in before["page_numbers"])):
                    raise ValueError("GA033–036 page metadata repair exceeds its genuine source-year mistakes")
            for field, value in before.items():
                actual = passage["metadata"].get(field) if field == "page_numbers" else passage.get(field)
                if actual != value or (pid, field) in repaired_fields:
                    raise ValueError("GA033–036 source metadata repair changes an unexpected field value")
                repaired_fields.add((pid, field))
                (passage["metadata"] if field == "page_numbers" else passage)[field] = deepcopy(after[field])
        repaired_annotations = set()
        for repair in recipe.get("annotation_repairs", []):
            raw, _ = original(repair)
            inspect_pdf_witnesses(repair, review)
            pid, aid = repair["passage_id"], repair["annotation_id"]
            element = bodies[repair["source_member"]][repair["body_index"]]
            imported_whitespace = ((review["work_id"] == "ga-035" and aid in {
                "EPUB/chapter-0002.xhtml#footnote-recovered-3", "EPUB/chapter-0003.xhtml#footnote-recovered-2"}
                or review["work_id"] == "ga-034" and aid in GA034_NOTE_IDS)
                and isinstance(repair.get("before"), str)
                and re.sub(r"\s", "", raw) == re.sub(r"\s", "", repair["before"]))
            expected_after = re.sub(r"\s*\n\s*", " ", repair.get("before", ""))
            joins = repair.get("word_joins", [])
            if joins:
                if review["work_id"] == "ga-035" and aid == "EPUB/chapter-0003.xhtml#footnote-recovered-2":
                    pages, exact_joins = [95], {"Schel ling": "Schelling", "Den ker": "Denker",
                                              "Bestre bungen": "Bestrebungen", "er fahren": "erfahren"}
                elif review["work_id"] == "ga-034" and aid in GA034_NOTE_JOINS:
                    pages, exact_joins = GA034_NOTE_JOINS[aid]
                else:
                    raise ValueError("Annotation word joins target an unreviewed source note")
                if ({join["old"]: join["new"] for join in joins} != exact_joins
                        or len(joins) != len(exact_joins) or repair.get("source_pdf_pages") != pages):
                    raise ValueError("Annotation word joins exceed their exact printed continuation list/pages")
                for join in joins:
                    if expected_after.count(join["old"]) != 1:
                        raise ValueError("Annotation source continuation is absent or repeated")
                    expected_after = expected_after.replace(join["old"], join["new"])
            if ((pid, aid) in repaired_annotations or "#" not in aid
                    or aid.split("#", 1)[0] != repair["source_member"]
                    or element.get("id") != aid.split("#", 1)[1] or element.get("role") != "doc-footnote"
                    or not isinstance(repair.get("before"), str)
                    or not imported_whitespace and ("\n\n" in repair["before"] or raw.strip() != repair["before"])
                    or expected_after != repair.get("after")):
                raise ValueError("GA033–036 annotation repair changes unreviewed source wording or structure")
            matches = [note for note in expected_by_id[pid]["metadata"].get("annotations", []) if note["id"] == aid]
            if len(matches) != 1 or matches[0]["marker"] != repair["marker"] or matches[0]["text"] != repair["before"]:
                raise ValueError("GA033–036 annotation repair differs from original inventory/text")
            repaired_annotations.add((pid, aid))
            matches[0]["text"] = repair["after"]
        for pid, passage in expected_by_id.items():
            if recipe["passages"][pid]["group_title"] != review["passages"][pid].get("group_title", passage["title"]):
                raise ValueError("GA033–036 source group title differs from frozen review: " + pid)
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
            raise ValueError("GA033–036 source article sections omit retained initial text")
        for number, index in enumerate(section_starts):
            end = section_starts[number + 1] if number + 1 < len(section_starts) else len(witness["starts"])
            block = actual["metadata"]["reading_blocks"][index]
            encoded = actual["text"].encode("utf-16-le")
            heading = encoded[2 * block["start_offset"]:2 * block["end_offset"]].decode("utf-16-le").split("\n", 1)[0]
            if number and block["kind"] != "heading":
                raise ValueError("GA033–036 source article lacks its original heading")
            sections.append({"start_segment": index, "end_segment": end,
                "title": witness["starts"][index].get("section_title", passage["title"] if not number else heading),
                "label_kind": witness["starts"][index].get("label_kind", "source_title"),
                "evidence": witness["starts"][index]["evidence"]})
        if plan.get("sections", []) != sections:
            raise ValueError("GA033–036 source article sections differ from frozen review")
        metadata_repairs = [r for r in recipe.get("metadata_repairs", []) if r["passage_id"] == pid]
        annotation_repairs = [r for r in recipe.get("annotation_repairs", []) if r["passage_id"] == pid]
        fragments = []
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
        raise ValueError("GA033–036 original contents are not bound to frozen source review")
    if "table_of_contents" in review:
        targets = {}
        for pid, witness in review["passages"].items():
            for index, start in enumerate(witness["starts"]):
                if start.get("toc_target"):
                    if start["toc_target"] in targets:
                        raise ValueError("GA033–036 original contents target is duplicated")
                    targets[start["toc_target"]] = (pid, index)
        toc = []
        original_rows = review.get("original_table_of_contents", [])
        assessments = review.get("original_toc_target_review", [])
        if not original_rows or not assessments:
            raise ValueError("Original contents navigation lacks its printed entry/target review")
        entries = {row["id"]: row for row in review["table_of_contents"]}
        mapped = set()
        for assessment in assessments:
            if not assessment.get("target"):
                continue
            identifier = assessment.get("toc_id")
            if identifier not in entries or identifier in mapped:
                raise ValueError("Original contents target is absent or duplicated in its entry review")
            entry = entries[identifier]
            if any(assessment.get(key) != entry.get(key) for key in ("target", "level", "parent_id")):
                raise ValueError("Original contents target hierarchy differs from its printed-entry review")
            if assessment.get("source_witness"):
                original(dict(assessment["source_witness"], evidence="Original printed contents target"))
            mapped.add(identifier)
        for row in review["table_of_contents"]:
            role = row.get("source_role")
            if role == "table_of_contents":
                if (targets[row["target"]][0] not in FRONT_IDS[review["work_id"]]
                        or row["level"] != 1 or row["parent_id"] is not None):
                    raise ValueError("Original contents area targets an author essay or incorrect hierarchy")
            elif role == "group":
                if not row.get("source_heading_witness"):
                    raise ValueError("Original contents group lacks its exact printed heading")
            elif row["id"] not in mapped:
                raise ValueError("An extra navigation article lacks an original printed-entry target")
            if "source_heading_witness" in row:
                raw, _ = original(dict(row["source_heading_witness"], evidence="Original printed contents division"))
                if " ".join(raw.split()) != " ".join(row.get("source_original_title", row["title"]).split()):
                    raise ValueError("GA033–036 contents division differs from its exact original heading")
            pid, index = targets[row["target"]]
            target = final_by_id[pid]["metadata"]["reading_blocks"][index]["start_offset"]
            toc.append({k: deepcopy(v) for k, v in row.items() if k != "target"} | {"passage_id": pid, "start_offset": target})
        if recipe["table_of_contents"] != toc:
            raise ValueError("GA033–036 original contents titles/targets differ from frozen source review")
    layout = projected.get("metadata", {}).get("source_layout", {})
    extra = {"source_epub_sha256": recipe["source_epub_sha256"], "review_sha256": revision,
             "source_evidence": source_evidence}
    if recipe.get("source_additions"):
        extra.update(source_restoration_count=len(recipe["source_additions"]),
                     original_passage_ids=list(recipe["original_passages"]))
    if recipe.get("annotation_additions"):
        extra["source_annotation_restoration_count"] = len(recipe["annotation_additions"])
    for key, value in extra.items():
        if layout.get(key) != value:
            errors.append("GA033–036 source-layout provenance differs: " + key)
        layout.pop(key, None)
    layout_errors, repairs = inspect_source_layout(expected, projected, recipe, checked_events)
    return errors + layout_errors, repairs
