#!/usr/bin/env python3
"""Archive the completed Nietzsche acquisition without deleting source/cache files.

Run after acquisition is frozen. Raw files stay byte-identical; local references
inside JSON copies are relocated to the permanent research cache. The cache is
already ignored by the repository's research/* rule. Only the optional public
inventory is intended for version control.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
GROUPS = (
    "gutenberg", "supplements", "musarion", "musarion-extracted",
    "alternates", "historical", "bibliography", "remaining", "private-research",
)
REPOSITORY_TOOLS = (
    "archive_nietzsche_sources.py", "import_nietzsche_sources.py",
    "import_author_library.py",
)
PATH_KEYS = {
    "path", "source_path", "raw_source_path", "normalized_path", "ocr_path",
    "sections_path", "archive_metadata_path", "pdf_path",
    "raw_scan_path", "normalized_source_path",
}
URL_KEYS = ("url", "download_url", "source_url", "source_metadata_url", "raw_scan_url")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Archive:
    def __init__(self, tmp_root: Path, cache_root: Path):
        self.tmp_root = tmp_root.absolute()
        self.cache_root = cache_root.absolute()
        self.paths: dict[Path, Path] = {}
        self.originals: dict[Path, dict] = {}
        self.urls: dict[Path, set[str]] = {}
        self.json_sources: dict[Path, object] = {}
        self.missing_groups: list[str] = []
        inventory_path = self.cache_root / "acquisition-inventory.json"
        previous = json.loads(inventory_path.read_text()) if inventory_path.exists() else {}
        self.previous_cache_root = Path(previous.get("archive_root", str(self.cache_root)))

    def remember_urls(self, path: Path, urls: list[str]) -> None:
        self.urls.setdefault(path, set()).update(
            value for value in urls if isinstance(value, str) and value.startswith(("https://", "http://"))
        )

    def copy_file(self, source: Path, destination: Path) -> None:
        if source.is_symlink():
            raise ValueError(f"Source symlink requires review before archival: {source}")
        if source in self.paths:
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.paths[source] = destination
        self.originals[destination] = {
            "original_sha256": sha256(source), "original_size_bytes": source.stat().st_size,
        }
        shutil.copy2(source, destination)
        if source.suffix.lower() == ".json":
            self.json_sources[source] = json.loads(source.read_text(encoding="utf-8"))

    def prepare(self) -> None:
        for group in GROUPS:
            source = self.tmp_root / f"nietzsche-{group}"
            if not source.is_dir():
                self.missing_groups.append(group)
                continue
            for path in sorted(source.rglob("*")):
                if path.is_file() and not any(part in {"__pycache__", ".DS_Store"} for part in path.parts):
                    self.copy_file(path, self.cache_root / group / path.relative_to(source))
        # Preserve acquisition, extraction, correction and bibliography scripts
        # as executable provenance, separately from the downloaded source trees.
        for source in sorted(self.tmp_root.glob("nietzsche-*.py")):
            self.copy_file(source, self.cache_root / "provenance/scripts/tmp" / source.name)
        for group in GROUPS:
            source = self.tmp_root / f"nietzsche-{group}"
            if source.is_dir():
                for path in sorted(source.rglob("*.py")):
                    target = self.cache_root / "provenance/scripts" / group / path.relative_to(source)
                    # The same script is intentionally retained in both places.
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
                    self.originals[target] = {"original_sha256": sha256(path), "original_size_bytes": path.stat().st_size}
        for name in REPOSITORY_TOOLS:
            source = ROOT / "tools" / name
            if source.exists():
                self.copy_file(source, self.cache_root / "provenance/repository-tools" / name)
        # Keep an existing cache useful after /tmp has gone away, including
        # relocation when the checkout/cache itself has moved.
        written_targets = set(self.paths.values())
        for path in sorted(self.cache_root.rglob("*.json")):
            if path.name != "acquisition-inventory.json" and path not in written_targets:
                self.paths[path] = path
                self.json_sources[path] = json.loads(path.read_text(encoding="utf-8"))

    def relocated_path(self, value: str) -> Path | None:
        if not value.startswith("/"):
            return None
        path = Path(value)
        # /private/tmp is macOS's canonical spelling of /tmp. Do not treat
        # archive.org's /1/items/... server directories as local references.
        if self.tmp_root == Path("/tmp") and value.startswith("/private/tmp/"):
            path = Path("/tmp") / path.relative_to("/private/tmp")
        if path == self.previous_cache_root or self.previous_cache_root in path.parents:
            return self.cache_root / path.relative_to(self.previous_cache_root)
        if path == self.cache_root or self.cache_root in path.parents:
            return path
        for group in GROUPS:
            base = self.tmp_root / f"nietzsche-{group}"
            if path == base or base in path.parents:
                target = self.cache_root / group / path.relative_to(base)
                if not path.exists() and not target.exists():
                    raise FileNotFoundError(f"Referenced Nietzsche acquisition file is missing: {path}")
                return target
        if path in self.paths:
            return self.paths[path]
        if path.parent == self.tmp_root and path.name.startswith("nietzsche-"):
            if not path.is_file():
                raise FileNotFoundError(f"Referenced Nietzsche acquisition file is missing: {path}")
            target = self.cache_root / "provenance/supporting-files" / path.name
            self.copy_file(path, target)
            return target
        return None

    def rewrite_json(self, value: object) -> object:
        if isinstance(value, dict):
            return {self.rewrite_json(key): self.rewrite_json(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.rewrite_json(item) for item in value]
        if isinstance(value, str):
            target = self.relocated_path(value)
            return str(target) if target is not None else value
        return value

    def collect_urls(self, value: object, source: Path) -> None:
        if isinstance(value, dict):
            urls = [value[key] for key in URL_KEYS if isinstance(value.get(key), str)]
            for key in PATH_KEYS:
                reference = value.get(key)
                if isinstance(reference, str):
                    path = self.relocated_path(reference)
                    if path is not None:
                        self.remember_urls(path, urls)
            metadata = value.get("metadata", {})
            identifier = metadata.get("identifier") if isinstance(metadata, dict) else None
            if isinstance(identifier, str) and isinstance(value.get("files"), list):
                # Internet Archive metadata lists all hosted filenames, even
                # when a download report has not yet been written for a scan.
                self.remember_urls(self.paths[source], [f"https://archive.org/metadata/{quote(identifier, safe='')}"])
                for item in value["files"]:
                    if isinstance(item, dict) and isinstance(item.get("name"), str):
                        local = source.parent / item["name"]
                        if local in self.paths:
                            url = f"https://archive.org/download/{quote(identifier, safe='')}/{quote(item['name'], safe='')}"
                            self.remember_urls(self.paths[local], [url])
            for child in value.values():
                self.collect_urls(child, source)
        elif isinstance(value, list):
            for child in value:
                self.collect_urls(child, source)

    def finish_json(self) -> None:
        processed: set[Path] = set()
        # Relocation may discover further JSON sidecars outside the source
        # directories. Process those in the same pass instead of leaving /tmp
        # dependencies in the durable manifests.
        while remaining := sorted(set(self.json_sources) - processed):
            for source in remaining:
                value = self.json_sources[source]
                self.collect_urls(value, source)
                write_json(self.paths[source], self.rewrite_json(value))
                processed.add(source)
        for source, destination in self.paths.items():
            if destination.parent == self.cache_root / "gutenberg" and source.stem.startswith("pg") and source.stem[2:].isdigit():
                ebook = source.stem[2:]
                self.remember_urls(destination, [f"https://www.gutenberg.org/ebooks/{ebook}", f"https://www.gutenberg.org/cache/epub/{ebook}/pg{ebook}.txt"])

    def inventory(self) -> dict:
        previous_path = self.cache_root / "acquisition-inventory.json"
        previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
        previous_files = {item["path"]: item for item in previous.get("files", [])}
        files = []
        for path in sorted(self.cache_root.rglob("*")):
            if not path.is_file() or path == previous_path:
                continue
            relative = path.relative_to(self.cache_root).as_posix()
            old = previous_files.get(relative, {})
            originals = self.originals.get(path, {key: old[key] for key in ("original_sha256", "original_size_bytes") if key in old})
            urls = sorted(self.urls.get(path, set()) | set(old.get("urls", [])))
            files.append({"path": relative, "sha256": sha256(path), "size_bytes": path.stat().st_size,
                          **originals, **({"urls": urls} if urls else {})})
        return {"schema_version": 1, "archive_root": str(self.cache_root),
                "scope": "Local acquisition cache including unintegrated references and scans; reader coverage is documented separately.",
                "path_relocation": "JSON filesystem references point to this cache; original and archived hashes distinguish relocated JSON from unchanged downloads.",
                "source_groups": list(GROUPS), "missing_source_groups": self.missing_groups,
                "file_count": len(files), "total_size_bytes": sum(item["size_bytes"] for item in files), "files": files}


def public_summary(edition: Path, inventory: dict) -> dict:
    manifest_path = edition / "source-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    catalog_path = edition / "library/catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    integrated = {work["id"] for work in catalog["works"]}
    declared = {work["work_id"] for work in manifest["works"]}
    if integrated - declared:
        raise ValueError("Catalog works lack source provenance: " + ", ".join(sorted(integrated - declared)))
    by_hash: dict[str, list[str]] = {}
    for item in inventory["files"]:
        by_hash.setdefault(item.get("original_sha256", item["sha256"]), []).append(item["path"])
    works = []
    for work in manifest["works"]:
        if work["work_id"] not in integrated:
            continue
        relative = Path(work["normalized_source_path"])
        path = edition / relative
        if relative.is_absolute() or edition.resolve() not in path.resolve().parents:
            raise ValueError(f"Integrated source must be inside the edition: {relative}")
        text = path.read_text(encoding="utf-8").rstrip("\n")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest != work["normalized_text_sha256"]:
            raise ValueError(f"Integrated source hash mismatch: {work['work_id']}")
        raw_hash = work["raw_source_sha256"]
        works.append({"work_id": work["work_id"], "title": work["title"], "language": work["language"],
                      "normalized_source_path": relative.as_posix(), "normalized_text_sha256": digest,
                      "normalized_source_file_sha256": sha256(path), "normalized_source_size_bytes": path.stat().st_size,
                      "raw_source_sha256": raw_hash, "archived_raw_paths": sorted(by_hash.get(raw_hash, [])),
                      **{key: work[key] for key in ("source_url", "download_url", "source_metadata_url", "acquired_on") if key in work}})
    return {"schema_version": 1, "prepared_on": manifest.get("prepared_on"),
            "scope": "Integrated reader source texts only; acquisition-inventory.json in the ignored Nietzsche research cache lists the full acquisition.",
            "source_manifest_sha256": sha256(manifest_path), "catalog_sha256": sha256(catalog_path),
            "work_count": len(works), "works": works}


def archive_sources(tmp_root: Path, cache_root: Path, edition: Path, write_public_summary: bool = False) -> dict:
    archive = Archive(tmp_root, cache_root)
    archive.prepare()
    archive.finish_json()
    command = (f"python3 tools/import_nietzsche_sources.py --gutenberg-dir {shlex.quote(str(archive.cache_root / 'gutenberg'))} "
               f"--supplements-dir {shlex.quote(str(archive.cache_root / 'supplements'))} "
               f"--musarion-dir {shlex.quote(str(archive.cache_root / 'musarion-extracted'))}")
    readme = archive.cache_root / "REIMPORT.md"
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text("# Nietzsche source cache\n\nRun from the repository root after reviewing the manifests:\n\n```sh\n" + command +
                      "\n```\n\nThis explicitly rebuilds the checked-in Nietzsche source texts. The ordinary author-library importer continues to use those checked-in texts. "
                      "The archived scripts preserve the acquisition/extraction versions; their original temporary paths have not been edited. "
                      "Relocated JSON metadata uses this cache's absolute paths. Rerun the archive command after moving the checkout to relocate references again.\n", encoding="utf-8")
    inventory = archive.inventory()
    write_json(archive.cache_root / "acquisition-inventory.json", inventory)
    if write_public_summary:
        write_json(edition / "provenance/source-inventory.json", public_summary(edition, inventory))
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tmp-root", type=Path, default=Path("/tmp"), help="Acquisition directories and provenance scripts parent")
    parser.add_argument("--archive-root", type=Path, default=ROOT / "research/nietzsche-complete")
    parser.add_argument("--edition-root", type=Path, default=ROOT / "editions/friedrich-nietzsche")
    parser.add_argument("--write-public-summary", action="store_true", help="Write the small integrated-source inventory inside the edition")
    args = parser.parse_args()
    inventory = archive_sources(args.tmp_root, args.archive_root, args.edition_root, args.write_public_summary)
    print(f"Archived {inventory['file_count']} files ({inventory['total_size_bytes']} bytes) in {args.archive_root}.")
    if inventory["missing_source_groups"]:
        print("Absent acquisition groups: " + ", ".join(inventory["missing_source_groups"]))


if __name__ == "__main__":
    main()
