#!/usr/bin/env python3
"""Build isolated author catalogs from attributed, original-language transcripts.

The checked-in sources are the reproducible input. This command does not fetch
network content or rewrite prose: it packages each entire normalized transcript
in the same catalog/content schema as GA, retaining paragraphs and verse. Source
acquisition, edition boundaries and rights evidence live in source-manifest.json.
Run with --check to audit the packaged output without changing any files.
"""

import argparse
import datetime
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITION_SLUGS = (
    "maria-montessori", "friedrich-nietzsche", "karl-may", "jane-austen",
    "arthur-conan-doyle", "hp-lovecraft", "fyodor-dostoevsky",
    "johann-wolfgang-von-goethe", "franz-kafka", "hp-blavatsky",
    "emanuel-swedenborg",
)
UPDATED_AT = "2026-10-10T00:00:00Z"
MAX_PASSAGE_CHARS = 24_000


def original_languages(author):
    """Allowed original languages; omitted lists retain the single-language contract."""
    languages = author.get("original_languages")
    if languages is None:
        languages = [author["language"]] if author.get("language") else []
    if (not isinstance(languages, list) or not languages
            or any(not isinstance(language, str) or not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]+)*", language)
                   for language in languages)
            or len(set(languages)) != len(languages)
            or (author.get("language") and author["language"] not in languages)):
        raise ValueError("Invalid original_languages declaration")
    return languages


def validated_timestamp(value, context="Content"):
    """Require an explicit, reproducible UTC timestamp rather than a rebuild date."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value):
        raise ValueError(f"{context} needs a reproducible UTC timestamp")
    try:
        datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ValueError(f"{context} needs a valid UTC timestamp") from error
    return value


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utf16_length(text):
    return len(text.encode("utf-16-le")) // 2


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def normalize_prose(text):
    """Join physical soft wraps only; keep blank-line paragraph boundaries."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    paragraphs = re.split(r"\n\s*\n", text.strip())
    return "\n\n".join(re.sub(r"\s+", " ", p).strip() for p in paragraphs if p.strip())


def gutenberg_body(text):
    """Require BOTH explicit boundaries; fail closed on malformed downloads."""
    start = re.search(r"\*\*\* START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK .*?\*\*\*", text)
    end = re.search(r"\*\*\* END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK .*?\*\*\*", text)
    if not start or not end or end.start() <= start.end():
        raise ValueError("Source lacks complete ebook boundaries")
    header = text[:start.start()]
    if "posted with permission" in header.lower() or "copyrighted" in header.lower():
        raise ValueError("Restricted ebook requires separate rights clearance")
    return text[start.end():end.start()].strip()


def blocks_for(text, verse=False, heading_indexes=(), verse_indexes=()):
    blocks = []
    offset = 0
    headings = set(heading_indexes)
    verses = set(verse_indexes)
    for index, paragraph in enumerate(text.split("\n\n")):
        length = utf16_length(paragraph)
        if paragraph:
            kind = "heading" if index in headings else "verse" if verse or index in verses else "prose"
            blocks.append({"kind": kind,
                           "start_offset": offset, "end_offset": offset + length})
        offset += length + 2
    return blocks


def split_transcript(text):
    """Split at paragraphs, preserving the full source exactly when rejoined."""
    parts = []
    current = []
    size = 0
    for paragraph in text.split("\n\n"):
        added = len(paragraph) + (2 if current else 0)
        if current and size + added > MAX_PASSAGE_CHARS:
            parts.append("\n\n".join(current))
            current, size = [], 0
        current.append(paragraph)
        size += len(paragraph) + (2 if len(current) > 1 else 0)
    if current:
        parts.append("\n\n".join(current))
    return parts


def section_parts(source, entry):
    """Use reviewed original divisions, splitting long chapters at paragraphs.

    Section boundaries are anchored to the checked-in transcript, rather than
    inferred from short dialogue or capitalized prose during every rebuild.
    """
    paragraphs = source.split("\n\n")
    sections = entry.get("sections", [{"start_paragraph": 0, "title": entry["title"]}])
    starts = [s["start_paragraph"] for s in sections]
    if not starts or starts[0] != 0 or starts != sorted(set(starts)):
        raise ValueError(f"Invalid source section order in {entry['work_id']}")
    all_headings = set(entry.get("heading_paragraphs", []))
    for position, section in enumerate(sections):
        start = section["start_paragraph"]
        end = starts[position + 1] if position + 1 < len(starts) else len(paragraphs)
        if not 0 <= start < end <= len(paragraphs):
            raise ValueError(f"Invalid source section boundary in {entry['work_id']}")
        if "first_paragraph" in section and section["first_paragraph"] != paragraphs[start]:
            raise ValueError(f"Source section anchor mismatch in {entry['work_id']}")
        parts = split_transcript("\n\n".join(paragraphs[start:end]))
        consumed = start
        for index, text in enumerate(parts, start=1):
            count = len(text.split("\n\n"))
            headings = {i - consumed for i in all_headings if consumed <= i < consumed + count}
            title = section["title"] if len(parts) == 1 else f'{section["title"]} · {index}'
            yield title, text, headings
            consumed += count


def package_work(author, entry, source):
    work_id = entry["work_id"]
    timestamp = validated_timestamp(entry.get("content_updated_at", UPDATED_AT), work_id)
    collection_tag = entry.get("collection_tag", "starter-collection")
    if not isinstance(collection_tag, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", collection_tag):
        raise ValueError(f"Invalid collection tag in {work_id}")
    search_terms = entry.get("search_terms", [])
    if not isinstance(search_terms, list) or any(not isinstance(term, str) or not term.strip() for term in search_terms):
        raise ValueError(f"Invalid search terms in {work_id}")
    verse_paragraphs = entry.get("verse_paragraphs", [])
    paragraph_count = len(source.split("\n\n"))
    if (not isinstance(verse_paragraphs, list)
            or any(not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < paragraph_count
                   for i in verse_paragraphs)
            or len(set(verse_paragraphs)) != len(verse_paragraphs)):
        raise ValueError(f"Invalid verse paragraph indexes in {work_id}")
    all_verses = set(verse_paragraphs)
    passages = []
    consumed = 0
    for index, (title, text, headings) in enumerate(section_parts(source, entry), start=1):
        count = len(text.split("\n\n"))
        verses = {i - consumed for i in all_verses if consumed <= i < consumed + count}
        # These are navigation labels, never additions to the author's prose.
        passages.append({
            "id": f"{work_id}-section-{index:03d}", "title": title,
            "ga_page": None, "source_label": entry["source_label"],
            "text": text, "checksum": sha256(text),
            "metadata": {"reading_blocks": blocks_for(text, entry.get("verse", False), headings, verses),
                         "annotations": [], "page_numbers": [], "page_anchors": []},
        })
        consumed += count
    payload = {
        "work_id": work_id, "title": entry["title"], "language": entry["language"],
        "content_completeness": "complete", "passage_count": len(passages),
        "word_count": len(source.split()), "passages": passages,
    }
    catalog_work = {
        "id": work_id, "ga_number": entry["work_label"], "title": entry["title"],
        "author": author["name"], "subtitle": entry.get("subtitle", ""),
        "language": entry["language"], "year_label": str(entry["original_publication_year"]),
        "type": entry.get("type", "book"), "priority": entry["priority"],
        "state": "published", "proofing_state": "needs_ai_sanity_check",
        "source_summary": entry["edition_note"],
        "tags": ["original-language", "public-domain", collection_tag, author["slug"]]
                + search_terms,
        "content_path": f"/api/catalog/{work_id}/content",
        "content_completeness": "complete", "content_updated_at": timestamp,
        "content_revision": hashlib.sha256(json_bytes(payload)).hexdigest(),
        "catalog_passage_count": len(passages),
        "sanity_checks": [{"id": "source-collation", "title": "Source edition",
                           "status": "warning", "detail": entry["quality_note"]}],
        "passages": [{key: p[key] for key in ("id", "title", "ga_page", "source_label", "checksum", "metadata")}
                     for p in passages],
    }
    return catalog_work, payload


def load_sources(slug, editions_root=None, manifest=None):
    edition = (editions_root or ROOT / "editions") / slug
    if manifest is None:
        manifest = json.loads((edition / "source-manifest.json").read_text(encoding="utf-8"))
    if manifest["author"]["slug"] != slug:
        raise ValueError(f"Author identity mismatch in {slug}")
    if not manifest["works"]:
        raise ValueError(f"Empty collection in {slug}")
    languages = original_languages(manifest["author"])
    generated_at = validated_timestamp(manifest.get("generated_at", UPDATED_AT), "Catalog")
    default_updated_at = validated_timestamp(manifest.get("content_updated_at", generated_at), "Content")
    for original in manifest["works"]:
        entry = dict(original)
        entry.setdefault("content_updated_at", default_updated_at)
        entry.setdefault("collection_tag", manifest.get("collection_tag", "starter-collection"))
        validated_timestamp(entry["content_updated_at"], entry["work_id"])
        if entry["language"] not in languages or not entry["is_original_language"]:
            raise ValueError(f"Translation or wrong language in {entry['work_id']}")
        if entry["rights"]["status"] != "public_domain_original":
            raise ValueError(f"Rights not cleared for {entry['work_id']}")
        relative = Path(entry["normalized_source_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Source path must remain inside the edition")
        source = (edition / relative).read_text(encoding="utf-8").rstrip("\n")
        if sha256(source) != entry["normalized_text_sha256"]:
            raise ValueError(f"Transcript checksum mismatch in {entry['work_id']}")
        minimum = entry["minimum_characters"]
        if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum <= 0:
            raise ValueError(f"Invalid transcript minimum in {entry['work_id']}")
        if not source.strip() or len(source) < minimum:
            raise ValueError(f"Incomplete transcript in {entry['work_id']}")
        if not source.startswith(entry["first_text_anchor"]) or not source.endswith(entry["last_text_anchor"]):
            raise ValueError(f"Source boundary mismatch in {entry['work_id']}")
        yield edition, manifest["author"], entry, source


def build_edition(slug, check=False, editions_root=None):
    works = []
    count = 0
    edition = (editions_root or ROOT / "editions") / slug
    manifest = json.loads((edition / "source-manifest.json").read_text(encoding="utf-8"))
    timestamp = validated_timestamp(manifest.get("generated_at", UPDATED_AT), "Catalog")
    for edition, author, entry, source in load_sources(slug, editions_root, manifest):
        work, payload = package_work(author, entry, source)
        path = edition / "library" / "content" / f'{entry["work_id"]}.json'
        data = json_bytes(payload)
        if check:
            if path.read_bytes() != data:
                raise ValueError(f"Packaged content differs from source: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        works.append(work)
        count += len(payload["passages"])
    catalog = {"schema_version": 1, "generated_at": timestamp, "works": works}
    data = json_bytes(catalog)
    path = edition / "library" / "catalog.json"
    if check:
        if path.read_bytes() != data:
            raise ValueError(f"Catalog differs from source: {path}")
    else:
        path.write_bytes(data)
    return len(works), count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edition", choices=EDITION_SLUGS, help="Build one author, or all if omitted")
    parser.add_argument("--check", action="store_true", help="Validate existing output without changing it")
    args = parser.parse_args()
    total_works = total_sections = 0
    for slug in (args.edition,) if args.edition else EDITION_SLUGS:
        works, sections = build_edition(slug, check=args.check)
        print(f"{slug}: {works} complete works, {sections} sections")
        total_works += works
        total_sections += sections
    print(f"{'Verified' if args.check else 'Packaged'} {total_works} works with {total_sections} sections.")


if __name__ == "__main__":
    main()
