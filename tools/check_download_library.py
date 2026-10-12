#!/usr/bin/env python3
"""Validate the complete downloadable catalog against the actual Swift models.

Run after importing the library: python3 tools/check_download_library.py
Compiles Models.swift and SeedLibrary.swift into a disposable executable. Its
injected resource bundle and fixtures never touch the app's saved user data.
"""

import gzip
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
import Foundation

private struct CheckFailure: Error, CustomStringConvertible {
    let description: String
}

@main
private enum DownloadLibraryChecks {
    static func main() {
        do {
            if CommandLine.arguments.count == 3, CommandLine.arguments[1] == "--default-url" {
                try expect(CatalogClient.contentURL(path: "/api/catalog")?.absoluteString == CommandLine.arguments[2],
                           "reader, developer and configured defaults resolve to their intended catalog")
                print("Catalog default URL check passed.")
                return
            }
            try run()
            print("Download library checks passed: 463 works, 324 complete downloads, five offline books with 77 sections, full GA 120, URL prefixes, Unicode, content identity and partial/corrupt-payload rejection.")
        } catch {
            fputs("Download library check failed: \(error)\n", stderr)
            exit(1)
        }
    }

    private static func run() throws {
        let bundleURL = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        let contentRoot = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
        guard let bundle = Bundle(url: bundleURL),
              let catalogURL = bundle.url(forResource: "catalog", withExtension: "json", subdirectory: "BundledCatalog") else {
            throw CheckFailure(description: "disposable resource bundle is unavailable")
        }

        // Decode the public works array independently of the bundle loader.
        let data = try Data(contentsOf: catalogURL)
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let works = object["works"] as? [[String: Any]] else {
            throw CheckFailure(description: "catalog does not contain a works array")
        }
        let encodedWorks = try JSONSerialization.data(withJSONObject: works)
        let catalog = try JSONDecoder().decode([GAVolume].self, from: encodedWorks)
        try expect(catalog.count == 463, "the complete catalog has 463 works")
        try expect(Set(catalog.map(\.id)).count == catalog.count, "catalog work IDs are unique")
        guard let ga354 = catalog.first(where: { $0.id == "ga-354" }) else {
            throw CheckFailure(description: "GA 354 is missing from the complete catalog")
        }
        let artisticWorks = catalog.filter { $0.id.hasPrefix("ga-k-") }
        try expect(!artisticWorks.isEmpty && artisticWorks.allSatisfy { $0.gaSortLabel > ga354.gaSortLabel && !$0.gaSortLabel.hasPrefix("-") },
                   "artistic K entries sort after GA 354 without integer-format overflow")
        let downloadable = catalog.filter(\.isDownloadable)
        let unavailable = catalog.filter { !$0.isDownloadable }
        try expect(downloadable.count == 324 && unavailable.count == 139, "324 texts are downloadable and 139 metadata entries remain visible")
        try expect(downloadable.allSatisfy { $0.contentCompleteness == .complete } &&
                   unavailable.allSatisfy { $0.contentCompleteness == .unavailable },
                   "the catalog explicitly identifies complete books and unavailable metadata")
        try expect(downloadable.filter { $0.publicationState == .published && $0.proofingState == .aiChecked }.count == 5,
                   "only the five existing normalized books keep their published proofing status")
        try expect(downloadable.filter { $0.publicationState == .sanityCheck && $0.proofingState == .needsAISanityCheck }.count == 319,
                   "the 319 imported working editions do not claim completed AI proofing")
        try expect(downloadable.filter { $0.publicationState == .sanityCheck }.allSatisfy {
            $0.sourceSummary.contains("Arbeitsausgabe") && $0.sanityChecks.contains { $0.status == .warning && $0.detail.contains("Kollation") }
        }, "every working edition carries a visible source summary and outstanding collation warning")
        try expect(catalog.allSatisfy { $0.passages.isEmpty }, "catalog metadata does not embed the full text corpus")
        try expect(catalog.allSatisfy { !$0.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }, "every catalog work has a title")
        try expect(catalog.contains { $0.title.contains("ä") || $0.title.contains("ö") || $0.title.contains("ü") }, "catalog titles retain German umlauts")
        try expect(try BundledCatalogStore.loadVolumes(bundle: bundle) == catalog, "real bundle loader agrees with independent catalog decoding")

        let hydrated = SeedLibrary.readerVolumes(in: bundle)
        let bundledCounts = ["ga-003": 10, "ga-004": 18, "ga-009": 16, "ga-010": 16, "ga-013": 17]
        let bundledIDs = Set(bundledCounts.keys)
        try expect(hydrated.count == catalog.count, "seed hydration preserves the complete catalog")
        try expect(Set(hydrated.filter(\.isReadable).map(\.id)) == bundledIDs, "exactly the five complete core books ship offline")
        try expect(hydrated.filter(\.isReadable).reduce(0) { $0 + $1.passages.count } == 77,
                   "the five complete offline books contain all 77 sections")
        try expect(Set(hydrated.map(\.id)) == Set(catalog.map(\.id)), "hydration preserves every catalog ID")
        try expect(hydrated.filter { !$0.isReaderAvailable }.count == 139, "unavailable works remain in the reader catalog")

        for id in bundledIDs {
            guard let seeded = SeedLibrary.volumes.first(where: { $0.id == id }),
                  let volume = hydrated.first(where: { $0.id == id }),
                  let passages = try BundledContentStore.loadPassages(for: id, bundle: bundle) else {
                throw CheckFailure(description: "missing offline fixture \(id)")
            }
            try expect(volume.title == seeded.title && volume.gaNumber == seeded.gaNumber && volume.tags == seeded.tags,
                       "curated metadata survives for \(id)")
            try expect(volume.passages == passages && !passages.isEmpty,
                       "real bundled content hydrates stable passage IDs for \(id)")
            try expect(volume.catalogPassageCount == bundledCounts[id] && passages.count == bundledCounts[id] && volume.isCompleteContent(passages),
                       "offline book \(id) contains its complete advertised section count")
        }
        guard let karma = hydrated.first(where: { $0.id == "ga-120" }) else {
            throw CheckFailure(description: "GA 120 is missing")
        }
        try expect(karma.passages.isEmpty && !karma.isReadable && karma.isDownloadable && karma.catalogPassageCount == 11,
                   "GA 120 starts as metadata with a complete eleven-section download")
        try expect(SeedLibrary.volumes.first(where: { $0.id == karma.id })?.passages.isEmpty == true,
                   "the built-in GA 120 seed contains no partial book")
        try expect(try BundledContentStore.loadPassages(for: karma.id, bundle: bundle) == nil,
                   "GA 120 has no bundled partial text body")
        try expect(karma.publicationState == .sanityCheck && karma.proofingState == .needsAISanityCheck,
                   "GA 120's full working edition carries its current quality status before downloading")

        let karmaData = try Data(contentsOf: contentRoot.appendingPathComponent("ga-120.json"))
        let fullKarma = try CatalogClient.decodePassages(from: karmaData, for: karma.id, expectedPassageCount: karma.catalogPassageCount)
        try expect(fullKarma.count == 11 && karma.isCompleteContent(fullKarma),
                   "the actual GA 120 server body is a complete eleven-lecture book")
        try expect(fullKarma.first?.id == "ga-120-page-15", "the complete GA 120 text preserves the existing first-page anchor")
        var downloadedKarma = karma
        downloadedKarma.passages = fullKarma
        try expect(downloadedKarma.isReadable, "GA 120 becomes readable after its complete book is downloaded")
        try editionChecks(base: karma, passages: fullKarma, data: karmaData)
        try reject(karmaData, for: karma.id, expectedPassageCount: 10,
                   reason: "downloads with more sections than the expected book count are rejected")

        // Keep this fixture independent of the current seeds so removing the old
        // excerpt cannot accidentally remove coverage of saved partial books.
        let legacyKarmaPassage = GAPassage(
            id: "ga-120-page-15", title: "Äußere Beobachtung und Karma", gaPage: "S. 15",
            sourceLabel: "Candidate extraction from GA 120 PDF sample",
            text: """
            Wir würden so etwas finden, wenn zum Beispiel ein Erlebnis in unser Leben hineinträte, bei dem wir uns sagen könnten: Dieses Erlebnis, das da für uns auftritt, steht in einem gewissen Zusammenhange mit einem früheren Erlebnis, an dem wir selber beteiligt sind, zu dem wir selber Veranlassung gegeben haben.

            Versuchen wir einmal - zunächst rein durch Beobachtung des Lebens - festzustellen, ob es so etwas gibt. Wir wollen uns jetzt also rein auf den Standpunkt der äußeren Beobachtung stellen. Wer solche Beobachtungen nicht anstellt, kann auch nie zum Erkennen eines gesetzmäßigen Zusammenhanges im Leben kommen; er kann es ebensowenig, wie derjenige das Gesetz des elastischen Stoßes an zwei Billardkugeln kennenlernen kann, der diesen Stoß nicht beobachten wird.

            Beobachtung des Lebens kann uns in der Tat zu der Anschauung eines gesetzmäßigen Zusammenhanges führen. Greifen wir dazu gleich einen bestimmten Zusammenhang heraus.
            """,
            metadata: GAPassageMetadata(pageNumbers: [15], pageMarkerSource: "pdf_page_anchor")
        )
        var legacyKarma = karma
        legacyKarma.passages = [legacyKarmaPassage]
        try expect(!karma.isCompleteContent(legacyKarma.passages) && !legacyKarma.isReadable,
                   "a saved legacy GA 120 one-passage excerpt is rejected against the full eleven-section catalog")
        try expect(!karma.isCompleteContent(Array(fullKarma.dropLast())) && !karma.isCompleteContent(fullKarma + [legacyKarmaPassage]),
                   "local content must contain exactly the advertised complete book")
        var unknownCount = karma
        unknownCount.catalogPassageCount = nil
        try expect(!unknownCount.isCompleteContent(fullKarma), "local content without a known full-book count is rejected")
        unknownCount.catalogPassageCount = 0
        try expect(!unknownCount.isCompleteContent(fullKarma), "a nonpositive full-book count cannot authorize local text")
        var malformedKarma = fullKarma
        malformedKarma[0].text = " \n\t "
        try expect(!karma.isCompleteContent(malformedKarma), "local books with blank text are incomplete")
        malformedKarma = fullKarma
        malformedKarma[0].id = " "
        try expect(!karma.isCompleteContent(malformedKarma), "local books with blank section IDs are incomplete")
        malformedKarma = fullKarma
        malformedKarma[1].id = malformedKarma[0].id
        try expect(!karma.isCompleteContent(malformedKarma), "local books with duplicate section IDs are incomplete")
        for completeness in [GAContentCompleteness.partial, .unavailable] {
            var flaggedKarma = downloadedKarma
            flaggedKarma.contentCompleteness = completeness
            try expect(!flaggedKarma.isCompleteContent(fullKarma) && !flaggedKarma.isReadable && !flaggedKarma.isDownloadable,
                       "an explicit \(completeness.rawValue) flag rejects local text and download paths despite a matching section count")
        }
        var formerSeed = downloadedKarma
        formerSeed.publicationState = .publishedSeed
        try expect(!formerSeed.isCompleteContent(fullKarma) && !formerSeed.isReadable && !formerSeed.isDownloadable,
                   "a former published seed is never readable or downloadable even when counts and completeness flags agree")

        let restored = try JSONDecoder().decode([GAVolume].self, from: JSONEncoder().encode(hydrated))
        try expect(restored == hydrated, "all catalog metadata and five complete hydrated books survive Codable persistence")
        let metadata = hydrated.map { volume in var item = volume; item.passages = []; return item }
        let restoredMetadata = try JSONDecoder().decode([GAVolume].self, from: JSONEncoder().encode(metadata))
        try expect(restoredMetadata == metadata && restoredMetadata.filter(\.isDownloadable).count == 324,
                   "small catalog cache retains download paths, availability and advertised counts")

        var sourcePageSeen = false
        var unicodeSeen = false
        for work in downloadable {
            guard let path = work.contentPath else { throw CheckFailure(description: "missing download path") }
            try expect(path == "/api/catalog/\(work.id)/content", "download path identifies \(work.id)")
            let contentData = try Data(contentsOf: contentRoot.appendingPathComponent("\(work.id).json"))
            let passages = try CatalogClient.decodePassages(from: contentData, for: work.id, expectedPassageCount: work.catalogPassageCount)
            try expect(passages.count == work.catalogPassageCount, "advertised section count matches content for \(work.id)")
            try expect(work.isCompleteContent(passages), "actual downloaded text is complete for \(work.id)")
            try expect(work.catalogContentFingerprint == GAVolume.contentFingerprint(for: passages,
                includesReaderMetadata: work.catalogIncludesReaderMetadata),
                "catalog fingerprints identify each actual complete download for \(work.id)")
            let roundTrip = try JSONDecoder().decode([GAPassage].self, from: JSONEncoder().encode(passages))
            try expect(roundTrip == passages, "download cache retains text, source pages and annotations for \(work.id)")
            sourcePageSeen = sourcePageSeen || passages.contains { !$0.metadata.pageNumbers.isEmpty }
            unicodeSeen = unicodeSeen || passages.contains { $0.text.contains("ü") || $0.text.contains("ß") }
        }
        try expect(sourcePageSeen && unicodeSeen, "actual downloaded bodies preserve source-page metadata and German Unicode")

        let endpoint = "https://fototausch.eu/ga-reader"
        for base in [endpoint, endpoint + "/"] {
            for path in ["/api/catalog", "api/catalog"] {
                try expect(CatalogClient.contentURL(path: path, baseURL: URL(string: base)!)?.absoluteString == endpoint + "/api/catalog",
                           "API path retains the service prefix and normalizes boundary slashes")
            }
            try expect(CatalogClient.contentURL(path: "/api/catalog/ga-333/content?q=%C3%A4#reader", baseURL: URL(string: base)!)?.absoluteString == endpoint + "/api/catalog/ga-333/content?q=%C3%A4#reader",
                       "download URL preserves its encoded query and fragment")
            try expect(CatalogClient.contentURL(path: "https://example.com/body.json", baseURL: URL(string: base)!)?.absoluteString == "https://example.com/body.json",
                       "absolute download URL remains absolute")
        }
        try expect(CatalogClient.contentURL(path: "/api/catalog", baseURL: URL(string: "http://127.0.0.1:4000")!)?.absoluteString == "http://127.0.0.1:4000/api/catalog",
                   "local development still resolves at the root")

        let validPassage: [String: Any] = ["id": "unicode", "title": "Über Erkenntnis", "source_label": "Fixture", "text": "📖 Äußere Beobachtung, Größe und überlieferter Text."]
        func payload(workID: String?, passages: [[String: Any]], passageCount: Int? = nil,
                     completeness: GAContentCompleteness? = nil, completenessAlias: GAContentCompleteness? = nil,
                     publicationState: GAPublicationState? = nil, state: GAPublicationState? = nil) throws -> Data {
            var object: [String: Any] = ["passages": passages]
            if let workID { object["work_id"] = workID }
            if let passageCount { object["passage_count"] = passageCount }
            if let completeness { object["content_completeness"] = completeness.rawValue }
            if let completenessAlias { object["completeness"] = completenessAlias.rawValue }
            if let publicationState { object["publication_state"] = publicationState.rawValue }
            if let state { object["state"] = state.rawValue }
            return try JSONSerialization.data(withJSONObject: object)
        }
        let validData = try payload(workID: "ga-333", passages: [validPassage], passageCount: 1, completeness: .complete)
        try expect(try CatalogClient.decodePassages(from: validData, for: "ga-333", expectedPassageCount: 1).first?.text == validPassage["text"] as? String,
                   "valid download preserves composed Unicode exactly")
        let legacyData = try payload(workID: nil, passages: [validPassage])
        try expect(try CatalogClient.decodePassages(from: legacyData, for: "ga-333", expectedPassageCount: 1).count == 1,
                   "legacy content without a work identifier remains readable when its complete count agrees")
        try reject(validData, for: "ga-333", expectedPassageCount: 2, reason: "a partial download is rejected against the catalog count")
        try reject(validData, for: "ga-333", expectedPassageCount: 0, reason: "a nonpositive expected book count is rejected")
        try reject(try payload(workID: "ga-333", passages: [validPassage], passageCount: 2), for: "ga-333", expectedPassageCount: 1,
                   reason: "declared payload section count must match actual content")
        try reject(try payload(workID: "ga-333", passages: [validPassage], passageCount: 2), for: "ga-333",
                   reason: "declared payload section count is checked even without an expected catalog count")
        for completeness in [GAContentCompleteness.partial, .unavailable] {
            let flagged = try payload(workID: "ga-333", passages: [validPassage], passageCount: 1, completeness: completeness)
            try reject(flagged, for: "ga-333", expectedPassageCount: 1,
                       reason: "an explicit \(completeness.rawValue) payload is rejected despite agreeing section counts")
            try reject(flagged, for: "ga-333",
                       reason: "an explicit \(completeness.rawValue) payload is rejected without a catalog count")
            try reject(try payload(workID: "ga-333", passages: [validPassage], passageCount: 1, completenessAlias: completeness),
                       for: "ga-333", expectedPassageCount: 1,
                       reason: "a \(completeness.rawValue) completeness alias is rejected")
            try reject(try payload(workID: "ga-333", passages: [validPassage], passageCount: 1,
                                   completeness: .complete, completenessAlias: completeness),
                       for: "ga-333", expectedPassageCount: 1,
                       reason: "a complete flag cannot override a \(completeness.rawValue) completeness alias")
            try reject(try payload(workID: "ga-333", passages: [validPassage], passageCount: 1,
                                   completeness: completeness, completenessAlias: .complete),
                       for: "ga-333", expectedPassageCount: 1,
                       reason: "a complete alias cannot override a \(completeness.rawValue) primary completeness flag")
        }
        let validAlias = try payload(workID: "ga-333", passages: [validPassage], passageCount: 1,
                                     completeness: .complete, completenessAlias: .complete)
        try expect(try CatalogClient.decodePassages(from: validAlias, for: "ga-333", expectedPassageCount: 1).count == 1,
                   "agreeing complete payload flags preserve readable content")
        try reject(try payload(workID: "ga-333", passages: [validPassage], passageCount: 1,
                               completeness: .complete, publicationState: .publishedSeed),
                   for: "ga-333", expectedPassageCount: 1,
                   reason: "a published_seed publication_state cannot authorize a complete download")
        try reject(try payload(workID: "ga-333", passages: [validPassage], passageCount: 1,
                               completeness: .complete, state: .publishedSeed),
                   for: "ga-333", expectedPassageCount: 1,
                   reason: "a published_seed state cannot authorize a complete download")
        let legacyKarmaData = try JSONSerialization.data(withJSONObject: [
            "work_id": karma.id, "passage_count": 1,
            "passages": [["id": legacyKarmaPassage.id, "title": legacyKarmaPassage.title,
                          "source_label": legacyKarmaPassage.sourceLabel, "text": legacyKarmaPassage.text]]
        ])
        try reject(legacyKarmaData, for: karma.id, expectedPassageCount: karma.catalogPassageCount,
                   reason: "the legacy GA 120 seed cannot be downloaded as the complete book")
        try reject(try payload(workID: "ga-004", passages: [validPassage]), for: "ga-333", reason: "wrong work cannot be cached under the requested ID")
        try reject(try payload(workID: "ga-333", passages: []), for: "ga-333", reason: "empty download is rejected")
        var blank = validPassage
        blank["text"] = " \n\t "
        try reject(try payload(workID: "ga-333", passages: [blank]), for: "ga-333", reason: "whitespace-only passage is rejected")
        try reject(try payload(workID: "ga-333", passages: [validPassage, blank]), for: "ga-333", reason: "partly empty payload is rejected")
        try reject(try payload(workID: "ga-333", passages: [validPassage, validPassage]), for: "ga-333", reason: "duplicate passage IDs are rejected")
        var unnamed = validPassage
        unnamed["id"] = " "
        try reject(try payload(workID: "ga-333", passages: [unnamed]), for: "ga-333", reason: "blank passage ID is rejected")
        try reject(Data("{broken".utf8), for: "ga-333", reason: "malformed JSON is rejected")
    }

    private static func editionChecks(base: GAVolume, passages: [GAPassage], data: Data) throws {
        let received = try CatalogClient.decodeDownloadEdition(from: data, for: base.id,
            expectedPassageCount: passages.count)
        try expect(!received.isLegacy && received.passageCount == passages.count && received.contentRevision?.count == 64,
                   "a download records its exact complete edition and raw reader checksum")
        _ = try CatalogClient.decodeDownloadEdition(from: data, for: base.id,
            expectedPassageCount: passages.count, expectedRevision: received.contentRevision)
        do {
            _ = try CatalogClient.decodeDownloadEdition(from: data, for: base.id,
                expectedPassageCount: passages.count, expectedRevision: String(repeating: "0", count: 64))
            throw CheckFailure(description: "a stale server bundle must be rejected before a cache replacement")
        } catch CatalogClientError.staleRevision { }

        let restored = try LocalContentStore.decodeEdition(from: JSONEncoder().encode(received), for: base.id)
        try expect(!restored.isLegacy && restored.contentRevision == received.contentRevision && restored.passages == passages,
                   "the edition cache preserves its full count, revision and reader metadata")
        do {
            _ = try LocalContentStore.decodeEdition(from: JSONEncoder().encode(received), for: "ga-999")
            throw CheckFailure(description: "an edition envelope for another book cannot be loaded")
        } catch CatalogClientError.unexpectedWork { }
        var badEnvelope = try JSONSerialization.jsonObject(with: JSONEncoder().encode(received)) as! [String: Any]
        badEnvelope["passage_count"] = passages.count + 1
        do {
            _ = try LocalContentStore.decodeEdition(from: JSONSerialization.data(withJSONObject: badEnvelope), for: base.id)
            throw CheckFailure(description: "a truncated edition envelope cannot authorize a complete offline book")
        } catch CatalogClientError.unexpectedPassageCount { }

        let legacy = try LocalContentStore.decodeEdition(from: JSONEncoder().encode(passages), for: base.id)
        try expect(legacy.isLegacy && legacy.contentRevision == nil && base.isCompleteContent(legacy.passages),
                   "a legacy full download remains usable with its independently advertised complete count")
        let excerpt = try LocalContentStore.decodeEdition(from: JSONEncoder().encode(Array(passages.prefix(1))), for: base.id)
        try expect(excerpt.isLegacy && !base.isCompleteContent(excerpt.passages),
                   "a legacy array's inferred count cannot authorize an old one-section excerpt")

        var saved = base
        saved.passages = passages
        saved.downloadedPassageCount = passages.count
        saved.downloadedContentRevision = received.contentRevision
        saved.catalogContentRevision = received.contentRevision
        try expect(saved.isReadable && saved.matchesCurrentEdition(passages) && !saved.hasContentUpdate,
                   "a downloaded current edition is readable without an update badge")
        saved.catalogContentRevision = "new-metadata-only-edition"
        try expect(saved.isReadable && saved.hasContentUpdate,
                   "a metadata-only server correction offers an update while preserving offline reading")
        saved.catalogPassageCount = passages.count + 1
        try expect(saved.isReadable && saved.hasContentUpdate && !saved.isCompleteContent(passages),
                   "a newer section count does not invalidate the previously complete offline edition")
        saved.catalogPassageCount = passages.count
        saved.downloadedContentRevision = nil
        try expect(saved.isReadable && saved.hasContentUpdate,
                   "a legacy downloaded edition gets one verifiable upgrade when server revisions become available")

        saved.catalogContentRevision = nil
        saved.catalogIncludesReaderMetadata = true
        saved.catalogContentFingerprint = GAVolume.contentFingerprint(for: passages)
        try expect(saved.matchesCurrentEdition(passages) && !saved.hasContentUpdate,
                   "legacy text fingerprints identify an unchanged complete edition")
        var changedText = passages
        changedText[0].text += " Korrigierter Text."
        saved.passages = changedText
        try expect(saved.isReadable && saved.hasContentUpdate,
                   "a same-count text correction is detected without losing offline readability")
        var changedStructure = passages
        changedStructure[0].metadata.groupTitle = "Korrigierte Gliederung"
        saved.passages = changedStructure
        try expect(saved.isReadable && saved.hasContentUpdate,
                   "reader structure participates in fingerprints when catalog metadata is available")
        try expect(!saved.matchesCurrentEdition(Array(passages.reversed())),
                   "changed passage ordering cannot impersonate the current edition")
        saved.passages = []
        let cachedCatalog = try JSONDecoder().decode(GAVolume.self, from: JSONEncoder().encode(saved))
        try expect(cachedCatalog.catalogContentFingerprint == saved.catalogContentFingerprint &&
                   cachedCatalog.downloadedPassageCount == passages.count,
                   "catalog cache metadata retains current fingerprint and downloaded complete count")

        var datedCatalog = try JSONSerialization.jsonObject(with: JSONEncoder().encode(saved)) as! [String: Any]
        for date in ["2026-10-09T02:02:38+00:00", "2026-10-09T02:02:38.123Z", "2026-10-09T04:02:38+02:00"] {
            datedCatalog["content_updated_at"] = date
            let volume = try JSONDecoder().decode(GAVolume.self, from: JSONSerialization.data(withJSONObject: datedCatalog))
            try expect(volume.contentUpdatedAt != nil, "edition dates parse ISO timestamps with timezone and optional fractions")
            let again = try JSONDecoder().decode(GAVolume.self, from: JSONEncoder().encode(volume))
            try expect(again.contentUpdatedAt == volume.contentUpdatedAt, "edition dates survive catalog cache persistence")
        }

        var packaged = saved
        packaged.catalogContentRevision = "packaged-current"
        packaged.contentUpdatedAt = Date(timeIntervalSince1970: 1_000)
        var server = packaged
        server.catalogContentRevision = "server-old"
        server.contentUpdatedAt = Date(timeIntervalSince1970: 999)
        try expect(server.preferringNewerEdition(over: packaged) == packaged,
                   "an older server catalogue cannot roll back the packaged edition")
        server.contentUpdatedAt = nil
        try expect(server.preferringNewerEdition(over: packaged) == packaged,
                   "an undated legacy server cannot replace a dated corrected edition")
        server.contentUpdatedAt = Date(timeIntervalSince1970: 1_001)
        server.catalogContentRevision = "server-new"
        try expect(server.preferringNewerEdition(over: packaged) == server,
                   "a newer server edition becomes the catalogue's available update")
        server.contentUpdatedAt = packaged.contentUpdatedAt
        try expect(server.preferringNewerEdition(over: packaged) == server,
                   "equal edition dates retain the preferred incoming catalogue")
        server.contentUpdatedAt = nil
        packaged.contentUpdatedAt = nil
        try expect(server.preferringNewerEdition(over: packaged) == server,
                   "legacy catalogues without edition dates retain the existing merge preference")
    }

    private static func reject(_ data: Data, for id: String, expectedPassageCount: Int? = nil, reason: String) throws {
        do {
            _ = try CatalogClient.decodePassages(from: data, for: id, expectedPassageCount: expectedPassageCount)
        } catch {
            return
        }
        throw CheckFailure(description: reason)
    }

    private static func expect(_ condition: Bool, _ message: String) throws {
        if !condition { throw CheckFailure(description: message) }
    }
}
'''


def main():
    catalog = ROOT / "apple/GA/BundledCatalog/catalog.json"
    server_catalog = ROOT / "server/priv/library/catalog.json"
    if not catalog.is_file() or not server_catalog.is_file():
        raise SystemExit("Import the complete library before running download checks.")
    catalog_payload = json.loads(catalog.read_text(encoding="utf-8"))
    imported = json.loads(server_catalog.read_text(encoding="utf-8"))
    def availability(payload):
        return {work["id"]: (work.get("content_path"), work.get("catalog_passage_count")
                            if work.get("catalog_passage_count") is not None else len(work.get("passages", [])),
                            work.get("content_completeness"))
                for work in payload["works"]}
    # Public exports may refine curated titles/types/priorities, while identity
    # and actual downloadable contents must agree with the independent import.
    if availability(catalog_payload) != availability(imported):
        raise SystemExit("Apple catalog identities, paths, section counts or completeness differ from the server import.")
    with tempfile.TemporaryDirectory(prefix="ga-download-library-check-") as scratch:
        scratch = Path(scratch)
        bundle = scratch / "LibraryFixtures.bundle"
        bundle.mkdir()
        (bundle / "Info.plist").write_bytes(plistlib.dumps({
            "CFBundleIdentifier": "com.jonathankutscher.ga.download-checks",
            "CFBundleName": "LibraryFixtures",
            "CFBundlePackageType": "BNDL",
        }))
        shutil.copytree(ROOT / "apple/GA/BundledCatalog", bundle / "BundledCatalog")
        shutil.copytree(ROOT / "apple/GA/BundledContent", bundle / "BundledContent")
        content_files = sorted((bundle / "BundledContent").glob("*.json"))
        expected_offline_ids = {"ga-003", "ga-004", "ga-009", "ga-010", "ga-013"}
        if {path.stem for path in content_files} != expected_offline_ids:
            raise SystemExit("The installation should contain exactly the five complete offline core books.")
        if sum(len(json.loads(path.read_text(encoding="utf-8"))["passages"]) for path in content_files) != 77:
            raise SystemExit("The five complete offline books should contain all 77 sections.")
        content = scratch / "ContentFixtures"
        content.mkdir()
        for work in catalog_payload["works"]:
            if not work.get("content_path"):
                continue
            work_id = work["id"]
            source = ROOT / "server/priv/content" / f"{work_id}.json"
            compressed = source.with_suffix(".json.gz")
            target = content / source.name
            # A full imported bundle supersedes an older uncompressed seed.
            if compressed.is_file():
                with gzip.open(compressed, "rb") as body:
                    target.write_bytes(body.read())
            else:
                shutil.copyfile(source, target)
        source = scratch / "DownloadLibraryChecks.swift"
        source.write_text(HARNESS, encoding="utf-8")
        executable = scratch / "checks"
        subprocess.run([
            "swiftc", "-swift-version", "6", "-parse-as-library",
            str(ROOT / "apple/GA/Models.swift"), str(ROOT / "apple/GA/SeedLibrary.swift"),
            str(source), "-o", str(executable),
        ], check=True)
        environment = os.environ.copy()
        environment.pop("GA_FRONTEND", None)
        environment.pop("GA_SERVER_BASE_URL", None)
        subprocess.run([str(executable), str(bundle), str(content)], env=environment, check=True)
        live = "https://fototausch.eu/ga-reader/api/catalog"
        local = "http://127.0.0.1:4000/api/catalog"
        for overrides, expected in [
            ({}, live),
            ({"GA_FRONTEND": "developer"}, local),
            ({"GA_SERVER_BASE_URL": "http://127.0.0.1:4000"}, local),
            ({"GA_FRONTEND": "developer", "GA_SERVER_BASE_URL": "https://fototausch.eu/ga-reader"}, live),
        ]:
            subprocess.run([str(executable), "--default-url", expected],
                           env={**environment, **overrides}, check=True)


if __name__ == "__main__":
    main()
