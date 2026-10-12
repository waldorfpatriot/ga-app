#!/usr/bin/env python3
"""Exercise ReadingStore without touching the real application-support directory.

Run: python3 tools/check_reading_store.py
Requires the macOS Swift toolchain; builds one disposable command-line executable.
The harness is appended to a temporary copy so it can check private merge and
entitlement safety without exposing those implementation details to the app.
"""

from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''

@main
private enum ReadingStoreChecks {
    @MainActor
    static func main() async throws {
        let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        var tick = Date(timeIntervalSince1970: 1_800_000_000)
        let file = root.appendingPathComponent("roundtrip/state.json")
        let store = ReadingStore(fileURL: file, now: { tick })
        try expect(store.position(for: "ga-004") == nil && store.status(for: "ga-004") == .unread, "fresh library")
        store.setStatus(.wantToRead, for: "ga-004")
        tick.addTimeInterval(1)
        store.recordPosition(volumeID: "ga-004", passageID: "p-1", characterOffset: -8, fraction: 7)
        try expect(store.position(for: "ga-004")?.characterOffset == 0, "negative position clamps")
        try expect(store.position(for: "ga-004")?.fraction == 1, "progress clamps")
        try expect(store.status(for: "ga-004") == .reading, "reading starts from wish list")
        store.setStatus(.finished, for: "ga-004")
        tick.addTimeInterval(1)
        store.recordPosition(volumeID: "ga-004", passageID: "p-2", characterOffset: 42, fraction: 0.4)
        try expect(store.status(for: "ga-004") == .finished, "rereading preserves explicit finished state")
        tick.addTimeInterval(1)
        store.recordPosition(volumeID: "ga-013", passageID: "p-1", characterOffset: 7, fraction: .nan)
        try expect(store.recentVolumeIDs == ["ga-013", "ga-004"], "recent reading order")
        try expect(store.position(for: "ga-013")?.fraction == 0, "nonfinite progress safely encodes")

        let body = "Vorwort 📖 Über Erkenntnis"
        let quote = "Über Erkenntnis"
        let range = (body as NSString).range(of: quote)
        var note = PersonalAnnotation(id: "note-1", volumeID: "ga-004", passageID: "p-2", location: range.location,
            length: range.length, quote: quote, note: "Meine Notiz", color: .yellow, isBookmark: false, updatedAt: .distantPast)
        store.saveAnnotation(note)
        try expect(store.annotations(for: "ga-004", passageID: "p-2").first?.updatedAt == tick, "edits own their timestamp")
        try expect((body as NSString).substring(with: NSRange(location: note.location, length: note.length)) == quote, "UTF-16 emoji selection")
        tick.addTimeInterval(1)
        note.note = "Überarbeitet"
        note.color = .blue
        store.saveAnnotation(note)
        try expect(store.annotations(for: "ga-004").count == 1, "editing does not duplicate highlights")
        let bookmark = PersonalAnnotation(id: "bookmark-1", volumeID: "ga-004", passageID: "p-1", location: -2,
            length: -1, quote: "", note: "", color: .green, isBookmark: true, updatedAt: tick)
        store.saveAnnotation(bookmark)
        try expect(store.annotations(for: "ga-004", passageID: "p-1").first?.location == 0, "bookmark range clamps")
        try expect(store.annotations(for: "ga-013").isEmpty, "notes stay scoped to their work")
        let collection = store.createCollection(name: "  Erkenntnis  ")!
        try expect(store.createCollection(name: "erkenntnis")?.id == collection.id, "collection names deduplicate")
        try expect(store.createCollection(name: " \n ") == nil, "blank collections rejected")
        store.setMembership(volumeID: "ga-013", collectionID: collection.id, included: true)
        store.setMembership(volumeID: "ga-004", collectionID: collection.id, included: true)
        store.setMembership(volumeID: "ga-004", collectionID: collection.id, included: true)
        try expect(store.collections.first?.volumeIDs == ["ga-004", "ga-013"], "membership is unique and stable")
        store.setMembership(volumeID: "ga-013", collectionID: collection.id, included: false)
        store.flush()
        let restored = ReadingStore(fileURL: file)
        try expect(restored.position(for: "ga-004")?.characterOffset == 42, "exact position survives relaunch")
        try expect(restored.status(for: "ga-004") == .finished, "status survives relaunch")
        try expect(restored.annotations(for: "ga-004").contains { $0.note == "Überarbeitet" && $0.color == .blue }, "note edits survive relaunch")
        try expect(restored.collections.first?.volumeIDs == ["ga-004"], "membership removal survives relaunch")
        restored.removeAnnotation(id: "note-1")
        restored.deleteCollection(id: collection.id)
        restored.setStatus(.unread, for: "ga-004")
        let deleted = ReadingStore(fileURL: file)
        try expect(deleted.annotations(for: "ga-004").count == 1 && deleted.collections.isEmpty, "deletions persist")
        try expect(deleted.status(for: "ga-004") == .unread, "explicit unread persists")
        let savedDeletionState = try JSONDecoder().decode(ReadingState.self, from: Data(contentsOf: file))
        try expect(savedDeletionState.deletedAnnotations["note-1"]! > tick, "deletion remains newer after a device clock rolls back")
        deleted.saveAnnotation(note)
        let savedRestoreState = try JSONDecoder().decode(ReadingState.self, from: Data(contentsOf: file))
        try expect(savedRestoreState.annotations["note-1"]!.updatedAt > savedDeletionState.deletedAnnotations["note-1"]!,
            "explicit restoration survives other-device deletion tombstones")

        let throttleFile = root.appendingPathComponent("throttle/state.json")
        let throttle = ReadingStore(fileURL: throttleFile)
        throttle.recordPosition(volumeID: "ga-001", passageID: "p-1", characterOffset: 1, fraction: 0.1)
        try await Task.sleep(for: .milliseconds(800))
        throttle.recordPosition(volumeID: "ga-001", passageID: "p-1", characterOffset: 2, fraction: 0.2)
        try await Task.sleep(for: .milliseconds(500))
        try expect(ReadingStore(fileURL: throttleFile).position(for: "ga-001")?.characterOffset == 2,
            "continuous reading flushes latest position without resetting deadline")

        let corruptFile = root.appendingPathComponent("corrupt.json")
        let corrupt = Data("{broken JSON".utf8)
        try corrupt.write(to: corruptFile)
        let recovered = ReadingStore(fileURL: corruptFile)
        try expect(recovered.lastError != nil, "malformed-state error visible")
        recovered.setStatus(.wantToRead, for: "ga-009")
        let copies = try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)
            .filter { $0.lastPathComponent.hasPrefix("corrupt.unreadable-") }
        try expect(copies.count == 1 && (try Data(contentsOf: copies[0])) == corrupt, "malformed original preserved byte-for-byte")
        let futureFile = root.appendingPathComponent("future.json")
        let future = Data("{\"schemaVersion\":99}".utf8)
        try future.write(to: futureFile)
        let futureStore = ReadingStore(fileURL: futureFile)
        futureStore.setStatus(.reading, for: "ga-001")
        futureStore.flush()
        try expect(futureStore.lastError != nil && (try Data(contentsOf: futureFile)) == future, "future schema never overwritten")
        let sparseFile = root.appendingPathComponent("sparse.json")
        try Data("{\"schemaVersion\":1}".utf8).write(to: sparseFile)
        try expect(ReadingStore(fileURL: sparseFile).lastError == nil, "missing optional state fields accepted")
        let blockedDirectory = root.appendingPathComponent("blocked")
        try Data().write(to: blockedDirectory)
        let blocked = ReadingStore(fileURL: blockedDirectory.appendingPathComponent("state.json"))
        blocked.setStatus(.reading, for: "ga-001")
        try expect(blocked.lastError != nil, "write errors visible")
        let unsigned = ReadingStore(fileURL: root.appendingPathComponent("unsigned.json"), cloudContainerIdentifier: "iCloud.com.example.unentitled")
        await unsigned.start()
        try expect(!unsigned.isSyncing && unsigned.lastError == nil, "unentitled CloudKit safely remains local")

        try checkMerge()
        try checkAnnotationStyles(in: root)
        try checkSignedEntitlementParser()
        print("ReadingStore checks passed: persistence, resume, notes, legacy annotations, purple underlines, collections, recovery, throttling, private sync merges, entitlement safety.")
    }

    static func expect(_ condition: Bool, _ message: String) throws {
        if !condition { throw NSError(domain: "ReadingStoreChecks", code: 1, userInfo: [NSLocalizedDescriptionKey: message]) }
    }

    @MainActor
    static func checkAnnotationStyles(in root: URL) throws {
        // This is the pre-style wire format, shared by older local and iCloud snapshots.
        let legacyJSON = Data(#"{"id":"legacy-note","volumeID":"ga-009","passageID":"p-3","location":7,"length":12,"quote":"Erkenntnis","note":"Ältere Notiz","color":"pink","isBookmark":false,"updatedAt":17}"#.utf8)
        let decoder = JSONDecoder()
        let legacy = try decoder.decode(PersonalAnnotation.self, from: legacyJSON)
        try expect(legacy.style == .highlight && legacy.color == .pink && legacy.note == "Ältere Notiz",
            "legacy annotation defaults to highlight without losing its note or color")
        let defaulted = PersonalAnnotation(id: "old-call", volumeID: "ga-009", passageID: "p-3", location: 0,
            length: 1, quote: "E", note: "", color: .yellow, isBookmark: false, updatedAt: .now)
        try expect(defaulted.style == .highlight, "existing initializer calls remain highlights")

        var legacyState = ReadingState()
        legacyState.positions["ga-009"] = ReadingPosition(volumeID: "ga-009", passageID: "p-3", characterOffset: 123,
            fraction: 0.35, updatedAt: Date(timeIntervalSince1970: 1_700_000_000))
        legacyState.annotations[legacy.id] = legacy
        let encoder = JSONEncoder()
        var snapshot = try JSONSerialization.jsonObject(with: encoder.encode(legacyState)) as! [String: Any]
        var annotations = snapshot["annotations"] as! [String: [String: Any]]
        annotations[legacy.id]?.removeValue(forKey: "style")
        snapshot["annotations"] = annotations
        let directory = root.appendingPathComponent("legacy")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let file = directory.appendingPathComponent("state.json")
        try JSONSerialization.data(withJSONObject: snapshot).write(to: file)
        let store = ReadingStore(fileURL: file)
        try expect(store.lastError == nil && store.position(for: "ga-009")?.characterOffset == 123,
            "legacy annotation migration keeps the existing reading position")
        var edited = store.annotations(for: "ga-009").first!
        edited.color = .purple
        edited.style = .underline
        store.saveAnnotation(edited)
        let restored = ReadingStore(fileURL: file)
        let underline = restored.annotations(for: "ga-009").first!
        try expect(underline.id == legacy.id && underline.note == legacy.note && underline.quote == legacy.quote,
            "style/color edits preserve annotation identity, note and quote")
        try expect(underline.style == .underline && underline.color == .purple,
            "purple underline survives a reading-library roundtrip")
        var noteEdit = underline
        noteEdit.note = "Überarbeitete ältere Notiz"
        restored.saveAnnotation(noteEdit)
        let afterNoteEdit = ReadingStore(fileURL: file).annotations(for: "ga-009").first!
        try expect(afterNoteEdit.id == legacy.id && afterNoteEdit.note == noteEdit.note
            && afterNoteEdit.style == .underline && afterNoteEdit.color == .purple,
            "editing a note preserves existing underline style and color")
        let encoded = try encoder.encode(afterNoteEdit)
        let roundtrip = try decoder.decode(PersonalAnnotation.self, from: encoded)
        try expect(roundtrip == afterNoteEdit, "annotation Codable preserves every property")
    }

    static func checkMerge() throws {
        let first = Date(timeIntervalSince1970: 10)
        let later = Date(timeIntervalSince1970: 20)
        let latest = Date(timeIntervalSince1970: 30)
        var old = ReadingState()
        old.positions["ga-004"] = ReadingPosition(volumeID: "ga-004", passageID: "p-1", characterOffset: 10, fraction: 0.2, updatedAt: first)
        old.annotations["note"] = PersonalAnnotation(id: "note", volumeID: "ga-004", passageID: "p-1", location: 2,
            length: 3, quote: "alt", note: "", color: .yellow, isBookmark: false, updatedAt: first)
        old.collections["shelf"] = ReadingCollection(id: "shelf", name: "Sammlung", volumeIDs: ["ga-004"], updatedAt: first)
        old.memberships["shelf"] = ["ga-004": DatedMembership(included: true, updatedAt: first)]
        var fresh = ReadingState()
        fresh.positions["ga-004"] = ReadingPosition(volumeID: "ga-004", passageID: "p-2", characterOffset: 50, fraction: 0.5, updatedAt: later)
        fresh.deletedAnnotations["note"] = later
        fresh.collections["shelf"] = ReadingCollection(id: "shelf", name: "Sammlung", volumeIDs: ["ga-013"], updatedAt: later)
        fresh.memberships["shelf"] = ["ga-013": DatedMembership(included: true, updatedAt: later)]
        var merged = old
        merged.merge(fresh)
        try expect(merged.positions["ga-004"]?.characterOffset == 50, "newer resume position wins")
        try expect(merged.annotations["note"] == nil, "deletion defeats stale highlight")
        try expect(merged.collections["shelf"]?.volumeIDs == ["ga-004", "ga-013"], "simultaneous shelf additions both survive")
        var reverse = fresh
        reverse.merge(old)
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        try expect(try encoder.encode(merged) == encoder.encode(reverse), "merge is commutative")
        fresh.memberships["shelf"]?["ga-004"] = DatedMembership(included: false, updatedAt: latest)
        merged.merge(fresh)
        try expect(merged.collections["shelf"]?.volumeIDs == ["ga-013"], "membership deletion beats stale addition")
        var resurrected = old
        resurrected.annotations["note"]?.updatedAt = latest
        resurrected.annotations["note"]?.style = .underline
        resurrected.annotations["note"]?.color = .purple
        merged.merge(resurrected)
        try expect(merged.annotations["note"]?.style == .underline && merged.annotations["note"]?.color == .purple,
            "explicit newer edit can restore a deleted annotation with its underline style and color")
        var deletion = ReadingState()
        deletion.deletedCollections["shelf"] = latest
        merged.merge(deletion)
        try expect(merged.collections["shelf"] == nil, "collection tombstone defeats other-device state")
        var tieA = ReadingState()
        var tieB = ReadingState()
        tieA.statuses["ga-004"] = DatedStatus(status: .finished, updatedAt: latest)
        tieB.statuses["ga-004"] = DatedStatus(status: .wantToRead, updatedAt: latest)
        let copyA = tieA
        tieA.merge(tieB)
        tieB.merge(copyA)
        try expect(try encoder.encode(tieA) == encoder.encode(tieB), "equal timestamps have deterministic conflict resolution")
    }

    static func checkSignedEntitlementParser() throws {
        let entitlements: [String: Any] = ["com.apple.developer.icloud-container-identifiers": ["iCloud.com.example.ga"],
            "com.apple.developer.icloud-services": ["CloudKit"]]
        let plist = try PropertyListSerialization.data(fromPropertyList: entitlements, format: .xml, options: 0)
        func word(_ value: UInt32, big: Bool = false) -> Data {
            Data((0..<4).map { UInt8(truncatingIfNeeded: value >> ((big ? 3 - $0 : $0) * 8)) })
        }
        var blob = word(0xfade7171, big: true) + word(UInt32(8 + plist.count), big: true) + plist
        blob = word(0xfade0cc0, big: true) + word(UInt32(20 + blob.count), big: true)
            + word(1, big: true) + word(5, big: true) + word(20, big: true) + blob
        let header = word(0xfeedfacf) + word(0x0100000c) + word(0) + word(2) + word(1) + word(16) + word(0) + word(0)
        let executable = header + word(0x1d) + word(16) + word(48) + word(UInt32(blob.count)) + blob
        let decoded = SignedExecutableEntitlements.load(from: executable)
        try expect(decoded?["com.apple.developer.icloud-services"] as? [String] == ["CloudKit"], "signed entitlement blob decoded")
        let signatureFixture = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[2]))
        try expect(SignedExecutableEntitlements.load(from: signatureFixture)?["com.example.ga.reading-check"] as? String == "signed-parser",
            "actual codesign-generated executable entitlements decoded")
        for count in 0..<executable.count {
            try expect(SignedExecutableEntitlements.load(from: Data(executable.prefix(count))) == nil, "truncated signature rejected safely")
        }
        try expect(SignedExecutableEntitlements.load(from: Data(repeating: 255, count: 100)) == nil, "unknown executable rejected safely")
    }
}
'''


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ga-reading-check-") as directory:
        directory = Path(directory)
        source = directory / "ReadingStoreChecks.swift"
        source.write_text((ROOT / "apple/GA/ReadingStore.swift").read_text() + HARNESS)
        executable = directory / "checks"
        subprocess.run(
            ["swiftc", "-swift-version", "6", "-parse-as-library", str(source), "-o", str(executable)],
            check=True,
        )
        entitlement_file = directory / "harness.entitlements"
        entitlement_file.write_bytes(plistlib.dumps({
            "com.example.ga.reading-check": "signed-parser",
        }))
        signature_fixture = directory / "signature-fixture"
        shutil.copy2(executable, signature_fixture)
        subprocess.run(
            ["codesign", "--force", "--sign", "-", "--entitlements", str(entitlement_file), str(signature_fixture)],
            check=True,
            capture_output=True,
        )
        state_directory = directory / "state"
        state_directory.mkdir()
        subprocess.run([str(executable), str(state_directory), str(signature_fixture)], check=True)


if __name__ == "__main__":
    main()
