#!/usr/bin/env python3
"""Import explicitly reviewed recovery sources into a fresh library staging tree.

Requires lxml, like import_library.py. The source EPUBs and existing payloads
remain unchanged. Run finalize_library.py on the output before using it.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from import_library import BLOCKS, HEADINGS, XHTML, read_epub, write_json

ROOT = Path(__file__).resolve().parents[1]
WARNING = ("Arbeitsausgabe aus wiedergewonnener Textquelle. Eine vollständige "
           "Kollation und Prüfung des Originaltextumfangs steht aus. "
           "Abbildungen bleiben in der Quellen-EPUB erhalten; die Leseausgabe enthält Text.")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def clean_image_placeholders(text: str) -> str:
    text = re.sub(r"(?m)^[ \t]*#Bild[ \t]+s\.[ \t]*\d+[a-z]?[ \t]*$", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def preserve_loose_text(body):
    """Wrap prose outside block elements without losing text or changing spelling.

    Some FVN EPUBs contain a paragraph followed by substantial bare body text
    and <br> tails. The prepared-library block walker cannot see that prose.
    """
    before = "".join(body.itertext())

    def wrap(container):
        children = list(container)
        if container.text and container.text.strip():
            paragraph = etree.Element(f"{{{XHTML}}}p")
            paragraph.text, container.text = container.text, None
            container.insert(0, paragraph)
        for child in children:
            tag = etree.QName(child).localname if isinstance(child.tag, str) else ""
            if isinstance(child.tag, str) and tag not in BLOCKS | HEADINGS:
                wrap(child)
            if child.tail and child.tail.strip():
                paragraph = etree.Element(f"{{{XHTML}}}p")
                paragraph.text, child.tail = child.tail, None
                container.insert(container.index(child) + 1, paragraph)

    wrap(body)
    if "".join(body.itertext()) != before:
        raise ValueError("Loose-text wrapping changed source prose")


def adapted_epub(source: Path, destination: Path):
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    changed = []
    with ZipFile(source) as incoming, ZipFile(destination, "w") as outgoing:
        for member in incoming.infolist():
            data = incoming.read(member.filename)
            if member.filename.endswith((".xhtml", ".html")):
                document = etree.fromstring(data, parser)
                body = document.find("{*}body")
                if body is not None:
                    preserve_loose_text(body)
                    data = etree.tostring(document, encoding="UTF-8", xml_declaration=True)
                    changed.append({"member": member.filename,
                                    "original_sha256": sha(incoming.read(member.filename)),
                                    "adapted_sha256": sha(data)})
            outgoing.writestr(member, data)
    return changed


def build(config: Path, existing: Path, output: Path):
    if output.exists():
        raise ValueError("Choose a fresh output directory")
    selected = json.loads(config.read_text())["works"]
    # Validate every source before creating the staging tree.
    for entry in selected:
        path = ROOT / entry["source_path"]
        if sha(path.read_bytes()) != entry["source_sha256"]:
            raise ValueError(f"Source changed: {entry['id']}; review scope again")
    shutil.copytree(existing, output)
    catalog_path = output / "library/catalog.json"
    catalog = json.loads(catalog_path.read_text())
    works = {work["id"]: work for work in catalog["works"]}
    report = {"schema_version": 1, "config_sha256": sha(config.read_bytes()), "works": []}
    with tempfile.TemporaryDirectory(prefix="ga-recovery-adapter-") as scratch:
        for entry in selected:
            work = works[entry["id"]]
            if work.get("content_path"):
                # Rebuild only if this exact previously recovered source is in use.
                old = output / "content" / (entry["id"] + ".json.gz")
                if not old.exists() or json.loads(gzip.decompress(old.read_bytes())).get("source_epub_sha256") != entry["source_sha256"]:
                    raise ValueError(f"Refusing to replace an existing edition: {entry['id']}")
            adapted = Path(scratch) / (entry["id"] + ".epub")
            adaptation = adapted_epub(ROOT / entry["source_path"], adapted)
            passages, details = read_epub(adapted, work["id"], work["title"], entry["scope"])
            if len(passages) != entry["expected_passage_count"]:
                raise ValueError(f"Reviewed section set changed for {work['id']}: {len(passages)}")
            if any(len(passage["text"].strip()) < 100 for passage in passages):
                raise ValueError(f"Empty or truncated recovered section: {work['id']}")
            trimmed = []
            for passage in passages:
                passage["source_label"] = "Wiedergewonnene GA-Arbeitsausgabe / FVN"
                passage["text"] = clean_image_placeholders(passage["text"])
                pages = list(dict.fromkeys(int(page) for page in re.findall(
                    r"#(?:G\d+[a-z]?(?:-\d+)?-\d{4}-SE|SE\d+[a-z]?-)(\d+)", passage["source_text"])))
                passage["metadata"]["page_numbers"] = pages
                passage["metadata"]["page_marker_source"] = "original_fvn_se_page_markers"
                for suffix in entry.get("editorial_suffixes", []):
                    if suffix in passage["text"]:
                        passage["text"] = passage["text"].split(suffix, 1)[0].rstrip()
                        trimmed.append(suffix)
                        details.setdefault("excluded_editorial_transitions", []).append(suffix)
                passage["checksum"] = sha(passage["text"].encode())
            if sorted(trimmed) != sorted(entry.get("editorial_suffixes", [])):
                raise ValueError(f"Reviewed editorial transition changed: {work['id']}")
            payload = {"work_id": work["id"], "title": work["title"], "language": "de",
                       "content_completeness": "complete", "source_url": entry["source_url"],
                       "source_label": "Wiedergewonnene quellengebundene GA-Arbeitsausgabe",
                       "source_epub_sha256": entry["source_sha256"],
                       "passage_count": len(passages), "passages": passages,
                       "proofing": {"status": "working_edition_needs_review", "strict_publishable": False,
                                    "source_retained_for_diff": True, "warnings": [WARNING],
                                    "scope_evidence": entry["scope_evidence"],
                                    "evidence_url": entry["evidence_url"],
                                    "source_adaptation": adaptation, **details}}
            write_json(output / "content" / (work["id"] + ".json.gz"), payload, True)
            work.update(state="sanity_check", proofing_state="needs_ai_sanity_check",
                        content_completeness="complete", content_path=f"/api/catalog/{work['id']}/content",
                        catalog_passage_count=len(passages),
                        source_summary="Wiedergewonnene Arbeitsausgabe. " + entry["scope_evidence"],
                        sanity_checks=[{"id": "scope", "title": "Textgrundlage", "status": "warning", "detail": WARNING}],
                        passages=[{k: passage.get(k) for k in ("id", "title", "ga_page", "source_label", "checksum")}
                                  for passage in passages])
            report["works"].append({"id": work["id"], "source_sha256": entry["source_sha256"],
                                    "source_url": entry["source_url"], "passage_count": len(passages),
                                    "character_count": sum(len(p["text"]) for p in passages)})
    write_json(catalog_path, catalog)
    write_json(output / "library/recovery-import-report.json", report)
    original_report_path = output / "library/import-report.json"
    if original_report_path.exists():
        original_report = json.loads(original_report_path.read_text())
        additions = {item["id"]: item for item in report["works"]}
        for item in original_report["works"]:
            if item["id"] in additions:
                item.update(additions[item["id"]], available=True, source_kind="recovered_fvn_epub")
        original_report["available_count"] = sum(item["available"] for item in original_report["works"])
        original_report["passage_count"] = sum(item.get("passage_count", 0) for item in original_report["works"])
        write_json(original_report_path, original_report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--existing", type=Path, default=ROOT / "server/priv")
    parser.add_argument("--scope", type=Path, default=ROOT / "tools/recovered-reader-scope.json")
    args = parser.parse_args()
    build(args.scope, args.existing, args.output)
