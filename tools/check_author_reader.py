#!/usr/bin/env python3
"""Verify every author app's shared reader with isolated, temporary app bundles.

Compiles the production author reader model once, then uses each generated
edition's Info.plist and build configuration. No real purchases, backend calls,
Keychain writes or personal reading data are used.
"""

import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import tempfile
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "apple/AuthorReader"
HARNESS = r'''import Foundation

private struct CheckFailure: Error { let message: String }

@main struct AuthorReaderChecks {
    static func expect(_ condition: @autoclosure () -> Bool, _ message: String) throws {
        guard condition() else { throw CheckFailure(message: message) }
    }

    static func main() throws {
        let args = CommandLine.arguments
        try expect(!AppEdition.isSteiner, "An author app must not identify as Steiner")
        try expect(AppEdition.authorSlug == args[1], "Author slug")
        try expect(AppEdition.bundleIdentifier == args[2], "Bundle identifier")
        try expect(AppEdition.authorName == args[3], "Author attribution")
        try expect(AppEdition.defaultLanguage == args[4], "Original language")
        try expect(AppEdition.workPrefix == args[5], "Work reference prefix")
        try expect(AppEdition.readerBaseURL.absoluteString == args[6], "Catalog service isolation")
        try expect(AccessClient().baseURL.absoluteString == args[7] + "/api/access", "Access service isolation")
        try expect(AccessOption.annual.productID == args[2] + ".annual", "Annual product identifier")
        try expect(AccessOption.supporter.productID == args[2] + ".supporter", "Supporter product identifier")
        try expect(AccessOption.free.productID == nil, "Free requests must not use a purchase product")
        try expect(AccessClient().keychainService.hasPrefix(args[2] + ".access."), "Keychain isolation")
        try expect(AppEdition.storageDirectory == args[2], "Local data isolation")
        try expect(AppEdition.cloudContainerIdentifier == "iCloud." + args[2], "CloudKit isolation")
        try expect(AppEdition.entitlementIdentifier == args[8], "Subscription entitlement")
        if args.contains("--empty") {
            try expect(SeedLibrary.readerVolumes.isEmpty && SeedLibrary.volumes.isEmpty,
                "An empty author collection must not fall back to Steiner books")
            return
        }
        if let index = args.firstIndex(of: "--actual") {
            let expected = try JSONDecoder().decode([String].self, from: Data(args[index + 1].utf8))
            let volumes = SeedLibrary.readerVolumes
            try expect(Set(volumes.map(\.id)) == Set(expected) && volumes.count == expected.count,
                "Every real starter work must be loaded, with no extra author or Steiner works")
            try expect(SeedLibrary.volumes.count == expected.count, "Developer catalog author isolation")
            for volume in volumes {
                try expect(volume.isReadable && volume.downloadedPassageCount == volume.passages.count,
                    "Real starter work must be complete and readable offline: \(volume.id)")
                for passage in volume.passages {
                    try expect(passage.metadata.validReadingBlocks(in: passage.text).count == passage.metadata.readingBlocks.count,
                        "Source headings and prose must remain valid native reading blocks: \(passage.id)")
                    try expect(passage.metadata.validReadingSections(in: passage.text, passageTitle: passage.title).count
                        == passage.metadata.readingSections.count,
                        "Source contents divisions must remain valid: \(passage.id)")
                    try expect(passage.metadata.validPageAnchors(in: passage.text).count == passage.metadata.pageAnchors.count,
                        "Source page anchors must remain valid: \(passage.id)")
                }
                print(try EPUBExporter.export(volume: volume).path)
            }
            return
        }
        try expect(SeedLibrary.readerVolumes.count == 1 && SeedLibrary.volumes.count == 1,
            "Only the author's bundled work should be loaded")
        let volume = SeedLibrary.readerVolumes[0]
        try expect(volume.id == "test-work" && volume.isReadable, "Complete offline author content")
        try expect(volume.gaSortLabel == "0001", "Numeric author work reference sorting")
        print(try EPUBExporter.export(volume: volume).path)
    }
}
'''


def expanded_info(author: dict) -> dict:
    edition = ROOT / "editions" / author["slug"] / "apple"
    settings = {}
    for line in (edition / "Purchases.xcconfig").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("//"):
            key, value = line.split("=", 1)
            settings[key.strip()] = value.strip().replace("/$()/", "//")
    info = plistlib.loads((edition / "Info.plist").read_bytes())
    for key, value in info.items():
        if isinstance(value, str):
            info[key] = re.sub(r"\$\(([^)]+)\)", lambda match: settings.get(match[1], ""), value)
    info.update(CFBundleIdentifier=author["bundle_id"], CFBundleExecutable="checks", CFBundlePackageType="APPL")
    return info


def verify_epub(epub: Path, author: dict, work: dict | None = None, passages: int | None = None) -> None:
    try:
        with zipfile.ZipFile(epub) as archive:
            metadata = ET.fromstring(archive.read("EPUB/package.opf"))
            namespace = {"dc": "http://purl.org/dc/elements/1.1/", "opf": "http://www.idpf.org/2007/opf"}
            assert metadata.find(".//dc:creator", namespace).text == author["author_name"]
            identifiers = [item.text for item in metadata.findall(".//dc:identifier", namespace)]
            assert any(identifier.startswith("urn:" + author["bundle_id"] + ":") for identifier in identifiers)
            assert "Rudolf Steiner" not in archive.read("EPUB/title.xhtml").decode()
            if work is not None:
                assert metadata.find(".//dc:title", namespace).text == work["title"]
                assert metadata.find(".//dc:language", namespace).text == work["language"]
                description = metadata.find(".//dc:description", namespace).text or ""
                title_text = "".join(ET.fromstring(archive.read("EPUB/title.xhtml")).itertext())
                for warning in work.get("sanity_checks", []):
                    if warning["status"] == "warning":
                        assert warning["detail"] in description and warning["detail"] in title_text
            if passages is not None:
                chapters = [item for item in metadata.findall(".//opf:manifest/opf:item", namespace)
                            if item.get("id", "").startswith("chapter-")]
                assert len(chapters) == passages
                assert all("EPUB/" + item.get("href") in archive.namelist() for item in chapters)
    finally:
        shutil.rmtree(epub.parent)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-content", action="store_true", help="Require every author's real starter library.")
    options = parser.parse_args()
    authors = json.loads((ROOT / "editions/authors.json").read_text())["authors"]
    sources = [SHARED / name for name in (
        "AppEdition.swift", "Models.swift", "SeedLibrary.swift", "AccessClient.swift", "EPUBExporter.swift",
    )]
    checked_real_works = 0
    missing_content = []
    with tempfile.TemporaryDirectory(prefix="ga-author-reader-check-") as scratch:
        scratch = Path(scratch)
        source = scratch / "AuthorReaderChecks.swift"
        source.write_text(HARNESS)
        binary = scratch / "checks"
        subprocess.run([
            "swiftc", "-swift-version", "6", "-parse-as-library", *map(str, sources), str(source), "-o", str(binary),
        ], check=True)
        for author in authors:
            bundle = scratch / (author["slug"] + ".app")
            executable = bundle / "Contents/MacOS/checks"
            executable.parent.mkdir(parents=True)
            shutil.copyfile(binary, executable)
            executable.chmod(0o755)
            (bundle / "Contents/Info.plist").write_bytes(plistlib.dumps(expanded_info(author)))
            args = [author[key] for key in (
                "slug", "bundle_id", "author_name", "language", "work_prefix", "reader_base_url", "access_base_url", "entitlement_id",
            )]
            environment = {key: value for key, value in os.environ.items()
                           if key not in {"GA_SERVER_BASE_URL", "GA_ACCESS_BASE_URL", "GA_FRONTEND"}}
            subprocess.run([str(executable), *args, "--empty"], env=environment, check=True)
            resources = bundle / "Contents/Resources"
            catalog = resources / "BundledCatalog"
            catalog.mkdir(parents=True)
            content = resources / "BundledContent"
            content.mkdir()
            passage = {"id": "one", "title": "Chapter", "text": "An author-specific original text.", "source_label": "Fixture"}
            volume = {
                "id": "test-work", "ga_number": author["work_prefix"] + " 001", "title": "Test work",
                "language": author["language"], "type": "book", "state": "published", "proofing_state": "ai_checked",
                "content_path": "/api/catalog/test-work/content", "catalog_passage_count": 1, "content_completeness": "complete",
            }
            (catalog / "catalog.json").write_text(json.dumps({"works": [volume]}))
            (content / "test-work.json").write_text(json.dumps({
                "work_id": "test-work", "passage_count": 1, "content_completeness": "complete", "passages": [passage],
            }))
            result = subprocess.run([str(executable), *args], env=environment, check=True, capture_output=True, text=True)
            verify_epub(Path(result.stdout.strip()), author, volume, 1)
            print(f"{author['slug']}: identity, services, subscriptions, storage, offline isolation and EPUB attribution passed")
            library = ROOT / "editions" / author["slug"] / "library"
            catalog_path = library / "catalog.json"
            if not catalog_path.is_file():
                missing_content.append(author["slug"])
                continue
            works = json.loads(catalog_path.read_text())["works"]
            if not works:
                missing_content.append(author["slug"])
                continue
            shutil.rmtree(catalog)
            catalog.mkdir()
            shutil.copyfile(catalog_path, catalog / "catalog.json")
            shutil.rmtree(content)
            shutil.copytree(library / "content", content)
            result = subprocess.run([
                str(executable), *args, "--actual", json.dumps([work["id"] for work in works]),
            ], env=environment, check=True, capture_output=True, text=True)
            exported = result.stdout.strip().splitlines()
            assert len(exported) == len(works)
            works_by_id = {work["id"]: work for work in works}
            exported_ids = set()
            for path in exported:
                with zipfile.ZipFile(path) as archive:
                    metadata = ET.fromstring(archive.read("EPUB/package.opf"))
                    identifier = metadata.find(".//{http://purl.org/dc/elements/1.1/}identifier").text
                    prefix = "urn:" + author["bundle_id"] + ":"
                    assert identifier.startswith(prefix)
                    work_id = unquote(identifier[len(prefix):].split(":", 1)[0])
                assert work_id in works_by_id and work_id not in exported_ids
                exported_ids.add(work_id)
                work = works_by_id[work_id]
                payload = json.loads((library / "content" / (work["id"] + ".json")).read_text())
                verify_epub(Path(path), author, work, len(payload["passages"]))
            assert exported_ids == set(works_by_id)
            checked_real_works += len(works)
            print(f"{author['slug']}: all {len(works)} real starter works read offline and exported completely")
    print(f"Author reader checks passed for {len(authors)} separate apps.")
    print(f"Verified {checked_real_works} real starter works.")
    if missing_content:
        message = "Missing starter libraries: " + ", ".join(missing_content)
        if options.require_content:
            raise SystemExit(message)
        print(message)


if __name__ == "__main__":
    main()
