import Foundation

public struct LibraryBook: Codable, Identifiable, Hashable, Sendable {
    public let id: String
    public let gaNumber: String
    public let title: String
    public let author: String
    public let categoryId: String
    public let epubPath: String?
    public let sourcePath: String?
    public let chapterCount: Int?
    public let availability: String?
    public let qualityNote: String?
    public let sourceStatus: String?
    public let sourceCategory: String?

    /// Server availability is separate from whether this device already has a copy.
    public let available: Bool?
    public let downloadURL: String?
    public let byteSize: Int64?
    public let sha256: String?

    public init(id: String, gaNumber: String, title: String, author: String, categoryId: String,
                epubPath: String? = nil, sourcePath: String? = nil, chapterCount: Int? = nil,
                availability: String? = nil, qualityNote: String? = nil, sourceStatus: String? = nil,
                sourceCategory: String? = nil, available: Bool? = nil, downloadURL: String? = nil,
                byteSize: Int64? = nil, sha256: String? = nil) {
        self.id = id; self.gaNumber = gaNumber; self.title = title; self.author = author
        self.categoryId = categoryId; self.epubPath = epubPath; self.sourcePath = sourcePath
        self.chapterCount = chapterCount; self.availability = availability; self.qualityNote = qualityNote
        self.sourceStatus = sourceStatus; self.sourceCategory = sourceCategory; self.available = available
        self.downloadURL = downloadURL; self.byteSize = byteSize; self.sha256 = sha256
    }

    public var isAvailableOnServer: Bool { available ?? hasEPUB }
    public var hasEPUB: Bool { epubPath?.isEmpty == false && availability != "unavailable" }
    public var gaLabel: String { gaNumber.lowercased().hasPrefix("ga") ? gaNumber : "GA \(gaNumber)" }
    public var normalizedSearchText: String {
        "\(gaLabel) \(title) \(author)".folding(options: [.diacriticInsensitive, .caseInsensitive], locale: .current)
    }
}

public struct BookCategory: Identifiable, Hashable, Sendable {
    public let id: String
    public let name: String
    public let subtitle: String?
    public let colorHex: String
    public let texturePath: String?
    public let order: Int

    public init(id: String, name: String, subtitle: String? = nil, colorHex: String, texturePath: String? = nil, order: Int = 100) {
        self.id = id; self.name = name; self.subtitle = subtitle
        self.colorHex = colorHex; self.texturePath = texturePath; self.order = order
    }
}

public enum LibraryError: LocalizedError {
    case missingCatalog(URL)
    case unsafePath(String)
    case invalidCategoryData
    public var errorDescription: String? {
        switch self {
        case .missingCatalog(let url): return "Kein Katalog in \(url.path) gefunden. Bitte den Bibliotheksordner mit catalog.json auswählen."
        case .unsafePath(let path): return "Der Bibliothekspfad ist nicht zulässig: \(path)"
        case .invalidCategoryData: return "Die Kategorie-Datei ist ungültig."
        }
    }
}

public struct LibraryData: Sendable {
    public let rootURL: URL
    public let books: [LibraryBook]
    public init(rootURL: URL) throws {
        self.rootURL = rootURL.standardizedFileURL
        let url = self.rootURL.appendingPathComponent("catalog.json")
        guard FileManager.default.fileExists(atPath: url.path) else { throw LibraryError.missingCatalog(rootURL) }
        let data = try Data(contentsOf: url)
        books = try Self.decodeBooks(data)
    }

    public init(rootURL: URL, books: [LibraryBook]) {
        self.rootURL = rootURL.standardizedFileURL
        self.books = books
    }

    public static func decodeBooks(_ data: Data) throws -> [LibraryBook] {
        let decoder = JSONDecoder()
        if let array = try? decoder.decode([LibraryBook].self, from: data) { return array }
        struct Envelope: Decodable { let books: [LibraryBook] }
        return try decoder.decode(Envelope.self, from: data).books
    }

    public func epubURL(for book: LibraryBook) throws -> URL? {
        guard let path = book.epubPath, !path.isEmpty else { return nil }
        return try Self.safeResource(path, within: rootURL)
    }

    public static func safeResource(_ path: String, within root: URL) throws -> URL {
        guard !path.hasPrefix("/"), !path.contains("\\"), !path.contains("\0") else { throw LibraryError.unsafePath(path) }
        let decoded = path.removingPercentEncoding ?? path
        guard !decoded.hasPrefix("/"), !decoded.contains("\\"), !decoded.contains("\0") else { throw LibraryError.unsafePath(path) }
        let components = decoded.split(separator: "/")
        guard !components.contains("..") else { throw LibraryError.unsafePath(path) }
        var result = root.standardizedFileURL.resolvingSymlinksInPath()
        let base = result.path
        // Resolving the complete URL alone can miss an ancestor symlink when the
        // final file does not exist. Inspect each component before returning it.
        for component in components {
            result.appendPathComponent(String(component))
            if (try? FileManager.default.destinationOfSymbolicLink(atPath: result.path)) != nil {
                throw LibraryError.unsafePath(path)
            }
        }
        result = result.standardizedFileURL
        guard result.path.hasPrefix(base + "/") else { throw LibraryError.unsafePath(path) }
        return result
    }

    public func filtered(query: String, categoryID: String?, readableOnly: Bool) -> [LibraryBook] {
        let foldedQuery = query.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: .current)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let explicitGA = Self.explicitGAQuery(foldedQuery)
        let terms = (explicitGA?.text ?? foldedQuery)
            .split(whereSeparator: { $0.isWhitespace }).map(String.init)
        return books.filter { book in
            (categoryID == nil || book.categoryId == categoryID) && (!readableOnly || book.isAvailableOnServer) &&
            (explicitGA == nil || Self.matchesGANumber(book.gaNumber, query: explicitGA!.number)) &&
            terms.allSatisfy { book.normalizedSearchText.contains($0) }
        }.sorted { $0.gaNumber.localizedStandardCompare($1.gaNumber) == .orderedAscending }
    }

    private static func explicitGAQuery(_ query: String) -> (number: String, text: String)? {
        let pattern = #"^ga\s*[-.:]?\s*(\d+[a-z]?(?:[-/][a-z0-9]+)*)(?:\s+(.*))?$"#
        guard let expression = try? NSRegularExpression(pattern: pattern),
              let match = expression.firstMatch(in: query, range: NSRange(query.startIndex..., in: query)),
              let numberRange = Range(match.range(at: 1), in: query) else { return nil }
        let textRange = Range(match.range(at: 2), in: query)
        return (String(query[numberRange]), textRange.map { String(query[$0]) } ?? "")
    }

    private static func matchesGANumber(_ number: String, query: String) -> Bool {
        func split(_ value: String) -> (Int?, String) {
            let normalized = value.lowercased().replacingOccurrences(of: "ga", with: "").filter { !$0.isWhitespace }
            let digits = normalized.prefix(while: \.isNumber)
            return (Int(digits), String(normalized.dropFirst(digits.count)))
        }
        let candidate = split(number), wanted = split(query)
        guard candidate.0 == wanted.0, wanted.0 != nil else { return false }
        if wanted.1.isEmpty { return true } // GA 300 includes its lettered or numbered parts.
        return candidate.1 == wanted.1 || candidate.1.hasPrefix(wanted.1 + "/") || candidate.1.hasPrefix(wanted.1 + "-")
    }
}

public enum CategoryLoader {
    /// The descriptive research JSON may include provenance and additional fields.
    public static func load(from url: URL) throws -> [BookCategory] {
        let object = try JSONSerialization.jsonObject(with: Data(contentsOf: url))
        let items: [[String: Any]]
        if let array = object as? [[String: Any]] { items = array }
        else if let dict = object as? [String: Any], let array = dict["categories"] as? [[String: Any]] { items = array }
        else { throw LibraryError.invalidCategoryData }
        return items.enumerated().compactMap { index, item in
            guard let id = item["id"] as? String else { return nil }
            return BookCategory(
                id: id,
                name: item["name"] as? String ?? item["label"] as? String ?? item["title"] as? String ?? id,
                subtitle: item["subtitle"] as? String ?? item["description"] as? String,
                colorHex: item["colorHex"] as? String ?? item["hex"] as? String ?? item["color"] as? String ?? "#69604B",
                texturePath: item["texturePath"] as? String ?? item["texture"] as? String,
                order: item["order"] as? Int ?? index
            )
        }.sorted { $0.order < $1.order }
    }
}

public struct ReadingPosition: Codable, Equatable, Sendable {
    public var chapter: Int
    public var fraction: Double
    public var lastRead: Date
    public var contentsEntryID: String?
    public init(chapter: Int = 0, fraction: Double = 0, lastRead: Date = Date(), contentsEntryID: String? = nil) {
        self.chapter = max(0, chapter)
        self.fraction = min(1, max(0, fraction.isFinite ? fraction : 0))
        self.lastRead = lastRead
        self.contentsEntryID = contentsEntryID
    }
}
