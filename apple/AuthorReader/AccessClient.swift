import Foundation
import Security

enum AccessOption: String, Codable, CaseIterable, Identifiable, Sendable {
    case annual, supporter, free

    var id: String { rawValue }
    var productID: String? {
        // The native Mac and iOS apps share one App Store record and its
        // subscription group through universal purchase.
        let prefix = AppEdition.productIDPrefix
        switch self {
        case .annual: return prefix + ".annual"
        case .supporter: return prefix + ".supporter"
        case .free: return nil
        }
    }
}

struct AccessProduct: Identifiable, Sendable {
    let id: String
    let localizedPrice: String
    let subscriptionPeriod: String
    let eligibleForTrial: Bool
    let trialDescription: String?
}

struct AccessSelectionStatistic: Codable, Sendable {
    let count: Int
    let percentage: Double
}

struct AccessStatistics: Decodable, Sendable {
    let windowDays: Int
    let total: Int
    let options: [AccessOption: AccessSelectionStatistic]

    private enum CodingKeys: String, CodingKey { case windowDays = "window_days", total, options }

    init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        windowDays = try container.decode(Int.self, forKey: .windowDays)
        total = try container.decode(Int.self, forKey: .total)
        let raw = try container.decode([String: AccessSelectionStatistic].self, forKey: .options)
        options = Dictionary(uniqueKeysWithValues: raw.compactMap { name, value in
            AccessOption(rawValue: name).map { ($0, value) }
        })
        guard windowDays > 0, total >= 0, options.values.allSatisfy({
            $0.count >= 0 && $0.percentage.isFinite && (0...100).contains($0.percentage)
        }) else { throw AccessClientError.invalidResponse }
    }

    func count(for option: AccessOption) -> Int { options[option]?.count ?? 0 }
    func percentage(for option: AccessOption) -> Double { options[option]?.percentage ?? 0 }
}

/// Only a grant returned by the authenticated service is cached. Its expiry is
/// checked again whenever access is evaluated, including while offline.
struct AccessFreeGrant: Codable, Sendable {
    let status: String
    let active: Bool
    let grantKind: String?
    let startsAt: Date?
    let expiresAt: Date?
    let revenuecatAppUserID: String

    private enum CodingKeys: String, CodingKey {
        case status, active
        case grantKind = "grant_kind"
        case startsAt = "starts_at"
        case expiresAt = "expires_at"
        case revenuecatAppUserID = "revenuecat_app_user_id"
    }

    func isValid(at date: Date = Date()) -> Bool {
        guard active, let startsAt, let expiresAt else { return false }
        return startsAt <= date && date < expiresAt
    }
}

struct AccessInstallation: Codable, Sendable {
    let installationID: String
    let accessToken: String
    var recoveryCode: String?
    let revenuecatAppUserID: String

    private enum CodingKeys: String, CodingKey {
        case installationID = "installation_id"
        case accessToken = "access_token"
        case recoveryCode = "recovery_code"
        case revenuecatAppUserID = "revenuecat_app_user_id"
    }

    var shareableRecoveryCode: String? { recoveryCode.map { installationID + "." + $0 } }
}

struct AccessClient: Sendable {
    private struct FreeRequest: Encodable { let request_id: String; let message: String }
    private struct Selection: Encodable { let event_id: String; let option: AccessOption }
    private struct Recovery: Encodable { let installation_id: String; let recovery_code: String }

    let baseURL: URL

    init() {
        baseURL = AppEdition.accessBaseURL.appendingPathComponent("api/access")
    }

    var keychainService: String { AppEdition.bundleIdentifier + ".access." + baseURL.absoluteString }

    func createInstallation() async throws -> AccessInstallation {
        let data = try await request(path: "installations", method: "POST", body: Data("{}".utf8))
        let installation = try decode(AccessInstallation.self, from: data)
        guard UUID(uuidString: installation.installationID) != nil, installation.accessToken.count >= 20,
              installation.recoveryCode.map({ $0.count >= 20 }) == true else { throw AccessClientError.invalidResponse }
        return installation
    }

    func status(for installation: AccessInstallation) async throws -> AccessFreeGrant {
        let data = try await request(path: "status", token: installation.accessToken)
        return try decode(AccessFreeGrant.self, from: data)
    }

    func submitFreeRequest(message: String, requestID: String, installation: AccessInstallation) async throws -> AccessFreeGrant {
        let body = try JSONEncoder().encode(FreeRequest(request_id: requestID, message: message))
        let data = try await request(path: "free-requests", method: "POST", token: installation.accessToken, body: body)
        return try decode(AccessFreeGrant.self, from: data)
    }

    func recordSelection(_ option: AccessOption, eventID: String, installation: AccessInstallation) async throws {
        let body = try JSONEncoder().encode(Selection(event_id: eventID, option: option))
        _ = try await request(path: "selections", method: "POST", token: installation.accessToken, body: body)
    }

    func statistics() async throws -> AccessStatistics {
        try decode(AccessStatistics.self, from: await request(path: "statistics"))
    }

    func recover(_ code: String) async throws -> AccessInstallation {
        let parts = code.trimmingCharacters(in: .whitespacesAndNewlines).split(separator: ".", maxSplits: 1)
        guard parts.count == 2, UUID(uuidString: String(parts[0])) != nil, parts[1].count >= 20 else {
            throw AccessClientError.invalidRecoveryCode
        }
        let body = try JSONEncoder().encode(Recovery(installation_id: String(parts[0]), recovery_code: String(parts[1])))
        let data: Data
        do { data = try await request(path: "recover", method: "POST", body: body) }
        catch AccessClientError.httpStatus(401) { throw AccessClientError.invalidRecoveryCode }
        var installation = try decode(AccessInstallation.self, from: data)
        guard installation.installationID.caseInsensitiveCompare(String(parts[0])) == .orderedSame,
              installation.accessToken.count >= 20 else { throw AccessClientError.invalidResponse }
        installation.recoveryCode = String(parts[1])
        return installation
    }

    func deleteInstallation(_ installation: AccessInstallation) async throws {
        _ = try await request(path: "installation", method: "DELETE", token: installation.accessToken)
    }

    private func request(path: String, method: String = "GET", token: String? = nil, body: Data? = nil) async throws -> Data {
        let url = baseURL.appendingPathComponent(path)
        guard isAllowed(url) else { throw AccessClientError.insecureEndpoint }
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 20)
        request.httpMethod = method
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        if let token { request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
        // Credentials must never be forwarded through a redirect to another host.
        let session = URLSession(configuration: .ephemeral, delegate: AccessRedirectPolicy(), delegateQueue: nil)
        defer { session.finishTasksAndInvalidate() }
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw AccessClientError.invalidResponse }
        guard (200..<300).contains(response.statusCode) else { throw AccessClientError.httpStatus(response.statusCode) }
        return data
    }

    private func isAllowed(_ url: URL) -> Bool {
        if url.scheme == "https", url.host != nil, url.user == nil, url.password == nil { return true }
        #if DEBUG
        if url.scheme == "http", ["localhost", "127.0.0.1", "::1"].contains(url.host ?? "") { return true }
        #endif
        return false
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let value = try decoder.singleValueContainer().decode(String.self)
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = formatter.date(from: value) { return date }
            formatter.formatOptions = [.withInternetDateTime]
            guard let date = formatter.date(from: value) else { throw AccessClientError.invalidResponse }
            return date
        }
        return try decoder.decode(type, from: data)
    }
}

private final class AccessRedirectPolicy: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                    completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

enum AccessClientError: LocalizedError {
    case invalidResponse, insecureEndpoint, invalidRecoveryCode, keychain(OSStatus), httpStatus(Int)

    var errorDescription: String? {
        switch self {
        case .invalidResponse: "Der Server hat keine gültige Zugangsbestätigung geliefert. Bitte versuche es erneut."
        case .insecureEndpoint: "Der Zugangsdienst benötigt eine sichere Verbindung."
        case .invalidRecoveryCode: "Der Wiederherstellungscode ist ungültig. Bitte prüfe den vollständigen Code."
        case .keychain: "Der Zugang konnte auf diesem Gerät nicht sicher gespeichert werden."
        case .httpStatus(401): "Der Zugangscode ist nicht mehr gültig. Stelle deinen Zugang mit deinem Wiederherstellungscode wieder her."
        case .httpStatus(404): "Der Zugangsdienst ist derzeit nicht erreichbar. Bitte versuche es später erneut."
        case .httpStatus(413), .httpStatus(422): "Bitte sende eine nicht leere Bitte mit höchstens 5.000 Zeichen."
        case .httpStatus(429): "Zu viele Anfragen. Bitte versuche es in einer Minute erneut."
        case .httpStatus: "Der Zugangsdienst ist derzeit nicht verfügbar. Bitte versuche es später erneut."
        }
    }
}

enum AccessKeychain {
    static func load<T: Decodable>(_ type: T.Type, account: String, service: String) throws -> T? {
        var query = baseQuery(account: account, service: service)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data else { throw AccessClientError.keychain(status) }
        return try JSONDecoder().decode(type, from: data)
    }

    static func save<T: Encodable>(_ value: T, account: String, service: String) throws {
        let query = baseQuery(account: account, service: service)
        let data = try JSONEncoder().encode(value)
        let updates = [kSecValueData as String: data]
        let status = SecItemUpdate(query as CFDictionary, updates as CFDictionary)
        if status == errSecItemNotFound {
            var insertion = query
            insertion[kSecValueData as String] = data
            // Recovery survives reinstall where Keychain is retained, but does
            // not silently sync private financial requests to other devices.
            insertion[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            let added = SecItemAdd(insertion as CFDictionary, nil)
            guard added == errSecSuccess else { throw AccessClientError.keychain(added) }
        } else if status != errSecSuccess { throw AccessClientError.keychain(status) }
    }

    static func delete(account: String, service: String) throws {
        let status = SecItemDelete(baseQuery(account: account, service: service) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw AccessClientError.keychain(status) }
    }

    private static func baseQuery(account: String, service: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service,
         kSecAttrAccount as String: account,
         kSecAttrSynchronizable as String: false]
    }
}
