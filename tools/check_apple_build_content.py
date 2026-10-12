#!/usr/bin/env python3
"""Verify proofreading content, Apple resources, and an optional built app.

Run from any directory:
    python3 tools/check_apple_build_content.py
    python3 tools/check_apple_build_content.py '/path/to/GA iOS.app'
    python3 tools/check_apple_build_content.py --snapshot /tmp/ga-reader-delivery

The check is read-only and uses the Python standard library. It compares reader
passage metadata, rather than the server's separate catalog business metadata.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import sys

from export_apple_content import WORK_IDS


ROOT = Path(__file__).resolve().parents[1]
CATALOG_FIELDS = ("id", "title", "ga_page", "source_label", "checksum")
OFFLINE_FIELDS = ("id", "title", "ga_page", "source_label", "text", "metadata")


class VerificationError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def read_json(path):
    body = path.read_bytes()
    return json.loads(gzip.decompress(body) if path.suffix == ".gz" else body)


def sha256(body):
    return hashlib.sha256(body).hexdigest()


def reader_safe(value):
    if isinstance(value, dict):
        return {key: reader_safe(child) for key, child in value.items() if key != "source_text"}
    if isinstance(value, list):
        return [reader_safe(child) for child in value]
    return value


def indexed_works(catalog, label):
    works = catalog["works"]
    result = {work["id"]: work for work in works}
    require(len(result) == len(works), f"{label} contains duplicate work IDs")
    return result


def source_path(work_id):
    suffixes = (".json", ".json.gz") if work_id in WORK_IDS else (".json.gz", ".json")
    for suffix in suffixes:
        path = ROOT / "server/priv/content" / (work_id + suffix)
        if path.is_file():
            return path
    raise VerificationError(f"{work_id}: current source content is missing")


def verify_repository(snapshot=None):
    catalog_path = ROOT / "apple/GA/BundledCatalog/catalog.json"
    catalog = read_json(catalog_path)
    works = indexed_works(catalog, "Apple catalog")
    proofing = indexed_works(read_json(ROOT / "server/priv/proofreading/catalog.json"), "Proofreading catalog")
    require(works.keys() == proofing.keys(), "Apple and proofreading catalog work IDs differ")
    advertised = {key for key, work in works.items() if work.get("content_path")}
    reviewed = {key for key, work in proofing.items() if work["available"]}
    require(advertised == reviewed, "Apple and proofreading catalog availability differs")
    expected_offline = {work_id + ".json" for work_id in WORK_IDS}
    offline_root = ROOT / "apple/GA/BundledContent"
    require({path.name for path in offline_root.glob("*.json")} == expected_offline,
            "Offline resources contain missing or unexpected books")
    if snapshot:
        require((snapshot / "catalog.json").read_bytes() == catalog_path.read_bytes(),
                "Public snapshot catalog differs from the Apple catalog")

    section_count = offline_count = 0
    for work_id, work in works.items():
        if work_id not in advertised:
            require(work.get("content_completeness") == "unavailable" and not work["passages"],
                    f"{work_id}: unavailable Apple entry advertises readable content")
            continue
        require(work.get("content_completeness") == "complete", f"{work_id}: Apple entry is incomplete")
        path = source_path(work_id)
        source = read_json(path)
        require(source["work_id"] == work_id, f"{work_id}: source identity differs")
        require(sha256(path.read_bytes()) == proofing[work_id]["after_sha256"],
                f"{work_id}: source differs from the applied proofreading ledger")
        passages = source["passages"]
        require(passages and len({passage["id"] for passage in passages}) == len(passages),
                f"{work_id}: source passage IDs are missing or duplicated")
        require(work.get("catalog_passage_count", len(work["passages"])) == len(passages),
                f"{work_id}: Apple catalog section count is stale")
        require([p["id"] for p in work["passages"]] == [p["id"] for p in passages],
                f"{work_id}: Apple catalog section IDs or order are stale")
        for source_passage, advertised_passage in zip(passages, work["passages"]):
            passage_id = source_passage["id"]
            require(source_passage.get("checksum") == sha256(source_passage["text"].encode("utf-8")),
                    f"{passage_id}: source text checksum is invalid")
            differences = [key for key in CATALOG_FIELDS
                           if advertised_passage.get(key) != source_passage.get(key)]
            require(not differences, f"{passage_id}: Apple catalog has stale {', '.join(differences)}")
            if "metadata" in advertised_passage:
                require(advertised_passage["metadata"] == reader_safe(source_passage.get("metadata", {})),
                        f"{passage_id}: Apple catalog reader metadata is stale")
        section_count += len(passages)

        if work_id in WORK_IDS:
            expected = {
                "work_id": work_id, "content_completeness": "complete", "passage_count": len(passages),
                "passages": [{key: reader_safe(passage[key]) for key in OFFLINE_FIELDS if key in passage}
                             for passage in passages],
            }
            require(read_json(offline_root / (work_id + ".json")) == expected,
                    f"{work_id}: offline text or reader metadata differs from current proofreading content; "
                    "run tools/export_apple_content.py")
            offline_count += len(passages)

        if snapshot:
            content_path = snapshot / "api/catalog" / work_id / "content"
            body = content_path.read_bytes()
            content = json.loads(body)
            require(content["work_id"] == work_id and content.get("content_completeness") == "complete",
                    f"{work_id}: public snapshot content is incomplete or has the wrong identity")
            require(content.get("passage_count") == len(passages), f"{work_id}: public snapshot count is stale")
            require(content["passages"] == reader_safe(passages),
                    f"{work_id}: public snapshot text or reader metadata is stale")
            require(content.get("table_of_contents", []) == reader_safe(source.get("table_of_contents", [])),
                    f"{work_id}: public snapshot contents targets are stale")
            manifest = read_json(content_path.with_name("manifest"))
            [manifest_bundle] = manifest["bundles"]
            require(manifest_bundle["checksum"] == sha256(body) and manifest_bundle["byte_size"] == len(body),
                    f"{work_id}: public snapshot manifest differs from content bytes")
            if "content_revision" in work or "content_updated_at" in work:
                require(work.get("content_revision") == sha256(body),
                        f"{work_id}: catalog content revision differs from exact public content bytes")
                date = work.get("content_updated_at")
                require(isinstance(date, str) and date, f"{work_id}: versioned catalog has no content update date")
                require(datetime.fromisoformat(date.replace("Z", "+00:00")).tzinfo is not None,
                        f"{work_id}: content update date must identify its timezone")
                for key in ("content_revision", "content_updated_at"):
                    require(manifest["work"].get(key) == work[key],
                            f"{work_id}: manifest work {key} differs from the catalog")

    return len(works), len(advertised), section_count, offline_count


def verify_app(app):
    require(app.is_dir(), f"Built app does not exist: {app}")
    resources = app / "Contents/Resources" if (app / "Contents/Resources").is_dir() else app
    for directory in ("BundledCatalog", "BundledContent"):
        expected_root = ROOT / "apple/GA" / directory
        actual_root = resources / directory
        expected = {path.name for path in expected_root.glob("*.json")}
        actual = {path.name for path in actual_root.glob("*.json")}
        require(expected == actual, f"Built app has missing or unexpected {directory} JSON resources")
        for name in sorted(expected):
            require((expected_root / name).read_bytes() == (actual_root / name).read_bytes(),
                    f"Built app contains stale {directory}/{name}; rebuild the app")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path, nargs="?", help="Built iOS/macOS .app bundle or its resource directory")
    parser.add_argument("--snapshot", type=Path, help="Also verify all exported public text and reader metadata")
    args = parser.parse_args()
    try:
        works, readable, sections, offline = verify_repository(args.snapshot)
        if args.app:
            verify_app(args.app)
        checks = ["current proofreading hashes", "catalog passage metadata", "offline text and reader metadata"]
        if args.snapshot:
            checks.append("all public snapshot passages and manifests")
        if args.app:
            checks.append("exact built resource bytes")
        print(f"Apple content passed: {works} catalog entries, {readable} readable works, {sections:,} sections, "
              f"{len(WORK_IDS)} offline books / {offline} sections; {', '.join(checks)}.")
        return 0
    except (VerificationError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"Apple content check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
