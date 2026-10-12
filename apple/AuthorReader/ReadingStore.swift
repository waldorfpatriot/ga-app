import Foundation
import Observation
import CloudKit
#if os(macOS)
import Security
#endif

struct ReadingPosition: Codable, Hashable, Sendable {
    var volumeID: String
    var passageID: String
    /// UTF-16 offset, matching NSRange and the platform text-selection APIs.
    var characterOffset: Int
    /// Fraction of the complete work, rather than just the current passage.
    var fraction: Double
    var updatedAt: Date
}

enum ReadingStatus: String, CaseIterable, Codable, Hashable, Sendable {
    case unread, reading, wantToRead, finished

    var displayName: String {
        switch self {
        case .unread: "Ungelesen"
        case .reading: "Wird gelesen"
        case .wantToRead: "Möchte ich lesen"
        case .finished: "Gelesen"
        }
    }
}

enum HighlightColor: String, Codable, CaseIterable, Hashable, Sendable {
    case yellow, green, blue, pink, purple

    var displayName: String {
        switch self {
        case .yellow: "Gelb"
        case .green: "Grün"
        case .blue: "Blau"
        case .pink: "Rosa"
        case .purple: "Violett"
        }
    }
}

enum AnnotationStyle: String, Codable, CaseIterable, Hashable, Sendable {
    case highlight, underline

    var displayName: String {
        switch self {
        case .highlight: "Markierung"
        case .underline: "Unterstreichung"
        }
    }
}

struct PersonalAnnotation: Codable, Hashable, Identifiable, Sendable {
    var id: String
    var volumeID: String
    var passageID: String
    /// UTF-16 range into the passage, matching NSRange.
    var location: Int
    var length: Int
    var quote: String
    var note: String
    var color: HighlightColor
    var style: AnnotationStyle = .highlight
    var isBookmark: Bool
    var updatedAt: Date

    init(
        id: String,
        volumeID: String,
        passageID: String,
        location: Int,
        length: Int,
        quote: String,
        note: String,
        color: HighlightColor,
        style: AnnotationStyle = .highlight,
        isBookmark: Bool,
        updatedAt: Date
    ) {
        self.id = id
        self.volumeID = volumeID
        self.passageID = passageID
        self.location = location
        self.length = length
        self.quote = quote
        self.note = note
        self.color = color
        self.style = style
        self.isBookmark = isBookmark
        self.updatedAt = updatedAt
    }

    private enum CodingKeys: String, CodingKey {
        case id, volumeID, passageID, location, length, quote, note, color, style, isBookmark, updatedAt
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decode(String.self, forKey: .id)
        volumeID = try values.decode(String.self, forKey: .volumeID)
        passageID = try values.decode(String.self, forKey: .passageID)
        location = try values.decode(Int.self, forKey: .location)
        length = try values.decode(Int.self, forKey: .length)
        quote = try values.decode(String.self, forKey: .quote)
        note = try values.decode(String.self, forKey: .note)
        color = try values.decode(HighlightColor.self, forKey: .color)
        // Older local and private iCloud snapshots contain highlights without a style key.
        style = try values.decodeIfPresent(AnnotationStyle.self, forKey: .style) ?? .highlight
        isBookmark = try values.decode(Bool.self, forKey: .isBookmark)
        updatedAt = try values.decode(Date.self, forKey: .updatedAt)
    }
}

struct ReadingCollection: Codable, Hashable, Identifiable, Sendable {
    var id: String
    var name: String
    var volumeIDs: [String]
    var updatedAt: Date
}

/// Personal data is always stored locally and is never sent to the catalog server.
///
/// Lifecycle: call `await start()` once, `await sync()` when the scene becomes active,
/// and `flush()` when it becomes inactive/backgrounded. Local edits work without iCloud.
/// Progress writes are coalesced to one per second; explicit edits persist immediately.
///
/// Optional iCloud configuration (both targets must use the SAME container):
/// - Enable the iCloud/CloudKit capability and a provisioned container in Xcode.
/// - Add `GACloudKitContainerIdentifier` to Info.plist, or pass the identifier to init.
/// - Deploy record type `GAReadingState` with fields `payload` (Asset) and
///   `schemaVersion` (Int64) to the production CloudKit schema before distribution.
/// - The app uses one record, `personal-reading-state-v1`, in the PRIVATE database.
///   It merges each position, status, annotation, and collection by its edit timestamp;
///   deletion tombstones prevent another device from resurrecting deleted items.
///   Conflicting CloudKit saves are refetched and merged, never blindly overwritten.
///
/// CloudKit is constructed only after checking the signed entitlement. Unsigned builds,
/// unprovisioned builds retain full local functionality. A changed iCloud
/// account pauses sync so previous-account notes cannot be uploaded to another account.
@MainActor
@Observable
final class ReadingStore {
    private(set) var lastError: String?
    private(set) var syncStatus = "Auf diesem Gerät gespeichert"
    private(set) var isSyncing = false

    var collections: [ReadingCollection] {
        state.collections.values.sorted {
            $0.name.localizedStandardCompare($1.name) == .orderedAscending
        }
    }

    var recentVolumeIDs: [String] {
        state.positions.values.sorted {
            $0.updatedAt == $1.updatedAt ? $0.volumeID < $1.volumeID : $0.updatedAt > $1.updatedAt
        }.map(\.volumeID)
    }

    @ObservationIgnored private let fileURL: URL
    @ObservationIgnored private let cloudContainerIdentifier: String?
    @ObservationIgnored private let now: () -> Date
    @ObservationIgnored private var writeTask: Task<Void, Never>?
    @ObservationIgnored private var syncTask: Task<Void, Never>?
    @ObservationIgnored private var localRevision = 0
    @ObservationIgnored private var canPersist = true
    @ObservationIgnored private var hasStarted = false
    @ObservationIgnored private var syncAgain = false
    @ObservationIgnored private var persistenceError: String?
    private var state = ReadingState()

    init(fileURL: URL? = nil, cloudContainerIdentifier: String? = nil, now: @escaping () -> Date = Date.init) {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("Library/Application Support")
        self.fileURL = fileURL ?? support.appendingPathComponent(AppEdition.storageDirectory)
            .appendingPathComponent("Reading/reading-state.json")
        self.cloudContainerIdentifier = cloudContainerIdentifier
            ?? AppEdition.cloudContainerIdentifier
        self.now = now
        load()
    }

    func start() async {
        guard !hasStarted else { return }
        hasStarted = true
        await sync()
    }

    func position(for volumeID: String) -> ReadingPosition? {
        state.positions[volumeID]
    }

    func recordPosition(volumeID: String, passageID: String, characterOffset: Int, fraction: Double) {
        guard !volumeID.isEmpty, !passageID.isEmpty else { return }
        let offset = max(0, characterOffset)
        let boundedFraction = fraction.isFinite ? min(1, max(0, fraction)) : 0
        if let previous = state.positions[volumeID], previous.passageID == passageID,
           previous.characterOffset == offset, previous.fraction == boundedFraction { return }
        let timestamp = editTime(after: state.positions[volumeID]?.updatedAt)
        state.positions[volumeID] = ReadingPosition(
            volumeID: volumeID, passageID: passageID, characterOffset: offset,
            fraction: boundedFraction, updatedAt: timestamp
        )
        if status(for: volumeID) != .finished && status(for: volumeID) != .reading {
            state.statuses[volumeID] = DatedStatus(status: .reading, updatedAt: editTime(after: state.statuses[volumeID]?.updatedAt))
        }
        didChange(coalesce: true)
    }

    func status(for volumeID: String) -> ReadingStatus {
        state.statuses[volumeID]?.status ?? .unread
    }

    func setStatus(_ status: ReadingStatus, for volumeID: String) {
        guard !volumeID.isEmpty, self.status(for: volumeID) != status else { return }
        state.statuses[volumeID] = DatedStatus(status: status, updatedAt: editTime(after: state.statuses[volumeID]?.updatedAt))
        didChange()
    }

    func annotations(for volumeID: String, passageID: String? = nil) -> [PersonalAnnotation] {
        state.annotations.values.filter {
            $0.volumeID == volumeID && (passageID == nil || $0.passageID == passageID)
        }.sorted {
            if $0.passageID != $1.passageID { return $0.passageID.localizedStandardCompare($1.passageID) == .orderedAscending }
            if $0.location != $1.location { return $0.location < $1.location }
            return $0.updatedAt < $1.updatedAt
        }
    }

    func saveAnnotation(_ annotation: PersonalAnnotation) {
        guard !annotation.id.isEmpty, !annotation.volumeID.isEmpty, !annotation.passageID.isEmpty else { return }
        var annotation = annotation
        annotation.location = max(0, annotation.location)
        annotation.length = max(0, annotation.length)
        // Store owns edit time so a caller editing an old value still wins a sync merge.
        annotation.updatedAt = editTime(after: [state.annotations[annotation.id]?.updatedAt, state.deletedAnnotations[annotation.id]].compactMap { $0 }.max())
        state.annotations[annotation.id] = annotation
        state.deletedAnnotations.removeValue(forKey: annotation.id)
        didChange()
    }

    func removeAnnotation(id: String) {
        guard let annotation = state.annotations.removeValue(forKey: id) else { return }
        state.deletedAnnotations[id] = editTime(after: annotation.updatedAt)
        didChange()
    }

    @discardableResult
    func createCollection(name: String) -> ReadingCollection? {
        let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return nil }
        if let existing = collections.first(where: { $0.name.caseInsensitiveCompare(name) == .orderedSame }) {
            return existing
        }
        let collection = ReadingCollection(id: UUID().uuidString, name: name, volumeIDs: [], updatedAt: now())
        state.collections[collection.id] = collection
        didChange()
        return collection
    }

    func deleteCollection(id: String) {
        guard let collection = state.collections.removeValue(forKey: id) else { return }
        state.deletedCollections[id] = editTime(after: collection.updatedAt)
        didChange()
    }

    func setMembership(volumeID: String, collectionID: String, included: Bool) {
        guard !volumeID.isEmpty, var collection = state.collections[collectionID],
              collection.volumeIDs.contains(volumeID) != included else { return }
        if included { collection.volumeIDs.append(volumeID) }
        else { collection.volumeIDs.removeAll { $0 == volumeID } }
        collection.volumeIDs.sort()
        collection.updatedAt = editTime(after: collection.updatedAt)
        state.collections[collectionID] = collection
        state.memberships[collectionID, default: [:]][volumeID] = DatedMembership(
            included: included, updatedAt: collection.updatedAt
        )
        didChange()
    }

    /// Flush before the app is suspended or a reader closes. Does not need network access.
    func flush() {
        writeTask?.cancel()
        writeTask = nil
        persist()
    }

    /// Foreground/manual sync. Errors never discard the device's local reading state.
    func sync() async {
        guard canPersist else { return }
        guard let identifier = cloudContainerIdentifier, !identifier.isEmpty,
              CloudEntitlements.permits(containerIdentifier: identifier) else {
            syncStatus = "Auf diesem Gerät gespeichert"
            return
        }
        if isSyncing { syncAgain = true; return }
        syncTask?.cancel()
        syncTask = nil
        isSyncing = true
        syncStatus = "iCloud wird synchronisiert …"
        defer {
            isSyncing = false
            if syncAgain {
                syncAgain = false
                scheduleSync()
            }
        }

        let container = CKContainer(identifier: identifier)
        do {
            guard try await container.accountStatus() == .available else {
                syncStatus = "Auf diesem Gerät gespeichert · iCloud nicht verfügbar"
                return
            }
            let accountID = try await container.userRecordID().recordName
            if let previousAccount = state.cloudAccountID, previousAccount != accountID {
                syncStatus = "Auf diesem Gerät gespeichert · iCloud-Account geändert"
                lastError = "Die iCloud-Synchronisierung ist pausiert, weil sich der angemeldete Account geändert hat. Deine Lesedaten bleiben auf diesem Gerät."
                return
            }
            state.cloudAccountID = accountID
            flush()
            let database = container.privateCloudDatabase
            let recordID = CKRecord.ID(recordName: "personal-reading-state-v1")
            for attempt in 0..<3 {
                let record: CKRecord
                let isNew: Bool
                do { record = try await database.record(for: recordID); isNew = false }
                catch let error as CKError where error.code == .unknownItem {
                    record = CKRecord(recordType: "GAReadingState", recordID: recordID)
                    isNew = true
                }

                var remoteData: Data?
                if let version = record["schemaVersion"] as? NSNumber, version.intValue != ReadingState.currentSchema {
                    throw ReadingStoreError.unsupportedSchema
                }
                if let asset = record["payload"] as? CKAsset, let url = asset.fileURL {
                    let data = try Data(contentsOf: url)
                    let remote = try Self.decode(data)
                    guard remote.cloudAccountID == nil || remote.cloudAccountID == accountID else {
                        throw ReadingStoreError.wrongAccount
                    }
                    state.merge(remote)
                    localRevision += 1
                    flush()
                    remoteData = try Self.encode(remote)
                } else if !isNew {
                    throw ReadingStoreError.invalidCloudPayload
                }
                let data = try Self.encode(state)
                let revision = localRevision
                // Fetching a matching state needs no write, and works with read-only schema errors.
                if remoteData == data {
                    syncStatus = "Mit iCloud synchronisiert"
                    lastError = persistenceError
                    return
                }
                let assetURL = FileManager.default.temporaryDirectory.appendingPathComponent("ga-reading-\(UUID().uuidString).json")
                try data.write(to: assetURL, options: .atomic)
                defer { try? FileManager.default.removeItem(at: assetURL) }
                record["payload"] = CKAsset(fileURL: assetURL)
                record["schemaVersion"] = NSNumber(value: ReadingState.currentSchema)
                do {
                    // CKDatabase.save uses the fetched record's change tag to detect conflicts.
                    _ = try await database.save(record)
                    lastError = persistenceError
                    syncStatus = "Mit iCloud synchronisiert"
                    if revision != localRevision { syncAgain = true }
                    return
                } catch let error as CKError where error.code == .serverRecordChanged && attempt < 2 {
                    continue
                }
            }
        } catch {
            syncStatus = "Auf diesem Gerät gespeichert · iCloud-Synchronisierung ausstehend"
            lastError = "Die iCloud-Synchronisierung konnte nicht abgeschlossen werden: \(error.localizedDescription)"
        }
    }

    private func didChange(coalesce: Bool = false) {
        localRevision += 1
        if coalesce {
            // Do not reset the deadline on each scroll event: continuous reading is saved too.
            if writeTask == nil {
                writeTask = Task { [weak self] in
                    do { try await Task.sleep(for: .seconds(1)) } catch { return }
                    guard let self else { return }
                    self.writeTask = nil
                    self.persist()
                }
            }
        } else { flush() }
        if cloudContainerIdentifier != nil { scheduleSync() }
    }

    /// Editing a restored/future-dated value must still win if a device clock went back.
    private func editTime(after previous: Date?) -> Date {
        let timestamp = now()
        guard let previous, timestamp <= previous else { return timestamp }
        return previous.addingTimeInterval(0.001)
    }

    private func scheduleSync() {
        guard syncTask == nil else { return }
        syncTask = Task { [weak self] in
            do { try await Task.sleep(for: .seconds(15)) } catch { return }
            guard let self else { return }
            self.syncTask = nil
            await self.sync()
        }
    }

    private func load() {
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return }
        do {
            state = try Self.decode(Data(contentsOf: fileURL))
        } catch ReadingStoreError.unsupportedSchema {
            canPersist = false
            lastError = "Diese Lesebibliothek wurde mit einer neueren App-Version gespeichert. Aktualisiere die App, um sie zu verwenden. Die gespeicherte Datei bleibt erhalten."
        } catch {
            // Preserve evidence and recovery options before creating a fresh state.
            let recoveryURL = fileURL.deletingPathExtension().appendingPathExtension("unreadable-\(UUID().uuidString).json")
            do {
                try FileManager.default.moveItem(at: fileURL, to: recoveryURL)
                lastError = "Die gespeicherte Lesebibliothek konnte nicht gelesen werden. Eine Wiederherstellungskopie wurde unter \(recoveryURL.lastPathComponent) gesichert."
            } catch {
                canPersist = false
                lastError = "Die gespeicherte Lesebibliothek konnte nicht gelesen werden. Die ursprüngliche Datei bleibt erhalten."
            }
        }
    }

    private func persist() {
        guard canPersist else { return }
        do {
            let directory = fileURL.deletingLastPathComponent()
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let data = try Self.encode(state)
            #if os(iOS)
            try data.write(to: fileURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
            #else
            try data.write(to: fileURL, options: .atomic)
            #endif
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: fileURL.path)
            if lastError == persistenceError { lastError = nil }
            persistenceError = nil
        } catch {
            let message = "Deine letzten Leseänderungen konnten nicht gespeichert werden: \(error.localizedDescription)"
            persistenceError = message
            lastError = message
        }
    }

    private static func encode(_ state: ReadingState) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return try encoder.encode(state)
    }

    private static func decode(_ data: Data) throws -> ReadingState {
        let state = try JSONDecoder().decode(ReadingState.self, from: data)
        guard state.schemaVersion == ReadingState.currentSchema else { throw ReadingStoreError.unsupportedSchema }
        return state.validated()
    }
}

private struct DatedStatus: Codable, Sendable {
    var status: ReadingStatus
    var updatedAt: Date
}

private struct DatedMembership: Codable, Sendable {
    var included: Bool
    var updatedAt: Date
}

private struct ReadingState: Codable, Sendable {
    static let currentSchema = 1
    var schemaVersion = currentSchema
    var positions: [String: ReadingPosition] = [:]
    var statuses: [String: DatedStatus] = [:]
    var annotations: [String: PersonalAnnotation] = [:]
    var collections: [String: ReadingCollection] = [:]
    /// Membership has its own edit time so simultaneous additions on two devices survive.
    var memberships: [String: [String: DatedMembership]] = [:]
    var deletedAnnotations: [String: Date] = [:]
    var deletedCollections: [String: Date] = [:]
    var cloudAccountID: String?

    init() {}

    private enum CodingKeys: String, CodingKey {
        case schemaVersion, positions, statuses, annotations, collections, memberships
        case deletedAnnotations, deletedCollections, cloudAccountID
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try values.decode(Int.self, forKey: .schemaVersion)
        positions = try values.decodeIfPresent([String: ReadingPosition].self, forKey: .positions) ?? [:]
        statuses = try values.decodeIfPresent([String: DatedStatus].self, forKey: .statuses) ?? [:]
        annotations = try values.decodeIfPresent([String: PersonalAnnotation].self, forKey: .annotations) ?? [:]
        collections = try values.decodeIfPresent([String: ReadingCollection].self, forKey: .collections) ?? [:]
        memberships = try values.decodeIfPresent([String: [String: DatedMembership]].self, forKey: .memberships) ?? [:]
        deletedAnnotations = try values.decodeIfPresent([String: Date].self, forKey: .deletedAnnotations) ?? [:]
        deletedCollections = try values.decodeIfPresent([String: Date].self, forKey: .deletedCollections) ?? [:]
        cloudAccountID = try values.decodeIfPresent(String.self, forKey: .cloudAccountID)
    }

    func validated() -> ReadingState {
        var result = self
        result.positions = positions.filter { !$0.key.isEmpty && $0.key == $0.value.volumeID && !$0.value.passageID.isEmpty }
            .mapValues { position in
                var position = position
                position.characterOffset = max(0, position.characterOffset)
                position.fraction = position.fraction.isFinite ? min(1, max(0, position.fraction)) : 0
                return position
            }
        result.statuses = statuses.filter { !$0.key.isEmpty }
        result.annotations = annotations.filter {
            !$0.key.isEmpty && $0.key == $0.value.id && !$0.value.volumeID.isEmpty && !$0.value.passageID.isEmpty
        }.mapValues { annotation in
            var annotation = annotation
            annotation.location = max(0, annotation.location)
            annotation.length = max(0, annotation.length)
            return annotation
        }
        result.collections = collections.filter { !$0.key.isEmpty && $0.key == $0.value.id && !$0.value.name.isEmpty }
            .mapValues { collection in
                var collection = collection
                collection.volumeIDs = Array(Set(collection.volumeIDs.filter { !$0.isEmpty })).sorted()
                return collection
            }
        result.memberships = memberships.filter { !$0.key.isEmpty }.mapValues {
            $0.filter { !$0.key.isEmpty }
        }
        // A missing membership map from an earlier schema-1 client is reconstructed.
        for collection in result.collections.values {
            for volumeID in collection.volumeIDs where result.memberships[collection.id]?[volumeID] == nil {
                result.memberships[collection.id, default: [:]][volumeID] = DatedMembership(
                    included: true, updatedAt: collection.updatedAt
                )
            }
        }
        result.applyMemberships()
        result.applyDeletions()
        return result
    }

    mutating func merge(_ remote: ReadingState) {
        positions.merge(remote.positions) { newer($0, $1, at: \.updatedAt) }
        statuses.merge(remote.statuses) { newer($0, $1, at: \.updatedAt) }
        annotations.merge(remote.annotations) { newer($0, $1, at: \.updatedAt) }
        collections.merge(remote.collections) { newer($0, $1, at: \.updatedAt) }
        for (collectionID, members) in remote.memberships {
            memberships[collectionID, default: [:]].merge(members) { newer($0, $1, at: \.updatedAt) }
        }
        deletedAnnotations.merge(remote.deletedAnnotations, uniquingKeysWith: max)
        deletedCollections.merge(remote.deletedCollections, uniquingKeysWith: max)
        applyMemberships()
        applyDeletions()
    }

    private mutating func applyMemberships() {
        for (collectionID, members) in memberships where collections[collectionID] != nil {
            collections[collectionID]?.volumeIDs = members.filter { $0.value.included }.keys.sorted()
        }
    }

    private mutating func applyDeletions() {
        annotations = annotations.filter { id, value in
            deletedAnnotations[id].map { $0 < value.updatedAt } ?? true
        }
        collections = collections.filter { id, value in
            deletedCollections[id].map { $0 < value.updatedAt } ?? true
        }
    }
}

/// Deterministic ties keep merges commutative when two devices edit within a clock tick.
private func newer<Value: Codable>(_ lhs: Value, _ rhs: Value, at date: KeyPath<Value, Date>) -> Value {
    if lhs[keyPath: date] != rhs[keyPath: date] { return lhs[keyPath: date] > rhs[keyPath: date] ? lhs : rhs }
    let encoder = JSONEncoder()
    encoder.outputFormatting = .sortedKeys
    let left = (try? encoder.encode(lhs)) ?? Data()
    let right = (try? encoder.encode(rhs)) ?? Data()
    return left.lexicographicallyPrecedes(right) ? rhs : lhs
}

private enum ReadingStoreError: LocalizedError {
    case unsupportedSchema, wrongAccount, invalidCloudPayload

    var errorDescription: String? {
        switch self {
        case .unsupportedSchema: "Die iCloud-Lesebibliothek verwendet ein neueres Format. Aktualisiere die App vor der Synchronisierung."
        case .wrongAccount: "Die iCloud-Lesebibliothek gehört zu einem anderen Account."
        case .invalidCloudPayload: "Die iCloud-Lesebibliothek konnte nicht gelesen werden. Ihre ursprünglichen Daten bleiben erhalten."
        }
    }
}

private enum CloudEntitlements {
    static func permits(containerIdentifier: String) -> Bool {
        #if os(macOS)
        guard let task = SecTaskCreateFromSelf(nil),
              let containers = SecTaskCopyValueForEntitlement(task, "com.apple.developer.icloud-container-identifiers" as CFString, nil) as? [String],
              let services = SecTaskCopyValueForEntitlement(task, "com.apple.developer.icloud-services" as CFString, nil) as? [String]
        else { return false }
        return containers.contains(containerIdentifier) && services.contains("CloudKit")
        #elseif os(iOS)
        // iOS has no public SecTask entitlement API. Read the OS-validated executable's
        // code-signature entitlement blob instead of assuming a profile grants the app
        // every entitlement the profile allows. This also fails safely for unsigned builds.
        guard let entitlements = SignedExecutableEntitlements.load(),
              let containers = entitlements["com.apple.developer.icloud-container-identifiers"] as? [String],
              let services = entitlements["com.apple.developer.icloud-services"] as? [String]
        else { return false }
        return containers.contains(containerIdentifier) && services.contains("CloudKit")
        #else
        return false
        #endif
    }
}

/// Minimal bounds-checked parser for the entitlement plist in a thin Mach-O signature.
/// Unsupported executable/signature formats disable optional sync; they never block reading.
private enum SignedExecutableEntitlements {
    static func load() -> [String: Any]? {
        guard let url = Bundle.main.executableURL,
              let data = try? Data(contentsOf: url, options: .mappedIfSafe) else { return nil }
        return load(from: data)
    }

    static func load(from data: Data) -> [String: Any]? {
        // Physical iOS executables and simulator builds are thin little-endian Mach-O.
        guard let magic = word(data, at: 0), magic == 0xfeedfacf || magic == 0xfeedface,
              let commandCount = word(data, at: 16), commandCount <= 4096 else { return nil }
        var cursor = magic == 0xfeedfacf ? 32 : 28
        for _ in 0..<commandCount {
            guard let command = word(data, at: cursor), let size = word(data, at: cursor + 4),
                  size >= 8, cursor + Int(size) <= data.count else { return nil }
            if command == 0x1d { // LC_CODE_SIGNATURE
                guard size >= 16, let offset = word(data, at: cursor + 8),
                      let length = word(data, at: cursor + 12),
                      Int(offset) + Int(length) <= data.count else { return nil }
                return entitlementPlist(data, signatureOffset: Int(offset), signatureLength: Int(length))
            }
            cursor += Int(size)
        }
        return nil
    }

    private static func entitlementPlist(_ data: Data, signatureOffset: Int, signatureLength: Int) -> [String: Any]? {
        guard signatureLength >= 12, word(data, at: signatureOffset, bigEndian: true) == 0xfade0cc0,
              let length = word(data, at: signatureOffset + 4, bigEndian: true),
              Int(length) <= signatureLength,
              let count = word(data, at: signatureOffset + 8, bigEndian: true), count <= 1024,
              12 + Int(count) * 8 <= Int(length) else { return nil }
        for index in 0..<Int(count) {
            let slot = signatureOffset + 12 + index * 8
            guard let type = word(data, at: slot, bigEndian: true),
                  let relativeOffset = word(data, at: slot + 4, bigEndian: true) else { return nil }
            guard type == 5 else { continue } // CSSLOT_ENTITLEMENTS (XML)
            let blob = signatureOffset + Int(relativeOffset)
            guard Int(relativeOffset) + 8 <= Int(length),
                  word(data, at: blob, bigEndian: true) == 0xfade7171,
                  let blobLength = word(data, at: blob + 4, bigEndian: true), blobLength >= 8,
                  Int(relativeOffset) + Int(blobLength) <= Int(length) else { return nil }
            let plist = data.subdata(in: (blob + 8)..<(blob + Int(blobLength)))
            return (try? PropertyListSerialization.propertyList(from: plist, format: nil)) as? [String: Any]
        }
        return nil
    }

    private static func word(_ data: Data, at offset: Int, bigEndian: Bool = false) -> UInt32? {
        guard offset >= 0, offset <= data.count - 4 else { return nil }
        if bigEndian {
            return (0..<4).reduce(0) { ($0 << 8) | UInt32(data[offset + $1]) }
        }
        return (0..<4).reduce(0) { $0 | (UInt32(data[offset + $1]) << ($1 * 8)) }
    }
}
