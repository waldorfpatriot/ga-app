#!/usr/bin/env python3
"""Check library search and catalog persistence against actual Swift sources.

Run: python3 tools/check_library_search.py
Requires the macOS Swift 6 toolchain. Compiles a disposable executable, reads
bundled public-domain content, and never creates ReadingStore or app user data.
"""

from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''

private struct ContentFixture: Decodable {
    var passages: [GAPassage]
}

private struct CheckFailure: Error, CustomStringConvertible {
    let description: String
}

@main
private enum LibrarySearchChecks {
    @MainActor
    static func main() {
        do {
            try run()
            print("Library search checks passed: bundled content, GA/page references, UTF-16 positions, Unicode snippets, notes, result limits and catalog persistence.")
        } catch {
            fputs("Library search check failed: \(error)\n", stderr)
            exit(1)
        }
    }

    @MainActor
    private static func run() throws {
        let fixtureRoot = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        func bundledVolume(_ id: String) throws -> GAVolume {
            guard var volume = SeedLibrary.volumes.first(where: { $0.id == id }) else {
                throw CheckFailure(description: "missing seeded work \(id)")
            }
            let data = try Data(contentsOf: fixtureRoot.appendingPathComponent("\(id).json"))
            volume.passages = try JSONDecoder().decode(ContentFixture.self, from: data).passages
            volume.catalogPassageCount = volume.passages.count
            return volume
        }
        let philosophy = try bundledVolume("ga-004")
        let knowledge = try bundledVolume("ga-003")
        let theosophy = try bundledVolume("ga-009")
        let bundled = [philosophy, knowledge, theosophy]
        try expect(philosophy.passages.count > 10 && !knowledge.passages.isEmpty && !theosophy.passages.isEmpty,
                   "actual bundled reader fixtures load")

        let realTextHits = LibrarySearch.find("WURZELFRAGEN", in: bundled, annotations: [])
        try expect(realTextHits.contains { $0.volumeID == "ga-004" && $0.passageID == philosophy.passages.first?.id },
                   "case-insensitive search reaches bundled full text")
        for hit in realTextHits where hit.passageID != nil {
            let passage = bundled.first(where: { $0.id == hit.volumeID })!.passages.first(where: { $0.id == hit.passageID })!
            let tail = (passage.text as NSString).substring(from: hit.offset)
            try expect(tail.lowercased().hasPrefix("wurzelfragen"), "bundled hit offset opens the matching text")
        }

        for alias in ["GA4", "GA004", "GA 004", "ga 0004"] {
            let hits = LibrarySearch.find(alias, in: bundled, annotations: [])
            try expect(hits.count == 1 && hits[0].volumeID == "ga-004" && hits[0].passageID == nil,
                       "\(alias) identifies the whole work")
        }
        let sourcePages = LibrarySearch.find("S. 15", in: bundled, annotations: [])
        try expect(Set(sourcePages.map(\.volumeID)) == Set(["ga-004", "ga-003"]),
                   "source-page lookup searches across downloaded works")
        let scopedPage = LibrarySearch.find("GA3 S15", in: bundled, annotations: [])
        try expect(scopedPage.count == 1 && scopedPage[0].volumeID == "ga-003" && scopedPage[0].passageID == knowledge.passages[1].id,
                   "combined GA/page reference is scoped to the requested work")
        let alternatePage = LibrarySearch.find("GA 004 Seite 15", in: bundled, annotations: [])
        try expect(alternatePage.count == 1 && alternatePage[0].volumeID == "ga-004", "written-out page reference")
        for hit in sourcePages + scopedPage + alternatePage {
            try expect(hit.offset == 0 && hit.passageID != nil && hit.context.contains("Quelle S. 15") && hit.excerpt.contains("Abschnitt"),
                       "page references promise section-level navigation and name the source page")
        }
        try expect(LibrarySearch.find("GA3 S99999", in: bundled, annotations: []).isEmpty,
                   "missing source page does not invent a reader location")
        try expect(LibrarySearch.find("GA9999", in: bundled, annotations: []).isEmpty, "missing GA work")

        let emojiText = "📖 Über Erkenntnis, Freiheit und Denken."
        let emojiPassage = GAPassage(id: "emoji-chapter", title: "Gedankenkapitel", gaPage: nil,
                                    sourceLabel: "Fixture", text: emojiText)
        let emojiWork = work(id: "emoji-work", number: "GA 999", title: "Freiheitsbuch", passages: [emojiPassage])
        let insensitive = LibrarySearch.find("uBER", in: [emojiWork], annotations: [])
        try expect(insensitive.count == 1 && insensitive[0].passageID == emojiPassage.id && insensitive[0].offset == 3,
                   "case/diacritic-insensitive match stores a UTF-16 offset after an emoji")
        try expect((emojiText as NSString).substring(from: insensitive[0].offset).hasPrefix("Über"),
                   "UTF-16 hit round-trips through the native reader API")
        let metadataHits = LibrarySearch.find("Freiheitsbuch", in: [emojiWork], annotations: [])
        try expect(metadataHits.count == 1 && metadataHits[0].passageID == nil && metadataHits[0].offset == 0,
                   "title result targets a work")
        let chapterHits = LibrarySearch.find("Gedankenkapitel", in: [emojiWork], annotations: [])
        try expect(chapterHits.count == 1 && chapterHits[0].passageID == emojiPassage.id && chapterHits[0].offset == 0,
                   "chapter title targets the beginning of its passage")

        let family = "👨‍👩‍👧‍👦"
        let clusterBody = "xxx" + family + String(repeating: "a", count: 68) + "Nadel" + String(repeating: "b", count: 137) + family + "Ende"
        let clusterPassage = GAPassage(id: "clusters", title: "Unicode", gaPage: nil, sourceLabel: "Fixture", text: clusterBody)
        let clusterWork = work(id: "clusters", number: "GA 998", title: "Unicode", passages: [clusterPassage])
        let clusterHits = LibrarySearch.find("Nadel", in: [clusterWork], annotations: [])
        try expect(clusterHits.count == 1 && clusterHits[0].offset == 82, "exact UTF-16 anchor after a joined emoji")
        try expect(clusterHits[0].excerpt.components(separatedBy: family).count == 3 && !clusterHits[0].excerpt.contains("�"),
                   "snippets preserve whole composed emojis at both excerpt boundaries")

        let note = PersonalAnnotation(id: "scoped-note", volumeID: emojiWork.id, passageID: emojiPassage.id,
            location: 3, length: 4, quote: "Über", note: "Meine Sternennotiz", color: .blue, isBookmark: false, updatedAt: .distantPast)
        let foreignNote = PersonalAnnotation(id: "foreign-note", volumeID: "missing-work", passageID: "missing-passage",
            location: 300, length: 4, quote: "Über", note: "Sternennotiz", color: .pink, isBookmark: false, updatedAt: .distantPast)
        let noteHits = LibrarySearch.find("sternennotiz", in: [emojiWork], annotations: [foreignNote, note])
        try expect(noteHits.count == 1 && noteHits[0].volumeID == emojiWork.id && noteHits[0].passageID == emojiPassage.id && noteHits[0].offset == 3,
                   "personal note search preserves its work, passage and range; unknown works are excluded")
        let quoteHits = LibrarySearch.find("Über", in: [emojiWork], annotations: [note])
        try expect(quoteHits.first?.id == "note:scoped-note", "matching personal notes lead full-text hits")
        var bookmark = note
        bookmark.id = "bookmark"
        bookmark.isBookmark = true
        let bookmarkHits = LibrarySearch.find("sternennotiz", in: [emojiWork], annotations: [bookmark])
        try expect(bookmarkHits.first?.title == "Lesezeichen", "bookmark search is identified separately")

        for query in ["", " ", "a", "UnauffindbaresZufallswort"] {
            try expect(LibrarySearch.find(query, in: bundled + [emojiWork], annotations: [note]).isEmpty,
                       "empty, too-short and missing queries return no results")
        }
        let manyVolumes = (0..<130).map { index in
            work(id: "limit-\(index)", number: "GA \(1000 + index)", title: "Grenztreffer \(index)", passages: [])
        }
        let limited = LibrarySearch.find("Grenztreffer", in: manyVolumes, annotations: [])
        try expect(limited.count == 100 && Set(limited.map(\.id)).count == 100, "library-wide results are bounded and unique")
        let repeatPassage = GAPassage(id: "repeat", title: "Repetition", gaPage: nil, sourceLabel: "Fixture",
                                     text: "Treffer Treffer Treffer Treffer Treffer")
        let repeatHits = LibrarySearch.find("Treffer", in: [work(id: "repeat", number: "GA 997", title: "Repetition", passages: [repeatPassage])], annotations: [])
        try expect(repeatHits.count == 3 && repeatHits.map(\.offset) == [0, 8, 16],
                   "repeated passages contribute bounded, distinct locations")

        let encodedWork = try JSONEncoder().encode(philosophy)
        let decodedWork = try JSONDecoder().decode(GAVolume.self, from: encodedWork)
        try expect(decodedWork == philosophy, "complete bundled work survives a Codable round trip")
        try expect(decodedWork.passages.contains { !$0.metadata.annotations.isEmpty }, "actual source annotations survive persistence")
        try expect(decodedWork.passages.map(\.metadata) == philosophy.passages.map(\.metadata), "source pages and edition notes retain metadata")
        var metadataOnly = philosophy
        metadataOnly.passages = []
        metadataOnly.catalogPassageCount = 321
        let encodedCatalog = try JSONEncoder().encode([metadataOnly])
        let decodedCatalog = try JSONDecoder().decode([GAVolume].self, from: encodedCatalog)
        try expect(decodedCatalog.count == 1 && decodedCatalog[0].passages.isEmpty && decodedCatalog[0].catalogPassageCount == 321,
                   "small catalog cache retains its independently advertised passage count")
        try expect(decodedCatalog[0].contentPath == philosophy.contentPath && decodedCatalog[0].id == philosophy.id,
                   "metadata-only cache still identifies the downloadable work")
        var advertised = philosophy
        advertised.catalogPassageCount = philosophy.passages.count + 20
        let advertisedRoundTrip = try JSONDecoder().decode(GAVolume.self, from: JSONEncoder().encode(advertised))
        try expect(advertisedRoundTrip.catalogPassageCount == advertised.catalogPassageCount && !advertisedRoundTrip.isReadable,
                   "explicit catalog count takes precedence and rejects incomplete cached content")
    }

    private static func work(id: String, number: String, title: String, passages: [GAPassage]) -> GAVolume {
        GAVolume(id: id, gaNumber: number, title: title, subtitle: "", languageCode: "de", yearLabel: "1900",
                 type: .book, priority: 1, publicationState: .published, proofingState: .aiChecked,
                 sourceSummary: "Disposable test fixture", tags: [], passages: passages, sanityChecks: [],
                 contentPath: "/api/catalog/\(id)/content", catalogPassageCount: passages.count)
    }

    private static func expect(_ condition: @autoclosure () -> Bool, _ description: String) throws {
        guard condition() else { throw CheckFailure(description: description) }
    }
}
'''


def main() -> None:
    implementation = (ROOT / "apple/GA/ReadingLibraryView.swift").read_text()
    marker = "struct LibrarySearchHit:"
    if marker not in implementation:
        raise SystemExit("Could not find the library search implementation.")
    source_tail = implementation[implementation.index(marker):]
    with tempfile.TemporaryDirectory(prefix="ga-library-search-check-") as directory:
        directory = Path(directory)
        source = directory / "LibrarySearchChecks.swift"
        source.write_text("import Foundation\n" + source_tail + HARNESS)
        executable = directory / "checks"
        subprocess.run(
            ["swiftc", "-swift-version", "6", "-parse-as-library",
             str(ROOT / "apple/GA/Models.swift"), str(ROOT / "apple/GA/SeedLibrary.swift"),
             str(ROOT / "apple/GA/ReadingStore.swift"), str(source), "-o", str(executable)],
            check=True,
        )
        subprocess.run([str(executable), str(ROOT / "apple/GA/BundledContent")], check=True)


if __name__ == "__main__":
    main()
