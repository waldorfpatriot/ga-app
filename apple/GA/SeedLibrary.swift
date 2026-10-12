import Foundation

enum SeedLibrary {
    static let volumes: [GAVolume] = [
        GAVolume(
            id: "ga-004",
            gaNumber: "GA 004",
            title: "Die Philosophie der Freiheit",
            subtitle: "Grundzüge einer modernen Weltanschauung",
            languageCode: "de",
            yearLabel: "1894",
            type: .book,
            priority: 1,
            publicationState: .published,
            proofingState: .aiChecked,
            sourceSummary: "Complete normalized public-domain text with auditable source diff.",
            tags: ["freedom", "philosophy", "ethics", "core"],
            passages: [],
            sanityChecks: productionChecks(),
            contentPath: "/api/catalog/ga-004/content"
        ),
        GAVolume(
            id: "ga-010",
            gaNumber: "GA 010",
            title: "Wie erlangt man Erkenntnisse der höheren Welten?",
            subtitle: "Core spiritual-scientific work",
            languageCode: "de",
            yearLabel: "1904-1905",
            type: .book,
            priority: 2,
            publicationState: .published,
            proofingState: .aiChecked,
            sourceSummary: "Complete normalized public-domain text with auditable source diff.",
            tags: ["core", "training", "meditation"],
            passages: [],
            sanityChecks: productionChecks(),
            contentPath: "/api/catalog/ga-010/content"
        ),
        GAVolume(
            id: "ga-013",
            gaNumber: "GA 013",
            title: "Die Geheimwissenschaft im Umriß",
            subtitle: "Large structured book with terminology-heavy passages",
            languageCode: "de",
            yearLabel: "1910",
            type: .book,
            priority: 3,
            publicationState: .published,
            proofingState: .aiChecked,
            sourceSummary: "Complete normalized public-domain text with auditable source diff.",
            tags: ["core", "cosmology", "anthroposophy"],
            passages: [],
            sanityChecks: productionChecks(),
            contentPath: "/api/catalog/ga-013/content"
        ),
        GAVolume(
            id: "ga-009",
            gaNumber: "GA 009",
            title: "Theosophie",
            subtitle: "Einführung in übersinnliche Welterkenntnis und Menschenbestimmung",
            languageCode: "de",
            yearLabel: "1904",
            type: .book,
            priority: 4,
            publicationState: .published,
            proofingState: .aiChecked,
            sourceSummary: "Complete normalized public-domain text with auditable source diff.",
            tags: ["core", "introduction", "anthroposophy"],
            passages: [],
            sanityChecks: productionChecks(),
            contentPath: "/api/catalog/ga-009/content"
        ),
        GAVolume(
            id: "ga-003",
            gaNumber: "GA 003",
            title: "Wahrheit und Wissenschaft",
            subtitle: "Vorspiel zu einer Philosophie der Freiheit",
            languageCode: "de",
            yearLabel: "1892",
            type: .book,
            priority: 5,
            publicationState: .published,
            proofingState: .aiChecked,
            sourceSummary: "Complete normalized public-domain text with auditable source diff.",
            tags: ["philosophy", "knowledge", "freedom"],
            passages: [],
            sanityChecks: [
                GASanityCheck(id: "content", title: "Complete text payload", status: .passed, detail: "Server payload contains 10 passages."),
                GASanityCheck(id: "umlauts", title: "German diacritics", status: .passed, detail: "Candidate text preserves ä, ö, ü and ß."),
                GASanityCheck(id: "editorial-scope", title: "Original text scope", status: .passed, detail: "Source header, table of contents and trailing Word field were excluded."),
                GASanityCheck(id: "proofing", title: "Full-volume proofing", status: .passed, detail: "Automated production checks passed; changes remain auditable.")
            ],
            contentPath: "/api/catalog/ga-003/content"
        ),
        GAVolume(
            id: "ga-120",
            gaNumber: "GA 120",
            title: "Die Offenbarungen des Karma",
            subtitle: "Elf Vorträge, Hamburg, 16.-28. Mai 1910",
            languageCode: "de",
            yearLabel: "1910",
            type: .lectureCycle,
            priority: 6,
            publicationState: .sanityCheck,
            proofingState: .needsAISanityCheck,
            sourceSummary: "Vollständige Arbeitsausgabe der elf Vorträge zum Herunterladen.",
            tags: ["karma", "lectures", "hamburg"],
            passages: [],
            sanityChecks: [],
            contentPath: "/api/catalog/ga-120/content",
            catalogPassageCount: 11,
            contentCompleteness: .complete
        ),
        GAVolume(
            id: "ga-293",
            gaNumber: "GA 293",
            title: "Allgemeine Menschenkunde als Grundlage der Pädagogik",
            subtitle: "Education priority volume for Waldorf-related readers",
            languageCode: "de",
            yearLabel: "1919",
            type: .education,
            priority: 7,
            publicationState: .importQueue,
            proofingState: .sourcePending,
            sourceSummary: "Important/popular education volume. Source import and AI sanity checks are queued.",
            tags: ["education", "waldorf", "pedagogy"],
            passages: [],
            sanityChecks: queuedChecks(source: "Source discovery pending")
        )
    ].sorted { $0.priority < $1.priority }

    static func volume(id: String?) -> GAVolume? {
        guard let id else { return volumes.first }
        return volumes.first { $0.id == id }
    }

    static let readerVolumes = readerVolumes(in: .main)

    static func readerVolumes(in bundle: Bundle) -> [GAVolume] {
        let catalog = (try? BundledCatalogStore.loadVolumes(bundle: bundle)) ?? []
        let curated = volumes.filter { $0.isReaderAvailable && $0.id != "ga-120" }
        let curatedIDs = Set(curated.map(\.id))
        let catalogIDs = Set(catalog.map(\.id))
        let fallback = volumes.filter { $0.isReaderAvailable && !curatedIDs.contains($0.id) && !catalogIDs.contains($0.id) }
        let works = curated + catalog.filter { !curatedIDs.contains($0.id) } + fallback
        return works.map { volume in
            var bundled = volume
            bundled.passages = []
            if let advertised = catalog.first(where: { $0.id == volume.id }) {
                bundled.catalogPassageCount = max(volume.catalogPassageCount ?? 0, advertised.catalogPassageCount ?? 0)
                bundled.contentCompleteness = advertised.contentCompleteness
                bundled.catalogContentFingerprint = advertised.catalogContentFingerprint
                bundled.catalogIncludesReaderMetadata = advertised.catalogIncludesReaderMetadata
                bundled.catalogContentRevision = advertised.catalogContentRevision
                bundled.contentUpdatedAt = advertised.contentUpdatedAt
            }
            if curatedIDs.contains(volume.id), let passages = try? BundledContentStore.loadPassages(for: volume.id, bundle: bundle) {
                if (bundled.catalogPassageCount ?? 0) == 0 { bundled.catalogPassageCount = passages.count }
                if bundled.isCompleteContent(passages) {
                    bundled.passages = passages
                    bundled.downloadedPassageCount = passages.count
                    if bundled.catalogContentFingerprint == GAVolume.contentFingerprint(for: passages,
                        includesReaderMetadata: bundled.catalogIncludesReaderMetadata) {
                        bundled.downloadedContentRevision = bundled.catalogContentRevision
                    }
                }
            }
            return bundled
        }.sorted { $0.priority == $1.priority ? $0.gaSortLabel < $1.gaSortLabel : $0.priority < $1.priority }
    }

    static var developerVolumes: [GAVolume] {
        volumes
    }

    static var defaultVolumeID: GAVolume.ID? {
        defaultReaderVolumeID
    }

    static var defaultReaderVolumeID: GAVolume.ID? {
        readerVolumes.first?.id
    }

    static var defaultDeveloperVolumeID: GAVolume.ID? {
        developerVolumes.first?.id
    }

    private static func queuedChecks(source: String) -> [GASanityCheck] {
        [
            GASanityCheck(id: "source", title: "Source acquisition", status: .queued, detail: source),
            GASanityCheck(id: "scope", title: "Original-text isolation", status: .queued, detail: "Exclude publisher pages, introductions, editorial notes and apparatus."),
            GASanityCheck(id: "ocr", title: "OCR sanity pass", status: .queued, detail: "Compare PDF text, DOC text and page-image OCR before publication.")
        ]
    }

    private static func productionChecks() -> [GASanityCheck] {
        [
            GASanityCheck(id: "source", title: "Source provenance", status: .passed, detail: "Public Domain Mark source retained."),
            GASanityCheck(id: "scope", title: "Original-text isolation", status: .passed, detail: "Non-reader front matter excluded."),
            GASanityCheck(id: "ocr", title: "OCR sanity pass", status: .passed, detail: "Automated production checks passed.")
        ]
    }
}
