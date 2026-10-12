#!/usr/bin/env python3
"""Rebuild source-bound whitespace, repair evidenced repeat errors, audit every GA.

Default is a staged dry run. --apply copies only verified content and checksums
into the working library. The persistent baseline preserves the first before
state and makes reruns idempotent without erasing the change history.
Requires lxml for the existing EPUB importer; no guessing at verse boundaries.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import difflib
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

from finalize_library import CORE, content_file, read_json, write_json, verify, normalize_text
from ga040_readability import reflow_confirmed_ga040_prose, join_confirmed_calendar_stanzas
from repair_source_structure import apply_recipe
from repair_early_structure import apply_plan as apply_outline, preserve_baseline as preserve_outline_baseline
from repair_ga014_readability import apply_layout as apply_ga014, preserve_baseline as preserve_ga014_baseline

ROOT = Path(__file__).resolve().parents[1]
LETTERS = "a-zA-ZäöüÄÖÜß"
WRAPPED_WORD = re.compile(rf"\b([{LETTERS}]+)-[ \t]*\n\s*([a-zäöüß][{LETTERS}]*)\b")
RULES = {
    "source_outline": "Originale Überschriften, Nummerierung und Gliederung wiederhergestellt",
    "source_layout": "Quellengebundene Gliederung, Versabsätze und Metadaten wiederhergestellt",
    "source_restoration": "Exakt belegten Originalquellentext wiederhergestellt",
    "source_hyphen_repair": "GA 038: belegte physische Worttrennungen quellengebunden geschlossen",
    "source_letter_headings": "GA 039: Originalbriefnummern und Briefüberschriften quellengebunden hergestellt",
    "source_whitespace": "EPUB-Quellumbrüche bereinigt; echte Verszeilen und Absätze erhalten",
    "soft_hyphen": "Unsichtbare bedingte Trennzeichen entfernt",
    "attested_dehyphenation": "Zeilentrennung mit Wortbeleg im Korpus verbunden",
    "reviewed_syllable_repair": "Geprüfte wiederkehrende Silbentrennung verbunden",
    "ga040_prose_reflow": "Quellengeprüfte Prosa in GA 040 als Fließtext gesetzt",
    "ga040_calendar_stanzas": "Quellengeprüfte Wochenverse in GA 040 als Strophen gesetzt",
    "ga014_readability": "GA 014: Versdialoge, Prosareden und Regieanweisungen quellengebunden gesetzt",
    "reviewed_ocr": "Am Druck geprüfte wiederkehrende OCR-Wörter korrigiert",
    "reader_spacing": "Abstände an Zeilengrenzen an das Leserformat angepasst",
    "prose_sentence_breaks": "GA 050+: Satzfortsetzungen verbunden; Verse und strukturierte Zeilen erhalten",
    "sentence_section_boundary": "Satzfortsetzung an fehlerhafter Abschnittsgrenze wiederhergestellt",
}
FLAG_LABELS = {
    "unresolved_hyphenation": "Mögliche Worttrennung ohne sicheren Wortbeleg",
    "duplicate_paragraph": "Wiederholter Absatz; kann absichtlich sein",
    "suspicious_page_label": "Unplausible Seitenzahl in der Quellenmetadaten",
    "ocr_suspect": "Möglicher OCR-Fehler; Original prüfen",
    "missing_illustration": "Bildplatzhalter; Abbildung in der Quelle prüfen",
    "private_use_glyph": "Sonderzeichen aus einer Quellenschrift prüfen",
    "ocr_source_review": "Textquelle mit weiteren systematischen OCR-Fehlern",
    "manuscript_transcription": "Unleserliche Handschriften-Transkription mit Faksimile vergleichen",
    "verse_paragraph_review": "Weitere Strophengrenzen mit dem Druck vergleichen",
    "verse_overrun_review": "Überlange Verszeile am Druck prüfen",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def excerpt_pair(before, after, limit=440):
    # The first changed character usually precedes a short excerpt even in a
    # lecture with 100,000 characters. Avoid quadratic full-text diffing.
    position = 0
    for left, right in zip(before, after):
        if left != right:
            break
        position += 1
    start = max(0, position - 100)
    return before[start:start + limit], after[start:start + limit]


def event(passage_id, rule, count, before, after, **extra):
    old, new = excerpt_pair(before, after)
    return {"passage_id": passage_id, "rule": rule, "label": RULES[rule], "count": count,
            "before_excerpt": old, "after_excerpt": new, **extra}


def vocabulary(payloads):
    works, occurrences, hyphenated = Counter(), Counter(), Counter()
    for payload in payloads.values():
        words = set()
        for passage in payload["passages"]:
            text = passage["text"].replace("\u00ad", "")
            tokens = [word.lower() for word in re.findall(rf"\b[{LETTERS}]{{3,}}\b", text)]
            words.update(tokens)
            occurrences.update(tokens)
            hyphenated.update((m[1].lower(), m[2].lower()) for m in re.finditer(rf"\b([{LETTERS}]+)-\s*([{LETTERS}]+)\b", text))
        works.update(words)
    return works, occurrences, hyphenated


def repair_words(original, rebuilt, evidence):
    word_works, word_count, hyphen_count = evidence
    changes = []
    before = rebuilt
    count = rebuilt.count("\u00ad")
    # A discretionary hyphen followed by wrapped whitespace still belongs to
    # the same word. Preserve an actual verse boundary elsewhere.
    def join_discretionary(match):
        joined = match[1] + match[3]
        return joined if word_works[joined.lower()] >= 2 else match[1] + match[2] + match[3]
    rebuilt = re.sub(rf"\b([{LETTERS}]+)\u00ad([ \t\n]+)([a-zäöüß][{LETTERS}]*)\b", join_discretionary, rebuilt)
    rebuilt = rebuilt.replace("\u00ad", "")
    if count:
        changes.append(("soft_hyphen", count, before, rebuilt, {}))
    candidates = Counter((m[1], m[2]) for m in WRAPPED_WORD.finditer(original))
    allowed = {}
    compound_prefixes = {"geistig", "göttlich", "physisch", "sinnlich", "seelisch", "leiblich", "körperlich", "politisch", "sozial", "ich", "christus", "äther", "geist", "erden", "archiv"}
    for (left, right), source_count in candidates.items():
        joined = left + right
        if word_works[joined.lower()] < 2:
            continue
        if left.lower() in compound_prefixes or word_count[joined.lower()] < max(10, 20 * hyphen_count[(left.lower(), right.lower())]):
            continue
        # Only source-evidenced split tokens; preserve hanging compounds such
        # as 'Ein- und Ausatmen' and legitimate hyphenated words.
        if right.lower() in {"und", "oder", "bis", "sowie", "beziehungsweise"}:
            continue
        allowed[(left, right)] = source_count
    replacements = Counter()
    def replace(match):
        pair = (match[1], match[2])
        if replacements[pair] < allowed.get(pair, 0):
            replacements[pair] += 1
            return match[1] + match[2]
        return match[0]
    before = rebuilt
    rebuilt = re.sub(rf"\b([{LETTERS}]+)-[ \t\n]+([a-zäöüß][{LETTERS}]*)\b", replace, rebuilt)
    if replacements:
        changes.append(("attested_dehyphenation", sum(replacements.values()), before, rebuilt,
                        {"replacements": [{"word": left + right, "split": left + "- / " + right, "count": n,
                                           "attested_work_count": word_works[(left + right).lower()],
                                           "attested_word_count": word_count[(left + right).lower()],
                                           "split_count": hyphen_count[(left.lower(), right.lower())]}
                                          for (left, right), n in sorted(replacements.items())]}))
    return rebuilt, changes


# Each pair was sampled in the corpus and reviewed as a syllabic break. Exact
# token boundaries also allow 'Geistes-Er-kenntnis' without removing its first,
# meaningful hyphen. Preserve case and historical spelling (e.g. Bewußtsein).
REVIEWED_SYLLABLES = {("zu", "nächst"), ("er", "kenntnis"), ("be", "wußtsein"),
    ("men", "schen"), ("wer", "den"), ("kön", "nen"), ("eigent", "lich"),
    ("son", "dern"), ("mensch", "lichen"), ("physi", "schen"), ("gei", "stigen"),
    ("das", "jenige"), ("ent", "wickelung"), ("mensch", "heit")}


def repair_reviewed_syllables(text):
    replacements = Counter()
    def replace(match):
        if (match[1].lower(), match[2].lower()) in REVIEWED_SYLLABLES:
            replacements[(match[1], match[2])] += 1
            return match[1] + match[2]
        return match[0]
    lefts = "|".join(sorted({left for left, _ in REVIEWED_SYLLABLES}, key=len, reverse=True))
    rights = "|".join(sorted({right for _, right in REVIEWED_SYLLABLES}, key=len, reverse=True))
    result = re.sub(rf"\b({lefts})-[ \t\n]*({rights})\b", replace, text, flags=re.I)
    return result, [{"word": left + right, "split": left + "- / " + right, "count": count}
                    for (left, right), count in sorted(replacements.items())]


REVIEWED_OCR = {"fiir": "für", "dafi": "daß", "grofien": "großen", "erfiillt": "erfüllt", "iiber": "über", "miissen": "müssen"}
OCR_EVIDENCE = [
    {"title": "GA 105 · gedruckte Seite 17", "url": "https://432hertz.de/wp-content/uploads/GA105.pdf"},
    {"title": "GA 104a · gedruckte Seiten 63 und 72", "url": "https://432hertz.de/wp-content/uploads/GA104a.pdf"},
]


def repair_reviewed_ocr(text):
    counts = Counter()
    def replace(match):
        counts[match[0]] += 1
        return REVIEWED_OCR[match[0]]
    result = re.sub(r"\b(?:" + "|".join(REVIEWED_OCR) + r")\b", replace, text)
    return result, [{"original": word, "word": REVIEWED_OCR[word], "count": n} for word, n in sorted(counts.items())]


def audit_flags(payload):
    flags = []
    for passage in payload["passages"]:
        text = passage["text"]
        hyphens = [m for m in re.finditer(rf"\b[{LETTERS}]+-[ \t\n]+([a-zäöüß][{LETTERS}]*)\b", text)
                   if m[1].lower() not in {"und", "oder", "bis", "sowie", "beziehungsweise"}]
        if hyphens:
            match = hyphens[0]
            flags.append({"passage_id": passage["id"], "rule": "unresolved_hyphenation", "count": len(hyphens),
                          "label": FLAG_LABELS["unresolved_hyphenation"], "excerpt": text[max(0,match.start()-80):match.end()+100]})
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) >= 150]
        duplicates = [p for p, count in Counter(paragraphs).items() if count > 1]
        if duplicates:
            flags.append({"passage_id": passage["id"], "rule": "duplicate_paragraph", "count": len(duplicates),
                          "label": FLAG_LABELS["duplicate_paragraph"], "excerpt": duplicates[0][:350]})
        pages = passage.get("metadata", {}).get("page_numbers", [])
        bad = [page for page in pages if page > 1200 or page < 1]
        if bad:
            flags.append({"passage_id": passage["id"], "rule": "suspicious_page_label", "count": len(bad),
                          "label": FLAG_LABELS["suspicious_page_label"], "excerpt": str(bad)})
        suspects = list(re.finditer(r"\b(?:fiir|dafi|Allsführungen|Nachlafiverwaltung|rnenschlich|Zusasnmenhang|wirklichkeitsgcmäß|Sruttgart)\b|\ufffd", text))
        if suspects:
            match = suspects[0]
            flags.append({"passage_id": passage["id"], "rule": "ocr_suspect", "count": len(suspects),
                          "label": FLAG_LABELS["ocr_suspect"], "excerpt": text[max(0,match.start()-80):match.end()+100]})
        for rule, pattern in (("missing_illustration", r"#Bild\b"), ("private_use_glyph", r"[\ue000-\uf8ff]")):
            matches = list(re.finditer(pattern, text))
            if matches:
                match = matches[0]
                flags.append({"passage_id": passage["id"], "rule": rule, "count": len(matches),
                              "label": FLAG_LABELS[rule], "excerpt": text[max(0,match.start()-80):match.end()+100]})
        if payload["work_id"] == "ga-040":
            for pattern in (r"\brinden\b", r"WinterhorTnung", r"heiPge", r"(?m)^5 2 "):
                matches = list(re.finditer(pattern, text))
                if matches:
                    m = matches[0]
                    flags.append({"passage_id": passage["id"], "rule": "ocr_suspect", "count": len(matches),
                                  "label": FLAG_LABELS["ocr_suspect"],
                                  "description": "Auffällige Lesart im Wochenvers; mit dem Druck der verwendeten Ausgabe vergleichen.",
                                  "excerpt": text[max(0,m.start()-60):m.end()+90]})
    if payload["work_id"] in {"ga-100", "ga-104a", "ga-105", "ga-112"}:
        p = payload["passages"][0]
        flags.append({"passage_id": p["id"], "rule": "ocr_source_review", "count": 1,
                      "label": FLAG_LABELS["ocr_source_review"],
                      "description": "Die Quelle enthält systematische Umlaut- und ß-Verwechslungen. Sechs am Druck bestätigte Wörter wurden korrigiert; weitere Lesarten müssen mit dem Druck verglichen werden.",
                      "excerpt": p["text"][:450]})
    if payload["work_id"] == "ga-040a":
        p = next((p for p in payload["passages"] if p["id"] == "ga-040a-pdf-outline-75-10"), payload["passages"][0])
        flags.append({"passage_id": p["id"], "rule": "manuscript_transcription", "count": 1,
                      "label": FLAG_LABELS["manuscript_transcription"],
                      "description": "Diese Handschriften-Transkription enthält unleserliche OCR-Zeichenfolgen. Formatkorrekturen ersetzen hier keine Neutranskription anhand des Faksimiles.",
                      "excerpt": p["text"][:450]})
    if payload["work_id"] == "ga-040" and not payload.get("metadata", {}).get("source_layout"):
        p = next((p for p in payload["passages"] if "WINTERSONNENWENDE" in p["text"][:100].upper()), payload["passages"][0])
        flags.append({"passage_id": p["id"], "rule": "verse_paragraph_review", "count": 1,
                      "label": FLAG_LABELS["verse_paragraph_review"],
                      "description": "Die 52 Wochenverse wurden anhand des Drucks als Strophen gesetzt. Bei weiteren Sprüchen bleiben unbestätigte Quellenabsätze bestehen; zum Beispiel die ersten vier Zeilen der Wintersonnenwende.",
                      "excerpt": p["text"][:450]})
    if payload["work_id"] == "ga-014" and payload.get("metadata", {}).get("source_layout"):
        flags.extend(read_json(ROOT / "tools/ga014_structure.json").get("review_flags", []))
    if payload["work_id"] == "ga-030" and payload.get("metadata", {}).get("source_layout"):
        flags.extend(read_json(ROOT / "tools/ga030_structure.json").get("review_flags", []))
    if payload["work_id"] in {"ga-032", "ga-033", "ga-034", "ga-035", "ga-036", "ga-045"} and payload.get("metadata", {}).get("source_layout"):
        recipe_name = payload["work_id"].replace("-", "") + "_structure.json"
        for reviewed in read_json(ROOT / "tools" / recipe_name).get("review_flags", []):
            if isinstance(reviewed, dict) and {"passage_id", "rule", "count", "label"} <= reviewed.keys():
                flags.append(reviewed)
            elif payload["work_id"] != "ga-032" and (isinstance(reviewed, str) or
                    isinstance(reviewed, dict) and reviewed.get("kind") == "source_scope"):
                # These frozen observations document retained spellings and the
                # original apparatus boundary; they are not unresolved flags.
                continue
            elif (payload["work_id"] == "ga-045" and isinstance(reviewed, dict)
                    and reviewed.get("id") == "ga045-secondary-pdf-edition-mismatch"
                    and reviewed.get("scope") == "secondary_source" and reviewed.get("evidence")):
                # This edition difference is already accounted for by using
                # the retained DOC/EPUB exclusively in the frozen repair.
                continue
            else:
                raise ValueError("Malformed source review flag: " + payload["work_id"])
    return flags


def extract(work, payload, source, scope, recovery, temporary):
    from import_library import read_epub
    from import_recovered_volumes import adapted_epub, clean_image_placeholders
    source_path = source / (work["id"] + ".epub")
    if sha(source_path.read_bytes()) != payload["source_epub_sha256"]:
        raise ValueError(f"Source hash changed: {work['id']}")
    if work["id"] not in recovery:
        ga = work["id"][3:].lstrip("0")
        if ga not in scope:
            ga = ga.replace("-", "/")
        passages, details = read_epub(source_path, work["id"], work["title"], scope[ga])
    else:
        entry = recovery[work["id"]]
        adapted = temporary / (work["id"] + ".epub")
        adapted_epub(source_path, adapted)
        passages, details = read_epub(adapted, work["id"], work["title"], entry["scope"])
        for passage in passages:
            passage["text"] = clean_image_placeholders(passage["text"])
            for suffix in entry.get("editorial_suffixes", []):
                if suffix in passage["text"]:
                    passage["text"] = passage["text"].split(suffix, 1)[0].rstrip()
    old_passages = payload["passages"]
    if [p["id"] for p in passages] != [p["id"] for p in old_passages]:
        raise ValueError(f"Scope or passage identity changed: {work['id']}")
    for old, new in zip(old_passages, passages):
        if old["source_text"] != new["source_text"]:
            raise ValueError(f"Retained original source changed: {old['id']}")
        # Whitespace reconstruction may never add, remove or substitute letters.
        if re.sub(r"\s", "", old["text"]) != re.sub(r"\s", "", new["text"]):
            raise ValueError(f"Non-whitespace extraction drift: {old['id']}")
    return {p["id"]: p["text"] for p in passages}


def preserve_layout_baseline(payload, directory):
    """Keep the exact input for an independent audit of structural repairs."""
    path = directory / "content" / (payload["work_id"] + ".json.gz")
    if path.exists():
        if read_json(path) != payload:
            raise ValueError("Preserved layout baseline differs; choose a new layout baseline for a changed edition")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, payload)
    return sha(path.read_bytes())


def build(root, sources, output, baseline, apply=False, layout_baseline=None):
    layout_baseline = layout_baseline or ROOT / "research/proofreading-layout-baseline"
    outline_recipe = read_json(ROOT / "tools/ga001_026_structure.json")
    sentence_recipe_path = ROOT / "tools/ga050_plus_sentence_breaks.json"
    sentence_recipe = read_json(sentence_recipe_path) if sentence_recipe_path.exists() else {"works": {}}
    if output.exists():
        raise ValueError("Choose a fresh staging directory; existing results are preserved.")
    existing_report = root / "proofreading/catalog.json"
    if not baseline.exists() and existing_report.exists():
        previous = read_json(existing_report)
        if all(not w["available"] or sha(content_file(root, w["id"]).read_bytes()) == w["after_sha256"] for w in previous["works"]):
            # A clean checkout may have the committed results but no ignored
            # local before-cache. Keep its original ledger instead of trying to
            # turn already corrected words back into source spelling.
            for folder in ("content", "library", "proofreading"):
                shutil.copytree(root / folder, output / folder)
            verify(output)
            if apply:
                apply_stage(root, output)
            print("Existing checked text and per-GA change history preserved byte-for-byte.")
            return previous
        raise ValueError("Content differs from the existing ledger; retain that history and explicitly choose a new baseline for a new edition.")
    if not baseline.exists():
        baseline.mkdir(parents=True)
        shutil.copytree(root / "content", baseline / "content")
        shutil.copytree(root / "library", baseline / "library")
    catalog = read_json(baseline / "library/catalog.json")
    payloads = {w["id"]: read_json(content_file(baseline, w["id"])) for w in catalog["works"] if w.get("content_path")}
    evidence = vocabulary(payloads)
    scope = read_json(ROOT / "tools/library-scope.json")
    recovery = {w["id"]: w for w in read_json(ROOT / "tools/recovered-reader-scope.json")["works"]}
    shutil.copytree(baseline / "content", output / "content")
    shutil.copytree(baseline / "library", output / "library")
    report_root = output / "proofreading"
    (report_root / "works").mkdir(parents=True)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    work_reports = []
    with tempfile.TemporaryDirectory(prefix="ga-proofread-adapter-") as temporary:
        for index, work in enumerate(catalog["works"]):
            changes, checks, flags, samples = [], [], [], []
            available = bool(work.get("content_path"))
            before_bytes, after_bytes, layout_base_sha256, outline_base_sha256, ga014_base_sha256 = None, None, None, None, None
            ga038_hyphen_input_sha256 = None
            ga039_heading_input_sha256 = None
            if available:
                payload = payloads[work["id"]]
                before_path = content_file(baseline, work["id"])
                before_bytes = sha(before_path.read_bytes())
                rebuilt = {} if work["id"] in CORE else extract(work, payload, sources, scope, recovery, Path(temporary))
                checks = ["Abschnittskennungen und Reihenfolge unverändert", "Originale Quellentexte unverändert", "Seitenanker und Anmerkungen erhalten"]
                if work["id"] not in CORE:
                    checks.extend(["EPUB-SHA-256 stimmt mit importierter Quelle überein", "Quellrekonstruktion verändert ausschließlich Leerraum"])
                summaries = {p["id"]: p for p in work["passages"]}
                for passage in payload["passages"]:
                    before = passage["text"]
                    text = rebuilt.get(passage["id"], before)
                    if text != before:
                        changes.append(event(passage["id"], "source_whitespace", 1, before, text,
                                             newlines_before=before.count("\n"), newlines_after=text.count("\n")))
                    if work["id"] not in CORE:
                        text, word_changes = repair_words(before, text, evidence)
                        changes.extend(event(passage["id"], rule, count, old, new, **extra)
                                       for rule, count, old, new, extra in word_changes)
                    before_syllables = text
                    text, replacements = repair_reviewed_syllables(text)
                    if replacements:
                        changes.append(event(passage["id"], "reviewed_syllable_repair", sum(r["count"] for r in replacements),
                                             before_syllables, text, replacements=replacements))
                    before_ocr = text
                    text, replacements = repair_reviewed_ocr(text)
                    if replacements:
                        changes.append(event(passage["id"], "reviewed_ocr", sum(r["count"] for r in replacements),
                                             before_ocr, text, replacements=replacements, evidence=OCR_EVIDENCE))
                    if work["id"] == "ga-040":
                        before_prose = text
                        text, count = reflow_confirmed_ga040_prose(passage["id"], text)
                        if count:
                            changes.append(event(passage["id"], "ga040_prose_reflow", count, before_prose, text))
                        before_stanzas = text
                        text, count = join_confirmed_calendar_stanzas(passage["id"], text)
                        if count:
                            changes.append(event(passage["id"], "ga040_calendar_stanzas", count, before_stanzas, text))
                    before_spacing = text
                    text, inline_pages = normalize_text(text)
                    if inline_pages:
                        raise ValueError("Unexpected remaining inline pages: " + passage["id"])
                    if text != before_spacing:
                        changes.append(event(passage["id"], "reader_spacing", 1, before_spacing, text))
                    if not text.strip():
                        raise ValueError("Blank cleaned passage: " + passage["id"])
                    passage["text"] = text
                    passage["checksum"] = sha(text.encode())
                    summaries[passage["id"]]["checksum"] = passage["checksum"]
                if work["id"] in {"ga-027", "ga-030", "ga-032", "ga-033", "ga-034", "ga-035", "ga-036", "ga-040", "ga-045"}:
                    layout_recipe = work["id"].replace("-", "") + "_structure.json"
                    if work["id"] == "ga-030":
                        from repair_ga030_readability import apply_layout as apply_ga030
                        structured, layout_changes = apply_ga030(payload, read_json(ROOT / "tools" / layout_recipe))
                    elif work["id"] == "ga-032":
                        from repair_ga032_readability import apply_layout as apply_ga032
                        structured, layout_changes = apply_ga032(payload, read_json(ROOT / "tools" / layout_recipe))
                    elif work["id"] in {"ga-033", "ga-034", "ga-035", "ga-036", "ga-045"}:
                        from importlib import import_module
                        layout_module = import_module("repair_" + work["id"].replace("-", "") + "_readability")
                        structured, layout_changes = layout_module.apply_layout(payload, read_json(ROOT / "tools" / layout_recipe))
                        checks.append(layout_module.CHECK)
                        if work["id"] == "ga-033" and len(structured["passages"]) != len(payload["passages"]):
                            work["passages"] = [{key: p.get(key) for key in
                                ("id", "title", "ga_page", "source_label", "checksum")} for p in structured["passages"]]
                            work["catalog_passage_count"] = len(structured["passages"])
                            work["content_completeness"] = structured.get("content_completeness")
                            summaries = {p["id"]: p for p in work["passages"]}
                    else:
                        structured, layout_changes = apply_recipe(payload, read_json(ROOT / "tools" / layout_recipe))
                    layout_base_sha256 = preserve_layout_baseline(payload, layout_baseline)
                    payload = structured
                    payloads[work["id"]] = payload
                    changes.extend(layout_changes)
                    if work["id"] == "ga-027":
                        from repair_ga027_readability import CHECK as ga027_check
                        checks.append(ga027_check)
                    if work["id"] == "ga-030":
                        from repair_ga030_readability import CHECK as ga030_check
                        checks.append(ga030_check)
                        checks[0] = "Die drei ursprünglichen Abschnittskennungen erhalten; fehlende Quellteile exakt belegt ergänzt"
                        work["passages"] = [{key:p.get(key) for key in ("id", "title", "ga_page", "source_label", "checksum")} for p in payload["passages"]]
                        work["catalog_passage_count"] = len(payload["passages"])
                        work["content_completeness"] = payload["content_completeness"]
                        summaries = {p["id"]:p for p in work["passages"]}
                    if work["id"] == "ga-032":
                        from repair_ga032_readability import CHECK as ga032_check
                        checks.append(ga032_check)
                    for passage in payload["passages"]:
                        summaries[passage["id"]].update(title=passage["title"], checksum=passage["checksum"], ga_page=passage["ga_page"])
                if work["id"] in outline_recipe["works"]:
                    outline_base_sha256 = preserve_outline_baseline(payload)
                    payload, outline_changes = apply_outline(payload, outline_recipe["works"][work["id"]])
                    payloads[work["id"]] = payload
                    changes.extend(outline_changes)
                    checks.append("Originale Nummerierung und Kapitelhierarchie am Quellenbestand geprüft; Buchtext und Notizanker unverändert")
                    for passage in payload["passages"]:
                        summaries[passage["id"]]["title"] = passage["title"]
                if work["id"] == "ga-014":
                    ga014_base_sha256 = preserve_ga014_baseline(payload)
                    payload, dramatic_changes = apply_ga014(payload)
                    payloads[work["id"]] = payload
                    changes.extend(dramatic_changes)
                    checks.append("GA 014: Druckseitenköpfe entfernt; Prosa, Regieanweisungen und Verszeilen getrennt am Faksimile geprüft")
                    for passage in payload["passages"]:
                        summaries[passage["id"]].update(title=passage["title"], checksum=passage["checksum"], ga_page=passage["ga_page"])
                sentence_input_sha256 = None
                if sentence_recipe["works"]:
                    from repair_sentence_breaks import apply_plan as apply_sentences, preserve_baseline as preserve_sentences
                    sentence_plan = sentence_recipe["works"].get(work["id"])
                    if sentence_plan:
                        sentence_payload, sentence_changes = apply_sentences(payload, sentence_plan)
                        if sentence_changes:
                            sentence_input_sha256 = preserve_sentences(payload)
                            payload = sentence_payload
                            payloads[work["id"]] = payload
                            changes.extend(sentence_changes)
                            for passage in payload["passages"]:
                                summaries[passage["id"]].update(checksum=passage["checksum"], title=passage["title"])
                if work["id"] == "ga-038" and (ROOT / "tools/ga038_hyphen_review.json").exists():
                    from repair_ga038_hyphens import (
                        CHECK as ga038_check, apply_review as apply_ga038_review,
                        preserve_baseline as preserve_ga038_baseline,
                    )
                    ga038_hyphen_input_sha256 = preserve_ga038_baseline(payload)
                    payload, hyphen_changes = apply_ga038_review(
                        payload, read_json(ROOT / "tools/ga038_hyphen_review.json"))
                    payloads[work["id"]] = payload
                    changes.extend(hyphen_changes)
                    checks.append(ga038_check)
                    for passage in payload["passages"]:
                        summaries[passage["id"]]["checksum"] = passage["checksum"]
                if work["id"] == "ga-039" and (ROOT / "tools/ga039_heading_review.json").exists():
                    from repair_ga039_headings import (
                        CHECK as ga039_check, apply_review as apply_ga039_review,
                        preserve_baseline as preserve_ga039_baseline,
                    )
                    original_ids = [p["id"] for p in payload["passages"]]
                    ga039_heading_input_sha256 = preserve_ga039_baseline(payload)
                    payload, heading_changes = apply_ga039_review(payload)
                    if [p["id"] for p in payload["passages"] if p["id"] in set(original_ids)] != original_ids:
                        raise ValueError("GA039 original passage inventory/order changed")
                    payloads[work["id"]] = payload
                    changes.extend(heading_changes)
                    checks.append(ga039_check)
                    work["passages"] = [{key: p.get(key) for key in
                        ("id", "title", "ga_page", "source_label", "checksum")} for p in payload["passages"]]
                    work["catalog_passage_count"] = len(payload["passages"])
                    work["content_completeness"] = payload["content_completeness"]
                    summaries = {p["id"]: p for p in work["passages"]}
                flags = audit_flags(payload)
                sample_indexes = sorted({0, len(payload["passages"]) // 2, len(payload["passages"]) - 1})
                for sample_index in sample_indexes:
                    p = payload["passages"][sample_index]
                    samples.append({"passage_id": p["id"], "title": p["title"], "excerpt": p["text"][:600],
                                    "position": "Anfang" if sample_index == 0 else "Ende" if sample_index == len(payload["passages"])-1 else "Mitte", "status": "automatically_checked"})
                after_path = content_file(output, work["id"])
                if changes:
                    write_json(after_path, payload)
                after_bytes = sha(after_path.read_bytes())
            counts = Counter()
            for change in changes:
                counts[change["rule"]] += change["count"]
            flag_counts = Counter()
            for flag in flags:
                flag_counts[flag["rule"]] += flag["count"]
            payload = payloads.get(work["id"], {})
            report = {
                "id": work["id"], "ga_number": work["ga_number"], "title": work["title"],
                "available": available, "passage_count": len(payload.get("passages", [])),
                "character_count": sum(len(p["text"]) for p in payload.get("passages", [])),
                "status": "unavailable" if not available else "needs_review" if flags else "automatically_checked",
                "change_count": sum(counts.values()), "changed_passage_count": len({c["passage_id"] for c in changes}),
                "changes_by_rule": dict(counts), "flag_count": sum(flag_counts.values()), "flags_by_rule": dict(flag_counts),
                "checks": checks, "samples": samples, "source_summary": work.get("source_summary", ""),
                "before_sha256": before_bytes, "after_sha256": after_bytes,
                "source_epub_sha256": payload.get("source_epub_sha256"),
                "human_proofread": False,
                "newlines_removed": sum(c.get("newlines_before", 0) - c.get("newlines_after", 0) for c in changes if c["rule"] == "source_whitespace"),
            }
            if layout_base_sha256:
                report["application_base_sha256"] = layout_base_sha256
                report["layout_input_sha256"] = layout_base_sha256
            if outline_base_sha256:
                report["outline_input_sha256"] = outline_base_sha256
            if ga014_base_sha256:
                report["ga014_input_sha256"] = ga014_base_sha256
            if available and sentence_input_sha256:
                report["sentence_input_sha256"] = sentence_input_sha256
            if ga038_hyphen_input_sha256:
                report["ga038_hyphen_input_sha256"] = ga038_hyphen_input_sha256
            if ga039_heading_input_sha256:
                report["ga039_heading_input_sha256"] = ga039_heading_input_sha256
            work_reports.append(report)
            write_json(report_root / "works" / (work["id"] + ".json"), {"work": report, "changes": changes, "flags": flags})
            if (index + 1) % 25 == 0:
                print(f"Audited {index + 1}/{len(catalog['works'])} GAs", flush=True)
    write_json(output / "library/catalog.json", catalog)
    for filename in ("import-report.json", "recovery-import-report.json"):
        path = output / "library" / filename
        if path.exists():
            report = read_json(path)
            counts = {w["id"]: w["character_count"] for w in work_reports}
            for work in report.get("works", []):
                if work["id"] in counts:
                    work["character_count"] = counts[work["id"]]
                if work["id"] == "ga-030":
                    work["passage_count"] = len(payloads["ga-030"]["passages"])
            if "passage_count" in report:
                report["passage_count"] = sum(w.get("passage_count", 0) for w in report.get("works", []))
            write_json(path, report)
    return complete_stage(output, apply_root=root if apply else None, generated_at=generated_at)


def complete_stage(output, apply_root=None, generated_at=None):
    """Finalize a fully extracted stage, retaining its individual change ledger.

    This also permits resuming an interrupted final validation without fetching
    or re-extracting unchanged sources. Every per-volume report/payload must be
    present and match its recorded SHA before any final spacing adjustment.
    """
    catalog_path = output / "library/catalog.json"
    catalog = read_json(catalog_path)
    report_root = output / "proofreading"
    work_reports = []
    counts = {}
    for work in catalog["works"]:
        path = report_root / "works" / (work["id"] + ".json")
        detail = read_json(path)
        report = detail["work"]
        if report["id"] != work["id"] or report["available"] != bool(work.get("content_path")):
            raise ValueError("Stage report identity differs: " + work["id"])
        if report["available"]:
            payload_path = content_file(output, work["id"])
            if sha(payload_path.read_bytes()) != report["after_sha256"]:
                raise ValueError("Stage payload changed after extraction: " + work["id"])
            payload = read_json(payload_path)
            summaries = {p["id"]: p for p in work["passages"]}
            changed = False
            for passage in payload["passages"]:
                before = passage["text"]
                text, pages = normalize_text(before)
                if pages:
                    raise ValueError("Unexpected inline pages during stage completion")
                if text != before:
                    detail["changes"].append(event(passage["id"], "reader_spacing", 1, before, text))
                    passage["text"] = text
                    passage["checksum"] = sha(text.encode())
                    summaries[passage["id"]]["checksum"] = passage["checksum"]
                    changed = True
            if changed:
                write_json(payload_path, payload)
            report["after_sha256"] = sha(payload_path.read_bytes())
            report["character_count"] = sum(len(p["text"]) for p in payload["passages"])
            counts[work["id"]] = report["character_count"]
            detail["flags"] = audit_flags(payload)
            passages = payload["passages"]
            first = next((i for i,p in enumerate(passages) if len(p["text"].strip()) >= 200), 0)
            report["samples"] = [{"passage_id": passages[i]["id"], "title": passages[i]["title"],
                                  "excerpt": passages[i]["text"][:600], "position": position,
                                  "status": "automatically_checked"}
                                 for i,position in ((first,"Anfang"),(len(passages)//2,"Mitte"),(len(passages)-1,"Ende"))
                                 if i >= 0]
        change_counts, flag_counts = Counter(), Counter()
        for change in detail["changes"]:
            change_counts[change["rule"]] += change["count"]
        for flag in detail["flags"]:
            flag_counts[flag["rule"]] += flag["count"]
        report.update(change_count=sum(change_counts.values()), changes_by_rule=dict(change_counts),
                      changed_passage_count=len({c["passage_id"] for c in detail["changes"]}),
                      flag_count=sum(flag_counts.values()), flags_by_rule=dict(flag_counts),
                      status="unavailable" if not report["available"] else "needs_review" if flag_counts else "automatically_checked")
        detail["work"] = report
        write_json(path, detail)
        work_reports.append(report)
    write_json(catalog_path, catalog)
    for filename in ("import-report.json", "recovery-import-report.json"):
        path = output / "library" / filename
        if path.exists():
            imported = read_json(path)
            for w in imported.get("works", []):
                if w["id"] in counts:
                    w["character_count"] = counts[w["id"]]
            write_json(path, imported)
    validation = verify(output)
    summary = {"total": len(work_reports), "available": sum(w["available"] for w in work_reports),
               "unavailable": sum(not w["available"] for w in work_reports),
               "changed_works": sum(w["change_count"] > 0 for w in work_reports),
               "changed_passages": sum(w["changed_passage_count"] for w in work_reports),
               "changes": sum(w["change_count"] for w in work_reports),
               "flagged_works": sum(w["flag_count"] > 0 for w in work_reports),
               "flags": sum(w["flag_count"] for w in work_reports),
               "newlines_removed": sum(w["newlines_removed"] for w in work_reports),
               "passages": sum(w["passage_count"] for w in work_reports)}
    report = {"schema_version": 1, "generated_at": generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"), "summary": summary, "works": work_reports,
              "rules": RULES, "flag_rules": FLAG_LABELS, "validation": validation,
              "review_policy": "Automatische Prüfung mit Proben; keine abgeschlossene manuelle Kollation."}
    write_json(report_root / "catalog.json", report)
    if apply_root:
        apply_stage(apply_root, output)
    print(json.dumps({"summary": summary, "validation": validation}, ensure_ascii=False))
    return report


def apply_stage(root, output):
    """Apply an already sampled stage; fail before writing on any checksum drift."""
    report = read_json(output / "proofreading/catalog.json")
    verify(output)
    for work in report["works"]:
        if not work["available"]:
            continue
        current = sha(content_file(root, work["id"]).read_bytes())
        incoming = sha(content_file(output, work["id"]).read_bytes())
        if incoming != work["after_sha256"]:
            raise ValueError("Staged content differs from its report: " + work["id"])
        if current not in {work["before_sha256"], work["after_sha256"], work.get("application_base_sha256")}:
            raise ValueError("Working content changed outside this pass: " + work["id"])
    for folder in ("content", "library", "proofreading"):
        for path in (output / folder).rglob("*"):
            if not path.is_file():
                continue
            target = root / folder / path.relative_to(output / folder)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.read_bytes() != path.read_bytes():
                temporary = target.with_name(target.name + ".proofreading-tmp")
                shutil.copyfile(path, temporary)
                temporary.replace(target)
    print("Applied verified readability pass.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "server/priv")
    parser.add_argument("--sources", type=Path, default=ROOT / "research/proofreading-sources")
    parser.add_argument("--baseline", type=Path, default=ROOT / "research/proofreading-baseline")
    parser.add_argument("--layout-baseline", type=Path, default=ROOT / "research/proofreading-layout-baseline", help="Preserve intermediate inputs for independent structural verification")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apply-stage", type=Path, help="Apply an already inspected, complete staging tree")
    parser.add_argument("--complete-stage", type=Path, help="Finish validation of an extracted tree with all per-GA reports")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.complete_stage:
        complete_stage(args.complete_stage)
    elif args.apply_stage:
        apply_stage(args.root, args.apply_stage)
    elif args.output:
        build(args.root, args.sources, args.output, args.baseline, args.apply, args.layout_baseline)
    else:
        parser.error("Provide --output for a dry run or --apply-stage for an inspected stage.")
