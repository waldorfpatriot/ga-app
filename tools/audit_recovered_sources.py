#!/usr/bin/env python3
"""Verify downloaded recovery witnesses and summarize all 143 original gaps."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research/unavailable-recovery"
REPORTS = [ROOT / ("tools/recovery-" + name + ".json")
           for name in ("early", "education-art", "new-lectures")]
PAIRS = [("path", "sha256"), ("file", "sha256"), ("local_path", "sha256"),
         ("original_path", "original_sha256"), ("text_path", "text_sha256"),
         ("local_original_path", "original_sha256"),
         ("text_file", "text_sha256"), ("index_path", "index_sha256"),
         ("combined_text_path", "combined_text_sha256"),
         ("candidate_path", "candidate_sha256"),
         ("candidate_text_path", "candidate_text_sha256"),
         ("metadata_path", "metadata_sha256"),
         ("epub_text_path", "epub_text_sha256"),
         ("reader_candidate_path", "reader_candidate_sha256"),
         ("source_index", "source_index_sha256")]


def run(output: Path):
    checked, visited = {}, set()

    def local(path):
        resolved = (ROOT / path).resolve()
        if not resolved.is_relative_to(RESEARCH.resolve()):
            raise ValueError(f"Witness escaped recovery directory: {path}")
        return resolved

    def walk(value):
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for file_key, hash_key in PAIRS:
                if value.get(file_key) and value.get(hash_key):
                    path, expected = value[file_key], value[hash_key]
                    digest = hashlib.sha256(local(path).read_bytes()).hexdigest()
                    if digest != expected:
                        raise ValueError(f"Recovery witness hash mismatch: {path}")
                    checked[path] = digest
            for key in ("source_index", "manifest_path", "manifest_file"):
                path = value.get(key)
                if isinstance(path, str) and path.endswith(".json") and path not in visited:
                    visited.add(path)
                    walk(json.loads(local(path).read_text()))
            for item in value.values():
                if isinstance(item, (dict, list)):
                    walk(item)

    records = {}
    manifests = {}
    for report in REPORTS:
        data = json.loads(report.read_text())
        walk(data)
        for row in data.get("works", data.get("records", data.get("rows", []))):
            work_id = row.get("id", row.get("work_id"))
            if work_id in records:
                raise ValueError(f"Duplicate assigned recovery row: {work_id}")
            records[work_id] = row
            manifests[work_id] = str(report.relative_to(ROOT))
    mirror = RESEARCH / "new-lectures/mirror-sources.json"
    mirrors = {}
    if mirror.exists():
        data = json.loads(mirror.read_text())
        walk(data)
        mirrors = {row["id"]: row for row in data["sources"] if row.get("source")}
    catalog = json.loads((ROOT / "server/priv/library/catalog.json").read_text())
    imported = {row["id"] for row in json.loads((ROOT / "tools/recovered-reader-scope.json").read_text())["works"]}
    baseline = {row["id"]: row for row in catalog["works"]
                if not row.get("content_path") or row["id"] in imported}
    if set(records) != set(baseline) or len(records) != 143:
        raise ValueError(f"Recovery coverage differs from original gaps: missing={set(baseline)-set(records)}, extra={set(records)-set(baseline)}")
    rows = []
    for work_id, work in baseline.items():
        row = records[work_id]
        archive = row.get("rsarchive", {})
        text_sections = row.get("recovered_sections", archive.get("unique_german_witness_count", archive.get("german_witness_count", 0)))
        files = row.get("source_files", row.get("sources", []))
        source_recovered = bool(text_sections or row.get("text_chars", 0) or any(file.get("sha256") for file in files)
                                or work_id in mirrors or row.get("candidate_path")
                                or row.get("pdf_sha256"))
        classification = row.get("classification", "text_volume")
        status = (classification if classification in {"catalogue_blank_number", "superseded_planned_volume"} else
                  "imported_working_edition" if work_id in imported else
                  "source_recovered_needs_review" if source_recovered else "no_usable_source_recovered")
        rows.append({"id": work_id, "ga_number": work["ga_number"], "title": work["title"],
                     "classification": classification,
                     "recovery_status": status, "german_web_sections": text_sections,
                     "research_manifest": manifests[work_id],
                     "has_partial_preview": bool(row.get("partial_sources")),
                     "has_secondary_ocr_witness": work_id in mirrors,
                     "reader_content_path": work.get("content_path")})
    result = {"schema_version": 1, "original_unavailable_count": len(rows),
              "recovery_counts": dict(Counter(row["recovery_status"] for row in rows)),
              "verified_file_count": len(checked),
              "german_web_section_count": sum(row["german_web_sections"] for row in rows),
              "secondary_ocr_volume_count": len(mirrors),
              "local_reader_available_count": sum(bool(row.get("content_path")) for row in catalog["works"]),
              "rows": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/unavailable-sources.json")
    run(parser.parse_args().output)
