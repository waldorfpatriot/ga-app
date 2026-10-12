import SwiftUI

struct LibraryScreen: View {
    private let frontendMode = GAFrontendMode.current

    var body: some View {
        switch frontendMode {
        case .reader:
            ReadingLibraryView()
        case .developer:
            DeveloperOverviewScreen()
        }
    }
}

private enum GAFrontendMode {
    case reader
    case developer

    static var current: GAFrontendMode {
        switch ProcessInfo.processInfo.environment["GA_FRONTEND"]?.lowercased() {
        case "developer", "dev", "overview", "status":
            .developer
        default:
            .reader
        }
    }
}

private struct DeveloperOverviewScreen: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    #if os(iOS)
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    #endif
    @State private var catalogVolumes: [GAVolume] = SeedLibrary.developerVolumes.sorted { $0.gaSortLabel < $1.gaSortLabel }
    @State private var selectedVolumeID: GAVolume.ID?
    @State private var searchText = ""
    @State private var filter: DeveloperCatalogFilter = .all
    @State private var catalogState: CatalogLoadState = .loading
    @State private var hasLoadedOverview = false
    @State private var preferredCompactColumn: NavigationSplitViewColumn = .sidebar

    private var filteredVolumes: [GAVolume] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)

        return catalogVolumes.filter { volume in
            let matchesFilter = filter.includes(volume)
            let matchesQuery = query.isEmpty || volume.searchBlob.localizedCaseInsensitiveContains(query)
            return matchesFilter && matchesQuery
        }
    }

    private var selectedVolume: GAVolume? {
        filteredVolumes.first { $0.id == selectedVolumeID }
    }

    private var isCompactWidth: Bool {
        #if os(iOS)
        horizontalSizeClass != .regular
        #else
        false
        #endif
    }

    private var volumeSelection: Binding<GAVolume.ID?> {
        Binding(
            get: { selectedVolumeID },
            set: { volumeID in
                selectedVolumeID = volumeID
                if volumeID != nil {
                    preferredCompactColumn = .detail
                }
            }
        )
    }

    var body: some View {
        NavigationSplitView(preferredCompactColumn: $preferredCompactColumn) {
            List(selection: volumeSelection) {
                Section {
                    if catalogState.showsStatus {
                        CatalogStatusRow(state: catalogState, catalogName: "Developer catalog") {
                            Task { await reloadCatalog() }
                        }
                    }
                    DeveloperSummaryRow(volumes: catalogVolumes)
                }

                Section("Filter") {
                    if dynamicTypeSize.isAccessibilitySize {
                        statusPicker.pickerStyle(.menu)
                    } else {
                        statusPicker.pickerStyle(.segmented)
                    }
                }

                Section(AppEdition.isSteiner ? "Complete GA" : "Collected works") {
                    ForEach(filteredVolumes) { volume in
                        DeveloperVolumeRow(volume: volume)
                            .tag(Optional(volume.id))
                    }
                }
            }
            .navigationTitle(AppEdition.isSteiner ? "GA Overview" : "\(AppEdition.authorShortName) Overview")
            .searchable(text: $searchText, prompt: "Search \(AppEdition.workPrefix), title or topic")
            .refreshable {
                await reloadCatalog()
            }
            .overlay {
                if filteredVolumes.isEmpty {
                    ContentUnavailableView("No matching entries", systemImage: "line.3.horizontal.decrease.circle")
                }
            }
        } detail: {
            if let selectedVolume {
                DeveloperVolumeDetailView(volume: selectedVolume)
                    .navigationTitle(selectedVolume.gaNumber)
            } else {
                ContentUnavailableView(AppEdition.isSteiner ? "Select a GA entry" : "Select a work", systemImage: "list.bullet.rectangle")
            }
        }
        .onChange(of: searchText) { _, _ in
            ensureSelection()
        }
        .onChange(of: filter) { _, _ in
            ensureSelection()
        }
        .onChange(of: isCompactWidth) { _, _ in
            ensureSelection()
        }
        .task {
            guard !hasLoadedOverview else { return }
            hasLoadedOverview = true
            ensureSelection()
            await reloadCatalog()
        }
    }

    private var statusPicker: some View {
        Picker("Status", selection: $filter) {
            ForEach(DeveloperCatalogFilter.allCases) { filter in
                Text(filter.label).tag(filter)
            }
        }
    }

    @MainActor
    private func reloadCatalog() async {
        guard CatalogClient.isServerConfigured else {
            catalogState = .bundled
            ensureSelection()
            return
        }
        catalogState = .loading

        do {
            catalogVolumes = try await CatalogClient.fetchDeveloperCatalog()
            ensureSelection()
            catalogState = .server
        } catch {
            catalogVolumes = SeedLibrary.developerVolumes.sorted { $0.gaSortLabel < $1.gaSortLabel }
            ensureSelection()
            catalogState = .offlineSeed(error.localizedDescription)
        }
    }

    private func ensureSelection() {
        if let selectedVolumeID, filteredVolumes.contains(where: { $0.id == selectedVolumeID }) {
            return
        }

        if isCompactWidth {
            selectedVolumeID = nil
            preferredCompactColumn = .sidebar
        } else {
            selectedVolumeID = filteredVolumes.first?.id
        }
    }
}

private enum DeveloperCatalogFilter: String, CaseIterable, Identifiable {
    case all
    case readerReady
    case sanityCheck
    case importQueue

    var id: String { rawValue }

    var label: String {
        switch self {
        case .all: "All"
        case .readerReady: "Reader"
        case .sanityCheck: "Check"
        case .importQueue: "Queue"
        }
    }

    func includes(_ volume: GAVolume) -> Bool {
        switch self {
        case .all:
            true
        case .readerReady:
            volume.isReaderAvailable
        case .sanityCheck:
            volume.publicationState == .sanityCheck
        case .importQueue:
            volume.publicationState == .importQueue
        }
    }
}

private struct DeveloperVolumeRow: View {
    let volume: GAVolume

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(volume.gaNumber)
                    .font(.headline)
                Spacer()
                if volume.isReaderAvailable {
                    Image(systemName: "book")
                        .foregroundStyle(.tint)
                        .accessibilityLabel("Visible in reader")
                }
            }

            Text(volume.title)
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)

            AdaptiveStatusGroup {
                StatusPill(label: volume.publicationState.shortLabel)
                Text(volume.proofingState.displayName)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.vertical, 4)
    }
}

private struct DeveloperVolumeDetailView: View {
    let volume: GAVolume

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 12) {
                    Text(volume.title)
                        .font(.title2.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)

                    if !volume.subtitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        Text(volume.subtitle)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    AdaptiveStatusGroup {
                        StatusPill(label: volume.publicationState.shortLabel)
                        StatusPill(label: volume.proofingState.displayName)
                    }
                }
                .padding(.vertical, 4)
            }

            Section("Status") {
                LabeledContent(AppEdition.workPrefix, value: volume.gaNumber)
                LabeledContent("Type", value: volume.type.displayName)
                LabeledContent("Language", value: volume.languageCode.uppercased())
                if !volume.yearLabel.isEmpty {
                    LabeledContent("Year", value: volume.yearLabel)
                }
                LabeledContent("Reader app", value: volume.isReaderAvailable ? "Visible" : "Hidden")
                if let contentPath = volume.contentPath {
                    LabeledContent("Content", value: contentPath)
                }
                if let catalogPassageSummary = volume.catalogPassageSummary {
                    LabeledContent("Passages", value: catalogPassageSummary)
                }
            }

            Section("AI Sanity Checks") {
                if volume.sanityChecks.isEmpty {
                    Text("No checks recorded yet.")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(volume.sanityChecks) { check in
                        SanityCheckRow(check: check)
                    }
                }
            }

            Section("Source Status") {
                Text(volume.sourceSummary)
                    .foregroundStyle(.secondary)

                if volume.contentPath != nil {
                    NavigationLink {
                        ProofingDiffView(volume: volume)
                    } label: {
                        Label("Inspect source normalization", systemImage: "rectangle.split.2x1")
                    }
                }
            }

            if !volume.tags.isEmpty {
                Section("Tags") {
                    Text(volume.tags.joined(separator: ", "))
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}

private struct ProofingDiffView: View {
    let volume: GAVolume

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var passages: [GAPassage] = []
    @State private var selectedPassageID: GAPassage.ID?
    @State private var errorMessage: String?

    private var selectedPassage: GAPassage? {
        passages.first { $0.id == selectedPassageID } ?? passages.first
    }

    var body: some View {
        Group {
            if let passage = selectedPassage {
                GeometryReader { geometry in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 18) {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(passage.title)
                                    .font(.title2.weight(.semibold))
                                    .fixedSize(horizontal: false, vertical: true)
                                    .accessibilityAddTraits(.isHeader)
                                Text(diffSummary(for: passage))
                                    .font(.callout)
                                    .foregroundStyle(.secondary)
                            }

                            let layout = geometry.size.width >= 720 && !dynamicTypeSize.isAccessibilitySize
                                ? AnyLayout(HStackLayout(alignment: .top, spacing: 12))
                                : AnyLayout(VStackLayout(alignment: .leading, spacing: 12))
                            layout {
                                diffColumn(
                                    title: "Original source",
                                    text: passage.sourceText ?? "Original source was not retained.",
                                    color: .red
                                )
                                diffColumn(title: "Normalized reader text", text: passage.text, color: .green)
                            }
                        }
                        .padding()
                        .frame(maxWidth: 1400, alignment: .leading)
                        .frame(maxWidth: .infinity)
                    }
                }
            } else if let errorMessage {
                ContentUnavailableView(
                    "Could not load proofing data",
                    systemImage: "exclamationmark.triangle",
                    description: Text(errorMessage)
                )
            } else {
                ProgressView("Loading original and normalized text…")
            }
        }
        .navigationTitle("Normalization Diff")
        .toolbar {
            if !passages.isEmpty {
                ToolbarItem {
                    #if os(iOS)
                    Menu {
                        sectionPicker
                    } label: {
                        Label("Choose section", systemImage: "list.bullet")
                            .labelStyle(.iconOnly)
                            .frame(minWidth: 44, minHeight: 44)
                    }
                    .accessibilityValue(selectedPassage?.title ?? "")
                    #else
                    sectionPicker
                        .frame(minWidth: 220)
                    #endif
                }
            }
        }
        .task {
            await loadPassages()
        }
    }

    private var sectionPicker: some View {
        Picker("Section", selection: $selectedPassageID) {
            ForEach(passages) { passage in
                Text(passage.title).tag(Optional(passage.id))
            }
        }
    }

    private func diffColumn(title: String, text: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: title == "Original source" ? "doc" : "text.badge.checkmark")
                .font(.headline)

            Text(text)
                .font(.system(.body, design: .monospaced))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(12)
                .background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
        }
        .frame(maxWidth: .infinity, alignment: .topLeading)
    }

    private func diffSummary(for passage: GAPassage) -> String {
        let original = passage.sourceText ?? ""
        let removedPageMarkers = original.matches(of: /\[\d{1,4}\]/).count
        let originalLines = original.components(separatedBy: .newlines).count
        let normalizedLines = passage.text.components(separatedBy: .newlines).count
        return "\(removedPageMarkers) page markers moved to metadata · \(originalLines) source lines → \(normalizedLines) reader lines"
    }

    @MainActor
    private func loadPassages() async {
        guard passages.isEmpty, volume.contentPath != nil else { return }
        do {
            passages = try await CatalogClient.downloadPassages(
                path: "/api/developer/catalog/\(volume.id)/proofing"
            )
            selectedPassageID = passages.first?.id
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct DeveloperSummaryRow: View {
    let volumes: [GAVolume]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("\(volumes.count) \(AppEdition.isSteiner ? "GA entries" : "works")")
                .font(.headline)
            AdaptiveStatusGroup {
                Text("\(readerReadyCount) reader")
                Text("\(sanityCheckCount) check")
                Text("\(importQueueCount) queued")
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }

    private var readerReadyCount: Int {
        volumes.filter(\.isReaderAvailable).count
    }

    private var sanityCheckCount: Int {
        volumes.filter { $0.publicationState == .sanityCheck }.count
    }

    private var importQueueCount: Int {
        volumes.filter { $0.publicationState == .importQueue }.count
    }
}

private struct CatalogStatusRow: View {
    let state: CatalogLoadState
    let catalogName: String
    let onRetry: () -> Void

    var body: some View {
        switch state {
        case .loading:
            Label("Loading \(catalogName.lowercased())", systemImage: "arrow.clockwise")
                .font(.callout)
                .fixedSize(horizontal: false, vertical: true)
        case .server, .bundled:
            EmptyView()
        case .offlineSeed(let message):
            VStack(alignment: .leading, spacing: 8) {
                Label("Using saved library", systemImage: "wifi.exclamationmark")
                    .font(.callout)
                Text(message)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Button(action: onRetry) {
                    Label("Retry", systemImage: "arrow.clockwise")
                        .frame(minHeight: 44)
                }
            }
        }
    }
}

private struct SanityCheckRow: View {
    let check: GASanityCheck

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Image(systemName: iconName)
                .foregroundStyle(iconColor)
            VStack(alignment: .leading, spacing: 3) {
                Text(check.title)
                Text(check.detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityValue(check.status.rawValue)
    }

    private var iconName: String {
        switch check.status {
        case .passed: "checkmark.circle.fill"
        case .warning: "exclamationmark.triangle.fill"
        case .queued: "clock"
        }
    }

    private var iconColor: Color {
        switch check.status {
        case .passed: .green
        case .warning: .orange
        case .queued: .secondary
        }
    }
}

struct StatusPill: View {
    let label: String

    var body: some View {
        Text(label)
            .font(.caption.weight(.medium))
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(.thinMaterial, in: Capsule())
    }
}

private struct AdaptiveStatusGroup<Content: View>: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    private let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 6))
            : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 8))
        layout {
            content
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}

private enum CatalogLoadState: Equatable {
    case loading
    case server
    case bundled
    case offlineSeed(String)

    var showsStatus: Bool {
        switch self {
        case .loading, .offlineSeed: true
        case .server, .bundled: false
        }
    }
}
