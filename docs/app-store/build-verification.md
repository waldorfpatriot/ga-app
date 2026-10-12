# Build-Verifikation

## Version 1.0.1, Build 4 — 11. Oktober 2026

Beide signierten Release-Archive und Exporte wurden erfolgreich erstellt. Apples
`altool --validate-app` bestätigt für IPA und Mac-Paket „VERIFY SUCCEEDED with no
errors“. Beide tatsächlichen Pakete enthalten Version 1.0.1, Build 4, die gemeinsame
Bundle-ID, die Produktions-URL, sechs eigene Datenschutzkategorien und das
RevenueCat-Manifest. Beide bestehen die strenge Signaturprüfung, verwenden
CloudKit Production und enthalten keine lokale StoreKit-Testkonfiguration oder
`GA_USE_LOCAL_STOREKIT`. Der Mac-Export enthält arm64 und x86_64 und eine gültige
Installer-Zertifikatskette.

Paketprüfsummen und Größen: `artifacts/app-store/build4-package-verification.json`.
Archive, Exporte sowie Validierungs- und Uploadprotokolle liegen unter
`artifacts/app-store/ios/build-4/` und
`artifacts/app-store/mac/universal/build-4/`.
Der [aktuelle Einreichungsbericht](publishing/release-1.0.1.md) enthält den
jeweiligen Apple-Verarbeitungsstand und die noch ausstehenden Schritte.

## Historischer Vorbereitungsstand vom 9. Oktober 2026

Stand: 9. Oktober 2026. Xcode 27.1 (27A9275), RevenueCat Swift SDK exakt 5.94.0. **Release-Kandidaten sind Version 1.0, Build 3 für beide Plattformen im gemeinsamen App-Eintrag `6820947669`, Bundle-ID `com.jonathankutscher.ga`.** Beide signierten Exporte bestehen die strenge Paketprüfung und Apples offizielle Validierung; beide Uploads wurden angenommen. Beide Builds sind `VALID` / `APP_STORE_ELIGIBLE` und in ihren manuellen Plattform-Entwürfen ausgewählt. Die nachstehenden Build-2-Berichte bleiben als historische Belege erhalten. Keine Review-Einreichung, Veröffentlichung oder externe TestFlight-Verteilung.

## Gemeinsamer Build 3: bestätigte Paketprüfung

Beide Targets verwenden die vorhandenen gemeinsamen Produkte `com.jonathankutscher.ga.annual` und `com.jonathankutscher.ga.supporter` sowie denselben öffentlichen RevenueCat-SDK-Schlüssel der iOS-Apple-Verbindung. Mac erhält die Kategorie Books passend zur gemeinsamen App-Information Books / Reference. Die bisherigen separaten Mac-Builds können nicht in den gemeinsamen Apple-Eintrag verschoben werden.

Zusätzlich wurde eine fehlende Laufzeitkonfiguration entdeckt: In beiden tatsächlichen alten Build-2-Info.plists fehlte `GACloudKitContainerIdentifier`, obwohl ihre signierten Entitlements den Container enthielten. Die **exportierten Builds 3** bestätigen jetzt ausdrücklich `iCloud.com.jonathankutscher.ga`, gemeinsame Bundle-ID, identischen öffentlichen SDK-Schlüssel, produktive URLs, Production-CloudKit-Entitlements, zwei Datenschutzmanifeste und die fünf eigenen Datenschutzkategorien. Beide enthalten keine lokale StoreKit-Testdatei und bestehen die strenge Signaturprüfung. Mac enthält arm64 und x86_64 sowie App Sandbox, Netzwerk- und Dateizugriffsrechte; auch die Installer-Zertifikatskette ist geprüft.

| Plattform | Signiertes Archiv | Export und Paketnachweis |
| --- | --- | --- |
| iOS/iPadOS | `artifacts/app-store/ios/build-3/GA-iOS-1.0-3.xcarchive` | [IPA-Paketprüfung](../../artifacts/app-store/ios/build-3/validation/package-verification.json), Export `ios/build-3/export/GA iOS.ipa` |
| Nativer Mac | `artifacts/app-store/mac/universal/build-3/GA-Mac-1.0-3.xcarchive` | [PKG-Paketprüfung](../../artifacts/app-store/mac/universal/build-3/validation/package-verification.json), Export `mac/universal/build-3/export/GA Mac.pkg` |

iOS verwendet das Profil **GA iOS App Store 2026-10-09**, UUID `f5d590a3-8ed4-4e2b-b8f5-c67bd3251404`; Mac **GA Universal Mac App Store 2026-10-09 CloudKit**, UUID `bc1fa24d-e573-4120-8494-c9f6e5fc1a76`. Beide tatsächlichen Profile enthalten die gemeinsame App-Kennung und Production-Containerzuordnung. Apples `altool --validate-app` bestätigt für beide Pakete „VERIFY SUCCEEDED with no errors“: [iOS-Protokoll](../../artifacts/app-store/ios/build-3/validation/apple-validation.log), [Mac-Protokoll](../../artifacts/app-store/mac/universal/build-3/validation/apple-validation.log).

Beide privaten Uploads sind erfolgreich. iOS-Build **`7f0ab926-cd37-4cf0-b635-082ebbbf955b`** ist `VALID` / `APP_STORE_ELIGIBLE`, `usesNonExemptEncryption=false`, und an Version `9a5d0b78-b826-4bc3-b6d2-9da53d1672c5` mit `MANUAL` ausgewählt: [Auswahl-Readback](../../artifacts/app-store/ios/build-3/validation/draft-build-selection.json). Mac-Build **`dc3f136c-e114-497b-bc50-481b34e199ce`** ist ebenfalls `VALID` / `APP_STORE_ELIGIBLE`, `usesNonExemptEncryption=false`, und an der gemeinsamen `MAC_OS`-Version `0ddcfe86-8da5-42d1-8ff1-1a16d905b09f` mit `MANUAL` ausgewählt: [Mac-Auswahl-Readback](../../artifacts/app-store/mac/universal/build-3/validation/draft-build-selection.json). Beide Versionen bleiben `PREPARE_FOR_SUBMISSION`.

Für reproduzierbare Archive setzt eine temporäre Xcode-Konfiguration das Profil je Produkt: `PROVISIONING_PROFILE_SPECIFIER=$(GA_PROFILE_$(PRODUCT_NAME:c99extidentifier))`, `GA_PROFILE_GA_iOS=GA iOS App Store 2026-10-09`, `GA_PROFILE_GA_Mac=GA Universal Mac App Store 2026-10-09 CloudKit`, `CODE_SIGN_STYLE=Manual`, `CODE_SIGN_IDENTITY=Apple Distribution`, Team `ER7U6R25KM`. Dadurch wird kein App-Profil auf RevenueCats Ressourcenbundle angewendet. Das regulär signierte Archiv und der manuelle Production-Export erhalten die geprüften App-Entitlements.

## Historische Artefakte für Build 2

Die dauerhaften, von Git ausgeschlossenen Belege der früheren getrennten Einrichtung liegen im Projekt:

| Plattform | Signiertes Archiv | App-Store-Paket |
| --- | --- | --- |
| iOS/iPadOS | `artifacts/app-store/ios/build-2/GA-iOS-1.0-2.xcarchive` | `artifacts/app-store/ios/build-2/export/GA iOS.ipa` |
| Mac | `artifacts/app-store/mac/build-2/GA-Mac-1.0-2.xcarchive` | `artifacts/app-store/mac/build-2/export/GA Mac.pkg` |

Exportoptionen und Zusammenfassungen stehen jeweils in `build-2/export/`. Die strukturierten Prüfberichte mit Paket-Prüfsummen stehen in `build-2/validation/package-verification.json`. Der damalige Quellstand ist mit SHA-256 in `artifacts/app-store/build-2/source-verification.json` festgehalten und wurde damals nach Export mit den zugehörigen Dateien verglichen.

## Historische Signierung und Produktionskonfiguration (Build 2)

iOS-Bundle-ID `com.jonathankutscher.ga`, Architektur arm64. Das Archiv trägt eine gültige Apple-Development-Signatur; das exportierte IPA trägt die Apple-Distribution-Signatur des Teams `ER7U6R25KM`. Das Distributionsprofil heißt **GA iOS App Store 2026-10-09** (Apple-ID `UPBAYU63B2`). Die tatsächlichen IPA-Entitlements bestätigen `get-task-allow = false`, den Container `iCloud.com.jonathankutscher.ga`, den Dienst CloudKit und die Containerumgebung **Production**. `codesign --verify --deep --strict` am ausgepackten App-Bundle bestand.

Mac-Bundle-ID `com.jonathankutscher.ga.mac`, Universal-App mit **arm64 und x86_64**, bestätigt durch `lipo -archs`. Das korrekte Profil **GA Mac App Store 2026-10-09 CloudKit** (Apple-ID `9UA4W4S5JQ`, UUID `d90e9730-444d-4d66-8694-e158b09b493f`) ist in der tatsächlich exportierten App enthalten und bestätigt den gemeinsamen Container. Die tatsächlichen signierten Entitlements enthalten **Production**, CloudKit, App Sandbox, ausgehende Netzwerkverbindungen und Zugriff auf vom Benutzer gewählte Dateien. Debugging ist nicht aktiviert. Das Paket trägt das vorhandene Mac-Installer-Distributionszertifikat; `pkgutil --check-signature` bestätigt die Apple-Zertifikatskette. Die ausgepackte App besteht `codesign --verify --deep --strict`.

Beide tatsächlichen Pakete enthalten den jeweils richtigen öffentlichen RevenueCat-SDK-Schlüssel aus `apple/GA/Purchases.xcconfig` sowie:

- Zugangsdienst: `https://fototausch.eu/rudolf-steiner-ga`
- Datenschutz: `https://fototausch.eu/rudolf-steiner-ga/privacy.html`
- Support: `https://fototausch.eu/rudolf-steiner-ga/support.html`

Das eigene `PrivacyInfo.xcprivacy` und das RevenueCat-Manifest sind enthalten. In keinem App-Bundle liegt eine `.storekit`-Testkonfiguration. Die Zeichenfolge `GA_USE_LOCAL_STOREKIT` fehlt in beiden optimierten Release-Programmen. Private Apple-, RevenueCat-Verwaltungs- oder Backend-Schlüssel werden nicht eingebettet; optionale lokale Konfigurationsüberschreibungen sind von Git ausgeschlossen.

## Datenschutzabgleich der historischen Builds 2

Build 2 korrigiert ausschließlich die Datenschutzmetadaten und die Buildnummer. Die eigene, tatsächlich in beiden Paketen enthaltene Datenschutzdeklaration entspricht jetzt allen fünf gespeicherten App-Store-Connect-Antworten:

| Datenkategorie | Zwecke | Mit Benutzer verknüpft | Tracking |
| --- | --- | --- | --- |
| User ID | App Functionality, Analytics | ja | nein |
| Purchase History | App Functionality, Analytics | ja | nein |
| Other User Content | App Functionality | ja | nein |
| Product Interaction | App Functionality, Analytics | ja | nein |
| Other Diagnostic Data | App Functionality | ja | nein |

Other Diagnostic Data umfasst die bestehenden, für Sicherheit und Verfügbarkeit aufbewahrten nginx-IP-/Anfrage-/Statusprotokolle. User ID erhielt zusätzlich Analytics; Product Interaction erhielt zusätzlich App Functionality für die in der App angezeigten Auswahlstatistiken. Das RevenueCat-Manifest selbst erklärt Purchase History; die Diagnose-Deklaration stammt aus der eigenen App. Die benötigte UserDefaults-Begründung `CA92.1` bleibt enthalten. Alle fünf tatsächlichen Paketdeklarationen wurden maschinell gegen die bestätigten Zwecke, Verknüpfung und Tracking-Antworten geprüft.

## Funktionsprüfungen

- iOS- und Mac-Debug-Builds sowie die endgültigen Build-2-Releasearchive erfolgreich.
- Die automatisierten nativen StoreKit-Prüfungen für Einführungsangebot, Kauf, Wiederherstellung und Widerruf wurden auf dem iPhone-Simulator ausgeführt; die Hauptprüfung enthält Auswertungen und Screenshots.
- Zwei Tests mit standardmäßig signiertem Simulator-Build bestätigten echte iOS-Keychain-Speicherung und den echten Zugangsdienst: kostenlose Anfrage mit Freischaltung, erneutem Start und Löschung sowie Netzwerkfehler mit erhaltenem Text. Beide bestanden. Für unsignierte Simulator-Apps wurde kein ungeschützter Speicherersatz eingebaut.
- Der Swift-Client bestand gegen den produktiven Zugangsdienst: Installation, zwölfmonatiger Gratiszugang, idempotente Anfrage, Token-Wechsel bei Wiederherstellung, Ablehnung des alten Tokens, Statistik-Dekodierung und Löschung. Testdaten wurden wieder gelöscht.
- `tools/check_access_store.py` bestand gegen den aktuellen AccessStore und das echte RevenueCat-SDK: gleichzeitige Backend-Vorgänge, veraltete Installationserstellung und Statusantworten, Wiederherstellung, Löschung, veraltete 401-Antworten sowie bestätigte Gratisanfragen. Echte CustomerInfo-Fixtures prüfen verifizierte Zahlungsfrist, abgelaufene/inaktive Ansprüche und fehlgeschlagene Verifikation. Das Formular leert sich nur nach ausdrücklich erfolgreicher Anfrage.
- `tools/check_library_search.py` bestand nach der Startverbesserung. Automatische Katalogaktualisierungen sind auf höchstens einmal je Minute begrenzt; manuelles Aktualisieren bleibt sofort möglich. Der schnellere Datumsparser liefert für sämtliche datierten Werke des geprüften Live-Katalogs und die Datumsformat-Proben dieselben gespeicherten Werte.
- Für die reine Metadatenkorrektur in Build 2 wurden die breiten UI-Tests nicht wiederholt. Die Laufzeitquellen sind unverändert; die tatsächlichen neuen Pakete wurden erneut vollständig auf Signatur, Konfiguration und Datenschutzdeklarationen geprüft.

## Historische Apple-Prüfung und private Bereitstellung (Build 2)

Die damaligen getrennten App-Store-Connect-Einträge und ihre Jahresabos mit 30,00 € und 90,00 € sowie drei Monaten kostenloser Einführung sind eingerichtet; Einzelheiten stehen im [Einrichtungsstand](publishing/setup-state.md). Beide damaligen Versionen waren für manuelle Veröffentlichung konfiguriert.

Apples offizielle Prüfung `altool --validate-app` bestand für **beide endgültigen Build-2-Pakete**: „VERIFY SUCCEEDED with no errors“. Beide Uploads wurden ebenfalls ohne Fehler angenommen:

| Plattform | App-Store-Connect-App | Build-2 Delivery UUID | Upload |
| --- | --- | --- | --- |
| iOS/iPadOS | `6820947669` | `88eef07a-2c33-4925-975c-8a44a52bdcb6` | erfolgreich |
| Mac | `6820968413` | `0b45ecbd-1efc-4dca-a963-24cc365c7334` | erfolgreich |

Die Plattform-Protokolle stehen jeweils unter `build-2/validation/apple-validation.log`, `apple-upload.log`, `apple-processing.log` und `app-store-builds.json`. Auch die anschließende Verarbeitung ist für beide Builds abgeschlossen: `BUILD-STATUS: VALID`, `IMPORT-STATUS: VALID`, `BUILD-AUDIENCE-TYPE: APP_STORE_ELIGIBLE`, `IS-ON-APP-STORE-CONNECT: true` und `USES-NON-EXEMPT-ENCRYPTION: false`. Die App-Store-Connect-API bestätigt für beide Buildnummer `2`, `processingState = VALID` und die jeweiligen Build-IDs aus der Tabelle.

Beide Build-2-Ressourcen wurden über die dokumentierte Build-Beziehung in den bestehenden Version-1.0-Entwürfen ausgewählt und anschließend erneut aus Apple gelesen:

| Plattform | App-Store-Version-ID | Gewählter Build | Veröffentlichung |
| --- | --- | --- | --- |
| iOS/iPadOS | `9a5d0b78-b826-4bc3-b6d2-9da53d1672c5` | `88eef07a-2c33-4925-975c-8a44a52bdcb6`, Build 2 | MANUAL |
| Mac | `34194598-a05b-4654-bc7f-2df7737ab63e` | `0b45ecbd-1efc-4dca-a963-24cc365c7334`, Build 2 | MANUAL |

Die gespeicherten Vorher-/Nachher-Beziehungen und Bestätigungen stehen jeweils in `build-2/validation/draft-build-selection.json`. Beim Auswahl-Readback waren beide Versionen `PREPARE_FOR_SUBMISSION`; es wurde keine Review-Einreichung ausgeführt.

Die ursprünglichen Build-1-Archive, Pakete und Nachweise bleiben unter `artifacts/app-store/ios/` und `artifacts/app-store/mac/` erhalten; ihr Quellstand steht in `artifacts/app-store/source-verification.json`. Build 1 war erfolgreich validiert, hochgeladen und verarbeitet, enthält jedoch die ältere Datenschutzdeklaration. Die damalige Entwurfsauswahl verwendete Build 2. Die neuen Versandkandidaten sind Builds 3; ihre bestätigte Auswahl steht im oberen Abschnitt.

Es wurden keine Testergruppen angelegt, keine externen Tester benachrichtigt und keine Review-Einreichung oder öffentliche Veröffentlichung ausgelöst. Das CloudKit-Production-Schema wurde veröffentlicht und im Portal erneut geprüft: `GAReadingState`, `payload` als Asset und `schemaVersion` als Int64. Der echte iCloud-Synchronisationstest zwischen zwei signierten Geräten bleibt in der [Release-Checkliste](release-checklist.md) offen.
