import Foundation

/// Builds a self-contained EPUB 3 without a platform-specific archiving library.
/// The returned file remains available until the caller finishes sharing it.
enum EPUBExporter: Sendable {
    static func export(volume: GAVolume, modifiedAt: Date = Date()) throws -> URL {
        try Task.checkCancellation()
        guard !volume.passages.isEmpty else { throw EPUBExportError.noReadableContent }
        if let expected = volume.catalogPassageCount, expected > volume.passages.count {
            throw EPUBExportError.incompleteContent(expected: expected, actual: volume.passages.count)
        }
        var passageIDs = Set<String>()
        for (index, passage) in volume.passages.enumerated() {
            try Task.checkCancellation()
            guard !passage.id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  passageIDs.insert(passage.id).inserted else {
                throw EPUBExportError.invalidPassageIdentifiers
            }
            guard !passage.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                throw EPUBExportError.unreadablePassage(index: index + 1)
            }
        }
        let language = volume.languageCode.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !volume.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !volume.id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !volume.gaNumber.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              language.range(of: "^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$", options: .regularExpression) != nil,
              modifiedAt.timeIntervalSince1970.isFinite else {
            throw EPUBExportError.invalidMetadata
        }
        let labels = Labels(isGerman: language.lowercased().hasPrefix("de"))
        var entries: [ZIPEntry] = [
            ZIPEntry(path: "mimetype", text: "application/epub+zip"),
            ZIPEntry(path: "META-INF/container.xml", text: """
            <?xml version="1.0" encoding="UTF-8"?>
            <container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
              <rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml" /></rootfiles>
            </container>
            """),
            ZIPEntry(path: "EPUB/package.opf", text: try package(volume: volume, language: language, modifiedAt: modifiedAt)),
            ZIPEntry(path: "EPUB/styles.css", text: stylesheet),
            ZIPEntry(path: "EPUB/title.xhtml", text: try titlePage(volume: volume, language: language, labels: labels)),
            ZIPEntry(path: "EPUB/nav.xhtml", text: try navigation(volume: volume, language: language, labels: labels))
        ]
        for (index, passage) in volume.passages.enumerated() {
            try Task.checkCancellation()
            entries.append(ZIPEntry(path: "EPUB/\(chapterPath(index))", text: try chapter(
                passage: passage, index: index, language: language, labels: labels
            )))
        }
        let archive = try zip(entries)
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("GA-EPUB-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = directory.appendingPathComponent(safeFilename("\(volume.gaNumber) - \(volume.title)") + ".epub")
        do {
            try Task.checkCancellation()
            try archive.write(to: url, options: .atomic)
            return url
        } catch {
            try? FileManager.default.removeItem(at: directory)
            throw error
        }
    }

    private static func package(volume: GAVolume, language: String, modifiedAt: Date) throws -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        let identifierPart = volume.id.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? volume.id
        let manifest = volume.passages.indices.map {
            "<item id=\"chapter-\($0 + 1)\" href=\"\(chapterPath($0))\" media-type=\"application/xhtml+xml\" />"
        }.joined(separator: "\n")
        let spine = volume.passages.indices.map { "<itemref idref=\"chapter-\($0 + 1)\" />" }.joined(separator: "\n")
        let labels = Labels(isGerman: language.lowercased().hasPrefix("de"))
        let description = [volume.publicationState == .publishedSeed ? labels.excerpt : "", volume.subtitle, volume.sourceSummary]
            .filter { !$0.isEmpty }.joined(separator: "\n\n")
        return """
        <?xml version="1.0" encoding="UTF-8"?>
        <package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="publication-id" xml:lang="\(try xml(language))">
          <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
            <dc:identifier id="publication-id">urn:ga-reader:\(try xml(identifierPart)):\(try xml(language))</dc:identifier>
            <dc:identifier>\(try xml(volume.gaNumber))</dc:identifier>
            <dc:title>\(try xml(volume.title))</dc:title>
            <dc:creator>Rudolf Steiner</dc:creator>
            <dc:language>\(try xml(language))</dc:language>
            <dc:description>\(try xml(description))</dc:description>
            <meta property="dcterms:modified">\(formatter.string(from: modifiedAt))</meta>
          </metadata>
          <manifest>
            <item id="title" href="title.xhtml" media-type="application/xhtml+xml" />
            <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" />
            <item id="css" href="styles.css" media-type="text/css" />
            \(manifest)
          </manifest>
          <spine>
            <itemref idref="title" />
            <itemref idref="nav" />
            \(spine)
          </spine>
        </package>
        """
    }

    private static func titlePage(volume: GAVolume, language: String, labels: Labels) throws -> String {
        var details = "<p class=\"ga-number\">\(try xml(volume.gaNumber))</p>\n<h1>\(try xml(volume.title))</h1>"
        if !volume.subtitle.isEmpty { details += "\n<p class=\"subtitle\">\(try xml(volume.subtitle))</p>" }
        details += "\n<p class=\"author\">Rudolf Steiner</p>"
        if !volume.yearLabel.isEmpty { details += "\n<p>\(try xml(volume.yearLabel))</p>" }
        if volume.publicationState == .publishedSeed { details += "\n<p class=\"excerpt\">\(labels.excerpt)</p>" }
        details += "\n<section class=\"edition\"><h2>\(labels.edition)</h2>"
        if !volume.sourceSummary.isEmpty { details += "\n\(try paragraphs(volume.sourceSummary))" }
        details += "\n</section>"
        return try document(title: volume.title, language: language, body: details)
    }

    private static func navigation(volume: GAVolume, language: String, labels: Labels) throws -> String {
        var links = "<li><a href=\"title.xhtml\">\(try xml(volume.title))</a></li>"
        var group: String?
        for (index, passage) in volume.passages.enumerated() {
            let nextGroup = passage.metadata.groupTitle.flatMap { $0.isEmpty ? nil : $0 }
            if nextGroup != group {
                if group != nil { links += "</ol></li>" }
                if let nextGroup { links += "\n<li class=\"main-division\"><a href=\"\(chapterPath(index))\">\(try xml(nextGroup))</a><ol>" }
                group = nextGroup
            }
            let sections = passage.metadata.validReadingSections(in: passage.text, passageTitle: passage.title)
            if sections.isEmpty {
                links += "\n<li><a href=\"\(chapterPath(index))\">\(try xml(chapterTitle(passage, index: index, labels: labels)))</a>\(try headingNavigation(passage, chapter: chapterPath(index)))</li>"
            } else {
                for (sectionIndex, section) in sections.enumerated() {
                    links += "\n<li class=\"work-unit\" data-label-kind=\"\(section.labelKind.rawValue)\"><a href=\"\(chapterPath(index))#reading-section-\(sectionIndex + 1)\">\(try xml(section.title))</a>\(try headingNavigation(passage, chapter: chapterPath(index), section: section))</li>"
                }
            }
        }
        if group != nil { links += "</ol></li>" }
        var pages = ""
        var seenPages = Set<Int>()
        for (index, passage) in volume.passages.enumerated() {
            for (anchorIndex, anchor) in passage.metadata.validPageAnchors(in: passage.text).enumerated() where seenPages.insert(anchor.page).inserted {
                pages += "\n<li><a href=\"\(chapterPath(index))#\(pageBreakID(anchor, index: anchorIndex))\">\(anchor.page)</a></li>"
            }
        }
        let pageList = pages.isEmpty ? "" : "\n<nav epub:type=\"page-list\" id=\"page-list\"><h2>\(labels.pages)</h2><ol>\(pages)</ol></nav>"
        return try document(title: labels.contents, language: language, body: """
        <nav epub:type="toc" id="toc"><h1>\(labels.contents)</h1><ol>
        \(links)
        </ol></nav>\(pageList)
        """)
    }

    private static func headingNavigation(_ passage: GAPassage, chapter: String, section: GAReadingSection? = nil) throws -> String {
        let body = passage.text as NSString
        let headings = passage.metadata.validReadingBlocks(in: passage.text).enumerated().filter { item in
            guard item.element.kind == .heading else { return false }
            guard let section else { return true }
            return item.element.startOffset >= section.startOffset && item.element.endOffset <= section.endOffset &&
                !(section.labelKind == .sourceTitle && item.element.startOffset == section.startOffset && body.substring(with: item.element.range) == section.title)
        }
        var index = 0
        func list(after parentLevel: Int) throws -> String {
            var children = ""
            while index < headings.count, (headings[index].element.level ?? 2) > parentLevel {
                let item = headings[index]
                index += 1
                children += "<li><a href=\"\(chapter)#reading-block-\(item.offset + 1)\">\(try xml(body.substring(with: item.element.range)))</a>\(try list(after: item.element.level ?? 2))</li>"
            }
            return children.isEmpty ? "" : "<ol>\(children)</ol>"
        }
        return try list(after: 0)
    }

    private static func chapter(passage: GAPassage, index: Int, language: String, labels: Labels) throws -> String {
        let title = chapterTitle(passage, index: index, labels: labels)
        let sections = passage.metadata.validReadingSections(in: passage.text, passageTitle: passage.title)
        var body = "<section id=\"chapter\">"
        if sections.isEmpty { body += "<h1 id=\"chapter-title\">\(try xml(title))</h1>" }
        if let group = passage.metadata.groupTitle, !group.isEmpty {
            body += "\n<p class=\"group-title\">\(try xml(group))</p>"
        }
        let pageLabel = passage.gaPage.flatMap { $0.isEmpty ? nil : $0 } ?? passage.metadata.pageNumberLabel
        let provenance = [passage.sourceLabel.isEmpty ? nil : passage.sourceLabel, pageLabel].compactMap { $0 }.joined(separator: " · ")
        if !provenance.isEmpty { body += "\n<p class=\"provenance\">\(try xml(provenance))</p>" }
        var references = AnnotationReferences(passage)
        body += "\n<div class=\"passage-text\">\(try readingContent(passage, references: &references))</div>\n</section>"
        if !passage.metadata.annotations.isEmpty {
            body += "\n<section class=\"edition-notes\"><h2>\(labels.notes)</h2><ol>"
            for (index, annotation) in passage.metadata.annotations.enumerated() {
                let marker = annotation.marker.isEmpty ? annotation.id : annotation.marker
                let firstReference = references.firstRendered[index]
                let backlink = firstReference.map { " <a href=\"#annotation-reference-\(index + 1)-\($0.location)\">↩</a>" } ?? ""
                body += "\n<li id=\"annotation-\(index + 1)\" epub:type=\"footnote\"><p><strong>\(try xml(marker))</strong>\(backlink)</p>\(try paragraphs(annotation.text))</li>"
            }
            body += "\n</ol></section>"
        }
        return try document(title: title, language: language, body: body)
    }

    private static func document(title: String, language: String, body: String) throws -> String {
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="\(try xml(language))" xml:lang="\(try xml(language))">
          <head><meta charset="utf-8" /><title>\(try xml(title))</title><link rel="stylesheet" type="text/css" href="styles.css" /></head>
          <body>\(body)</body>
        </html>
        """
    }

    private static func chapterTitle(_ passage: GAPassage, index: Int, labels: Labels) -> String {
        passage.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "\(labels.section) \(index + 1)" : passage.title
    }

    private static func chapterPath(_ index: Int) -> String { "chapter-\(index + 1).xhtml" }

    /// Overlapping legacy markers may not all produce links. Backlinks use only
    /// references that were actually emitted, rather than candidate matches.
    private struct AnnotationReferences {
        let ranges: [(index: Int, range: NSRange)]
        var firstRendered: [Int: NSRange] = [:]

        init(_ passage: GAPassage) {
            ranges = passage.metadata.annotations.enumerated().flatMap { index, note in
                note.markerRanges(in: passage.text).map { (index: index, range: $0) }
            }.sorted { $0.range.location < $1.range.location }
        }
    }

    private static func readingContent(_ passage: GAPassage, references: inout AnnotationReferences) throws -> String {
        let blocks = passage.metadata.validReadingBlocks(in: passage.text)
        if !blocks.isEmpty {
            let sections = passage.metadata.validReadingSections(in: passage.text, passageTitle: passage.title)
            let body = passage.text as NSString
            var content = ""
            var offset = 0
            for (index, block) in blocks.enumerated() {
                let unitStart = sections.enumerated().first { $0.element.startOffset == block.startOffset }
                let sourceLabel = unitStart?.element.labelKind == .sourceTitle && (passage.text as NSString).substring(with: block.range) == unitStart?.element.title
                let tag = block.kind == .heading ? (sourceLabel ? "h1" : "h\(min(6, max(2, (block.level ?? 2) + (sections.isEmpty ? 1 : 0))))") : "p"
                let poemClass = block.kind == .verse && block.poemStart == true ? " poem-start" : ""
                let joinedClass = index + 1 < blocks.count && blocks[index + 1].startOffset == block.endOffset + 1 &&
                    body.substring(with: NSRange(location: block.endOffset, length: 1)) == "\n" ? " joined-next" : ""
                content += pageBreaks(passage, from: offset, to: block.startOffset)
                if let unitStart {
                    let labelID = sourceLabel ? "reading-block-\(index + 1)" :
                        unitStart.offset == 0 && unitStart.element.labelKind == .sourceTitle && unitStart.element.title == passage.title ? "chapter-title" : "reading-section-label-\(unitStart.offset + 1)"
                    content += "\n<section id=\"reading-section-\(unitStart.offset + 1)\" class=\"reading-section\" data-section-id=\"\(try xml(unitStart.element.id))\" data-label-kind=\"\(unitStart.element.labelKind.rawValue)\" aria-labelledby=\"\(labelID)\">"
                    if labelID == "chapter-title", !sourceLabel {
                        content += "\n<h1 id=\"chapter-title\" class=\"unit-preamble\">\(try xml(unitStart.element.title))</h1>"
                    }
                }
                let labelClass = sourceLabel ? " unit-source-title" : ""
                let inline: String
                if let unitStart, unitStart.element.labelKind == .incipit {
                    let line = (passage.text as NSString).substring(with: block.range).components(separatedBy: "\n").first ?? ""
                    let lineLength = (line as NSString).length
                    inline = "<span id=\"reading-section-label-\(unitStart.offset + 1)\" class=\"unit-incipit\">\(try readingInline(passage, range: NSRange(location: block.startOffset, length: lineLength), references: &references))</span>" +
                        (try readingInline(passage, range: NSRange(location: block.startOffset + lineLength, length: block.range.length - lineLength), references: &references))
                } else {
                    inline = try readingInline(passage, range: block.range, references: &references)
                }
                content += "\n<\(tag) id=\"reading-block-\(index + 1)\" class=\"reading-\(block.kind.rawValue)\(poemClass)\(labelClass)\(joinedClass)\">\(inline)</\(tag)>"
                if sections.contains(where: { $0.endOffset == block.endOffset }) { content += "\n</section>" }
                offset = block.endOffset
            }
            content += pageBreaks(passage, from: offset, to: (passage.text as NSString).length + 1)
            return content
        }
        // Keep legacy paragraphs and CRLF handling, while allowing old notes to link.
        let body = passage.text as NSString
        let lines = try NSRegularExpression(pattern: "[^\\r\\n]*(?:\\r\\n|\\r|\\n|$)")
        var ranges: [NSRange] = []
        var start: Int?
        var end = 0
        for match in lines.matches(in: passage.text, range: NSRange(location: 0, length: body.length)) {
            let line = body.substring(with: match.range).trimmingCharacters(in: .newlines)
            if line.trimmingCharacters(in: .whitespaces).isEmpty {
                if let beginning = start { ranges.append(NSRange(location: beginning, length: end - beginning)); start = nil }
            } else {
                if start == nil { start = match.range.location }
                end = match.range.location + (line as NSString).length
            }
        }
        if let start { ranges.append(NSRange(location: start, length: end - start)) }
        var content = ""
        var offset = 0
        for range in ranges {
            content += pageBreaks(passage, from: offset, to: range.location)
            content += "\n<p>\(try readingInline(passage, range: range, references: &references))</p>"
            offset = NSMaxRange(range)
        }
        content += pageBreaks(passage, from: offset, to: body.length + 1)
        return content
    }

    private static func pageBreakID(_ anchor: GAPageAnchor, index: Int) -> String { "page-\(anchor.page)-\(index + 1)" }

    private static func pageBreak(_ anchor: GAPageAnchor, index: Int) -> String {
        "<span id=\"\(pageBreakID(anchor, index: index))\" epub:type=\"pagebreak\" role=\"doc-pagebreak\" title=\"\(anchor.page)\" aria-label=\"\(anchor.page)\"></span>"
    }

    private static func pageBreaks(_ passage: GAPassage, from start: Int, to end: Int) -> String {
        passage.metadata.validPageAnchors(in: passage.text).enumerated().filter { $0.element.startOffset >= start && $0.element.startOffset < end }
            .map { pageBreak($0.element, index: $0.offset) }.joined()
    }

    private static func readingInline(_ passage: GAPassage, range: NSRange, references: inout AnnotationReferences) throws -> String {
        let body = passage.text as NSString
        var result = ""
        var start = range.location
        func fragment(_ range: NSRange) throws -> String {
            func escaped(_ piece: NSRange) throws -> String {
                try xml(body.substring(with: piece).replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\r", with: "\n"))
                .replacingOccurrences(of: "\n", with: "<br />")
            }
            var content = ""
            var offset = range.location
            for (index, anchor) in passage.metadata.validPageAnchors(in: passage.text).enumerated() where anchor.startOffset >= range.location && anchor.startOffset < NSMaxRange(range) {
                content += try escaped(NSRange(location: offset, length: anchor.startOffset - offset))
                content += pageBreak(anchor, index: index)
                offset = anchor.startOffset
            }
            content += try escaped(NSRange(location: offset, length: NSMaxRange(range) - offset))
            return content
        }
        for reference in references.ranges where reference.range.location >= start && NSMaxRange(reference.range) <= NSMaxRange(range) {
            guard reference.range.location >= start else { continue }
            result += try fragment(NSRange(location: start, length: reference.range.location - start))
            result += "<a epub:type=\"noteref\" href=\"#annotation-\(reference.index + 1)\" id=\"annotation-reference-\(reference.index + 1)-\(reference.range.location)\">\(try fragment(reference.range))</a>"
            if references.firstRendered[reference.index] == nil { references.firstRendered[reference.index] = reference.range }
            start = NSMaxRange(reference.range)
        }
        result += try fragment(NSRange(location: start, length: NSMaxRange(range) - start))
        return result
    }

    /// Plain text is escaped, never interpreted as markup. Blank lines divide
    /// paragraphs; single line breaks remain visible, including in verse.
    private static func paragraphs(_ text: String) throws -> String {
        let normalized = text.replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\r", with: "\n")
        var paragraphs: [String] = []
        var lines: [String] = []
        for line in normalized.components(separatedBy: "\n") {
            if line.trimmingCharacters(in: .whitespaces).isEmpty {
                if !lines.isEmpty { paragraphs.append(lines.joined(separator: "\n")); lines.removeAll(keepingCapacity: true) }
            } else {
                lines.append(line)
            }
        }
        if !lines.isEmpty { paragraphs.append(lines.joined(separator: "\n")) }
        return try paragraphs.map { "<p>\(try xml($0).replacingOccurrences(of: "\n", with: "<br />"))</p>" }.joined(separator: "\n")
    }

    private static func xml(_ text: String) throws -> String {
        guard text.unicodeScalars.allSatisfy({ scalar in
            switch scalar.value {
            case 0x9, 0xA, 0xD, 0x20...0xD7FF, 0xE000...0xFFFD, 0x10000...0x10FFFF: true
            default: false
            }
        }) else { throw EPUBExportError.invalidXMLCharacters }
        return text.replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\"", with: "&quot;")
            .replacingOccurrences(of: "'", with: "&apos;")
    }

    private static func safeFilename(_ title: String) -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: " -_"))
        let safe = String(String.UnicodeScalarView(title.unicodeScalars.map { allowed.contains($0) ? $0 : "-" }))
            .components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.joined(separator: " ")
            .decomposedStringWithCanonicalMapping // File URLs on Apple platforms normalize names to this form.
        var prefix = ""
        for character in safe {
            guard prefix.utf8.count + String(character).utf8.count <= 160 else { break }
            prefix.append(character)
        }
        let result = prefix.trimmingCharacters(in: CharacterSet(charactersIn: " -_"))
        return result.isEmpty ? "GA-Book" : result
    }

    private struct Labels {
        let contents: String
        let edition: String
        let notes: String
        let section: String
        let excerpt: String
        let pages: String
        init(isGerman: Bool) {
            contents = isGerman ? "Inhaltsverzeichnis" : "Contents"
            edition = isGerman ? "Angaben zur Ausgabe" : "Edition information"
            notes = isGerman ? "Anmerkungen der Ausgabe" : "Edition notes"
            section = isGerman ? "Abschnitt" : "Section"
            excerpt = isGerman ? "Textauszug" : "Excerpt"
            pages = isGerman ? "Seiten" : "Pages"
        }
    }

    private static let stylesheet = """
    body { font-family: serif; line-height: 1.5; margin: 5%; }
    h1, h2, h3, h4, h5, h6 { line-height: 1.2; page-break-after: avoid; }
    h1 { font-size: 1.6em; }
    h2 { font-size: 1.2em; }
    p { margin: 0 0 1em; orphans: 2; widows: 2; }
    p.joined-next { margin-bottom: 0; }
    .ga-number, .provenance { font-size: 0.85em; }
    .subtitle { font-size: 1.2em; }
    .group-title { font-size: 0.9em; font-weight: bold; }
    .reading-verse { line-height: 1.5; }
    .reading-verse.poem-start { margin-top: 1.35em; }
    .reading-section { margin-top: 2.4em; padding-top: 1.2em; border-top: 1px solid; }
    .reading-section:first-of-type { margin-top: 0; padding-top: 0; border-top: 0; }
    .reading-section > :first-child { margin-top: 0; }
    .unit-source-title { font-size: 1.6em; font-weight: bold; line-height: 1.2; }
    .reading-attribution, .reading-note { font-size: 0.88em; }
    .author { font-size: 1.1em; }
    .edition, .edition-notes { margin-top: 2em; font-size: 0.9em; }
    nav li { margin-bottom: 0.5em; }
    """

    private struct ZIPEntry {
        let path: String
        let data: Data
        init(path: String, text: String) {
            self.path = path
            self.data = Data(text.utf8)
        }
    }

    /// OCF permits stored entries. Using method 0 keeps the implementation
    /// Foundation-only, with `mimetype` first and no ZIP extra fields.
    private static func zip(_ entries: [ZIPEntry]) throws -> Data {
        guard entries.count < Int(UInt16.max) else { throw EPUBExportError.archiveTooLarge }
        var archive = Data()
        var central = Data()
        for entry in entries {
            try Task.checkCancellation()
            let name = Data(entry.path.utf8)
            guard let size = UInt32(exactly: entry.data.count),
                  let offset = UInt32(exactly: archive.count),
                  let nameLength = UInt16(exactly: name.count),
                  UInt64(archive.count) + UInt64(entry.data.count) + UInt64(name.count) + 30 < UInt64(UInt32.max) else {
                throw EPUBExportError.archiveTooLarge
            }
            let crc = crc32(entry.data)
            archive.appendLittleEndian(UInt32(0x04034B50))
            archive.appendLittleEndian(UInt16(20))
            archive.appendLittleEndian(UInt16(0x0800)) // UTF-8 filenames
            archive.appendLittleEndian(UInt16(0)) // Stored, no compression
            archive.appendLittleEndian(UInt16(0)) // 00:00:00
            archive.appendLittleEndian(UInt16(0x0021)) // 1980-01-01
            archive.appendLittleEndian(crc)
            archive.appendLittleEndian(size)
            archive.appendLittleEndian(size)
            archive.appendLittleEndian(nameLength)
            archive.appendLittleEndian(UInt16(0)) // No extra field
            archive.append(name)
            archive.append(entry.data)

            central.appendLittleEndian(UInt32(0x02014B50))
            central.appendLittleEndian(UInt16(20)) // ZIP 2.0, MS-DOS creator
            central.appendLittleEndian(UInt16(20))
            central.appendLittleEndian(UInt16(0x0800))
            central.appendLittleEndian(UInt16(0))
            central.appendLittleEndian(UInt16(0))
            central.appendLittleEndian(UInt16(0x0021))
            central.appendLittleEndian(crc)
            central.appendLittleEndian(size)
            central.appendLittleEndian(size)
            central.appendLittleEndian(nameLength)
            central.appendLittleEndian(UInt16(0)) // Extra length
            central.appendLittleEndian(UInt16(0)) // Comment length
            central.appendLittleEndian(UInt16(0)) // Disk number
            central.appendLittleEndian(UInt16(0)) // Internal attributes
            central.appendLittleEndian(UInt32(0)) // External attributes
            central.appendLittleEndian(offset)
            central.append(name)
        }
        guard let centralOffset = UInt32(exactly: archive.count),
              let centralSize = UInt32(exactly: central.count),
              UInt64(archive.count) + UInt64(central.count) + 22 < UInt64(UInt32.max) else {
            throw EPUBExportError.archiveTooLarge
        }
        archive.append(central)
        archive.appendLittleEndian(UInt32(0x06054B50))
        archive.appendLittleEndian(UInt16(0)) // This disk
        archive.appendLittleEndian(UInt16(0)) // Central directory disk
        archive.appendLittleEndian(UInt16(entries.count))
        archive.appendLittleEndian(UInt16(entries.count))
        archive.appendLittleEndian(centralSize)
        archive.appendLittleEndian(centralOffset)
        archive.appendLittleEndian(UInt16(0)) // Archive comment
        return archive
    }

    private static let crcTable: [UInt32] = (0..<256).map { byte in
        var value = UInt32(byte)
        for _ in 0..<8 { value = (value & 1) == 0 ? value >> 1 : (value >> 1) ^ 0xEDB88320 }
        return value
    }

    private static func crc32(_ data: Data) -> UInt32 {
        var crc = UInt32.max
        for byte in data { crc = crcTable[Int((crc ^ UInt32(byte)) & 0xFF)] ^ (crc >> 8) }
        return crc ^ UInt32.max
    }
}

enum EPUBExportError: LocalizedError, Equatable, Sendable {
    case noReadableContent
    case incompleteContent(expected: Int, actual: Int)
    case unreadablePassage(index: Int)
    case invalidPassageIdentifiers
    case invalidMetadata
    case invalidXMLCharacters
    case archiveTooLarge

    var errorDescription: String? {
        switch self {
        case .noReadableContent:
            "Für dieses Buch ist noch kein lesbarer Text verfügbar."
        case .incompleteContent(let expected, let actual):
            "Der Buchtext ist unvollständig: \(actual) von \(expected) Abschnitten sind verfügbar."
        case .unreadablePassage(let index):
            "Abschnitt \(index) enthält keinen lesbaren Text. Das Buch konnte nicht vollständig exportiert werden."
        case .invalidPassageIdentifiers:
            "Die Abschnitte des Buchs sind nicht eindeutig zugeordnet. Bitte lade den Buchtext erneut."
        case .invalidMetadata:
            "Titel, GA-Nummer oder Sprache des Buchs sind ungültig."
        case .invalidXMLCharacters:
            "Der Buchtext enthält Zeichen, die nicht als EPUB gespeichert werden können."
        case .archiveTooLarge:
            "Das Buch ist für diesen EPUB-Export zu groß."
        }
    }
}

private extension Data {
    mutating func appendLittleEndian<T: FixedWidthInteger>(_ value: T) {
        var littleEndian = value.littleEndian
        Swift.withUnsafeBytes(of: &littleEndian) { append(contentsOf: $0) }
    }
}
