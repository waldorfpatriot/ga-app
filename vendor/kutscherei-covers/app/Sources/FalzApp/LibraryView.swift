import FalzCore
import SwiftUI

struct LibraryView: View {
    @EnvironmentObject private var model: AppModel
    @State private var isSidebarVisible = true
    @State private var showCategories = false
    #if os(iOS)
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    #endif
    private var compact: Bool {
        #if os(iOS)
        horizontalSizeClass == .compact
        #else
        false
        #endif
    }
    private var pageInset: CGFloat { compact ? 18 : 32 }

    var body: some View {
        HStack(spacing: 0) {
            if !compact && isSidebarVisible {
                LibrarySidebar().frame(width: 236)
                Rectangle().fill(FalzTheme.line).frame(width: 1)
            }
            VStack(spacing: 0) {
                topBar
                if model.library == nil { emptyLibrary }
                else {
                    libraryHeading
                    if model.books.isEmpty { noResults }
                    else {
                        ScrollView {
                            if model.layout == "spines" { ShelfGrid(books: model.books) }
                            else {
                                LazyVGrid(columns: compact ? [GridItem(.flexible(), spacing: 20), GridItem(.flexible(), spacing: 20)] : [GridItem(.adaptive(minimum: 165, maximum: 205), spacing: 27)], alignment: .leading, spacing: 28) {
                                    ForEach(model.books) { book in BookCoverCard(book: book) }
                                }.padding(.horizontal, pageInset).padding(.top, 4).padding(.bottom, 35)
                            }
                        }
                        .refreshable { await model.refreshCatalog() }
                        .id("\(model.selectedCategory ?? "all")-\(model.layout)")
                    }
                    footer
                }
            }
        }
        .background(FalzTheme.paper)
        .foregroundStyle(FalzTheme.ink)
        .sheet(item: $model.detailBook) { BookDetailSheet(book: $0).environmentObject(model) }
        .sheet(isPresented: $showCategories) {
            VStack(spacing: 0) {
                HStack {
                    Text("Bibliothek").font(FalzTheme.serif(25))
                    Spacer()
                    Button("Fertig") { showCategories = false }
                }.padding(20).background(FalzTheme.sidebar)
                LibrarySidebar(onSelect: { showCategories = false })
            }.environmentObject(model)
        }
    }

    private var topBar: some View {
        HStack(spacing: compact ? 10 : 18) {
            Button {
                if compact { showCategories = true }
                else { withAnimation(.easeInOut(duration: 0.18)) { isSidebarVisible.toggle() } }
            } label: {
                Image(systemName: "sidebar.left").font(.system(size: 17)).frame(minWidth: 30, minHeight: 44)
            }.buttonStyle(.plain).help("Kategorien ein- oder ausblenden").accessibilityLabel("Kategorien")
            HStack(spacing: 9) {
                Image(systemName: "magnifyingglass").foregroundStyle(FalzTheme.muted)
                TextField("GA-Nummer oder Titel", text: $model.search)
                    .textFieldStyle(.plain).font(FalzTheme.ui(compact ? 15 : 13))
                    .accessibilityIdentifier("library-search")
                if !model.search.isEmpty {
                    Button { model.search = "" } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(FalzTheme.muted) }.buttonStyle(.plain).help("Suche löschen").accessibilityLabel("Suche löschen")
                }
            }.padding(.horizontal, 12).padding(.vertical, 11)
                .background(.white.opacity(0.42), in: RoundedRectangle(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(FalzTheme.line.opacity(0.7)))
                .frame(maxWidth: compact ? .infinity : 430)
            if !compact { Spacer(minLength: 5) }
            Menu {
                Toggle("Nicht verfügbare zeigen", isOn: Binding(get: { !model.readableOnly }, set: { model.readableOnly = !$0 }))
                    .accessibilityIdentifier("show-unavailable")
                Picker("Sortieren", selection: $model.sortOrder) {
                    Text("GA-Nummer").tag("ga")
                    Text("Titel").tag("title")
                    Text("Zuletzt gelesen").tag("recent")
                }
                Picker("Ansicht", selection: $model.layout) {
                    Label("Cover", systemImage: "square.grid.2x2").tag("covers")
                    Label("Buchrücken", systemImage: "books.vertical").tag("spines")
                }
                Divider()
                Button { Task { await model.refreshCatalog() } } label: { Label("Katalog aktualisieren", systemImage: "arrow.clockwise") }.disabled(model.isRefreshing)
            } label: { Image(systemName: "line.3.horizontal.decrease.circle").font(.system(size: 21)).frame(minWidth: 32, minHeight: 44) }
                .menuIndicator(.hidden).help("Ansicht und Filter").accessibilityLabel("Ansicht und Filter").accessibilityIdentifier("library-options")
            if !compact {
                Picker("Ansicht", selection: $model.layout) {
                    Image(systemName: "square.grid.2x2").tag("covers").help("Coveransicht")
                    Image(systemName: "books.vertical").tag("spines").help("Buchrückenansicht")
                }.pickerStyle(.segmented).labelsHidden().frame(width: 92).accessibilityIdentifier("view-mode")
            }
        }.padding(.horizontal, compact ? 12 : 30).padding(.vertical, compact ? 5 : 12)
        .overlay(alignment: .bottom) { FalzTheme.line.opacity(0.65).frame(height: 1) }
    }

    private var libraryHeading: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .bottom) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("RUDOLF STEINER").font(FalzTheme.ui(10, weight: .semibold)).tracking(2.6).foregroundStyle(FalzTheme.muted)
                    Text(model.currentCategory?.name ?? "Die Gesamtausgabe")
                        .font(FalzTheme.serif(compact ? 29 : 35)).lineLimit(2).minimumScaleFactor(0.7)
                }
                Spacer(minLength: 8)
                if model.isRefreshing { ProgressView().controlSize(.small).accessibilityLabel("Katalog wird aktualisiert") }
                else {
                    Button { Task { await model.refreshCatalog() } } label: {
                        Image(systemName: "arrow.clockwise").frame(width: 40, height: 40)
                    }.buttonStyle(.plain).accessibilityLabel("Katalog aktualisieren")
                }
            }
            HStack(spacing: compact ? 12 : 20) {
                Label("Geladen", systemImage: "checkmark.circle.fill")
                Label("Cloud", systemImage: "icloud.and.arrow.down")
                if !model.readableOnly { Label("Nicht verfügbar", systemImage: "icloud.slash") }
            }.font(FalzTheme.ui(10)).foregroundStyle(FalzTheme.muted)
            if let message = model.statusMessage {
                Text(message).font(FalzTheme.ui(11)).foregroundStyle(FalzTheme.muted).fixedSize(horizontal: false, vertical: true)
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, pageInset).padding(.top, compact ? 19 : 27).padding(.bottom, compact ? 19 : 27)
    }
    private var footer: some View {
        HStack(spacing: 6) {
            Text("\(model.books.count) Bände")
            Text("·")
            Text("\(model.downloadedCount) geladen")
            Spacer()
            if !compact { Text("GESAMTAUSGABE").tracking(1.8).font(FalzTheme.ui(9, weight: .medium)) }
        }.font(FalzTheme.ui(11)).foregroundStyle(FalzTheme.muted)
            .padding(.horizontal, pageInset).padding(.vertical, 12)
            .background(FalzTheme.background.opacity(0.8))
    }
    private var noResults: some View {
        VStack(spacing: 13) {
            Image(systemName: "text.magnifyingglass").font(.system(size: 33, weight: .light)).foregroundStyle(FalzTheme.muted)
            Text("Keine Bände gefunden").font(FalzTheme.serif(27))
            Text("Versuche eine andere GA-Nummer oder einen anderen Titel.").font(FalzTheme.ui(13)).foregroundStyle(FalzTheme.muted).multilineTextAlignment(.center)
            Button("Filter zurücksetzen") { model.search = ""; model.selectedCategory = nil; model.readableOnly = true }.buttonStyle(.bordered)
            if model.readableOnly { Button("Nicht verfügbare Bände zeigen") { model.readableOnly = false }.font(FalzTheme.ui(12)) }
        }.padding(20).frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    private var emptyLibrary: some View {
        VStack(spacing: 17) {
            Image(systemName: "books.vertical").font(.system(size: 44, weight: .ultraLight))
            Text("Deine Gesamtausgabe").font(FalzTheme.serif(32))
            Text("Lade den Katalog, um deine Bibliothek zu entdecken.").font(FalzTheme.ui(14)).foregroundStyle(FalzTheme.muted).multilineTextAlignment(.center)
            Button("Katalog laden") { Task { await model.refreshCatalog() } }.buttonStyle(.borderedProminent).tint(FalzTheme.ink).disabled(model.isRefreshing)
            #if os(macOS)
            Button("Lokale Bibliothek auswählen …") { model.chooseLibrary() }.buttonStyle(.bordered)
            #endif
        }.padding(20).frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private struct LibrarySidebar: View {
    @EnvironmentObject private var model: AppModel
    var onSelect: () -> Void = {}
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            GALogo().padding(.top, 28).padding(.horizontal, 25).padding(.bottom, 31)
            Button { model.selectedCategory = nil; onSelect() } label: {
                HStack {
                    Image(systemName: "books.vertical").font(.system(size: 15))
                    Text("Alle Bände").font(FalzTheme.ui(13, weight: .medium))
                    Spacer()
                    Text("\(model.library?.books.count ?? 0)").font(FalzTheme.ui(11)).foregroundStyle(FalzTheme.muted)
                }.padding(.horizontal, 11).padding(.vertical, 11)
                    .background(model.selectedCategory == nil ? FalzTheme.paper : .clear, in: RoundedRectangle(cornerRadius: 7))
            }.buttonStyle(.plain).padding(.horizontal, 14)
            Text("ABTEILUNGEN").font(FalzTheme.ui(9, weight: .semibold)).tracking(1.8).foregroundStyle(FalzTheme.muted)
                .padding(.horizontal, 25).padding(.top, 29).padding(.bottom, 12)
            ScrollView {
                VStack(spacing: 3) {
                    ForEach(model.visibleCategories) { category in
                        Button { model.selectedCategory = category.id; onSelect() } label: {
                            HStack(alignment: .center, spacing: 10) {
                                RoundedRectangle(cornerRadius: 2).fill(Color(hex: category.colorHex)).frame(width: 5, height: 24)
                                Text(category.name).font(FalzTheme.ui(11.5)).lineLimit(2).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                                Spacer(minLength: 3)
                                Text("\(model.count(category))").font(FalzTheme.ui(10)).monospacedDigit().foregroundStyle(FalzTheme.muted)
                            }.padding(.horizontal, 11).padding(.vertical, 8)
                                .background(model.selectedCategory == category.id ? FalzTheme.paper : .clear, in: RoundedRectangle(cornerRadius: 7))
                                .contentShape(Rectangle())
                        }.buttonStyle(.plain)
                    }
                }.padding(.horizontal, 14)
            }
            Spacer(minLength: 16)
            VStack(alignment: .leading, spacing: 8) {
                Rectangle().fill(FalzTheme.line).frame(height: 1)
                Text("\(model.readableCount) Bände zum Lesen").font(FalzTheme.ui(11)).foregroundStyle(FalzTheme.muted)
                Toggle("Nicht verfügbare zeigen", isOn: Binding(get: { !model.readableOnly }, set: { model.readableOnly = !$0 })).font(FalzTheme.ui(11))
                #if os(macOS)
                Button { model.chooseLibrary() } label: { Label("Bibliothek öffnen …", systemImage: "folder").font(FalzTheme.ui(11)) }
                    .buttonStyle(.plain).foregroundStyle(FalzTheme.muted).padding(.top, 2)
                #endif
            }.padding(.horizontal, 25).padding(.bottom, 20)
        }.background(FalzTheme.sidebar)
    }
}

struct BookCoverCard: View {
    @EnvironmentObject private var model: AppModel
    let book: LibraryBook
    @State private var hovered = false
    var body: some View {
        Button { model.openBook(book) } label: {
            VStack(alignment: .leading, spacing: 10) {
                BookCover(book: book)
                    .aspectRatio(0.71, contentMode: .fit)
                    .shadow(color: .black.opacity(hovered ? 0.22 : 0.15), radius: hovered ? 9 : 5, x: 3, y: hovered ? 9 : 6)
                    .offset(y: hovered ? -3 : 0)
                HStack(alignment: .firstTextBaseline) {
                    Text(book.gaLabel).font(FalzTheme.ui(10, weight: .semibold)).tracking(0.6)
                    Spacer(minLength: 1)
                    BookStatusIcon(book: book)
                    if model.positions[book.id] != nil { Image(systemName: "bookmark.fill").font(.system(size: 10)).foregroundStyle(FalzTheme.muted) }
                }.padding(.horizontal, 2)
            }.contentShape(Rectangle())
        }.buttonStyle(.plain).onHover { hovered = $0 }.animation(.easeOut(duration: 0.18), value: hovered)
            .help("\(book.gaLabel) · \(book.title) · \(model.availability(for: book).displayLabel)")
            .accessibilityLabel("\(book.gaLabel), \(book.title), \(model.availability(for: book).displayLabel)")
            .accessibilityIdentifier("book-\(book.id)")
            .contextMenu { bookMenu(book) }
    }
    @ViewBuilder private func bookMenu(_ book: LibraryBook) -> some View {
        if model.availability(for: book) != .unavailable {
            Button(model.availability(for: book) == .downloaded ? "Lesen" : "Herunterladen und lesen") { model.openBook(book) }
            #if os(macOS)
            if model.availability(for: book) == .downloaded { Button("EPUB im Finder zeigen") { model.reveal(book) } }
            #endif
        }
        Button("Buchdetails") { model.detailBook = book }
    }
}

struct BookCover: View {
    @EnvironmentObject private var model: AppModel
    let book: LibraryBook
    var body: some View {
        let category = model.category(for: book)
        GeometryReader { geometry in
            let width = geometry.size.width
            ZStack {
                TextileSurface(color: Color(hex: category.colorHex), textureURL: model.textureURL(for: category))
                Rectangle().fill(LinearGradient(stops: [.init(color: .black.opacity(0.35), location: 0), .init(color: .white.opacity(0.13), location: 0.3), .init(color: .black.opacity(0.14), location: 0.7), .init(color: .clear, location: 1)], startPoint: .leading, endPoint: .trailing)).frame(width: 10).frame(maxWidth: .infinity, alignment: .leading)
                VStack(spacing: 0) {
                    GoldText(text: "RUDOLF STEINER", font: FalzTheme.ui(width * 0.049, weight: .medium), textureURL: model.goldURL).tracking(1.2).padding(.top, width * 0.20)
                    Rectangle().fill(FalzTheme.gold.opacity(0.63)).frame(width: width * 0.38, height: 0.65).padding(.top, width * 0.08)
                    Spacer(minLength: 12)
                    GoldText(text: book.title, font: FalzTheme.serif(width * 0.113), textureURL: model.goldURL)
                        .multilineTextAlignment(.center).lineLimit(6).minimumScaleFactor(0.58).padding(.horizontal, width * 0.13)
                    Spacer(minLength: 12)
                    GoldText(text: book.gaLabel.uppercased(), font: FalzTheme.ui(width * 0.061, weight: .medium), textureURL: model.goldURL).tracking(1.8)
                    Text("GESAMTAUSGABE").font(FalzTheme.ui(width * 0.037)).tracking(1.5).foregroundStyle(FalzTheme.gold.opacity(0.83)).padding(.top, 9).padding(.bottom, width * 0.14)
                }
            }.clipShape(RoundedRectangle(cornerRadius: 2.5))
                .overlay(RoundedRectangle(cornerRadius: 2.5).stroke(.black.opacity(0.14), lineWidth: 0.8))
                .overlay(alignment: .trailing) { Rectangle().fill(.white.opacity(0.09)).frame(width: 1).padding(.vertical, 3) }
        }
    }
}

private struct ShelfGrid: View {
    @EnvironmentObject private var model: AppModel
    let books: [LibraryBook]
    @State private var width: CGFloat = 900
    private var columns: Int { max(1, Int((width - 64) / 67)) }
    private var rows: [[LibraryBook]] {
        stride(from: 0, to: books.count, by: columns).map { Array(books[$0..<min($0 + columns, books.count)]) }
    }
    var body: some View {
        LazyVStack(alignment: .leading, spacing: 31) {
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                HStack(alignment: .bottom, spacing: 5) {
                    ForEach(row) { book in BookSpine(book: book).frame(width: 62, height: 310) }
                    Spacer(minLength: 0)
                }.padding(.horizontal, 32).padding(.bottom, 13)
                    .background(alignment: .bottom) {
                        VStack(spacing: 0) {
                            LinearGradient(colors: [Color(hex: "C2B69B").opacity(0.5), Color(hex: "E0D6C0")], startPoint: .top, endPoint: .bottom).frame(height: 5)
                            Color(hex: "DDD4C1").frame(height: 9)
                        }.shadow(color: .black.opacity(0.12), radius: 5, y: 6)
                    }
            }
        }.padding(.top, 3).padding(.bottom, 40)
            .background(GeometryReader { proxy in Color.clear.onAppear { width = proxy.size.width }.onChange(of: proxy.size.width) { _, value in width = value } })
    }
}

private struct BookSpine: View {
    @EnvironmentObject private var model: AppModel
    let book: LibraryBook
    @State private var hovered = false
    var body: some View {
        let category = model.category(for: book)
        Button { model.openBook(book) } label: {
            ZStack {
                TextileSurface(color: Color(hex: category.colorHex), textureURL: model.textureURL(for: category))
                LinearGradient(stops: [.init(color: .black.opacity(0.35), location: 0), .init(color: .white.opacity(0.08), location: 0.24), .init(color: .clear, location: 0.45), .init(color: .black.opacity(0.23), location: 1)], startPoint: .leading, endPoint: .trailing)
                VStack(spacing: 0) {
                    GoldText(text: "R · S", font: FalzTheme.serif(14), textureURL: model.goldURL).padding(.top, 15)
                    Rectangle().fill(FalzTheme.gold.opacity(0.48)).frame(width: 33, height: 0.6).padding(.top, 8)
                    Spacer()
                    GoldText(text: book.title, font: FalzTheme.serif(18), textureURL: model.goldURL)
                        .lineLimit(2).minimumScaleFactor(0.55).multilineTextAlignment(.center)
                        .frame(width: 208, height: 43).rotationEffect(.degrees(-90)).frame(width: 43, height: 208)
                    Spacer(minLength: 6)
                    Rectangle().fill(FalzTheme.gold.opacity(0.48)).frame(width: 33, height: 0.6)
                    GoldText(text: book.gaNumber, font: FalzTheme.serif(22), textureURL: model.goldURL).lineLimit(1).minimumScaleFactor(0.55).frame(height: 35).padding(.horizontal, 4).padding(.bottom, 7)
                }
            }.clipShape(RoundedRectangle(cornerRadius: 3)).overlay(RoundedRectangle(cornerRadius: 3).stroke(.black.opacity(0.18), lineWidth: 0.7))
                .shadow(color: .black.opacity(0.2), radius: 2, x: 2, y: 3)
                .offset(y: hovered ? -7 : 0)
                .overlay(alignment: .topTrailing) { BookStatusIcon(book: book).padding(5).background(FalzTheme.paper, in: Circle()).padding(3) }
        }.buttonStyle(.plain).onHover { hovered = $0 }.animation(.easeOut(duration: 0.16), value: hovered)
            .help("\(book.gaLabel) · \(book.title) · \(model.availability(for: book).displayLabel)")
            .accessibilityLabel("\(book.gaLabel), \(book.title), \(model.availability(for: book).displayLabel)")
            .accessibilityIdentifier("book-\(book.id)")
            .contextMenu {
                if model.availability(for: book) != .unavailable { Button(model.availability(for: book) == .downloaded ? "Lesen" : "Herunterladen und lesen") { model.openBook(book) } }
                #if os(macOS)
                if model.availability(for: book) == .downloaded { Button("EPUB im Finder zeigen") { model.reveal(book) } }
                #endif
                Button("Buchdetails") { model.detailBook = book }
            }
    }
}

private struct BookStatusIcon: View {
    @EnvironmentObject private var model: AppModel
    let book: LibraryBook
    var body: some View {
        Group {
            if model.availability(for: book) == .downloading {
                ProgressView().controlSize(.mini).frame(width: 16, height: 16)
            } else {
                Image(systemName: model.availability(for: book).symbolName)
                    .font(.system(size: 13))
                    .foregroundStyle(model.availability(for: book) == .downloaded ? FalzTheme.ink : FalzTheme.muted)
            }
        }.accessibilityLabel(model.availability(for: book).displayLabel)
    }
}

extension BookAvailability {
    var displayLabel: String {
        switch self {
        case .downloaded: return "Heruntergeladen"
        case .cloud: return "In der Cloud – zum Laden tippen"
        case .unavailable: return "Nicht verfügbar"
        case .downloading: return "Wird heruntergeladen"
        }
    }
    var symbolName: String {
        switch self {
        case .downloaded: return "checkmark.circle.fill"
        case .cloud, .downloading: return "icloud.and.arrow.down"
        case .unavailable: return "icloud.slash"
        }
    }
}

private struct BookDetailSheet: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    let book: LibraryBook
    var body: some View {
        ScrollView {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 30) {
                    cover
                    details.frame(minWidth: 300, maxWidth: .infinity, alignment: .leading)
                }
                VStack(alignment: .leading, spacing: 24) { cover.frame(maxWidth: .infinity); details }
            }.padding(25)
        }
        .frame(idealWidth: 680, idealHeight: 470)
        .background(FalzTheme.paper).foregroundStyle(FalzTheme.ink)
    }
    private var cover: some View {
        BookCover(book: book).frame(width: 160, height: 226).shadow(color: .black.opacity(0.2), radius: 8, y: 5)
    }
    private var availabilityExplanation: String {
        switch model.availability(for: book) {
        case .downloaded: return "Auf diesem Gerät gespeichert. Du kannst das Buch auch ohne Internetverbindung lesen."
        case .cloud: return "Lade das Buch mit einem Tippen herunter. Danach kannst du es auch offline lesen."
        case .unavailable: return "Für diesen Band liegt auf dem Server noch keine lesbare EPUB-Datei vor."
        case .downloading: return "Das Buch wird auf diesem Gerät gespeichert."
        }
    }
    private var details: some View {
        VStack(alignment: .leading, spacing: 13) {
            Text(book.gaLabel.uppercased()).font(FalzTheme.ui(11, weight: .semibold)).tracking(2).foregroundStyle(FalzTheme.muted)
            Text(book.title).font(FalzTheme.serif(29)).fixedSize(horizontal: false, vertical: true)
            Text(book.author).font(FalzTheme.ui(13))
            Text(model.category(for: book).name).font(FalzTheme.ui(12)).foregroundStyle(FalzTheme.muted)
            Divider().padding(.vertical, 4)
            Label(model.availability(for: book).displayLabel, systemImage: model.availability(for: book).symbolName).font(FalzTheme.ui(12))
            Text(availabilityExplanation).font(FalzTheme.ui(12)).foregroundStyle(FalzTheme.muted).fixedSize(horizontal: false, vertical: true)
            HStack {
                Button("Schließen") { dismiss() }.keyboardShortcut(.cancelAction)
                if model.availability(for: book) == .downloaded || model.availability(for: book) == .cloud {
                    Button(model.availability(for: book) == .downloaded ? "Lesen" : "Herunterladen") { dismiss(); model.openBook(book) }.buttonStyle(.borderedProminent).tint(FalzTheme.ink).keyboardShortcut(.defaultAction)
                }
            }.padding(.top, 12)
        }
    }
}
