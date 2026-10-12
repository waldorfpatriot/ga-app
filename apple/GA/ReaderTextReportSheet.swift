import SwiftUI

struct ReaderTextReportSheet: View {
    let report: TextReportRequest
    let reference: String
    let onSent: () -> Void
    @Environment(AccessStore.self) private var access
    @Environment(\.dismiss) private var dismiss
    @State private var message = ""
    @State private var isSending = false
    @State private var errorMessage: String?
    @State private var pendingSubmission: TextReportRequest?

    private var normalizedMessage: String? {
        let value = message.trimmingCharacters(in: .whitespacesAndNewlines)
        return value.isEmpty ? nil : value
    }

    private var validationMessage: String? {
        do {
            try report.withMessage(normalizedMessage, reportID: report.reportID).validate()
            return nil
        } catch { return error.localizedDescription }
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Markierte Textstelle") {
                    Text(reference).font(.caption).foregroundStyle(.secondary)
                    Text(report.selectedText)
                        .font(.system(.body, design: .serif))
                        .textSelection(.enabled)
                        .accessibilityIdentifier("reader-report-quote")
                }
                Section {
                    TextEditor(text: $message)
                        .frame(minHeight: 110, idealHeight: 140)
                        .accessibilityLabel("Beschreibung des Fehlers, optional")
                        .accessibilityIdentifier("reader-report-message")
                        .disabled(isSending)
                    Text("\(message.unicodeScalars.count) / 2.000 Zeichen")
                        .font(.caption).foregroundStyle(.secondary)
                } header: {
                    Text("Beschreibung (optional)")
                } footer: {
                    Text("Gesendet werden diese Textstelle, ihre Fundstelle und deine Beschreibung. Eine E-Mail-Adresse ist nicht erforderlich.")
                }
                if let validationMessage {
                    Section { Text(validationMessage).foregroundStyle(.red) }
                }
                if let errorMessage {
                    Section {
                        Text(errorMessage).foregroundStyle(.red)
                            .accessibilityIdentifier("reader-report-error")
                    }
                }
                if isSending {
                    Section { ProgressView("Meldung wird gesendet …") }
                }
            }
            .formStyle(.grouped)
            .navigationTitle("Fehler melden")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                        .disabled(isSending)
                        .accessibilityIdentifier("reader-report-cancel")
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Senden") { Task { await send() } }
                        .disabled(isSending || validationMessage != nil)
                        .accessibilityIdentifier("reader-report-send")
                        .keyboardShortcut(.return, modifiers: .command)
                }
            }
        }
        .frame(minWidth: 300, idealWidth: 540, minHeight: 420)
        .interactiveDismissDisabled(isSending)
        #if os(iOS)
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        #endif
    }

    @MainActor private func send() async {
        guard !isSending, validationMessage == nil else { return }
        isSending = true
        errorMessage = nil
        defer { isSending = false }
        // A retry after an uncertain response reuses the exact same payload.
        // Editing the description creates a new logical report instead.
        if pendingSubmission?.message != normalizedMessage || pendingSubmission == nil {
            pendingSubmission = report.withMessage(normalizedMessage,
                reportID: pendingSubmission == nil ? report.reportID : UUID())
        }
        guard let pendingSubmission else { return }
        do {
            try await access.submitTextReport(pendingSubmission)
            onSent()
        } catch { errorMessage = TextReportError.description(for: error) }
    }
}
