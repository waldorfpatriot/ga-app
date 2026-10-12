import SwiftUI
import StoreKit
#if os(iOS)
import UIKit
#endif

/// One entitlement, three contributions. Statistics describe choices, never sales.
struct PurchaseScreen: View {
    @Environment(AccessStore.self) private var access
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL
    @State private var showsRequest = false
    @State private var request = ""
    @State private var recovery = ""
    @State private var showsPrivacy = false
    @State private var confirmsDeletion = false
    @State private var managementError: String?
    @FocusState private var requestFocused: Bool

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    introduction
                    accessStatus
                    statisticsHeading
                    subscription(.annual)
                    subscription(.supporter)
                    freeOption
                    if let notice = access.notice {
                        Label(notice, systemImage: "checkmark.circle")
                            .foregroundStyle(.tint).accessibilityIdentifier("access-notice")
                    }
                    if let error = access.errorMessage {
                        Text(error).foregroundStyle(.red).accessibilityIdentifier("access-error")
                    }
                    accountActions
                    legal
                }
                .padding(24)
                .frame(maxWidth: 620, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
            .accessibilityIdentifier("access-content")
            #if os(iOS)
            .scrollDismissesKeyboard(.interactively)
            #endif
            .navigationTitle("Dein App-Zugang")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Fertig") { dismiss() }.accessibilityIdentifier("close-access")
                }
                #if os(iOS)
                ToolbarItemGroup(placement: .keyboard) {
                    if requestFocused {
                        Spacer()
                        Button("Tastatur schließen") { requestFocused = false }
                            .accessibilityIdentifier("dismiss-free-keyboard")
                    }
                }
                #endif
            }
            .task { await access.refresh() }
            .sheet(isPresented: $showsPrivacy) { GAPrivacyView() }
            .confirmationDialog("Zugangsdaten löschen?", isPresented: $confirmsDeletion, titleVisibility: .visible) {
                Button("Gratiszugang und Anfragen löschen", role: .destructive) {
                    Task { await access.deleteFreeAccessData() }
                }
            } message: {
                Text("Dein Gratiszugang und deine Anfragen werden gelöscht. Ein Apple-Abo wird dadurch nicht gekündigt. Deine Bücher, Notizen und Markierungen bleiben erhalten.")
            }
            .alert("Aboverwaltung", isPresented: Binding(get: { managementError != nil }, set: { if !$0 { managementError = nil } })) {
                Button("OK") { managementError = nil }
            } message: { Text(managementError ?? "") }
        }
        #if os(macOS)
        .frame(minWidth: 480, idealWidth: 620, minHeight: 600, idealHeight: 860)
        #endif
    }

    private var introduction: some View {
        VStack(alignment: .leading, spacing: 12) {
            Image(systemName: "books.vertical").font(.largeTitle).foregroundStyle(.tint)
                .accessibilityHidden(true)
            Text("Ein Beitrag.\nGemeinsam getragen.")
                .font(.largeTitle.weight(.semibold)).fontDesign(.serif)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            Text("Alle erhalten den gleichen vollständigen App-Zugang. Wähle den Beitrag, der für dich passt.")
                .foregroundStyle(.secondary)
            Text("Für das Lesen ist ein aktiver Zugang nötig. Die Bibliothek kannst du jederzeit erkunden.")
                .font(.footnote).foregroundStyle(.secondary)
        }
    }

    @ViewBuilder private var accessStatus: some View {
        if access.hasAccess {
            VStack(alignment: .leading, spacing: 6) {
                Label("Dein Zugang ist aktiv", systemImage: "checkmark.seal.fill").font(.headline)
                if let grant = access.freeGrant, grant.isValid(at: Date()), let end = grant.expiresAt {
                    Text("Kostenloses Jahr bis \(end.formatted(date: .long, time: .omitted))")
                    if let start = grant.startsAt {
                        Text("Beginn: \(start.formatted(date: .long, time: .omitted))").font(.footnote)
                    }
                } else if let end = access.paidExpiration {
                    Text("Aktuelle Laufzeit bis \(end.formatted(date: .long, time: .omitted))")
                }
            }
            .padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.accentColor.opacity(0.08), in: RoundedRectangle(cornerRadius: 16))
            .accessibilityIdentifier("active-access")
        } else if access.isLoading {
            ProgressView("Zugang wird geprüft …")
        }
    }

    private var statisticsHeading: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let stats = access.statistics, stats.total > 0 {
                Text("Auswahlklicks der letzten \(stats.windowDays) Tage · \(stats.total.formatted()) insgesamt")
            } else {
                Text("Noch keine Auswahlzahlen verfügbar")
            }
            Text("Gezählt werden Auswahlklicks, auch bei abgebrochenen Käufen.")
                .font(.caption).foregroundStyle(.secondary)
        }.font(.footnote).accessibilityIdentifier("access-statistics")
    }

    private func subscription(_ option: AccessOption) -> some View {
        let supporter = option == .supporter
        let product = access.products[option]
        return VStack(alignment: .leading, spacing: 12) {
            Text(supporter ? "Förderabo" : "Jahresabo").font(.title2.bold())
            if let product {
                Text("\(product.localizedPrice) / \(product.subscriptionPeriod)")
                    .font(.title.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
            } else {
                Text("Preis wird geladen …").font(.headline).foregroundStyle(.secondary)
            }
            Text(supporter ? "Dein Mehrbeitrag unterstützt kostenlose Zugänge." :
                "Dein Beitrag für die \(AppEdition.isSteiner ? "GA" : AppEdition.authorShortName)-App.")
                .foregroundStyle(.secondary)
            frequency(option)
            if let product, product.eligibleForTrial, let trial = product.trialDescription {
                Text("\(trial) kostenlos, danach \(product.localizedPrice) jährlich.")
                    .font(.subheadline.weight(.medium))
            }
            Button {
                Task { await access.purchase(option) }
            } label: {
                Group {
                    if let product, product.eligibleForTrial, let trial = product.trialDescription {
                        Text("\(trial) kostenlos testen")
                    } else if let product {
                        Text(supporter ? "Für \(product.localizedPrice) jährlich fördern" : "Für \(product.localizedPrice) jährlich abonnieren")
                    } else { Text("Abo derzeit nicht verfügbar") }
                }
                .frame(maxWidth: .infinity).padding(.vertical, 8)
                .fixedSize(horizontal: false, vertical: true)
            }
            .buttonStyle(.borderedProminent)
            .disabled(access.isBusy || product == nil)
            .accessibilityIdentifier("purchase-\(option.rawValue)")
        }
        .padding(20).frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.accentColor.opacity(supporter ? 0.08 : 0.04), in: RoundedRectangle(cornerRadius: 20))
        .overlay(RoundedRectangle(cornerRadius: 20).strokeBorder(Color.accentColor.opacity(0.18)))
    }

    private var freeOption: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Wenn du den Beitrag gerade nicht aufbringen kannst").font(.headline)
            Text("Kostenloses Jahr · 0 €").font(.title3.bold())
            frequency(.free)
            Button(showsRequest ? "Anfrage schließen" : "Ein kostenloses Jahr anfragen") {
                showsRequest.toggle()
                if showsRequest { Task { await access.recordSelection(.free) } }
            }
            .buttonStyle(.bordered).frame(minHeight: 44)
            .accessibilityIdentifier("open-free-request")
            if showsRequest {
                Text("Eine klare Bitte genügt. Du brauchst keinen Einkommensnachweis. Du kannst jederzeit erneut anfragen.")
                    .font(.subheadline)
                Text("Deine Bitte").font(.headline)
                ZStack(alignment: .topLeading) {
                    TextEditor(text: $request).frame(minHeight: 135).focused($requestFocused)
                        .accessibilityLabel("Deine Bitte")
                        .accessibilityIdentifier("free-request-message")
                        .scrollContentBackground(.hidden)
                    if request.isEmpty {
                        Text("Bitte ermögliche mir ein kostenloses Jahr. Den Beitrag kann ich zurzeit nicht aufbringen.")
                            .foregroundStyle(.secondary).padding(8).allowsHitTesting(false)
                            .accessibilityHidden(true)
                    }
                }
                .padding(4).background(.background, in: RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(.secondary.opacity(0.3)))
                Text("Deine Nachricht bleibt vertraulich und wird nach 30 Tagen gelöscht. Nach erfolgreicher Speicherung beginnt dein kostenloses Jahr sofort. Es geht ohne Zahlung zu Ende.")
                    .font(.footnote).foregroundStyle(.secondary)
                Button {
                    requestFocused = false
                    Task {
                        if await access.submitFreeRequest(request) { request = "" }
                    }
                } label: {
                    HStack {
                        if access.isBusy { ProgressView() }
                        Text("Bitte absenden").frame(maxWidth: .infinity)
                    }.padding(.vertical, 8)
                }
                .buttonStyle(.borderedProminent)
                .disabled(access.isBusy || access.isLoading || request.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .accessibilityIdentifier("submit-free-request")
            }
        }
        .padding(18).frame(maxWidth: .infinity, alignment: .leading)
        .background(.quaternary.opacity(0.3), in: RoundedRectangle(cornerRadius: 16))
    }

    @ViewBuilder private func frequency(_ option: AccessOption) -> some View {
        if let stats = access.statistics, stats.total > 0 {
            VStack(alignment: .leading, spacing: 4) {
                Text("\(stats.percentage(for: option).formatted(.number.precision(.fractionLength(1)))) % · \(stats.count(for: option).formatted()) Auswahlklicks")
                    .font(.caption).monospacedDigit()
                ProgressView(value: stats.percentage(for: option), total: 100).accessibilityHidden(true)
            }
        } else {
            Text("Noch keine Auswahlzahlen verfügbar").font(.caption).foregroundStyle(.secondary)
        }
    }

    private var accountActions: some View {
        VStack(alignment: .leading, spacing: 12) {
            Divider()
            Button("Käufe wiederherstellen") { Task { await access.restorePurchases() } }
                .disabled(access.isBusy).frame(minHeight: 44).accessibilityIdentifier("restore-purchases")
            Button("Abo verwalten") { Task { await manageSubscriptions() } }.frame(minHeight: 44)
            DisclosureGroup("Gratiszugang wiederherstellen") {
                VStack(alignment: .leading, spacing: 12) {
                    if let code = access.recoveryCode {
                        Text("Bewahre deinen persönlichen Wiederherstellungscode sicher auf. Er ermöglicht den Zugang auf einem anderen Gerät.")
                        Text(code).font(.caption.monospaced()).textSelection(.enabled)
                            .privacySensitive().accessibilityIdentifier("access-recovery-code")
                        ShareLink(item: code) { Label("Code sichern", systemImage: "square.and.arrow.up") }
                    }
                    TextField("Wiederherstellungscode", text: $recovery)
                        .textFieldStyle(.roundedBorder).autocorrectionDisabled()
                        .accessibilityIdentifier("recover-access-code")
                    Button("Gratiszugang wiederherstellen") { Task { await access.recoverFreeAccess(recovery) } }
                        .disabled(access.isBusy || access.isLoading || recovery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    Text("Die Wiederherstellung meldet das vorherige Gerät für Gratisanfragen ab.")
                        .font(.caption).foregroundStyle(.secondary)
                }.padding(.vertical, 12)
            }
            Button("Zugang aktualisieren") { Task { await access.refresh() } }
                .disabled(access.isBusy).frame(minHeight: 44)
            Button("Zugangsdaten löschen", role: .destructive) { confirmsDeletion = true }
                .disabled(access.isBusy || access.isLoading).frame(minHeight: 44)
        }
    }

    private var legal: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Beide Abos verlängern sich jährlich. Bei einem berechtigten Apple-Konto beginnt das Abo mit der im Angebot angezeigten kostenlosen Probephase. Danach wird der angezeigte Jahresbeitrag berechnet. Kündige mindestens 24 Stunden vor Ende der Probephase oder der Laufzeit in deinen Apple-Abos, um die nächste Zahlung zu vermeiden.")
            Text("Jahresabo, Förderabo und Gratisjahr enthalten dieselben Funktionen. Der Zugang umfasst die in der App verfügbaren Texte; noch fehlende Bände werden in der Bibliothek kenntlich gemacht.")
            HStack {
                Button("Datenschutz") { showsPrivacy = true }
                Link("Nutzungsbedingungen", destination: URL(string: "https://www.apple.com/legal/internet-services/itunes/dev/stdeula/")!)
            }
            Link("Kontakt und Hilfe", destination: supportURL)
        }.font(.footnote).foregroundStyle(.secondary)
    }

    private var supportURL: URL {
        if let configured = Bundle.main.object(forInfoDictionaryKey: "GASupportURL") as? String,
           let url = URL(string: configured), url.scheme == "https" {
            return url
        }
        return URL(string: "mailto:jonathan@kutscher.club")!
    }

    @MainActor private func manageSubscriptions() async {
        #if os(iOS)
        guard let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first(where: { $0.activationState == .foregroundActive }) else {
            openURL(access.manageSubscriptionsURL); return
        }
        do { try await AppStore.showManageSubscriptions(in: scene) }
        catch { managementError = "Die Aboverwaltung konnte nicht geöffnet werden. Bitte öffne deine Abos in den Apple-Einstellungen." }
        #else
        openURL(access.manageSubscriptionsURL)
        #endif
    }
}

struct GAPrivacyView: View {
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("Datenschutz").font(.largeTitle.bold())
                    Text("Verantwortlich: Jonathan Kutscher, Einzelunternehmen. Kontakt: jonathan@kutscher.club, Telefon 01799439545.")
                    Text("Käufe und Zugang").font(.headline)
                    Text("Apple wickelt Käufe und Zahlungen ab. RevenueCat prüft deinen Abozugang anhand einer zufälligen Benutzerkennung und Kaufdaten. Wir erhalten keine Zahlungsdaten wie deine Kreditkartennummer. Dein persönlicher Wiederherstellungscode und die Zugangsdaten werden im Schlüsselbund deines Geräts gespeichert.")
                    Text("Kostenloses Jahr").font(.headline)
                    Text("Für ein kostenloses Jahr sendet die App deine Bitte und eine zufällige Zugangskennung an unseren Server. Die Bitte wird verschlüsselt gespeichert und nach 30 Tagen gelöscht. Anfragenummer, Status und Zugangszeitraum bleiben gespeichert, damit dein Zugang geprüft und eine doppelte Übermittlung vermieden werden kann. Du kannst diese Daten über „Zugangsdaten löschen“ entfernen. Ein Gratisjahr wird nicht in ein bezahltes Abo umgewandelt.")
                    Text("Auswahlzahlen").font(.headline)
                    Text("Die Auswahl von Jahresabo, Förderabo oder Gratisjahr wird als Klick erfasst. Öffentlich zeigt die App nur die Anzahl und den Anteil der Klicks der letzten 90 Tage. Deine Nachricht und Zugangskennung werden nicht veröffentlicht.")
                    Text("Deine Bibliothek").font(.headline)
                    Text("Lesepositionen, Notizen und Markierungen bleiben auf deinem Gerät. Wenn iCloud verfügbar ist, gleicht die App sie über deine private CloudKit-Datenbank ab. Der Katalog- und Zugangsserver erhält diese Daten nicht. Bei Serverabrufen werden technisch notwendige Verbindungsdaten verarbeitet.")
                    Text("Deine Rechte").font(.headline)
                    Text("Für Auskunft, Berichtigung oder Löschung und Fragen zum Datenschutz erreichst du uns per E-Mail. Die vollständige Datenschutzerklärung beschreibt auch Rechtsgrundlagen, Dienstleister und deine weiteren Rechte.")
                    if let url = Bundle.main.object(forInfoDictionaryKey: "GAPrivacyURL") as? String, let url = URL(string: url), url.scheme == "https" {
                        Link("Vollständige Datenschutzerklärung", destination: url)
                    }
                }.padding(24).frame(maxWidth: 650, alignment: .leading).frame(maxWidth: .infinity)
            }
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } } }
        }
        #if os(macOS)
        .frame(minWidth: 440, minHeight: 500)
        #endif
    }
}
