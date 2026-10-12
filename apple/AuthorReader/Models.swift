import Foundation
import CryptoKit

private func validUTF16Boundary(_ offset: Int, in text: NSString) -> Bool {
    guard offset >= 0, offset <= text.length else { return false }
    guard offset > 0, offset < text.length else { return true }
    let before = text.character(at: offset - 1)
    let after = text.character(at: offset)
    return !(0xD800...0xDBFF).contains(before) || !(0xDC00...0xDFFF).contains(after)
}

enum GAWorkType: String, CaseIterable, Codable, Hashable, Identifiable, Sendable {
    case book = "book"
    case lectureCycle = "lecture_cycle"
    case lectures = "lectures"
    case essays = "essays"
    case education = "education"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .book: "Book"
        case .lectureCycle: "Lecture cycle"
        case .lectures: "Lectures"
        case .essays: "Essays"
        case .education: "Education"
        }
    }
}

enum GAPublicationState: String, Codable, Hashable, Sendable {
    case published = "published"
    case publishedSeed = "published_seed"
    case sanityCheck = "sanity_check"
    case importQueue = "import_queue"

    var shortLabel: String {
        switch self {
        case .published: "Published"
        case .publishedSeed: "Seed excerpt"
        case .sanityCheck: "AI sanity check"
        case .importQueue: "Import queue"
        }
    }
}

enum GAProofingState: String, Codable, Hashable, Sendable {
    case humanProofed = "human_proofed"
    case aiChecked = "ai_checked"
    case needsAISanityCheck = "needs_ai_sanity_check"
    case sourcePending = "source_pending"

    var displayName: String {
        switch self {
        case .humanProofed: "Human proofed"
        case .aiChecked: "AI checked"
        case .needsAISanityCheck: "Needs AI sanity check"
        case .sourcePending: "Source pending"
        }
    }
}

enum GASanityCheckStatus: String, Codable, Hashable, Sendable {
    case passed = "passed"
    case warning = "warning"
    case queued = "queued"

    var displayName: String {
        switch self {
        case .passed: "Passed"
        case .warning: "Warning"
        case .queued: "Queued"
        }
    }
}

struct GASanityCheck: Identifiable, Codable, Hashable, Sendable {
    var id: String
    var title: String
    var status: GASanityCheckStatus
    var detail: String
}

struct GAPassage: Identifiable, Codable, Hashable, Sendable {
    var id: String
    var title: String
    var gaPage: String?
    var sourceLabel: String
    var sourceText: String?
    var text: String
    var metadata: GAPassageMetadata

    init(
        id: String,
        title: String,
        gaPage: String?,
        sourceLabel: String,
        sourceText: String? = nil,
        text: String,
        metadata: GAPassageMetadata = .empty
    ) {
        self.id = id
        self.title = title
        self.gaPage = gaPage
        self.sourceLabel = sourceLabel
        self.sourceText = sourceText
        self.text = text
        self.metadata = metadata
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        title = try container.decode(String.self, forKey: .title)
        gaPage = try container.decodeIfPresent(String.self, forKey: .gaPage)
        sourceLabel = try container.decode(String.self, forKey: .sourceLabel)
        sourceText = try container.decodeIfPresent(String.self, forKey: .sourceText)
        text = try container.decode(String.self, forKey: .text)
        metadata = try container.decodeIfPresent(GAPassageMetadata.self, forKey: .metadata) ?? .empty
    }

    private enum CodingKeys: String, CodingKey {
        case id
        case title
        case gaPage = "ga_page"
        case sourceLabel = "source_label"
        case sourceText = "source_text"
        case text
        case metadata
    }
}

struct GAPassageMetadata: Codable, Hashable, Sendable {
    static let empty = GAPassageMetadata()

    var pageNumbers: [Int]
    var pageMarkerSource: String?
    var annotations: [GAAnnotation]
    var readingBlocks: [GAReadingBlock]
    var readingSections: [GAReadingSection]
    var groupTitle: String?
    var pageAnchors: [GAPageAnchor]

    init(
        pageNumbers: [Int] = [],
        pageMarkerSource: String? = nil,
        annotations: [GAAnnotation] = [],
        readingBlocks: [GAReadingBlock] = [],
        groupTitle: String? = nil,
        pageAnchors: [GAPageAnchor] = [],
        readingSections: [GAReadingSection] = []
    ) {
        self.pageNumbers = pageNumbers
        self.pageMarkerSource = pageMarkerSource
        self.annotations = annotations
        self.readingBlocks = readingBlocks
        self.readingSections = readingSections
        self.groupTitle = groupTitle
        self.pageAnchors = pageAnchors
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        pageNumbers = try container.decodeIfPresent([Int].self, forKey: .pageNumbers) ?? []
        pageMarkerSource = try container.decodeIfPresent(String.self, forKey: .pageMarkerSource)
        annotations = try container.decodeIfPresent([GAAnnotation].self, forKey: .annotations) ?? []
        // Structure is optional: an older or malformed edition remains readable.
        readingBlocks = (try? container.decodeIfPresent([GAReadingBlock].self, forKey: .readingBlocks)) ?? []
        readingSections = (try? container.decodeIfPresent([GAReadingSection].self, forKey: .readingSections)) ?? []
        groupTitle = try? container.decodeIfPresent(String.self, forKey: .groupTitle)
        pageAnchors = (try? container.decodeIfPresent([GAPageAnchor].self, forKey: .pageAnchors)) ?? []
    }

    /// Ranges use UTF-16, matching native selections and browser Range offsets.
    /// Reject the whole layout when ranges overlap, split Unicode, or omit text.
    func validReadingBlocks(in text: String) -> [GAReadingBlock] {
        guard !readingBlocks.isEmpty else { return [] }
        let body = text as NSString
        var end = 0
        for block in readingBlocks {
            guard block.startOffset >= end, block.endOffset > block.startOffset,
                  block.endOffset <= body.length,
                  validUTF16Boundary(block.startOffset, in: body), validUTF16Boundary(block.endOffset, in: body),
                  Range(block.range, in: text) != nil,
                  block.level == nil || (1...6).contains(block.level!),
                  body.substring(with: NSRange(location: end, length: block.startOffset - end))
                    .trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return [] }
            end = block.endOffset
        }
        guard body.substring(from: end).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return [] }
        return readingBlocks
    }

    func validPageAnchors(in text: String) -> [GAPageAnchor] {
        let body = text as NSString
        var previous = 0
        for anchor in pageAnchors {
            guard anchor.page > 0, anchor.startOffset >= previous,
                  validUTF16Boundary(anchor.startOffset, in: body) else { return [] }
            previous = anchor.startOffset
        }
        return pageAnchors
    }

    /// Work boundaries refine a passage without replacing its text or its ID.
    /// Labels must come from the passage title or an existing first source line.
    func validReadingSections(in text: String, passageTitle: String? = nil) -> [GAReadingSection] {
        guard !readingSections.isEmpty else { return [] }
        let blocks = validReadingBlocks(in: text)
        guard !blocks.isEmpty else { return [] }
        let body = text as NSString
        let ends = Set(blocks.map(\.endOffset))
        var ids = Set<String>()
        var end = 0
        for (index, section) in readingSections.enumerated() {
            guard !section.id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  !section.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  ids.insert(section.id).inserted,
                  section.startOffset >= end, section.endOffset > section.startOffset,
                  section.endOffset <= body.length,
                  validUTF16Boundary(section.startOffset, in: body), validUTF16Boundary(section.endOffset, in: body),
                  ends.contains(section.endOffset),
                  let first = blocks.first(where: { $0.startOffset == section.startOffset }),
                  body.substring(with: NSRange(location: end, length: section.startOffset - end))
                    .trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return [] }
            switch section.labelKind {
            case .sourceTitle:
                let isPassageTitle = index == 0 && section.title == passageTitle
                guard isPassageTitle || (first.kind == .heading && body.substring(with: first.range) == section.title) else { return [] }
            case .incipit:
                guard first.kind == .verse,
                      body.substring(with: first.range).components(separatedBy: "\n").first == section.title else { return [] }
            }
            end = section.endOffset
        }
        guard body.substring(from: end).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return [] }
        return readingSections
    }

    var pageNumberLabel: String? {
        guard !pageNumbers.isEmpty else { return nil }

        let ranges = collapsedPageRanges(from: pageNumbers)
        return "S. " + ranges.joined(separator: ", ")
    }

    private func collapsedPageRanges(from pageNumbers: [Int]) -> [String] {
        let sortedPages = Array(Set(pageNumbers)).sorted()
        guard let firstPage = sortedPages.first else { return [] }

        var ranges: [String] = []
        var rangeStart = firstPage
        var rangeEnd = firstPage

        for page in sortedPages.dropFirst() {
            if page == rangeEnd + 1 {
                rangeEnd = page
            } else {
                appendRange(to: &ranges, start: rangeStart, end: rangeEnd)
                rangeStart = page
                rangeEnd = page
            }
        }

        appendRange(to: &ranges, start: rangeStart, end: rangeEnd)
        return ranges
    }

    private func appendRange(to ranges: inout [String], start: Int, end: Int) {
        if start == end {
            ranges.append("\(start)")
        } else {
            ranges.append("\(start)-\(end)")
        }
    }

    private enum CodingKeys: String, CodingKey {
        case pageNumbers = "page_numbers"
        case pageMarkerSource = "page_marker_source"
        case annotations
        case readingBlocks = "reading_blocks"
        case readingSections = "reading_sections"
        case groupTitle = "group_title"
        case pageAnchors = "page_anchors"
    }
}

struct GAPageAnchor: Codable, Hashable, Sendable {
    var page: Int
    var startOffset: Int
    var source: String
    var confidence: String? = nil
    var sourceSection: Int? = nil

    private enum CodingKeys: String, CodingKey {
        case page, source, confidence
        case startOffset = "start_offset"
        case sourceSection = "source_section"
    }
}

struct GAReadingBlock: Codable, Hashable, Sendable {
    enum Kind: String, Codable, Sendable { case heading, verse, prose, attribution, note }
    var kind: Kind
    var startOffset: Int
    var endOffset: Int
    var level: Int? = nil
    var poemStart: Bool? = nil
    var range: NSRange { NSRange(location: startOffset, length: endOffset - startOffset) }

    private enum CodingKeys: String, CodingKey {
        case kind, level
        case poemStart = "poem_start"
        case startOffset = "start_offset"
        case endOffset = "end_offset"
    }
}

struct GAReadingSection: Identifiable, Codable, Hashable, Sendable {
    enum LabelKind: String, Codable, Sendable {
        case sourceTitle = "source_title"
        case incipit
    }
    var id: String
    var title: String
    var labelKind: LabelKind
    var startOffset: Int
    var endOffset: Int
    var range: NSRange { NSRange(location: startOffset, length: endOffset - startOffset) }

    private enum CodingKeys: String, CodingKey {
        case id, title
        case labelKind = "label_kind"
        case startOffset = "start_offset"
        case endOffset = "end_offset"
    }
}

struct GAContentsUnit: Identifiable, Hashable, Sendable {
    var id: String
    var title: String
    var labelKind: GAReadingSection.LabelKind
    var startOffset: Int
    var endOffset: Int
    var headings: [GAContentsHeading]
}

/// Reader-facing outline labels leave the source text and jump offsets intact.
struct GAContentsHeading: Identifiable, Hashable, Sendable {
    var id: Int
    var title: String
    var subtitle: String?
    var startOffset: Int
    var level: Int
    var isSeason: Bool
}

extension GAPassage {
    func contentsUnit(at offset: Int) -> GAContentsUnit? {
        let units = contentsUnits
        return units.last(where: { $0.startOffset <= max(0, offset) }) ?? units.first
    }

    func pageNumberLabel(for unit: GAContentsUnit) -> String? {
        let anchors = metadata.validPageAnchors(in: text)
        var pages = anchors.filter { $0.startOffset >= unit.startOffset && $0.startOffset < unit.endOffset }.map(\.page)
        if let firstPage = anchors.last(where: { $0.startOffset <= unit.startOffset })?.page { pages.insert(firstPage, at: 0) }
        return GAPassageMetadata(pageNumbers: pages).pageNumberLabel ?? metadata.pageNumberLabel ?? gaPage
    }

    var contentsUnits: [GAContentsUnit] {
        let sections = metadata.validReadingSections(in: text, passageTitle: title)
        let blocks = metadata.validReadingBlocks(in: text)
        let body = text as NSString
        let headings = contentsHeadings
        return sections.map { section in
            let hasSourceHeading = section.labelKind == .sourceTitle && blocks.contains { block in
                block.kind == .heading && block.startOffset == section.startOffset && body.substring(with: block.range) == section.title
            }
            let season = headings.first { $0.startOffset == section.startOffset && $0.isSeason }
            return GAContentsUnit(id: section.id, title: season?.title ?? section.title, labelKind: section.labelKind,
                startOffset: section.startOffset, endOffset: section.endOffset,
                headings: headings.filter { heading in
                    heading.startOffset >= section.startOffset && heading.startOffset < section.endOffset &&
                        !(hasSourceHeading && heading.startOffset == section.startOffset)
                })
        }
    }

    var hasCalendarContents: Bool {
        metadata.groupTitle?.localizedCaseInsensitiveContains("Seelenkalender") == true
    }

    var contentsHeadings: [GAContentsHeading] {
        let body = text as NSString
        let seasons = ["FRÜHLING": "Frühling", "SOMMER": "Sommer", "HERBST": "Herbst", "WINTER": "Winter"]
        var week: String?
        var entries: [GAContentsHeading] = []
        for (index, block) in metadata.validReadingBlocks(in: text).enumerated() where block.kind == .heading {
            let sourceTitle = body.substring(with: block.range)
            if hasCalendarContents, block.level == 2 {
                week = sourceTitle
                continue
            }
            if hasCalendarContents, block.level == 3, let number = Int(sourceTitle), (1...52).contains(number) {
                entries.append(GAContentsHeading(id: index, title: "Spruch \(number)", subtitle: week,
                    startOffset: block.startOffset, level: 2, isSeason: false))
                week = nil
            } else {
                let season = hasCalendarContents ? seasons[sourceTitle] : nil
                entries.append(GAContentsHeading(id: index, title: season ?? sourceTitle, subtitle: nil,
                    startOffset: block.startOffset, level: block.level ?? 2, isSeason: season != nil))
            }
        }
        return entries
    }
}

struct GAAnnotation: Identifiable, Codable, Hashable, Sendable {
    var id: String
    var marker: String
    var text: String
    var startOffset: Int? = nil
    var endOffset: Int? = nil

    init(id: String, marker: String, text: String, startOffset: Int? = nil, endOffset: Int? = nil) {
        self.id = id
        self.marker = marker
        self.text = text
        self.startOffset = startOffset
        self.endOffset = endOffset
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        marker = try container.decode(String.self, forKey: .marker)
        text = try container.decode(String.self, forKey: .text)
        // Invalid anchored ranges disable linking rather than changing the book.
        if container.contains(.startOffset) || container.contains(.endOffset) {
            startOffset = (try? container.decode(Int.self, forKey: .startOffset)) ?? -1
            endOffset = (try? container.decode(Int.self, forKey: .endOffset)) ?? -1
        }
    }

    func markerRanges(in text: String) -> [NSRange] {
        guard !marker.isEmpty else { return [] }
        let body = text as NSString
        if startOffset != nil || endOffset != nil {
            guard let startOffset, let endOffset, startOffset >= 0,
                  endOffset > startOffset, endOffset <= body.length else { return [] }
            let range = NSRange(location: startOffset, length: endOffset - startOffset)
            guard validUTF16Boundary(startOffset, in: body), validUTF16Boundary(endOffset, in: body),
                  Range(range, in: text) != nil, body.substring(with: range) == marker else { return [] }
            return [range]
        }
        var ranges: [NSRange] = []
        var start = 0
        while start < body.length {
            let range = body.range(of: marker, range: NSRange(location: start, length: body.length - start))
            guard range.location != NSNotFound else { break }
            ranges.append(range)
            start = NSMaxRange(range)
        }
        return ranges
    }

    var linkURL: URL? {
        var components = URLComponents()
        components.scheme = "ga-note"
        components.host = "annotation"
        components.queryItems = [URLQueryItem(name: "id", value: id)]
        return components.url
    }

    static func id(from url: URL) -> String? {
        guard url.scheme == "ga-note", url.host == "annotation" else { return nil }
        return URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "id" })?.value
    }

    private enum CodingKeys: String, CodingKey {
        case id, marker, text
        case startOffset = "start_offset"
        case endOffset = "end_offset"
    }
}

enum GAContentCompleteness: String, Codable, Hashable, Sendable {
    case complete
    case partial
    case unavailable
}

struct GAVolume: Identifiable, Codable, Hashable, Sendable {
    var id: String
    var gaNumber: String
    var title: String
    var subtitle: String
    var languageCode: String
    var yearLabel: String
    var type: GAWorkType
    var priority: Int
    var publicationState: GAPublicationState
    var proofingState: GAProofingState
    var sourceSummary: String
    var tags: [String]
    var passages: [GAPassage]
    var sanityChecks: [GASanityCheck]
    var contentPath: String?
    var catalogPassageCount: Int?
    var contentCompleteness: GAContentCompleteness?
    /// Retained even when passage bodies are removed from the catalog cache.
    var catalogContentFingerprint: String?
    var catalogIncludesReaderMetadata: Bool
    var catalogContentRevision: String?
    var contentUpdatedAt: Date?
    var downloadedContentRevision: String?
    var downloadedPassageCount: Int?

    init(
        id: String,
        gaNumber: String,
        title: String,
        subtitle: String,
        languageCode: String,
        yearLabel: String,
        type: GAWorkType,
        priority: Int,
        publicationState: GAPublicationState,
        proofingState: GAProofingState,
        sourceSummary: String,
        tags: [String],
        passages: [GAPassage],
        sanityChecks: [GASanityCheck],
        contentPath: String? = nil,
        catalogPassageCount: Int? = nil,
        contentCompleteness: GAContentCompleteness? = nil,
        catalogContentFingerprint: String? = nil,
        catalogIncludesReaderMetadata: Bool = false,
        catalogContentRevision: String? = nil,
        contentUpdatedAt: Date? = nil,
        downloadedContentRevision: String? = nil,
        downloadedPassageCount: Int? = nil
    ) {
        self.id = id
        self.gaNumber = gaNumber
        self.title = title
        self.subtitle = subtitle
        self.languageCode = languageCode
        self.yearLabel = yearLabel
        self.type = type
        self.priority = priority
        self.publicationState = publicationState
        self.proofingState = proofingState
        self.sourceSummary = sourceSummary
        self.tags = tags
        self.passages = passages
        self.sanityChecks = sanityChecks
        self.contentPath = contentPath
        self.catalogPassageCount = catalogPassageCount
        self.contentCompleteness = contentCompleteness
        self.catalogContentFingerprint = catalogContentFingerprint
        self.catalogIncludesReaderMetadata = catalogIncludesReaderMetadata
        self.catalogContentRevision = catalogContentRevision
        self.contentUpdatedAt = contentUpdatedAt
        self.downloadedContentRevision = downloadedContentRevision
        self.downloadedPassageCount = downloadedPassageCount
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let catalogPassages = try container.decodeIfPresent([GACatalogPassage].self, forKey: .passages) ?? []
        let includesMetadata = try container.decodeIfPresent(Bool.self, forKey: .catalogIncludesReaderMetadata)
            ?? (!catalogPassages.isEmpty && catalogPassages.allSatisfy { $0.metadata != nil })

        self.init(
            id: try container.decode(String.self, forKey: .id),
            gaNumber: try container.decode(String.self, forKey: .gaNumber),
            title: try container.decode(String.self, forKey: .title),
            subtitle: try container.decodeIfPresent(String.self, forKey: .subtitle) ?? "",
            languageCode: try container.decode(String.self, forKey: .languageCode),
            yearLabel: try container.decodeIfPresent(String.self, forKey: .yearLabel) ?? "",
            type: try container.decode(GAWorkType.self, forKey: .type),
            priority: try container.decodeIfPresent(Int.self, forKey: .priority) ?? Int.max,
            publicationState: try container.decode(GAPublicationState.self, forKey: .publicationState),
            proofingState: try container.decode(GAProofingState.self, forKey: .proofingState),
            sourceSummary: try container.decodeIfPresent(String.self, forKey: .sourceSummary) ?? "",
            tags: try container.decodeIfPresent([String].self, forKey: .tags) ?? [],
            passages: catalogPassages.compactMap(\.readablePassage),
            sanityChecks: try container.decodeIfPresent([GASanityCheck].self, forKey: .sanityChecks) ?? [],
            contentPath: try container.decodeIfPresent(String.self, forKey: .contentPath),
            catalogPassageCount: try container.decodeIfPresent(Int.self, forKey: .catalogPassageCount)
                ?? (catalogPassages.isEmpty ? nil : catalogPassages.count),
            contentCompleteness: try container.decodeIfPresent(GAContentCompleteness.self, forKey: .contentCompleteness),
            catalogContentFingerprint: try container.decodeIfPresent(String.self, forKey: .catalogContentFingerprint)
                ?? GACatalogPassage.contentFingerprint(catalogPassages, includesMetadata: includesMetadata),
            catalogIncludesReaderMetadata: includesMetadata,
            catalogContentRevision: try container.decodeIfPresent(String.self, forKey: .catalogContentRevision),
            contentUpdatedAt: Self.contentDate(from: container),
            downloadedContentRevision: try container.decodeIfPresent(String.self, forKey: .downloadedContentRevision),
            downloadedPassageCount: try container.decodeIfPresent(Int.self, forKey: .downloadedPassageCount)
        )
    }

    var isReadable: Bool {
        isCompleteContent(passages, expectedPassageCount: downloadedPassageCount ?? catalogPassageCount)
    }

    func isCompleteContent(_ candidate: [GAPassage]) -> Bool {
        isCompleteContent(candidate, expectedPassageCount: catalogPassageCount)
    }

    func isCompleteContent(_ candidate: [GAPassage], expectedPassageCount: Int?) -> Bool {
        guard publicationState != .publishedSeed,
              contentCompleteness != .partial, contentCompleteness != .unavailable,
              let expectedPassageCount, expectedPassageCount > 0,
              candidate.count == expectedPassageCount else { return false }
        return candidate.allSatisfy {
            !$0.id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
            !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        } && Set(candidate.map(\.id)).count == candidate.count
    }

    /// An older downloaded edition stays readable while an update is offered.
    func matchesCurrentEdition(_ candidate: [GAPassage], revision: String? = nil) -> Bool {
        guard isCompleteContent(candidate) else { return false }
        if let catalogContentRevision {
            return (revision ?? downloadedContentRevision) == catalogContentRevision
        }
        guard let catalogContentFingerprint else { return true }
        return Self.contentFingerprint(for: candidate, includesReaderMetadata: catalogIncludesReaderMetadata)
            == catalogContentFingerprint
    }

    var hasContentUpdate: Bool {
        isReadable && (catalogContentRevision != nil || catalogContentFingerprint != nil)
            && !matchesCurrentEdition(passages)
    }

    /// A dated packaged or cached edition must not be replaced by an older host.
    func preferringNewerEdition(over fallback: GAVolume) -> GAVolume {
        guard fallback.id == id, let knownDate = fallback.contentUpdatedAt else { return self }
        guard let incomingDate = contentUpdatedAt, incomingDate >= knownDate else { return fallback }
        return self
    }

    static func contentFingerprint(for passages: [GAPassage], includesReaderMetadata: Bool = true) -> String {
        GAPassageRevision.fingerprint(passages.map {
            GAPassageRevision(id: $0.id, textChecksum: GAPassageRevision.checksum(Data($0.text.utf8)),
                title: $0.title, gaPage: $0.gaPage, sourceLabel: $0.sourceLabel,
                metadata: includesReaderMetadata ? $0.metadata : nil)
        })
    }

    private static func contentDate(from container: KeyedDecodingContainer<CodingKeys>) -> Date? {
        if let timestamp = try? container.decode(String.self, forKey: .contentUpdatedAt) {
            if let date = try? Date.ISO8601FormatStyle(includingFractionalSeconds: true).parse(timestamp) {
                // Match the millisecond precision of previously cached catalog dates.
                let milliseconds = (date.timeIntervalSince1970 * 1_000).rounded(.down)
                return Date(timeIntervalSince1970: milliseconds / 1_000)
            }
            return try? Date.ISO8601FormatStyle().parse(timestamp)
        }
        return try? container.decode(Date.self, forKey: .contentUpdatedAt)
    }

    var isDownloadable: Bool {
        guard publicationState != .publishedSeed,
              contentCompleteness != .partial, contentCompleteness != .unavailable else { return false }
        guard let contentPath else { return false }
        return !contentPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var isReaderAvailable: Bool {
        isReadable || isDownloadable
    }

    var statusSummary: String {
        "\(publicationState.shortLabel) - \(proofingState.displayName)"
    }

    var catalogPassageSummary: String? {
        guard let catalogPassageCount, catalogPassageCount > 0 else { return nil }
        return catalogPassageCount == 1 ? "1 section" : "\(catalogPassageCount) sections"
    }

    var searchBlob: String {
        ([gaNumber, title, subtitle, languageCode, yearLabel, type.displayName,
          publicationState.shortLabel, publicationState.rawValue,
          proofingState.displayName, proofingState.rawValue] + tags).joined(separator: " ")
    }

    var gaSortLabel: String {
        let rawNumber = gaNumber
            .replacingOccurrences(of: AppEdition.workPrefix, with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let digits = rawNumber.prefix(while: { $0.isNumber })
        let suffix = rawNumber.drop(while: { $0.isNumber }).lowercased()
        let number = Int(digits) ?? Int.max
        return String(format: "%04lld%@", Int64(number), suffix)
    }

    private enum CodingKeys: String, CodingKey {
        case id
        case gaNumber = "ga_number"
        case title
        case subtitle
        case languageCode = "language"
        case yearLabel = "year_label"
        case type
        case priority
        case publicationState = "state"
        case proofingState = "proofing_state"
        case sourceSummary = "source_summary"
        case tags
        case passages
        case sanityChecks = "sanity_checks"
        case contentPath = "content_path"
        case catalogPassageCount = "catalog_passage_count"
        case contentCompleteness = "content_completeness"
        case catalogContentFingerprint = "catalog_content_fingerprint"
        case catalogIncludesReaderMetadata = "catalog_includes_reader_metadata"
        case catalogContentRevision = "content_revision"
        case contentUpdatedAt = "content_updated_at"
        case downloadedContentRevision = "downloaded_content_revision"
        case downloadedPassageCount = "downloaded_passage_count"
    }
}

enum ContentDownloadStatus: Equatable {
    case idle
    case downloading
    case loaded(Int)
    case failed(String)

    var isDownloading: Bool {
        self == .downloading
    }
}

enum CatalogClient {
    static var isServerConfigured: Bool {
        true
    }

    static func fetchCatalog() async throws -> [GAVolume] {
        try await fetchReaderCatalog()
    }

    static func fetchReaderCatalog() async throws -> [GAVolume] {
        let data = try await loadData(path: "/api/catalog")
        let payload = try JSONDecoder().decode(GACatalogPayload.self, from: data)
        return payload.works.sorted { $0.priority < $1.priority }
    }

    static func fetchDeveloperCatalog() async throws -> [GAVolume] {
        let data = try await loadData(path: "/api/developer/catalog")
        let payload = try JSONDecoder().decode(GACatalogPayload.self, from: data)
        return payload.works.sorted { $0.gaSortLabel < $1.gaSortLabel }
    }

    static func downloadPassages(path: String, for volumeID: GAVolume.ID? = nil, expectedPassageCount: Int? = nil) async throws -> [GAPassage] {
        let data = try await loadData(path: path)
        return try decodePassages(from: data, for: volumeID, expectedPassageCount: expectedPassageCount)
    }

    static func downloadEdition(path: String, for volumeID: GAVolume.ID, expectedPassageCount: Int? = nil,
                                expectedRevision: String? = nil) async throws -> LocalContentStore.Edition {
        let data = try await loadData(path: path)
        return try decodeDownloadEdition(from: data, for: volumeID,
            expectedPassageCount: expectedPassageCount, expectedRevision: expectedRevision)
    }

    static func decodeDownloadEdition(from data: Data, for volumeID: GAVolume.ID,
                                     expectedPassageCount: Int? = nil,
                                     expectedRevision: String? = nil) throws -> LocalContentStore.Edition {
        let actualRevision = GAPassageRevision.checksum(data)
        if let expectedRevision, actualRevision != expectedRevision { throw CatalogClientError.staleRevision }
        let passages = try decodePassages(from: data, for: volumeID, expectedPassageCount: expectedPassageCount)
        return LocalContentStore.Edition(workID: volumeID, passageCount: passages.count,
            contentRevision: actualRevision, passages: passages)
    }

    static func decodePassages(from data: Data, for volumeID: GAVolume.ID? = nil, expectedPassageCount: Int? = nil) throws -> [GAPassage] {
        let payload = try JSONDecoder().decode(GAContentPayload.self, from: data)
        if let volumeID, let workID = payload.workID, workID != volumeID {
            throw CatalogClientError.unexpectedWork
        }
        guard payload.publicationState != .publishedSeed, payload.state != .publishedSeed,
              payload.contentCompleteness == nil || payload.contentCompleteness == .complete,
              payload.completeness == nil || payload.completeness == .complete,
              !payload.passages.isEmpty,
              payload.passages.allSatisfy({
                  !$0.id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
                  !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
              }),
              Set(payload.passages.map(\.id)).count == payload.passages.count else {
            throw CatalogClientError.invalidContent
        }
        if let expectedPassageCount, payload.passages.count != expectedPassageCount {
            throw CatalogClientError.unexpectedPassageCount
        }
        if let declaredCount = payload.passageCount, payload.passages.count != declaredCount {
            throw CatalogClientError.unexpectedPassageCount
        }
        return payload.passages
    }

    private static func loadData(path: String) async throws -> Data {
        guard let url = contentURL(path: path) else {
            throw CatalogClientError.invalidURL
        }

        let (data, response) = try await URLSession.shared.data(from: url)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw CatalogClientError.invalidResponse
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw CatalogClientError.httpStatus(httpResponse.statusCode)
        }

        return data
    }

    static func contentURL(path: String, baseURL: URL? = nil) -> URL? {
        if let url = URL(string: path), url.scheme != nil {
            return url
        }

        guard var components = URLComponents(url: baseURL ?? self.baseURL, resolvingAgainstBaseURL: false),
              let requested = URLComponents(string: path) else {
            return nil
        }
        // API paths belong below the configured service prefix, including when
        // a catalog advertises them with a leading slash.
        let prefix = components.percentEncodedPath.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let suffix = requested.percentEncodedPath.drop(while: { $0 == "/" })
        components.percentEncodedPath = "/" + ([prefix, String(suffix)].filter { !$0.isEmpty }.joined(separator: "/"))
        components.percentEncodedQuery = requested.percentEncodedQuery
        components.percentEncodedFragment = requested.percentEncodedFragment
        return components.url
    }

    private static var baseURL: URL { AppEdition.readerBaseURL }
}

enum CatalogClientError: LocalizedError {
    case invalidURL
    case invalidResponse
    case httpStatus(Int)
    case unexpectedWork
    case invalidContent
    case unexpectedPassageCount
    case staleRevision

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            "The catalog endpoint URL is invalid."
        case .invalidResponse:
            "The catalog endpoint returned an invalid response."
        case .httpStatus(let statusCode):
            "The catalog endpoint returned HTTP \(statusCode)."
        case .unexpectedWork:
            "Der Server hat Text für ein anderes Werk geliefert."
        case .invalidContent:
            "Der Server hat keinen gültigen Lesetext geliefert."
        case .unexpectedPassageCount:
            "Die Anzahl der Abschnitte stimmt nicht mit dem vollständigen Buch überein. Bitte lade den Text erneut herunter."
        case .staleRevision:
            "Die Textversion auf dem Server hat sich geändert. Bitte aktualisiere die Bibliothek und versuche es erneut."
        }
    }
}

enum LocalContentStore {
    struct Edition: Codable {
        let workID: String
        let passageCount: Int
        let contentRevision: String?
        let passages: [GAPassage]
        var isLegacy = false

        private enum CodingKeys: String, CodingKey {
            case workID = "work_id"
            case passageCount = "passage_count"
            case contentRevision = "content_revision"
            case passages
        }
    }

    static func removePassages(for volumeID: GAVolume.ID) throws {
        let url = try contentFileURL(for: volumeID, createsDirectory: false)
        if FileManager.default.fileExists(atPath: url.path) {
            try FileManager.default.removeItem(at: url)
        }
    }
    static func loadPassages(for volumeID: GAVolume.ID) throws -> [GAPassage]? {
        try loadEdition(for: volumeID)?.passages
    }

    static func loadEdition(for volumeID: GAVolume.ID) throws -> Edition? {
        let fileURL = try contentFileURL(for: volumeID, createsDirectory: false)
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return nil }
        return try decodeEdition(from: Data(contentsOf: fileURL), for: volumeID)
    }

    static func decodeEdition(from data: Data, for volumeID: GAVolume.ID) throws -> Edition {
        if let edition = try? JSONDecoder().decode(Edition.self, from: data) {
            guard edition.workID == volumeID else { throw CatalogClientError.unexpectedWork }
            guard edition.passageCount == edition.passages.count else { throw CatalogClientError.unexpectedPassageCount }
            return edition
        }
        let passages = try JSONDecoder().decode([GAPassage].self, from: data)
        return Edition(workID: volumeID, passageCount: passages.count, contentRevision: nil,
            passages: passages, isLegacy: true)
    }

    static func save(passages: [GAPassage], for volumeID: GAVolume.ID, contentRevision: String? = nil) throws {
        let fileURL = try contentFileURL(for: volumeID, createsDirectory: true)
        let edition = Edition(workID: volumeID, passageCount: passages.count,
            contentRevision: contentRevision, passages: passages)
        let data = try JSONEncoder().encode(edition)
        try data.write(to: fileURL, options: [.atomic])
    }

    private static func contentFileURL(for volumeID: GAVolume.ID, createsDirectory: Bool) throws -> URL {
        guard let supportURL = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else {
            throw LocalContentStoreError.missingApplicationSupportDirectory
        }

        let directory = supportURL
            .appendingPathComponent(AppEdition.storageDirectory, isDirectory: true)
            .appendingPathComponent("Content", isDirectory: true)

        if createsDirectory {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        }

        let filename = volumeID.replacingOccurrences(of: "/", with: "-") + ".json"
        return directory.appendingPathComponent(filename, isDirectory: false)
    }
}

enum BundledContentStore {
    static func loadPassages(for volumeID: GAVolume.ID, bundle: Bundle = .main) throws -> [GAPassage]? {
        guard let url = bundle.url(
            forResource: volumeID,
            withExtension: "json",
            subdirectory: "BundledContent"
        ) else { return nil }
        let payload = try JSONDecoder().decode(GAContentPayload.self, from: Data(contentsOf: url))
        return payload.passages
    }
}

enum BundledCatalogStore {
    static func loadVolumes(bundle: Bundle = .main) throws -> [GAVolume] {
        guard let url = bundle.url(
            forResource: "catalog",
            withExtension: "json",
            subdirectory: "BundledCatalog"
        ) else { return [] }
        return try JSONDecoder().decode(GACatalogPayload.self, from: Data(contentsOf: url)).works
    }
}

enum LocalContentStoreError: LocalizedError {
    case missingApplicationSupportDirectory

    var errorDescription: String? {
        switch self {
        case .missingApplicationSupportDirectory:
            "The local content directory is unavailable."
        }
    }
}

private struct GACatalogPayload: Decodable {
    let works: [GAVolume]
}

private struct GAContentPayload: Decodable {
    let workID: String?
    let passageCount: Int?
    let contentCompleteness: GAContentCompleteness?
    let completeness: GAContentCompleteness?
    let publicationState: GAPublicationState?
    let state: GAPublicationState?
    let passages: [GAPassage]

    private enum CodingKeys: String, CodingKey {
        case workID = "work_id"
        case passageCount = "passage_count"
        case contentCompleteness = "content_completeness"
        case completeness
        case publicationState = "publication_state"
        case state
        case passages
    }
}

private struct GACatalogPassage: Decodable {
    let id: String
    let title: String
    let gaPage: String?
    let sourceLabel: String?
    let text: String?
    let metadata: GAPassageMetadata?
    let checksum: String?

    static func contentFingerprint(_ passages: [Self], includesMetadata: Bool) -> String? {
        guard !passages.isEmpty else { return nil }
        let revisions = passages.compactMap { passage -> GAPassageRevision? in
            // Embedded local passages are not catalog revision descriptors.
            // Deriving a fingerprint from them would change a manual volume on
            // its first Codable round trip.
            guard let checksum = passage.checksum else {
                return nil
            }
            return GAPassageRevision(id: passage.id, textChecksum: checksum, title: passage.title,
                gaPage: passage.gaPage, sourceLabel: passage.sourceLabel ?? "Catalog",
                metadata: includesMetadata ? passage.metadata ?? .empty : nil)
        }
        guard revisions.count == passages.count else { return nil }
        return GAPassageRevision.fingerprint(revisions)
    }

    var readablePassage: GAPassage? {
        guard let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return nil
        }

        return GAPassage(
            id: id,
            title: title,
            gaPage: gaPage,
            sourceLabel: sourceLabel ?? "Catalog",
            text: text,
            metadata: metadata ?? .empty
        )
    }

    private enum CodingKeys: String, CodingKey {
        case id
        case title
        case gaPage = "ga_page"
        case sourceLabel = "source_label"
        case text
        case metadata
        case checksum
    }
}

/// Only the reader's text identity and visible structure define an edition.
/// Developer source diffs and proofing status do not make a saved book stale.
private struct GAPassageRevision: Encodable {
    let id: String
    let textChecksum: String
    let title: String
    let gaPage: String?
    let sourceLabel: String
    let metadata: GAPassageMetadata?

    static func fingerprint(_ revisions: [Self]) -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        // All fields are strings, finite integer offsets and Codable metadata.
        return checksum(try! encoder.encode(revisions))
    }

    static func checksum(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
}
