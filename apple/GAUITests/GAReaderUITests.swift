import XCTest
import StoreKitTest
#if os(iOS)
import UIKit
#endif

/// Runs against the dedicated GA QA simulator without resetting the app's data.
@MainActor
final class GAReaderUITests: XCTestCase {
    private var app: XCUIApplication!
    private var readerTestStore: SKTestSession?

    override func setUp() async throws {
        // Reader regressions need a real verified test entitlement now that
        // every book requires access. Access-specific tests own their sessions.
        if !name.contains("testAccessGate") && !name.contains("testFreeRequest") && !name.contains("testCaptureGerman") {
            let session = try SKTestSession(configurationFileNamed: "GA")
            session.resetToDefaultState()
            session.clearTransactions()
            session.disableDialogs = true
            readerTestStore = session
        }
    }

    override func tearDown() async throws {
        readerTestStore?.clearTransactions()
        readerTestStore = nil
    }

    func testHomeLibraryViewsFiltersAndTextSearch() throws {
        try launch()
        check(app.navigationBars["Jetzt lesen"].exists)
        capture("Home with Kutscherei covers")

        try tab("Bibliothek")
        try tap(app.buttons["Bibliotheksoptionen"], "Library options")
        try tap(app.buttons["Liste"], "List view")
        check(app.staticTexts["Die Philosophie der Freiheit"].exists)
        capture("Library list")

        try tap(app.buttons["Bibliotheksoptionen"], "Library options")
        try tap(app.buttons["Cover"], "Cover view")
        try require(app.buttons["Aktionen für Die Philosophie der Freiheit"], "Cover grid actions")
        capture("Library cover grid")

        try tap(app.buttons["Alle Werke"], "Collection filter")
        try tap(app.buttons["Offline verfügbar"], "Offline filter")
        check(app.buttons["Offline verfügbar"].exists)
        check(app.staticTexts["Die Philosophie der Freiheit"].exists)
        try tap(app.buttons["Offline verfügbar"], "Collection filter")
        try tap(app.buttons["Alle Werke"], "All works filter")

        try search("Philosophie")
        let passageHit = app.buttons.matching(NSPredicate(format:
            "label CONTAINS %@ AND NOT label CONTAINS %@", "GA 004 · Die Philosophie der Freiheit", "· Werk")).firstMatch
        try tap(passageHit, "Full-text search hit")
        try require(app.buttons["Buch schließen"].firstMatch, "Reader opened by full-text result")
        try require(app.textViews.firstMatch, "Native reading text")
        check(app.buttons["Weitere Leseoptionen"].exists)
        capture("Reader opened at search passage")
        try closeReader()
    }

    func testServerDownloadPersistsOffline() throws {
        try launch()
        let originalEnvironment = app.launchEnvironment
        defer {
            app.terminate()
            app.launchEnvironment = originalEnvironment
            app.launch()
        }

        // Remove only this test book's body through the app so repeat runs also
        // exercise a fresh server download. Notes and reading positions remain.
        try tab("Bibliothek")
        let originallyGrid = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Aktionen für ")).count > 0
        if !originallyGrid {
            try tap(app.buttons["Bibliotheksoptionen"], "Library options before download QA")
            try tap(app.buttons["Cover"], "Cover actions before download QA")
        }
        let filter = app.buttons.matching(NSPredicate(format: "label IN %@",
            ["Alle Werke", "Wird gelesen", "Möchte ich lesen", "Gelesen", "Offline verfügbar"])).firstMatch
        try require(filter, "Current library filter before download QA")
        let originalFilter = filter.label
        if originalFilter != "Offline verfügbar" {
            try tap(filter, "Download QA collection filter")
            try tap(app.buttons["Offline verfügbar"], "Previously downloaded books")
        }
        let actions = app.buttons["Aktionen für Einleitungen zu Goethes Naturwissenschaftlichen Schriften (1884 - 1897)"]
        for _ in 0..<4 where !actions.isHittable { app.scrollViews.firstMatch.swipeUp() }
        if actions.isHittable {
            try tap(actions, "Only GA 001 download actions")
            try tap(app.buttons["Download entfernen"], "Remove only GA 001 body before its fresh download")
            check(!actions.exists, "GA 001 must leave the offline filter before its server download")
        }
        app.scrollViews.firstMatch.swipeDown()
        if originalFilter != "Offline verfügbar" {
            try tap(app.buttons["Offline verfügbar"], "Restore collection filter")
            try tap(app.buttons[originalFilter], "Restore original collection")
        }
        if !originallyGrid {
            try tap(app.buttons["Bibliotheksoptionen"], "Restore library view before download QA")
            try tap(app.buttons["Liste"], "Restore original library list")
        }

        try search("GA001")
        let work = app.buttons.matching(NSPredicate(format:
            "label CONTAINS %@ AND label CONTAINS %@", "GA 001", "· Werk")).firstMatch
        try tap(work, "Unbundled GA 001 catalog result")
        try require(app.buttons["Buch schließen"].firstMatch, "GA 001 downloaded from the public server")
        try require(app.textViews.firstMatch, "Downloaded native reading text")
        let section = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Abschnitt ")).firstMatch
        try require(section, "Downloaded work section indicator")
        let savedSection = section.label
        check(savedSection.hasSuffix("von 28"), "The complete GA 001 work must contain its 28 advertised sections")
        capture("GA001 downloaded from the public library")
        try closeReader()

        app.terminate()
        app.launchEnvironment["GA_SERVER_BASE_URL"] = "http://127.0.0.1:1"
        app.launch()
        try require(app.buttons["Bibliothek"].firstMatch, "Offline library after process relaunch")
        try search("GA001")
        let offlineWork = app.buttons.matching(NSPredicate(format:
            "label CONTAINS %@ AND label CONTAINS %@", "GA 001", "· Werk")).firstMatch
        try tap(offlineWork, "Downloaded GA 001 metadata restored offline")
        try require(app.buttons["Buch schließen"].firstMatch, "Cached GA 001 opened with an unreachable server")
        try require(app.textViews.firstMatch, "Cached native reading text survives relaunch")
        try require(app.staticTexts[savedSection], "Downloaded chapter position survives offline relaunch")
        capture("GA001 restored from its offline download")
        try closeReader()
    }

    /// Run through tools/check_book_updates.py, which supplies and restores the
    /// legacy cache plus a disposable server whose first update request fails.
    func testBookUpdateKeepsOldEditionUntilVerifiedAndPersistsOffline() async throws {
        let fixtureURL = URL(string: "http://127.0.0.1:4178/api/catalog")!
        do {
            let (_, response) = try await URLSession.shared.data(for: URLRequest(url: fixtureURL, timeoutInterval: 2))
            guard let response = response as? HTTPURLResponse,
                  response.value(forHTTPHeaderField: "X-GA-Update-QA") == "1" else {
                throw XCTSkip("Run this regression through tools/check_book_updates.py")
            }
        } catch {
            throw XCTSkip("Run this regression through tools/check_book_updates.py")
        }
        // Missing-element helpers throw after recording their failure. Keep
        // XCTest from aborting an async test before that cleanup can run.
        continueAfterFailure = true
        app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages", "(de)", "-AppleLocale", "de_DE",
                               "-libraryGrid", "YES", "-librarySort", "ga"]
        app.launchEnvironment["GA_SERVER_BASE_URL"] = "http://127.0.0.1:4178"
        app.launch()
        defer { app.terminate() }
        try require(app.buttons["Bibliothek"].firstMatch, "Library with the disposable update server")
        try tab("Bibliothek")
        try tap(app.buttons["Bibliotheksoptionen"], "Library update options")
        try tap(app.buttons["Nach Updates suchen"], "Check for book updates")
        try tap(app.buttons["Alle Werke"], "Update QA collection filter")
        try tap(app.buttons["Offline verfügbar"], "Legacy books remain available offline")

        let actions = app.buttons["Aktionen für Einleitungen zu Goethes Naturwissenschaftlichen Schriften (1884 - 1897)"]
        for _ in 0..<6 where !actions.isHittable { app.scrollViews.firstMatch.swipeUp() }
        try tap(actions, "Legacy GA 001 book actions")
        try require(app.buttons["update-book-ga-001"], "Update action in the legacy book menu")
        try tap(app.buttons["Buchdetails"], "Legacy GA 001 book details")
        try require(app.navigationBars["Buchdetails"], "Legacy edition details")
        try require(app.staticTexts["Update verfügbar"].firstMatch, "New edition badge while old text is readable")
        try tap(app.buttons["update-book-ga-001"], "First book update with a deliberate server failure")
        try require(app.alerts["Aktion nicht abgeschlossen"], "Failed update error")
        try tap(app.alerts["Aktion nicht abgeschlossen"].buttons["OK"], "Dismiss the failed update")
        try require(app.staticTexts["Update verfügbar"].firstMatch, "Failed update keeps the pending badge")
        try require(app.buttons["update-book-ga-001"], "Failed update can be retried")
        capture("Failed update preserves the downloaded edition")

        // The wrapper checks the exact original cache bytes when this retry
        // reaches its server, before supplying the successful response.
        try tap(app.buttons["update-book-ga-001"], "Download the verified corrected edition")

        let updated = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"),
                                                object: app.buttons["update-book-ga-001"])
        let updateResult = await XCTWaiter.fulfillment(of: [updated], timeout: 20)
        check(updateResult == .completed,
              "The update action must disappear after installing the verified new edition")
        check(!app.staticTexts["Update verfügbar"].exists, "The details badge must disappear with the update action")
        capture("Corrected edition replaces the legacy book in current details")
        try tap(app.buttons["Schließen"], "Close the updated book details")
        try search("Auf Schröers Empfehlung")
        let correctedHit = app.buttons.matching(NSPredicate(format:
            "label CONTAINS %@ AND NOT label CONTAINS %@", "GA 001", "· Werk")).firstMatch
        try tap(correctedHit, "Open the corrected source paragraph through full-text search")
        try require(app.buttons["Buch schließen"].firstMatch, "Reader after the successful update")
        try require(app.textViews.matching(NSPredicate(format: "label CONTAINS %@",
            "Auf Schröers Empfehlung hin lud mich 1883 Joseph Kürschner ein")).firstMatch,
                    "Corrected source paragraph is visible in native text")
        check(!app.textViews.matching(NSPredicate(format: "label CONTAINS %@",
            "Veraltete QA-Textfassung.")).firstMatch.exists, "The old first-chapter body must be replaced")
        try require(app.staticTexts["Abschnitt 1 von 28"], "The updated book retains all 28 sections")
        capture("Corrected GA 001 first chapter")
        try closeReader()

        app.terminate()
        app.launchEnvironment["GA_SERVER_BASE_URL"] = "http://127.0.0.1:1"
        app.launch()
        try require(app.buttons["Bibliothek"].firstMatch, "Updated library restored without a server")
        try search("Auf Schröers Empfehlung")
        let offlineHit = app.buttons.matching(NSPredicate(format:
            "label CONTAINS %@ AND NOT label CONTAINS %@", "GA 001", "· Werk")).firstMatch
        try tap(offlineHit, "Updated GA 001 full-text passage restored offline")
        try require(app.buttons["Buch schließen"].firstMatch, "Updated book opens with an unreachable server")
        try require(app.textViews.matching(NSPredicate(format: "label CONTAINS %@",
            "Auf Schröers Empfehlung hin lud mich 1883 Joseph Kürschner ein")).firstMatch,
                    "Corrected text survives offline process relaunch")
        check(!app.textViews.matching(NSPredicate(format: "label CONTAINS %@",
            "Veraltete QA-Textfassung.")).firstMatch.exists, "Offline relaunch must keep the corrected edition")
        capture("Verified book update survives offline relaunch")
        try closeReader()
    }

    func testEPUBSharingFromLibraryDetailsAndReader() throws {
        try launch()
        try tab("Bibliothek")
        let actions = app.buttons["Aktionen für Die Philosophie der Freiheit"]
        let originallyGrid = actions.exists
        if !originallyGrid {
            try tap(app.buttons["Bibliotheksoptionen"], "Library options")
            try tap(app.buttons["Cover"], "Cover view for book actions")
        }

        try tap(actions, "Philosophy book actions")
        try tap(app.buttons["share-epub-ga-004"], "Share EPUB from the library")
        try inspectAndDismissEPUBShareSheet("EPUB shared from library actions")

        try tap(actions, "Philosophy book actions")
        try tap(app.buttons["Buchdetails"], "Philosophy book details")
        try require(app.navigationBars["Buchdetails"], "Book details sheet")
        try tap(app.buttons["share-epub-ga-004"], "Share EPUB from book details")
        try inspectAndDismissEPUBShareSheet("EPUB shared from book details")
        try require(app.navigationBars["Buchdetails"], "Book details remain after sharing")
        try tap(app.buttons["Schließen"], "Close book details")

        if !originallyGrid {
            try tap(app.buttons["Bibliotheksoptionen"], "Restore library options")
            try tap(app.buttons["Liste"], "Restore library list view")
        }
        try openPhilosophy()
        try tap(app.buttons["Weitere Leseoptionen"], "Reader menu")
        try tap(app.buttons["share-epub-ga-004"], "Share EPUB from the reader")
        try inspectAndDismissEPUBShareSheet("EPUB shared from reader options")
        try require(app.textViews.firstMatch, "Reader remains open after sharing")
        try closeReader()
    }

    func testChapterThemeAndBookmarkSurviveReaderDismissalAndRelaunch() throws {
        try launch()
        try openPhilosophy()
        try chooseChapter("I. Das bewusste menschliche Handeln")
        try require(app.staticTexts["Abschnitt 2 von 18"], "Selected chapter")
        let text = app.textViews.firstMatch
        try require(text, "Native reading text")
        text.swipeUp()
        text.swipeUp()
        capture("Reader at scrolled passage")

        try tap(app.buttons["Leseeinstellungen"], "Reader settings")
        try require(app.buttons["Papier"], "Paper theme")
        let previousTheme = ["Automatisch", "Hell", "Papier", "Dunkel"].first { app.buttons[$0].isSelected }
        let previousFont = ["Serif", "Sans Serif"].first { app.buttons[$0].isSelected }
        try tap(app.buttons["Papier"], "Paper theme")
        try tap(app.buttons["Sans Serif"], "Sans-serif font")
        check(app.buttons["Papier"].isSelected)
        check(app.buttons["Sans Serif"].isSelected)
        capture("Reader settings preview")
        try tap(app.buttons["Fertig"], "Close settings")

        try tap(app.buttons["Weitere Leseoptionen"], "Reader menu")
        let createdBookmark = app.buttons["Lesezeichen setzen"].exists
        if createdBookmark {
            try tap(app.buttons["Lesezeichen setzen"], "Set bookmark")
        } else {
            try tap(app.buttons["Markierungen und Notizen"], "Existing annotation list")
            try tap(app.buttons["Fertig"], "Close annotations")
        }
        let savedProgress = try readingProgress()
        capture("Reader before dismissal")
        try closeReader()
        try tab("Jetzt lesen")
        try tap(app.buttons.matching(NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@",
                                                 "Die Philosophie der Freiheit", "Weiterlesen")).firstMatch, "Continue reading")
        try require(app.staticTexts["Abschnitt 2 von 18"], "Chapter restored on reopen")
        check(try readingProgress() == savedProgress, "Scrolled reading progress must survive dismissal")
        capture("Reader after dismissal")
        try tap(app.buttons["Weitere Leseoptionen"], "Reader menu")
        try require(app.buttons["Lesezeichen entfernen"], "Bookmark restored at saved position")
        try tap(app.buttons["Markierungen und Notizen"], "Annotations")
        try tap(app.buttons["Lesezeichen"], "Bookmark filter")
        check(!app.staticTexts["Noch keine Notizen"].exists)
        capture("Persisted bookmark")
        try tap(app.buttons["Fertig"], "Close annotations")
        try closeReader()

        app.terminate()
        app.launch()
        try require(app.buttons["Jetzt lesen"], "Home after relaunch")
        try tap(app.buttons.matching(NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@",
                                                 "Die Philosophie der Freiheit", "Weiterlesen")).firstMatch, "Continue after relaunch")
        try require(app.staticTexts["Abschnitt 2 von 18"], "Chapter restored after relaunch")
        check(try readingProgress() == savedProgress, "Scrolled reading progress must survive process relaunch")
        capture("Reader after process relaunch before restoring appearance")
        try tap(app.buttons["Leseeinstellungen"], "Restored settings")
        check(app.buttons["Papier"].isSelected)
        check(app.buttons["Sans Serif"].isSelected)
        if let previousTheme { try tap(app.buttons[previousTheme], "Restore prior theme") }
        if let previousFont { try tap(app.buttons[previousFont], "Restore prior font") }
        try tap(app.buttons["Fertig"], "Close settings")
        if createdBookmark {
            try tap(app.buttons["Weitere Leseoptionen"], "Reader menu")
            try tap(app.buttons["Lesezeichen entfernen"], "Remove only the bookmark created by this test")
        }
        capture("Reader restored after process relaunch")
        try closeReader()
    }

    func testReaderScrollsThroughShortLineChapter() throws {
        try launch(readerTheme: "dark")
        try search("Sprüche, Dichtungen, Mantren. Ergänzungsband")
        let work = app.buttons.matching(NSPredicate(format:
            "label CONTAINS %@ AND label CONTAINS %@", "Sprüche, Dichtungen, Mantren. Ergänzungsband", "· Werk")).firstMatch
        try tap(work, "GA 040a book result")
        try require(app.buttons["Buch schließen"].firstMatch, "GA 040a reader")
        // Selecting the chapter explicitly starts at its beginning even when
        // this dedicated simulator has a reading position from an earlier run.
        try chooseChapter("Nachträge zu «Wahrspruchworte» GA 40")
        try require(app.staticTexts["Abschnitt 1 von 11"], "Short-line first chapter")

        let text = app.textViews.firstMatch
        try require(text, "Scrollable native short-line chapter")
        let firstPoem = app.textViews.matching(NSPredicate(format:
            "label BEGINSWITH %@", "Wandernd in Geistesweiten")).firstMatch
        let lastPoem = app.textViews.matching(NSPredicate(format:
            "label BEGINSWITH %@", "Wahr, gut, stark werden.")).firstMatch
        try require(firstPoem, "First poem at the beginning of the chapter")
        let initialFrame = firstPoem.frame
        let initialProgress = try readingProgressPercent()
        check(initialProgress == 0, "The first chapter must start at zero progress")
        capture("Short-line chapter before scrolling")

        for _ in 0..<3 { text.swipeUp() }
        let increased = XCTNSPredicateExpectation(predicate: NSPredicate { [weak self] _, _ in
            guard let self, let value = self.app.progressIndicators["Lesefortschritt"].firstMatch.value as? String,
                  let percent = Int(value.filter(\.isNumber)) else { return false }
            return percent > initialProgress
        }, object: nil)
        let didIncrease = XCTWaiter.wait(for: [increased], timeout: 8) == .completed
        let finalProgress = try readingProgressPercent()
        let diagnostics = XCTAttachment(string:
            "Progress before: \(initialProgress)%; after: \(finalProgress)%\n" +
            "First poem before: \(initialFrame); after: \(firstPoem.frame)\n" +
            "Last poem: \(lastPoem.exists ? String(describing: lastPoem.frame) : "absent"); reading view: \(text.frame)\n\n" + app.debugDescription)
        diagnostics.name = "Short-line scroll metrics and accessibility hierarchy"
        diagnostics.lifetime = .keepAlways
        add(diagnostics)
        capture("Short-line chapter after scrolling")
        check(didIncrease && finalProgress > initialProgress,
              "Swiping the short-line chapter must advance its reading progress; before \(initialProgress)%, after \(finalProgress)%")
        check(firstPoem.frame.minY < initialFrame.minY - 100,
              "The first poem must move upward by more than 100 points after swiping")
        try require(lastPoem, "Later poem after scrolling")
        let visibleLaterText = lastPoem.frame.intersection(text.frame)
        // UIKit exposes each short line as its own accessibility text view.
        check(!visibleLaterText.isNull && visibleLaterText.height > 10,
              "Swiping must reveal the chapter's later line ‘Wahr, gut, stark werden.’")

        try closeReader()
    }

    func testSourceNotesAndRealTextSelectionSavePersonalNote() throws {
        try launch()
        try openPhilosophy()
        try chooseChapter("V. Das Erkennen der Welt")
        try require(app.staticTexts["Abschnitt 6 von 18"], "Chapter containing source notes")
        try tap(app.buttons["Weitere Leseoptionen"], "Reader menu")
        try tap(app.buttons["Anmerkungen der Ausgabe"], "Source annotations")
        try require(app.staticTexts["Anmerkung 1"], "Original source annotation")
        capture("Original source annotation")
        try tap(app.buttons["Fertig"], "Close source annotations")

        let text = app.textViews.firstMatch
        try require(text, "Native text selection surface")
        let paragraph = app.textViews.matching(NSPredicate(format: "label BEGINSWITH %@",
                                                            "Aus den vorhergehenden Betrachtungen")).firstMatch
        try require(paragraph, "Visible source-body paragraph")
        let visibleBody = paragraph.frame.intersection(text.frame)
        check(!visibleBody.isNull && !visibleBody.isEmpty, "Body paragraph must be visible for native selection")
        let bodyPoint = paragraph.coordinate(withNormalizedOffset: .zero).withOffset(
            CGVector(dx: visibleBody.midX - paragraph.frame.minX, dy: visibleBody.midY - paragraph.frame.minY))
        bodyPoint.press(forDuration: 1.2)
        try require(app.menuItems["Notiz hinzufügen"].firstMatch, "Native selected-text note action")
        capture("Native selected-text menu with marking and note")
        try tap(app.menuItems["Markierung"].firstMatch, "Native selected-text marking action")
        for label in ["Gelb markieren", "Grün markieren", "Blau markieren", "Rosa markieren", "Violett markieren", "Unterstreichen"] {
            try require(app.buttons[label], "Marking palette action " + label)
            check(app.buttons[label].frame.height >= 44, "Every marking action needs a comfortable touch target")
        }
        capture("Native selection and five-color marking palette")
        try tap(app.buttons["Violett markieren"], "Color this selected text purple")
        check(app.buttons["Violett markieren"].isSelected)
        try tap(app.buttons["Unterstreichen"], "Underline the same selected text")
        check(app.buttons["Unterstreichen"].isSelected)
        capture("Purple underline selected in marking palette")

        let outside = text.coordinate(withNormalizedOffset: CGVector(dx: 0.02, dy: 0.15))
        outside.tap()
        bodyPoint.tap()
        try require(app.buttons["Entfernen"], "Single tap opens existing-mark actions")
        try require(app.buttons["Schreibtools"], "System Writing Tools affordance")
        #if os(iOS)
        if !UIWritingToolsCoordinator.isWritingToolsAvailable {
            check(!app.buttons["Schreibtools"].isEnabled,
                  "Writing Tools must be disabled when the system reports no availability")
        }
        #endif
        check(app.buttons["Inhaltsverzeichnis"].exists && app.buttons["Leseeinstellungen"].exists,
              "Tapping a marking must keep reading controls visible")
        capture("Single-tap anchored actions and unavailable Writing Tools")
        try tap(app.buttons["Markierung"].firstMatch, "Open existing marking style")
        try require(app.buttons["Unterstreichen"], "Underline action after reopening the marking palette")
        check(app.buttons["Unterstreichen"].isSelected, "Single-tap editing preserves the underline style")
        outside.tap()
        bodyPoint.tap()
        try tap(app.buttons["Notiz hinzufügen"].firstMatch, "Add a note to the existing marked quote")
        let uniqueNote = "GA native annotation QA " + UUID().uuidString
        let editor = app.textViews["reader-note-editor"]
        try require(editor, "Focused personal note editor")
        let quote = app.staticTexts["reader-note-quote"]
        try require(quote, "Quoted selection in the note editor")
        let selectedQuote = quote.label
        check(!selectedQuote.isEmpty, "The note must show its selected quote")
        check((editor.value as? String ?? "").isEmpty, "This test must not overwrite an existing personal note")
        check(app.keyboards.firstMatch.waitForExistence(timeout: 5), "The note editor should focus automatically")
        capture("Focused quote note editor with keyboard and checkmark save")
        editor.typeText(uniqueNote)
        try tap(app.buttons["Notiz speichern"], "Save using the note checkmark")
        try require(app.buttons["Weitere Leseoptionen"], "Return to the reader after saving")
        capture("Reader with saved purple underline note")
        try closeReader()

        try openPhilosophy()
        try require(app.staticTexts["Abschnitt 6 von 18"], "Marked chapter restored after reopening")
        bodyPoint.tap()
        try require(app.buttons["Notiz bearbeiten"], "Single tap restores the persisted note actions")
        try tap(app.buttons["Markierung"].firstMatch, "Inspect persisted marking style")
        try require(app.buttons["Unterstreichen"], "Persisted underline action")
        check(app.buttons["Unterstreichen"].isSelected, "Underline persists across reader dismissal")
        outside.tap()
        bodyPoint.tap()
        try tap(app.buttons["Notiz bearbeiten"], "Reopen the saved quote note")
        let reopenedEditor = app.textViews["reader-note-editor"]
        try require(reopenedEditor, "Reopened note editor")
        check(reopenedEditor.value as? String == uniqueNote, "The note text must persist")
        check(app.staticTexts["reader-note-quote"].label == selectedQuote, "The original quote must persist")
        capture("Reopened quote note with saved text")
        try tap(app.buttons["Notiz speichern"], "Close reopened note")

        bodyPoint.tap()
        try require(app.buttons["Notiz bearbeiten"], "Persisted note actions before searching")
        let annotationSearch = app.buttons.matching(NSPredicate(format:
            "label == %@ AND (identifier == %@ OR identifier == %@)",
            "Suchen", "reader-annotation-menu", "reader-annotation-search")).firstMatch
        try tap(annotationSearch, "Search the marked quote from its anchored menu")
        try require(app.navigationBars["Im Buch suchen"], "In-book selected-quote search")
        let searchField = app.searchFields["Wort oder Textstelle"]
        try require(searchField, "Prefilled selected-quote search field")
        check(searchField.value as? String == selectedQuote,
              "Suchen must prefill the exact selected quote; field: \(String(describing: searchField.value)), quote: \(selectedQuote)")
        capture("In-book search prefilled from existing marking")
        try tap(app.buttons["Fertig"], "Close selected-quote search")

        // Identify only this test's uniquely named note before removing via the tap menu.
        try tap(app.buttons["Weitere Leseoptionen"], "Reader menu")
        try tap(app.buttons["Markierungen und Notizen"], "Persisted annotation list")
        try require(app.staticTexts[uniqueNote], "Unique QA note before cleanup")
        let testNote = app.cells.containing(.staticText, identifier: uniqueNote).firstMatch
        try require(testNote, "Only the uniquely named QA annotation")
        check(app.cells.containing(.button, identifier: selectedQuote).count == 1,
              "Recoloring, underline and note editing must share one annotation")
        capture("One persisted quote annotation after all edits")
        try tap(app.buttons["Fertig"], "Close annotations")
        bodyPoint.tap()
        try tap(app.buttons["Entfernen"], "Remove the test annotation using its tap menu")
        try tap(app.buttons["Weitere Leseoptionen"], "Reader menu after removal")
        try tap(app.buttons["Markierungen und Notizen"], "Verify targeted cleanup")
        check(!app.staticTexts[uniqueNote].exists, "The uniquely named QA note must be removed")
        capture("Annotation list after targeted tap-menu removal")
        try tap(app.buttons["Fertig"], "Close annotations")
        try closeReader()
    }

    /// Run with tools/check_text_reports_ui.py. The first response deliberately
    /// fails after receiving the report, so retry must preserve its UUID/body.
    func testSelectedTextReportCancelFailureRetryAndConfirmation() async throws {
        let fixtureURL = URL(string: "http://127.0.0.1:4184/qa/state")!
        do {
            let (_, response) = try await URLSession.shared.data(for: URLRequest(url: fixtureURL, timeoutInterval: 2))
            guard let response = response as? HTTPURLResponse,
                  response.value(forHTTPHeaderField: "X-GA-Text-Report-QA") == "1" else {
                throw XCTSkip("Run this regression through tools/check_text_reports_ui.py")
            }
        } catch { throw XCTSkip("Run this regression through tools/check_text_reports_ui.py") }
        try launch(accessBaseURL: "http://127.0.0.1:4184")
        continueAfterFailure = true
        defer { app.terminate() }
        try openPhilosophy()
        try chooseChapter("V. Das Erkennen der Welt")

        let text = app.textViews.firstMatch
        let paragraph = app.textViews.matching(NSPredicate(format: "label BEGINSWITH %@",
            "Aus den vorhergehenden Betrachtungen")).firstMatch
        try require(paragraph, "Actual reading paragraph for error reporting")
        let visible = paragraph.frame.intersection(text.frame)
        check(!visible.isNull && !visible.isEmpty, "Reporting selects visible source-body text")
        let bodyPoint = paragraph.coordinate(withNormalizedOffset: .zero).withOffset(
            CGVector(dx: visible.midX - paragraph.frame.minX, dy: visible.midY - paragraph.frame.minY))
        check(!app.menuItems["Fehler melden …"].exists, "The report action needs a native text selection")
        bodyPoint.press(forDuration: 1.2)
        try tapSelectedTextReport()
        try require(app.staticTexts["reader-report-quote"], "Captured selected quote")
        check(app.buttons["reader-report-send"].isEnabled, "A description is optional")
        try tap(app.buttons["reader-report-cancel"], "Cancel before any report is sent")
        try require(app.buttons["Weitere Leseoptionen"], "Reader after report cancellation")
        let (cancelState, _) = try await URLSession.shared.data(from: fixtureURL)
        let cancelled = try XCTUnwrap(JSONSerialization.jsonObject(with: cancelState) as? [String: Any])
        check((cancelled["reports"] as? [[String: Any]])?.isEmpty == true,
              "Cancelling the form must not send a report")

        bodyPoint.press(forDuration: 1.2)
        try tapSelectedTextReport()
        let quote = app.staticTexts["reader-report-quote"].label
        check(!quote.isEmpty, "The original selected text must be shown")
        let message = "In dieser Textstelle fehlt ein Wort."
        let editor = app.textViews["reader-report-message"]
        try tap(editor, "Optional error description")
        editor.typeText(message)
        capture("Selected-text report before sending")
        try tap(app.buttons["reader-report-send"], "First report response deliberately fails")
        try require(app.staticTexts["reader-report-error"], "Failure leaves the report form open")
        check(editor.value as? String == message, "The error description must survive a failed response")
        check(app.staticTexts["reader-report-quote"].label == quote, "The selected quote must survive a failed response")
        capture("Report input preserved for retry")
        try tap(app.buttons["reader-report-send"], "Retry the unchanged logical report")
        try require(app.alerts["Meldung gesendet"], "Confirmed receipt closes the report sheet")
        check(!app.buttons["reader-report-send"].exists, "Success must close the report form")
        try tap(app.alerts["Meldung gesendet"].buttons["OK"], "Acknowledge confirmed report receipt")
        try require(app.buttons["Weitere Leseoptionen"], "Reading continues after success")
        let (stateData, _) = try await URLSession.shared.data(from: fixtureURL)
        let state = try XCTUnwrap(JSONSerialization.jsonObject(with: stateData) as? [String: Any])
        let reports = try XCTUnwrap(state["reports"] as? [[String: Any]])
        check(reports.count == 2, "The fixture must receive the first attempt and one retry")
        guard reports.count == 2 else { return }
        let first = try JSONSerialization.data(withJSONObject: reports[0], options: .sortedKeys)
        let retry = try JSONSerialization.data(withJSONObject: reports[1], options: .sortedKeys)
        check(first == retry, "Retry must send the identical UUID and payload")
        check(reports[0]["selected_text"] as? String == quote, "The service receives the exact selected text")
        check(reports[0]["message"] as? String == message, "The service receives the optional description")
        check(reports[0]["book_id"] as? String == "ga-004", "The selected quote is assigned to its book")
        check(reports[0]["platform"] as? String == "ios", "The platform is included")
        let start = try XCTUnwrap(reports[0]["selection_start"] as? Int)
        let end = try XCTUnwrap(reports[0]["selection_end"] as? Int)
        check(end - start == (quote as NSString).length, "Selection offsets use UTF-16 units")
        check(reports[0]["email"] == nil, "Reporting needs no contact address")
        capture("Report receipt and return to reading")
        try closeReader()
    }

    func testHomeLibraryAndReaderAtCurrentAppearanceAndTextSize() throws {
        try launch()
        capture("Home at current appearance and text size")
        try tab("Bibliothek")
        let book = app.buttons.matching(NSPredicate(format:
            "label CONTAINS %@ AND NOT label BEGINSWITH %@", "Die Philosophie der Freiheit", "Aktionen für")).firstMatch
        try require(book, "Readable book at current text size")
        capture("Library at current appearance and text size")
        try tap(book, "Open book at current text size")
        try require(app.textViews.firstMatch, "Readable native text")
        try require(app.buttons["Buch schließen"].firstMatch, "Accessible reader dismissal")
        try require(app.buttons["Leseeinstellungen"], "Accessible reader appearance controls")
        try tap(app.buttons["Leseeinstellungen"], "Reader appearance at current system settings")
        try revealThemePicker()
        let previousTheme = selectedTheme()
        try chooseTheme("Papier")
        capture("Reader settings at current appearance and text size")
        try chooseTheme("Automatisch")
        try tap(app.buttons["Fertig"], "Close settings")
        capture("Reader at current appearance and text size")
        try tap(app.buttons["Weitere Leseoptionen"], "Reader menu at current text size")
        try tap(app.buttons["Markierungen und Notizen"], "Annotations at current text size")
        let bookmark = app.cells.containing(.staticText, identifier: "I. Das bewusste menschliche Handeln").firstMatch
        if app.buttons["Lesezeichen"].exists && bookmark.exists {
            let quote = bookmark.buttons.matching(NSPredicate(format:
                "label != %@ AND label != %@ AND label != %@", "Zur Stelle", "Bearbeiten", "Löschen")).firstMatch
            try require(quote, "Bookmark quote")
            let firstActionY = ["Zur Stelle", "Bearbeiten", "Löschen"].map { bookmark.buttons[$0].frame.minY }.min() ?? .infinity
            let gap = firstActionY - quote.frame.maxY
            check(gap >= 0 && gap <= 44, "Bookmark actions must follow the quote without a large blank gap")
            check(bookmark.frame.height <= 250, "Standard bookmark row should fit its caption, quote, and one action row")
        }
        capture("Annotations at current appearance and text size")
        try tap(app.buttons["Fertig"], "Close annotations")
        if let previousTheme {
            try tap(app.buttons["Leseeinstellungen"], "Restore prior reading theme")
            try chooseTheme(previousTheme)
            try tap(app.buttons["Fertig"], "Close settings")
        }
        try closeReader()
    }

    func testKutschereiCoversInHomeLibraryAndRoseLectureCategory() throws {
        try launch()
        capture("Kutscherei cloth and gold covers on Home")
        try tab("Bibliothek")
        let originallyGrid = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Aktionen für")).firstMatch.exists
        if !originallyGrid {
            try tap(app.buttons["Bibliotheksoptionen"], "Library options")
            try tap(app.buttons["Cover"], "Cover view")
        }
        capture("Kutscherei cloth and gold library grid")

        let roseTitle = "Die Offenbarungen des Karma"
        let rose = app.buttons.matching(NSPredicate(format:
            "label CONTAINS %@ AND NOT label BEGINSWITH %@", roseTitle, "Aktionen für")).firstMatch
        let libraryScroll = app.scrollViews.firstMatch
        for _ in 0..<8 {
            if rose.exists && rose.isHittable { break }
            try require(libraryScroll, "Scrollable cover library")
            libraryScroll.swipeUp()
        }
        try require(rose, "Rose lecture-category book")
        check(rose.isHittable, "Rose lecture-category cover must be visible and tappable")
        try require(app.buttons["Aktionen für " + roseTitle], "Rose book cover actions")
        capture("Kutscherei GA120 rose lecture cloth cover")

        try tap(app.buttons["Bibliotheksoptionen"], "Library options")
        try tap(app.buttons["Liste"], "List view")
        let listRose = app.buttons.matching(NSPredicate(format:
            "label CONTAINS %@ AND NOT label BEGINSWITH %@", roseTitle, "Aktionen für")).firstMatch
        for _ in 0..<8 {
            if listRose.exists && listRose.isHittable { break }
            try require(app.scrollViews.firstMatch, "Scrollable list library")
            app.scrollViews.firstMatch.swipeUp()
        }
        try require(listRose, "Rose lecture book in list view")
        check(listRose.isHittable, "Cloth cover and external title must remain tappable in list view")
        capture("Kutscherei GA120 rose lecture cover in list")
        if originallyGrid {
            try tap(app.buttons["Bibliotheksoptionen"], "Restore library options")
            try tap(app.buttons["Cover"], "Restore cover view")
        }
        try tab("Jetzt lesen")
    }

    func testAccessGateTrialPurchaseRestoreAndRefund() async throws {
        let session = try SKTestSession(configurationFileNamed: "GA")
        session.resetToDefaultState()
        session.clearTransactions()
        session.disableDialogs = true
        defer { session.clearTransactions(); app?.terminate() }
        try launch()
        continueAfterFailure = true
        try tap(app.buttons["show-access"].firstMatch, "App access")
        try require(app.buttons["purchase-annual"], "Annual choice")
        let available = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: app.buttons["purchase-annual"])
        let loaded = await XCTWaiter.fulfillment(of: [available], timeout: 20)
        check(loaded == .completed, "Real StoreKit annual product loads")
        check(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "30", "Jahr")).firstMatch.exists, "Localized annual price")
        check(app.buttons["purchase-annual"].label.contains("3 Monate"), "Eligible Apple account sees real three-month trial")
        capture("AppStore-04-Solidarischer-Zugang")
        try tap(app.buttons["close-access"], "Close access screen")
        let firstBook = app.buttons.matching(NSPredicate(format: "label CONTAINS %@ AND NOT label BEGINSWITH %@", "Die Philosophie der Freiheit", "Aktionen für")).firstMatch
        try tap(firstBook, "All reading requires access")
        try require(app.buttons["purchase-annual"], "Reader is gated before a purchase")
        check(!app.buttons["Buch schließen"].exists, "No reading access without entitlement")
        try tap(app.buttons["purchase-annual"], "Buy native Apple trial")
        try require(app.staticTexts["Dein Zugang ist aktiv"], "Confirmed purchase unlocks access")
        try tap(app.buttons["close-access"], "Close purchased access")
        try tap(firstBook, "Read after verified native trial")
        try require(app.buttons["Buch schließen"].firstMatch, "Reader after entitlement")
        try closeReader()
        try tap(app.buttons["show-access"].firstMatch, "Restore controls")
        for _ in 0..<5 where !app.buttons["restore-purchases"].isHittable { app.scrollViews["access-content"].swipeUp() }
        try tap(app.buttons["restore-purchases"], "Restore verified Apple purchase")
        try require(app.staticTexts["Dein Abo wurde wiederhergestellt."], "Restore confirmation")
        let purchased = try XCTUnwrap(session.allTransactions().first)
        try session.refundTransaction(identifier: purchased.identifier)
        app.terminate()
        app.launch()
        try require(app.buttons["Bibliothek"].firstMatch, "Relaunch after refund")
        try tap(app.buttons.matching(NSPredicate(format: "label CONTAINS %@ AND NOT label BEGINSWITH %@", "Die Philosophie der Freiheit", "Aktionen für")).firstMatch, "Refund removes access")
        try require(app.buttons["purchase-annual"], "Refunded purchase is gated")
        check(!app.buttons["Buch schließen"].exists, "Refund never leaves active reading access")
    }

    func testFreeRequestFailureKeepsTextAndBlankRequestDisabled() throws {
        app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages", "(de)", "-AppleLocale", "de_DE"]
        app.launchEnvironment["GA_ACCESS_BASE_URL"] = "http://127.0.0.1:1"
        app.launch()
        defer { app.terminate() }
        try require(app.buttons["show-access"].firstMatch, "Access entry point")
        try tap(app.buttons["show-access"].firstMatch, "Open free request screen")
        for _ in 0..<5 where !app.buttons["open-free-request"].isHittable { app.scrollViews["access-content"].swipeUp() }
        try tap(app.buttons["open-free-request"], "Open free request")
        for _ in 0..<4 where !app.textViews["free-request-message"].isHittable { app.scrollViews["access-content"].swipeUp() }
        let message = app.textViews["free-request-message"]
        try tap(message, "Free request field")
        message.typeText("Bitte ermögliche mir ein kostenloses Jahr.")
        try tap(app.buttons["dismiss-free-keyboard"], "Dismiss request keyboard")
        for _ in 0..<4 where !app.buttons["submit-free-request"].isHittable { app.scrollViews["access-content"].swipeUp() }
        try tap(app.buttons["submit-free-request"], "Submit to unreachable server")
        try require(app.staticTexts["access-error"], "Actual request failure")
        check(!app.staticTexts["access-error"].label.contains("sicher gespeichert"), "Failure must reach the unavailable server after secure device storage")
        check((message.value as? String)?.contains("Bitte ermögliche") == true, "Request is retained for retry")
        check(!app.staticTexts["Dein Zugang ist aktiv"].exists, "Failed request doesn't grant access")
        capture("QA-Free-Request-Failure")
    }

    func testFreeRequestGrantsActualServerAccess() throws {
        let session = try SKTestSession(configurationFileNamed: "GA")
        session.resetToDefaultState()
        session.clearTransactions()
        app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages", "(de)", "-AppleLocale", "de_DE"]
        app.launchEnvironment["GA_ACCESS_BASE_URL"] = "http://127.0.0.1:4181"
        app.launchEnvironment["GA_USE_LOCAL_STOREKIT"] = "1"
        app.launch()
        defer { app.terminate() }
        try require(app.buttons["show-access"].firstMatch, "Server free-access entry")
        try tap(app.buttons["show-access"].firstMatch, "Actual server request")
        if app.staticTexts["Dein Zugang ist aktiv"].exists {
            try deleteQAFreeAccess()
            try tap(app.buttons["close-access"], "Close previous QA access")
            try tap(app.buttons["show-access"].firstMatch, "Fresh server request")
        }
        for _ in 0..<6 where !app.buttons["open-free-request"].isHittable { app.scrollViews["access-content"].swipeUp() }
        try tap(app.buttons["open-free-request"], "Open server request")
        for _ in 0..<5 where !app.textViews["free-request-message"].isHittable { app.scrollViews["access-content"].swipeUp() }
        check(!app.buttons["submit-free-request"].isEnabled, "Empty requests cannot be submitted")
        try tap(app.textViews["free-request-message"], "Actual server request message")
        app.textViews["free-request-message"].typeText("Bitte ermögliche mir ein kostenloses Jahr.")
        try tap(app.buttons["dismiss-free-keyboard"], "Dismiss request keyboard")
        for _ in 0..<5 where !app.buttons["submit-free-request"].isHittable { app.scrollViews["access-content"].swipeUp() }
        try tap(app.buttons["submit-free-request"], "Persist and grant on actual Phoenix server")
        try require(app.staticTexts["Dein kostenloses Jahr ist freigeschaltet. Es endet ohne Zahlung."], "Confirmed server grant")
        try tap(app.buttons["close-access"], "Close confirmed grant")
        try tap(app.buttons.matching(NSPredicate(format: "label CONTAINS %@ AND NOT label BEGINSWITH %@", "Die Philosophie der Freiheit", "Aktionen für")).firstMatch, "Server grant permits all reading")
        try require(app.buttons["Buch schließen"].firstMatch, "Reading after actual free-year grant")
        try closeReader()
        app.terminate()
        app.launch()
        try require(app.buttons["show-access"].firstMatch, "Free grant survives relaunch")
        try tap(app.buttons["show-access"].firstMatch, "Saved free access dates")
        try require(app.staticTexts["Dein Zugang ist aktiv"], "Stored grant restored after relaunch")
        try deleteQAFreeAccess()
    }

    private func deleteQAFreeAccess() throws {
        for _ in 0..<8 where !app.buttons["Zugangsdaten löschen"].isHittable { app.scrollViews["access-content"].swipeUp() }
        try tap(app.buttons["Zugangsdaten löschen"], "Delete disposable local QA grant")
        try tap(app.buttons["Gratiszugang und Anfragen löschen"], "Confirm QA grant deletion")
        try require(app.staticTexts["Deine kostenlosen Zugangsdaten und Bitten wurden gelöscht. Ein Apple-Abo kannst du unter „Abo verwalten“ kündigen."], "Server confirms QA data deletion")
        check(!app.staticTexts["Dein Zugang ist aktiv"].exists, "Deleted free grant immediately removes reading access")
    }

    /// Additional marketing captures use the real local free-access API and
    /// ordinary collection/note actions. Existing first-three captures stay intact.
    func testCaptureGermanReadingAndCollectionScreenshots() async throws {
        let session = try SKTestSession(configurationFileNamed: "GA")
        session.resetToDefaultState()
        session.clearTransactions()
        session.disableDialogs = true
        defer { session.clearTransactions(); app?.terminate() }
        app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages", "(de)", "-AppleLocale", "de_DE", "-readerTheme", "paper"]
        app.launchEnvironment["GA_USE_LOCAL_STOREKIT"] = "1"
        // Separate Keychain namespace from earlier disposable access tests.
        app.launchEnvironment["GA_ACCESS_BASE_URL"] = "http://localhost:4181"
        app.launchEnvironment["GA_SERVER_BASE_URL"] = "http://localhost:4181"
        app.launch()
        try require(app.buttons["show-access"].firstMatch, "Local screenshot access")
        try tap(app.buttons["show-access"].firstMatch, "Open local free-access request")
        if !app.staticTexts["Dein Zugang ist aktiv"].exists {
            for _ in 0..<6 where !app.buttons["open-free-request"].isHittable { app.scrollViews["access-content"].swipeUp() }
            try tap(app.buttons["open-free-request"], "Request local screenshot access")
            for _ in 0..<5 where !app.textViews["free-request-message"].isHittable { app.scrollViews["access-content"].swipeUp() }
            try tap(app.textViews["free-request-message"], "Local request message")
            app.textViews["free-request-message"].typeText("Bitte ermögliche mir ein kostenloses Jahr zum Lesen.")
            try tap(app.buttons["dismiss-free-keyboard"], "Dismiss local request keyboard")
            for _ in 0..<5 where !app.buttons["submit-free-request"].isHittable { app.scrollViews["access-content"].swipeUp() }
            try tap(app.buttons["submit-free-request"], "Confirm actual local free grant")
            try require(app.staticTexts["Dein kostenloses Jahr ist freigeschaltet. Es endet ohne Zahlung."], "Confirmed local server grant")
        }
        try tap(app.buttons["close-access"], "Return to library with confirmed access")

        try tab("Bibliothek")
        try tap(app.buttons["Bibliotheksoptionen"], "Collection screenshot library options")
        try tap(app.buttons["Cover"], "Collection screenshot cover view")
        try tap(app.buttons["Bibliotheksoptionen"], "Predictable collection book order")
        try tap(app.buttons["GA-Nummer"], "Sort collection source books by GA number")
        try tap(app.buttons["Bibliotheksoptionen"], "Manage screenshot collections")
        try tap(app.buttons["Sammlungen verwalten"], "Collection editor")
        let collectionNames = ["Gedanken zur Freiheit", "Anthroposophie entdecken", "Mein Lesekreis"]
        // These names belong to this capture on the dedicated QA devices;
        // remove leftovers from an interrupted capture before recreating them.
        for name in collectionNames where app.staticTexts[name].exists {
            try tap(app.cells.containing(.staticText, identifier: name).firstMatch.buttons["Entfernen"], "Reset this capture's collection")
        }
        for name in collectionNames {
            try tap(app.textFields["Name"], "New personal collection name")
            app.textFields["Name"].typeText(name)
            try tap(app.buttons["Sammlung erstellen"], "Create actual personal collection")
        }
        try tap(app.buttons["Fertig"], "Close collection editor")
        if app.buttons["Alle Werke"].exists { /* default collection */ }
        else {
            let collectionFilter = app.buttons.matching(NSPredicate(format: "label IN %@", collectionNames)).firstMatch
            try tap(collectionFilter, "Restore all-works filter")
            try tap(app.buttons["Alle Werke"], "All works for collection membership")
        }
        for title in ["Die Philosophie der Freiheit", "Theosophie", "Wie erlangt man Erkenntnisse der höheren Welten?"] {
            let actions = app.buttons["Aktionen für " + title]
            for _ in 0..<12 where !actions.isHittable { app.scrollViews.firstMatch.swipeUp() }
            try tap(actions, "Collection membership for " + title)
            let membershipMenu = app.buttons["Zu Sammlung hinzufügen"]
            try tap(membershipMenu, "Choose personal collection")
            // On a narrower phone the two-line native submenu label can leave
            // its submenu closed after a center tap. Use its disclosure edge.
            if !app.buttons[collectionNames[0]].waitForExistence(timeout: 2) {
                membershipMenu.coordinate(withNormalizedOffset: CGVector(dx: 0.92, dy: 0.5)).tap()
            }
            try tap(app.buttons[collectionNames[0]], "Add book to actual collection")
        }
        try tap(app.buttons["Bibliotheksoptionen"], "Collection overview")
        try tap(app.buttons["Sammlungen verwalten"], "Show saved collections")
        try require(app.staticTexts["3 Werke"].firstMatch, "Three actual collection members")
        capture("AppStore-04-Sammlungen")
        try tap(app.buttons["Fertig"], "Close collection overview")
        for _ in 0..<12 where !app.buttons["Alle Werke"].isHittable { app.scrollViews.firstMatch.swipeDown() }
        try tap(app.buttons["Alle Werke"], "Filter by saved collection")
        try tap(app.buttons[collectionNames[0]], "Show collection detail")
        try require(app.staticTexts["Die Philosophie der Freiheit"].firstMatch, "Actual collection book")
        capture("AppStore-05-Sammlung-lesen")

        let book = app.buttons.matching(NSPredicate(format: "label CONTAINS %@ AND NOT label BEGINSWITH %@", "Die Philosophie der Freiheit", "Aktionen für")).firstMatch
        try tap(book, "Read from personal collection")
        try require(app.buttons["Inhaltsverzeichnis"], "Real reader controls")
        try tap(app.buttons["Inhaltsverzeichnis"], "Reading table of contents")
        try require(app.navigationBars["Inhaltsverzeichnis"], "Actual book chapters")
        capture("AppStore-06-Inhaltsverzeichnis")
        try tap(app.buttons["Fertig"], "Close table of contents after capture")
        try captureGermanReaderDetails()
        try closeReader()
        try cleanupGermanScreenshotCollections()
        try tap(app.buttons["show-access"].firstMatch, "Cleanup disposable local grant")
        try deleteQAFreeAccess()
    }

    /// Finish reader captures without repeating saved collection screenshots.
    func testCaptureGermanReaderDetailScreenshots() async throws {
        let session = try SKTestSession(configurationFileNamed: "GA")
        session.resetToDefaultState()
        session.clearTransactions()
        session.disableDialogs = true
        defer { session.clearTransactions(); app?.terminate() }
        try launchGermanAdditionalScreenshotApp()
        try tap(app.buttons["show-access"].firstMatch, "Existing disposable screenshot grant")
        try require(app.staticTexts["Dein Zugang ist aktiv"], "Actual local screenshot grant is active")
        try tap(app.buttons["close-access"], "Return to reading")
        try tab("Bibliothek")
        let book = app.buttons.matching(NSPredicate(format: "label CONTAINS %@ AND NOT label BEGINSWITH %@", "Die Philosophie der Freiheit", "Aktionen für")).firstMatch
        try tap(book, "Read the actual saved collection book")
        try require(app.buttons["Inhaltsverzeichnis"], "Actual collection reader")
        try captureGermanReaderDetails()
        try closeReader()
        try cleanupGermanScreenshotCollections()
        try tap(app.buttons["show-access"].firstMatch, "Cleanup disposable local grant")
        try deleteQAFreeAccess()
    }

    func testCaptureGermanExpandedSettingsScreenshot() async throws {
        let session = try SKTestSession(configurationFileNamed: "GA")
        session.resetToDefaultState()
        session.clearTransactions()
        session.disableDialogs = true
        defer { session.clearTransactions(); app?.terminate() }
        try launchGermanAdditionalScreenshotApp()
        try tap(app.buttons["show-access"].firstMatch, "Temporary settings capture access")
        for _ in 0..<6 where !app.buttons["open-free-request"].isHittable { app.scrollViews["access-content"].swipeUp() }
        try tap(app.buttons["open-free-request"], "Actual local settings capture request")
        for _ in 0..<5 where !app.textViews["free-request-message"].isHittable { app.scrollViews["access-content"].swipeUp() }
        try tap(app.textViews["free-request-message"], "Local settings request message")
        app.textViews["free-request-message"].typeText("Bitte ermögliche mir ein kostenloses Jahr zum Lesen.")
        try tap(app.buttons["dismiss-free-keyboard"], "Dismiss settings capture request keyboard")
        for _ in 0..<5 where !app.buttons["submit-free-request"].isHittable { app.scrollViews["access-content"].swipeUp() }
        try tap(app.buttons["submit-free-request"], "Confirm real settings capture grant")
        try require(app.staticTexts["Dein kostenloses Jahr ist freigeschaltet. Es endet ohne Zahlung."], "Confirmed local settings grant")
        try tap(app.buttons["close-access"], "Return to actual reader")
        try tab("Bibliothek")
        let book = app.buttons.matching(NSPredicate(format: "label CONTAINS %@ AND NOT label BEGINSWITH %@", "Die Philosophie der Freiheit", "Aktionen für")).firstMatch
        for _ in 0..<8 where !book.isHittable { app.scrollViews.firstMatch.swipeDown() }
        try tap(book, "Actual reading settings book")
        try require(app.buttons["Leseeinstellungen"], "Real reader settings")
        try tap(app.buttons["Leseeinstellungen"], "Open settings for expanded capture")
        let navigation = app.navigationBars["Leseeinstellungen"]
        try require(navigation, "Actual reading settings sheet")
        // Expand the native detent so the font controls are visible in the
        // marketing image rather than capturing a clipped medium sheet.
        let grabber = app.buttons["Aufzeichnungsblatt"]
        try require(grabber, "Native settings sheet grabber")
        grabber.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
            .press(forDuration: 0.15, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.15)))
        let fontSize = app.sliders["Schriftgröße"]
        let visible = XCTNSPredicateExpectation(predicate: NSPredicate(format: "hittable == true"), object: fontSize)
        let expanded = await XCTWaiter.fulfillment(of: [visible], timeout: 8)
        check(expanded == .completed, "Expanded settings expose the actual font-size control")
        capture("AppStore-07-Leseeinstellungen")
        try tap(app.buttons["Fertig"], "Close expanded settings")
        try closeReader()
        try tap(app.buttons["show-access"].firstMatch, "Delete temporary settings capture grant")
        try deleteQAFreeAccess()
    }

    func testCaptureGermanScreenshotCleanup() throws {
        defer { app?.terminate() }
        try launchGermanAdditionalScreenshotApp()
        try cleanupGermanScreenshotCollections()
        try tap(app.buttons["show-access"].firstMatch, "Cleanup disposable screenshot identity")
        try deleteQAFreeAccess()
    }

    private func launchGermanAdditionalScreenshotApp() throws {
        app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages", "(de)", "-AppleLocale", "de_DE", "-readerTheme", "paper"]
        app.launchEnvironment["GA_USE_LOCAL_STOREKIT"] = "1"
        app.launchEnvironment["GA_ACCESS_BASE_URL"] = "http://localhost:4181"
        app.launchEnvironment["GA_SERVER_BASE_URL"] = "http://localhost:4181"
        app.launch()
        try require(app.buttons["Bibliothek"].firstMatch, "Screenshot library tab")
    }

    private func cleanupGermanScreenshotCollections() throws {
        try tab("Bibliothek")
        try tap(app.buttons["Bibliotheksoptionen"], "Cleanup screenshot collection options")
        try tap(app.buttons["Sammlungen verwalten"], "Cleanup screenshot collections")
        for name in ["Gedanken zur Freiheit", "Anthroposophie entdecken", "Mein Lesekreis"] where app.staticTexts[name].exists {
            try tap(app.cells.containing(.staticText, identifier: name).firstMatch.buttons["Entfernen"], "Remove only this screenshot's collection")
        }
        try tap(app.buttons["Fertig"], "Close collection cleanup")
    }

    private func captureGermanReaderDetails() throws {
        // Visible footer navigation works on phones and the iPad's compact
        // sheet without relying on an off-screen table-of-contents row.
        for _ in 0..<18 {
            let position = app.staticTexts.matching(NSPredicate(format: "label MATCHES %@", "Abschnitt [0-9]+ von 18")).firstMatch
            try require(position, "Actual chapter position")
            guard let current = Int(position.label.split(separator: " ")[1]) else {
                XCTFail("The reader must expose its actual section position")
                return
            }
            if current == 6 { break }
            let forward = current < 6
            try tap(app.buttons[forward ? "Nächster Abschnitt" : "Vorheriger Abschnitt"], "Select the note chapter using visible reader navigation")
            try require(app.staticTexts["Abschnitt \(current + (forward ? 1 : -1)) von 18"], "Reader advances to the actual section")
        }
        try require(app.staticTexts["Abschnitt 6 von 18"], "Real selected chapter")
        try tap(app.buttons["Leseeinstellungen"], "Reading settings screenshot")
        try require(app.navigationBars["Leseeinstellungen"], "Actual reading settings")
        capture("AppStore-07-Leseeinstellungen")
        try tap(app.buttons["Fertig"], "Close reading settings")

        let text = app.textViews.firstMatch
        let paragraph = app.textViews.matching(NSPredicate(format: "label BEGINSWITH %@", "Aus den vorhergehenden Betrachtungen")).firstMatch
        try require(paragraph, "Visible paragraph for actual note selection")
        let visibleBody = paragraph.frame.intersection(text.frame)
        check(!visibleBody.isNull && !visibleBody.isEmpty, "The actual paragraph is visible")
        paragraph.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(
            dx: visibleBody.midX - paragraph.frame.minX, dy: visibleBody.midY - paragraph.frame.minY)).press(forDuration: 1.2)
        try tap(app.menuItems["Notiz hinzufügen"].firstMatch, "Native selection note action")
        let note = "Wie entsteht freies Handeln? Diese Stelle im Lesekreis besprechen."
        let editor = app.textViews["reader-note-editor"]
        try require(editor, "Actual personal note editor")
        check((editor.value as? String ?? "").isEmpty, "Screenshot note uses a fresh selection")
        editor.typeText(note)
        try tap(app.buttons["Notiz speichern"], "Save actual personal note")
        try tap(app.buttons["Weitere Leseoptionen"], "Show saved notes")
        try tap(app.buttons["Markierungen und Notizen"], "Personal annotations")
        try require(app.staticTexts[note], "Saved personal note shown in annotations")
        capture("AppStore-08-Markierungen-und-Notizen")
        let noteCell = app.cells.containing(.staticText, identifier: note).firstMatch
        try tap(noteCell.buttons["Löschen"], "Remove only the screenshot note")
        try tap(app.buttons["Fertig"], "Close annotations after screenshot")
    }

    func testCaptureGermanAppStoreScreenshots() async throws {
        let session = try SKTestSession(configurationFileNamed: "GA")
        session.resetToDefaultState()
        session.clearTransactions()
        session.disableDialogs = true
        defer { session.clearTransactions(); app?.terminate() }
        try launch(readerTheme: "paper")
        continueAfterFailure = true
        try activateTrialForReading()
        capture("AppStore-01-Jetzt-lesen")
        try tab("Bibliothek")
        capture("AppStore-02-Bibliothek")
        let book = app.buttons.matching(NSPredicate(format: "label CONTAINS %@ AND NOT label BEGINSWITH %@", "Die Philosophie der Freiheit", "Aktionen für")).firstMatch
        try tap(book, "App Store reading screenshot")
        try require(app.textViews.firstMatch, "Real original text in reader")
        capture("AppStore-03-Lesen")
        try closeReader()
    }

    private func inspectAndDismissEPUBShareSheet(_ name: String) throws {
        let sheet = app.otherElements["ActivityListView"].firstMatch
        try require(sheet, "Native EPUB sharing sheet")
        let title = sheet.descendants(matching: .any).matching(NSPredicate(format:
            "label CONTAINS %@", "Die Philosophie der Freiheit")).firstMatch
        try require(title, "Book title in native sharing preview")
        let saveToFiles = sheet.cells["In Dateien sichern"].firstMatch
        try require(saveToFiles, "Native file export activity")
        capture(name)

        // Opening the native file picker requests the actual FileRepresentation.
        // Cancel before saving so this check creates no document in the user's Files.
        try tap(saveToFiles, "Prepare the EPUB in the native file picker")
        let filename = "GA 004 - Die Philosophie der Freiheit"
        let suggestedName = app.textFields["DOCPicker.filenameTextField"]
        try require(suggestedName, "Generated EPUB filename in the native file picker")
        check((suggestedName.value as? String)?.hasPrefix(filename) == true,
              "Native file export must use the book's GA number and title as its filename")
        capture(name + " native file picker")
        let filePicker = app.otherElements["Browse View (Picker)"].firstMatch
        try require(filePicker, "Native Files document picker")
        let cancel = filePicker.buttons.matching(NSPredicate(format:
            "label IN %@", ["Abbrechen", "Cancel", "Schließen", "Close"])).firstMatch
        let back = filePicker.buttons["BackButton"]
        if !cancel.exists, back.exists {
            try tap(back, "Return to the file picker's browse root")
            let atRoot = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: back)
            check(XCTWaiter.wait(for: [atRoot], timeout: 8) == .completed,
                  "The Files browse root must finish appearing before cancellation")
        }
        if cancel.waitForExistence(timeout: 3) {
            try tap(cancel, "Cancel file export without saving")
        } else {
            let browseNavigation = filePicker.navigationBars["FullDocumentManagerViewControllerNavigationBar"]
            try tap(browseNavigation.buttons.firstMatch, "Close Files using its leading browse-root button")
        }
        let pickerDismissed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: filePicker)
        check(XCTWaiter.wait(for: [pickerDismissed], timeout: 8) == .completed,
              "The file picker must close without saving the EPUB")

        if sheet.exists {
            let dismissRegion = app.otherElements["PopoverDismissRegion"].firstMatch
            let close = sheet.buttons.matching(NSPredicate(format:
                "label IN %@", ["Schließen", "Close", "Abbrechen", "Cancel"])).firstMatch
            if dismissRegion.exists {
                let upperPoint = CGPoint(x: dismissRegion.frame.midX,
                                         y: dismissRegion.frame.minY + dismissRegion.frame.height * 0.25)
                let outsideFraction = sheet.frame.contains(upperPoint) ? 0.75 : 0.25
                dismissRegion.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: outsideFraction)).tap()
            } else if close.exists {
                close.tap()
            } else {
                sheet.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.05))
                    .press(forDuration: 0.1, thenDragTo: sheet.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.95)))
            }
        }
        let dismissed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: sheet)
        check(XCTWaiter.wait(for: [dismissed], timeout: 8) == .completed,
              "Dismissing the native share sheet must return to the current book screen")
    }

    private func launch(readerTheme: String? = nil, accessBaseURL: String = "http://127.0.0.1:4181") throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages", "(de)", "-AppleLocale", "de_DE"]
        app.launchEnvironment["GA_USE_LOCAL_STOREKIT"] = "1"
        app.launchEnvironment["GA_ACCESS_BASE_URL"] = accessBaseURL
        if let readerTheme {
            // Override the theme only for this process. Changing settings after
            // opening the chapter rebuilds its text and masks first-layout bugs.
            app.launchArguments += ["-readerTheme", readerTheme]
        }
        app.launch()
        try require(app.buttons["Bibliothek"].firstMatch, "Library tab")
        if readerTestStore != nil { try activateTrialForReading() }
    }

    private func activateTrialForReading() throws {
        try tap(app.buttons["show-access"].firstMatch, "Verified test entitlement")
        let product = app.buttons["purchase-annual"]
        let available = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: product)
        check(XCTWaiter.wait(for: [available], timeout: 20) == .completed, "Annual product is available")
        try tap(product, "Real native trial purchase")
        try require(app.staticTexts["Dein Zugang ist aktiv"], "Verified test trial is active")
        try tap(app.buttons["close-access"], "Return to reading")
    }

    private func check(_ condition: Bool, _ message: String = "UI assertion failed",
                       file: StaticString = #filePath, line: UInt = #line) {
        if !condition {
            capture("UI at assertion failure")
            let hierarchy = XCTAttachment(string: app.debugDescription)
            hierarchy.name = "Accessibility hierarchy at failure"
            hierarchy.lifetime = .keepAlways
            add(hierarchy)
            XCTFail(message, file: file, line: line)
        }
    }

    private func openPhilosophy() throws {
        try search("Die Philosophie der Freiheit")
        let work = app.buttons.matching(NSPredicate(format:
            "label CONTAINS %@ AND label CONTAINS %@", "Die Philosophie der Freiheit", "· Werk")).firstMatch
        try tap(work, "Philosophy book result")
        try require(app.buttons["Buch schließen"].firstMatch, "Open reader")
    }

    private func search(_ query: String) throws {
        try tab("Suchen")
        let field = app.searchFields.firstMatch
        if !field.waitForExistence(timeout: 2), app.collectionViews.firstMatch.exists {
            app.collectionViews.firstMatch.swipeDown()
        }
        try tap(field, "Library search field")
        if let old = field.value as? String, !old.isEmpty, old != field.placeholderValue {
            field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: old.count))
        }
        field.typeText(query)
    }

    private func chooseChapter(_ title: String) throws {
        try tap(app.buttons["Inhaltsverzeichnis"], "Table of contents")
        try tap(app.buttons.matching(NSPredicate(format: "label CONTAINS %@", title)).firstMatch, "Chapter " + title)
    }

    private func readingProgress() throws -> String {
        let progress = app.progressIndicators["Lesefortschritt"].firstMatch
        try require(progress, "Reading progress indicator")
        return progress.value as? String ?? ""
    }

    private func tapSelectedTextReport() throws {
        let action = app.menuItems["Fehler melden …"].firstMatch
        // Newer iOS versions expose the expanded native menu as buttons.
        let expandedAction = app.buttons["Fehler melden …"].firstMatch
        for _ in 0..<4 {
            if action.waitForExistence(timeout: 1) {
                try tap(action, "Report action in the real selected-text menu")
                return
            }
            if expandedAction.exists {
                try tap(expandedAction, "Report action in the expanded native selected-text menu")
                return
            }
            let nextPage = app.buttons["Nächste Seite"].firstMatch
            guard nextPage.exists && nextPage.isHittable else { break }
            try tap(nextPage, "Next page of the native selected-text menu")
        }
        try tap(action, "Report action after native menu pagination")
    }

    private func readingProgressPercent() throws -> Int {
        let value = try readingProgress()
        guard let percent = Int(value.filter(\.isNumber)) else {
            check(false, "Reading progress must report a numeric percent, received: \(value)")
            throw UIError.missingElement("Numeric reading progress")
        }
        return percent
    }

    private func selectedTheme() -> String? {
        let titles = ["Automatisch", "Hell", "Papier", "Dunkel"]
        if let segmented = titles.first(where: { app.buttons[$0].exists && app.buttons[$0].isSelected }) { return segmented }
        let menu = themeMenu()
        guard menu.exists else { return nil }
        if let value = menu.value as? String, titles.contains(value) { return value }
        return titles.first { menu.label.contains($0) }
    }

    private func chooseTheme(_ title: String) throws {
        if !app.buttons[title].exists {
            try revealThemePicker()
            let menu = themeMenu()
            try tap(menu, "Accessible theme picker")
        }
        try tap(app.buttons[title], "Theme " + title)
    }

    private func themeMenu() -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: "reader-theme").firstMatch
    }

    private func revealThemePicker() throws {
        if app.buttons["Automatisch"].exists { return }
        for _ in 0..<8 {
            let menu = themeMenu()
            if menu.exists && menu.isHittable { return }
            let collections = app.collectionViews.allElementsBoundByIndex
            guard let form = collections.last else { break }
            form.swipeUp()
        }
        try require(themeMenu(), "Theme picker after scrolling the settings form")
    }

    private func closeReader() throws {
        try tap(app.buttons["Buch schließen"].firstMatch, "Close reader")
        try require(app.buttons["Bibliothek"].firstMatch, "Return to the library")
    }

    private func tab(_ title: String) throws {
        if app.keyboards.firstMatch.exists {
            let closeSearch = app.navigationBars.buttons["Close"].firstMatch
            let cancelSearch = app.navigationBars.buttons["Abbrechen"].firstMatch
            if closeSearch.exists { closeSearch.tap() }
            else if cancelSearch.exists { cancelSearch.tap() }
        }
        try tap(app.buttons[title].firstMatch, title + " tab")
        try require(app.navigationBars[title], title + " destination")
    }

    private func tap(_ element: XCUIElement, _ name: String) throws {
        try require(element, name)
        element.tap()
    }

    private func require(_ element: XCUIElement, _ name: String) throws {
        guard element.waitForExistence(timeout: 12) else {
            capture("Missing " + name)
            XCTFail("Missing " + name + "\n" + app.debugDescription)
            throw UIError.missingElement(name)
        }
    }

    private func capture(_ name: String) {
        let screenshot = app.screenshot()
        let filename = name.replacingOccurrences(of: " ", with: "-") + ".png"
        let output = FileManager.default.temporaryDirectory.appendingPathComponent(filename)
        try? screenshot.pngRepresentation.write(to: output, options: .atomic)
        print("GA QA screenshot: " + output.path)
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private enum UIError: Error { case missingElement(String) }
}
