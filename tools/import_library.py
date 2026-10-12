#!/usr/bin/env python3
"""Adapt the existing, source-audited Falz EPUB collection to native reader JSON.

Requires lxml. Sources stay untouched. The five existing normalized books keep
their edition and passage IDs. Other volumes remain explicitly working editions;
structural extraction is not a claim of complete facsimile proofing.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import posixpath
import re
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

CORE = {"ga-003", "ga-004", "ga-009", "ga-010", "ga-013"}
XHTML = "http://www.w3.org/1999/xhtml"
EPUB = "http://www.idpf.org/2007/ops"
BLOCKS = {"p", "li", "pre", "table", "blockquote", "figcaption"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
EDITORIAL = re.compile(
    r"^(?:hinweise(?:\s|$)|zu dieser ausgabe|zur vorliegenden ausgabe|"
    r"(?:namen|personen|sach|begriffs|literatur|titel|stellen)register|register$|"
    r"bibliographi(?:e|sche)|literaturverzeichnis|inhaltsverzeichnis|inhaltsübersicht|inhalt$|"
    r"ausführliche inhaltsangaben|anmerkungsverzeichnis|"
    r"rudolf steiner[ -]+gesamtausgabe|übersicht (?:über|der) (?:die )?gesamtausgabe|"
    r"(?:vor|nach)wort (?:des|der) herausgeber|die herausgeber|"
    r"pythagoras[ -]+zweig|theosophische gesellschaft\s*\(adyar\))", re.I,
)
MACRO = re.compile(r"#(?:SE\d[^\s\ufdd0\ufdd1\ufdd2]*|(?:TI|TX|BI|LI|IR|HY|MU)\b)")
HTML_WHITESPACE = re.compile(r"[ \t\r\n\f]+")
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
CSS_WHITESPACE_ATTRIBUTE = "data-ga-import-white-space"
CSS_WHITESPACE_MODES = {"normal", "nowrap", "initial", "inherit", "unset", "pre", "pre-wrap", "pre-line", "break-spaces"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_id(ga: str, source_id: str | None = None) -> str:
    match = re.fullmatch(r"(\d+)([a-z0-9/-]*)", ga.lower().strip())
    if not match:
        if source_id and re.fullmatch(r"ga-[a-z0-9]+(?:-[a-z0-9]+)*", source_id):
            return source_id
        raise ValueError(f"Noncanonical GA number: {ga}")
    return f"ga-{int(match[1]):03d}{match[2].replace('/', '-')}"


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def name(element) -> str:
    return etree.QName(element).localname if isinstance(element.tag, str) else ""


def whitespace_declarations(style: str) -> list[tuple[str, bool]]:
    values = []
    for declaration in re.findall(r"(?:^|;)\s*white-space\s*:\s*([^;]+)", style, re.I):
        important = bool(re.search(r"!important\s*$", declaration, re.I))
        value = re.sub(r"\s*!important\s*$", "", declaration, flags=re.I).strip().lower()
        values.append((value, important))
    return values


def apply_stylesheet_whitespace(root, archive: ZipFile, member: str) -> list[str]:
    """Apply local simple tag/class/id whitespace rules; report other rules.

    The prepared library uses .source-lines {white-space:pre-line}. Reading its
    actual stylesheet prevents those literal lines from being silently folded.
    This deliberately is not a general browser CSS implementation.
    """
    styles, warnings = [], []
    for element in root.iter():
        if name(element) == "style":
            styles.append("".join(element.itertext()))
        elif name(element) == "link" and "stylesheet" in element.get("rel", "").lower().split():
            href = element.get("href", "").split("#", 1)[0]
            if re.match(r"^[a-z][a-z0-9+.-]*:|^//", href, re.I):
                warnings.append(f"{member}: externes Stylesheet wird nicht interpretiert: {href}")
                continue
            path = posixpath.normpath(posixpath.join(posixpath.dirname(member), href))
            try:
                styles.append(archive.read(path).decode("utf-8"))
            except (KeyError, UnicodeError):
                warnings.append(f"{member}: Stylesheet nicht lesbar: {path}")
    elements = [element for element in root.iter() if isinstance(element.tag, str)]
    applied = {}
    rule_order = 0
    for style in styles:
        style = re.sub(r"/\*.*?\*/", "", style, flags=re.S)
        if "white-space" in style.lower() and re.search(r"@(media|supports|import|layer|container)\b", style, re.I):
            warnings.append(f"{member}: bedingte oder importierte CSS-Regeln benötigen Prüfung")
        for selector_group, body in re.findall(r"([^{}]+)\{([^{}]*)\}", style):
            declarations = whitespace_declarations(body)
            if not declarations:
                continue
            rule_order += 1
            value, important = max(enumerate(declarations), key=lambda pair: (pair[1][1], pair[0]))[1]
            if value not in CSS_WHITESPACE_MODES:
                warnings.append(f"{member}: unbekannter white-space-Wert: {value}")
                continue
            for selector in selector_group.split(","):
                selector = selector.strip()
                if not selector or not re.fullmatch(r"(?:[a-zA-Z][\w-]*|\*)?(?:[.#][\w-]+)*", selector):
                    warnings.append(f"{member}: nicht unterstützter white-space-Selektor: {selector}")
                    continue
                tag = re.match(r"^[a-zA-Z][\w-]*", selector)
                classes, ids = re.findall(r"\.([\w-]+)", selector), re.findall(r"#([\w-]+)", selector)
                priority = (important, len(ids), len(classes), bool(tag), rule_order)
                for element in elements:
                    if tag and name(element).lower() != tag[0].lower():
                        continue
                    if not set(classes).issubset(element.get("class", "").split()):
                        continue
                    if ids and any(element.get("id") != identifier for identifier in ids):
                        continue
                    previous = applied.get(element)
                    if previous is None or priority >= previous[0]:
                        applied[element] = (priority, value, important)
    for element, (_, value, important) in applied.items():
        element.set(CSS_WHITESPACE_ATTRIBUTE, value + (" !important" if important else ""))
    return list(dict.fromkeys(warnings))


def whitespace_mode(element, inherited: str = "normal") -> str:
    """Recognize inherited literal text and the resolved local CSS declaration."""
    mode = "preserve" if name(element) == "pre" else inherited
    if element.get(XML_SPACE) == "preserve":
        mode = "preserve"
    elif element.get(XML_SPACE) == "default":
        mode = "normal"
    declarations = whitespace_declarations("white-space:" + element.get(CSS_WHITESPACE_ATTRIBUTE, ""))
    external_important = bool(declarations and declarations[-1][1])
    inline = whitespace_declarations(element.get("style", ""))
    if inline:
        best_inline = max(enumerate(inline), key=lambda pair: (pair[1][1], pair[0]))[1]
        if best_inline[1] or not external_important:
            declarations = [best_inline]
    if declarations:
        value = declarations[-1][0]
        if value in {"pre", "pre-wrap", "break-spaces"}:
            mode = "preserve"
        elif value == "pre-line":
            mode = "pre-line"
        elif value in {"normal", "nowrap", "initial"}:
            mode = "normal"
        elif value in {"inherit", "unset"}:
            mode = inherited
    return mode


def text_of(element) -> str:
    # XML text-node line breaks are collapsible HTML whitespace, not verse
    # boundaries. Keep <br> separate until the source's raw whitespace has been
    # collapsed; otherwise a <br/> followed by source indentation becomes two
    # line breaks. Protected fragments keep literal <pre>/xml:space/CSS text.
    br_marker = "\ufdd0"
    protected: list[str] = []

    def protect(value: str) -> str:
        protected.append(value)
        return f"\ufdd1{len(protected) - 1}\ufdd2"

    def fragment(value: str | None, mode: str) -> str:
        if not value:
            return ""
        if mode == "preserve":
            return protect(value)
        if mode == "pre-line":
            return re.sub(r"\r\n?|\n", br_marker, value)
        return value

    def collect(node, inherited: str = "normal") -> str:
        mode = whitespace_mode(node, inherited)
        parts = [fragment(node.text, mode)]
        for child in node:
            if name(child) == "br":
                parts.append(protect("\n") if mode == "preserve" else br_marker)
            elif isinstance(child.tag, str):
                parts.append(collect(child, mode))
            parts.append(fragment(child.tail, mode))
        return "".join(parts)

    inherited = "normal"
    for ancestor in reversed(list(element.iterancestors())):
        inherited = whitespace_mode(ancestor, inherited)
    text = collect(element, inherited)
    # #TI contains an edition header/title; #TX begins the original text even
    # when the source has collapsed all three macros into a single paragraph.
    text = re.sub(r"#G\d.*?(?=#TX\b)", "", text, flags=re.S)
    text = re.sub(r"(?m)(?:^|(?<=" + br_marker + r"))[ \t]*#G\d[^\n" + br_marker + r"]*(?=$|\n|" + br_marker + r")", "", text)
    text = re.sub(r"#TI\b[^#]*?(?=#TX\b)", "", text)
    text = MACRO.sub("", text)
    text = re.sub(r"PAGE\s+\\\*\s+MERGEFORMAT\s+\d+", "", text)
    # Preserve explicit verse breaks and source spelling. No word corrections.
    text = HTML_WHITESPACE.sub(" ", text)
    text = re.sub(r" *" + br_marker + r" *", "\n", text).strip()
    return re.sub(r"\ufdd1(\d+)\ufdd2", lambda match: protected[int(match[1])], text)


def drop(element):
    parent = element.getparent()
    if parent is None:
        return
    tail = element.tail or ""
    previous = element.getprevious()
    if previous is None:
        parent.text = (parent.text or "") + tail
    else:
        previous.tail = (previous.tail or "") + tail
    parent.remove(element)


def blocks(element):
    for child in element:
        tag = name(child)
        if tag in HEADINGS or (tag in BLOCKS and not child.xpath(".//*[local-name()='h1' or local-name()='h2' or local-name()='h3']")):
            yield child
        else:
            yield from blocks(child)


def editorial_note(element) -> bool:
    return element.get("data-note-editorial") == "true" or bool(re.match(
        r"^\s*(?:\(\d+\)|\d+[.)]?|\*)?\s*\[?\s*(?:anmerkung|anmerkungen|hinweis|zusatz)\s+(?:des|der)\s+herausgeber", "".join(element.itertext()), re.I,
    ))


def read_epub(path: Path, work_id: str, title: str, scope: dict | None = None) -> tuple[list, dict]:
    passages, excluded, annotations = [], [], {}
    current = None
    started = False
    skipping = False
    source_members = []
    whitespace_warnings = []
    scope = scope or {}
    parser = etree.XMLParser(resolve_entities=False, no_network=True)

    def finish():
        nonlocal current
        if current and current["parts"]:
            text = "\n\n".join(current.pop("parts"))
            inline_pages = list(dict.fromkeys(int(page) for page in re.findall(r"\[(\d{1,4})\]", text)))

            def remove_inline_page(match):
                # Only tidy the gap created by this removed navigation marker.
                # Global line stripping would destroy literal pre indentation.
                at_boundary = match.start() == 0 or text[match.start() - 1] == "\n" or match.end() == len(text) or text[match.end()] == "\n"
                had_space = match[0].startswith((" ", "\t")) or match[0].endswith((" ", "\t"))
                return " " if had_space and not at_boundary else ""

            text = re.sub(r"[ \t]*\[\d{1,4}\][ \t]*", remove_inline_page, text)
            if not text.strip():
                current = None
                return
            source_text = "\n\n".join(current.pop("source_parts"))
            span_pages = current.pop("pages")
            pages = list(dict.fromkeys(span_pages + inline_pages))
            refs = current.pop("refs")
            current["text"] = text
            current["source_text"] = source_text
            current["checksum"] = digest(text.encode())
            current["ga_page"] = (f"S. {min(pages)}" if len(pages) == 1 else f"S. {min(pages)}–{max(pages)}") if pages else None
            marker_source = "epub_source_page_labels"
            if inline_pages:
                marker_source = "epub_source_page_labels_and_original_inline_bracket_markers" if span_pages else "original_inline_bracket_markers"
            current["metadata"] = {"page_numbers": pages, "page_marker_source": marker_source, "annotations": []}
            current["annotation_refs"] = list(dict.fromkeys(refs))
            passages.append(current)
        current = None

    with ZipFile(path) as archive:
        container = etree.fromstring(archive.read("META-INF/container.xml"), parser)
        package_path = container.find("{*}rootfiles/{*}rootfile").get("full-path")
        package = etree.fromstring(archive.read(package_path), parser)
        manifest = {item.get("id"): item for item in package.find("{*}manifest")}
        documents = []
        editorial_targets = set()
        for ref in package.find("{*}spine"):
            item = manifest[ref.get("idref")]
            member = posixpath.normpath(posixpath.join(posixpath.dirname(package_path), item.get("href")))
            if item.get("properties") == "nav" or posixpath.basename(member) in {"title.xhtml", "nav.xhtml", "cover.xhtml", "chapter-9999.xhtml"}:
                continue
            root = etree.fromstring(archive.read(member), parser)
            whitespace_warnings.extend(apply_stylesheet_whitespace(root, archive, member))
            body = root.find("{*}body")
            if body is None:
                continue
            documents.append((member, body))
            for note in body.iter():
                if editorial_note(note) and note.get("id"):
                    editorial_targets.add(member + "#" + note.get("id"))
        has_headings = any(name(e) in HEADINGS and "continuation-heading" not in e.get("class", "") for _, body in documents for e in body.iter())
        for member, body in documents:
            source_members.append({"member": member, "sha256": digest(archive.read(member))})
            original_blocks = {}
            original_pages = {}
            for index, block in enumerate(blocks(body)):
                key = str(index)
                block.set("data-ga-import-key", key)
                original_blocks[key] = "".join(block.itertext())
                original_pages[key] = [int(e.get("data-page-label")) for e in block.iter() if (e.get("data-page-label") or "").isdigit() and e.get("data-page-kind", "page") != "letter"]
            # Collect only author notes; editorial and generated note links are removed.
            for note in list(body.iter()):
                is_note = note.get("data-note-definition") == "true" or note.get("role") in {"doc-footnote", "doc-endnote"} or "footnote" in note.get(f"{{{EPUB}}}type", "").split()
                if editorial_note(note):
                    drop(note)
                elif is_note:
                    key = member + "#" + (note.get("id") or "")
                    note_text = text_of(note)
                    if note_text:
                        matched_marker = re.match(r"^(\(\d+\)|\d+[.)]|\*+)", note_text)
                        marker = note.get("data-note-marker") or (matched_marker[1] if matched_marker else "")
                        annotations[key] = {"id": key, "marker": marker, "text": note_text}
                    drop(note)
            for anchor in list(body.iter(f"{{{XHTML}}}a")):
                href = anchor.get("href", "")
                target = posixpath.normpath(posixpath.join(posixpath.dirname(member), href.split("#")[0] or posixpath.basename(member))) + ("#" + href.split("#", 1)[1] if "#" in href else "")
                if anchor.get("role") == "doc-backlink":
                    drop(anchor)
                elif target in editorial_targets and anchor.get("data-note-ref-kind") != "quotation":
                    drop(anchor)
            # Standalone page labels are navigation metadata rather than prose.
            for marker in list(body.xpath("//*[@data-page-label]")):
                if name(marker) not in HEADINGS and name(marker) not in BLOCKS:
                    drop(marker)
            for element in blocks(body):
                heading = name(element) in HEADINGS and "continuation-heading" not in element.get("class", "")
                label = compact("".join(element.itertext()))
                if name(element) in HEADINGS and not heading:
                    continue
                key = member + "#" + element.get("id", "")
                text = text_of(element)
                if not started and scope.get("start"):
                    if key != scope["start"]:
                        continue
                    started = True
                if not started and scope.get("start_text"):
                    wanted = re.compile(r"\s+".join(re.escape(part) for part in scope["start_text"].split()))
                    match = wanted.search(text)
                    if match is None:
                        continue
                    text = text[match.start():]
                    started = True
                if skipping and any(compact(text).startswith(prefix) for prefix in scope.get("resume_texts", [])):
                    skipping = False
                if any(compact(text).startswith(prefix) for prefix in scope.get("exclude_texts", [])):
                    finish()
                    skipping = True
                    excluded.append({"member": member, "heading": compact(text)[:180], "id": element.get("id")})
                    continue
                if heading:
                    finish()
                    skipping = bool(EDITORIAL.match(label) or key in scope.get("exclude", []))
                    if skipping:
                        excluded.append({"member": member, "heading": label, "id": element.get("id")})
                        continue
                    started = True
                    anchor = element.get("id") or f"section-{len(passages) + 1}"
                    passage_id = f"{work_id}-{anchor}"
                    if work_id == "ga-120" and not passages:
                        passage_id = "ga-120-page-15"  # Legacy ID; source pages remain the actual source anchors.
                    current = {"id": passage_id, "title": label or title, "source_label": "Vorhandene GA-Arbeitsausgabe / Kutscherei", "source_member": member, "parts": [], "source_parts": [], "pages": [], "refs": []}
                    continue
                if skipping or (has_headings and not started):
                    continue
                if not text:
                    continue
                if current is None:
                    current = {"id": f"{work_id}-{Path(member).stem}", "title": title, "source_label": "Vorhandene GA-Arbeitsausgabe / Kutscherei", "source_member": member, "parts": [], "source_parts": [], "pages": [], "refs": []}
                # A paragraph can itself begin an unheaded publisher appendix.
                if EDITORIAL.match(compact(text).strip(" .:")) and len(text) < 180:
                    finish()
                    skipping = True
                    excluded.append({"member": member, "heading": compact(text), "id": element.get("id")})
                    continue
                current["parts"].append(text)
                block_key = element.get("data-ga-import-key")
                current["source_parts"].append(original_blocks.get(block_key, text))
                current["pages"].extend(original_pages.get(block_key, []))
                for e in element.iter():
                    page = e.get("data-page-label")
                    if page and page.isdigit() and e.get("data-page-kind", "page") != "letter":
                        current["pages"].append(int(page))
                    href = e.get("href", "")
                    if "#" in href:
                        target = posixpath.normpath(posixpath.join(posixpath.dirname(member), href.split("#")[0] or posixpath.basename(member))) + "#" + href.split("#", 1)[1]
                        current["refs"].append(target)
            # Continuations stay in the preceding original section across spine files.
        finish()
    for passage in passages:
        passage["metadata"]["annotations"] = [annotations[r] for r in passage.pop("annotation_refs") if r in annotations]
    ids = [p["id"] for p in passages]
    if len(set(ids)) != len(ids):
        for index, passage in enumerate(passages):
            passage["id"] += f"-{index + 1:03d}"
    details = {"excluded_sections": excluded, "source_members": source_members, "real_headings_present": has_headings}
    if whitespace_warnings:
        details["whitespace_warnings"] = list(dict.fromkeys(whitespace_warnings))
    return passages, details


def write_json(path: Path, payload: dict, compressed: bool = False):
    data = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(data, compresslevel=9, mtime=0) if compressed else data)


def build(source: Path, output: Path, existing: Path, scope_file: Path | None):
    source_catalog = json.loads((source / "catalog.json").read_text())
    scope = json.loads(scope_file.read_text()) if scope_file else {}
    works, failures = [], []
    report = {"source_catalog_sha256": digest((source / "catalog.json").read_bytes()), "works": []}
    for index, book in enumerate(source_catalog):
        work_id = canonical_id(book["gaNumber"], book["id"])
        ga = book["gaNumber"]
        work = {"id": work_id, "ga_number": "GA " + work_id[3:] if ga[0].isdigit() else ga, "title": book["title"], "subtitle": book.get("sourceCategory") or "", "language": "de", "year_label": "", "type": "book" if book.get("categoryId") == "works" else "lectures", "priority": 100 + index, "state": "import_queue", "proofing_state": "source_pending", "tags": [book.get("categoryId") or "complete-ga", "complete-ga"], "source_summary": book.get("qualityNote") or "", "sanity_checks": [], "passages": []}
        entry = {"id": work_id, "source_id": book["id"], "available": False}
        if work_id in CORE and (existing / f"{work_id}.json").exists():
            payload = json.loads((existing / f"{work_id}.json").read_text())
            passages = payload["passages"]
            work.update(state="published", proofing_state="ai_checked")
            (output / "content").mkdir(parents=True, exist_ok=True)
            (output / "content" / f"{work_id}.json").write_bytes((existing / f"{work_id}.json").read_bytes())
        elif book.get("epubPath"):
            path = (source / book["epubPath"]).resolve()
            if not path.is_relative_to(source.resolve()):
                raise ValueError("Source EPUB escaped library root")
            try:
                epub_hash = digest(path.read_bytes())
                expected_hash = scope.get(ga, {}).get("source_epub_sha256")
                if expected_hash and expected_hash != epub_hash:
                    raise ValueError("Source EPUB changed; review the scope anchors before importing")
                passages, details = read_epub(path, work_id, book["title"], scope.get(ga))
                if not passages:
                    raise ValueError("No original-text candidate sections remained")
                provenance_path = source / "provenance" / (book["id"] + ".json")
                provenance = json.loads(provenance_path.read_text()) if provenance_path.exists() else {}
                warnings = ["Die vorhandene Textgrundlage ist eine Arbeitsausgabe. Eine vollständige Kollation und Prüfung des Originaltextumfangs steht aus."] + scope.get(ga, {}).get("warnings", [])
                payload = {"work_id": work_id, "title": book["title"], "language": "de", "content_completeness": "complete", "source_id": book["id"], "source_url": "https://fototausch.eu/api/ga/books/" + book["id"] + "/download", "source_label": "Vorhandene quellengebundene GA-Arbeitsausgabe", "source_epub_sha256": epub_hash, "source_sha256": provenance.get("sourceSha256"), "passage_count": len(passages), "proofing": {"status": "working_edition_needs_review", "source_retained_for_diff": True, "strict_publishable": book.get("strictPublishable", False), "warnings": warnings, **details}, "passages": passages}
                write_json(output / "content" / (work_id + ".json.gz"), payload, True)
                work.update(state="sanity_check", proofing_state="needs_ai_sanity_check")
                work["source_summary"] = "Arbeitsausgabe aus der vorhandenen GA-Sammlung. " + (book.get("qualityNote") or "")
                work["sanity_checks"] = [{"id": "scope", "title": "Textgrundlage", "status": "warning", "detail": " ".join(warnings)}]
                entry.update(source_epub_sha256=payload["source_epub_sha256"], excluded_sections=details["excluded_sections"], real_headings_present=details["real_headings_present"])
            except Exception as error:
                failures.append({"id": work_id, "error": str(error)})
                passages = []
        else:
            passages = []
        work["content_completeness"] = "complete" if passages else "unavailable"
        if passages:
            work["content_path"] = f"/api/catalog/{work_id}/content"
            work["catalog_passage_count"] = len(passages)
            work["passages"] = [{k: p.get(k) for k in ("id", "title", "ga_page", "source_label", "checksum")} for p in passages]
            entry.update(available=True, passage_count=len(passages), character_count=sum(len(p["text"]) for p in passages))
        works.append(work)
        report["works"].append(entry)
    if failures:
        raise RuntimeError(json.dumps(failures, ensure_ascii=False))
    report["catalog_count"] = len(works)
    report["available_count"] = sum(e["available"] for e in report["works"])
    report["passage_count"] = sum(e.get("passage_count", 0) for e in report["works"])
    catalog = {"edition": "independent-public-domain", "audience": "reader", "works": works}
    write_json(output / "library" / "catalog.json", catalog)
    write_json(output / "library" / "import-report.json", report)
    print(json.dumps({k: report[k] for k in ("catalog_count", "available_count", "passage_count")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Prepared library containing catalog.json and epubs/")
    parser.add_argument("output", type=Path, help="Output directory for content/ and library/")
    parser.add_argument("--existing-content", type=Path, required=True, help="The five original normalized JSON books")
    parser.add_argument("--scope", type=Path)
    args = parser.parse_args()
    build(args.source, args.output, args.existing_content, args.scope)
