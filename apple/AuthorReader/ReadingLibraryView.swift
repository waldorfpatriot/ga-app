import SwiftUI
#if os(iOS)
import UIKit
#else
import AppKit
#endif

private enum ReadingDestination: String, CaseIterable, Identifiable {
    case home, library, search
    var id: String { rawValue }
    var title: String {
        switch self { case .home: "Jetzt lesen"; case .library: "Bibliothek"; case .search: "Suchen" }
    }
    var symbol: String {
        switch self { case .home: "book"; case .library: "books.vertical"; case .search: "magnifyingglass" }
    }
}

private struct OpenReading: Identifiable {
    var id = UUID()
    var volume: GAVolume
    var passageID: String?
    var offset: Int?
    var searchText: String?
}

private struct ReadingShelf: Identifiable {
    var id: String
    var title: String
    var volumeIDs: [String]
}

struct ReadingLibraryView: View {
    private static let steinerHomeShelves: [ReadingShelf] = [
        ReadingShelf(id: "foundations", title: "Grundlagen entdecken", volumeIDs: ["ga-009", "ga-010", "ga-013"]),
        ReadingShelf(id: "freedom", title: "Freiheit und Erkenntnis", volumeIDs: ["ga-003", "ga-004"]),
        ReadingShelf(id: "karma", title: "Karma", volumeIDs: ["ga-120", "ga-135", "ga-235"]),
        ReadingShelf(id: "education", title: "Erziehung", volumeIDs: ["ga-293", "ga-294", "ga-311"]),
        ReadingShelf(id: "social-threefolding", title: "Dreigliederung", volumeIDs: ["ga-023", "ga-024", "ga-334"]),
        ReadingShelf(id: "curative-education", title: "Heilpädagogik", volumeIDs: ["ga-317"]),
        ReadingShelf(id: "eurythmy", title: "Eurythmie", volumeIDs: ["ga-277a", "ga-278", "ga-279"]),
        ReadingShelf(id: "speech", title: "Sprachgestaltung", volumeIDs: ["ga-280"]),
        ReadingShelf(id: "meditation", title: "Meditation und geistige Schulung", volumeIDs: ["ga-016", "ga-017", "ga-026"]),
        ReadingShelf(id: "christianity", title: "Christentum", volumeIDs: ["ga-103", "ga-112", "ga-131"]),
        ReadingShelf(id: "medicine", title: "Medizin und Heilkunst", volumeIDs: ["ga-027", "ga-312", "ga-316"]),
        ReadingShelf(id: "agriculture", title: "Natur und Landwirtschaft", volumeIDs: ["ga-327", "ga-230", "ga-351"]),
        ReadingShelf(id: "art", title: "Kunst und Ästhetik", volumeIDs: ["ga-271", "ga-275", "ga-276"])
    ]

    private static let bundledVolumes = Dictionary(uniqueKeysWithValues:
        SeedLibrary.readerVolumes.filter(\.isReadable).map { ($0.id, $0) }
    )
    @Environment(ReadingStore.self) private var personal
    @Environment(AccessStore.self) private var access
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.scenePhase) private var scenePhase
    @State private var destination: ReadingDestination = .home
    @State private var volumes = SeedLibrary.readerVolumes
    @State private var currentReading: OpenReading?
    @State private var readingAfterDetails: OpenReading?
    @State private var detailVolume: GAVolume?
    @State private var detailExportError: String?
    @State private var filter = "all"
    @State private var query = ""
    @State private var searchIsPresented = false
    @State private var results: [LibrarySearchHit] = []
    @State private var searchInProgress = false
    @State private var downloadStates: [String: ContentDownloadStatus] = [:]
    @State private var catalogMessage: String?
    @State private var isLoadingCatalog = false
    @State private var hasLoadedLibrary = false
    @State private var lastCatalogRefresh: Date?
    @State private var serverEditions: [String: GAVolume] = [:]
    @State private var showsCollections = false
    @State private var showsAccess = false
    @State private var showsDetailAccess = false
    @State private var newCollectionName = ""
    @State private var errorMessage: String?
    @AppStorage("libraryGrid") private var usesGrid = true
    @AppStorage("librarySort") private var sort = "recent"

    private var visibleVolumes: [GAVolume] {
        let filtered = volumes.filter { volume in
            return switch filter {
            case "reading": personal.status(for: volume.id) == .reading
            case "want": personal.status(for: volume.id) == .wantToRead
            case "finished": personal.status(for: volume.id) == .finished
            case "downloaded": volume.isReadable
            case "updates": updateAvailable(for: volume)
            case "all": true
            default: personal.collections.first(where: { $0.id == filter })?.volumeIDs.contains(volume.id) == true
            }
        }
        return filtered.sorted { a, b in
            switch sort {
            case "title": return a.title.localizedStandardCompare(b.title) == .orderedAscending
            case "year": return a.yearLabel == b.yearLabel ? a.gaSortLabel < b.gaSortLabel : a.yearLabel < b.yearLabel
            case "ga": return a.gaSortLabel < b.gaSortLabel
            default:
                let left = personal.position(for: a.id)?.updatedAt ?? .distantPast
                let right = personal.position(for: b.id)?.updatedAt ?? .distantPast
                return left == right ? a.priority < b.priority : left > right
            }
        }
    }

    private var recentVolumes: [GAVolume] {
        personal.recentVolumeIDs.compactMap { id in volumes.first { $0.id == id } }
    }

    private var homeShelves: [ReadingShelf] {
        if AppEdition.isSteiner { return Self.steinerHomeShelves }
        let available = volumes.filter(\.isReaderAvailable).sorted { $0.priority < $1.priority }
        return stride(from: 0, to: available.count, by: 6).map { start in
            ReadingShelf(id: "works-\(start)", title: start == 0 ? "Werke entdecken" : "Weitere Werke",
                volumeIDs: available[start..<min(start + 6, available.count)].map(\.id))
        }
    }

    var body: some View {
        Group {
            #if os(macOS)
            NavigationSplitView {
                List(ReadingDestination.allCases, selection: Binding<ReadingDestination?>(get: { destination }, set: { if let value = $0 { destination = value } })) { item in
                    Label(item.title, systemImage: item.symbol).tag(item)
                }
                .navigationTitle(AppEdition.editionTitle)
                .navigationSplitViewColumnWidth(min: 200, ideal: 230)
            } detail: {
                navigationPage(destination)
            }
            .frame(minWidth: 640, minHeight: 500)
            #else
            TabView(selection: $destination) {
                ForEach(ReadingDestination.allCases) { item in
                    Tab(item.title, systemImage: item.symbol, value: item) {
                        navigationPage(item)
                    }
                }
            }
            .tabViewStyle(.sidebarAdaptable)
            #endif
        }
        .task {
            guard !hasLoadedLibrary else { return }
            hasLoadedLibrary = true
            restoreLibrary()
            await reloadCatalog(isAutomatic: true)
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { Task { await reloadCatalog(isAutomatic: true) } }
        }
        .sheet(item: $detailVolume, onDismiss: {
            if let reading = readingAfterDetails {
                readingAfterDetails = nil
                open(reading.volume, passageID: reading.passageID, offset: reading.offset)
            }
        }) { volume in
            bookDetails(volume)
                .onDisappear { detailExportError = nil }
        }
        .sheet(isPresented: $showsAccess) { PurchaseScreen() }
        .sheet(isPresented: $showsCollections) { collectionEditor }
        .onChange(of: destination) { searchIsPresented = false }
        .onChange(of: personal.collections.map(\.id)) {
            let builtIn = ["all", "reading", "want", "finished", "downloaded", "updates"]
            if !builtIn.contains(filter), !personal.collections.contains(where: { $0.id == filter }) {
                filter = "all"
            }
        }
        #if os(iOS)
        .fullScreenCover(item: $currentReading) { reading in readerSession(reading) }
        #else
        .sheet(item: $currentReading) { reading in
            readerSession(reading).frame(minWidth: 640, idealWidth: 850, minHeight: 500, idealHeight: 760)
        }
        #endif
        .alert("Aktion nicht abgeschlossen", isPresented: Binding(
            get: { errorMessage != nil && detailVolume == nil }, set: { if !$0 { errorMessage = nil } }
        )) {
            Button("OK") { errorMessage = nil }
        } message: { Text(errorMessage ?? "") }
    }

    private func navigationPage(_ item: ReadingDestination) -> some View {
        NavigationStack {
            Group {
                switch item {
                case .home: home
                case .library: library
                case .search: search
                }
            }
            .navigationTitle(item.title)
            .toolbar {
                ToolbarItem {
                    Button("App-Zugang", systemImage: "person.crop.circle") { showsAccess = true }
                        .accessibilityIdentifier("show-access")
                }
                if item == .library {
                    ToolbarItem {
                        Menu {
                            Picker("Ansicht", selection: $usesGrid) {
                                Label("Cover", systemImage: "square.grid.2x2").tag(true)
                                Label("Liste", systemImage: "list.bullet").tag(false)
                            }
                            Picker("Sortieren", selection: $sort) {
                                Text("Zuletzt gelesen").tag("recent")
                                Text(AppEdition.workNumberLabel).tag("ga")
                                Text("Titel").tag("title")
                                Text("Erscheinungsjahr").tag("year")
                            }
                            Button("Sammlungen verwalten", systemImage: "folder.badge.plus") { showsCollections = true }
                            Button("Nach Updates suchen", systemImage: "arrow.triangle.2.circlepath") {
                                Task { await reloadCatalog() }
                            }.disabled(isLoadingCatalog)
                        } label: { Label("Bibliotheksoptionen", systemImage: "ellipsis.circle") }
                    }
                }
            }
        }
    }

    private var home: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 30) {
                if let volume = recentVolumes.first {
                    Text("Weiterlesen").font(.title2.bold()).accessibilityAddTraits(.isHeader)
                    continueReading(volume)
                } else if let volume = volumes.first(where: \.isReaderAvailable) {
                    Text("Deine nächste Seite").font(.title2.bold()).accessibilityAddTraits(.isHeader)
                    continueReading(volume)
                }
                if recentVolumes.count > 1 {
                    shelf("Zuletzt gelesen", works: Array(recentVolumes.dropFirst().prefix(3)))
                }
                ForEach(homeShelves) { category in
                    let works = orderedWorks(category.volumeIDs)
                    if !works.isEmpty {
                        shelf(category.title, works: works)
                    }
                }
                HStack(spacing: 8) {
                    Image(systemName: "icloud")
                    Text(personal.syncStatus).font(.footnote)
                }
                .foregroundStyle(.secondary)
                .accessibilityElement(children: .combine)
                if let personalError = personal.lastError {
                    Text(personalError).font(.footnote).foregroundStyle(.secondary)
                    Button("Erneut synchronisieren") { Task { await personal.sync() } }
                }
            }
            .padding(24)
            .frame(maxWidth: 1020, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .refreshable { await reloadCatalog() }
    }

    private func continueReading(_ volume: GAVolume) -> some View {
        Button { open(volume) } label: {
            Group {
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 18) {
                        BookCover(volume: volume).frame(width: 100)
                        continueLabel(volume)
                    }
                } else {
                    HStack(alignment: .center, spacing: 20) {
                        BookCover(volume: volume).frame(width: 100)
                        continueLabel(volume).frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
            .padding(22)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.quaternary.opacity(0.45), in: RoundedRectangle(cornerRadius: 20))
            .contentShape(RoundedRectangle(cornerRadius: 20))
        }
        .buttonStyle(.plain)
        .contextMenu { workActions(volume) }
    }

    private func continueLabel(_ volume: GAVolume) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(volume.gaNumber).font(.caption).foregroundStyle(.secondary)
            Text(volume.title).font(.title2.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                .foregroundStyle(volume.isReaderAvailable ? Color.primary : Color.secondary)
            if let position = personal.position(for: volume.id) {
                if let passage = volume.passages.first(where: { $0.id == position.passageID }) {
                    Text(passage.title).font(.subheadline).foregroundStyle(.secondary)
                }
                ProgressView(value: position.fraction).accessibilityLabel("Lesefortschritt")
                Text("\(Int(position.fraction * 100)) % gelesen").font(.caption).foregroundStyle(.secondary)
            } else {
                Text(AppEdition.authorName).font(.subheadline).foregroundStyle(.secondary)
            }
            if volume.isReaderAvailable {
                Label(personal.position(for: volume.id) == nil ? "Lesen" : "Weiterlesen", systemImage: "book.fill")
                    .font(.headline).foregroundStyle(.tint).padding(.top, 4)
            } else {
                availability(volume)
            }
        }
    }

    private func shelf(_ title: String, works: [GAVolume]) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(title).font(.title2.bold()).accessibilityAddTraits(.isHeader)
            LazyVGrid(columns: gridColumns, alignment: .leading, spacing: 24) {
                ForEach(works) { volume in bookTile(volume) }
            }
        }
    }

    private var gridColumns: [GridItem] {
        [GridItem(.adaptive(minimum: dynamicTypeSize.isAccessibilitySize ? 250 : 130, maximum: dynamicTypeSize.isAccessibilitySize ? .infinity : 210), spacing: 24, alignment: .top)]
    }

    private var library: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Menu {
                    Picker("Sammlung", selection: $filter) {
                        Text("Alle Werke").tag("all")
                        Text("Wird gelesen").tag("reading")
                        Text("Möchte ich lesen").tag("want")
                        Text("Gelesen").tag("finished")
                        Text("Offline verfügbar").tag("downloaded")
                        Text("Updates verfügbar").tag("updates")
                        ForEach(personal.collections) { collection in Text(collection.name).tag(collection.id) }
                    }
                    Button("Neue Sammlung", systemImage: "folder.badge.plus") { showsCollections = true }
                } label: {
                    Label(filterTitle, systemImage: "line.3.horizontal.decrease").font(.headline).frame(minHeight: 44)
                }
                Text("\(volumes.count) Werke · \(volumes.filter(\.isReaderAvailable).count) zum Lesen verfügbar")
                    .font(.footnote).foregroundStyle(.secondary)
                let updateCount = volumes.filter { updateAvailable(for: $0) }.count
                if updateCount > 0 {
                    Button {
                        filter = "updates"
                    } label: {
                        Label("\(updateCount) \(updateCount == 1 ? "Update verfügbar" : "Updates verfügbar")", systemImage: "arrow.down.circle")
                    }.accessibilityIdentifier("available-library-updates")
                }
                if let catalogMessage {
                    VStack(alignment: .leading, spacing: 8) {
                        Label(catalogMessage, systemImage: "wifi.slash").font(.footnote).foregroundStyle(.secondary)
                        Button("Katalog erneut laden") { Task { await reloadCatalog() } }.disabled(isLoadingCatalog)
                    }
                }
                if visibleVolumes.isEmpty {
                    ContentUnavailableView("Noch keine Werke", systemImage: "books.vertical", description: Text("Füge Werke über ihr Menü zu dieser Sammlung hinzu."))
                } else if usesGrid && !dynamicTypeSize.isAccessibilitySize {
                    LazyVGrid(columns: gridColumns, alignment: .leading, spacing: 30) {
                        ForEach(visibleVolumes) { volume in bookTile(volume) }
                    }
                } else {
                    LazyVStack(spacing: 0) {
                        ForEach(visibleVolumes) { volume in
                            Button { open(volume) } label: {
                                HStack(alignment: .top, spacing: 16) {
                                    BookCover(volume: volume).frame(width: 64)
                                    VStack(alignment: .leading, spacing: 6) {
                                        Text(volume.title).font(.headline)
                                            .foregroundStyle(volume.isReaderAvailable ? Color.primary : Color.secondary)
                                        Text("\(volume.gaNumber) · \(volume.yearLabel)").font(.subheadline).foregroundStyle(.secondary)
                                        availability(volume)
                                    }
                                    Spacer(minLength: 0)
                                }.padding(.vertical, 16).contentShape(Rectangle())
                            }.buttonStyle(.plain).contextMenu { workActions(volume) }
                            Divider()
                        }
                    }
                }
            }.padding(24).frame(maxWidth: 1020, alignment: .leading).frame(maxWidth: .infinity)
        }
        .refreshable { await reloadCatalog() }
    }

    private var filterTitle: String {
        switch filter {
        case "reading": "Wird gelesen"
        case "want": "Möchte ich lesen"
        case "finished": "Gelesen"
        case "downloaded": "Offline verfügbar"
        case "updates": "Updates verfügbar"
        case "all": "Alle Werke"
        default: personal.collections.first(where: { $0.id == filter })?.name ?? "Alle Werke"
        }
    }

    private func bookTile(_ volume: GAVolume) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Button { open(volume) } label: {
                VStack(alignment: .leading, spacing: 10) {
                    BookCover(volume: volume)
                    Text(volume.title).font(.subheadline.weight(.medium)).fixedSize(horizontal: false, vertical: true)
                        .foregroundStyle(volume.isReaderAvailable ? Color.primary : Color.secondary)
                    if let position = personal.position(for: volume.id) {
                        ProgressView(value: position.fraction).accessibilityLabel("Lesefortschritt")
                    }
                }.contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("\(volume.title), \(volume.gaNumber)")
            .contextMenu { workActions(volume) }
            HStack {
                Text(volume.gaNumber).font(.caption).foregroundStyle(.secondary)
                Spacer(minLength: 0)
                Menu { workActions(volume) } label: {
                    Image(systemName: "ellipsis").frame(minWidth: 44, minHeight: 44)
                }
                .foregroundStyle(volume.isReaderAvailable ? Color.accentColor : Color.secondary)
                .accessibilityLabel("Aktionen für \(volume.title)")
            }
            availability(volume)
        }
    }

    private func availability(_ volume: GAVolume) -> some View {
        Group {
            if !volume.isReaderAvailable {
                Label("Coming soon", systemImage: "clock")
                    .font(.caption.weight(.medium)).foregroundStyle(.secondary)
                    .padding(.horizontal, 8).padding(.vertical, 5)
                    .background(.quaternary, in: Capsule())
                    .fixedSize(horizontal: false, vertical: true)
            } else if case .downloading = downloadStates[volume.id] {
                ProgressView().accessibilityLabel("Wird geladen")
            } else if updateAvailable(for: volume) {
                Label("Update verfügbar", systemImage: "arrow.down.circle")
                    .font(.caption.weight(.medium)).foregroundStyle(.tint)
                    .accessibilityIdentifier("book-update-available-\(volume.id)")
            } else {
                Label(volume.isReadable ? "Offline" : "Laden", systemImage: volume.isReadable ? "checkmark.circle" : "arrow.down.circle")
                    .font(.caption).foregroundStyle(.secondary).labelStyle(.titleAndIcon)
            }
        }
    }

    @ViewBuilder private func workActions(_ volume: GAVolume) -> some View {
        Button("Lesen", systemImage: "book") { open(volume) }
            .disabled(!volume.isReaderAvailable || (!volume.isReadable && downloadStates[volume.id]?.isDownloading == true))
        Button("Buchdetails", systemImage: "info.circle") { detailVolume = volume }
        Menu("Lesestatus", systemImage: "checkmark.circle") {
            Button("Ungelesen") { personal.setStatus(.unread, for: volume.id) }
            Button("Wird gelesen") { personal.setStatus(.reading, for: volume.id) }
            Button("Möchte ich lesen") { personal.setStatus(.wantToRead, for: volume.id) }
            Button("Gelesen") { personal.setStatus(.finished, for: volume.id) }
        }
        Menu("Zu Sammlung hinzufügen", systemImage: "folder") {
            ForEach(personal.collections) { collection in
                let included = collection.volumeIDs.contains(volume.id)
                Button(collection.name, systemImage: included ? "checkmark.circle.fill" : "circle") {
                    personal.setMembership(volumeID: volume.id, collectionID: collection.id, included: !included)
                }
            }
            Button("Neue Sammlung") { showsCollections = true }
        }
        if !volume.isReadable && volume.isDownloadable {
            Button("Für offline laden", systemImage: "arrow.down.circle") { Task { await download(volume) } }
                .disabled(downloadStates[volume.id]?.isDownloading == true)
        }
        if updateAvailable(for: volume) { updateButton(volume) }
        if volume.isReadable && !isBundled(volume.id) {
            Button("Download entfernen", systemImage: "trash", role: .destructive) { removeDownload(volume) }
        }
        ShareLink(item: "\(AppEdition.authorName): \(volume.title), \(volume.gaNumber).") {
            Label("Titel teilen", systemImage: "square.and.arrow.up")
        }
        EPUBShareLink(volume: volume) { errorMessage = "Das EPUB konnte nicht erstellt werden. \($0)" }
    }

    private var search: some View {
        List {
            if query.trimmingCharacters(in: .whitespacesAndNewlines).count < 2 {
                ContentUnavailableView(AppEdition.isSteiner ? "In der Gesamtausgabe suchen" : "\(AppEdition.authorShortName) durchsuchen", systemImage: "magnifyingglass", description: Text("Suche nach Titel, \(AppEdition.workNumberLabel) oder einer Textstelle. Auch deine Notizen werden durchsucht."))
            } else if searchInProgress {
                ProgressView("Texte durchsuchen …")
            } else if results.isEmpty {
                ContentUnavailableView.search(text: query)
            } else {
                ForEach(results) { hit in
                    let volume = volumes.first(where: { $0.id == hit.volumeID })
                    Button {
                        guard let volume else { return }
                        open(volume, passageID: hit.passageID, offset: hit.passageID == nil ? nil : hit.offset, searchText: hit.passageID == nil ? nil : query)
                    } label: {
                        VStack(alignment: .leading, spacing: 7) {
                            Text(hit.title).font(.headline)
                                .foregroundStyle(volume?.isReaderAvailable == false ? Color.secondary : Color.primary)
                            Text(hit.context).font(.caption).foregroundStyle(.secondary)
                            if !hit.excerpt.isEmpty {
                                Text(highlighted(hit.excerpt)).font(.subheadline).lineLimit(4)
                                    .foregroundStyle(volume?.isReaderAvailable == false ? Color.secondary : Color.primary)
                            }
                            if let volume, !volume.isReaderAvailable { availability(volume) }
                        }.padding(.vertical, 6).frame(minHeight: 44, alignment: .leading)
                    }.buttonStyle(.plain)
                }
            }
        }
        #if os(iOS)
        .searchable(text: $query, isPresented: $searchIsPresented, placement: .navigationBarDrawer(displayMode: .always), prompt: AppEdition.searchPrompt)
        #else
        .searchable(text: $query, isPresented: $searchIsPresented, placement: .toolbar, prompt: AppEdition.searchPrompt)
        #endif
        .task(id: SearchRequestKey(query: query, hasAccess: access.hasAccess, volumes: volumes, annotations: volumes.flatMap { personal.annotations(for: $0.id) })) {
            guard query.trimmingCharacters(in: .whitespacesAndNewlines).count >= 2 else { results = []; searchInProgress = false; return }
            searchInProgress = true
            do { try await Task.sleep(for: .milliseconds(220)) } catch { return }
            let works = access.hasAccess ? volumes : volumes.map { item in var metadata = item; metadata.passages = []; return metadata }
            let notes = volumes.flatMap { personal.annotations(for: $0.id) }
            let term = query
            let task = Task.detached(priority: .userInitiated) { LibrarySearch.find(term, in: works, annotations: notes) }
            let hits = await task.value
            guard !Task.isCancelled else { return }
            results = hits
            searchInProgress = false
        }
    }

    private func highlighted(_ text: String) -> AttributedString {
        var result = AttributedString(text)
        if let range = result.range(of: query, options: [.caseInsensitive, .diacriticInsensitive]) {
            result[range].font = .body.bold()
        }
        return result
    }

    private func bookDetails(_ selection: GAVolume) -> some View {
        let volume = volumes.first(where: { $0.id == selection.id }) ?? selection
        let isWorkingEdition = volume.isReaderAvailable && (
            (volume.publicationState != .published && volume.publicationState != .publishedSeed)
            || volume.proofingState == .needsAISanityCheck || volume.proofingState == .sourcePending
            || volume.sanityChecks.contains { $0.status == .warning }
        )
        return NavigationStack {
            List {
                Section {
                    HStack { Spacer(); BookCover(volume: volume).frame(width: 150); Spacer() }.listRowSeparator(.hidden)
                    Text(volume.title).font(.title2.bold()).accessibilityAddTraits(.isHeader)
                        .foregroundStyle(volume.isReaderAvailable ? Color.primary : Color.secondary)
                    Text("\(AppEdition.authorName) · \(volume.gaNumber) · \(volume.yearLabel)").foregroundStyle(.secondary)
                    if isWorkingEdition { Label("Arbeitsausgabe", systemImage: "doc.text.magnifyingglass") }
                    availability(volume)
                    if volume.isReaderAvailable {
                        Button(personal.position(for: volume.id) == nil ? "Lesen" : "Weiterlesen", systemImage: "book.fill") {
                            readingAfterDetails = OpenReading(volume: volume)
                            detailVolume = nil
                        }.frame(minHeight: 44)
                    } else {
                        Text("Für dieses Werk ist noch kein Lesetext verfügbar.").foregroundStyle(.secondary)
                    }
                    if volume.isDownloadable && !volume.isReadable {
                        Button("Für offline laden", systemImage: "arrow.down.circle") {
                            Task { await download(volume) }
                        }
                        .disabled(downloadStates[volume.id]?.isDownloading == true)
                        .frame(minHeight: 44)
                    }
                    if updateAvailable(for: volume) {
                        updateButton(volume).frame(minHeight: 44)
                        Text("Die gespeicherte Ausgabe bleibt bis zum erfolgreichen Download verfügbar.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                    EPUBShareLink(volume: volume) { detailExportError = "Das EPUB konnte nicht erstellt werden. \($0)" }
                        .frame(minHeight: 44)
                    if let detailExportError {
                        Text(detailExportError).font(.callout).foregroundStyle(.red)
                    }
                }
                Section("Inhalt") {
                    if volume.passages.isEmpty {
                        if let count = volume.catalogPassageCount, count > 0 {
                            Text("\(count) \(count == 1 ? "Abschnitt" : "Abschnitte") · nach dem Download verfügbar")
                                .foregroundStyle(.secondary)
                        } else {
                            Text(volume.isDownloadable ? "Die Abschnitte erscheinen nach dem Download." : "Der Lesetext wird vorbereitet.")
                                .foregroundStyle(.secondary)
                        }
                    }
                    ForEach(volume.passages) { passage in
                        Button(passage.title) {
                            readingAfterDetails = OpenReading(volume: volume, passageID: passage.id, offset: 0)
                            detailVolume = nil
                        }.frame(minHeight: 44, alignment: .leading)
                    }
                }
                Section {
                    DisclosureGroup("Über diese Ausgabe") {
                        if isWorkingEdition {
                            Text("Arbeitsausgabe. Eine vollständige Kollation mit der Originalquelle und die Prüfung des Originaltextumfangs stehen noch aus.")
                            if !volume.sourceSummary.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                                Text(volume.sourceSummary)
                            }
                            ForEach(volume.sanityChecks.filter { $0.status == .warning }) { check in
                                Text(check.detail)
                            }
                        } else if volume.isReaderAvailable {
                            Text("Originaltext von \(AppEdition.authorName). Die Leseausgabe enthält keine Herausgebertexte oder Verlagsmaterialien.")
                        } else {
                            Text("Für diesen Band wird eine Lesefassung vorbereitet.")
                        }
                        Text("Historische Seitenangaben beziehen sich auf die Textquelle und bleiben unabhängig von deiner Schriftgröße.")
                    }
                    if isBundled(volume.id) { Label("Auf diesem Gerät enthalten", systemImage: "checkmark.circle") }
                }
            }
            .navigationTitle("Buchdetails")
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Schließen") { detailVolume = nil } } }
        }.frame(minWidth: 300, idealWidth: 520, minHeight: 420)
        .alert("Aktion nicht abgeschlossen", isPresented: Binding(
            get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } }
        )) {
            Button("OK") { errorMessage = nil }
        } message: { Text(errorMessage ?? "") }
        .sheet(isPresented: $showsDetailAccess) { PurchaseScreen() }
    }

    private var collectionEditor: some View {
        NavigationStack {
            Form {
                Section("Neue Sammlung") {
                    TextField("Name", text: $newCollectionName).onSubmit(createCollection)
                    Button("Sammlung erstellen", systemImage: "folder.badge.plus", action: createCollection)
                        .disabled(newCollectionName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                Section("Deine Sammlungen") {
                    ForEach(personal.collections) { collection in
                        HStack {
                            VStack(alignment: .leading) {
                                Text(collection.name)
                                Text("\(collection.volumeIDs.count) Werke").font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button("Entfernen", systemImage: "trash", role: .destructive) {
                                personal.deleteCollection(id: collection.id)
                                if filter == collection.id { filter = "all" }
                            }.labelStyle(.iconOnly).frame(minWidth: 44, minHeight: 44)
                        }
                    }
                }
            }
            .navigationTitle("Sammlungen")
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { showsCollections = false } } }
        }.frame(minWidth: 300, idealWidth: 480, minHeight: 360)
    }

    private func createCollection() {
        guard !newCollectionName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        personal.createCollection(name: newCollectionName)
        newCollectionName = ""
    }

    private func readerSession(_ reading: OpenReading) -> some View {
        LibraryReaderSession(reading: reading, status: downloadStates[reading.volume.id] ?? .loaded(reading.volume.passages.count)) {
            Task { await download(reading.volume) }
        } onClose: { currentReading = nil; personal.flush() }
    }

    private func open(_ volume: GAVolume, passageID: String? = nil, offset: Int? = nil, searchText: String? = nil) {
        searchIsPresented = false
        guard volume.isReaderAvailable else {
            detailVolume = volume
            return
        }
        guard access.hasAccess else { showsAccess = true; return }
        guard volume.isReadable else {
            Task { await download(volume, openAfterwards: true, passageID: passageID, offset: offset, searchText: searchText) }
            return
        }
        let saved = personal.position(for: volume.id)
        currentReading = OpenReading(volume: volume, passageID: passageID ?? saved?.passageID ?? volume.passages.first?.id,
                                     offset: offset ?? (passageID == nil ? saved?.characterOffset : 0), searchText: searchText)
    }

    private func orderedWorks(_ ids: [String]) -> [GAVolume] {
        ids.compactMap { id in volumes.first { $0.id == id } }
    }

    private func isBundled(_ id: String) -> Bool {
        Self.bundledVolumes[id] != nil
    }

    private func updateAvailable(for volume: GAVolume) -> Bool {
        guard volume.hasContentUpdate, let server = serverEditions[volume.id] else { return false }
        // A packaged edition can be ahead of the public service during a release.
        // Offer only the edition the server can actually deliver.
        return server.catalogContentRevision == volume.catalogContentRevision
            && server.catalogContentFingerprint == volume.catalogContentFingerprint
    }

    private func updateButton(_ volume: GAVolume) -> some View {
        Button("Buch aktualisieren", systemImage: "arrow.down.circle") {
            Task { await download(volume) }
        }
        .disabled(downloadStates[volume.id]?.isDownloading == true)
        .accessibilityIdentifier("update-book-\(volume.id)")
    }

    private func restoreLibrary() {
        let cached = (try? LibraryCatalogCache.load()) ?? []
        volumes = hydrate(merge(SeedLibrary.readerVolumes, cached), previous: cached)
    }

    private func hydrate(_ works: [GAVolume], previous: [GAVolume]) -> [GAVolume] {
        let known = Dictionary(uniqueKeysWithValues: previous.map { ($0.id, $0) })
        return works.map { item in
            var volume = item
            volume.passages = []
            volume.downloadedPassageCount = nil
            volume.downloadedContentRevision = nil
            if let cached = try? LocalContentStore.loadEdition(for: item.id) {
                let prior = known[item.id]
                let priorWasComplete = prior?.publicationState != .publishedSeed
                    && prior?.contentCompleteness != .partial && prior?.contentCompleteness != .unavailable
                let trustedCount = priorWasComplete
                    ? prior?.downloadedPassageCount ?? prior?.catalogPassageCount : nil
                let expected = cached.isLegacy
                    ? trustedCount ?? volume.catalogPassageCount
                    : cached.passageCount
                if volume.isCompleteContent(cached.passages, expectedPassageCount: expected) {
                    volume.passages = cached.passages
                    volume.downloadedPassageCount = expected
                    volume.downloadedContentRevision = cached.contentRevision
                }
            }
            if let bundled = Self.bundledVolumes[item.id], bundled.isReadable,
               !volume.isReadable || (!volume.matchesCurrentEdition(volume.passages)
                    && volume.matchesCurrentEdition(bundled.passages, revision: bundled.downloadedContentRevision)) {
                volume.passages = bundled.passages
                volume.downloadedPassageCount = bundled.downloadedPassageCount
                volume.downloadedContentRevision = bundled.downloadedContentRevision
            }
            return volume
        }
    }

    private func merge(_ preferred: [GAVolume], _ fallback: [GAVolume]) -> [GAVolume] {
        let ids = Set(preferred.map(\.id))
        let alternatives = Dictionary(uniqueKeysWithValues: fallback.map { ($0.id, $0) })
        let newest = preferred.map { volume in
            guard let other = alternatives[volume.id] else { return volume }
            return volume.preferringNewerEdition(over: other)
        }
        return newest + fallback.filter { !ids.contains($0.id) }
    }

    @MainActor private func reloadCatalog(isAutomatic: Bool = false) async {
        guard !isLoadingCatalog, CatalogClient.isServerConfigured else { return }
        let now = Date()
        if isAutomatic, let lastCatalogRefresh, now.timeIntervalSince(lastCatalogRefresh) < 60 { return }
        lastCatalogRefresh = now
        isLoadingCatalog = true
        defer { isLoadingCatalog = false }
        do {
            let received = try await CatalogClient.fetchReaderCatalog()
            serverEditions = Dictionary(uniqueKeysWithValues: received.map { ($0.id, $0) })
            // Keep the complete packaged catalog and downloaded works when the
            // development server only has a subset of the public library.
            let fallback = merge(volumes, SeedLibrary.readerVolumes)
            volumes = hydrate(merge(received, fallback), previous: volumes)
            try LibraryCatalogCache.save(volumes)
            catalogMessage = nil
        } catch {
            catalogMessage = "Deine gespeicherte Bibliothek ist offline verfügbar."
        }
    }

    @MainActor private func download(_ volume: GAVolume, openAfterwards: Bool = false, passageID: String? = nil, offset: Int? = nil, searchText: String? = nil) async {
        guard volume.isDownloadable, let path = volume.contentPath else {
            errorMessage = "Für dieses Werk ist noch kein Lesetext verfügbar."
            return
        }
        guard access.hasAccess else {
            if detailVolume != nil { showsDetailAccess = true } else { showsAccess = true }
            return
        }
        guard downloadStates[volume.id]?.isDownloading != true else { return }
        downloadStates[volume.id] = .downloading
        do {
            let edition = try await CatalogClient.downloadEdition(path: path, for: volume.id,
                expectedPassageCount: volume.catalogPassageCount, expectedRevision: volume.catalogContentRevision)
            let passages = edition.passages
            guard volume.isCompleteContent(passages) else {
                throw CatalogClientError.unexpectedPassageCount
            }
            try LocalContentStore.save(passages: passages, for: volume.id, contentRevision: edition.contentRevision)
            if let index = volumes.firstIndex(where: { $0.id == volume.id }) {
                volumes[index].passages = passages
                volumes[index].downloadedPassageCount = passages.count
                volumes[index].downloadedContentRevision = edition.contentRevision
                downloadStates[volume.id] = .loaded(passages.count)
                try LibraryCatalogCache.save(volumes)
                if openAfterwards { open(volumes[index], passageID: passageID, offset: offset, searchText: searchText) }
            }
        } catch {
            downloadStates[volume.id] = .failed(error.localizedDescription)
            errorMessage = "Der Text konnte nicht geladen werden. \(error.localizedDescription)"
        }
    }

    private func removeDownload(_ volume: GAVolume) {
        do {
            try LocalContentStore.removePassages(for: volume.id)
            if let index = volumes.firstIndex(where: { $0.id == volume.id }) {
                volumes[index].passages = []
                volumes[index].downloadedPassageCount = nil
                volumes[index].downloadedContentRevision = nil
            }
            downloadStates[volume.id] = .idle
            try LibraryCatalogCache.save(volumes)
        } catch { errorMessage = error.localizedDescription }
    }
}

struct BookCover: View {
    let volume: GAVolume
    var body: some View {
        KutschereiBookCover(title: volume.title, gaLabel: volume.gaNumber)
            .saturation(volume.isReaderAvailable ? 1 : 0)
            .opacity(volume.isReaderAvailable ? 1 : 0.55)
            .shadow(color: .black.opacity(0.12), radius: 5, x: 0, y: 3)
            .accessibilityHidden(true)
    }
}

private struct LibraryReaderSession: View {
    let reading: OpenReading
    let status: ContentDownloadStatus
    let onDownload: () -> Void
    let onClose: () -> Void
    @State private var passageID: String?
    @Environment(AccessStore.self) private var access
    init(reading: OpenReading, status: ContentDownloadStatus, onDownload: @escaping () -> Void, onClose: @escaping () -> Void) {
        self.reading = reading; self.status = status; self.onDownload = onDownload; self.onClose = onClose
        _passageID = State(initialValue: reading.passageID)
    }
    var body: some View {
        NavigationStack {
            TimelineView(.periodic(from: .now, by: 30)) { _ in
                if access.hasAccess {
                    ReaderView(volume: reading.volume, passageID: $passageID, downloadStatus: status, onDownload: onDownload,
                               initialCharacterOffset: reading.offset, initialSearchText: reading.searchText)
                } else {
                    PurchaseScreen()
                }
            }
        }
        .onDisappear(perform: onClose)
    }
}

private enum LibraryCatalogCache {
    private static var url: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent(AppEdition.storageDirectory)
            .appendingPathComponent("reader-catalog.json")
    }
    static func load() throws -> [GAVolume] {
        guard FileManager.default.fileExists(atPath: url.path) else { return [] }
        return try JSONDecoder().decode([GAVolume].self, from: Data(contentsOf: url))
    }
    static func save(_ volumes: [GAVolume]) throws {
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        // Passage bodies have their own cache; keep catalog metadata small.
        let metadata = volumes.map { volume in var item = volume; item.passages = []; return item }
        try JSONEncoder().encode(metadata).write(to: url, options: .atomic)
    }
}

private struct SearchRequestKey: Equatable {
    let query: String
    let hasAccess: Bool
    let volumes: [GAVolume]
    let annotations: [PersonalAnnotation]
}

struct LibrarySearchHit: Identifiable, Sendable {
    var id: String
    var volumeID: String
    var passageID: String?
    var offset: Int
    var title: String
    var context: String
    var excerpt: String
}

enum LibrarySearch {
    nonisolated static func find(_ query: String, in volumes: [GAVolume], annotations: [PersonalAnnotation]) -> [LibrarySearchHit] {
        let term = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard term.count >= 2 else { return [] }
        if let reference = referenceLookup(term) {
            return volumes.flatMap { volume -> [LibrarySearchHit] in
                if let ga = reference.ga, volume.gaSortLabel != String(format: "%04d", ga) { return [] }
                guard let page = reference.page else {
                    return [LibrarySearchHit(id: "work:\(volume.id)", volumeID: volume.id, passageID: nil, offset: 0,
                                             title: volume.title, context: "\(volume.gaNumber) · Werk", excerpt: "")]
                }
                return volume.passages.filter { $0.metadata.pageNumbers.contains(page) }.map { passage in
                    LibrarySearchHit(id: "page:\(volume.id):\(passage.id):\(page)", volumeID: volume.id,
                                     passageID: passage.id, offset: 0, title: passage.title,
                                     context: "\(volume.gaNumber) · Quelle S. \(page)",
                                     excerpt: "Dieser Abschnitt enthält die Quellseite \(page).")
                }
            }
        }
        var results: [LibrarySearchHit] = []
        for volume in volumes {
            if volume.searchBlob.localizedStandardContains(term) {
                results.append(LibrarySearchHit(id: "work:\(volume.id)", volumeID: volume.id, passageID: nil, offset: 0,
                                              title: volume.title, context: "\(volume.gaNumber) · Werk", excerpt: ""))
            }
            for passage in volume.passages {
                let text = passage.text as NSString
                var searchRange = NSRange(location: 0, length: text.length)
                var count = 0
                while searchRange.length > 0 && count < 3 {
                    let range = text.range(of: term, options: [.caseInsensitive, .diacriticInsensitive], range: searchRange)
                    guard range.location != NSNotFound else { break }
                    let lower = max(0, range.location - 70)
                    let upper = min(text.length, NSMaxRange(range) + 140)
                    let contextRange = text.rangeOfComposedCharacterSequences(for: NSRange(location: lower, length: upper - lower))
                    let excerpt = (lower > 0 ? "… " : "") + text.substring(with: contextRange).replacingOccurrences(of: "\n", with: " ") + (upper < text.length ? " …" : "")
                    results.append(LibrarySearchHit(id: "text:\(volume.id):\(passage.id):\(range.location)", volumeID: volume.id,
                                                  passageID: passage.id, offset: range.location, title: passage.title,
                                                  context: "\(volume.gaNumber) · \(volume.title)", excerpt: excerpt))
                    searchRange = NSRange(location: NSMaxRange(range), length: text.length - NSMaxRange(range))
                    count += 1
                }
                if count == 0 && passage.title.localizedStandardContains(term) {
                    results.append(LibrarySearchHit(id: "chapter:\(passage.id)", volumeID: volume.id, passageID: passage.id, offset: 0,
                                                  title: passage.title, context: "\(volume.gaNumber) · Kapitel", excerpt: ""))
                }
            }
        }
        for note in annotations where (note.note + " " + note.quote).localizedStandardContains(term) {
            guard let volume = volumes.first(where: { $0.id == note.volumeID }) else { continue }
            results.insert(LibrarySearchHit(id: "note:\(note.id)", volumeID: note.volumeID, passageID: note.passageID,
                                           offset: note.location, title: note.isBookmark ? "Lesezeichen" : "Deine Notiz",
                                           context: "\(volume.gaNumber) · \(volume.title)", excerpt: note.note.isEmpty ? note.quote : note.note), at: 0)
        }
        return Array(results.prefix(100))
    }

    /// Source page numbers identify sections; they are not generated reader pages or precise per-line anchors.
    nonisolated private static func referenceLookup(_ term: String) -> (ga: Int?, page: Int?)? {
        let prefix = NSRegularExpression.escapedPattern(for: AppEdition.workPrefix)
        let pattern = "^(?:\(prefix)\\s*0*(\\d+)\\s*)?(?:(?:S\\.?|Seite)\\s*(\\d+))?$"
        guard let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive),
              let match = regex.firstMatch(in: term, range: NSRange(location: 0, length: (term as NSString).length)) else { return nil }
        let string = term as NSString
        func number(_ index: Int) -> Int? {
            let range = match.range(at: index)
            return range.location == NSNotFound ? nil : Int(string.substring(with: range))
        }
        let ga = number(1), page = number(2)
        return ga == nil && page == nil ? nil : (ga, page)
    }
}
