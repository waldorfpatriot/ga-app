#if os(macOS)
import AppKit
#endif
import Combine
import CoreText
import FalzCore
import Foundation

@MainActor
final class AppModel: ObservableObject {
    @Published var library: LibraryData?
    @Published var categories: [BookCategory] = []
    @Published var selectedCategory: String?
    @Published var search = ""
    @Published var readableOnly = true
    @Published var sortOrder = "ga"
    @Published var layout: String = UserDefaults.standard.string(forKey: "libraryLayout") ?? "covers" {
        didSet { UserDefaults.standard.set(layout, forKey: "libraryLayout") }
    }
    @Published var selectedBook: LibraryBook?
    @Published var detailBook: LibraryBook?
    @Published var document: EPUBDocument?
    @Published var isOpening = false
    @Published var errorMessage: String?
    @Published var isRefreshing = false
    @Published var statusMessage: String?
    @Published private(set) var downloadingBookIDs: Set<String> = []
    @Published private var localCopies: [String: URL] = [:]
    @Published var positions: [String: ReadingPosition] = [:]
    var texturesURL: URL?
    private var accessURL: URL?
    private var openRequestID = UUID()
    private(set) var openingTask: Task<Void, Never>?
    private let cloudStore: CloudLibraryStore
    private let cloudClient: CloudLibraryClient
    private static func defaultCloudStore() -> CloudLibraryStore {
        #if DEBUG
        if let namespace = ProcessInfo.processInfo.environment["GA_CLOUD_STORAGE_NAMESPACE"],
           !namespace.isEmpty, namespace.utf8.count <= 100,
           namespace.unicodeScalars.allSatisfy({ CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_" )).contains($0) }) {
            return CloudLibraryStore(rootURL: CloudLibraryStore.applicationSupport.rootURL
                .appendingPathComponent("UITests", isDirectory: true).appendingPathComponent(namespace, isDirectory: true))
        }
        #endif
        return .applicationSupport
    }
    private static func defaultCloudClient() -> CloudLibraryClient {
        #if DEBUG
        if let value = ProcessInfo.processInfo.environment["GA_CATALOG_URL"], let url = URL(string: value) {
            return CloudLibraryClient(catalogURL: url, allowInsecureLoopback: true)
        }
        #endif
        return CloudLibraryClient()
    }
    private var localLibrary: LibraryData?
    private var localBooksByID: [String: LibraryBook] = [:]
    private var extractionCache: URL {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("de.falz.library/Books", isDirectory: true)
    }

    init(cloudStore: CloudLibraryStore? = nil, cloudClient: CloudLibraryClient? = nil,
         libraryURL: URL? = nil, refreshOnLaunch: Bool = true) {
        self.cloudStore = cloudStore ?? Self.defaultCloudStore()
        self.cloudClient = cloudClient ?? Self.defaultCloudClient()
        registerFonts()
        if let saved = UserDefaults.standard.data(forKey: "readingPositions"),
           let decoded = try? JSONDecoder().decode([String: ReadingPosition].self, from: saved) { positions = decoded }
        texturesURL = Self.findResourceDirectory("textures")
        if let url = texturesURL?.appendingPathComponent("categories.json"), let loaded = try? CategoryLoader.load(from: url) { categories = loaded }
        if let libraryURL { loadLibrary(libraryURL) }
        #if os(macOS)
        if libraryURL == nil, let bookmark = UserDefaults.standard.data(forKey: "libraryBookmark") {
            var stale = false
            if let url = try? URL(resolvingBookmarkData: bookmark, options: .withSecurityScope, bookmarkDataIsStale: &stale), FileManager.default.fileExists(atPath: url.appendingPathComponent("catalog.json").path) {
                _ = url.startAccessingSecurityScopedResource(); accessURL = url
                loadLibrary(url)
            }
        }
        #endif
        if library == nil, let url = Self.locateLibrary() { loadLibrary(url) }
        if let books = try? self.cloudStore.cachedBooks() {
            library = LibraryData(rootURL: localLibrary?.rootURL ?? self.cloudStore.rootURL, books: books)
        }
        refreshLocalCopies()
        if refreshOnLaunch { Task { await refreshCatalog() } }
    }

    static func locateLibrary() -> URL? {
        var candidates: [URL] = []
        let environment = ProcessInfo.processInfo.environment
        if let override = environment["GA_LIBRARY_PATH"] ?? environment["FALZ_LIBRARY_PATH"] {
            candidates.append(URL(fileURLWithPath: override))
        }
        if let bundled = Bundle.main.resourceURL { candidates.append(bundled.appendingPathComponent("library")) }
        return candidates.first { FileManager.default.fileExists(atPath: $0.appendingPathComponent("catalog.json").path) }
    }

    static func findResourceDirectory(_ name: String) -> URL? {
        var candidates: [URL] = []
        if let resource = Bundle.main.resourceURL { candidates.append(resource.appendingPathComponent(name)) }
        var base = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        for _ in 0..<6 { candidates.append(base.appendingPathComponent("assets/\(name)")); base.deleteLastPathComponent() }
        return candidates.first { FileManager.default.fileExists(atPath: $0.path) }
    }

    var books: [LibraryBook] {
        let filtered = (library?.filtered(query: search, categoryID: selectedCategory, readableOnly: false) ?? [])
            .filter { !readableOnly || availability(for: $0) != .unavailable }
        if sortOrder == "title" { return filtered.sorted { $0.title.localizedStandardCompare($1.title) == .orderedAscending } }
        if sortOrder == "recent" { return filtered.sorted { (positions[$0.id]?.lastRead ?? .distantPast) > (positions[$1.id]?.lastRead ?? .distantPast) } }
        return filtered
    }
    var readableCount: Int { library?.books.filter { availability(for: $0) != .unavailable }.count ?? 0 }
    var downloadedCount: Int { library?.books.filter { localURL(for: $0) != nil }.count ?? 0 }
    func availability(for book: LibraryBook) -> BookAvailability {
        if localURL(for: book) != nil { return .downloaded }
        if downloadingBookIDs.contains(book.id) { return .downloading }
        return book.isAvailableOnServer ? .cloud : .unavailable
    }
    func localURL(for book: LibraryBook) -> URL? { localCopies[book.id] }
    private func verifiedLocalURL(for book: LibraryBook) -> URL? {
        if let url = cloudStore.downloadedURL(for: book) { return url }
        guard let localLibrary else { return nil }
        let localBook = localBooksByID[book.id] ?? book
        guard let url = try? localLibrary.epubURL(for: localBook),
              let values = try? url.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey]),
              values.isRegularFile == true, (values.fileSize ?? 0) > 0 else { return nil }
        return url
    }
    private func refreshLocalCopies() {
        // Rendering hundreds of badges must not repeatedly hit the filesystem.
        // Re-scan on catalog refresh and verify the selected file again on opening.
        localCopies = Dictionary((library?.books ?? []).compactMap { book in
            verifiedLocalURL(for: book).map { (book.id, $0) }
        }, uniquingKeysWith: { first, _ in first })
    }
    func refreshCatalog() async {
        guard !isRefreshing else { return }
        isRefreshing = true
        refreshLocalCopies()
        defer { isRefreshing = false }
        do {
            let books = try await cloudClient.fetchCatalog()
            try cloudStore.saveCatalog(books)
            library = LibraryData(rootURL: localLibrary?.rootURL ?? cloudStore.rootURL, books: books)
            refreshLocalCopies()
            statusMessage = nil
        } catch {
            statusMessage = library == nil
                ? "Der Katalog konnte nicht geladen werden. Bitte die Verbindung prüfen und erneut laden."
                : "Offline-Katalog · Heruntergeladene Bücher bleiben lesbar."
        }
    }
    var currentCategory: BookCategory? { categories.first { $0.id == selectedCategory } }
    var visibleCategories: [BookCategory] {
        let known = Set(categories.map(\.id))
        let extra = Set(library?.books.map(\.categoryId) ?? []).subtracting(known).sorted().map {
            BookCategory(id: $0, name: $0.replacingOccurrences(of: "-", with: " ").capitalized, colorHex: "#6E6650")
        }
        return categories.filter { category in library?.books.contains { $0.categoryId == category.id } == true } + extra
    }
    func count(_ category: BookCategory) -> Int {
        library?.books.filter { $0.categoryId == category.id && (!readableOnly || availability(for: $0) != .unavailable) }.count ?? 0
    }
    func category(for book: LibraryBook) -> BookCategory {
        categories.first { $0.id == book.categoryId } ?? BookCategory(id: book.categoryId, name: book.sourceCategory ?? "Gesamtausgabe", colorHex: "#6E6650")
    }
    func textureURL(for category: BookCategory) -> URL? {
        guard let path = category.texturePath, let base = texturesURL else { return nil }
        return try? LibraryData.safeResource(path, within: base)
    }
    var goldURL: URL? { texturesURL?.appendingPathComponent("gold/gold-foil.png") }
    func loadLibrary(_ url: URL) {
        do {
            let loaded = try LibraryData(rootURL: url)
            localLibrary = loaded
            localBooksByID = Dictionary(loaded.books.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
            library = loaded; selectedCategory = nil; errorMessage = nil
            refreshLocalCopies()
        }
        catch { errorMessage = error.localizedDescription }
    }
    #if os(macOS)
    func chooseLibrary() {
        let panel = NSOpenPanel()
        panel.title = "Bibliothek auswählen"; panel.message = "Wähle den Ordner, der catalog.json und die EPUB-Dateien enthält."
        panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        accessURL?.stopAccessingSecurityScopedResource()
        _ = url.startAccessingSecurityScopedResource(); accessURL = url
        if let bookmark = try? url.bookmarkData(options: .withSecurityScope, includingResourceValuesForKeys: nil, relativeTo: nil) {
            UserDefaults.standard.set(bookmark, forKey: "libraryBookmark")
        }
        closeBook(); loadLibrary(url)
        Task { await refreshCatalog() }
    }
    #endif
    func openBook(_ book: LibraryBook) {
        guard !downloadingBookIDs.contains(book.id) else { return }
        let existingURL = verifiedLocalURL(for: book)
        localCopies[book.id] = existingURL
        guard availability(for: book) != .unavailable else { detailBook = book; return }
        let request = UUID(); openRequestID = request
        selectedBook = book; isOpening = true; document = nil; errorMessage = nil
        if existingURL == nil { downloadingBookIDs.insert(book.id) }
        let cache = extractionCache, client = cloudClient, store = cloudStore
        openingTask = Task {
            do {
                let result = try await Task.detached(priority: .userInitiated) {
                    let url: URL
                    if let existingURL { url = existingURL }
                    else { url = try await client.download(book, to: store, cacheRoot: cache) }
                    return try EPUBLoader.open(url, cacheRoot: cache)
                }.value
                localCopies[book.id] = verifiedLocalURL(for: book)
                downloadingBookIDs.remove(book.id)
                guard openRequestID == request else { return }
                document = result; isOpening = false
            } catch {
                localCopies[book.id] = verifiedLocalURL(for: book)
                downloadingBookIDs.remove(book.id)
                guard openRequestID == request else { return }
                selectedBook = nil; isOpening = false; errorMessage = error.localizedDescription
            }
        }
    }
    // Downloads continue after returning to the library. Invalidating this request
    // prevents a late result (or error) from replacing the current screen.
    func closeBook() { openRequestID = UUID(); selectedBook = nil; document = nil; isOpening = false }
    func savePosition(bookID: String, chapter: Int, fraction: Double, contentsEntryID: String? = nil) {
        positions[bookID] = ReadingPosition(chapter: chapter, fraction: fraction, contentsEntryID: contentsEntryID)
        if let data = try? JSONEncoder().encode(positions) { UserDefaults.standard.set(data, forKey: "readingPositions") }
    }
    #if os(macOS)
    func reveal(_ book: LibraryBook) {
        if let url = localURL(for: book) { NSWorkspace.shared.activateFileViewerSelecting([url]) }
    }
    #endif
    private func registerFonts() {
        var folders: [URL] = []
        if let resource = Bundle.main.resourceURL { folders.append(resource.appendingPathComponent("Fonts")) }
        let cwd = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        folders += [cwd.appendingPathComponent("output/falz-icons/fonts"), cwd.deletingLastPathComponent().appendingPathComponent("output/falz-icons/fonts")]
        for folder in folders {
            for url in (try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)) ?? [] where ["ttf", "otf"].contains(url.pathExtension) {
                CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
            }
        }
    }
}
