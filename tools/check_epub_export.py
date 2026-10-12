#!/usr/bin/env python3
"""Exercise the real Swift exporter and independently inspect its EPUB archives.

Run: python3 tools/check_epub_export.py
Requires the macOS Swift 6 toolchain; uses no app user data or external services.
Checks synthetic edge cases plus every bundled reader text, including long books.
"""

import argparse
import gzip
from pathlib import Path
import json
import posixpath
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
NS = {
    "ocf": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "html": "http://www.w3.org/1999/xhtml",
}
HARNESS = r'''
import Foundation

private struct ContentFixture: Decodable { var passages: [GAPassage] }
private struct CheckFailure: Error, CustomStringConvertible { let description: String }

@main
private enum EPUBExportChecks {
    static let timestamp = Date(timeIntervalSince1970: 1_700_000_000)

    static func main() async {
        do {
            try await run()
        } catch {
            FileHandle.standardError.write(Data("EPUB export check failed: \(error)\n".utf8))
            exit(1)
        }
    }

    static func run() async throws {
        let fixtureRoot = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        let output = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
        let passage = GAPassage(
            id: "first", title: "Über <Kapitel> & \"Zitate\"", gaPage: "S. 1–3",
            sourceLabel: "Quelle <Archiv> & Verlag",
            text: "Erste Zeile: äöü ß 📖 & <em>unverändert</em> \"Worte\" 'Zitat'.\r\nZweite Zeile.\r\n \t\r\nNeuer Absatz.\n\nLetzter Absatz.",
            metadata: GAPassageMetadata(pageNumbers: [1, 2, 3], annotations: [
                GAAnnotation(id: "note", marker: "[*] &", text: "Anmerkung: <i>kein HTML</i>.\nZweite Zeile.")
            ])
        )
        let second = GAPassage(id: "second", title: "", gaPage: nil, sourceLabel: "Weitere Quelle",
                               text: "Zweites Kapitel — vollständig.", metadata: GAPassageMetadata(pageNumbers: [5, 6]))
        var synthetic = GAVolume(id: "unsafe/../work?x=1", gaNumber: "GA 999", title: "Buch / ../ <>& \"äöü 📖\"",
            subtitle: "Untertitel & Ergänzung", languageCode: "de-DE", yearLabel: "1894 / 1918", type: .book,
            priority: 1, publicationState: .published, proofingState: .humanProofed,
            sourceSummary: "Quelle & Edition <1918>\n\nZweiter Quellenabsatz.", tags: [], passages: [passage, second],
            sanityChecks: [], catalogPassageCount: 2)
        var cases: [[String: String]] = []
        try save(synthetic, name: "synthetic", output: output, cases: &cases)

        var structured = synthetic
        structured.id = "structured"
        let structuredText = "📖 Frühling\n\nOster-Stimmung\n\n1\n\nWenn aus den Weltenweiten *\nDie Sonne spricht *"
        let structuredBody = structuredText as NSString
        func block(_ content: String, kind: GAReadingBlock.Kind, level: Int? = nil) -> GAReadingBlock {
            let range = structuredBody.range(of: content)
            return GAReadingBlock(kind: kind, startOffset: range.location, endOffset: NSMaxRange(range), level: level)
        }
        let sourceNote = GAAnnotation(id: "EPUB/chapter-0001.xhtml#footnote-6&name=ä %?", marker: "*", text: "Zweite Ausgabe 1918/19",
                                     startOffset: structuredBody.range(of: "*").location, endOffset: NSMaxRange(structuredBody.range(of: "*")))
        structured.passages = [GAPassage(id: "poems", title: "Seelenkalender", gaPage: nil, sourceLabel: "Quelle",
            text: structuredText, metadata: GAPassageMetadata(annotations: [sourceNote], readingBlocks: [
                block("📖 Frühling", kind: .heading, level: 1), block("Oster-Stimmung", kind: .heading, level: 2),
                block("1", kind: .heading, level: 3), block("Wenn aus den Weltenweiten *\nDie Sonne spricht *", kind: .verse)
            ], groupTitle: "Anthroposophischer Seelenkalender", pageAnchors: [
                GAPageAnchor(page: 9, startOffset: 0, source: "original_doc_page_footer", confidence: "observed"),
                GAPageAnchor(page: 10, startOffset: NSMaxRange(structuredBody.range(of: "📖 Frühling")), source: "original_doc_page_footer"),
                GAPageAnchor(page: 11, startOffset: structuredBody.range(of: "*").location, source: "original_doc_page_footer"),
                GAPageAnchor(page: 12, startOffset: structuredBody.length, source: "original_doc_page_footer")
            ]))]
        structured.catalogPassageCount = 1
        try expect(structured.passages[0].metadata.validReadingBlocks(in: structuredText).count == 4, "valid structure survives a leading UTF-16 surrogate pair")
        try expect(sourceNote.markerRanges(in: structuredText).count == 1, "only the anchored occurrence of a repeated marker is linked")
        try expect(sourceNote.linkURL.flatMap(GAAnnotation.id(from:)) == sourceNote.id, "source note IDs round-trip with paths, fragments, query characters and Unicode")
        try save(structured, name: "structured", output: output, cases: &cases)
        var invalid = structured
        invalid.id = "invalid-structure"
        invalid.passages[0].metadata.readingBlocks[0].endOffset = 1
        try expect(invalid.passages[0].metadata.validReadingBlocks(in: structuredText).isEmpty, "ranges splitting a Unicode surrogate pair fall back to plain text")
        try save(invalid, name: "invalid-structure", output: output, cases: &cases)

        var overlappingNotes = synthetic
        overlappingNotes.id = "overlapping-notes"
        let noteParagraphs = ["Ein Stern *.", "Ein belegter Hinweis †.", "Zwei Sterne **."]
        let noteText = noteParagraphs.joined(separator: "\n\n")
        let noteBody = noteText as NSString
        let anchoredMarker = noteBody.range(of: "†")
        let duplicateNotes = [
            GAAnnotation(id: "legacy-first", marker: "*", text: "Erste historische Anmerkung."),
            GAAnnotation(id: "legacy-overlap", marker: "*", text: "Zweite historische Anmerkung."),
            GAAnnotation(id: "anchored-note", marker: "†", text: "Eindeutig verankerte Anmerkung.",
                         startOffset: anchoredMarker.location, endOffset: NSMaxRange(anchoredMarker)),
            GAAnnotation(id: "legacy-double-star", marker: "**", text: "Überlappende Anmerkung mit zwei Sternen.")
        ]
        overlappingNotes.passages = [true, false].enumerated().map { index, structured in
            GAPassage(id: "notes-\(index)", title: "Fußnoten", gaPage: nil, sourceLabel: "Quellprüfung", text: noteText,
                metadata: GAPassageMetadata(annotations: duplicateNotes, readingBlocks: structured ? noteParagraphs.map { paragraph in
                    let range = noteBody.range(of: paragraph)
                    return GAReadingBlock(kind: .prose, startOffset: range.location, endOffset: NSMaxRange(range))
                } : []))
        }
        overlappingNotes.catalogPassageCount = 2
        try save(overlappingNotes, name: "overlapping-notes", output: output, cases: &cases)

        var dramatic = synthetic
        dramatic.id = "dramatic-spacing"
        let dramaticSegments: [(GAReadingBlock.Kind, String)] = [
            (.attribution, "MARIA:"), (.prose, "(Leise.)"),
            (.verse, "Die Sonne 📖 spricht\nDie Seele hört"),
            (.attribution, "ESTELLA:"), (.prose, "Ich höre deine Worte.")
        ]
        let dramaticGaps = ["\n", "\n", "\n\n", "\n", ""]
        var dramaticText = ""
        var dramaticBlocks: [GAReadingBlock] = []
        for (index, segment) in dramaticSegments.enumerated() {
            let start = (dramaticText as NSString).length
            dramaticText += segment.1
            dramaticBlocks.append(GAReadingBlock(kind: segment.0, startOffset: start, endOffset: (dramaticText as NSString).length))
            dramaticText += dramaticGaps[index]
        }
        dramatic.passages = [GAPassage(id: "dialogue", title: "Dramatischer Prüftext", gaPage: nil, sourceLabel: "Quellprüfung",
            text: dramaticText, metadata: GAPassageMetadata(readingBlocks: dramaticBlocks))]
        dramatic.catalogPassageCount = 1
        try expect(dramatic.passages[0].metadata.validReadingBlocks(in: dramaticText).count == 5,
                   "speaker labels, stage directions and speech have valid UTF-16 ranges")
        try save(dramatic, name: "dramatic-spacing", output: output, cases: &cases)

        var units = synthetic
        units.id = "work-units"
        let unitSegments: [(GAReadingBlock.Kind, String, Int?)] = [
            (.heading, "J", 2), (.verse, "Gedanke 📖 *\nGedankenfolge", nil),
            (.heading, "B", 2), (.verse, "Wille\nWillensfolge", nil),
            (.verse, "Es leuchten gleich Sternen *\nAm Himmel", nil),
            (.verse, "Offenbarung durch die Höhen dem Gotte,\nRuhe und Stille", nil),
            (.heading, "TISCHGEBET", 2), (.verse, "Es keimen die Pflanzen\nEs sprossen die Kräuter", nil),
            (.verse, "So keimet die Seele\nSo sprosset der Geist", nil),
            (.verse, "Rätsel an Rätsel stellt sich im Raum,\nLösung bringt der Geist", nil),
            (.verse, "Erkenne dich selbst.\nErkenne die Welt\nErkenne dich im Strome", nil),
            (.verse, "Gottes schützender segnender Strahl\nErfülle meine Seele", nil)
        ]
        let unitsText = unitSegments.map(\.1).joined(separator: "\n\n")
        let unitsBody = unitsText as NSString
        var unitsBlocks: [GAReadingBlock] = []
        var unitOffset = 0
        for segment in unitSegments {
            let length = (segment.1 as NSString).length
            unitsBlocks.append(GAReadingBlock(kind: segment.0, startOffset: unitOffset, endOffset: unitOffset + length, level: segment.2))
            unitOffset += length + 2
        }
        let unitBounds = [(0, 4), (4, 5), (5, 6), (6, 9), (9, 10), (10, 11), (11, 12)]
        let sourceTitle = "DIE VIER SPRÜCHE DER SÄULENWEISHEIT"
        let unitsSections = unitBounds.enumerated().map { index, bounds in
            GAReadingSection(id: "work-\(index + 1)",
                title: index == 0 ? sourceTitle : unitSegments[bounds.0].1.components(separatedBy: "\n")[0],
                labelKind: index == 0 || index == 3 ? .sourceTitle : .incipit,
                startOffset: unitsBlocks[bounds.0].startOffset, endOffset: unitsBlocks[bounds.1 - 1].endOffset)
        }
        let unitNoteRange = unitsBody.range(of: "*")
        let incipitNoteRange = unitsBody.range(of: "*", range: unitsBlocks[4].range)
        units.passages = [GAPassage(id: "seven-works", title: sourceTitle, gaPage: "S. 74–78", sourceLabel: "Quellprüfung",
            text: unitsText, metadata: GAPassageMetadata(annotations: [
                GAAnnotation(id: "source#note", marker: "*", text: "Quellenanmerkung", startOffset: unitNoteRange.location, endOffset: NSMaxRange(unitNoteRange)),
                GAAnnotation(id: "incipit#note", marker: "*", text: "Anmerkung im Spruchbeginn", startOffset: incipitNoteRange.location, endOffset: NSMaxRange(incipitNoteRange))
            ], readingBlocks: unitsBlocks, groupTitle: "Wahrspruchworte", pageAnchors: [
                GAPageAnchor(page: 74, startOffset: 0, source: "original_doc_page_footer"),
                GAPageAnchor(page: 75, startOffset: unitsSections[1].startOffset, source: "original_doc_page_footer"),
                GAPageAnchor(page: 76, startOffset: unitsSections[3].startOffset, source: "original_doc_page_footer"),
                GAPageAnchor(page: 77, startOffset: unitsSections[4].startOffset, source: "original_doc_page_footer"),
                GAPageAnchor(page: 78, startOffset: unitsSections[6].startOffset, source: "original_doc_page_footer")
            ], readingSections: unitsSections))]
        units.catalogPassageCount = 1
        try expect(units.passages[0].metadata.validReadingSections(in: unitsText, passageTitle: sourceTitle).count == 7,
                   "source-bound work units remain within the original passage")
        try save(units, name: "work-units", output: output, cases: &cases)
        var inlineTitleUnits = units
        inlineTitleUnits.id = "inline-title-work-units"
        let titlePrefix = sourceTitle + "\n\n"
        let prefixLength = (titlePrefix as NSString).length
        inlineTitleUnits.passages[0].text = titlePrefix + unitsText
        inlineTitleUnits.passages[0].metadata.readingBlocks = [
            GAReadingBlock(kind: .heading, startOffset: 0, endOffset: (sourceTitle as NSString).length, level: 1)
        ] + unitsBlocks.map { block in
            var shifted = block
            shifted.startOffset += prefixLength
            shifted.endOffset += prefixLength
            return shifted
        }
        inlineTitleUnits.passages[0].metadata.readingSections = unitsSections.enumerated().map { index, section in
            var shifted = section
            shifted.startOffset = index == 0 ? 0 : section.startOffset + prefixLength
            shifted.endOffset += prefixLength
            return shifted
        }
        inlineTitleUnits.passages[0].metadata.pageAnchors = units.passages[0].metadata.pageAnchors.enumerated().map { index, anchor in
            var shifted = anchor
            shifted.startOffset = index == 0 ? 0 : anchor.startOffset + prefixLength
            return shifted
        }
        inlineTitleUnits.passages[0].metadata.annotations = units.passages[0].metadata.annotations.map { note in
            var shifted = note
            shifted.startOffset! += prefixLength
            shifted.endOffset! += prefixLength
            return shifted
        }
        try save(inlineTitleUnits, name: "inline-title-work-units", output: output, cases: &cases)
        var invalidUnits = units
        invalidUnits.id = "invalid-work-units"
        invalidUnits.passages[0].metadata.readingSections[1].startOffset += 1
        try expect(invalidUnits.passages[0].metadata.validReadingSections(in: unitsText, passageTitle: sourceTitle).isEmpty,
                   "partial verse boundaries disable all work-unit presentation")
        try save(invalidUnits, name: "invalid-work-units", output: output, cases: &cases)

        var calendarUnits = units
        calendarUnits.id = "calendar-units"
        let calendarTitles = ["VORWORT ZUR ERSTEN AUSGABE 1912/13", "VORWORT ZUR ZWEITEN AUSGABE 1918", "FRÜHLING", "SOMMER", "HERBST", "WINTER"]
        var calendarSegments: [(GAReadingBlock.Kind, String, Int?)] = [
            (.prose, "Das erste Vorwort bleibt ein eigener Text.", nil),
            (.heading, calendarTitles[1], 1), (.prose, "Das zweite Vorwort bleibt ein eigener Text.", nil)
        ]
        var calendarBounds = [0, 1]
        var poemNumber = 0
        for (seasonIndex, count) in [13, 13, 9, 17].enumerated() {
            calendarBounds.append(calendarSegments.count)
            calendarSegments.append((.heading, calendarTitles[seasonIndex + 2], 1))
            for _ in 0..<count {
                poemNumber += 1
                calendarSegments.append((.heading, "Woche \(poemNumber)", 2))
                calendarSegments.append((.heading, String(poemNumber), 3))
                calendarSegments.append((.verse, "Erste Verszeile \(poemNumber)\nZweite Verszeile", nil))
            }
        }
        calendarBounds.append(calendarSegments.count)
        let calendarText = calendarSegments.map(\.1).joined(separator: "\n\n")
        var calendarBlocks: [GAReadingBlock] = []
        var calendarOffset = 0
        for segment in calendarSegments {
            let length = (segment.1 as NSString).length
            calendarBlocks.append(GAReadingBlock(kind: segment.0, startOffset: calendarOffset, endOffset: calendarOffset + length, level: segment.2))
            calendarOffset += length + 2
        }
        let calendarSections = calendarTitles.enumerated().map { index, title in
            GAReadingSection(id: "calendar-unit-\(index + 1)", title: title, labelKind: .sourceTitle,
                startOffset: calendarBlocks[calendarBounds[index]].startOffset,
                endOffset: calendarBlocks[calendarBounds[index + 1] - 1].endOffset)
        }
        calendarUnits.passages = [GAPassage(id: "six-calendar-units", title: calendarTitles[0], gaPage: nil, sourceLabel: "Kalender-Prüftext",
            text: calendarText, metadata: GAPassageMetadata(readingBlocks: calendarBlocks, groupTitle: "Anthroposophischer Seelenkalender", readingSections: calendarSections))]
        try save(calendarUnits, name: "calendar-units", output: output, cases: &cases)

        let firstURL = try EPUBExporter.export(volume: synthetic, modifiedAt: timestamp)
        let secondURL = try EPUBExporter.export(volume: synthetic, modifiedAt: timestamp)
        defer { remove(firstURL); remove(secondURL) }
        try expect(firstURL != secondURL && firstURL.deletingLastPathComponent() != secondURL.deletingLastPathComponent(),
                   "each export has an independent temporary directory")
        try expect(firstURL.lastPathComponent == secondURL.lastPathComponent, "shared filename remains readable and stable")
        try expect(try Data(contentsOf: firstURL) == Data(contentsOf: secondURL), "fixed inputs produce byte-identical archives")
        try expect(FileManager.default.fileExists(atPath: firstURL.path), "earlier exports remain available while sharing")

        var empty = synthetic
        empty.passages = []
        try reject(empty, error: .noReadableContent)
        var partial = synthetic
        partial.catalogPassageCount = 3
        try reject(partial, error: .incompleteContent(expected: 3, actual: 2))
        var blank = synthetic
        blank.passages[1].text = " \n\t "
        try reject(blank, error: .unreadablePassage(index: 2))
        var badXML = synthetic
        badXML.passages[1].text = "Inhalt\u{0001}Ende"
        try reject(badXML, error: .invalidXMLCharacters)
        badXML = synthetic
        badXML.title += "\u{0000}"
        try reject(badXML, error: .invalidXMLCharacters)
        var badLanguage = synthetic
        badLanguage.languageCode = "de\" onclick=\"bad"
        try reject(badLanguage, error: .invalidMetadata)
        var badTitle = synthetic
        badTitle.title = " "
        try reject(badTitle, error: .invalidMetadata)
        var duplicate = synthetic
        duplicate.passages[1].id = duplicate.passages[0].id
        try reject(duplicate, error: .invalidPassageIdentifiers)
        duplicate.passages[1].id = " "
        try reject(duplicate, error: .invalidPassageIdentifiers)
        synthetic.catalogPassageCount = 1
        let newer = try EPUBExporter.export(volume: synthetic, modifiedAt: timestamp)
        remove(newer)
        synthetic.catalogPassageCount = 2

        var english = synthetic
        english.id = "english"
        english.languageCode = "en"
        english.title = "English work"
        try save(english, name: "english", output: output, cases: &cases)
        var longName = synthetic
        longName.id = "long-name"
        longName.title = String(repeating: "書📖ä / ", count: 100)
        let longURL = try EPUBExporter.export(volume: longName, modifiedAt: timestamp)
        defer { remove(longURL) }
        try expect(longURL.lastPathComponent.utf8.count <= 165 && longURL.pathExtension == "epub", "filename stays below filesystem byte limits")
        remove(longURL)

        let snapshot = synthetic
        let cancelled = Task.detached {
            withUnsafeCurrentTask { $0?.cancel() }
            return try EPUBExporter.export(volume: snapshot, modifiedAt: timestamp)
        }
        do {
            let url = try await cancelled.value
            remove(url)
            throw CheckFailure(description: "cancelled export unexpectedly succeeded")
        } catch is CancellationError {
            // Cancellation reaches the synchronous generator before it creates a file.
        }
        let concurrent = try await withThrowingTaskGroup(of: URL.self, returning: [URL].self) { group in
            for _ in 0..<4 {
                group.addTask { try EPUBExporter.export(volume: snapshot, modifiedAt: timestamp) }
            }
            var urls: [URL] = []
            for try await url in group { urls.append(url) }
            return urls
        }
        defer { concurrent.forEach(remove) }
        try expect(Set(concurrent).count == 4, "concurrent exports do not overwrite one another")
        for url in concurrent { try expect(try Data(contentsOf: url) == Data(contentsOf: firstURL), "background exports are deterministic") }

        let fixtureURLs = try FileManager.default.contentsOfDirectory(at: fixtureRoot, includingPropertiesForKeys: nil)
            .filter { $0.pathExtension == "json" }.sorted { $0.lastPathComponent < $1.lastPathComponent }
        try expect(!fixtureURLs.isEmpty, "bundled books are available")
        for url in fixtureURLs {
            let id = url.deletingPathExtension().lastPathComponent
            guard var volume = SeedLibrary.volumes.first(where: { $0.id == id }) else {
                throw CheckFailure(description: "missing seeded volume \(id)")
            }
            volume.passages = try JSONDecoder().decode(ContentFixture.self, from: Data(contentsOf: url)).passages
            volume.catalogPassageCount = volume.passages.count
            try save(volume, name: id, output: output, cases: &cases)
        }
        if CommandLine.arguments.count > 3 {
            let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[3]))
            let object = try JSONSerialization.jsonObject(with: data) as! [String: Any]
            var volume = synthetic
            volume.id = object["work_id"] as? String ?? "external"
            volume.title = object["title"] as? String ?? "External source edition"
            volume.gaNumber = "GA " + volume.id.replacingOccurrences(of: "ga-", with: "")
            volume.languageCode = object["language"] as? String ?? "de"
            volume.sourceSummary = object["source_label"] as? String ?? "Source edition"
            volume.passages = try JSONDecoder().decode(ContentFixture.self, from: data).passages
            volume.catalogPassageCount = volume.passages.count
            try save(volume, name: "external", output: output, cases: &cases)
        }
        let manifest = try JSONSerialization.data(withJSONObject: cases, options: [.prettyPrinted, .sortedKeys])
        try manifest.write(to: output.appendingPathComponent("cases.json"))
        print("Swift EPUB export checks passed: rejection of incomplete/invalid text, unique temporary files, deterministic archives and background concurrency.")
    }

    static func save(_ volume: GAVolume, name: String, output: URL, cases: inout [[String: String]]) throws {
        let url = try EPUBExporter.export(volume: volume, modifiedAt: timestamp)
        defer { remove(url) }
        let epubName = "\(name).epub"
        let volumeName = "\(name).json"
        try FileManager.default.copyItem(at: url, to: output.appendingPathComponent(epubName))
        try JSONEncoder().encode(volume).write(to: output.appendingPathComponent(volumeName))
        cases.append(["epub": epubName, "volume": volumeName])
    }

    static func reject(_ volume: GAVolume, error expected: EPUBExportError) throws {
        do {
            let url = try EPUBExporter.export(volume: volume, modifiedAt: timestamp)
            remove(url)
            throw CheckFailure(description: "export unexpectedly accepted invalid volume")
        } catch let error as EPUBExportError {
            try expect(error == expected, "expected \(expected), got \(error)")
        }
    }

    static func remove(_ url: URL) { try? FileManager.default.removeItem(at: url.deletingLastPathComponent()) }
    static func expect(_ condition: Bool, _ description: String) throws {
        guard condition else { throw CheckFailure(description: description) }
    }
}
'''


def expect(condition: bool, description: str) -> None:
    if not condition:
        raise AssertionError(description)


def paragraph_text(element: ET.Element) -> str:
    result = element.text or ""
    for child in element:
        result += "\n" if child.tag == f"{{{NS['html']}}}br" else "".join(child.itertext())
        result += child.tail or ""
    return result


def normalized_paragraphs(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    groups: list[str] = []
    lines: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            if lines:
                groups.append("\n".join(lines))
                lines = []
        else:
            lines.append(line)
    if lines:
        groups.append("\n".join(lines))
    return groups


def inspect_epub(path: Path, volume: dict) -> int:
    raw = path.read_bytes()
    header = struct.unpack_from("<IHHHHHIIIHH", raw)
    expect(header[0] == 0x04034B50 and header[3] == 0, "first ZIP entry is stored")
    expect(header[-2:] == (8, 0), "mimetype has its exact filename length and no extra field")
    expect(raw[30:38] == b"mimetype" and raw[38:58] == b"application/epub+zip", "mimetype is first, exact and unpadded")
    with zipfile.ZipFile(path) as archive:
        expect(archive.testzip() is None, f"CRC checks pass for {path.name}")
        names = archive.namelist()
        expect(names[0] == "mimetype" and len(names) == len(set(names)), "archive members are unique and ordered")
        expect(archive.read("mimetype") == b"application/epub+zip", "mimetype contains no whitespace or BOM")
        css = archive.read("EPUB/styles.css").decode("utf-8")
        expect(".unit-incipit" not in css, "incipit anchors inherit the normal verse font, size and weight")
        for info in archive.infolist():
            expect(info.compress_type == zipfile.ZIP_STORED and not info.extra, "stored entries have no extra fields")
            expect(not info.flag_bits & 1 and not info.flag_bits & 8, "entries are unencrypted with explicit CRC and size")
            expect(info.date_time == (1980, 1, 1, 0, 0, 0), "archive timestamps are fixed")
            expect(not info.filename.startswith("/") and ".." not in info.filename.split("/"), "archive paths are safe")

        container = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container.find("ocf:rootfiles/ocf:rootfile", NS)
        expect(rootfile is not None and rootfile.attrib["media-type"] == "application/oebps-package+xml", "container identifies the OPF")
        package_path = rootfile.attrib["full-path"]
        package = ET.fromstring(archive.read(package_path))
        expect(package.attrib["version"] == "3.0", "EPUB 3 package version")
        metadata = package.find("opf:metadata", NS)
        expect(metadata.find("dc:title", NS).text == volume["title"], "book title survives escaping")
        expect(metadata.find("dc:creator", NS).text == "Rudolf Steiner", "author metadata")
        expect(metadata.find("dc:language", NS).text == volume["language"], "language metadata")
        if volume["state"] == "published_seed":
            excerpt = "Textauszug" if volume["language"].lower().startswith("de") else "Excerpt"
            expect(excerpt in metadata.find("dc:description", NS).text, "excerpt editions identify their scope in metadata")
        identifiers = metadata.findall("dc:identifier", NS)
        expect(any(item.attrib.get("id") == package.attrib["unique-identifier"] for item in identifiers), "unique identifier resolves")
        expect(any(item.text == volume["ga_number"] for item in identifiers), "GA identifier is included")
        modified = [item for item in metadata.findall("opf:meta", NS) if item.attrib.get("property") == "dcterms:modified"]
        expect(len(modified) == 1 and modified[0].text == "2023-11-14T22:13:20Z", "single UTC modification timestamp")

        base = posixpath.dirname(package_path)
        manifest = package.find("opf:manifest", NS)
        items = {item.attrib["id"]: item.attrib for item in manifest}
        expect(len(items) == len(manifest), "manifest IDs are unique")
        declared = {posixpath.join(base, item["href"]) for item in items.values()}
        expect(declared == set(names) - {"mimetype", "META-INF/container.xml", package_path}, "manifest covers all publication resources")
        for item in items.values():
            expect(posixpath.join(base, item["href"]) in names, "every manifest resource exists")
        nav_items = [item for item in items.values() if "nav" in item.get("properties", "").split()]
        expect(len(nav_items) == 1, "exactly one EPUB navigation document")
        nav = ET.fromstring(archive.read(posixpath.join(base, nav_items[0]["href"])))
        toc = nav.find(".//html:nav", NS)
        expect(toc is not None and toc.attrib["{http://www.idpf.org/2007/ops}type"] == "toc", "semantic table of contents")
        chapter_paths = [f"chapter-{index + 1}.xhtml" for index in range(len(volume["passages"]))]
        links = [link for node in toc.findall(".//html:li", NS) if node.attrib.get("class") != "main-division"
                 for link in node.findall("html:a", NS)]
        first_targets = list(dict.fromkeys(link.attrib["href"].split("#")[0] for link in links))
        expect(first_targets == ["title.xhtml"] + chapter_paths, "TOC covers every chapter in its original order")
        spine = package.find("opf:spine", NS)
        spine_paths = [items[item.attrib["idref"]]["href"] for item in spine]
        expect(spine_paths == ["title.xhtml", "nav.xhtml"] + chapter_paths, "reading order includes the full book")

        for name in names:
            if name.endswith(".xhtml"):
                document = ET.fromstring(archive.read(name))
                expect(document.tag == f"{{{NS['html']}}}html", "content uses the XHTML namespace")
                expect(document.attrib["{http://www.w3.org/XML/1998/namespace}lang"] == volume["language"], "XHTML language matches the book")
                stylesheet = document.find("html:head/html:link", NS)
                expect(stylesheet is not None and posixpath.join(posixpath.dirname(name), stylesheet.attrib["href"]) in names, "stylesheet reference resolves")
                expect(document.find(".//html:script", NS) is None, "book text cannot inject scripts")
                ids = [node.attrib["id"] for node in document.iter() if "id" in node.attrib]
                expect(len(ids) == len(set(ids)), "document anchor IDs are unique")
                for link in document.findall(".//html:a", NS):
                    target, separator, fragment = link.attrib["href"].partition("#")
                    target_path = posixpath.join(posixpath.dirname(name), target) if target else name
                    expect(target_path in names, "every navigation and note link resolves to an exported file")
                    if separator:
                        target_doc = ET.fromstring(archive.read(target_path))
                        expect(any(node.attrib.get("id") == fragment for node in target_doc.iter()),
                               f"every internal heading, note, backlink and page-list link resolves: {path.name}, {name}, href={link.attrib['href']!r}")

        for index, passage in enumerate(volume["passages"]):
            document = ET.fromstring(archive.read(posixpath.join(base, chapter_paths[index])))
            actual_title = paragraph_text(document.find(".//html:h1", NS))
            fallback = ("Abschnitt" if volume["language"].lower().startswith("de") else "Section") + f" {index + 1}"
            expect(actual_title == (passage["title"] if passage["title"].strip() else fallback), f"chapter title or fallback is retained in {path.name}: {actual_title!r}")
            body = document.find(".//html:div[@class='passage-text']", NS)
            blocks = passage.get("metadata", {}).get("reading_blocks", [])
            if blocks and path.stem != "invalid-structure":
                body_blocks = [node for node in body.iter() if node.attrib.get("id", "").startswith("reading-block-")]
                encoded = passage["text"].encode("utf-16-le")
                expected_blocks = [encoded[block["start_offset"] * 2:block["end_offset"] * 2].decode("utf-16-le") for block in blocks]
                for block_index, (block, node) in enumerate(zip(blocks, body_blocks)):
                    gap = "" if block_index + 1 == len(blocks) else encoded[
                        block["end_offset"] * 2:blocks[block_index + 1]["start_offset"] * 2
                    ].decode("utf-16-le")
                    expect(("joined-next" in node.attrib.get("class", "").split()) == (gap == "\n"),
                           "only a canonical single line feed removes the paragraph margin before the next block")
            else:
                body_blocks = [node for node in body if node.tag != f"{{{NS['html']}}}span"]
                expected_blocks = normalized_paragraphs(passage["text"])
            expect([paragraph_text(p) for p in body_blocks] == expected_blocks, f"all paragraphs and Unicode survive in {path.name}, chapter {index + 1}")
            units = passage.get("metadata", {}).get("reading_sections", [])
            if path.stem == "invalid-work-units":
                expect(body.findall("html:section", NS) == [], "invalid work boundaries preserve the prior block rendering")
                expect(toc.findall(".//html:li[@class='work-unit']", NS) == [], "invalid work boundaries preserve the prior heading navigation")
            elif units:
                exported_units = body.findall("html:section[@class='reading-section']", NS)
                expect(len(exported_units) == len(units), "each audited work has one sibling section within its original chapter")
                unit_entries = [node for node in toc.findall(".//html:li[@class='work-unit']", NS)
                                if node.find("html:a", NS).attrib["href"].split("#")[0] == chapter_paths[index]]
                expect(len(unit_entries) == len(units), "all work units have sibling navigation entries")
                expect(any(all(entry in list(parent) for entry in unit_entries) for parent in toc.findall(".//html:ol", NS)),
                       "work entries share one navigation parent")
                for unit_index, (unit, exported, entry) in enumerate(zip(units, exported_units, unit_entries)):
                    expect(exported.attrib["id"] == f"reading-section-{unit_index + 1}" and exported.attrib["data-section-id"] == unit["id"],
                           "work section anchors retain their source-bound IDs")
                    expect(exported.attrib["data-label-kind"] == entry.attrib["data-label-kind"] == unit["label_kind"],
                           "source-title and incipit labels keep their distinct semantics")
                    expect(entry.find("html:a", NS).text == unit["title"] and entry.find("html:a", NS).attrib["href"] ==
                           f"{chapter_paths[index]}#reading-section-{unit_index + 1}", "unit labels and links match the exact metadata")
                    unit_blocks = [(block_index, block) for block_index, block in enumerate(blocks)
                                   if block["start_offset"] >= unit["start_offset"] and block["end_offset"] <= unit["end_offset"]]
                    expect([node.attrib["id"] for node in exported if node.attrib.get("id", "").startswith("reading-block-")] == [f"reading-block-{block_index + 1}" for block_index, _ in unit_blocks],
                           "all existing verse stanzas stay inside their audited work")
                    label = next(node for node in document.iter() if node.attrib.get("id") == exported.attrib["aria-labelledby"])
                    expect(paragraph_text(label) == unit["title"], "unit labels refer to source text once, including the passage title preamble")
                    if unit["label_kind"] == "incipit":
                        first_verse = exported.find("html:p", NS)
                        expect(label.tag == f"{{{NS['html']}}}span" and "role" not in label.attrib and "aria-level" not in label.attrib and "style" not in label.attrib,
                               "incipits remain normal source verse, without heading semantics or an added text label")
                        expect(label in list(first_verse), "the normal incipit anchor remains inside its intact verse stanza")
                    elif unit_index > 0:
                        expect(label.tag == f"{{{NS['html']}}}h1" and "unit-source-title" in label.attrib["class"].split(),
                               "existing source titles use the same sibling work-heading level")
                    expected_children = [expected_blocks[block_index] for block_index, block in unit_blocks
                                         if block["kind"] == "heading" and not (block["start_offset"] == unit["start_offset"] and
                                             expected_blocks[block_index] == unit["title"])]
                    child_list = entry.find("html:ol", NS)
                    actual_children = [] if child_list is None else [link.text for link in child_list.findall(".//html:a", NS)]
                    expect(actual_children == expected_children,
                           "internal headings remain within their work and its own source label is not duplicated as a child")
                expect(sum(1 for node in document.iter() if node.tag in {f"{{{NS['html']}}}h1", f"{{{NS['html']}}}h2"} and
                           paragraph_text(node) == units[0]["title"]) == 1, "the first source title appears only once")
                if path.stem in {"work-units", "inline-title-work-units"}:
                    expect([paragraph_text(node) for node in exported_units[0] if node.attrib.get("id", "").startswith("reading-block-") and node.tag.rsplit("}", 1)[-1].startswith("h") and paragraph_text(node) != units[0]["title"]] == ["J", "B"],
                           "only J and B belong below the first audited work")
                expect(document.find("html:body/html:section/html:h1", NS) is None, "the first work title is not a shared heading over all sibling works")
                first_label = next(node for node in document.iter() if node.attrib.get("id") == exported_units[0].attrib["aria-labelledby"])
                expect(first_label in list(exported_units[0]) and first_label.tag == f"{{{NS['html']}}}h1",
                       "the original passage title belongs only to the first work section, as a preamble or existing source heading")
                if passage.get("metadata", {}).get("group_title") == "Anthroposophischer Seelenkalender" and len(units) == 6:
                    expect([unit["title"] for unit in units] == ["VORWORT ZUR ERSTEN AUSGABE 1912/13", "VORWORT ZUR ZWEITEN AUSGABE 1918", "FRÜHLING", "SOMMER", "HERBST", "WINTER"],
                           "both prefaces and all four seasons have independent source-title navigation entries")
                    expect(all(entry.find("html:ol", NS) is None for entry in unit_entries[:2]),
                           "neither preface contains the other preface or calendar seasons in navigation")
                    poem_numbers = [[int(link.text) for link in entry.findall(".//html:a", NS) if (link.text or "").isdigit()]
                                    for entry in unit_entries[2:]]
                    expect([len(numbers) for numbers in poem_numbers] == [13, 13, 9, 17] and
                           [number for numbers in poem_numbers for number in numbers] == list(range(1, 53)),
                           "all 52 calendar sayings stay beneath their original season, in source order")
            if path.stem == "dramatic-spacing":
                expect(["joined-next" in node.attrib["class"].split() for node in body_blocks] == [True, True, False, True, False],
                       "speaker and stage cue attach to the speech while double line feeds retain paragraph gaps")
                expect([len(node.findall("html:br", NS)) for node in body_blocks] == [0, 0, 1, 0, 0],
                       "the internal verse line feed remains a visible line break")
                expect("p.joined-next { margin-bottom: 0; }" in css and "p { margin: 0 0 1em;" in css,
                       "joined blocks suppress their bottom margin while normal paragraphs retain theirs")
                exported_text = "".join(paragraph_text(node) for node in body_blocks)
                original_text = "".join(expected_blocks)
                expect(exported_text == original_text and len(exported_text) == len(original_text),
                       "compacting dramatic blocks preserves every canonical content character")
            elif path.stem == "structured":
                expect([p.tag.rsplit("}", 1)[-1] for p in body_blocks] == ["h2", "h3", "h4", "p"], "heading levels and verse blocks have semantic elements")
                expect(body_blocks[-1].attrib["class"] == "reading-verse" and len(body_blocks[-1].findall("html:br", NS)) == 1, "one true verse line feed is retained")
                references = body.findall(".//html:a", NS)
                expect(len(references) == 1 and "".join(references[0].itertext()) == "*", "only the anchored star links to its source note")
                expect(references[0].attrib["href"] == "#annotation-1" and references[0].attrib["{http://www.idpf.org/2007/ops}type"] == "noteref", "EPUB noteref resolves locally")
                backlink = document.find(".//html:section[@class='edition-notes']/html:ol/html:li/html:p/html:a", NS)
                expect(backlink is not None and backlink.attrib["href"] == "#" + references[0].attrib["id"], "edition note links back to its exact source marker")
                expect(document.find(".//html:p[@class='group-title']", NS).text == "Anthroposophischer Seelenkalender", "main division title survives export")
                outline = [link.attrib["href"] for link in toc.findall(".//html:a", NS) if "#reading-block-" in link.attrib["href"]]
                expect(outline == ["chapter-1.xhtml#reading-block-1", "chapter-1.xhtml#reading-block-2", "chapter-1.xhtml#reading-block-3"], "internal heading navigation preserves the complete poem hierarchy")
                page_list = nav.find(".//html:nav[@id='page-list']", NS)
                page_links = page_list.findall("html:ol/html:li/html:a", NS)
                page_breaks = document.findall(".//html:span[@role='doc-pagebreak']", NS)
                expect([link.text for link in page_links] == ["9", "10", "11", "12"], "source pages have a semantic page list")
                expect(len(page_breaks) == 4 and all(not "".join(point.itertext()) for point in page_breaks), "page anchors insert no text, including in separator gaps or at the end")
                expect([link.attrib["href"].split("#")[-1] for link in page_links] == [point.attrib["id"] for point in page_breaks], "all page-list links resolve to their exact pagebreak IDs")
            elif path.stem == "overlapping-notes":
                references = body.findall(".//html:a", NS)
                expect([link.attrib["href"] for link in references] ==
                       ["#annotation-1", "#annotation-3", "#annotation-1", "#annotation-1"],
                       "overlapping legacy markers keep their prior rendering and anchored notes retain their exact reference")
                notes = document.findall(".//html:section[@class='edition-notes']/html:ol/html:li", NS)
                backlinks = [note.find("html:p/html:a", NS) for note in notes]
                expect(backlinks[1] is None and backlinks[3] is None,
                       "omitted duplicate and overlapping star references cannot produce dangling backlinks")
                expect([backlinks[index].attrib["href"] for index in (0, 2)] ==
                       ["#" + references[index].attrib["id"] for index in (0, 1)],
                       "both structured and legacy text return only to references actually emitted")
            elif path.stem == "invalid-structure":
                expect(all(p.tag == f"{{{NS['html']}}}p" for p in body_blocks), "invalid structure renders all original text as legacy paragraphs")
            if passage.get("source_label"):
                provenance = document.find(".//html:p[@class='provenance']", NS)
                expect(provenance is not None and passage["source_label"] in provenance.text, "source provenance is retained")
            annotations = passage.get("metadata", {}).get("annotations", [])
            notes = document.findall(".//html:section[@class='edition-notes']/html:ol/html:li", NS)
            expect(len(notes) == len(annotations), "all edition notes are exported")
            for note, annotation in zip(notes, annotations):
                expect([paragraph_text(p) for p in list(note)[1:]] == normalized_paragraphs(annotation["text"]), "edition note text survives escaping")
        title_page = ET.fromstring(archive.read(posixpath.join(base, "title.xhtml")))
        if volume["state"] == "published_seed":
            expect(title_page.find(".//html:p[@class='excerpt']", NS).text == excerpt, "excerpt editions visibly identify their scope")
        if volume.get("source_summary"):
            source_paragraphs = title_page.findall(".//html:section[@class='edition']/html:p", NS)
            expect([paragraph_text(p) for p in source_paragraphs] == normalized_paragraphs(volume["source_summary"]), "book source and edition summary are retained")
    return len(volume["passages"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content", type=Path, help="Also export and verify a canonical JSON or gzip payload")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="ga-epub-check-") as directory:
        output = Path(directory)
        harness = output / "EPUBExportChecks.swift"
        harness.write_text(HARNESS)
        executable = output / "checks"
        subprocess.run(
            ["swiftc", "-swift-version", "6", "-parse-as-library",
             str(ROOT / "apple/GA/Models.swift"), str(ROOT / "apple/GA/SeedLibrary.swift"),
             str(ROOT / "apple/GA/EPUBExporter.swift"), str(harness), "-o", str(executable)],
            check=True,
        )
        command = [str(executable), str(ROOT / "apple/GA/BundledContent"), str(output)]
        if args.content:
            raw = args.content.read_bytes()
            if args.content.suffix == ".gz":
                raw = gzip.decompress(raw)
            fixture = output / "external-content.json"
            fixture.write_bytes(raw)
            command.append(str(fixture))
        subprocess.run(command, check=True)
        cases = json.loads((output / "cases.json").read_text())
        total_chapters = 0
        for case in cases:
            volume = json.loads((output / case["volume"]).read_text())
            total_chapters += inspect_epub(output / case["epub"], volume)
        print(f"Independent EPUB checks passed: {len(cases)} books, {total_chapters} chapters; ZIP/CRC integrity, OCF container, metadata, manifest, TOC/spine order, escaped full text and edition notes.")


if __name__ == "__main__":
    main()
