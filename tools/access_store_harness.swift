import Foundation
import RevenueCat

@MainActor
final class ControlledBackend {
    static let shared = ControlledBackend()
    var pauseCreation = false
    var creations: [CheckedContinuation<AccessInstallation, any Error>] = []
    var pausedStatusID: String?
    var statuses: [CheckedContinuation<AccessFreeGrant, any Error>] = []
    var nextIdentity = makeIdentity()
    var recoveredIdentity = makeIdentity()
    var deleted: [String] = []
    var recoverCalls = 0
    var submitMessages: [String] = []
    var selected: [String] = []
    var reports: [TextReportRequest] = []

    static func makeIdentity() -> AccessInstallation {
        let id = UUID().uuidString
        return AccessInstallation(installationID: id, accessToken: UUID().uuidString,
                                  recoveryCode: UUID().uuidString, revenuecatAppUserID: id)
    }
    static func grant(_ identity: AccessInstallation) -> AccessFreeGrant {
        AccessFreeGrant(status: "granted", active: true, grantKind: "free",
                        startsAt: Date().addingTimeInterval(-10), expiresAt: Date().addingTimeInterval(3600),
                        revenuecatAppUserID: identity.revenuecatAppUserID)
    }
    func reset() {
        precondition(creations.isEmpty && statuses.isEmpty)
        pauseCreation = false; pausedStatusID = nil
        nextIdentity = Self.makeIdentity(); recoveredIdentity = Self.makeIdentity()
        deleted = []; recoverCalls = 0; submitMessages = []; selected = []; reports = []
        AccessKeychain.items = [:]
    }
    func create() async throws -> AccessInstallation {
        if pauseCreation { return try await withCheckedThrowingContinuation { creations.append($0) } }
        return nextIdentity
    }
    func status(_ identity: AccessInstallation) async throws -> AccessFreeGrant {
        if identity.installationID == pausedStatusID {
            return try await withCheckedThrowingContinuation { statuses.append($0) }
        }
        return Self.grant(identity)
    }
}

struct AccessClient: Sendable {
    let baseURL = URL(string: "https://isolated-unit-test.invalid/api/access")!
    var keychainService: String { "isolated-memory-test" }
    func createInstallation() async throws -> AccessInstallation { try await ControlledBackend.shared.create() }
    func status(for identity: AccessInstallation) async throws -> AccessFreeGrant { try await ControlledBackend.shared.status(identity) }
    func submitFreeRequest(message: String, requestID: String, installation: AccessInstallation) async throws -> AccessFreeGrant {
        await MainActor.run { ControlledBackend.shared.submitMessages.append(message) }
        return await ControlledBackend.grant(installation)
    }
    func recordSelection(_ option: AccessOption, eventID: String, installation: AccessInstallation) async throws {
        await MainActor.run { ControlledBackend.shared.selected.append(installation.installationID) }
    }
    func submitTextReport(_ report: TextReportRequest, installation: AccessInstallation) async throws {
        await MainActor.run { ControlledBackend.shared.reports.append(report) }
    }
    func statistics() async throws -> AccessStatistics {
        try JSONDecoder().decode(AccessStatistics.self, from: Data(#"{"window_days":90,"total":0,"options":{}}"#.utf8))
    }
    func recover(_ code: String) async throws -> AccessInstallation {
        await MainActor.run {
            ControlledBackend.shared.recoverCalls += 1
            return ControlledBackend.shared.recoveredIdentity
        }
    }
    func deleteInstallation(_ identity: AccessInstallation) async throws {
        await MainActor.run { ControlledBackend.shared.deleted.append(identity.installationID) }
    }
}

@MainActor
enum AccessKeychain {
    static var items: [String: Data] = [:]
    static func load<T: Decodable>(_ type: T.Type, account: String, service: String) throws -> T? {
        guard let data = items[account] else { return nil }
        return try JSONDecoder().decode(type, from: data)
    }
    static func save<T: Encodable>(_ value: T, account: String, service: String) throws {
        items[account] = try JSONEncoder().encode(value)
    }
    static func delete(account: String, service: String) throws { items[account] = nil }
}

@main
struct AccessStoreChecks {
    @MainActor static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        precondition(condition(), message)
    }
    @MainActor static func waitFor(_ condition: () -> Bool) async {
        for _ in 0..<10_000 {
            if condition() { return }
            await Task.yield()
        }
        preconditionFailure("Controlled operation never reached its suspension point")
    }
    @MainActor static func seededStore(_ identity: AccessInstallation) throws -> AccessStore {
        let store = AccessStore()
        store.installation = identity
        store.recoveryCode = identity.shareableRecoveryCode
        try AccessKeychain.save(identity, account: "installation", service: store.client.keychainService)
        try store.save(ControlledBackend.grant(identity), for: identity, generation: store.backendGeneration)
        return store
    }
    @MainActor static func info(subscriptionExpiry: Date, grace: Date?, active: Bool = true,
                                verification: Int = 1) throws -> CustomerInfo {
        let now = Date(timeIntervalSince1970: Date().timeIntervalSince1970.rounded(.down))
        let f = ISO8601DateFormatter()
        func timestamp(_ date: Date) -> String { f.string(from: date) }
        let product = AccessOption.annual.productID!
        var subscription: [String: Any] = ["expires_date": timestamp(subscriptionExpiry),
            "purchase_date": timestamp(now.addingTimeInterval(-86400)), "period_type": "normal",
            "store": "app_store", "is_sandbox": true, "ownership_type": "PURCHASED"]
        if let grace { subscription["grace_period_expires_date"] = timestamp(grace) }
        let entitlementEnd = active ? (grace ?? subscriptionExpiry) : now.addingTimeInterval(-7200)
        let raw: [String: Any] = ["entitlementVerification": verification,
            "request_date": timestamp(now),
            "subscriber": ["original_app_user_id": "isolated-fixture", "first_seen": timestamp(now),
                "subscriptions": [product: subscription],
                "entitlements": ["ga_access": ["expires_date": timestamp(entitlementEnd),
                    "product_identifier": product, "purchase_date": timestamp(now.addingTimeInterval(-86400))]]]]
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(CustomerInfo.self, from: JSONSerialization.data(withJSONObject: raw))
    }
    @MainActor static func main() async throws {
        expect(AccessOption.annual.productID == "com.jonathankutscher.ga.annual"
               && AccessOption.supporter.productID == "com.jonathankutscher.ga.supporter"
               && AccessOption.free.productID == nil,
               "Universal purchase must use the shared App Store product identifiers on Mac")
        let backend = ControlledBackend.shared
        let unicodeQuote = String(repeating: "🌻", count: 8_000)
        let boundaryReport = TextReportRequest(bookID: "ga-004", sectionID: "chapter", sectionTitle: nil,
            selectedText: unicodeQuote, selectionStart: 0, selectionEnd: 16_000,
            message: String(repeating: "🌻", count: 2_000))
        try boundaryReport.validate()
        let encodedReport = try JSONSerialization.jsonObject(with: JSONEncoder().encode(boundaryReport)) as! [String: Any]
        expect(encodedReport["selection_end"] as? Int == 16_000 && encodedReport["section_title"] == nil,
               "Report encoding must use UTF-16 offsets and omit missing optional fields")
        expect(encodedReport["report_id"] as? String == boundaryReport.reportID.uuidString
               && encodedReport["selected_text"] as? String == unicodeQuote,
               "Report encoding must preserve its UUID and exact Unicode quote")
        for invalid in [
            TextReportRequest(bookID: "ga-004", sectionID: "chapter", sectionTitle: nil,
                selectedText: " \n", selectionStart: nil, selectionEnd: nil),
            TextReportRequest(bookID: "ga-004", sectionID: "chapter", sectionTitle: nil,
                selectedText: unicodeQuote + "🌻", selectionStart: nil, selectionEnd: nil),
            TextReportRequest(bookID: "ga-004", sectionID: "chapter", sectionTitle: nil,
                selectedText: "🌻", selectionStart: 0, selectionEnd: 1),
            TextReportRequest(bookID: "ga-004", sectionID: "chapter", sectionTitle: nil,
                selectedText: "🌻", selectionStart: 0, selectionEnd: nil),
            boundaryReport.withMessage(String(repeating: "🌻", count: 2_001), reportID: boundaryReport.reportID)
        ] {
            do {
                try invalid.validate()
                preconditionFailure("Invalid report crossed the Unicode/UTF-16 API boundary")
            } catch is TextReportError {}
        }
        backend.reset()
        let reporting = AccessStore()
        reporting.isLoading = true
        reporting.isBusy = true
        let report = TextReportRequest(bookID: "ga-004", sectionID: "chapter", sectionTitle: "Kapitel",
            selectedText: "Grüße 🌻", selectionStart: 7, selectionEnd: 15)
        expect(!reporting.hasAccess, "Report test needs an installation without an entitlement")
        try await reporting.submitTextReport(report)
        expect(backend.reports.count == 1 && backend.reports.first?.reportID == report.reportID,
               "A report must use the anonymous installation without an access, loading or purchase gate")
        expect(backend.submitMessages.isEmpty && reporting.freeGrant == nil,
               "Reporting must not submit a financial request or grant free reading access")
        backend.reset()
        let guarded = AccessStore()
        guarded.isLoading = true
        let sentDuringRefresh = await guarded.submitFreeRequest("Bitte")
        await guarded.recoverFreeAccess("code")
        await guarded.deleteFreeAccessData()
        expect(!sentDuringRefresh && backend.submitMessages.isEmpty && backend.recoverCalls == 0 && backend.deleted.isEmpty,
               "A mutation ran while refresh was active or reported an unsent request as successful")

        backend.reset()
        backend.pauseCreation = true
        let store = AccessStore()
        let first = Task { await store.recordSelection(.free) }
        await waitFor { backend.creations.count == 1 }
        let obsolete = ControlledBackend.makeIdentity()
        await store.deleteFreeAccessData()
        let second = Task { await store.recordSelection(.annual) }
        await waitFor { backend.creations.count == 2 }
        let newTaskID = store.installationTask?.id
        backend.creations.removeFirst().resume(returning: obsolete)
        await first.value
        expect(store.installation == nil && AccessKeychain.items["installation"] == nil,
               "An obsolete creation rewrote a deleted identity")
        expect(store.installationTask?.id == newTaskID, "Old task completion cleared a newer installation task")
        expect(backend.deleted.contains(obsolete.installationID), "Obsolete server identity was not cleaned up")
        let current = ControlledBackend.makeIdentity()
        backend.creations.removeFirst().resume(returning: current)
        await second.value
        expect(store.installation?.installationID == current.installationID && backend.selected == [current.installationID],
               "Current creation or selection was lost")

        for failsWith401 in [false, true] {
            backend.reset()
            let old = ControlledBackend.makeIdentity()
            let recovered = backend.recoveredIdentity
            let recovering = try seededStore(old)
            backend.pausedStatusID = old.installationID
            let late = Task { await recovering.refreshBackend() }
            await waitFor { backend.statuses.count == 1 }
            await recovering.recoverFreeAccess(recovered.shareableRecoveryCode!)
            if failsWith401 { backend.statuses.removeFirst().resume(throwing: AccessClientError.httpStatus(401)) }
            else { backend.statuses.removeFirst().resume(returning: ControlledBackend.grant(old)) }
            await late.value
            expect(recovering.installation?.installationID == recovered.installationID && recovering.hasAccess,
                   "A stale status/error destroyed recovered access")
            expect(recovering.freeGrant?.revenuecatAppUserID == recovered.installationID && recovering.errorMessage == nil,
                   "A stale grant or 401 overwrote the current state")
        }

        backend.reset()
        let old = ControlledBackend.makeIdentity()
        let deleting = try seededStore(old)
        backend.pausedStatusID = old.installationID
        let lateDelete = Task { await deleting.refreshBackend() }
        await waitFor { backend.statuses.count == 1 }
        await deleting.deleteFreeAccessData()
        backend.statuses.removeFirst().resume(returning: ControlledBackend.grant(old))
        await lateDelete.value
        expect(!deleting.hasAccess && deleting.freeGrant == nil && AccessKeychain.items["grant"] == nil,
               "A stale status resurrected deleted access")

        backend.reset()
        let submitting = AccessStore()
        let sent = await submitting.submitFreeRequest("  Bitte QA  ")
        expect(sent && submitting.hasAccess && backend.submitMessages == ["Bitte QA"],
               "Current free submission did not save its confirmed grant or report success")

        backend.reset()
        let billing = AccessStore()
        let now = Date(timeIntervalSince1970: Date().timeIntervalSince1970.rounded(.down))
        let expired = now.addingTimeInterval(-3600)
        let grace = now.addingTimeInterval(3600)
        let graceInfo = try info(subscriptionExpiry: expired, grace: grace)
        expect(graceInfo.entitlements["ga_access"]?.isActive == true && graceInfo.entitlements["ga_access"]?.expirationDate == expired,
               "The real RevenueCat fixture does not reproduce the billing-grace distinction")
        billing.apply(graceInfo)
        expect(billing.hasAccess && billing.paidExpiration == grace, "Verified billing grace did not retain finite access")
        billing.apply(try info(subscriptionExpiry: expired, grace: grace, active: false))
        expect(!billing.hasAccess, "An inactive entitlement was resurrected by a grace date")
        billing.apply(try info(subscriptionExpiry: expired, grace: grace, verification: 2))
        expect(!billing.hasAccess, "An unverified entitlement gained access through a grace date")
        billing.apply(try info(subscriptionExpiry: expired, grace: nil))
        expect(!billing.hasAccess, "An expired entitlement without grace gained access")
        print("AccessStore checks passed: anonymous text reporting, Unicode/UTF-16 report boundaries, refresh serialization, explicit submit outcome, obsolete creation cleanup, task identity, stale status/401, deletion, real RevenueCat grace/verification fixtures.")
    }
}
