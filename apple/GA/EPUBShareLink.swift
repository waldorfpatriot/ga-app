import SwiftUI
import CoreTransferable
import UniformTypeIdentifiers

/// A file representation lets the native share sheet offer Books, Files,
/// AirDrop and other destinations that accept EPUB publications.
struct EPUBShareLink: View {
    @Environment(AccessStore.self) private var access
    @State private var showsAccess = false
    let volume: GAVolume
    let onFailure: @MainActor @Sendable (String) -> Void

    var body: some View {
        Group {
            if access.hasAccess {
                ShareLink(
            item: EPUBBook(volume: volume, access: access, onFailure: onFailure),
            preview: SharePreview(volume.title, image: Image(systemName: "book.closed"))
        ) {
            Label("EPUB teilen", systemImage: "square.and.arrow.up")
        }
        .accessibilityIdentifier("share-epub-\(volume.id)")
                .disabled(!volume.isReaderAvailable)
            } else {
                Button("EPUB teilen", systemImage: "square.and.arrow.up") { showsAccess = true }
                    .disabled(!volume.isReaderAvailable)
                    .accessibilityIdentifier("share-epub-\(volume.id)")
            }
        }
        .sheet(isPresented: $showsAccess) { PurchaseScreen() }
    }
}

private struct EPUBBook: Transferable, Sendable {
    let volume: GAVolume
    let access: AccessStore
    let onFailure: @MainActor @Sendable (String) -> Void

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(exportedContentType: .epub) { book in
            do {
                guard await book.access.hasAccess else { throw EPUBAccessError.expired }
                let volume = try await EPUBExportContent.prepare(volume: book.volume)
                try Task.checkCancellation()
                guard await book.access.hasAccess else { throw EPUBAccessError.expired }
                let generation = Task.detached(priority: .userInitiated) {
                    try EPUBExporter.export(volume: volume)
                }
                let file = try await withTaskCancellationHandler {
                    try await generation.value
                } onCancel: {
                    generation.cancel()
                }
                do {
                    try Task.checkCancellation()
                } catch {
                    try? FileManager.default.removeItem(at: file.deletingLastPathComponent())
                    throw error
                }
                // The receiving service can request the file after the sheet
                // closes, so keep it in the system-managed temporary directory.
                return SentTransferredFile(file)
            } catch is CancellationError {
                throw CancellationError()
            } catch {
                await book.onFailure(error.localizedDescription)
                throw error
            }
        }
    }
}

private enum EPUBAccessError: LocalizedError {
    case expired
    var errorDescription: String? { "Dein Zugang ist abgelaufen. Bitte wähle einen Beitrag, um weiterzulesen und EPUBs zu teilen." }
}
