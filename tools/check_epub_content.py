#!/usr/bin/env python3
"""Exercise EPUB content resolution with actual Swift sources and isolated fixtures.

Run: python3 tools/check_epub_content.py
Requires the macOS Swift 6 toolchain. Never reads or writes app user data.
"""

from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
import Foundation

private struct CheckFailure: Error, CustomStringConvertible {
    let description: String
}

private final class CallLog: @unchecked Sendable {
    private let lock = NSLock()
    private var calls: [String] = []

    func record(_ call: String) {
        lock.lock()
        defer { lock.unlock() }
        calls.append(call)
    }

    var events: [String] {
        lock.lock()
        defer { lock.unlock() }
        return calls
    }
}

@main
private enum EPUBContentChecks {
    static func main() async {
        do {
            try await run()
            print("EPUB content checks passed: complete snapshots, revision-aware downloads and caches, older offline editions, stale readers, seed excerpts, full downloads, cache failures, partial/blank content, localized errors and cancellation.")
        } catch {
            print("EPUB content check failed: \(error)")
            exit(1)
        }
    }

    private static func run() async throws {
        let one = [passage(1)]
        let two = [passage(1), passage(2)]
        let three = two + [passage(3)]

        let snapshotLog = CallLog()
        let original = volume(passages: three, expected: 2)
        let complete = try await EPUBExportContent.prepare(volume: original,
            sources: sources(local: one, bundled: two, downloaded: one, log: snapshotLog))
        try expect(complete == original && snapshotLog.events.isEmpty,
                   "a complete larger reader snapshot is retained without loading smaller caches")

        let currentRevision = String(repeating: "b", count: 64)
        let olderRevision = String(repeating: "a", count: 64)
        var olderSnapshot = volume(passages: two, expected: 3)
        olderSnapshot.catalogContentRevision = currentRevision
        olderSnapshot.downloadedContentRevision = olderRevision
        olderSnapshot.downloadedPassageCount = two.count
        let olderSnapshotLog = CallLog()
        let exportedOlder = try await EPUBExportContent.prepare(volume: olderSnapshot,
            sources: sources(log: olderSnapshotLog))
        try expect(exportedOlder == olderSnapshot && olderSnapshotLog.events.isEmpty && exportedOlder.hasContentUpdate,
                   "a complete older downloaded edition remains exportable offline while an update is available")

        var newerCatalog = volume(passages: [], expected: 3)
        newerCatalog.catalogContentRevision = currentRevision
        let olderCacheLog = CallLog()
        let fromOlderCache = try await EPUBExportContent.prepare(volume: newerCatalog,
            sources: sources(local: two, localRevision: olderRevision, log: olderCacheLog))
        try expect(fromOlderCache.passages == two && fromOlderCache.downloadedContentRevision == olderRevision
                   && fromOlderCache.downloadedPassageCount == two.count && fromOlderCache.hasContentUpdate
                   && olderCacheLog.events == ["local"],
                   "a saved complete older edition retains its revision and count without requiring a server update")

        let localLog = CallLog()
        let stale = volume(passages: one, expected: 2)
        let fromLocal = try await EPUBExportContent.prepare(volume: stale,
            sources: sources(local: two, downloaded: three, log: localLog))
        try expect(fromLocal.passages == two && localLog.events == ["local"],
                   "a stale reader uses a complete local download while offline")

        let bundledLog = CallLog()
        let fromBundle = try await EPUBExportContent.prepare(volume: volume(passages: one, expected: 3),
            sources: sources(local: two, bundled: three, log: bundledLog))
        try expect(fromBundle.passages == three && bundledLog.events == ["local", "bundled"],
                   "a partial local cache falls through to complete bundled content")

        let downloadedLog = CallLog()
        let downloaded = try await EPUBExportContent.prepare(volume: volume(passages: [], expected: 2),
            sources: sources(local: one, downloaded: three, log: downloadedLog))
        try expect(downloaded.passages == three && downloaded.catalogPassageCount == 3,
                   "newer full downloads can contain more sections than the old catalog")
        try expect(downloadedLog.events == ["local", "bundled", "download:/api/catalog/test/content:test", "save:test:3"],
                   "download receives the normalized advertised path and book identity, then caches complete content")

        var revisionedCatalog = volume(passages: [], expected: 2)
        revisionedCatalog.catalogContentRevision = currentRevision
        let revisionLog = CallLog()
        let revisionedDownload = try await EPUBExportContent.prepare(volume: revisionedCatalog,
            sources: sources(downloaded: two, downloadedRevision: currentRevision, log: revisionLog))
        try expect(revisionedDownload.downloadedContentRevision == currentRevision
                   && revisionedDownload.downloadedPassageCount == two.count && !revisionedDownload.hasContentUpdate,
                   "a verified new download records its exact revision and does not offer the same edition as an update")
        try expect(revisionLog.events == ["local", "bundled", "download:/api/catalog/test/content:test",
                                         "expected-revision:\(currentRevision)", "save:test:2", "saved-revision:\(currentRevision)"],
                   "download verification receives the advertised revision and cache persistence receives the downloaded revision")

        let writeFailureLog = CallLog()
        let afterCacheFailure = try await EPUBExportContent.prepare(volume: volume(passages: [], expected: 2),
            sources: sources(downloaded: two, log: writeFailureLog, cacheWriteFails: true))
        try expect(afterCacheFailure.passages == two && writeFailureLog.events.last == "save:test:2",
                   "failure to save the cache does not prevent sharing downloaded content")

        var blank = two
        blank[1].text = " \n\t "
        let blankCacheLog = CallLog()
        let afterBlankCache = try await EPUBExportContent.prepare(volume: volume(passages: blank, expected: 2),
            sources: sources(local: blank, bundled: two, log: blankCacheLog))
        try expect(afterBlankCache.passages == two && blankCacheLog.events == ["local", "bundled"],
                   "a blank chapter in a snapshot or cache requires a complete alternative")

        var duplicate = two
        duplicate[1].id = duplicate[0].id
        let invalidCacheLog = CallLog()
        let afterInvalidCache = try await EPUBExportContent.prepare(volume: volume(passages: duplicate, expected: 2),
            sources: sources(local: duplicate, downloaded: two, log: invalidCacheLog))
        try expect(afterInvalidCache.passages == two && invalidCacheLog.events.contains("download:/api/catalog/test/content:test"),
                   "duplicate chapter identifiers in stored content require a fresh download")
        try await expectError(.invalidPassageIdentifiers, volume: volume(passages: [], expected: 2),
            sources: sources(downloaded: duplicate, log: CallLog()))
        var invalidID = two
        invalidID[0].id = " \t"
        try await expectError(.invalidPassageIdentifiers, volume: volume(passages: [], expected: 2),
            sources: sources(downloaded: invalidID, log: CallLog()))

        let partialLog = CallLog()
        try await expectError(.incomplete(expected: 3, actual: 2),
            volume: volume(passages: one, expected: 3),
            sources: sources(local: two, downloaded: two, log: partialLog))
        try expect(!partialLog.events.contains(where: { $0.hasPrefix("save:") }),
                   "a partial download never overwrites the content cache")
        try await expectError(.emptyChapter, volume: volume(passages: [], expected: 2),
            sources: sources(downloaded: blank, log: CallLog()))
        try await expectError(.unavailable, volume: volume(passages: [], expected: 2),
            sources: sources(downloaded: [], log: CallLog()))

        var unavailable = volume(passages: one, expected: 2)
        unavailable.contentPath = " \n "
        try await expectError(.unavailable, volume: unavailable,
            sources: sources(log: CallLog()))
        try await expectError(.downloadFailed, volume: volume(passages: one, expected: 2),
            sources: sources(log: CallLog()))

        var seed = volume(passages: one, expected: nil)
        seed.publicationState = .publishedSeed
        let seedLog = CallLog()
        let fullSeed = try await EPUBExportContent.prepare(volume: seed,
            sources: sources(downloaded: two, log: seedLog))
        try expect(fullSeed.passages == two && seedLog.events.contains("download:/api/catalog/test/content:test"),
                   "unverified seed excerpts fetch all available edition content")
        seed.catalogPassageCount = 1
        let verifiedLog = CallLog()
        let verifiedSeed = try await EPUBExportContent.prepare(volume: seed,
            sources: sources(log: verifiedLog))
        try expect(verifiedSeed == seed && verifiedLog.events.isEmpty,
                   "an edition explicitly advertising one seed section remains exportable")

        var cancelling = sources(log: CallLog())
        cancelling.download = { _, _, _ in throw CancellationError() }
        do {
            _ = try await EPUBExportContent.prepare(volume: volume(passages: [], expected: 1), sources: cancelling)
            throw CheckFailure(description: "cancellation was not propagated")
        } catch is CancellationError {
            // Cancellation must remain cancellation for the system sharing operation.
        }
    }

    private static func sources(local: [GAPassage]? = nil, bundled: [GAPassage]? = nil,
                                downloaded: [GAPassage]? = nil, localRevision: String? = nil,
                                downloadedRevision: String? = nil, log: CallLog,
                                cacheWriteFails: Bool = false) -> EPUBExportContent.Sources {
        EPUBExportContent.Sources(
            loadLocal: { id in
                log.record("local")
                return local.map { LocalContentStore.Edition(workID: id, passageCount: $0.count,
                    contentRevision: localRevision, passages: $0, isLegacy: localRevision == nil) }
            },
            loadBundled: { id in
                log.record("bundled")
                return bundled.map { LocalContentStore.Edition(workID: id, passageCount: $0.count,
                    contentRevision: nil, passages: $0, isLegacy: true) }
            },
            download: { path, id, expectedRevision in
                log.record("download:\(path):\(id)")
                if let expectedRevision { log.record("expected-revision:\(expectedRevision)") }
                guard let downloaded else {
                    throw CheckFailure(description: "English underlying network failure")
                }
                return LocalContentStore.Edition(workID: id, passageCount: downloaded.count,
                    contentRevision: downloadedRevision, passages: downloaded)
            },
            save: { passages, id, revision in
                log.record("save:\(id):\(passages.count)")
                if let revision { log.record("saved-revision:\(revision)") }
                if cacheWriteFails { throw CheckFailure(description: "cache unavailable") }
            }
        )
    }

    private static func passage(_ index: Int) -> GAPassage {
        GAPassage(id: "chapter-\(index)", title: "Kapitel \(index)", gaPage: nil,
                  sourceLabel: "Testausgabe", text: "Vollständiger Abschnitt \(index).")
    }

    private static func volume(passages: [GAPassage], expected: Int?) -> GAVolume {
        GAVolume(id: "test", gaNumber: "GA 999", title: "Prüfbuch", subtitle: "",
                 languageCode: "de", yearLabel: "1900", type: .book, priority: 1,
                 publicationState: .published, proofingState: .humanProofed,
                 sourceSummary: "Testausgabe", tags: [], passages: passages, sanityChecks: [],
                 contentPath: " /api/catalog/test/content \n", catalogPassageCount: expected)
    }

    private static func expectError(_ expected: EPUBExportContentError, volume: GAVolume,
                                    sources: EPUBExportContent.Sources) async throws {
        do {
            _ = try await EPUBExportContent.prepare(volume: volume, sources: sources)
            throw CheckFailure(description: "expected export failure: \(expected)")
        } catch let error as EPUBExportContentError {
            try expect(String(describing: error) == String(describing: expected),
                       "expected \(expected), received \(error)")
            try expect(error.localizedDescription.hasPrefix("Der ") || error.localizedDescription.hasPrefix("Für "),
                       "export failures have a German localized description")
        }
    }

    private static func expect(_ condition: @autoclosure () -> Bool, _ description: String) throws {
        guard condition() else { throw CheckFailure(description: description) }
    }
}
'''


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ga-epub-content-check-") as directory:
        directory = Path(directory)
        source = directory / "EPUBContentChecks.swift"
        source.write_text(HARNESS)
        executable = directory / "checks"
        subprocess.run(
            ["swiftc", "-swift-version", "6", "-parse-as-library",
             str(ROOT / "apple/GA/Models.swift"), str(ROOT / "apple/GA/EPUBExportContent.swift"),
             str(source), "-o", str(executable)],
            check=True,
        )
        subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    main()
