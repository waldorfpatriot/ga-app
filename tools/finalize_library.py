#!/usr/bin/env python3
"""Finalize native library text using GA.ContentPipeline's normalization rules.

The five existing normalized books are never rewritten. Imported page spans are
retained alongside inline source page markers. Source text and annotations stay
untouched; this pass changes reader text and its corresponding catalog metadata.
Only Python's standard library is required, including on the import host.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path

CORE = {"ga-003", "ga-004", "ga-009", "ga-010", "ga-013"}
PAGE_MARKER = re.compile(r"\[(\d{1,4})\]")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_text(text: str) -> tuple[str, list[int]]:
    """Match ContentPipeline.extract_page_markers/1 without editing spelling."""
    pages = list(dict.fromkeys(int(match) for match in PAGE_MARKER.findall(text)))
    text = PAGE_MARKER.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"^[ \t]+|[ \t]+$", "", text, flags=re.M)
    return text.strip(), pages


def page_label(pages: list[int]) -> str | None:
    if not pages:
        return None
    return f"S. {min(pages)}" if len(pages) == 1 else f"S. {min(pages)}–{max(pages)}"


def content_file(root: Path, work_id: str) -> Path:
    # Match the server's compressed import preference, preserving plain core bytes.
    suffixes = (".json", ".json.gz") if work_id in CORE else (".json.gz", ".json")
    files = [root / "content" / (work_id + suffix) for suffix in suffixes]
    present = [path for path in files if path.is_file()]
    if not present:
        raise ValueError(f"No content file for {work_id}")
    return present[0]


def read_json(path: Path) -> dict:
    data = path.read_bytes()
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    return json.loads(data)


def write_json(path: Path, payload: dict):
    data = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    path.write_bytes(gzip.compress(data, compresslevel=9, mtime=0) if path.suffix == ".gz" else data)


def finalize(root: Path) -> dict:
    catalog_path = root / "library" / "catalog.json"
    catalog = read_json(catalog_path)
    report = {"available_count": 0, "normalized_work_count": 0, "passage_count": 0,
              "changed_text_count": 0, "added_inline_page_count": 0, "core_sha256": {}}
    counts = {}
    for work in catalog["works"]:
        if not work.get("content_path"):
            continue
        report["available_count"] += 1
        path = content_file(root, work["id"])
        if work["id"] in CORE:
            report["core_sha256"][work["id"]] = digest(path.read_bytes())
            report["passage_count"] += len(read_json(path)["passages"])
            continue
        payload = read_json(path)
        if payload.get("work_id") != work["id"]:
            raise ValueError(f"Payload identity differs from catalog for {work['id']}")
        passages = payload["passages"]
        summaries = {entry["id"]: entry for entry in work["passages"]}
        if len(summaries) != len(passages):
            raise ValueError(f"Catalog passage count differs from content for {work['id']}")
        for passage in passages:
            text, inline_pages = normalize_text(passage["text"])
            if not text:
                raise ValueError(f"Empty normalized passage: {work['id']}/{passage['id']}")
            report["changed_text_count"] += text != passage["text"]
            metadata = passage.setdefault("metadata", {})
            span_pages = metadata.get("page_numbers", [])
            if not isinstance(span_pages, list) or any(type(page) is not int for page in span_pages):
                raise ValueError(f"Invalid source page metadata: {work['id']}/{passage['id']}")
            pages = list(dict.fromkeys(span_pages + inline_pages))
            report["added_inline_page_count"] += len(pages) - len(set(span_pages))
            metadata["page_numbers"] = pages
            if inline_pages:
                metadata["page_marker_source"] = (
                    "epub_source_page_labels_and_original_inline_bracket_markers"
                    if span_pages else "original_inline_bracket_markers"
                )
            passage["text"] = text
            passage["checksum"] = digest(text.encode("utf-8"))
            passage["ga_page"] = page_label(pages)
            if passage["id"] not in summaries:
                raise ValueError(f"Passage missing from catalog: {work['id']}/{passage['id']}")
            summaries[passage["id"]].update(checksum=passage["checksum"], ga_page=passage["ga_page"])
        write_json(path, payload)
        report["normalized_work_count"] += 1
        report["passage_count"] += len(passages)
        counts[work["id"]] = sum(len(passage["text"]) for passage in passages)
    write_json(catalog_path, catalog)
    import_report_path = root / "library" / "import-report.json"
    if import_report_path.exists():
        import_report = read_json(import_report_path)
        for work in import_report.get("works", []):
            if work["id"] in counts:
                work["character_count"] = counts[work["id"]]
        write_json(import_report_path, import_report)
    for work_id, before in report["core_sha256"].items():
        if digest(content_file(root, work_id).read_bytes()) != before:
            raise ValueError(f"Core book was unexpectedly rewritten: {work_id}")
    report["verification"] = verify(root)
    write_json(root / "library" / "finalization-report.json", report)
    return report


def verify(root: Path) -> dict:
    """Read all advertised payloads and independently check text and summaries."""
    catalog = read_json(root / "library" / "catalog.json")
    result = {"catalog_count": len(catalog["works"]), "available_count": 0,
              "passage_count": 0, "normalized_checksum_mismatches": [],
              "catalog_checksum_mismatches": [], "page_metadata_mismatches": [],
              "remaining_inline_markers": 0, "remaining_word_macros": []}
    for work in catalog["works"]:
        if not work.get("content_path"):
            continue
        result["available_count"] += 1
        path = content_file(root, work["id"])
        payload = read_json(path)
        if payload.get("work_id") != work["id"]:
            raise ValueError(f"Payload identity differs from catalog for {work['id']}")
        summaries = {entry["id"]: entry for entry in work["passages"]}
        passages = payload["passages"]
        if len(summaries) != len(passages) or set(summaries) != {passage["id"] for passage in passages}:
            raise ValueError(f"Catalog passage IDs differ from content for {work['id']}")
        result["passage_count"] += len(passages)
        for passage in passages:
            identity = work["id"] + "/" + passage["id"]
            # Spell the server transformation independently of normalize_text().
            normalized = re.sub(r"\[\d{1,4}\]", "", passage["text"])
            normalized = re.sub(r"[ \t][ \t]+", " ", normalized)
            normalized = "\n".join(line.strip(" \t") for line in normalized.split("\n")).strip()
            checksum = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            if checksum != passage.get("checksum"):
                result["normalized_checksum_mismatches"].append(identity)
            if summaries[passage["id"]].get("checksum") != passage.get("checksum"):
                result["catalog_checksum_mismatches"].append(identity)
            if work["id"] not in CORE:
                if normalized != passage["text"]:
                    result["normalized_checksum_mismatches"].append(identity + ":text_not_normalized")
                pages = passage.get("metadata", {}).get("page_numbers", [])
                label = page_label(pages)
                if passage.get("ga_page") != label or summaries[passage["id"]].get("ga_page") != label:
                    result["page_metadata_mismatches"].append(identity)
                result["remaining_inline_markers"] += len(re.findall(r"\[\d{1,4}\]", passage["text"]))
                if re.search(r"#(?:G\d|SE\d|TI\b|TX\b|BI\b|LI\b|IR\b|HY\b|MU\b)", passage["text"]):
                    result["remaining_word_macros"].append(identity)
        if path.suffix == ".gz" and path.read_bytes()[4:8] != b"\0\0\0\0":
            raise ValueError(f"Non-deterministic gzip modification time: {work['id']}")
    failures = (result["normalized_checksum_mismatches"] or result["catalog_checksum_mismatches"]
                or result["page_metadata_mismatches"] or result["remaining_inline_markers"])
    if failures:
        raise ValueError(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Imported output containing library/ and content/")
    parser.add_argument("--check", "--verify-only", action="store_true", help="Verify existing output without writing")
    arguments = parser.parse_args()
    print(json.dumps(verify(arguments.root) if arguments.check else finalize(arguments.root), ensure_ascii=False))
