#!/usr/bin/env python3
"""Reproduce the Nietzsche extension from archived historical source transcripts.

Acquisition never uses Nietzsche Source, Zeno or Kolimo transcripts with a
noncommercial restriction. Raw downloads and explicit literary boundaries are
recorded in the source inventory; this command packages only author text.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote, unquote

from import_author_library import gutenberg_body, normalize_prose

ROOT = Path(__file__).resolve().parents[1]
EDITION = ROOT / "editions/friedrich-nietzsche"
DATE = "2026-10-11"
STAMP = DATE + "T00:00:00Z"

# IDs 001/002 and their source text remain unchanged for existing annotations.
GUTENBERG = [
    ("nietzsche-003", 7206, "Die Geburt der Tragödie", 1872,
     "Versuch einer Selbstkritik.", ["Versuch einer Selbstkritik.", "Vorwort an Richard Wagner."]),
    ("nietzsche-004", 7207, "Menschliches, Allzumenschliches I", 1878,
     "An Stelle einer Vorrede.", ["An Stelle einer Vorrede.", "Vorrede.",
      "Erstes Hauptstück.", "Zweites Hauptstück.", "Drittes Hauptstück.",
      "Viertes Hauptstück.", "Fünftes Hauptstück.", "Sechstes Hauptstück.",
      "Siebentes Hauptstück.", "Achtes Hauptstück.", "Neuntes Hauptstück.", "Unter Freunden."]),
    ("nietzsche-005", 7203, "Götzen-Dämmerung", 1889,
     "Vorwort.", ["Vorwort.", "Sprüche und Pfeile.", "Das Problem des Sokrates.",
      'Die "Vernunft" in der Philosophie.', 'Wie die "wahre Welt" endlich zur Fabel wurde.',
      "Moral als Widernatur.", "Die vier grossen Irrthümer.", 'Die "Verbesserer" der Menschheit.',
      "Was den Deutschen abgeht.", "Streifzüge eines Unzeitgemässen.", "Was ich den Alten verdanke.",
      "Der Hammer redet."]),
    ("nietzsche-006", 7202, "Ecce homo", 1908,
     "Vorwort", ["Vorwort", "Warum ich so weise bin.", "Warum ich so klug bin.",
      "Warum ich so gute Bücher schreibe.", "Die Geburt der Tragödie.", "Die Unzeitgemässen.",
      "Menschliches, Allzumenschliches.", "Morgenröthe.", "Die fröhliche Wissenschaft.",
      "Also sprach Zarathustra.", "Jenseits von Gut und Böse.", "Genealogie der Moral.",
      "Götzen-Dämmerung.", "Der Fall Wagner.", "Warum ich ein Schicksal bin."]),
]

# Reviewed historical headings. These are navigation labels; the actual source
# paragraph is kept byte-for-byte and anchored on every re-import.
HISTORICAL_HEADINGS = {
    "nietzsche-022": ["Democritea", "Einleitung in das Studium der classischen Philologie", "Homer's Wettkampf"],
    "nietzsche-023": ["Versuch einer Selbstkritik. (1886)", "Die Geburt der Tragödie aus dem Geiste der Musik", "Die dionysische Weltanschauung."],
    "nietzsche-024": ["Ueber das Pathos der Wahrheit", "Die vorplatonischen Philosophen", "Einleitung in das Studium der platonischen Dialoge"],
    "nietzsche-025": ["Der Gottesdienst der Griechen", "Einzelne Gedanken aus den Jahren 1869-1875"],
    "nietzsche-026": ["1, Ueber Wahrheit und Lüge im aussermoralischen Sinne.", "David Strauss, der Bekenner und der Schriftsteller"],
    "nietzsche-027": ["Drittes Stück Schopenhauer als Erzieher", "Gedanken und Entwürfe zu der Betrachtung: Wir Philologen", "Mahnruf an die Deutschen.", "Richard Wagner in Bayreuth.", "Gedanken zu der Betrachtung: Lesen und Schreiben"],
    "nietzsche-028": ["Unter Freunden", "Zwei Vorreden und ein Epilog"],
    "nietzsche-029": ["Vermischte Meinungen und Sprüche", "Der Wanderer und sein Schatten"],
    "nietzsche-030": ["Gedanken über Moral aus der Zeit der Morgenröthe"],
    "nietzsche-031": ["Aus der Zeit der Fröhlichen Wissenschaft"],
    "nietzsche-032": ["Vorrede zur zweiten Ausgabe.", "Erstes Buch.", "Zweites Buch.", "Drittes Buch.", "Fünftes Buch.", "Lieder des Prinzen Vogelfrei."],
    "nietzsche-034": ["Zur Kritik des Manu-Gesetzbuches.", "Die Griechen als Menschenkenner.", "Aus dem Vorreden-Material"],
    "nietzsche-035": ["Erste Abhandlung:", "Zweite Abhandlung:", "Dritte Abhandlung:"],
    "nietzsche-037": ["Götzen -Dämmerung", "Erstes Buch. Der Antichrist. Versuch einer Kritik des Christenthums.", "Nietzsche contra Wagner"],
    "nietzsche-038": ["Anhang: Pläne und Entwürfe"],
    "nietzsche-039": ["Nachträge"],
    "nietzsche-040": ["SCHERZ, LIST UND RACHE«", "LIEDER DES PRINZEN VOGELFREI", "Zarathustra-Lieder", "Dionysos- Dithyramben"],
    "nietzsche-041": ["Ecce homo"],
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def portable_provenance(value):
    if isinstance(value, dict):
        return {key: portable_provenance(item) for key, item in value.items()}
    if isinstance(value, list):
        return [portable_provenance(item) for item in value]
    if isinstance(value, str) and value.startswith(str(ROOT) + "/"):
        return str(Path(value).relative_to(ROOT))
    return value


def entry_for(work_id, title, year, language, text, raw, source_url, download_url,
              edition_note, quality_note, **extra):
    number = int(work_id.rsplit("-", 1)[1])
    return {
        "work_id": work_id, "work_label": f"FN {number:03d}", "title": title,
        "language": language, "is_original_language": True,
        "original_publication_year": year, "priority": max(1, 100 - number),
        "source_url": source_url, "download_url": download_url,
        "source_label": f"{title} · historische Originalausgabe",
        "acquired_on": DATE, "raw_source_sha256": digest(raw),
        "normalized_source_path": f"library/sources/{work_id}.txt",
        "normalized_text_sha256": digest(text.encode()),
        "minimum_characters": len(text), "character_count": len(text),
        "word_count": len(text.split()), "first_text_anchor": text[:120],
        "last_text_anchor": text[-120:], "content_updated_at": STAMP,
        "collection_tag": "historical-collected-works", "edition_note": edition_note,
        "quality_note": quality_note,
        "rights": {
            "status": "public_domain_original", "scope": ["Germany", "United States"],
            "author_death_year": 1900,
            "german_author_copyright_expired_on": "1971-01-01",
            "german_basis": ["https://www.gesetze-im-internet.de/urhg/__64.html",
                             "https://www.gesetze-im-internet.de/urhg/__69.html"],
            "us_basis": "Original historical edition published before 1931; only the author's underlying original text is imported.",
            "exclusions": "Modern translations, introductions by other authors, editorial afterwords and protected critical apparatus excluded.",
        }, **extra,
    }


def import_gutenberg(raw_dir):
    entries = []
    for wid, ebook, title, year, start, headings in GUTENBERG:
        path = raw_dir / f"pg{ebook}.txt"
        raw = path.read_bytes()
        body = gutenberg_body(raw.decode("utf-8-sig")).replace("\r\n", "\n").replace("\r", "\n")
        paragraphs = re.split(r"\n\s*\n", body.strip())
        # Gutenberg indents verse lines, while its physical prose wraps start
        # at column zero. Preserve every such stanza, including quoted poems.
        normalized = ["\n".join(line.strip() for line in p.strip("\n").splitlines())
                      if len(p.splitlines()) > 1 and
                      all(line.startswith("    ") for line in p.splitlines() if line.strip())
                      else normalize_prose(p)
                      for p in paragraphs if p.strip()]
        assert normalized.count(start) == 1, (wid, "ambiguous literary boundary")
        normalized = normalized[normalized.index(start):]
        if ebook == 7202:
            # Archive-added contents between the preface and the first chapter.
            a = normalized.index("Inhalt")
            assert normalized[a + 1].replace("\n", " ").startswith("Warum ich so weise bin. Warum ich so klug bin.")
            assert normalized[a + 2].startswith("An diesem vollkommnen Tage")
            normalized[a:a + 2] = []
        text = "\n\n".join(normalized)
        indexes = [normalized.index(h) for h in headings]
        assert indexes == sorted(set(indexes)), (wid, "chapter order")
        # GT must include every original chapter, not only its later self-critique.
        if ebook == 7206:
            chapter_start = normalized.index("Vorwort an Richard Wagner.")
            numerals = [(i, p) for i, p in enumerate(normalized) if i > chapter_start and re.fullmatch(r"\d+\.", p)]
            assert [int(p[:-1]) for _, p in numerals] == list(range(1, 26))
            indexes += [i for i, _ in numerals]
        indexes.sort()
        (EDITION / "library/sources" / f"{wid}.txt").write_text(text + "\n", encoding="utf-8")
        original_url = f"https://www.gutenberg.org/ebooks/{ebook}"
        entry = entry_for(wid, title, year, "de", text, raw, original_url,
                          f"https://www.gutenberg.org/cache/epub/{ebook}/pg{ebook}.txt",
                          f"Vollständiger literarischer Text der historischen Ausgabe, digitalisiert als E-Book {ebook}. Quellenangabe: {original_url}. Archivrahmen und nicht vom Autor stammende Angaben entfernt; Originalorthografie erhalten.",
                          "Vollständige Quellentranskription mit geprüften Werkgrenzen und Kapitelstruktur. Eine vollständige menschliche Kollation gegen den historischen Druck steht noch aus.",
                          sections=[{"start_paragraph": i, "title": normalized[i], "first_paragraph": normalized[i]} for i in indexes],
                          heading_paragraphs=indexes,
                          verse_paragraphs=[i for i, p in enumerate(normalized) if "\n" in p],
                          source_metadata_url=original_url,
                          normalization="Archive wrapper and non-author front matter removed; physical prose wraps joined; indented closing poem retained.")
        entries.append(entry)
    return entries


def import_supplements(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    entries = []
    for item in manifest["entries"]:
        wid = item["app_work_id"]
        if not wid.startswith("nietzsche-"):
            wid = "nietzsche-" + wid
        text = Path(item["normalized_path"]).read_text().rstrip("\n")
        raw = Path(item["raw_source_path"]).read_bytes()
        assert digest(raw) == item["raw_source_sha256"]
        assert text.startswith(item["first"]) and text.endswith(item["last"])
        assert item["rights_public_domain"]
        cursor = 0
        sections = []
        for section in item["sections"]:
            body = section["text"].rstrip("\n")
            sections.append({"start_paragraph": cursor, "title": section["title"],
                             "first_paragraph": body.split("\n\n")[0]})
            cursor += len(body.split("\n\n"))
        assert "\n\n".join(s["text"].rstrip("\n") for s in item["sections"]) == text
        title = item["title"]
        if item["id"] == "philologica-3":
            title += " (Haupttexte ohne Fußnoten)"
        historical_year = {"jugendschriften": 1922, "philologica-1": 1910,
                "philologica-2": 1912, "philologica-3": 1913,
                "briefe-historische-auswahl": 1902}.get(item["id"])
        year = item.get("original_publication_year", historical_year or int(re.search(r"\d{4}", item["year"]).group()))
        (EDITION / "library/sources" / f"{wid}.txt").write_text(text + "\n", encoding="utf-8")
        note = f"{item['scope']} Quelle: {item['source_url']}. {item['rights_note']}"
        entry = entry_for(wid, title, year, item["lang"], text, raw,
                          item["source_url"], item["download_url"], note, item["quality_note"],
                          sections=sections, original_languages=item["original_languages"],
                          source_pages=item.get("source_pages", []),
                          verse_paragraphs=[i for i, p in enumerate(text.split("\n\n")) if "\n" in p],
                          verse=item.get("verse", False),
                          subtitle="Historische Arbeitsfassung · " + item["year"],
                          source_extent=item["scope"],
                          normalization="Reviewed literary boundaries; no generated author prose. See quality note for the historical source's limitations.")
        # Preserve provenance of independently transcribed originals without
        # carrying private research scans into the distributable manifest.
        for key in ("raw_source_kind", "source_print_edition", "original_publication_date"):
            if item.get(key):
                entry[key] = item[key]
        if item.get("source_digital_representation_rights"):
            entry["rights"]["consulted_digital_representation"] = {
                "label": item["source_digital_representation_rights"],
                "rights_url": item["source_digital_representation_rights_url"],
                "source_usage_policy_url": item["source_usage_policy_url"],
                "policy_review_date": item["source_usage_policy_review_date"],
                "policy_observation": item["source_usage_policy_observation"],
                "scan_bundled_or_published": False,
            }
        if item["id"] == "homer" or item.get("transcript_license"):
            entry["rights"]["transcript_license"] = item.get("transcript_license", "CC BY-SA 4.0")
            entry["rights"]["transcript_license_url"] = item.get("transcript_license_url", "https://creativecommons.org/licenses/by-sa/4.0/")
            page_title = unquote(item["source_url"].split("/wiki/", 1)[-1])
            history = item.get("transcript_history_url", f"https://de.wikisource.org/w/index.php?title={quote(page_title)}&action=history")
            entry["rights"]["transcript_history_url"] = history
            if item.get("attribution"):
                entry["rights"]["transcript_attribution"] = item["attribution"]
            entry["edition_note"] += f" Die angepasste Wikisource-Transkription wird unter {entry['rights']['transcript_license']} bereitgestellt ({entry['rights']['transcript_license_url']}); geändert wurden Seiten-/Korrekturmarkierungen und Navigationsaufteilung. Autoren und Bearbeitungsgeschichte: {history}."
        entries.append(entry)
    return entries


def import_musarion(directory):
    entries = []
    # One reviewed extraction manifest per historical volume; archival
    # registers (22/23) contain editorial material and are never reader books.
    for path in sorted(directory.glob("nietzsche-*.json")):
        item = json.loads(path.read_text())
        wid = item["id"]
        archived_text = Path(item["source_path"]).read_bytes()
        assert digest(archived_text) == item["sha256"]
        text = archived_text.decode("utf-8").rstrip("\n")
        raw = Path(item["raw_source_path"]).read_bytes()
        assert digest(raw) == item["source_sha256"]
        volume = item.get("volume")
        assert volume is None or volume < 22
        paragraphs = text.split("\n\n")
        indexes = [0]
        historical_headings = item["contained_works"][1:] if wid == "nietzsche-045" else HISTORICAL_HEADINGS.get(wid, [])
        for heading in historical_headings:
            assert paragraphs.count(heading) == 1, (wid, heading, "historical heading anchor")
            indexes.append(paragraphs.index(heading))
        indexes = sorted(set(indexes))
        (EDITION / "library/sources" / f"{wid}.txt").write_text(text + "\n", encoding="utf-8")
        title = item["title"] + " (historische Fassung)" if wid == "nietzsche-045" else item["title"]
        historical_note = item["editorial_notes"]
        if wid == "nietzsche-023":
            historical_note += " Die dionysische Weltanschauung und Sokrates und die Tragödie sind in diesem Band nur in historischen Teilfassungen überliefert; vollständige moderne Einzeltextfassungen dieser beiden Schriften sind hier nicht enthalten."
        subtitle = (f"Musarion, Band {volume} · historische Arbeitsfassung" if volume
                    else "Aus historischen Sammelbänden zusammengestellt" if wid == "nietzsche-045"
                    else "Historische Originalausgabe · Arbeitsfassung")
        entry = entry_for(wid, title, item.get("original_publication_year", "1920–1929" if volume else 1887), item["language"], text, raw,
                          item["source_url"], item["download_url"],
                          f"{item['source_print_edition']} {historical_note} Quelle: {item['source_url']}.",
                          historical_note,
                          subtitle=subtitle,
                          contained_works=item["contained_works"], search_terms=item["contained_works"],
                          sections=[{"start_paragraph": i, "title": item["title"] if i == 0 else paragraphs[i],
                                     "first_paragraph": paragraphs[i]} for i in indexes],
                          original_languages=["de", "la", "grc"],
                          source_extent="Complete extracted author-text body of this historical volume; historical selection and arrangement, not the modern KGW." if volume else "Declared author text from the recorded historical sources; edition limitations are documented in the source note.",
                          extraction=portable_provenance(item["extraction"]), scan_downloads=portable_provenance(item.get("scan_downloads", [])),
                          raw_sources=portable_provenance(item.get("raw_sources", [])),
                          source_publication_year=item.get("source_publication_year"),
                          original_publication_year_note=item.get("original_publication_year_note", ""),
                          scan_provenance={"sha256": item.get("raw_scan_sha256"), "url": item.get("raw_scan_url"),
                                           "rights_url": item.get("rights_url"), "rights_label": item.get("rights_label")},
                          verse_paragraphs=[i for i, p in enumerate(paragraphs) if "\n" in p],
                          verse=volume == 20)
        entries.append(entry)
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gutenberg-dir", type=Path)
    parser.add_argument("--supplements-dir", type=Path)
    parser.add_argument("--musarion-dir", type=Path)
    args = parser.parse_args()
    manifest_path = EDITION / "source-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if not any([args.gutenberg_dir, args.supplements_dir, args.musarion_dir]):
        parser.error("Select at least one archived source directory")
    entries = []
    if args.gutenberg_dir:
        entries += import_gutenberg(args.gutenberg_dir)
    if args.supplements_dir:
        entries += import_supplements(args.supplements_dir)
    if args.musarion_dir:
        entries += import_musarion(args.musarion_dir)
    by_id = {e["work_id"]: e for e in manifest["works"]}
    for entry in entries:
        by_id[entry["work_id"]] = entry
    manifest.update(prepared_on=DATE, generated_at=STAMP,
                    collection_scope="Historische Originalwerke und historische Sammelbände. Die bibliografische Gesamtübersicht dokumentiert auch den darüber hinausgehenden kritischen Editionsbestand; keine Behauptung einer vollständigen modernen KGW/KGB.")
    for wid in ("nietzsche-001", "nietzsche-002"):
        by_id[wid]["content_updated_at"] = "2026-10-10T00:00:00Z"
    manifest["works"] = sorted(by_id.values(), key=lambda e: e["work_id"])
    manifest["author"]["original_languages"] = ["de", "la", "grc"]
    write_json(manifest_path, manifest)
    print(f"Imported {len(entries)} historical reader volumes and separate texts.")


if __name__ == "__main__":
    main()
