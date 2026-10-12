import SwiftUI
#if os(iOS)
import UIKit
#else
import AppKit
#endif

enum ReaderSelectionAction {
    case marking, note, search
}

/// Range is relative to passage text; rect is in the native view's visible viewport.
struct ReaderTextContext {
    var range: NSRange
    var rect: CGRect
    var showWritingTools: (@MainActor () -> Void)?
    var clearSelection: @MainActor () -> Void
}

struct ReaderAnchor: Equatable {
    var offset: Int
    var requestID = UUID()
}

struct ReaderTextSettings {
    var fontSize: CGFloat
    var serif: Bool
    var lineSpacing: Double
    var margin: Double
    var showsPages: Bool
    var palette: ReaderPalette
    var signature: String { "\(fontSize):\(serif):\(lineSpacing):\(margin):\(showsPages):\(palette.dark):\(palette.background)" }
}

private extension NSAttributedString.Key {
    static let readerAnnotationID = NSAttributedString.Key("GAReaderAnnotationID")
}

#if os(iOS)
private typealias ReaderPlatformFont = UIFont
private typealias ReaderPlatformColor = UIColor
#else
private typealias ReaderPlatformFont = NSFont
private typealias ReaderPlatformColor = NSColor
#endif

struct ReaderDocument {
    var text: NSAttributedString
    var bodyStart: Int
    var bodyLength: Int

    func bodyRange(for range: NSRange) -> NSRange {
        guard range.location != NSNotFound, range.location >= 0 else { return NSRange(location: 0, length: 0) }
        let start = max(range.location, bodyStart)
        let end = min(NSMaxRange(range), bodyStart + bodyLength)
        return NSRange(location: min(bodyLength, max(0, start - bodyStart)), length: max(0, end - start))
    }

    func documentRange(for range: NSRange) -> NSRange {
        let start = min(bodyLength, max(0, range.location))
        return NSRange(location: bodyStart + start, length: min(max(0, range.length), bodyLength - start))
    }
}

@MainActor func readingDocument(passage: GAPassage, title: String, settings: ReaderTextSettings,
                             annotations: [PersonalAnnotation], searchText: String) -> ReaderDocument {
    let font = ReaderPlatformFont.systemFont(ofSize: settings.fontSize)
    let bodyFont: ReaderPlatformFont
    #if os(iOS)
    bodyFont = settings.serif ? UIFont(descriptor: font.fontDescriptor.withDesign(.serif) ?? font.fontDescriptor, size: settings.fontSize) : font
    #else
    bodyFont = settings.serif ? NSFont(descriptor: font.fontDescriptor.withDesign(.serif) ?? font.fontDescriptor, size: settings.fontSize) ?? font : font
    #endif
    let paragraph = NSMutableParagraphStyle()
    paragraph.lineSpacing = settings.lineSpacing
    paragraph.paragraphSpacing = settings.fontSize * 0.65
    let foreground = ReaderPlatformColor(settings.palette.foreground)
    let blocks = passage.metadata.validReadingBlocks(in: passage.text)
    let sections = passage.metadata.validReadingSections(in: passage.text, passageTitle: passage.title)
    let firstTitleInBody = sections.first?.labelKind == .sourceTitle && blocks.first?.kind == .heading &&
        blocks.first.map { (passage.text as NSString).substring(with: $0.range) == sections.first?.title } == true
    let usesTitlePreamble = sections.isEmpty || (sections.first?.labelKind == .sourceTitle && sections.first?.title == passage.title && !firstTitleInBody)
    let text = NSMutableAttributedString(string: "\(title)\n", attributes: [.font: ReaderPlatformFont.systemFont(ofSize: settings.fontSize * 0.72), .foregroundColor: foreground.withAlphaComponent(0.7)])
    if let group = passage.metadata.groupTitle, !group.isEmpty {
        text.append(NSAttributedString(string: "\(group)\n", attributes: [.font: ReaderPlatformFont.systemFont(ofSize: settings.fontSize * 0.75, weight: .semibold), .foregroundColor: foreground.withAlphaComponent(0.7)]))
    }
    if usesTitlePreamble {
        text.append(NSAttributedString(string: "\(passage.title)\n\n", attributes: [.font: ReaderPlatformFont.systemFont(ofSize: settings.fontSize * 1.4, weight: .semibold), .foregroundColor: foreground]))
    }
    if settings.showsPages, let pages = passage.metadata.pageNumberLabel ?? passage.gaPage {
        text.append(NSAttributedString(string: "\(pages)\n\n", attributes: [.font: ReaderPlatformFont.systemFont(ofSize: settings.fontSize * 0.7), .foregroundColor: foreground.withAlphaComponent(0.7)]))
    }
    let bodyStart = text.length
    text.append(NSAttributedString(string: passage.text, attributes: [.font: bodyFont, .foregroundColor: foreground, .paragraphStyle: paragraph]))
    let bodyLength = (passage.text as NSString).length
    if !blocks.isEmpty {
        let structuredParagraph = paragraph.mutableCopy() as! NSMutableParagraphStyle
        // The canonical text already contains stanza and paragraph separators.
        // Single verse line feeds must not acquire paragraph-sized gaps.
        structuredParagraph.paragraphSpacing = 0
        text.addAttribute(.paragraphStyle, value: structuredParagraph, range: NSRange(location: bodyStart, length: bodyLength))
        for block in blocks {
            let range = NSRange(location: bodyStart + block.startOffset, length: block.range.length)
            switch block.kind {
            case .heading:
                let level = block.level ?? 2
                let size = settings.fontSize * (level <= 1 ? 1.3 : level == 2 ? 1.18 : 1.06)
                text.addAttribute(.font, value: ReaderPlatformFont.systemFont(ofSize: size, weight: .semibold), range: range)
            case .attribution, .note:
                text.addAttributes([.font: ReaderPlatformFont.systemFont(ofSize: settings.fontSize * 0.88), .foregroundColor: foreground.withAlphaComponent(0.75)], range: range)
            case .verse, .prose:
                break
            }
            if block.kind == .verse, block.poemStart == true {
                let firstLine = (passage.text as NSString).substring(with: block.range).components(separatedBy: "\n").first ?? ""
                let firstParagraph = NSRange(location: range.location, length: min(range.length, (firstLine as NSString).length + 1))
                let poemParagraph = structuredParagraph.mutableCopy() as! NSMutableParagraphStyle
                poemParagraph.paragraphSpacingBefore = settings.fontSize * 0.35
                text.addAttribute(.paragraphStyle, value: poemParagraph, range: firstParagraph)
            }
        }
        let body = passage.text as NSString
        for (index, section) in sections.enumerated() {
            guard let first = blocks.first(where: { $0.startOffset == section.startOffset }) else { continue }
            // The first source title is already displayed above the body.
            if index == 0, usesTitlePreamble { continue }
            let firstLine = body.substring(with: first.range).components(separatedBy: "\n").first ?? ""
            let length = section.labelKind == .incipit ? (firstLine as NSString).length : first.range.length
            let labelRange = NSRange(location: bodyStart + first.startOffset, length: length)
            if section.labelKind == .sourceTitle {
                text.addAttribute(.font, value: ReaderPlatformFont.systemFont(ofSize: settings.fontSize * 1.4, weight: .semibold), range: labelRange)
            }
            let unitParagraph = structuredParagraph.mutableCopy() as! NSMutableParagraphStyle
            unitParagraph.paragraphSpacingBefore = index == 0 ? 0 : settings.fontSize * 1.1
            text.addAttribute(.paragraphStyle, value: unitParagraph,
                range: NSRange(location: labelRange.location, length: min(first.range.length, length + 1)))
        }
    }
    for annotation in annotations where !annotation.isBookmark && annotation.location >= 0 && annotation.length > 0 && annotation.location < bodyLength {
        let range = NSRange(location: bodyStart + annotation.location, length: min(annotation.length, bodyLength - annotation.location))
        text.addAttribute(.readerAnnotationID, value: annotation.id, range: range)
        if annotation.style == .underline {
            text.addAttributes([.underlineStyle: NSUnderlineStyle.single.rawValue,
                                .underlineColor: ReaderPlatformColor(annotation.color.readerColor)], range: range)
        } else {
            text.addAttribute(.backgroundColor, value: ReaderPlatformColor(annotation.color.readerColor).withAlphaComponent(settings.palette.dark ? 0.35 : 0.28), range: range)
        }
    }
    for annotation in passage.metadata.annotations {
        for range in annotation.markerRanges(in: passage.text) {
            if let url = annotation.linkURL {
                text.addAttributes([.link: url, .underlineStyle: NSUnderlineStyle.single.rawValue], range: NSRange(location: bodyStart + range.location, length: range.length))
            }
        }
    }
    if searchText.count >= 2 {
        let body = passage.text as NSString
        var start = 0
        while start < bodyLength {
            let range = body.range(of: searchText, options: [.caseInsensitive, .diacriticInsensitive], range: NSRange(location: start, length: bodyLength - start))
            guard range.location != NSNotFound else { break }
            text.addAttribute(.backgroundColor, value: ReaderPlatformColor.systemOrange.withAlphaComponent(0.3), range: NSRange(location: bodyStart + range.location, length: range.length))
            start = NSMaxRange(range)
        }
    }
    return ReaderDocument(text: text, bodyStart: bodyStart, bodyLength: bodyLength)
}

#if os(iOS)
struct NativeReadingText: UIViewRepresentable {
    var passage: GAPassage
    var volumeTitle: String
    var languageCode: String
    var settings: ReaderTextSettings
    var annotations: [PersonalAnnotation]
    var searchText: String
    var anchor: ReaderAnchor
    var onPosition: (Int) -> Void
    var onSelection: (NSRange) -> Void
    var onToggleControls: () -> Void
    var onSourceNote: (GAAnnotation) -> Void
    var onAnnotationTap: (String, ReaderTextContext) -> Void = { _, _ in }
    var onSelectionAction: (ReaderSelectionAction, ReaderTextContext) -> Void = { _, _ in }
    var onInteractionDismiss: () -> Void = {}

    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIView(context: Context) -> ReaderUITextView {
        // Reader geometry uses NSLayoutManager throughout. Switching from
        // TextKit 2 during the first restore leaves an undersized scroll area.
        let view = ReaderUITextView(usingTextLayoutManager: false)
        view.delegate = context.coordinator
        view.isEditable = false
        view.isSelectable = true
        view.writingToolsBehavior = .limited
        view.allowedWritingToolsResultOptions = []
        view.alwaysBounceVertical = true
        view.textContainer.lineFragmentPadding = 0
        view.adjustsFontForContentSizeCategory = false
        view.accessibilityLanguage = languageCode
        let tap = UITapGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.tapped(_:)))
        tap.cancelsTouchesInView = false
        tap.delegate = context.coordinator
        view.addGestureRecognizer(tap)
        view.onWidthChange = { [weak coordinator = context.coordinator] in coordinator?.layoutChanged() }
        context.coordinator.view = view
        return view
    }
    func updateUIView(_ view: ReaderUITextView, context: Context) { context.coordinator.update(self, view: view) }
    static func dismantleUIView(_ uiView: ReaderUITextView, coordinator: Coordinator) {
        coordinator.positionWork?.cancel()
        coordinator.parent.onPosition(coordinator.currentOffset)
    }

    @MainActor final class Coordinator: NSObject, UITextViewDelegate, UIGestureRecognizerDelegate {
        var parent: NativeReadingText
        weak var view: ReaderUITextView?
        var document = ReaderDocument(text: NSAttributedString(string: ""), bodyStart: 0, bodyLength: 0)
        var signature = ""
        var anchorID: UUID?
        var currentOffset = 0
        var restoring = false
        var positionWork: DispatchWorkItem?
        init(_ parent: NativeReadingText) { self.parent = parent }
        func update(_ parent: NativeReadingText, view: ReaderUITextView) {
            self.parent = parent
            view.backgroundColor = UIColor(parent.settings.palette.background)
            view.tintColor = UIColor(parent.settings.palette.accent)
            view.linkTextAttributes = [.foregroundColor: UIColor(parent.settings.palette.accent)]
            view.accessibilityCustomActions = parent.passage.metadata.annotations.map { note in
                UIAccessibilityCustomAction(name: "Anmerkung \(note.id)") { [weak self] _ in
                    self?.parent.onSourceNote(note)
                    return true
                }
            }
            view.accessibilityCustomActions = (view.accessibilityCustomActions ?? []) + parent.annotations.filter { !$0.isBookmark }.map { annotation in
                UIAccessibilityCustomAction(name: "\(annotation.style.displayName): \(annotation.quote.prefix(60))") { [weak self] _ in
                    self?.openAnnotation(annotation)
                    return true
                }
            }
            let nextSignature = "\(parent.passage.id):\(parent.settings.signature):\(parent.annotations):\(parent.searchText)"
            let requested = anchorID != parent.anchor.requestID
            if signature != nextSignature {
                let selected = view.selectedRange
                signature = nextSignature
                document = readingDocument(passage: parent.passage, title: parent.volumeTitle, settings: parent.settings, annotations: parent.annotations, searchText: parent.searchText)
                restoring = true
                view.attributedText = document.text
                if NSMaxRange(selected) <= document.text.length { view.selectedRange = selected }
                view.textContainerInset = UIEdgeInsets(top: 28, left: max(parent.settings.margin, (view.bounds.width - 760) / 2), bottom: 70, right: max(parent.settings.margin, (view.bounds.width - 760) / 2))
                restore(requested ? parent.anchor.offset : currentOffset)
            } else if requested { restore(parent.anchor.offset) }
            anchorID = parent.anchor.requestID
        }
        func layoutChanged() {
            guard let view else { return }
            DispatchQueue.main.async { [weak self] in self?.parent.onInteractionDismiss() }
            view.textContainerInset = UIEdgeInsets(top: 28, left: max(parent.settings.margin, (view.bounds.width - 760) / 2), bottom: 70, right: max(parent.settings.margin, (view.bounds.width - 760) / 2))
            restore(currentOffset)
        }
        func restore(_ offset: Int) {
            currentOffset = min(max(offset, 0), document.bodyLength)
            restoring = true
            DispatchQueue.main.async { [weak self] in
                guard let self, let view = self.view, let manager = view.layoutManager as NSLayoutManager? else { return }
                manager.ensureLayout(for: view.textContainer)
                let location = min(self.document.bodyStart + self.currentOffset, max(0, self.document.text.length - 1))
                let glyph = manager.glyphIndexForCharacter(at: location)
                let rect = manager.lineFragmentRect(forGlyphAt: glyph, effectiveRange: nil)
                let proposed = self.currentOffset == 0 ? 0 : rect.minY + view.textContainerInset.top
                view.setContentOffset(CGPoint(x: 0, y: min(max(0, proposed), max(0, view.contentSize.height - view.bounds.height))), animated: false)
                self.restoring = false
            }
        }
        func scrollViewDidScroll(_ scrollView: UIScrollView) {
            guard !restoring, let view, document.bodyLength > 0 else { return }
            if scrollView.isDragging || scrollView.isDecelerating { parent.onInteractionDismiss() }
            let point = CGPoint(x: 1, y: max(0, view.contentOffset.y - view.textContainerInset.top + 1))
            let glyph = view.layoutManager.glyphIndex(for: point, in: view.textContainer)
            let character = view.layoutManager.characterIndexForGlyph(at: glyph)
            currentOffset = min(max(0, character - document.bodyStart), document.bodyLength)
            publishPosition()
        }
        func publishPosition() {
            positionWork?.cancel()
            let offset = currentOffset
            let callback = parent.onPosition
            let work = DispatchWorkItem { callback(offset) }
            positionWork = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15, execute: work)
        }
        func textViewDidChangeSelection(_ textView: UITextView) {
            guard !restoring else { return }
            let selection = document.bodyRange(for: textView.selectedRange)
            DispatchQueue.main.async { [weak self] in self?.parent.onSelection(selection) }
        }
        func textView(_ textView: UITextView, editMenuForTextInRanges ranges: [NSValue], suggestedActions: [UIMenuElement]) -> UIMenu? {
            guard let first = ranges.first?.rangeValue else { return UIMenu(children: suggestedActions) }
            let combined = ranges.dropFirst().reduce(first) { NSUnionRange($0, $1.rangeValue) }
            let range = document.bodyRange(for: combined)
            guard range.length > 0 else { return UIMenu(children: suggestedActions) }
            let custom = UIMenu(options: .displayInline, children: [
                selectionAction("Markierung", image: "highlighter", kind: .marking, range: range),
                selectionAction("Notiz hinzufügen", image: "square.and.pencil", kind: .note, range: range),
                selectionAction("Suchen", image: "magnifyingglass", kind: .search, range: range)
            ])
            return UIMenu(children: [custom] + suggestedActions)
        }

        private func selectionAction(_ title: String, image: String, kind: ReaderSelectionAction, range: NSRange) -> UIAction {
            UIAction(title: title, image: UIImage(systemName: image)) { [weak self] _ in
                guard let self else { return }
                self.parent.onSelectionAction(kind, self.context(for: range))
            }
        }

        private func context(for range: NSRange) -> ReaderTextContext {
            let rect = viewportRect(for: range)
            let tools: (@MainActor () -> Void)? = writingToolsSupported(for: range) ? { @MainActor [weak self] in
                guard let self, let view = self.view else { return }
                self.parent.onInteractionDismiss()
                view.becomeFirstResponder()
                view.selectedRange = self.document.documentRange(for: range)
                guard view.canPerformAction(#selector(UIResponder.showWritingTools(_:)), withSender: view) else { return }
                view.showWritingTools(view)
            } : nil
            return ReaderTextContext(range: range, rect: rect, showWritingTools: tools, clearSelection: { [weak self] in
                guard let self, let view = self.view else { return }
                view.selectedRange = NSRange(location: view.selectedRange.location, length: 0)
                self.parent.onSelection(NSRange(location: range.location, length: 0))
            })
        }

        private func writingToolsSupported(for range: NSRange) -> Bool {
            guard UIWritingToolsCoordinator.isWritingToolsAvailable, let view else { return false }
            let previous = view.selectedRange
            let wasRestoring = restoring
            restoring = true
            view.selectedRange = document.documentRange(for: range)
            let supported = view.canPerformAction(#selector(UIResponder.showWritingTools(_:)), withSender: nil)
            view.selectedRange = previous
            restoring = wasRestoring
            return supported
        }

        private func viewportRect(for range: NSRange) -> CGRect {
            guard let view else { return .zero }
            let selected = document.documentRange(for: range)
            guard selected.length > 0 else { return .zero }
            view.layoutManager.ensureLayout(for: view.textContainer)
            let glyphs = view.layoutManager.glyphRange(forCharacterRange: selected, actualCharacterRange: nil)
            let rect = view.layoutManager.boundingRect(forGlyphRange: glyphs, in: view.textContainer)
                .offsetBy(dx: view.textContainerInset.left - view.contentOffset.x,
                          dy: view.textContainerInset.top - view.contentOffset.y)
            let visible = rect.intersection(CGRect(origin: .zero, size: view.bounds.size))
            return visible.isNull ? CGRect(x: view.textContainerInset.left, y: 16, width: 1, height: 24) : visible
        }

        private func openAnnotation(_ annotation: PersonalAnnotation) {
            if let view {
                let wasRestoring = restoring
                restoring = true
                view.selectedRange = NSRange(location: view.selectedRange.location, length: 0)
                restoring = wasRestoring
            }
            parent.onAnnotationTap(annotation.id, context(for: NSRange(location: annotation.location, length: annotation.length)))
        }

        func textViewWritingToolsWillBegin(_ textView: UITextView) { parent.onInteractionDismiss() }

        func textView(_ textView: UITextView, primaryActionFor textItem: UITextItem, defaultAction: UIAction) -> UIAction? {
            if textItem.range.location < document.text.length,
               let id = document.text.attribute(.readerAnnotationID, at: textItem.range.location, effectiveRange: nil) as? String,
               let annotation = parent.annotations.first(where: { $0.id == id }) {
                return UIAction(title: annotation.style.displayName) { [weak self] _ in self?.openAnnotation(annotation) }
            }
            guard case .link(let url) = textItem.content, let id = GAAnnotation.id(from: url),
                  let note = parent.passage.metadata.annotations.first(where: { $0.id == id }) else { return defaultAction }
            return UIAction(title: "Anmerkung \(note.id)") { [weak self] _ in self?.parent.onSourceNote(note) }
        }
        @objc func tapped(_ recognizer: UITapGestureRecognizer) {
            guard let view, !UIAccessibility.isVoiceOverRunning,
                  view.selectedRange.length == 0 else { return }
            let point = recognizer.location(in: view)
            let localPoint = CGPoint(x: point.x - view.textContainerInset.left, y: point.y - view.textContainerInset.top)
            let glyph = view.layoutManager.glyphIndex(for: localPoint, in: view.textContainer)
            let index = view.layoutManager.characterIndexForGlyph(at: glyph)
            guard index < document.text.length else { return }
            let glyphRect = view.layoutManager.boundingRect(forGlyphRange: NSRange(location: glyph, length: 1), in: view.textContainer)
            if glyphRect.insetBy(dx: -5, dy: -5).contains(localPoint),
               let id = document.text.attribute(.readerAnnotationID, at: index, effectiveRange: nil) as? String,
               let annotation = parent.annotations.first(where: { $0.id == id }) {
                openAnnotation(annotation)
                return
            }
            if glyphRect.insetBy(dx: -5, dy: -5).contains(localPoint), document.text.attribute(.link, at: index, effectiveRange: nil) != nil { return }
            parent.onToggleControls()
        }
        func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldRequireFailureOf otherGestureRecognizer: UIGestureRecognizer) -> Bool {
            // Native long press and double tap must finish choosing text before
            // a plain tap may open a personal marking or hide the reader controls.
            if otherGestureRecognizer is UILongPressGestureRecognizer { return true }
            if let tap = otherGestureRecognizer as? UITapGestureRecognizer { return tap.numberOfTapsRequired > 1 }
            return false
        }
        func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith otherGestureRecognizer: UIGestureRecognizer) -> Bool {
            if otherGestureRecognizer is UILongPressGestureRecognizer { return false }
            if let tap = otherGestureRecognizer as? UITapGestureRecognizer, tap.numberOfTapsRequired > 1 { return false }
            return true
        }
    }
}

final class ReaderUITextView: UITextView {
    var onWidthChange: (() -> Void)?
    private var lastWidth: CGFloat = 0
    override func layoutSubviews() {
        super.layoutSubviews()
        if abs(bounds.width - lastWidth) > 1 {
            lastWidth = bounds.width
            onWidthChange?()
        }
    }
}
#else
struct NativeReadingText: NSViewRepresentable {
    var passage: GAPassage
    var volumeTitle: String
    var languageCode: String
    var settings: ReaderTextSettings
    var annotations: [PersonalAnnotation]
    var searchText: String
    var anchor: ReaderAnchor
    var onPosition: (Int) -> Void
    var onSelection: (NSRange) -> Void
    var onToggleControls: () -> Void
    var onSourceNote: (GAAnnotation) -> Void
    var onAnnotationTap: (String, ReaderTextContext) -> Void = { _, _ in }
    var onSelectionAction: (ReaderSelectionAction, ReaderTextContext) -> Void = { _, _ in }
    var onInteractionDismiss: () -> Void = {}

    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> NSScrollView {
        let scroll = ReaderNSScrollView()
        scroll.onUserScroll = { [weak coordinator = context.coordinator] in coordinator?.parent.onInteractionDismiss() }
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true
        scroll.drawsBackground = false
        let storage = NSTextStorage()
        let manager = NSLayoutManager()
        storage.addLayoutManager(manager)
        let container = NSTextContainer(containerSize: NSSize(width: 0, height: CGFloat.greatestFiniteMagnitude))
        container.widthTracksTextView = true
        container.lineFragmentPadding = 0
        manager.addTextContainer(container)
        let textView = ReaderNSTextView(frame: .zero, textContainer: container)
        textView.isEditable = false
        textView.isSelectable = true
        textView.writingToolsBehavior = .limited
        textView.allowedWritingToolsResultOptions = []
        textView.isRichText = true
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
        textView.minSize = NSSize(width: 0, height: 0)
        textView.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        textView.delegate = context.coordinator
        textView.onTap = { [weak coordinator = context.coordinator] point in coordinator?.tapped(at: point) ?? false }
        textView.onEmptyTap = { [weak coordinator = context.coordinator] in coordinator?.emptyTap() }
        textView.onWidthChange = { [weak coordinator = context.coordinator] in coordinator?.layoutChanged() }
        scroll.documentView = textView
        scroll.contentView.postsBoundsChangedNotifications = true
        context.coordinator.scroll = scroll
        context.coordinator.view = textView
        context.coordinator.observer = NotificationCenter.default.addObserver(forName: NSView.boundsDidChangeNotification, object: scroll.contentView, queue: .main) { [weak coordinator = context.coordinator] _ in
            MainActor.assumeIsolated { coordinator?.scrolled() }
        }
        return scroll
    }
    func updateNSView(_ scroll: NSScrollView, context: Context) { context.coordinator.update(self) }
    static func dismantleNSView(_ nsView: NSScrollView, coordinator: Coordinator) {
        coordinator.positionWork?.cancel()
        coordinator.parent.onPosition(coordinator.currentOffset)
        if let observer = coordinator.observer { NotificationCenter.default.removeObserver(observer) }
    }

    @MainActor final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: NativeReadingText
        weak var scroll: NSScrollView?
        weak var view: ReaderNSTextView?
        var observer: NSObjectProtocol?
        var document = ReaderDocument(text: NSAttributedString(string: ""), bodyStart: 0, bodyLength: 0)
        var signature = ""
        var anchorID: UUID?
        var currentOffset = 0
        var restoring = false
        var positionWork: DispatchWorkItem?
        init(_ parent: NativeReadingText) { self.parent = parent }
        func update(_ parent: NativeReadingText) {
            self.parent = parent
            guard let view else { return }
            view.backgroundColor = NSColor(parent.settings.palette.background)
            view.textColor = NSColor(parent.settings.palette.foreground)
            view.insertionPointColor = NSColor(parent.settings.palette.accent)
            view.linkTextAttributes = [.foregroundColor: NSColor(parent.settings.palette.accent)]
            view.setAccessibilityCustomActions(parent.passage.metadata.annotations.map { note in
                NSAccessibilityCustomAction(name: "Anmerkung \(note.id)", handler: { [weak self] in
                    self?.parent.onSourceNote(note)
                    return true
                })
            })
            view.setAccessibilityCustomActions((view.accessibilityCustomActions() ?? []) + parent.annotations.filter { !$0.isBookmark }.map { annotation in
                NSAccessibilityCustomAction(name: "\(annotation.style.displayName): \(annotation.quote.prefix(60))", handler: { [weak self] in
                    self?.openAnnotation(annotation)
                    return true
                })
            })
            let nextSignature = "\(parent.passage.id):\(parent.settings.signature):\(parent.annotations):\(parent.searchText)"
            let requested = anchorID != parent.anchor.requestID
            if signature != nextSignature {
                signature = nextSignature
                let selection = view.selectedRange()
                document = readingDocument(passage: parent.passage, title: parent.volumeTitle, settings: parent.settings, annotations: parent.annotations, searchText: parent.searchText)
                restoring = true
                view.textStorage?.setAttributedString(document.text)
                if NSMaxRange(selection) <= document.text.length { view.setSelectedRange(selection) }
                updateInsets()
                restore(requested ? parent.anchor.offset : currentOffset)
            } else if requested { restore(parent.anchor.offset) }
            anchorID = parent.anchor.requestID
        }
        func updateInsets() {
            guard let view, let scroll else { return }
            let width = scroll.contentSize.width
            view.textContainerInset = NSSize(width: max(parent.settings.margin, (width - 760) / 2), height: 28)
            view.setFrameSize(NSSize(width: width, height: max(view.frame.height, scroll.contentSize.height)))
        }
        func layoutChanged() {
            DispatchQueue.main.async { [weak self] in self?.parent.onInteractionDismiss() }
            updateInsets()
            restore(currentOffset)
        }
        func restore(_ offset: Int) {
            currentOffset = min(max(offset, 0), document.bodyLength)
            restoring = true
            DispatchQueue.main.async { [weak self] in
                guard let self, let view = self.view, let scroll = self.scroll,
                      let manager = view.layoutManager, let container = view.textContainer else { return }
                manager.ensureLayout(for: container)
                let location = min(self.document.bodyStart + self.currentOffset, max(0, self.document.text.length - 1))
                let glyph = manager.glyphIndexForCharacter(at: location)
                let rect = manager.lineFragmentRect(forGlyphAt: glyph, effectiveRange: nil)
                let proposed = self.currentOffset == 0 ? 0 : rect.minY + view.textContainerInset.height
                scroll.contentView.scroll(to: NSPoint(x: 0, y: min(max(0, proposed), max(0, view.frame.height - scroll.contentSize.height))))
                scroll.reflectScrolledClipView(scroll.contentView)
                self.restoring = false
            }
        }
        func scrolled() {
            guard !restoring, let view, let manager = view.layoutManager, let container = view.textContainer,
                  let scroll, document.bodyLength > 0 else { return }
            if NSApp.currentEvent?.type == .leftMouseDragged { parent.onInteractionDismiss() }
            let point = NSPoint(x: 1, y: max(0, scroll.contentView.bounds.minY - view.textContainerInset.height + 1))
            let glyph = manager.glyphIndex(for: point, in: container)
            currentOffset = min(max(0, manager.characterIndexForGlyph(at: glyph) - document.bodyStart), document.bodyLength)
            positionWork?.cancel()
            let offset = currentOffset
            let callback = parent.onPosition
            let work = DispatchWorkItem { callback(offset) }
            positionWork = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15, execute: work)
        }
        func textViewDidChangeSelection(_ notification: Notification) {
            guard !restoring, let view else { return }
            let selection = document.bodyRange(for: view.selectedRange())
            DispatchQueue.main.async { [weak self] in self?.parent.onSelection(selection) }
        }
        func textViewWritingToolsWillBegin(_ textView: NSTextView) { parent.onInteractionDismiss() }

        func textView(_ textView: NSTextView, clickedOnLink link: Any, at charIndex: Int) -> Bool {
            if charIndex < document.text.length,
               let id = document.text.attribute(.readerAnnotationID, at: charIndex, effectiveRange: nil) as? String,
               let annotation = parent.annotations.first(where: { $0.id == id }) {
                openAnnotation(annotation)
                return true
            }
            guard let url = link as? URL, let id = GAAnnotation.id(from: url),
                  let note = parent.passage.metadata.annotations.first(where: { $0.id == id }) else { return false }
            parent.onSourceNote(note)
            return true
        }
        func tapped(at point: NSPoint) -> Bool {
            guard let view, let manager = view.layoutManager, let container = view.textContainer else { return false }
            let local = NSPoint(x: point.x - view.textContainerOrigin.x, y: point.y - view.textContainerOrigin.y)
            let glyph = manager.glyphIndex(for: local, in: container)
            let index = manager.characterIndexForGlyph(at: glyph)
            guard index < document.text.length else { return false }
            let glyphRect = manager.boundingRect(forGlyphRange: NSRange(location: glyph, length: 1), in: container)
            if glyphRect.insetBy(dx: -5, dy: -5).contains(local),
               let id = document.text.attribute(.readerAnnotationID, at: index, effectiveRange: nil) as? String,
               let annotation = parent.annotations.first(where: { $0.id == id }) {
                openAnnotation(annotation)
                return true
            }
            return glyphRect.insetBy(dx: -5, dy: -5).contains(local) && document.text.attribute(.link, at: index, effectiveRange: nil) != nil
        }

        func emptyTap() {
            guard let view, view.selectedRange().length == 0 else { return }
            parent.onToggleControls()
        }

        func textView(_ textView: NSTextView, menu: NSMenu, for event: NSEvent, at charIndex: Int) -> NSMenu? {
            let range = document.bodyRange(for: textView.selectedRange())
            guard range.length > 0 else { return menu }
            let additions: [(String, ReaderSelectionAction)] = [("Markierung", .marking), ("Notiz hinzufügen", .note), ("Suchen", .search)]
            menu.insertItem(.separator(), at: 0)
            for (index, addition) in additions.enumerated() {
                let item = ReaderSelectionMenuItem(title: addition.0, kind: addition.1, range: range)
                item.target = self
                item.action = #selector(performSelectionAction(_:))
                menu.insertItem(item, at: index)
            }
            return menu
        }

        @objc private func performSelectionAction(_ item: ReaderSelectionMenuItem) {
            parent.onSelectionAction(item.kind, context(for: item.range))
        }

        private func context(for range: NSRange) -> ReaderTextContext {
            let tools: (@MainActor () -> Void)? = writingToolsSupported(for: range) ? { @MainActor [weak self] in
                guard let self, let view = self.view else { return }
                self.parent.onInteractionDismiss()
                view.window?.makeFirstResponder(view)
                view.setSelectedRange(self.document.documentRange(for: range))
                let item = NSMenuItem(title: "Writing Tools", action: #selector(NSResponder.showWritingTools(_:)), keyEquivalent: "")
                guard view.validateUserInterfaceItem(item) else { return }
                view.showWritingTools(view)
            } : nil
            return ReaderTextContext(range: range, rect: viewportRect(for: range), showWritingTools: tools, clearSelection: { [weak self] in
                guard let self, let view = self.view else { return }
                view.setSelectedRange(NSRange(location: view.selectedRange().location, length: 0))
                self.parent.onSelection(NSRange(location: range.location, length: 0))
            })
        }

        private func writingToolsSupported(for range: NSRange) -> Bool {
            guard NSWritingToolsCoordinator.isWritingToolsAvailable, let view else { return false }
            let previous = view.selectedRange()
            let wasRestoring = restoring
            restoring = true
            view.setSelectedRange(document.documentRange(for: range))
            let item = NSMenuItem(title: "Writing Tools", action: #selector(NSResponder.showWritingTools(_:)), keyEquivalent: "")
            let supported = view.validateUserInterfaceItem(item)
            view.setSelectedRange(previous)
            restoring = wasRestoring
            return supported
        }

        private func viewportRect(for range: NSRange) -> CGRect {
            guard let view, let scroll, let manager = view.layoutManager, let container = view.textContainer else { return .zero }
            let selected = document.documentRange(for: range)
            guard selected.length > 0 else { return .zero }
            manager.ensureLayout(for: container)
            let glyphs = manager.glyphRange(forCharacterRange: selected, actualCharacterRange: nil)
            let rect = manager.boundingRect(forGlyphRange: glyphs, in: container)
                .offsetBy(dx: view.textContainerOrigin.x - scroll.contentView.bounds.minX,
                          dy: view.textContainerOrigin.y - scroll.contentView.bounds.minY)
            let visible = rect.intersection(CGRect(origin: .zero, size: scroll.contentSize))
            return visible.isNull ? CGRect(x: view.textContainerOrigin.x, y: 16, width: 1, height: 24) : visible
        }

        private func openAnnotation(_ annotation: PersonalAnnotation) {
            if let view {
                let wasRestoring = restoring
                restoring = true
                view.setSelectedRange(NSRange(location: view.selectedRange().location, length: 0))
                restoring = wasRestoring
            }
            parent.onAnnotationTap(annotation.id, context(for: NSRange(location: annotation.location, length: annotation.length)))
        }
    }
}

private final class ReaderNSScrollView: NSScrollView {
    var onUserScroll: (() -> Void)?
    override func scrollWheel(with event: NSEvent) {
        onUserScroll?()
        super.scrollWheel(with: event)
    }
}

private final class ReaderSelectionMenuItem: NSMenuItem {
    let kind: ReaderSelectionAction
    let range: NSRange
    init(title: String, kind: ReaderSelectionAction, range: NSRange) {
        self.kind = kind
        self.range = range
        super.init(title: title, action: nil, keyEquivalent: "")
    }
    required init(coder: NSCoder) { fatalError("Reader selection actions are created programmatically") }
}

final class ReaderNSTextView: NSTextView {
    var onTap: ((NSPoint) -> Bool)?
    var onEmptyTap: (() -> Void)?
    var onWidthChange: (() -> Void)?
    private var lastWidth: CGFloat = 0
    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        if abs(newSize.width - lastWidth) > 1 {
            lastWidth = newSize.width
            onWidthChange?()
        }
    }
    override func mouseDown(with event: NSEvent) {
        let point = convert(event.locationInWindow, from: nil)
        super.mouseDown(with: event)
        guard event.clickCount == 1, selectedRange().length == 0 else { return }
        if onTap?(point) != true { onEmptyTap?() }
    }
}
#endif
