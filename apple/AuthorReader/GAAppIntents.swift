#if canImport(AppIntents)
import AppIntents
import Foundation

struct GAVolumeEntity: AppEntity {
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Volume")
    static let defaultQuery = GAVolumeQuery()

    let id: String
    let gaNumber: String
    let title: String

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\(gaNumber) \(title)")
    }

    init(volume: GAVolume) {
        id = volume.id
        gaNumber = volume.gaNumber
        title = volume.title
    }
}

struct GAVolumeQuery: EntityStringQuery {
    func entities(for identifiers: [GAVolumeEntity.ID]) async throws -> [GAVolumeEntity] {
        let volumes = await currentVolumes()
        return volumes
            .filter { identifiers.contains($0.id) }
            .map(GAVolumeEntity.init(volume:))
    }

    func entities(matching string: String) async throws -> [GAVolumeEntity] {
        let volumes = await currentVolumes()
        return volumes
            .filter { $0.searchBlob.localizedCaseInsensitiveContains(string) }
            .map(GAVolumeEntity.init(volume:))
    }

    func suggestedEntities() async throws -> [GAVolumeEntity] {
        let volumes = await currentVolumes()
        return volumes.prefix(6).map(GAVolumeEntity.init(volume:))
    }

    private func currentVolumes() async -> [GAVolume] {
        do {
            return try await CatalogClient.fetchReaderCatalog()
        } catch {
            return SeedLibrary.readerVolumes
        }
    }
}

struct OpenGAVolumeIntent: AppIntent {
    static let title: LocalizedStringResource = "Open Volume"
    static let description = IntentDescription("Finds a volume in this author's independent public-domain reading edition.")

    @Parameter(title: "Volume")
    var volume: GAVolumeEntity

    @MainActor
    func perform() async throws -> some IntentResult {
        .result()
    }
}

struct GAAppShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: OpenGAVolumeIntent(),
            phrases: [
                "Open \(\.$volume) in \(.applicationName)",
                "Read \(\.$volume) in \(.applicationName)"
            ],
            shortTitle: "Open Volume",
            systemImageName: "book"
        )
    }
}
#endif
