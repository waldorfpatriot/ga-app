import Foundation

/// Resolves a complete book independently of the reader's potentially stale snapshot.
enum EPUBExportContent {
    struct Sources: Sendable {
        var loadLocal: @Sendable (GAVolume.ID) throws -> LocalContentStore.Edition?
        var loadBundled: @Sendable (GAVolume.ID) throws -> LocalContentStore.Edition?
        var download: @Sendable (String, GAVolume.ID, String?) async throws -> LocalContentStore.Edition
        var save: @Sendable ([GAPassage], GAVolume.ID, String?) throws -> Void

        static let live = Sources(
            loadLocal: { try LocalContentStore.loadEdition(for: $0) },
            loadBundled: { try bundledEdition(for: $0) },
            download: { try await CatalogClient.downloadEdition(path: $0, for: $1, expectedRevision: $2) },
            save: { try LocalContentStore.save(passages: $0, for: $1, contentRevision: $2) }
        )
    }

    static func prepare(volume: GAVolume, sources: Sources = .live) async throws -> GAVolume {
        try Task.checkCancellation()
        // A reader may hold an excerpt even after the complete book was downloaded.
        // Never replace a larger snapshot with a smaller cached copy either.
        let expectedCount = max(volume.downloadedPassageCount ?? volume.catalogPassageCount ?? 0,
                                volume.passages.count)
        let isUnverifiedSeed = volume.publicationState == .publishedSeed
            && (volume.catalogPassageCount ?? 0) <= 0

        if !isUnverifiedSeed, isComplete(volume.passages, expectedCount: expectedCount) {
            return volume
        }

        for load in [sources.loadLocal, sources.loadBundled] {
            if let edition = try? load(volume.id),
               edition.workID == volume.id,
               edition.passageCount == edition.passages.count,
               isComplete(edition.passages,
                          expectedCount: edition.isLegacy ? expectedCount : edition.passageCount) {
                return preparedVolume(volume, edition: edition)
            }
        }

        guard let path = volume.contentPath?.trimmingCharacters(in: .whitespacesAndNewlines),
              !path.isEmpty else {
            throw EPUBExportContentError.unavailable
        }

        let edition: LocalContentStore.Edition
        do {
            edition = try await sources.download(path, volume.id, volume.catalogContentRevision)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            try Task.checkCancellation()
            throw EPUBExportContentError.downloadFailed
        }
        try Task.checkCancellation()
        let passages = edition.passages

        guard !passages.isEmpty else {
            throw EPUBExportContentError.unavailable
        }
        guard passages.count >= expectedCount else {
            throw EPUBExportContentError.incomplete(expected: expectedCount, actual: passages.count)
        }
        guard passages.allSatisfy({ !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) else {
            throw EPUBExportContentError.emptyChapter
        }
        guard hasValidIdentifiers(passages) else {
            throw EPUBExportContentError.invalidPassageIdentifiers
        }

        // A cache write failure must not prevent sharing a successfully loaded book.
        try? sources.save(passages, volume.id, edition.contentRevision)
        return preparedVolume(volume, edition: edition)
    }

    private static func isComplete(_ passages: [GAPassage], expectedCount: Int) -> Bool {
        !passages.isEmpty && passages.count >= expectedCount
            && passages.allSatisfy { !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            && hasValidIdentifiers(passages)
    }

    private static func hasValidIdentifiers(_ passages: [GAPassage]) -> Bool {
        passages.allSatisfy { !$0.id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            && Set(passages.map(\.id)).count == passages.count
    }

    private static func bundledEdition(for volumeID: GAVolume.ID) throws -> LocalContentStore.Edition? {
        guard let passages = try BundledContentStore.loadPassages(for: volumeID) else { return nil }
        let catalog = (try? BundledCatalogStore.loadVolumes())?.first { $0.id == volumeID }
        let matchesCatalog = catalog?.catalogContentFingerprint == GAVolume.contentFingerprint(
            for: passages, includesReaderMetadata: catalog?.catalogIncludesReaderMetadata ?? false)
        return LocalContentStore.Edition(workID: volumeID, passageCount: passages.count,
            contentRevision: matchesCatalog ? catalog?.catalogContentRevision : nil,
            passages: passages, isLegacy: catalog?.isCompleteContent(passages) != true)
    }

    private static func preparedVolume(_ volume: GAVolume, edition: LocalContentStore.Edition) -> GAVolume {
        var prepared = volume
        prepared.passages = edition.passages
        prepared.catalogPassageCount = max(volume.catalogPassageCount ?? 0, edition.passages.count)
        prepared.downloadedPassageCount = edition.passages.count
        prepared.downloadedContentRevision = edition.contentRevision
        return prepared
    }
}

enum EPUBExportContentError: LocalizedError {
    case unavailable
    case downloadFailed
    case incomplete(expected: Int, actual: Int)
    case emptyChapter
    case invalidPassageIdentifiers

    var errorDescription: String? {
        switch self {
        case .unavailable:
            "Für dieses Buch ist noch kein vollständiger Lesetext verfügbar."
        case .downloadFailed:
            "Der vollständige Buchtext konnte nicht geladen werden. Bitte versuche es später erneut."
        case .incomplete(let expected, let actual):
            "Der Buchtext ist unvollständig: Es wurden \(actual) von \(expected) Abschnitten geladen. Bitte versuche es später erneut."
        case .emptyChapter:
            "Der Buchtext enthält einen leeren Abschnitt und kann deshalb noch nicht als EPUB geteilt werden."
        case .invalidPassageIdentifiers:
            "Der Buchtext enthält ungültige oder doppelte Abschnittskennungen. Bitte lade das Buch erneut."
        }
    }
}
