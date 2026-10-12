import SwiftUI
#if os(iOS)
import UIKit
#else
import AppKit
#endif

struct ReaderView: View {
    let volume: GAVolume
    @Binding var passageID: GAPassage.ID?
    let downloadStatus: ContentDownloadStatus
    let onDownload: () -> Void
    var initialCharacterOffset: Int? = nil
    var initialSearchText: String? = nil

    @Environment(ReadingStore.self) private var readingStore
    @Environment(\.dismiss) private var dismiss
    @Environment(\.colorScheme) private var colorScheme
    @AppStorage("readerTheme") private var themeName = ReaderTheme.system.rawValue
    @AppStorage("readerFontDesign") private var fontDesign = "serif"
    @AppStorage("readerFontScale") private var fontScale = 1.0
    @AppStorage("readerLineSpacing") private var lineSpacing = 8.0
    @AppStorage("readerMargin") private var margin = 24.0
    @AppStorage("readerSourcePageNumbers") private var showsSourcePageNumbers = false
    @ScaledMetric(relativeTo: .body) private var bodySize: CGFloat = 19
    @State private var controlsVisible = true
    @State private var activeSheet: ReaderSheet?
    @State private var selectedSourceNote: GAAnnotation?
    @State private var selection = NSRange(location: 0, length: 0)
    @State private var characterOffset = 0
    @State private var anchor = ReaderAnchor(offset: 0)
    @State private var hasRestoredPosition = false
    @State private var searchText = ""
    @State private var annotationMenu: ReaderAnnotationPresentation?
    @State private var annotationMenuPage = ReaderAnnotationMenuPage.actions
    @State private var exportError: String?
    @State private var reportReceived = false
    @State private var showsReportConfirmation = false

    private var passage: GAPassage? {
        volume.passages.first(where: { $0.id == passageID }) ?? volume.passages.first
    }
    private var passageIndex: Int {
        volume.passages.firstIndex(where: { $0.id == passage?.id }) ?? 0
    }
    private var theme: ReaderTheme { ReaderTheme(rawValue: themeName) ?? .system }
    private var palette: ReaderPalette { theme.palette(systemDark: colorScheme == .dark) }
    private var progress: Double {
        guard let passage, !volume.passages.isEmpty else { return 0 }
        let length = max(1, (passage.text as NSString).length)
        return min(1, (Double(passageIndex) + Double(characterOffset) / Double(length)) / Double(volume.passages.count))
    }
    private var selectedQuote: String {
        guard let passage, selection.length > 0 else { return "" }
        let text = passage.text as NSString
        guard selection.location >= 0, NSMaxRange(selection) <= text.length else { return "" }
        return text.substring(with: selection)
    }
    private var citation: String {
        guard let passage else { return volume.title }
        var reference = "Rudolf Steiner: \(volume.title), \(volume.gaNumber), \(passage.title)"
        if let page = passage.metadata.pageNumberLabel ?? passage.gaPage { reference += ", \(page)" }
        return selectedQuote.isEmpty ? reference : "„\(selectedQuote)“\n\n\(reference)"
    }
    private var currentBookmark: PersonalAnnotation? {
        guard let passage else { return nil }
        return readingStore.annotations(for: volume.id, passageID: passage.id)
            .first { $0.isBookmark && abs($0.location - characterOffset) < 160 }
    }

    var body: some View {
        Group {
            if let passage {
                NativeReadingText(
                    passage: passage,
                    volumeTitle: volume.title,
                    languageCode: volume.languageCode,
                    settings: ReaderTextSettings(
                        fontSize: bodySize * fontScale,
                        serif: fontDesign == "serif",
                        lineSpacing: lineSpacing,
                        margin: margin,
                        showsPages: showsSourcePageNumbers,
                        palette: palette
                    ),
                    annotations: readingStore.annotations(for: volume.id, passageID: passage.id),
                    searchText: searchText,
                    anchor: anchor,
                    onPosition: { offset in recordPosition(offset, for: passage.id) },
                    onSelection: { range in
                        if self.passage?.id == passage.id { selection = range }
                    },
                    onToggleControls: {
                        if annotationMenu != nil { dismissAnnotationMenu() }
                        else { withAnimation(.easeInOut(duration: 0.2)) { controlsVisible.toggle() } }
                    },
                    onSourceNote: { dismissAnnotationMenu(); selectedSourceNote = $0 },
                    onAnnotationTap: { id, context in
                        showAnnotationMenu(id: id, context: context, page: .actions)
                    },
                    onSelectionAction: { action, context in
                        switch action {
                        case .marking: showAnnotationMenu(context: context, page: .marking)
                        case .note: editNote(context: context)
                        case .search: searchSelection(context: context)
                        case .reportError: reportError(context: context)
                        }
                    },
                    onInteractionDismiss: { dismissAnnotationMenu() }
                )
                .id(passage.id)
                .overlay { annotationMenuAnchor }
                .safeAreaInset(edge: .top, spacing: 0) {
                    if controlsVisible { topControls }
                }
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    if controlsVisible { bottomControls }
                }
                .overlay(alignment: .topTrailing) {
                    if !controlsVisible {
                        Button {
                            withAnimation { controlsVisible = true }
                        } label: {
                            Image(systemName: "ellipsis")
                                .frame(width: 44, height: 44)
                                .background(.regularMaterial, in: Circle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Lesesteuerung einblenden")
                        .padding(12)
                    }
                }
            } else {
                downloadView
            }
        }
        .background(palette.background)
        .foregroundStyle(palette.foreground)
        .tint(palette.accent)
        .navigationTitle(volume.gaNumber)
        #if os(iOS)
        .toolbar(.hidden, for: .navigationBar)
        #endif
        .environment(\.colorScheme, theme.colorScheme ?? colorScheme)
        .sheet(item: $activeSheet, onDismiss: {
            if reportReceived {
                reportReceived = false
                showsReportConfirmation = true
            }
        }) { sheet in sheetContent(sheet) }
        .alert("Meldung gesendet", isPresented: $showsReportConfirmation) {
            Button("OK", role: .cancel) {}
        } message: {
            Text("Danke! Deine Meldung zur markierten Textstelle ist eingegangen.")
        }
        .alert("EPUB konnte nicht erstellt werden", isPresented: Binding(
            get: { exportError != nil }, set: { if !$0 { exportError = nil } }
        )) {
            Button("OK") { exportError = nil }
        } message: { Text(exportError ?? "") }
        .popover(item: $selectedSourceNote) { note in
            SourceAnnotationPopover(annotation: note, languageCode: volume.languageCode)
        }
        .onAppear { restorePosition() }
        .onDisappear { DispatchQueue.main.async { readingStore.flush() } }
        .onChange(of: passage?.id) {
            dismissAnnotationMenu()
            selection = NSRange(location: 0, length: 0)
            selectedSourceNote = nil
            if hasRestoredPosition { recordPosition(anchor.offset) }
            else { restorePosition() }
        }
    }

    private var topControls: some View {
        HStack(spacing: 12) {
            Button { dismiss() } label: { Image(systemName: "chevron.down").readerControl() }
                .accessibilityLabel("Buch schließen")
            VStack(alignment: .leading, spacing: 2) {
                Text(volume.gaNumber).font(.caption).foregroundStyle(.secondary)
                Text(volume.title).font(.subheadline.weight(.medium)).lineLimit(1)
            }
            Spacer(minLength: 0)
            Button { activeSheet = .contents } label: { Image(systemName: "list.bullet").readerControl() }
                .accessibilityLabel("Inhaltsverzeichnis")
            Button { activeSheet = .settings } label: { Image(systemName: "textformat.size").readerControl() }
                .accessibilityLabel("Leseeinstellungen")
            Menu {
                Button("Im Buch suchen", systemImage: "magnifyingglass") { activeSheet = .search }
                Button(currentBookmark == nil ? "Lesezeichen setzen" : "Lesezeichen entfernen", systemImage: currentBookmark == nil ? "bookmark" : "bookmark.fill") { toggleBookmark() }
                Button("Markierungen und Notizen", systemImage: "pencil.and.list.clipboard") { activeSheet = .annotations }
                if let passage, !passage.metadata.annotations.isEmpty {
                    Button("Anmerkungen der Ausgabe", systemImage: "text.bubble") { activeSheet = .sourceNotes }
                }
                ShareLink(item: citation) { Label("Zitat teilen", systemImage: "square.and.arrow.up") }
                EPUBShareLink(volume: volume) { exportError = $0 }
                Button("Quellenangabe kopieren", systemImage: "doc.on.doc") { copyCitation() }
                if !searchText.isEmpty {
                    Button("Suchmarkierungen ausblenden", systemImage: "xmark.circle") { searchText = "" }
                }
                Button("Als gelesen markieren", systemImage: "checkmark.circle") { readingStore.setStatus(.finished, for: volume.id) }
            } label: { Image(systemName: "ellipsis.circle").readerControl() }
            .accessibilityLabel("Weitere Leseoptionen")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 4)
        .background(.regularMaterial)
    }

    private var bottomControls: some View {
        HStack(spacing: 12) {
            Button { goToPassage(index: passageIndex - 1) } label: { Image(systemName: "chevron.left").readerControl() }
                .disabled(passageIndex == 0)
                .accessibilityLabel("Vorheriger Abschnitt")
            VStack(spacing: 4) {
                Text("Abschnitt \(passageIndex + 1) von \(volume.passages.count)")
                    .font(.caption).foregroundStyle(.secondary)
                ProgressView(value: progress)
                    .accessibilityLabel("Lesefortschritt")
                    .accessibilityValue("\(Int(progress * 100)) Prozent")
            }
            Text(progress, format: .percent.precision(.fractionLength(0)))
                .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
            Button { goToPassage(index: passageIndex + 1) } label: { Image(systemName: "chevron.right").readerControl() }
                .disabled(passageIndex + 1 >= volume.passages.count)
                .accessibilityLabel("Nächster Abschnitt")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 4)
        .background(.regularMaterial)
    }

    @ViewBuilder private var annotationMenuAnchor: some View {
        GeometryReader { geometry in
            if let menu = annotationMenu {
                let point = CGPoint(
                    x: min(max(menu.context.rect.midX, 24), max(24, geometry.size.width - 24)),
                    y: min(max(menu.context.rect.minY, 12), max(12, geometry.size.height - 12))
                )
                Color.clear
                    .frame(width: 1, height: 1)
                    .popover(isPresented: Binding(
                        get: { annotationMenu != nil },
                        set: { if !$0 { dismissAnnotationMenu() } }
                    ), attachmentAnchor: .point(.top), arrowEdge: .bottom) {
                        ReaderAnnotationMenu(
                            page: $annotationMenuPage,
                            annotation: annotation(for: menu.context, id: menu.annotationID),
                            canUseWritingTools: menu.context.showWritingTools != nil,
                            onColor: { applyMarking(color: $0, style: .highlight) },
                            onUnderline: { applyMarking(style: .underline) },
                            onNote: { editNote(context: menu.context, id: menu.annotationID) },
                            onRemove: { removeMarking(menu) },
                            onSearch: { searchSelection(context: menu.context) },
                            onReportError: { reportError(context: menu.context) },
                            onWritingTools: {
                                let action = menu.context.showWritingTools
                                dismissAnnotationMenu()
                                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { action?() }
                            }
                        )
                        .presentationCompactAdaptation(.popover)
                        .presentationBackground(.regularMaterial)
                    }
                    .position(point)
            }
        }
        .allowsHitTesting(annotationMenu != nil)
    }

    @ViewBuilder private func sheetContent(_ sheet: ReaderSheet) -> some View {
        switch sheet {
        case .settings:
            ReaderSettingsSheet(theme: $themeName, fontDesign: $fontDesign, fontScale: $fontScale,
                                lineSpacing: $lineSpacing, margin: $margin, showsPages: $showsSourcePageNumbers)
        case .contents:
            ReaderContentsSheet(volume: volume, selectedPassageID: passage?.id, selectedOffset: characterOffset) { selected, offset in
                jump(to: selected.id, offset: offset)
                activeSheet = nil
            }
        case .annotations:
            ReaderAnnotationsSheet(volume: volume, annotations: readingStore.annotations(for: volume.id), onJump: { item in
                jump(to: item.passageID, offset: item.location)
                activeSheet = nil
            }, onEdit: { activeSheet = .editAnnotation($0) }, onDelete: { readingStore.removeAnnotation(id: $0.id) })
        case .sourceNotes:
            SourceAnnotationList(annotations: passage?.metadata.annotations ?? [], languageCode: volume.languageCode)
        case .search:
            ReaderSearchSheet(volume: volume, initialQuery: searchText) { result, query in
                searchText = query
                jump(to: result.passageID, offset: result.location)
                activeSheet = nil
            }
        case .editAnnotation(let annotation):
            ReaderNoteEditor(annotation: annotation) { edited in
                readingStore.saveAnnotation(edited)
                activeSheet = nil
            }
        case .textReport(let report):
            ReaderTextReportSheet(report: report, reference: "\(volume.gaNumber) · \(report.sectionTitle ?? volume.title)") {
                reportReceived = true
                activeSheet = nil
            }
        }
    }

    private func restorePosition() {
        guard !hasRestoredPosition, let first = volume.passages.first else { return }
        hasRestoredPosition = true
        searchText = initialSearchText ?? ""
        if let initialCharacterOffset {
            jump(to: passage?.id ?? first.id, offset: initialCharacterOffset)
        } else if let saved = readingStore.position(for: volume.id),
                  passageID == nil || passageID == saved.passageID,
                  volume.passages.contains(where: { $0.id == saved.passageID }) {
            jump(to: saved.passageID, offset: saved.characterOffset)
        } else {
            jump(to: passage?.id ?? first.id, offset: 0)
        }
    }

    private func recordPosition(_ offset: Int, for expectedPassageID: String? = nil) {
        guard hasRestoredPosition, let passage, expectedPassageID == nil || expectedPassageID == passage.id else { return }
        characterOffset = min(max(0, offset), (passage.text as NSString).length)
        readingStore.recordPosition(volumeID: volume.id, passageID: passage.id,
                                    characterOffset: characterOffset, fraction: progress)
    }

    private func jump(to id: String, offset: Int) {
        characterOffset = max(0, offset)
        anchor = ReaderAnchor(offset: characterOffset)
        passageID = id
        dismissAnnotationMenu()
        selection = NSRange(location: 0, length: 0)
        recordPosition(characterOffset, for: id)
    }

    private func goToPassage(index: Int) {
        guard volume.passages.indices.contains(index) else { return }
        jump(to: volume.passages[index].id, offset: 0)
    }

    private func newAnnotation(color: HighlightColor, bookmark: Bool = false) -> PersonalAnnotation {
        if !bookmark, let passage,
           let existing = readingStore.annotations(for: volume.id, passageID: passage.id).first(where: {
               !$0.isBookmark && $0.location == selection.location && $0.length == selection.length && $0.quote == selectedQuote
           }) {
            return existing
        }
        return PersonalAnnotation(id: UUID().uuidString, volumeID: volume.id, passageID: passage?.id ?? "",
                                  location: bookmark ? characterOffset : selection.location,
                                  length: bookmark ? 0 : selection.length,
                                  quote: bookmark ? bookmarkQuote() : selectedQuote,
                                  note: "", color: color, isBookmark: bookmark, updatedAt: Date())
    }

    private func showAnnotationMenu(id: String? = nil, context: ReaderTextContext, page: ReaderAnnotationMenuPage) {
        guard context.range.length > 0 else { return }
        selection = context.range
        annotationMenuPage = page
        var annotationID = id
        if page == .marking, let item = annotation(for: context, id: id) {
            if !readingStore.annotations(for: volume.id).contains(where: { $0.id == item.id }) {
                readingStore.saveAnnotation(item)
            }
            annotationID = item.id
            context.clearSelection()
        }
        annotationMenu = ReaderAnnotationPresentation(annotationID: annotationID, context: context)
    }

    private func dismissAnnotationMenu() {
        guard annotationMenu != nil else { return }
        let context = annotationMenu?.context
        annotationMenu = nil
        selection = NSRange(location: 0, length: 0)
        context?.clearSelection()
    }

    private func annotation(for context: ReaderTextContext, id: String? = nil) -> PersonalAnnotation? {
        guard let passage, context.range.location >= 0, context.range.length > 0,
              NSMaxRange(context.range) <= (passage.text as NSString).length else { return nil }
        let quote = (passage.text as NSString).substring(with: context.range)
        let annotations = readingStore.annotations(for: volume.id, passageID: passage.id)
        if let existing = annotations.first(where: { !$0.isBookmark && $0.id == id }) { return existing }
        if let existing = annotations.first(where: {
            !$0.isBookmark && $0.location == context.range.location && $0.length == context.range.length && $0.quote == quote
        }) { return existing }
        return PersonalAnnotation(id: UUID().uuidString, volumeID: volume.id, passageID: passage.id,
                                  location: context.range.location, length: context.range.length,
                                  quote: quote, note: "", color: .yellow, isBookmark: false, updatedAt: Date())
    }

    private func applyMarking(color: HighlightColor? = nil, style: AnnotationStyle) {
        guard let menu = annotationMenu,
              var item = annotation(for: menu.context, id: menu.annotationID) else { return }
        if let color { item.color = color }
        item.style = style
        readingStore.saveAnnotation(item)
        annotationMenu?.annotationID = item.id
    }

    private func editNote(context: ReaderTextContext, id: String? = nil) {
        guard let item = annotation(for: context, id: id) else { return }
        dismissAnnotationMenu()
        context.clearSelection()
        activeSheet = .editAnnotation(item)
    }

    private func removeMarking(_ menu: ReaderAnnotationPresentation) {
        if let id = menu.annotationID { readingStore.removeAnnotation(id: id) }
        else if let item = annotation(for: menu.context), readingStore.annotations(for: volume.id).contains(where: { $0.id == item.id }) {
            readingStore.removeAnnotation(id: item.id)
        }
        dismissAnnotationMenu()
    }

    private func searchSelection(context: ReaderTextContext) {
        guard let quote = annotation(for: context)?.quote else { return }
        dismissAnnotationMenu()
        context.clearSelection()
        searchText = quote
        activeSheet = .search
    }

    private func reportError(context: ReaderTextContext) {
        guard let passage, let quote = annotation(for: context)?.quote,
              !quote.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        let report = TextReportRequest(bookID: volume.id, sectionID: passage.id, sectionTitle: passage.title,
            selectedText: quote, selectionStart: context.range.location, selectionEnd: NSMaxRange(context.range))
        dismissAnnotationMenu()
        context.clearSelection()
        activeSheet = .textReport(report)
    }

    private func bookmarkQuote() -> String {
        guard let text = passage?.text as NSString? else { return "" }
        let start = min(characterOffset, text.length)
        let range = text.rangeOfComposedCharacterSequences(for: NSRange(location: start, length: min(120, text.length - start)))
        return text.substring(with: range)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func copyCitation() {
        #if os(iOS)
        UIPasteboard.general.string = citation
        #else
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(citation, forType: .string)
        #endif
    }

    private func toggleBookmark() {
        if let bookmark = currentBookmark { readingStore.removeAnnotation(id: bookmark.id) }
        else { readingStore.saveAnnotation(newAnnotation(color: .yellow, bookmark: true)) }
    }

    private var downloadView: some View {
        ContentUnavailableView {
            Label(downloadTitle, systemImage: "tray.and.arrow.down")
        } description: {
            Text(downloadDescription)
        } actions: {
            if case .downloading = downloadStatus { ProgressView() }
            else if volume.isDownloadable {
                Button("Volltext herunterladen", systemImage: "arrow.down.doc", action: onDownload)
            }
            Button("Schließen") { dismiss() }
        }
    }
    private var downloadTitle: String {
        if !volume.isDownloadable { return "Text nicht verfügbar" }
        switch downloadStatus {
        case .failed: return "Download fehlgeschlagen"
        case .downloading: return "Buch wird geladen"
        default: return "Bereit zum Lesen"
        }
    }
    private var downloadDescription: String {
        switch downloadStatus {
        case .failed(let message): return message
        case .downloading: return "Der Volltext wird für das Offline-Lesen gespeichert."
        default: return volume.isDownloadable ? "Lade das Buch herunter, um es auch offline zu lesen." : "Für dieses Werk ist noch kein Lesetext verfügbar."
        }
    }
}

private extension Image {
    func readerControl() -> some View { frame(width: 44, height: 44).contentShape(Rectangle()) }
}

private enum ReaderSheet: Identifiable {
    case settings, contents, annotations, sourceNotes, search
    case editAnnotation(PersonalAnnotation)
    case textReport(TextReportRequest)
    var id: String {
        switch self {
        case .settings: "settings"
        case .contents: "contents"
        case .annotations: "annotations"
        case .sourceNotes: "sourceNotes"
        case .search: "search"
        case .editAnnotation(let annotation): "edit-\(annotation.id)"
        case .textReport(let report): "report-\(report.id)"
        }
    }
}

private enum ReaderTheme: String, CaseIterable, Identifiable {
    case system, light, cream, dark
    var id: String { rawValue }
    var title: String {
        switch self { case .system: "Automatisch"; case .light: "Hell"; case .cream: "Papier"; case .dark: "Dunkel" }
    }
    var colorScheme: ColorScheme? {
        switch self { case .system: nil; case .light, .cream: .light; case .dark: .dark }
    }
    func palette(systemDark: Bool) -> ReaderPalette {
        let isDark = self == .dark || (self == .system && systemDark)
        if isDark { return ReaderPalette(background: Color(red: 0.09, green: 0.09, blue: 0.10), foreground: Color(red: 0.89, green: 0.88, blue: 0.85), accent: Color(red: 0.93, green: 0.65, blue: 0.34), dark: true) }
        if self == .cream { return ReaderPalette(background: Color(red: 0.97, green: 0.94, blue: 0.86), foreground: Color(red: 0.22, green: 0.19, blue: 0.15), accent: Color(red: 0.53, green: 0.30, blue: 0.10), dark: false) }
        return ReaderPalette(background: .white, foreground: Color(red: 0.12, green: 0.12, blue: 0.13), accent: Color(red: 0.66, green: 0.32, blue: 0.10), dark: false)
    }
}

struct ReaderPalette {
    var background: Color
    var foreground: Color
    var accent: Color
    var dark: Bool
}

extension HighlightColor {
    var readerColor: Color {
        switch self { case .yellow: .yellow; case .green: .green; case .blue: .blue; case .pink: .pink; case .purple: .purple }
    }
    var readerLabel: String {
        switch self { case .yellow: "Gelb"; case .green: "Grün"; case .blue: "Blau"; case .pink: "Rosa"; case .purple: "Violett" }
    }
}

private struct ReaderSettingsSheet: View {
    @Binding var theme: String
    @Binding var fontDesign: String
    @Binding var fontScale: Double
    @Binding var lineSpacing: Double
    @Binding var margin: Double
    @Binding var showsPages: Bool
    @Environment(\.dismiss) private var dismiss
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ScaledMetric(relativeTo: .body) private var previewBodySize: CGFloat = 19

    var body: some View {
        NavigationStack {
            Form {
                Section("Vorschau") {
                    let palette = (ReaderTheme(rawValue: theme) ?? .system).palette(systemDark: colorScheme == .dark)
                    Text("Ein gutes Buch öffnet eine Welt. Nimm dir Zeit, in Ruhe zu lesen.")
                        .font(.system(size: previewBodySize * fontScale, design: fontDesign == "serif" ? .serif : .default))
                        .lineSpacing(lineSpacing)
                        .padding(.horizontal, margin)
                        .padding(.vertical, 20)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .foregroundStyle(palette.foreground)
                        .background(palette.background, in: RoundedRectangle(cornerRadius: 12))
                }
                Section("Darstellung") {
                    if dynamicTypeSize.isAccessibilitySize {
                        themePicker.pickerStyle(.menu)
                        fontPicker.pickerStyle(.menu)
                    } else {
                        themePicker.pickerStyle(.segmented)
                        fontPicker.pickerStyle(.segmented)
                    }
                }
                Section("Text") {
                    LabeledContent("Schriftgröße", value: "\(Int(fontScale * 100)) %")
                    Slider(value: $fontScale, in: 0.8...2, step: 0.05).accessibilityLabel("Schriftgröße")
                    LabeledContent("Zeilenabstand", value: "\(Int(lineSpacing))")
                    Slider(value: $lineSpacing, in: 2...18, step: 1).accessibilityLabel("Zeilenabstand")
                    LabeledContent("Seitenrand", value: "\(Int(margin))")
                    Slider(value: $margin, in: 16...64, step: 4).accessibilityLabel("Seitenrand")
                    Toggle("Originalseiten anzeigen", isOn: $showsPages)
                }
                Section {
                    Text("Die Änderungen erscheinen direkt im Buch. Deine Lesestelle bleibt erhalten.")
                        .font(.footnote).foregroundStyle(.secondary)
                    Button("Standard wiederherstellen") {
                        theme = ReaderTheme.system.rawValue
                        fontDesign = "serif"
                        fontScale = 1
                        lineSpacing = 8
                        margin = 24
                    }
                }
            }
            .formStyle(.grouped)
            .navigationTitle("Leseeinstellungen")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
        }
        .frame(minWidth: 300, idealWidth: 480, minHeight: 400)
        #if os(iOS)
        .presentationDetents(dynamicTypeSize.isAccessibilitySize ? [.large] : [.medium, .large])
        #endif
    }

    private var themePicker: some View {
        Picker("Thema", selection: $theme) {
            ForEach(ReaderTheme.allCases) { Text($0.title).tag($0.rawValue) }
        }
        .accessibilityIdentifier("reader-theme")
    }
    private var fontPicker: some View {
        Picker("Schrift", selection: $fontDesign) {
            Text("Serif").tag("serif")
            Text("Sans Serif").tag("sans")
        }
        .accessibilityIdentifier("reader-font")
    }
}

private struct ReaderContentsSheet: View {
    let volume: GAVolume
    let selectedPassageID: String?
    var selectedOffset: Int = 0
    let onSelect: (GAPassage, Int) -> Void
    @Environment(\.dismiss) private var dismiss

    private struct ContentsGroup: Identifiable {
        var id: Int
        var title: String?
        var passages: [GAPassage]
    }

    private var groups: [ContentsGroup] {
        var result: [ContentsGroup] = []
        for (index, passage) in volume.passages.enumerated() {
            let title = passage.metadata.groupTitle
            if result.last?.title != title || result.isEmpty {
                result.append(ContentsGroup(id: index, title: title, passages: []))
            }
            result[result.count - 1].passages.append(passage)
        }
        return result
    }

    var body: some View {
        NavigationStack {
            List {
                ForEach(groups) { group in
                    Section {
                        ForEach(group.passages) { passage in
                            let units = passage.contentsUnits
                            if !units.isEmpty {
                                let activeUnit = passage.contentsUnit(at: selectedOffset)
                                ForEach(units) { unit in
                                    passageRow(passage: passage, title: unit.title, offset: unit.startOffset,
                                        pages: passage.pageNumberLabel(for: unit),
                                        isActive: passage.id == selectedPassageID && unit.id == activeUnit?.id)
                                    if !unit.headings.isEmpty {
                                        headingRows(passage: passage, headings: unit.headings)
                                    }
                                }
                            } else {
                                passageRow(passage: passage, title: passage.title, offset: 0,
                                    pages: passage.metadata.pageNumberLabel ?? passage.gaPage, isActive: passage.id == selectedPassageID)
                                if !passage.contentsHeadings.isEmpty {
                                    if passage.hasCalendarContents {
                                        headingRows(passage: passage, headings: passage.contentsHeadings)
                                    } else {
                                        DisclosureGroup("Unterabschnitte") {
                                            headingRows(passage: passage, headings: passage.contentsHeadings)
                                        }
                                        .font(.subheadline)
                                    }
                                }
                            }
                        }
                    } header: {
                        if let title = group.title { Text(title) }
                    }
                }
            }
            .navigationTitle("Inhaltsverzeichnis")
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
        }.frame(minWidth: 300, idealWidth: 500, minHeight: 420)
    }

    private func passageRow(passage: GAPassage, title: String, offset: Int, pages: String?, isActive: Bool) -> some View {
        Button { onSelect(passage, offset) } label: {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(title).foregroundStyle(.primary)
                    if let pages {
                        Text(pages).font(.caption).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                if isActive { Image(systemName: "book.fill").accessibilityLabel("Aktueller Abschnitt") }
            }.padding(.vertical, 6)
        }.buttonStyle(.plain)
    }

    private func headingRows(passage: GAPassage, headings: [GAContentsHeading]) -> some View {
        ForEach(headings) { heading in
            Button { onSelect(passage, heading.startOffset) } label: {
                VStack(alignment: .leading, spacing: 4) {
                    Text(heading.title)
                        .font(heading.isSeason ? .headline : .body)
                        .foregroundStyle(.primary)
                    if let subtitle = heading.subtitle {
                        Text(subtitle).font(.caption).foregroundStyle(.secondary)
                    }
                }
                .padding(.leading, CGFloat(max(0, heading.level - 1)) * 16)
                .padding(.vertical, heading.isSeason ? 5 : 2)
            }.buttonStyle(.plain)
        }
    }
}

private struct ReaderAnnotationsSheet: View {
    let volume: GAVolume
    let annotations: [PersonalAnnotation]
    let onJump: (PersonalAnnotation) -> Void
    let onEdit: (PersonalAnnotation) -> Void
    let onDelete: (PersonalAnnotation) -> Void
    @State private var filter = 0
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    private var visible: [PersonalAnnotation] {
        annotations.filter { filter == 0 || (filter == 1 ? $0.isBookmark : !$0.isBookmark) }
    }
    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if dynamicTypeSize.isAccessibilitySize {
                    annotationFilter.pickerStyle(.menu).padding()
                } else {
                    annotationFilter.pickerStyle(.segmented).padding()
                }
                if visible.isEmpty {
                    ContentUnavailableView("Noch keine Notizen", systemImage: "pencil.and.list.clipboard", description: Text("Wähle Text im Buch aus, um ihn zu markieren oder eine persönliche Notiz hinzuzufügen."))
                } else {
                    List(visible) { item in
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Image(systemName: item.isBookmark ? "bookmark.fill" : (item.style == .underline ? "underline" : "highlighter"))
                                    .foregroundStyle(item.color.readerColor)
                                    .accessibilityLabel(item.isBookmark ? "Lesezeichen" : item.style.displayName)
                                Text(volume.passages.first(where: { $0.id == item.passageID })?.title ?? "Abschnitt")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            Button { onJump(item) } label: {
                                Text(item.quote.isEmpty ? "Zur Lesestelle" : item.quote)
                                    .underline(!item.isBookmark && item.style == .underline, color: item.color.readerColor)
                                    .lineLimit(5).fixedSize(horizontal: false, vertical: true).foregroundStyle(.primary)
                            }.buttonStyle(.plain)
                            if !item.note.isEmpty { Text(item.note).font(.subheadline).foregroundStyle(.secondary) }
                            if dynamicTypeSize.isAccessibilitySize {
                                VStack(alignment: .leading) { annotationActions(item) }
                            } else {
                                HStack { annotationActions(item) }.labelStyle(.iconOnly)
                            }
                        }.padding(.vertical, 8)
                    }
                }
            }
            .navigationTitle("Markierungen und Notizen")
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
        }.frame(minWidth: 320, idealWidth: 520, minHeight: 420)
    }
    @ViewBuilder private func annotationActions(_ item: PersonalAnnotation) -> some View {
        Button { onJump(item) } label: {
            Label("Zur Stelle", systemImage: "arrow.up.forward")
                .frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
        }.buttonStyle(.borderless)
        Button { onEdit(item) } label: {
            Label("Bearbeiten", systemImage: "square.and.pencil")
                .frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
        }.buttonStyle(.borderless)
        Button(role: .destructive) { onDelete(item) } label: {
            Label("Löschen", systemImage: "trash")
                .frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
        }.buttonStyle(.borderless)
    }
    private var annotationFilter: some View {
        Picker("Notizart", selection: $filter) {
            Text("Alle").tag(0); Text("Lesezeichen").tag(1); Text("Markierungen").tag(2)
        }
    }
}

private struct ReaderSearchResult: Identifiable {
    var passageID: String
    var location: Int
    var title: String
    var excerpt: String
    var id: String { "\(passageID):\(location)" }
}

private struct ReaderSearchSheet: View {
    let volume: GAVolume
    var initialQuery: String
    let onSelect: (ReaderSearchResult, String) -> Void
    @State private var query = ""
    @Environment(\.dismiss) private var dismiss
    private var results: [ReaderSearchResult] {
        let term = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard term.count >= 2 else { return [] }
        var found: [ReaderSearchResult] = []
        for passage in volume.passages {
            let text = passage.text as NSString
            var start = 0
            while start < text.length && found.count < 150 {
                let range = text.range(of: term, options: [.caseInsensitive, .diacriticInsensitive], range: NSRange(location: start, length: text.length - start))
                guard range.location != NSNotFound else { break }
                let excerptStart = max(0, range.location - 65)
                let excerptLength = min(text.length - excerptStart, range.length + 160)
                let excerptRange = text.rangeOfComposedCharacterSequences(for: NSRange(location: excerptStart, length: excerptLength))
                found.append(ReaderSearchResult(passageID: passage.id, location: range.location, title: passage.title,
                    excerpt: (excerptRange.location > 0 ? "…" : "") + text.substring(with: excerptRange).replacingOccurrences(of: "\n", with: " ") + "…"))
                start = NSMaxRange(range)
            }
            if found.count >= 150 { break }
        }
        return found
    }
    var body: some View {
        NavigationStack {
            Group {
                if query.count < 2 {
                    ContentUnavailableView("Im Buch suchen", systemImage: "magnifyingglass", description: Text("Suche nach einem Wort oder einer Textstelle."))
                } else if results.isEmpty {
                    ContentUnavailableView.search(text: query)
                } else {
                    List(results) { result in
                        Button { onSelect(result, query) } label: {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(result.title).font(.caption).foregroundStyle(.secondary)
                                Text(highlightedExcerpt(result.excerpt)).foregroundStyle(.primary)
                            }.padding(.vertical, 6)
                        }.buttonStyle(.plain)
                    }
                }
            }
            .searchable(text: $query, prompt: "Wort oder Textstelle")
            .navigationTitle("Im Buch suchen")
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
        }
        .onAppear { query = initialQuery }
        .frame(minWidth: 320, idealWidth: 540, minHeight: 420)
    }
    private func highlightedExcerpt(_ excerpt: String) -> AttributedString {
        var text = AttributedString(excerpt)
        if let range = text.range(of: query, options: [.caseInsensitive, .diacriticInsensitive]) {
            text[range].font = .body.bold()
            text[range].backgroundColor = .yellow.opacity(0.3)
        }
        return text
    }
}

private struct SourceAnnotationPopover: View {
    let annotation: GAAnnotation
    let languageCode: String
    var body: some View {
        ScrollView { SourceAnnotationContent(annotation: annotation, languageCode: languageCode).padding() }
            .frame(idealWidth: 420, maxWidth: 520, alignment: .leading)
    }
}

private struct SourceAnnotationList: View {
    let annotations: [GAAnnotation]
    let languageCode: String
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            List(annotations) { SourceAnnotationContent(annotation: $0, languageCode: languageCode).padding(.vertical, 8) }
                .navigationTitle("Anmerkungen der Ausgabe")
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
        }.frame(minWidth: 300, idealWidth: 500, minHeight: 360)
    }
}

private struct SourceAnnotationContent: View {
    let annotation: GAAnnotation
    let languageCode: String
    private var text: AttributedString {
        var result = AttributedString(annotation.text)
        result.languageIdentifier = languageCode
        return result
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Anmerkung \(annotation.id)", systemImage: "text.bubble")
                .font(.headline).accessibilityAddTraits(.isHeader)
            Text(text).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
        }
    }
}
