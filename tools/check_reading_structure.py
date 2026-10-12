#!/usr/bin/env python3
"""Verify native heading/verse styling without changing text or note offsets.

Compiles the actual native document builder with small presentation fixtures;
no app data, simulator, network request or personal notes are accessed.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
import Foundation
import SwiftUI
import AppKit

struct ReaderPalette {
    var foreground: Color = .black
    var background: Color = .white
    var dark = false
}
enum FixtureStyle { case underline, highlight }
struct FixtureColor { var readerColor: Color { .yellow } }
struct PersonalAnnotation {
    var id: String
    var isBookmark: Bool
    var location: Int
    var length: Int
    var style: FixtureStyle
    var color = FixtureColor()
}
struct FixturePayload: Decodable { var passages: [GAPassage] }
struct Failure: Error, CustomStringConvertible { var description: String }

@main
enum NativeStructureChecks {
    @MainActor static func main() throws {
        let body = "📖 Frühling\n\nOster-Stimmung\n\n1\n\nWenn aus den Weltenweiten *\nDie Sonne spricht *"
        let ns = body as NSString
        func block(_ text: String, _ kind: GAReadingBlock.Kind, _ level: Int? = nil) -> GAReadingBlock {
            let range = ns.range(of: text)
            return GAReadingBlock(kind: kind, startOffset: range.location, endOffset: NSMaxRange(range), level: level)
        }
        let star = ns.range(of: "*")
        let note = GAAnnotation(id: "EPUB/chapter.xhtml#note-1&ä %?", marker: "*", text: "Eine Anmerkung",
                                startOffset: star.location, endOffset: NSMaxRange(star))
        var blocks = [block("📖 Frühling", .heading, 1), block("Oster-Stimmung", .heading, 2),
                      block("1", .heading, 3), block("Wenn aus den Weltenweiten *\nDie Sonne spricht *", .verse)]
        blocks[3].poemStart = true
        var passage = GAPassage(id: "calendar", title: "Seelenkalender", gaPage: nil, sourceLabel: "Quelle", text: body,
                                 metadata: GAPassageMetadata(annotations: [note], readingBlocks: blocks, groupTitle: "Anthroposophischer Seelenkalender"))
        let settings = ReaderTextSettings(fontSize: 20, serif: true, lineSpacing: 4, margin: 24, showsPages: false, palette: ReaderPalette())
        let marking = PersonalAnnotation(id: "personal", isBookmark: false, location: blocks[3].startOffset,
                                         length: 4, style: .underline)
        let document = readingDocument(passage: passage, title: "GA 040", settings: settings, annotations: [marking], searchText: "")
        try expect(document.text.attributedSubstring(from: NSRange(location: document.bodyStart, length: document.bodyLength)).string == body,
                   "native styling preserves every UTF-16 character and all canonical separators")
        try expect(document.bodyLength == ns.length && document.bodyRange(for: document.documentRange(for: star)) == star,
                   "source selection offsets survive the title/group preamble and a surrogate pair")
        let headingFont = document.text.attribute(.font, at: document.bodyStart, effectiveRange: nil) as? NSFont
        let verseFont = document.text.attribute(.font, at: document.bodyStart + blocks[3].startOffset, effectiveRange: nil) as? NSFont
        try expect((headingFont?.pointSize ?? 0) > (verseFont?.pointSize ?? 0), "internal headings have larger type than the verses")
        let verseStyle = document.text.attribute(.paragraphStyle, at: document.bodyStart + blocks[3].startOffset, effectiveRange: nil) as? NSParagraphStyle
        try expect(verseStyle?.paragraphSpacing == 0, "a verse line feed does not add paragraph spacing")
        let secondLine = ns.range(of: "Die Sonne spricht")
        let secondLineStyle = document.text.attribute(.paragraphStyle, at: document.bodyStart + secondLine.location, effectiveRange: nil) as? NSParagraphStyle
        try expect((verseStyle?.paragraphSpacingBefore ?? 0) > 0 && secondLineStyle?.paragraphSpacingBefore == 0,
                   "independent poems add space before only their first verse line")
        let link = document.text.attribute(.link, at: document.bodyStart + star.location, effectiveRange: nil) as? URL
        try expect(link.flatMap(GAAnnotation.id(from:)) == note.id, "native source links round-trip their complete EPUB note ID")
        let secondStar = ns.range(of: "*", options: .backwards)
        try expect(document.text.attribute(.link, at: document.bodyStart + secondStar.location, effectiveRange: nil) == nil,
                   "an anchored star does not turn unrelated later stars into the same note")
        try expect(document.text.attribute(.underlineStyle, at: document.bodyStart + marking.location, effectiveRange: nil) != nil,
                   "personal markings retain their offsets after structure is styled")

        for malformed in [[GAReadingBlock(kind: .heading, startOffset: 0, endOffset: 1)],
                          [blocks[0], blocks[0]], Array(blocks.dropFirst()),
                          [GAReadingBlock(kind: .heading, startOffset: -1, endOffset: 4)]] {
            passage.metadata.readingBlocks = malformed
            try expect(passage.metadata.validReadingBlocks(in: body).isEmpty, "malformed or incomplete layout falls back to plain text")
            let fallback = readingDocument(passage: passage, title: "GA 040", settings: settings, annotations: [], searchText: "")
            try expect(fallback.text.attributedSubstring(from: NSRange(location: fallback.bodyStart, length: fallback.bodyLength)).string == body,
                       "malformed layout never loses book text")
        }
        let legacy = try JSONDecoder().decode(GAPassageMetadata.self, from: Data("{}".utf8))
        try expect(legacy.readingBlocks.isEmpty && legacy.readingSections.isEmpty && legacy.groupTitle == nil, "older metadata decodes unchanged")
        let malformedJSON = try JSONDecoder().decode(GAPassageMetadata.self, from: Data(#"{"reading_blocks":[{"kind":"future","start_offset":0,"end_offset":1}]}"#.utf8))
        try expect(malformedJSON.readingBlocks.isEmpty, "unknown structure does not prevent reading")
        let unknownSections = try JSONDecoder().decode(GAPassageMetadata.self, from: Data(#"{"reading_sections":[{"id":"unit","title":"Title","label_kind":"future","start_offset":0,"end_offset":1}]}"#.utf8))
        try expect(unknownSections.readingSections.isEmpty, "unknown work-section labels do not prevent reading")
        let incompleteSections = try JSONDecoder().decode(GAPassageMetadata.self, from: Data(#"{"reading_sections":[{"id":"unit","title":"Title","label_kind":"incipit","start_offset":0}]}"#.utf8))
        try expect(incompleteSections.readingSections.isEmpty, "incomplete work-section metadata decodes to the backward-compatible fallback")
        let malformedNote = try JSONDecoder().decode(GAAnnotation.self, from: Data(#"{"id":"note","marker":"*","text":"Note","start_offset":"bad","end_offset":1}"#.utf8))
        try expect(malformedNote.markerRanges(in: body).isEmpty, "bad anchor metadata disables accidental marker matching")
        let pageMetadata = GAPassageMetadata(pageAnchors: [GAPageAnchor(page: 23, startOffset: 0, source: "original_doc_page_footer", confidence: "inferred_between_consistent_footers", sourceSection: 5)])
        let restoredMetadata = try JSONDecoder().decode(GAPassageMetadata.self, from: JSONEncoder().encode(pageMetadata))
        try expect(restoredMetadata == pageMetadata, "native decoding and offline caching retain page offsets, source and confidence")
        let badPageMetadata = GAPassageMetadata(pageAnchors: [GAPageAnchor(page: 23, startOffset: 1, source: "original_doc_page_footer")])
        try expect(badPageMetadata.validPageAnchors(in: body).isEmpty, "page anchors cannot split a Unicode surrogate pair")
        let bodyHeadingUnit = GAReadingSection(id: "source-heading", title: "📖 Frühling", labelKind: .sourceTitle, startOffset: 0, endOffset: ns.length)
        let bodyHeadingMetadata = GAPassageMetadata(readingBlocks: blocks, readingSections: [bodyHeadingUnit])
        try expect(bodyHeadingMetadata.validReadingSections(in: body) == [bodyHeadingUnit] &&
                   bodyHeadingMetadata.validReadingSections(in: body, passageTitle: "Seelenkalender") == [bodyHeadingUnit],
                   "a first exact source heading inside the body validates with or without a separate passage title")
        let inlineTitlePassage = GAPassage(id: "inline-title", title: "📖 Frühling", gaPage: nil, sourceLabel: "Quelle", text: body,
                                          metadata: bodyHeadingMetadata)
        let inlineTitleDocument = readingDocument(passage: inlineTitlePassage, title: "GA 040", settings: settings, annotations: [], searchText: "")
        let inlinePreamble = inlineTitleDocument.text.attributedSubstring(from: NSRange(location: 0, length: inlineTitleDocument.bodyStart)).string
        try expect(!inlinePreamble.contains(inlineTitlePassage.title) && inlineTitleDocument.text.string.components(separatedBy: "📖 Frühling").count == 2,
                   "an original first body heading appears once and omits a duplicate passage-title preamble")
        try expect(inlineTitleDocument.text.attributedSubstring(from: NSRange(location: inlineTitleDocument.bodyStart, length: inlineTitleDocument.bodyLength)).string == body,
                   "the first inline source title keeps the entire canonical body selectable without adding text")
        let inlineHeadingFont = inlineTitleDocument.text.attribute(.font, at: inlineTitleDocument.bodyStart, effectiveRange: nil) as? NSFont
        let inlineHeadingStyle = inlineTitleDocument.text.attribute(.paragraphStyle, at: inlineTitleDocument.bodyStart, effectiveRange: nil) as? NSParagraphStyle
        try expect(inlineHeadingFont?.pointSize == settings.fontSize * 1.4 && inlineHeadingStyle?.paragraphSpacingBefore == 0,
                   "the first original body heading receives work-title type without a later-work separation")
        let fixture = try JSONDecoder().decode(FixturePayload.self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
        if var unitsPassage = fixture.passages.first(where: { $0.id == "ga-040-doc-heading-9" }) {
            let ranges = [(0, 285), (287, 464), (466, 569), (571, 857), (859, 1035), (1037, 1125), (1127, 1414)]
            let unitText = unitsPassage.text as NSString
            try expect(unitText.length == 1414, "the seven-work fixture retains the audited canonical Säulenweisheit text")
            let units = ranges.enumerated().map { index, bounds in
                let firstLine = unitText.substring(with: NSRange(location: bounds.0, length: bounds.1 - bounds.0)).components(separatedBy: "\n").first ?? ""
                return GAReadingSection(id: "fixture-work-\(index)", title: index == 0 ? unitsPassage.title : firstLine,
                                        labelKind: index == 0 || index == 3 ? .sourceTitle : .incipit,
                                        startOffset: bounds.0, endOffset: bounds.1)
            }
            if !unitsPassage.metadata.readingSections.isEmpty {
                let canonicalUnits = unitsPassage.metadata.readingSections
                try expect(canonicalUnits.map(\.title) == units.map(\.title) && canonicalUnits.map(\.labelKind) == units.map(\.labelKind),
                           "the canonical Säulenweisheit passage contains all seven source-audited works in order")
                try expect(canonicalUnits.map(\.startOffset) == ranges.map(\.0) && canonicalUnits.map(\.endOffset) == ranges.map(\.1),
                           "the canonical seven-work boundaries retain every audited original offset")
            }
            unitsPassage.metadata.readingSections = units
            try expect(unitsPassage.metadata.validReadingSections(in: unitsPassage.text, passageTitle: unitsPassage.title) == units,
                       "the seven works cover complete reading blocks with only canonical separators between them")
            try expect(unitsPassage.metadata.validReadingSections(in: unitsPassage.text).isEmpty,
                       "a first source title outside the body needs the actual passage title for validation")
            let outline = unitsPassage.contentsUnits
            try expect(outline.map(\.id) == units.map(\.id) && outline.map(\.title) == units.map(\.title),
                       "all seven sibling contents entries retain their source title or exact incipit")
            try expect(outline.map(\.startOffset) == ranges.map(\.0) && outline.map(\.endOffset) == ranges.map(\.1),
                       "each work has its exact canonical jump range")
            try expect(outline[0].headings.map(\.title) == ["J", "B"] && outline.dropFirst().allSatisfy { $0.headings.isEmpty },
                       "J and B belong only to Säulenweisheit and Tischgebet is a sibling work, not its child")
            try expect(outline[0].headings.map(\.startOffset) == [0, 141], "the subordinate J/B jump targets stay unchanged")
            try expect(outline.map { unitsPassage.pageNumberLabel(for: $0) } == ["S. 74", "S. 75", "S. 75", "S. 76", "S. 77", "S. 77", "S. 78"],
                       "each of the seven works shows only its own source page, including inherited pages for Offenbarung and Erkenne")
            var pageFixture = unitsPassage
            pageFixture.metadata.pageAnchors = [(10, 0), (11, 3), (12, 68), (13, 285), (14, 300), (15, 400), (16, 464)].map { page, offset in
                GAPageAnchor(page: page, startOffset: offset, source: "original_doc_page_footer")
            }
            try expect(pageFixture.pageNumberLabel(for: outline[0]) == "S. 10-12" &&
                       pageFixture.pageNumberLabel(for: outline[1]) == "S. 13-15" &&
                       pageFixture.pageNumberLabel(for: outline[2]) == "S. 16",
                       "work page labels combine inherited and internal pages, compress consecutive pages and exclude a page starting exactly at the work end")
            pageFixture.metadata.pageAnchors = []
            try expect(pageFixture.pageNumberLabel(for: outline[0]) == (pageFixture.metadata.pageNumberLabel ?? pageFixture.gaPage),
                       "older content without exact page anchors retains its original passage page label")
            try expect(unitsPassage.contentsUnit(at: -1)?.id == units[0].id && unitsPassage.contentsUnit(at: 0)?.id == units[0].id,
                       "the initial and negative reader positions select the first work")
            for (index, unit) in units.enumerated() {
                try expect(unitsPassage.contentsUnit(at: unit.startOffset)?.id == unit.id &&
                           unitsPassage.contentsUnit(at: (unit.startOffset + unit.endOffset) / 2)?.id == unit.id &&
                           unitsPassage.contentsUnit(at: unit.endOffset)?.id == unit.id,
                           "each exact work start, interior position and trailing separator selects that work alone")
                if index > 0 {
                    try expect(unitsPassage.contentsUnit(at: unit.startOffset - 1)?.id == units[index - 1].id,
                               "the separator immediately before a new work keeps the preceding work selected")
                }
            }
            try expect(unitsPassage.contentsUnit(at: unitText.length)?.id == units.last?.id &&
                       unitsPassage.contentsUnit(at: unitText.length + 1)?.id == units.last?.id,
                       "the exact end of the passage and positions beyond it select its final work")
            let unitDocument = readingDocument(passage: unitsPassage, title: "GA 040", settings: settings, annotations: [], searchText: "")
            try expect(unitDocument.text.attributedSubstring(from: NSRange(location: unitDocument.bodyStart, length: unitDocument.bodyLength)).string == unitsPassage.text,
                       "work labels never duplicate a title or verse and retain every selectable character")
            let preamble = unitDocument.text.attributedSubstring(from: NSRange(location: 0, length: unitDocument.bodyStart)).string
            try expect(preamble.components(separatedBy: unitsPassage.title).count == 2,
                       "the first work's source title occurs exactly once in the native preamble")
            let jFont = unitDocument.text.attribute(.font, at: unitDocument.bodyStart, effectiveRange: nil) as? NSFont
            let titleFont = unitDocument.text.attribute(.font, at: (preamble as NSString).range(of: unitsPassage.title).location, effectiveRange: nil) as? NSFont
            for unit in units.dropFirst() {
                let labelFont = unitDocument.text.attribute(.font, at: unitDocument.bodyStart + unit.startOffset, effectiveRange: nil) as? NSFont
                let labelStyle = unitDocument.text.attribute(.paragraphStyle, at: unitDocument.bodyStart + unit.startOffset, effectiveRange: nil) as? NSParagraphStyle
                try expect(labelStyle?.paragraphSpacingBefore == settings.fontSize * 1.1 && labelStyle?.paragraphSpacing == 0,
                           "a later work starts with a larger separation while verse line spacing stays intact")
                if unit.labelKind == .incipit {
                    let firstLine = unitText.substring(with: unit.range).components(separatedBy: "\n").first ?? ""
                    let secondLineOffset = unit.startOffset + (firstLine as NSString).length + 1
                    try expect(secondLineOffset < unit.endOffset, "the fixture incipit has a following actual verse line")
                    let nextFont = unitDocument.text.attribute(.font, at: unitDocument.bodyStart + secondLineOffset, effectiveRange: nil) as? NSFont
                    let nextStyle = unitDocument.text.attribute(.paragraphStyle, at: unitDocument.bodyStart + secondLineOffset, effectiveRange: nil) as? NSParagraphStyle
                    try expect(labelFont?.pointSize == settings.fontSize && labelFont?.fontDescriptor == nextFont?.fontDescriptor &&
                               nextFont?.pointSize == settings.fontSize && nextStyle?.paragraphSpacingBefore == 0 && nextStyle?.paragraphSpacing == 0,
                               "an incipit keeps the exact normal verse font and weight of the following line while its stanza stays intact")
                } else {
                    try expect(labelFont?.pointSize == titleFont?.pointSize && (labelFont?.pointSize ?? 0) > (jFont?.pointSize ?? 0),
                               "a later source title keeps the original title hierarchy above the J/B headings")
                }
            }
            let restoredUnits = try JSONDecoder().decode(GAPassage.self, from: JSONEncoder().encode(unitsPassage))
            try expect(restoredUnits.metadata.readingSections == units && restoredUnits.contentsUnits == outline,
                       "native decoding and offline caching retain work identities, hierarchy and exact offsets")
            var duplicateID = units; duplicateID[1].id = duplicateID[0].id
            var blankID = units; blankID[1].id = " "
            var blankTitle = units; blankTitle[1].title = " "
            var wrongIncipit = units; wrongIncipit[1].title = "Erfundener Titel"
            var wrongSourceTitle = units; wrongSourceTitle[3].title = "Tischgebet"
            var wrongFirstTitle = units; wrongFirstTitle[0].title = "Ein anderer Titel"
            var wrongKind = units; wrongKind[1].labelKind = .sourceTitle
            var wrongBoundary = units; wrongBoundary[1].startOffset += 1
            var wrongEndBoundary = units; wrongEndBoundary[1].endOffset -= 1
            var negativeStart = units; negativeStart[0].startOffset = -1
            var beyondBody = units; beyondBody[6].endOffset = unitText.length + 1
            var emptyRange = units; emptyRange[1].endOffset = emptyRange[1].startOffset
            var overlap = units; overlap[1].startOffset = units[0].startOffset
            var incompleteBlock = units; incompleteBlock[0].endOffset = 214
            for malformed in [Array(units.dropFirst()), Array(units.dropLast()), duplicateID, blankID, blankTitle,
                              wrongIncipit, wrongSourceTitle, wrongFirstTitle, wrongKind, wrongBoundary, wrongEndBoundary,
                              negativeStart, beyondBody, emptyRange, overlap, incompleteBlock] {
                unitsPassage.metadata.readingSections = malformed
                try expect(unitsPassage.metadata.validReadingSections(in: unitsPassage.text, passageTitle: unitsPassage.title).isEmpty && unitsPassage.contentsUnits.isEmpty && unitsPassage.contentsUnit(at: 0) == nil,
                           "invalid work identities, labels, boundaries or coverage use the existing passage contents")
                let fallback = readingDocument(passage: unitsPassage, title: "GA 040", settings: settings, annotations: [], searchText: "")
                try expect(fallback.text.attributedSubstring(from: NSRange(location: fallback.bodyStart, length: fallback.bodyLength)).string == unitsPassage.text,
                           "invalid work structure preserves the complete readable source text")
                let incipitFont = fallback.text.attribute(.font, at: fallback.bodyStart + ranges[1].0, effectiveRange: nil) as? NSFont
                try expect(incipitFont?.pointSize == settings.fontSize, "invalid work structure cannot apply a fabricated incipit title")
            }
            unitsPassage.metadata.readingSections = units
            unitsPassage.metadata.readingBlocks = Array(unitsPassage.metadata.readingBlocks.dropLast())
            try expect(unitsPassage.metadata.validReadingSections(in: unitsPassage.text, passageTitle: unitsPassage.title).isEmpty,
                       "work sections cannot validate against incomplete underlying reading blocks")
            print("Native work-section checks passed: seven sibling works, J/B only beneath Säulenweisheit, source-bound titles, exact incipits, intact verse lines, offline caching and malformed fallback.")
        }
        let unicodeText = "📖 Erste Zeile\nZweite Zeile"
        let unicodeLength = (unicodeText as NSString).length
        let unicodeBlock = GAReadingBlock(kind: .verse, startOffset: 0, endOffset: unicodeLength)
        let unicodeUnit = GAReadingSection(id: "unicode", title: "📖 Erste Zeile", labelKind: .incipit, startOffset: 0, endOffset: unicodeLength)
        var unicodeMetadata = GAPassageMetadata(readingBlocks: [unicodeBlock], readingSections: [unicodeUnit])
        try expect(unicodeMetadata.validReadingSections(in: unicodeText) == [unicodeUnit], "an exact incipit can contain a Unicode surrogate pair")
        let incipitFirstPassage = GAPassage(id: "incipit-first", title: "Gemeinsamer Quellabschnitt", gaPage: nil, sourceLabel: "Quelle", text: unicodeText,
                                           metadata: unicodeMetadata)
        let incipitFirstDocument = readingDocument(passage: incipitFirstPassage, title: "GA 040", settings: settings, annotations: [], searchText: "")
        let incipitPreamble = incipitFirstDocument.text.attributedSubstring(from: NSRange(location: 0, length: incipitFirstDocument.bodyStart)).string
        try expect(!incipitPreamble.contains(incipitFirstPassage.title) && !incipitPreamble.contains(unicodeUnit.title),
                   "an incipit-first work omits the shared passage header and does not repeat its verse as a separate title")
        try expect(incipitFirstDocument.text.attributedSubstring(from: NSRange(location: incipitFirstDocument.bodyStart, length: incipitFirstDocument.bodyLength)).string == unicodeText &&
                   incipitFirstDocument.text.string.components(separatedBy: unicodeUnit.title).count == 2,
                   "the first incipit remains one actual source line with every Unicode selection offset intact")
        let incipitFirstFont = incipitFirstDocument.text.attribute(.font, at: incipitFirstDocument.bodyStart, effectiveRange: nil) as? NSFont
        let incipitNextFont = incipitFirstDocument.text.attribute(.font, at: incipitFirstDocument.bodyStart + (unicodeUnit.title as NSString).length + 1, effectiveRange: nil) as? NSFont
        let incipitFirstStyle = incipitFirstDocument.text.attribute(.paragraphStyle, at: incipitFirstDocument.bodyStart, effectiveRange: nil) as? NSParagraphStyle
        try expect(incipitFirstFont?.pointSize == settings.fontSize && incipitFirstFont?.fontDescriptor == incipitNextFont?.fontDescriptor &&
                   incipitNextFont?.pointSize == settings.fontSize && incipitFirstStyle?.paragraphSpacingBefore == 0,
                   "a first incipit stays in the exact normal verse font and weight with no additional initial work separation")
        unicodeMetadata.readingSections[0].startOffset = 1
        try expect(unicodeMetadata.validReadingSections(in: unicodeText).isEmpty, "work sections cannot split a Unicode surrogate pair")
        if let calendar = fixture.passages.first(where: { $0.hasCalendarContents }) {
            let outline = calendar.contentsHeadings
            let seasons = outline.filter(\.isSeason)
            try expect(seasons.map(\.title) == ["Frühling", "Sommer", "Herbst", "Winter"], "calendar contents expose all four readable season labels")
            let poems = outline.filter { $0.title.hasPrefix("Spruch ") }
            try expect(poems.map(\.title) == (1...52).map { "Spruch \($0)" }, "calendar contents expose Spruch 1 through Spruch 52 in order")
            let calendarText = calendar.text as NSString
            for (index, poem) in poems.enumerated() {
                let number = String(index + 1)
                try expect(calendarText.substring(with: NSRange(location: poem.startOffset, length: (number as NSString).length)) == number,
                           "Spruch \(index + 1) jumps to its exact source number")
                try expect(poem.level == 2 && !(poem.subtitle ?? "").isEmpty, "each poem is indented beneath its season with a readable week/date subtitle")
            }
            for season in seasons {
                let sourceTitle = season.title.uppercased()
                try expect(calendarText.substring(with: NSRange(location: season.startOffset, length: (sourceTitle as NSString).length)) == sourceTitle,
                           "\(season.title) jumps to its exact season heading")
                try expect(season.level == 1, "season entries remain above their poem entries")
            }
            let calendarBlocks = calendar.metadata.validReadingBlocks(in: calendar.text)
            let seasonBlockIndices = calendarBlocks.indices.filter {
                calendarBlocks[$0].kind == .heading && calendarBlocks[$0].level == 1 &&
                    ["FRÜHLING", "SOMMER", "HERBST", "WINTER"].contains(calendarText.substring(with: calendarBlocks[$0].range))
            }
            try expect(calendarBlocks.count > 4 && calendarBlocks[0].kind == .prose && calendarBlocks[1].kind == .heading && seasonBlockIndices.count == 4,
                       "the calendar fixture has both source prefaces and all four exact season headings")
            let unitBlockStarts = [0, 1] + seasonBlockIndices
            let calendarUnits = unitBlockStarts.enumerated().map { index, blockIndex in
                let nextBlock = index + 1 < unitBlockStarts.count ? unitBlockStarts[index + 1] : calendarBlocks.count
                return GAReadingSection(id: "fixture-calendar-\(index)",
                                        title: index == 0 ? calendar.title : calendarText.substring(with: calendarBlocks[blockIndex].range),
                                        labelKind: .sourceTitle, startOffset: calendarBlocks[blockIndex].startOffset,
                                        endOffset: calendarBlocks[nextBlock - 1].endOffset)
            }
            if !calendar.metadata.readingSections.isEmpty {
                let canonicalUnits = calendar.metadata.readingSections
                try expect(canonicalUnits.map(\.title) == calendarUnits.map(\.title) &&
                           canonicalUnits.map(\.labelKind) == calendarUnits.map(\.labelKind) &&
                           canonicalUnits.map(\.startOffset) == calendarUnits.map(\.startOffset) &&
                           canonicalUnits.map(\.endOffset) == calendarUnits.map(\.endOffset),
                           "the canonical calendar has six complete source-preface and season units at the original exact block boundaries")
            }
            var sectionedCalendar = calendar
            sectionedCalendar.metadata.readingSections = calendarUnits
            try expect(sectionedCalendar.metadata.validReadingSections(in: calendar.text, passageTitle: calendar.title) == calendarUnits,
                       "both prefaces and the four seasons cover every calendar source block exactly once")
            let calendarUnitOutline = sectionedCalendar.contentsUnits
            let expectedLabels = [calendar.title, calendarUnits[1].title, "Frühling", "Sommer", "Herbst", "Winter"]
            try expect(calendarUnitOutline.map(\.title) == expectedLabels && calendarUnitOutline.map(\.id) == calendarUnits.map(\.id),
                       "the native calendar contents expose six sibling preface/season rows with readable season labels")
            try expect(calendarUnitOutline.map(\.startOffset) == calendarUnits.map(\.startOffset) &&
                       calendarUnitOutline.map(\.endOffset) == calendarUnits.map(\.endOffset),
                       "every preface and season row jumps to its unchanged source range")
            try expect(calendarUnitOutline.prefix(2).allSatisfy { $0.headings.isEmpty } &&
                       calendarUnitOutline.dropFirst(2).allSatisfy { $0.headings.allSatisfy { !$0.isSeason && $0.title.hasPrefix("Spruch ") } },
                       "source preface and season headings never repeat as children of their own contents row")
            let expectedPoemNumbers = [Array(1...13), Array(14...26), Array(27...35), Array(36...52)]
            for (seasonIndex, unit) in calendarUnitOutline.dropFirst(2).enumerated() {
                try expect(unit.headings.map(\.title) == expectedPoemNumbers[seasonIndex].map { "Spruch \($0)" },
                           "each calendar season contains only its own ordered source sayings")
                for poem in unit.headings {
                    let original = poems.first(where: { $0.id == poem.id })
                    try expect(original == poem && poem.level == 2 && !(poem.subtitle ?? "").isEmpty &&
                               poem.startOffset > unit.startOffset && poem.startOffset < unit.endOffset,
                               "each calendar saying retains its exact source number, date subtitle and subordinate jump target")
                }
            }
            try expect(calendarUnitOutline.flatMap(\.headings).map(\.title) == (1...52).map { "Spruch \($0)" },
                       "all 52 calendar sayings occur once beneath their six sibling source sections")
            let calendarDocument = readingDocument(passage: sectionedCalendar, title: "GA 040", settings: settings, annotations: [], searchText: "")
            try expect(calendarDocument.text.attributedSubstring(from: NSRange(location: calendarDocument.bodyStart, length: calendarDocument.bodyLength)).string == calendar.text,
                       "calendar hierarchy keeps every preface, season, saying and source separator unchanged")
            let calendarPreamble = calendarDocument.text.attributedSubstring(from: NSRange(location: 0, length: calendarDocument.bodyStart)).string
            try expect(calendarPreamble.components(separatedBy: calendar.title).count == 2,
                       "the source title for the first preface appears once above its prose")
            for unit in calendarUnits.dropFirst() {
                let titleFont = calendarDocument.text.attribute(.font, at: calendarDocument.bodyStart + unit.startOffset, effectiveRange: nil) as? NSFont
                let titleStyle = calendarDocument.text.attribute(.paragraphStyle, at: calendarDocument.bodyStart + unit.startOffset, effectiveRange: nil) as? NSParagraphStyle
                try expect(titleFont?.pointSize == settings.fontSize * 1.4 && titleStyle?.paragraphSpacingBefore == settings.fontSize * 1.1,
                           "the second preface and each source season heading share the work-title typography")
                try expect(calendarDocument.text.string.components(separatedBy: unit.title).count == 2,
                           "each existing calendar source title remains a single original body heading")
            }
            for note in calendar.metadata.annotations {
                for marker in note.markerRanges(in: calendar.text) {
                    let url = calendarDocument.text.attribute(.link, at: calendarDocument.bodyStart + marker.location, effectiveRange: nil) as? URL
                    try expect(url.flatMap(GAAnnotation.id(from:)) == note.id &&
                               calendarDocument.bodyRange(for: calendarDocument.documentRange(for: marker)) == marker,
                               "calendar hierarchy retains each source note link and its exact selectable marker offsets")
                }
            }
            let cachedCalendar = try JSONDecoder().decode(GAPassage.self, from: JSONEncoder().encode(sectionedCalendar))
            try expect(cachedCalendar.metadata.readingSections == calendarUnits && cachedCalendar.contentsUnits == calendarUnitOutline &&
                       cachedCalendar.metadata.annotations == calendar.metadata.annotations,
                       "offline calendar caching retains all six section identities, readable contents and unchanged source notes")
            var wrongCalendarLabel = sectionedCalendar
            wrongCalendarLabel.metadata.readingSections[2].title = "Frühling"
            try expect(wrongCalendarLabel.contentsUnits.isEmpty && wrongCalendarLabel.contentsHeadings == outline,
                       "a transformed metadata source title falls back to the existing complete calendar outline")
            print("Native contents checks passed: four seasons, Spruch 1–52, 52 week/date subtitles and all 56 exact jump targets.")
            print("Native calendar section checks passed: six sibling prefaces/seasons, 52 correctly nested sayings, no repeated source headings, exact jumps, title styles, note offsets and offline caching.")
        }
        for item in fixture.passages {
            let rendered = readingDocument(passage: item, title: "GA 040", settings: settings, annotations: [], searchText: "")
            try expect(rendered.text.attributedSubstring(from: NSRange(location: rendered.bodyStart, length: rendered.bodyLength)).string == item.text,
                       "section \(item.id) retains its entire text in the native reader")
            if !item.metadata.readingBlocks.isEmpty {
                try expect(item.metadata.validReadingBlocks(in: item.text).count == item.metadata.readingBlocks.count,
                           "section \(item.id) has valid complete UTF-16 structure")
                for block in item.metadata.readingBlocks where block.kind == .verse {
                    let style = rendered.text.attribute(.paragraphStyle, at: rendered.bodyStart + block.startOffset, effectiveRange: nil) as? NSParagraphStyle
                    let workUnits = item.metadata.validReadingSections(in: item.text, passageTitle: item.title)
                    let laterUnitStartsHere = workUnits.dropFirst().contains { $0.startOffset == block.startOffset }
                    let firstIncipitStartsHere = workUnits.first?.labelKind == .incipit && workUnits.first?.startOffset == block.startOffset
                    let expected = laterUnitStartsHere ? settings.fontSize * 1.1 : firstIncipitStartsHere ? 0 : block.poemStart == true ? settings.fontSize * 0.35 : 0
                    try expect(style?.paragraphSpacingBefore == expected && style?.paragraphSpacing == 0,
                               "section \(item.id) adds poem spacing only at explicitly marked independent beginnings")
                }
            }
            try expect(item.metadata.validPageAnchors(in: item.text).count == item.metadata.pageAnchors.count,
                       "section \(item.id) retains all valid UTF-16 page anchors")
            let cached = try JSONDecoder().decode(GAPassage.self, from: JSONEncoder().encode(item))
            try expect(cached.metadata.pageAnchors == item.metadata.pageAnchors, "offline cache retains source page metadata")
            try expect(cached.metadata.readingBlocks == item.metadata.readingBlocks, "offline cache retains explicit poem boundaries")
            try expect(cached.metadata.readingSections == item.metadata.readingSections, "offline cache retains explicit work sections")
            if !item.metadata.readingSections.isEmpty {
                let units = item.metadata.validReadingSections(in: item.text, passageTitle: item.title)
                try expect(units.count == item.metadata.readingSections.count && item.contentsUnits.count == units.count,
                           "section \(item.id) exposes every valid sibling work in its native contents")
                for unit in units {
                    if unit.labelKind == .incipit {
                        let unitText = (item.text as NSString).substring(with: unit.range)
                        try expect(unitText.components(separatedBy: "\n").first == unit.title,
                                   "section \(item.id) labels an incipit with its exact first actual verse line")
                    }
                }
            }
        }
        print("Native structure checks passed: heading/verse styles, independent poems, exact selectable text, UTF-16 offsets, linked notes, personal markings, malformed metadata fallback, \(fixture.passages.count) complete sections.")
    }
    static func expect(_ condition: Bool, _ description: String) throws {
        guard condition else { throw Failure(description: description) }
    }
}
'''


def validate_payload(payload):
    """Independently validate machine-readable ranges against canonical text."""
    contexts = {}
    totals = {"blocks": 0, "reading_sections": 0, "page_anchors": 0, "anchored_notes": 0, "toc_entries": 0}

    def require(condition, label):
        if not condition:
            raise AssertionError(label)

    def context(text):
        boundaries, offset = {0}, 0
        for character in text:
            offset += len(character.encode("utf-16-le")) // 2
            boundaries.add(offset)
        return {"length": offset, "boundaries": boundaries, "bytes": text.encode("utf-16-le")}

    def valid_offset(value, ctx):
        return type(value) is int and value in ctx["boundaries"]

    def piece(ctx, start, end):
        return ctx["bytes"][start * 2:end * 2].decode("utf-16-le")

    for passage in payload["passages"]:
        text, metadata = passage["text"], passage.get("metadata", {})
        ctx = context(text)
        require(passage["id"] not in contexts, "unique passage IDs")
        contexts[passage["id"]] = ctx
        if "checksum" in passage:
            require(passage["checksum"] == hashlib.sha256(text.encode()).hexdigest(), f"canonical checksum for {passage['id']}")
        if "group_title" in metadata:
            require(isinstance(metadata["group_title"], str), "string group title")
        blocks = metadata.get("reading_blocks", [])
        require(isinstance(blocks, list), "reading blocks are an array")
        end = 0
        for block in blocks:
            start, finish = block["start_offset"], block["end_offset"]
            require(block["kind"] in {"heading", "verse", "prose", "attribution", "note"}, "known reading block kind")
            require(valid_offset(start, ctx) and valid_offset(finish, ctx) and finish > start >= end, "ordered complete UTF-16 block ranges")
            require(not piece(ctx, end, start).strip(), "only separators may lie between blocks")
            if "level" in block:
                require(type(block["level"]) is int and 1 <= block["level"] <= 6, "heading level 1–6")
            if "poem_start" in block:
                require(type(block["poem_start"]) is bool, "boolean independent poem marker")
            end = finish
        if blocks:
            require(not piece(ctx, end, ctx["length"]).strip(), "complete block coverage")
        totals["blocks"] += len(blocks)
        sections = metadata.get("reading_sections", [])
        require(isinstance(sections, list), "reading sections are an array")
        if sections:
            require(bool(blocks), "work sections require valid complete reading blocks")
            starts = {block["start_offset"]: block for block in blocks}
            finishes = {block["end_offset"] for block in blocks}
            identities, end = set(), 0
            for index, section in enumerate(sections):
                identity, title = section["id"], section["title"]
                require(isinstance(identity, str) and identity.strip() and identity not in identities, "unique nonempty work section identity")
                require(isinstance(title, str) and title.strip(), "nonempty work section title")
                require(section["label_kind"] in {"source_title", "incipit"}, "known work section label kind")
                start, finish = section["start_offset"], section["end_offset"]
                require(valid_offset(start, ctx) and valid_offset(finish, ctx) and finish > start >= end, "ordered UTF-16 work section ranges")
                require(start in starts and finish in finishes, "work sections start and end at exact reading block boundaries")
                require(not piece(ctx, end, start).strip(), "only separators may lie between work sections")
                first_block = starts[start]
                first_block_text = piece(ctx, start, first_block["end_offset"])
                if section["label_kind"] == "incipit":
                    require(first_block["kind"] == "verse" and first_block_text.split("\n", 1)[0] == title,
                            "incipits are exact actual first verse lines")
                else:
                    require(index == 0 and title == passage["title"] or first_block["kind"] == "heading" and first_block_text == title,
                            "source titles come from the first passage preamble or an existing exact heading")
                identities.add(identity)
                end = finish
            require(not piece(ctx, end, ctx["length"]).strip(), "complete work section coverage")
        totals["reading_sections"] += len(sections)
        anchors = metadata.get("page_anchors", [])
        require(isinstance(anchors, list), "page anchors are an array")
        previous = 0
        for anchor in anchors:
            start = anchor["start_offset"]
            require(valid_offset(start, ctx) and start >= previous, "ordered UTF-16 page offsets")
            require(type(anchor["page"]) is int and anchor["page"] > 0 and isinstance(anchor["source"], str), "source page anchor")
            if "confidence" in anchor:
                require(isinstance(anchor["confidence"], str), "page anchor confidence")
            if "source_section" in anchor:
                require(type(anchor["source_section"]) is int and anchor["source_section"] >= 0, "source page section")
            previous = start
        totals["page_anchors"] += len(anchors)
        for note in metadata.get("annotations", []):
            require(all(isinstance(note[field], str) for field in ["id", "marker", "text"]), "source note identity, marker and text")
            if "start_offset" in note or "end_offset" in note:
                require("start_offset" in note and "end_offset" in note, "both anchored marker offsets are required")
                start, finish = note["start_offset"], note["end_offset"]
                require(valid_offset(start, ctx) and valid_offset(finish, ctx) and finish > start, "UTF-16 source marker range")
                require(piece(ctx, start, finish) == note["marker"], "source note links to its exact marker")
                totals["anchored_notes"] += 1
    toc = payload.get("table_of_contents", [])
    require(isinstance(toc, list), "table of contents is an array")
    nodes = {entry["id"]: entry for entry in toc}
    require(len(nodes) == len(toc), "unique table-of-contents IDs")
    for entry in toc:
        require(isinstance(entry["id"], str) and entry["id"] and isinstance(entry["title"], str) and entry["title"].strip(), "TOC identity and title")
        require(type(entry["level"]) is int and 1 <= entry["level"] <= 6, "TOC level 1–6")
        require(entry["passage_id"] in contexts and valid_offset(entry["start_offset"], contexts[entry["passage_id"]]), "TOC targets valid passage offsets")
        parent = entry["parent_id"]
        require(parent is None or isinstance(parent, str) and parent in nodes and nodes[parent]["level"] < entry["level"], "TOC parent precedes its child in the hierarchy")
    totals["toc_entries"] = len(toc)
    return totals


def check_section_validation():
    """Exercise independent section validation with Unicode and invalid labels."""
    from copy import deepcopy

    text = "J\n\n📖 Erstes Licht\nZweite Zeile\n\nTISCHGEBET\n\nDrittes Licht\nZweite Zeile\n\nLetztes Wort.\nLetzte Zeile."

    def offset(index):
        return len(text[:index].encode("utf-16-le")) // 2

    def block(part, kind, **extra):
        start = text.index(part)
        return {"kind": kind, "start_offset": offset(start), "end_offset": offset(start + len(part)), **extra}

    blocks = [block("J", "heading", level=2), block("📖 Erstes Licht\nZweite Zeile", "verse"),
              block("TISCHGEBET", "heading", level=2), block("Drittes Licht\nZweite Zeile", "verse"),
              block("Letztes Wort.\nLetzte Zeile.", "verse")]
    sections = [{"id": "first", "title": "QUELLTITEL", "label_kind": "source_title", "start_offset": 0, "end_offset": blocks[1]["end_offset"]},
                {"id": "table", "title": "TISCHGEBET", "label_kind": "source_title", "start_offset": blocks[2]["start_offset"], "end_offset": blocks[3]["end_offset"]},
                {"id": "last", "title": "Letztes Wort.", "label_kind": "incipit", "start_offset": blocks[4]["start_offset"], "end_offset": blocks[4]["end_offset"]}]
    payload = {"passages": [{"id": "sections", "title": "QUELLTITEL", "text": text,
                            "metadata": {"reading_blocks": blocks, "reading_sections": sections}}]}
    assert validate_payload(payload)["reading_sections"] == 3
    invalid = []
    for field, value in [("id", "first"), ("title", "Erfundener Titel"), ("label_kind", "source_title"),
                         ("start_offset", blocks[4]["start_offset"] + 1), ("end_offset", blocks[4]["end_offset"] - 1)]:
        candidate = deepcopy(payload)
        candidate["passages"][0]["metadata"]["reading_sections"][2][field] = value
        invalid.append(candidate)
    candidate = deepcopy(payload)
    candidate["passages"][0]["metadata"]["reading_sections"].pop(1)
    invalid.append(candidate)
    candidate = deepcopy(payload)
    candidate["passages"][0]["metadata"]["reading_sections"][1]["title"] = "Tischgebet"
    invalid.append(candidate)
    candidate = deepcopy(payload)
    candidate["passages"][0]["metadata"]["reading_blocks"].pop()
    invalid.append(candidate)
    candidate = deepcopy(payload)
    candidate["passages"][0]["metadata"]["reading_sections"][0]["end_offset"] = blocks[1]["start_offset"] + 1
    invalid.append(candidate)
    for candidate in invalid:
        try:
            validate_payload(candidate)
        except AssertionError:
            continue
        raise AssertionError("independent validator accepted malformed work-section labels, boundaries or coverage")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content", type=Path, default=ROOT / "server/priv/content/ga-040.json.gz", help="Canonical JSON or gzip content payload to validate")
    args = parser.parse_args()
    raw = args.content.read_bytes()
    raw = gzip.decompress(raw) if args.content.suffix == ".gz" else raw
    payload = json.loads(raw)
    check_section_validation()
    totals = validate_payload(payload)
    print("Canonical structure checks passed: " + ", ".join(f"{number} {label.replace('_', ' ')}" for label, number in totals.items()), flush=True)
    with tempfile.TemporaryDirectory(prefix="ga-native-structure-") as directory:
        scratch = Path(directory)
        builder = (ROOT / "apple/GA/NativeReadingText.swift").read_text().split("\n#if os(iOS)\nstruct NativeReadingText:", 1)[0]
        view_source = (ROOT / "apple/GA/ReaderView.swift").read_text()
        contents_sheet = "private struct ReaderContentsSheet: View {" + view_source.split("private struct ReaderContentsSheet: View {", 1)[1].split("\nprivate struct ReaderAnnotationsSheet:", 1)[0]
        source = scratch / "NativeStructure.swift"
        source.write_text(builder + "\n" + contents_sheet + HARNESS)
        fixture = scratch / "content.json"
        fixture.write_bytes(raw)
        executable = scratch / "checks"
        subprocess.run(["swiftc", "-swift-version", "6", "-parse-as-library", str(ROOT / "apple/GA/Models.swift"), str(source), "-o", str(executable)], check=True)
        subprocess.run([str(executable), str(fixture)], check=True)


if __name__ == "__main__":
    main()
