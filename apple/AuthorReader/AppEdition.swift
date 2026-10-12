import Foundation

/// Each app target supplies its identity through build settings. The reader,
/// subscription options and storage implementation stay shared across editions.
enum AppEdition {
    static var authorName: String { value("GAAuthorName", default: "Rudolf Steiner") }
    static var authorShortName: String { value("GAAuthorShortName", default: "Steiner") }
    static var authorSlug: String { value("GAAuthorSlug", default: "steiner") }
    static var editionTitle: String { value("GAEditionTitle", default: "Gesamtausgabe") }
    static var workPrefix: String { value("GAWorkPrefix", default: "GA") }
    static var defaultLanguage: String { value("GADefaultLanguage", default: "de") }
    static var isSteiner: Bool { authorSlug == "steiner" }
    static var bundleIdentifier: String {
        Bundle.main.bundleIdentifier ?? (isSteiner ? "com.jonathankutscher.ga" : "com.jonathankutscher." + authorSlug)
    }
    static var productIDPrefix: String {
        value("GAProductIDPrefix", default: isSteiner ? "com.jonathankutscher.ga" : bundleIdentifier)
    }
    static var entitlementIdentifier: String { value("GAEntitlementIdentifier", default: "ga_access") }
    static var cloudContainerIdentifier: String? { configuredValue("GACloudKitContainerIdentifier") }

    // Preserve the existing app's local data location while isolating other
    // authors on macOS, where apps can share an Application Support directory.
    static var storageDirectory: String { isSteiner ? "Gesamtausgabe" : bundleIdentifier }
    static var epubIdentifierNamespace: String { isSteiner ? "ga-reader" : bundleIdentifier }
    static var workNumberLabel: String { isSteiner ? "GA-Nummer" : "Werknummer" }
    static var searchPrompt: String { "Titel, \(workNumberLabel), Text oder Notiz" }

    static var readerBaseURL: URL {
        if let configured = ProcessInfo.processInfo.environment["GA_SERVER_BASE_URL"]
            ?? configuredValue("GA_SERVER_BASE_URL"), let url = URL(string: configured),
           ["http", "https"].contains(url.scheme?.lowercased() ?? ""), url.host != nil {
            return url
        }
        switch ProcessInfo.processInfo.environment["GA_FRONTEND"]?.lowercased() {
        case "developer", "dev", "overview", "status":
            return URL(string: "http://127.0.0.1:4000")!
        default:
            let path = isSteiner ? "ga-reader" : authorSlug + "-reader"
            return URL(string: "https://fototausch.eu/")!.appendingPathComponent(path)
        }
    }

    static var accessBaseURL: URL {
        if let configured = ProcessInfo.processInfo.environment["GA_ACCESS_BASE_URL"]
            ?? configuredValue("GAAccessBaseURL"), let url = URL(string: configured),
           ["http", "https"].contains(url.scheme?.lowercased() ?? ""), url.host != nil {
            return url
        }
        if isSteiner { return readerBaseURL }
        return URL(string: "https://fototausch.eu/")!.appendingPathComponent(authorSlug)
    }

    private static func value(_ key: String, default fallback: String) -> String {
        configuredValue(key) ?? fallback
    }

    private static func configuredValue(_ key: String) -> String? {
        guard let value = Bundle.main.object(forInfoDictionaryKey: key) as? String else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !trimmed.contains("$(") else { return nil }
        return trimmed
    }
}
