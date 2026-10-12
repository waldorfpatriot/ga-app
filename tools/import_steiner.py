#!/usr/bin/env python3
"""Build auditable reader payloads from the cached Rudolf Steiner DOC extracts."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "research" / "doc_text"
OUTPUT_DIR = ROOT / "server" / "priv" / "content"


@dataclass(frozen=True)
class Work:
    number: str
    title: str
    start_line: int
    headings: tuple[str, ...]
    cutoff: str | None = None


WORKS = (
    Work(
        "003",
        "Wahrheit und Wissenschaft",
        34,
        (
            "Vorrede zur 1. Auflage 1892",
            "Einleitung",
            "I. Vorbemerkungen",
            "II. Kants erkenntnistheoretische Grundfrage",
            "III. Die Erkenntnistheorie nach Kant",
            "IV. Die Ausgangspunkte der Erkenntnistheorie",
            "V. Erkennen und Wirklichkeit",
            "VI. Die voraussetzungslose Erkenntnistheorie und Fichtes Wissenschaftslehre",
            "VII. Erkenntnistheoretische Schlussbetrachtung",
            "VIII. Praktische Schlussbetrachtung",
        ),
    ),
    Work(
        "004",
        "Die Philosophie der Freiheit",
        42,
        (
            "Vorrede zur Neuausgabe 1918",
            "I. Das bewusste menschliche Handeln",
            "II. Der Grundtrieb zur Wissenschaft",
            "III. Das Denken im Dienste der Weltauffassung",
            "IV. Die Welt als Wahrnehmung",
            "V. Das Erkennen der Welt",
            "VI. Die menschliche Individualität",
            "VII. Gibt es Grenzen des Erkennens?",
            "VIII. Die Faktoren des Lebens",
            "IX. Die Idee der Freiheit",
            "X. Freiheitsphilosophie und Monismus",
            "XI. Weltzweck und Lebenszweck (Bestimmung des Menschen)",
            "XII. Die moralische Phantasie (Darwinismus und Sittlichkeit)",
            "XIII. Der Wert des Lebens (Pessimismus und Optimismus)",
            "XIV. Individualität und Gattung",
            "Die letzten Fragen",
            "Erster Anhang (Zusatz zur Neuausgabe 1918)",
            "Zweiter Anhang (Vorrede zur 1. Auflage von 1884)",
        ),
    ),
    Work(
        "009",
        "Theosophie",
        35,
        (
            "Vorrede zur 6. Auflage",
            "Einleitung",
            "Das Wesen des Menschen",
            "I. Die leibliche Wesenheit des Menschen",
            "II. Die seelische Wesenheit des Menschen",
            "III. Die geistige Wesenheit des Menschen",
            "IV. Leib, Seele und Geist",
            "Wiederverkörperung des Geistes und Schicksal",
            "I. Die Seelenwelt",
            "II. Die Seele in der Seelenwelt nach dem Tode",
            "III. Das Geisterland",
            "IV. Der Geist im Geisterland nach dem Tode",
            "V. Die physische Welt und ihre Verbindung mit Seelen- und Geisterland",
            "VI. Von den Gedankenformen und der menschlichen Aura",
            "Der Pfad der Erkenntnis",
            "Einzelne Bemerkungen und Ergänzungen",
        ),
        "Hinweise des Herausgebers",
    ),
    Work(
        "010",
        "Wie erlangt man Erkenntnisse der höheren Welten?",
        31,
        (
            "Vorrede zum achten bis elften Tausend",
            "Vorrede 1914",
            "Vorrede",
            "Wie erlangt man Erkenntnisse der höheren Welten?",
            "Die Stufen der Einweihung",
            "Die Erleuchtung",
            "Die Einweihung",
            "Praktische Gesichtspunkte",
            "Die Bedingungen der Geheimschulung",
            "Über einige Wirkungen der Geheimschulung",
            "Veränderungen im Traumleben des Geheimschülers",
            "Die Erlangung der Kontinuität des Bewußtseins",
            "Die Spaltung der Persönlichkeit während der Geistesschulung",
            "Der Hüter der Schwelle",
            "Leben und Tod – Der große Hüter der Schwelle",
            "Nachwort zum achten bis zwölften Tausend",
        ),
    ),
    Work(
        "013",
        "Die Geheimwissenschaft im Umriß",
        36,
        (
            "Vorrede zur 16. – 20. Auflage",
            "Charakter der Geheimwissenschaft",
            "Wesen der Menschheit",
            "Schlaf und Tod",
            "Die Weltentwicklung und der Mensch",
            "Die Erkenntnis der höheren Welten (von der Einweihung oder Initiation)",
            "Gegenwart und Zukunft der Welt- und Menschheits-Entwickelung",
            "Der Ätherleib des Menschen",
            "Die astralische Welt",
            "Vom Leben des Menschen nach dem Tode",
            "Der Lebenslauf des Menschen",
            "Die höheren Gebiete der geistigen Welt",
            "Die Wesensglieder des Menschen",
            "Der Traumzustand",
            "Zur Erlangung übersinnlicher Erkenntnisse",
            "Beobachtung besonderer Ereignisse und Wesen der Geisteswelt",
            "Besondere Bemerkungen",
        ),
    ),
)

SAFE_CORRECTIONS = {
    "Schiksal": "Schicksal",
    "voraussetzunglose": "voraussetzungslose",
}


def canonical_line(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    value = value.replace("\ufeff", "").replace("\u00a0", " ").replace("\u2028", "")
    value = value.replace("’", "").replace("'", "").replace("–", "-").replace("—", "-")
    value = value.replace("voraussetzunglose", "voraussetzungslose")
    return re.sub(r"\s+", " ", value).strip(" \t\r\n\f")


def locate_heading(lines: list[str], heading: str, start: int) -> int:
    wanted = canonical_line(heading).casefold()
    for index in range(start, len(lines)):
        candidate = canonical_line(lines[index])
        candidate = re.sub(r"^[IVXLC]+\.\s+", "", candidate, flags=re.I)
        normalized_wanted = re.sub(r"^[IVXLC]+\.\s+", "", wanted, flags=re.I)
        if candidate.casefold() == wanted or candidate.casefold() == normalized_wanted:
            return index
    raise ValueError(f"Could not locate heading {heading!r} after line {start + 1}")


def normalize_text(source: str) -> tuple[str, list[int], list[dict[str, str]]]:
    value = unicodedata.normalize("NFC", source)
    value = value.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\u00a0", " ").replace("\u2028", "\n").replace("\f", "\n\n")
    page_numbers = [int(page) for page in re.findall(r"\[(\d{1,4})\]", value)]
    value = re.sub(r"\[(\d{1,4})\]", "", value)
    corrections: list[dict[str, str]] = []
    word_field_count = len(re.findall(r"PAGE\s+\\\*\s+MERGEFORMAT\s+\d+", value))
    if word_field_count:
        value = re.sub(r"PAGE\s+\\\*\s+MERGEFORMAT\s+\d+", "", value)
        corrections.append(
            {"from": "Word PAGE field", "to": "", "count": str(word_field_count)}
        )
    for original, replacement in SAFE_CORRECTIONS.items():
        count = value.count(original)
        if count:
            value = value.replace(original, replacement)
            corrections.append({"from": original, "to": replacement, "count": str(count)})
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
    value = "\n".join(lines)
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    value = re.sub(r" +([,.;:!?])", r"\1", value)
    return value, list(dict.fromkeys(page_numbers)), corrections


def extract_annotations(source: str) -> tuple[str, list[dict[str, str]]]:
    """Separate an author's trailing Anmerkungen block from a chapter body."""
    matches = list(re.finditer(r"(?im)^\s*Anmerkungen:\s*$", source))
    if not matches:
        return source, []

    marker = matches[-1]
    body = source[: marker.start()].rstrip()
    notes_block = source[marker.end() :].strip()
    note_markers = list(re.finditer(r"(?m)^\s*\((\d+)\)\s*", notes_block))
    annotations: list[dict[str, str]] = []

    for index, note_marker in enumerate(note_markers):
        stop = note_markers[index + 1].start() if index + 1 < len(note_markers) else len(notes_block)
        note_source = notes_block[note_marker.end() : stop].strip()
        note_text, _, _ = normalize_text(note_source)
        number = note_marker.group(1)
        if note_text and re.search(rf"\({re.escape(number)}\)", body):
            annotations.append({"id": number, "marker": f"({number})", "text": note_text})

    return (body, annotations) if annotations else (source, [])


def slug(index: int, title: str) -> str:
    simple = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    simple = re.sub(r"[^a-z0-9]+", "-", simple.lower()).strip("-")
    return f"{index + 1:02d}-{simple[:52]}"


def build(work: Work) -> dict:
    source_path = SOURCE_DIR / f"rudolf-steiner-ga-{work.number}.txt"
    raw = source_path.read_text(encoding="utf-8-sig")
    lines = raw.splitlines(keepends=True)
    cursor = work.start_line - 1
    positions: list[int] = []
    for heading in work.headings:
        position = locate_heading(lines, heading, cursor)
        positions.append(position)
        cursor = position + 1

    end = len(lines)
    if work.cutoff:
        end = locate_heading(lines, work.cutoff, positions[-1] + 1)

    passages = []
    all_corrections: list[dict[str, str]] = []
    for index, (title, start) in enumerate(zip(work.headings, positions)):
        stop = positions[index + 1] if index + 1 < len(positions) else end
        original = "".join(lines[start + 1 : stop]).strip()
        reader_source, annotations = extract_annotations(original)
        text, pages, corrections = normalize_text(reader_source)
        if not text:
            raise ValueError(f"{work.number} / {title}: empty normalized passage")
        all_corrections.extend(corrections)
        checksum = hashlib.sha256(text.encode()).hexdigest()
        passages.append(
            {
                "id": f"ga-{work.number}-{slug(index, title)}",
                "title": title,
                "ga_page": f"S. {pages[0]}–{pages[-1]}" if len(pages) > 1 else (f"S. {pages[0]}" if pages else None),
                "source_label": f"Rudolf Steiner Online Archiv DOC / Internet Archive GA {work.number}",
                "source_text": original,
                "text": text,
                "checksum": checksum,
                "metadata": {
                    "page_numbers": pages,
                    "page_marker_source": "original_inline_bracket_markers",
                    "normalization": "unicode_nfc_whitespace_page_markers_safe_corrections_v1",
                    "annotations": annotations,
                },
            }
        )

    joined = "\n".join(p["text"] for p in passages)
    warnings = []
    for pattern in (r"\b(dafi|fiir|Nachlaf|grofi|muB|daB)\b", r"PAGE\s+\\\*"):
        matches = re.findall(pattern, joined)
        if matches:
            warnings.append({"pattern": pattern, "count": len(matches)})
    return {
        "work_id": f"ga-{work.number}",
        "title": work.title,
        "language": "de",
        "license": "Public Domain Mark 1.0",
        "source_id": f"rudolf-steiner-ga-{work.number}",
        "source_file": source_path.name,
        "source_label": "Rudolf Steiner Online Archiv DOC mirrored by Internet Archive",
        "source_url": f"https://archive.org/details/rudolf-steiner-ga-{work.number}",
        "passage_count": len(passages),
        "word_count": len(joined.split()),
        "proofing": {
            "status": "automated_checks_passed" if not warnings else "warnings",
            "normalization_version": 1,
            "source_retained_for_diff": True,
            "safe_corrections": all_corrections,
            "warnings": warnings,
        },
        "passages": passages,
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    requested = set(sys.argv[1:])
    selected = [work for work in WORKS if not requested or work.number in requested]
    if requested and len(selected) != len(requested):
        known = ", ".join(work.number for work in WORKS)
        raise SystemExit(f"Unknown GA number. Available imports: {known}")

    for work in selected:
        payload = build(work)
        output = OUTPUT_DIR / f"ga-{work.number}.json"
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            f"GA {work.number}: {payload['passage_count']} passages, "
            f"{payload['word_count']} words, {payload['proofing']['status']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
