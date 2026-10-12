import SwiftUI
#if os(iOS)
import UIKit
#endif

struct ReaderAnnotationPresentation: Identifiable {
    let id = UUID()
    var annotationID: String?
    var context: ReaderTextContext
}

enum ReaderAnnotationMenuPage {
    case actions, marking
}

struct ReaderAnnotationMenu: View {
    @Binding var page: ReaderAnnotationMenuPage
    let annotation: PersonalAnnotation?
    let canUseWritingTools: Bool
    let onColor: (HighlightColor) -> Void
    let onUnderline: () -> Void
    let onNote: () -> Void
    let onRemove: () -> Void
    let onSearch: () -> Void
    let onWritingTools: () -> Void
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        Group {
            if page == .marking {
                markingPicker
            } else {
                VStack(spacing: 0) {
                    menuAction("Markierung", icon: "highlighter") { page = .marking }
                    menuAction(annotation?.note.isEmpty == false ? "Notiz bearbeiten" : "Notiz hinzufügen", icon: "note.text", action: onNote)
                    if annotation != nil {
                        menuAction("Entfernen", icon: "minus.circle", destructive: true, action: onRemove)
                    }
                    Divider().padding(.horizontal, 14).padding(.vertical, 4)
                    menuAction("Suchen", icon: "magnifyingglass", action: onSearch)
                        .accessibilityIdentifier("reader-annotation-search")
                    Divider().padding(.horizontal, 14).padding(.vertical, 4)
                    menuAction("Schreibtools", icon: "pencil.and.scribble", action: onWritingTools)
                        .disabled(!canUseWritingTools)
                        .accessibilityHint(canUseWritingTools ? "Öffnet die Schreibtools von Apple Intelligence für diese Textstelle." : "Auf diesem Gerät oder für diese Textstelle nicht verfügbar.")
                }
                .padding(.vertical, 8)
                .frame(width: dynamicTypeSize.isAccessibilitySize ? 310 : 260)
                .accessibilityIdentifier("reader-annotation-menu")
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .tint(.primary)
    }

    private var markingPicker: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 0) { markingActions }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 48))], spacing: 4) { markingActions }
                .frame(width: 260)
        }
        .padding(8)
        .accessibilityIdentifier("reader-marking-picker")
    }

    @ViewBuilder private var markingActions: some View {
        ForEach(HighlightColor.allCases, id: \.self) { color in
            Button { onColor(color) } label: {
                Circle().fill(color.readerColor)
                    .frame(width: 22, height: 22)
                    .overlay {
                        if annotation?.style == .highlight && annotation?.color == color {
                            Image(systemName: "checkmark").font(.system(size: 12, weight: .bold)).foregroundStyle(.black.opacity(0.75))
                        }
                    }
                    .frame(width: 44, height: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("\(color.readerLabel) markieren")
            .accessibilityAddTraits(annotation?.style == .highlight && annotation?.color == color ? .isSelected : [])
        }
        Button(action: onUnderline) {
            Text("U").font(.system(size: 21, weight: .medium)).underline()
                .frame(width: 44, height: 44)
                .background(annotation?.style == .underline ? Color.primary.opacity(0.1) : .clear, in: Circle())
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Unterstreichen")
        .accessibilityAddTraits(annotation?.style == .underline ? .isSelected : [])
    }

    private func menuAction(_ title: String, icon: String, destructive: Bool = false, action: @escaping () -> Void) -> some View {
        Button(role: destructive ? .destructive : nil, action: action) {
            HStack(spacing: 14) {
                Image(systemName: icon).frame(width: 24)
                Text(title).multilineTextAlignment(.leading)
                Spacer(minLength: 0)
            }
            .foregroundStyle(destructive ? Color.red : .primary)
            .padding(.horizontal, 18)
            .padding(.vertical, 11)
            .frame(minHeight: 44)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

struct ReaderNoteEditor: View {
    @State private var annotation: PersonalAnnotation
    private let original: PersonalAnnotation
    let onSave: (PersonalAnnotation) -> Void
    @State private var saved = false
    @FocusState private var noteFocused: Bool
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    init(annotation: PersonalAnnotation, onSave: @escaping (PersonalAnnotation) -> Void) {
        _annotation = State(initialValue: annotation)
        original = annotation
        self.onSave = onSave
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(spacing: 7) {
                Text(annotation.isBookmark ? "Lesezeichen" : "Notiz").font(.headline)
                Text(annotation.updatedAt, format: .dateTime.hour().minute())
                    .font(.headline).foregroundStyle(.secondary)
                Spacer(minLength: 4)
                Button(action: save) {
                    Image(systemName: "checkmark")
                        .font(.system(size: 23, weight: .medium))
                        .foregroundStyle(.background)
                        .frame(width: 48, height: 48)
                        .background(Color.primary, in: Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Notiz speichern")
                .keyboardShortcut(.return, modifiers: .command)
            }
            .padding(.bottom, 8)
            if !annotation.quote.isEmpty {
                HStack(alignment: .top, spacing: 13) {
                    Rectangle().fill(annotation.color.readerColor).frame(width: 4)
                    Text(annotation.quote)
                        .font(.system(.body, design: .serif))
                        .lineLimit(dynamicTypeSize.isAccessibilitySize ? 3 : 5)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityIdentifier("reader-note-quote")
                }
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityElement(children: .contain)
            }
            ZStack(alignment: .topLeading) {
                #if os(iOS)
                ReaderNoteTextEditor(text: $annotation.note)
                    .accessibilityLabel("Persönliche Notiz")
                    .accessibilityIdentifier("reader-note-editor")
                #else
                TextEditor(text: $annotation.note)
                    .font(.body)
                    .scrollContentBackground(.hidden)
                    .focused($noteFocused)
                    .accessibilityLabel("Persönliche Notiz")
                    .accessibilityIdentifier("reader-note-editor")
                #endif
                if annotation.note.isEmpty {
                    Text("Notiz hinzufügen …")
                        .font(.body).foregroundStyle(.secondary)
                        .padding(.top, 8).padding(.leading, 5)
                        .allowsHitTesting(false)
                        .accessibilityHidden(true)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .padding(24)
        .background(.background)
        .frame(minWidth: 300, idealWidth: 520, minHeight: 360)
        .presentationDragIndicator(.visible)
        #if os(macOS)
        .task {
            // The editor must join the presented sheet before it can receive focus.
            try? await Task.sleep(for: .milliseconds(450))
            guard !Task.isCancelled else { return }
            noteFocused = true
        }
        #endif
        .onDisappear {
            if !saved && annotation.note != original.note { save() }
        }
    }

    private func save() {
        guard !saved else { return }
        saved = true
        annotation.updatedAt = Date()
        onSave(annotation)
    }
}

#if os(iOS)
/// Requests focus when the sheet finishes appearing, after its source popover closes.
private struct ReaderNoteTextEditor: UIViewControllerRepresentable {
    @Binding var text: String

    func makeCoordinator() -> Coordinator { Coordinator(text: $text) }

    func makeUIViewController(context: Context) -> EditorController {
        let controller = EditorController()
        controller.editor.delegate = context.coordinator
        controller.editor.text = text
        return controller
    }

    func updateUIViewController(_ controller: EditorController, context: Context) {
        context.coordinator.text = $text
        if controller.editor.text != text { controller.editor.text = text }
    }

    @MainActor final class Coordinator: NSObject, UITextViewDelegate {
        var text: Binding<String>
        init(text: Binding<String>) { self.text = text }
        func textViewDidChange(_ textView: UITextView) { text.wrappedValue = textView.text }
    }

    @MainActor final class EditorController: UIViewController {
        let editor = UITextView()
        private var didRequestFocus = false

        override func loadView() {
            editor.font = .preferredFont(forTextStyle: .body)
            editor.adjustsFontForContentSizeCategory = true
            editor.textColor = .label
            editor.backgroundColor = .clear
            editor.keyboardDismissMode = .interactive
            editor.accessibilityLabel = "Persönliche Notiz"
            editor.accessibilityIdentifier = "reader-note-editor"
            view = editor
        }

        override func viewDidAppear(_ animated: Bool) {
            super.viewDidAppear(animated)
            guard !didRequestFocus else { return }
            didRequestFocus = true
            editor.becomeFirstResponder()
        }
    }
}
#endif
