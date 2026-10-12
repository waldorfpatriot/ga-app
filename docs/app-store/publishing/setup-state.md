# Bestätigter Einrichtungsstand

Aktualisierung vom 11. Oktober 2026: iOS-Version 1.0 (Build 3) ist inzwischen
freigegeben und veröffentlicht; Mac 1.0 (Build 3) wartete beim heutigen Readback
auf Review. Für Version 1.0.1 (Build 4) sind Textmeldungen implementiert, das Backend
produktiv und die Gewaltfelder deaktiviert. Die territoriale Apple-API bestätigt
für Deutschland 16+. Der [aktuelle Releasebericht](release-1.0.1.md) dokumentiert
Builds, Datenschutz-Ergänzung und erneute Einreichung. Die nachstehenden Angaben
beschreiben den historischen Vorbereitungsstand vom 9. Oktober.

Stand: 9. Oktober 2026. **Ein gemeinsamer App-Store-Eintrag für iPhone, iPad und Mac ist technisch vorbereitet; der frühere separate Mac-Eintrag ist entfernt.** Es wurde keine App-Prüfung übermittelt und keine App veröffentlicht. Datenschutzattest, belegbare Inhaltsrechte und reale geräteübergreifende Tests bleiben offen.

## Gemeinsames Ziel und aktuelle Zuordnung

| Objekt | Ziel / bestätigter Stand |
| --- | --- |
| Apple-App | `6820947669`, Rudolf Steiner: Gesamtausgabe |
| Bundle-ID beider nativer Targets | `com.jonathankutscher.ga` |
| Gemeinsame App-Information | Deutsch, Books / Reference |
| iOS/iPadOS-Version 1.0 | `9a5d0b78-b826-4bc3-b6d2-9da53d1672c5`, `PREPARE_FOR_SUBMISSION`, `MANUAL` |
| Ausgewählter iOS-Build 3 | `7f0ab926-cd37-4cf0-b635-082ebbbf955b`, `VALID` / `APP_STORE_ELIGIBLE`, `MANUAL` |
| Gemeinsame Mac-Version 1.0 | `0ddcfe86-8da5-42d1-8ff1-1a16d905b09f`, `MAC_OS`; deutsche Lokalisierung `e9e0ed83-4150-4231-a756-99d26924a73a` angelegt |
| Ausgewählter gemeinsamer Mac-Build 3 | `dc3f136c-e114-497b-bc50-481b34e199ce`, `VALID` / `APP_STORE_ELIGIBLE`, `MANUAL` |
| Gemeinsame Builds 3 | Beide Exporte streng geprüft, offiziell validiert, erfolgreich hochgeladen, verarbeitet und in den gemeinsamen Plattform-Entwürfen ausgewählt |
| Abo-Gruppe | `22458743`, GA-App-Zugang |
| Gemeinsames Jahresabo | `6820967918`, `com.jonathankutscher.ga.annual` |
| Gemeinsames Förderabo | `6820968113`, `com.jonathankutscher.ga.supporter` |

Der frische schreibgeschützte Apple-Abgleich vor der Umstellung zeigte im gemeinsamen Eintrag nur die iOS-Version; inzwischen ist die neue `MAC_OS`-Version mit deutscher Lokalisierung angelegt und ihr Textabgleich bestätigt. Die beiden gemeinsamen Produkte standen auf `READY_TO_SUBMIT`; ihre aktuellen Produktversionen und die Gruppe waren im privaten Review-Entwurf vorbereitet. Apples [Plattform-Erstellung](https://developer.apple.com/help/app-store-connect/create-an-app-record/add-platforms) verwendet dieselbe Apple-ID, SKU und Bundle-ID. Die API [`POST /v1/appStoreVersions`](https://developer.apple.com/documentation/appstoreconnectapi/post-v1-appstoreversions) unterstützt ausdrücklich die erste Version auf einer neuen Plattform. Bestehende getrennte Einträge können nicht zusammengeführt werden; neue Builds 3 für beide Targets sind erforderlich. Universeller Kauf ist erst nach Apples Freigabe mindestens zweier Plattformversionen verfügbar.

## Gemeinsame Produkte und Vertrieb

Die zwei wiederverwendeten Abos haben `ONE_YEAR`, `groupLevel=1`, deutsche Namen und Beschreibungen. Die **exakten deutschen Preise 30,00 € / 90,00 €** und jeweils **drei Kalendermonate `FREE_TRIAL`** für berechtigte Accounts sind eingerichtet. Beginn des Angebots: 9. Oktober 2026, ohne festes Enddatum. Es gibt keinen automatisch erteilten Backend-Testzugang.

Apples tatsächliche private Reviewvalidierung verlangte Preispläne in sämtlichen 175 Territorien, auch bei deutscher Verfügbarkeit. Die beiden gemeinsamen Produkte besitzen bereits **175 wirksame `UPFRONT`-Preise** aus Apples Equalisierungen des deutschen Basispreises. Der [unabhängige Preis-Readback](../../../artifacts/app-store/subscription-price-coverage-readback.json) bestätigt jede Preiskennung, die exakten deutschen Preise und ausschließlich `DEU` mit ausgeschalteter Freigabe neuer Territorien. Dieser historische Bericht enthält zusätzlich die zwei früheren separaten Mac-Produkte; sie sind kein neues Vier-Produkte-Ziel. Der App-Download ist 0,00 €, nur Deutschland verfügbar.

Das kostenlose Jahr auf vertrauliche Bitte bleibt eine eigene Backend-Freischaltung: unmittelbar zwölf Kalendermonate, keine Zahlung, keine automatische Umwandlung in ein bezahltes Abo. Alle Optionen haben denselben Funktionsumfang.

## RevenueCat

Projekt [Gesamtausgabe](https://app.revenuecat.com/projects/34fd17d0/overview), ID `34fd17d0`. Die gemeinsame Apple-App verwendet die vorhandene Verbindung **`app64fd68fa61`**, Bundle `com.jonathankutscher.ga`; ihr öffentlicher SDK-Schlüssel wird für beide Plattformen verwendet. Entitlement **`ga_access`**, Offering **`default`** (`ofrng38b6d405b1`), Pakete **`$rc_annual`** und **`supporter`**. Gemeinsame Produkte: `proda60495850c` und `prod91425ebda4`.

Diese vorhandene Verbindung bestätigt ASC-Schlüssel **B8AQ567J5P** und IAP-Schlüssel **XB7ML48U4A** als gültig. Production- und Sandbox-Serverbenachrichtigungen der gemeinsamen Apple-App sind V2 zu `api.revenuecat.com`; geheime Endpoint-Pfade bleiben aus Berichten ausgeschlossen. Das Projekt zeigt null aktive Drittintegrationen. Die tatsächliche Kaufbarkeit, Angebotsberechtigung und Wiederherstellung über iOS/Mac müssen auf den gemeinsamen Produkten in Sandbox/TestFlight geprüft werden.

Die frühere Mac-Verbindung `app85b7787fe9` bleibt historische Konfiguration; die beiden zugehörigen separaten Apple-Produkte sind ausgeschaltet. Der ursprüngliche RevenueCat-Store-Produktstatus war „Could not check“; gültige Credentials allein belegen keine tatsächlichen Käufe. Belege der früheren Einrichtung: [Produkte](../revenuecat-products-proof.jpg), [Entitlement](../revenuecat-entitlement-proof.jpg), [Offering](../revenuecat-offering-proof.jpg), [damalige Mac-Credentials](revenuecat-mac-credentials-proof.jpg).

## Texte und Bilder

Die neue deutsche Beschreibung hat **4000 Zeichen und 26 tatsächlich verfügbare GA-Titel**, der Werbetext **145 Zeichen**. Die endgültige Beschreibung und der unveränderte Werbetext sind in beiden gemeinsamen Entwürfen exakt gespeichert und zurückgelesen: [Textabgleich](../../../artifacts/app-store/universal-copy-refresh-20261009.json); der [gemeinsame Mac-Metadatenabgleich](../../../artifacts/app-store/universal-mac-metadata-20261009.json) bestätigt auch Name, Books / Reference und `MANUAL`. Die früheren separaten Mac-Belege bleiben historisch erhalten. Beide Plattformen verwenden den Namen Rudolf Steiner: Gesamtausgabe und Books / Reference. Der Katalog enthält 463 Einträge, davon 324 verfügbare Texte; fünf vollständige Grundwerke sind enthalten. Die unabhängige Ausgabe verspricht nicht sämtliche Bände und keine offizielle Verlagszugehörigkeit.

Die neue Marketingfolge umfasst **acht Bilder je mobiler Größenklasse und vier Mac-Bilder**; alle 28 Dateien liegen lokal mit geprüften nativen Maßen und RGB ohne Transparenz vor. Die vorhandenen Aufnahmen 01–03 bleiben bytegleich; sechs alte mobile Kaufbilder sind unter `screenshots/review/<Gerät>/` unverändert erhalten. Neue Aufnahmen zeigen Sammlungen, Sammlung mit Büchern, Inhaltsverzeichnis, Leseeinstellungen sowie Markierungen und Notizen. Alle vier Mac-Dateien sind an der neuen gemeinsamen Lokalisierung als `COMPLETE` mit passenden Originalprüfsummen und Reihenfolge bestätigt: [neuer Mac-Readback](../../../artifacts/app-store/universal-mac-screenshots-20261009.json). Auch die drei mobilen Sets sind vollständig bestätigt. Der [abschließende gemeinsame Readback](../../../artifacts/app-store/marketing-screenshot-refresh-20261009.json) bestätigt alle 28 Bilder als COMPLETE mit passenden Originalprüfsummen und Reihenfolge sowie die Entfernung der sechs öffentlichen Kaufbilder. [Aktuelle lokale Bildinventur](../screenshots/README.md).

Historie: [18 ursprüngliche Marketingbilder](../../../artifacts/app-store/marketing-screenshot-upload-report.json) und [vier Mac-Bilder am separaten Eintrag](../../../artifacts/app-store/mac-screenshot-refresh-20261009.json) sind `COMPLETE` mit Original-MD5 und geprüfter Reihenfolge. Ihre alten Mac-Zuordnungen belegen keinen Upload im gemeinsamen Eintrag. Die **zwei gemeinsamen Abo-Reviewassets bleiben unverändert**, erneut als COMPLETE mit identischen MD5-Prüfsummen und Dateigrößen bestätigt: [aktueller Readback](../../../artifacts/app-store/universal-subscription-review-assets-20261009.json). Die Quellen liegen unter `screenshots/review/iphone-6.9/`; die zwei damaligen separaten Mac-Reviewassets bleiben als historische Belege erhalten. [Vier damalige Reviewassets](../../../artifacts/app-store/subscription-review-screenshot-upload-report.json), [gespeicherte Hinweise](../../../artifacts/app-store/subscription-review-notes-report.json).

Die kleineren nativen Mac-Lese-/Kaufblätter bleiben ausschließlich QA-Belege und wurden nicht gestreckt oder gepolstert. Die für eine Aufnahme angelegte lokale Gratisinstallation wurde gezielt entfernt; Produktionsdaten blieben unberührt.

## Private Review-Entwürfe

Der **iOS-Entwurf `935ba689-4148-4cfd-a308-58b5fd47edcf`** enthält drei Items: die gemeinsame Gruppe und beide Produkte. Der neue gemeinsame **Mac-Entwurf `63883c48-e34e-4bd2-9148-a8b5200a3203`** enthält derzeit null Items und erhält ausschließlich seine App-Version; Gruppe und Produkte werden nicht dupliziert. Beide Entwürfe sind `READY_FOR_REVIEW`, `submittedDate=null`. Beide finalen Builds 3 sind bestätigt und ausgewählt. Apples tatsächlicher Versuch, die App-Versionen hinzuzufügen, meldet für beide ausschließlich fehlende `contentRightsDeclaration` und `APP_DATA_USAGES_REQUIRED` (gespeicherte Datenschutzantworten noch nicht veröffentlicht): [Validierungsbericht](../../../artifacts/app-store/universal-private-review-drafts-20261009.json). Die zugehörigen rechtlichen Zustimmungen bleiben offen. Es wurde keine endgültige Aktion „Zur Prüfung übermitteln“ ausgeführt.

Historie: Der separate Mac-Reviewentwurf `288db6c4-05d0-4abb-8446-413e75bb97fd` enthält die frühere Mac-Gruppe und deren zwei Produkte. Seine anfänglich falsche Plattform `IOS` wurde durch PATCH ausschließlich `platform=MAC_OS` korrigiert; drei Item-IDs, `READY_FOR_REVIEW`, `submittedDate=null` und die damalige manuelle Build-2-Auswahl blieben erhalten. Berichte: `artifacts/app-store/private-review-platform-correction.json`, `review-platform-rights-readback.json`. Die frühere [Mac-Oberflächenaufnahme](apple-mac-private-review-proof.jpg) stammt vor der Plattformkorrektur und ist kein aktueller Nachweis. Dieser alte Entwurf wurde bei der Stilllegung geleert; seine drei früheren Items sind entfernt. Er wird nicht für den universellen Kauf wiederverwendet.

## Datenschutz und Inhaltsrechte

Im gemeinsamen App-Eintrag sind fünf Datentypen gespeichert, jeweils mit Benutzerverknüpfung und ohne Tracking:

- Other User Content: App Functionality.
- User ID: App Functionality und Analytics.
- Purchase History: App Functionality und Analytics.
- Product Interaction: App Functionality und Analytics.
- Other Diagnostic Data: App Functionality.

Die tatsächlich exportierten Builds 3 enthalten die beiden Datenschutzmanifeste; ihre fünf eigenen Kategorien entsprechen diesen gespeicherten Antworten. [Dateninventur](../privacy-inventory.md). **Die abschließende Apple-Veröffentlichung der Antworten wartet weiterhin auf ausdrückliche Zustimmung zum konkreten Rechtsattest** über Richtigkeit, Prüfrichtlinien, geltendes Recht und Aktualisierung. Der Bestätigungsgrund ist diese Rechtszustimmung, nicht der Buttonname. [Tatsächlicher Dialog](apple-privacy-approval-proof.jpg).

**`contentRightsDeclaration` ist weiterhin `null`.** Apples Ja-Auswahl bestätigt ausdrücklich erforderliche Rechte. Aktuelle Reader-Payloads enthalten tatsächlich modernes Herausgeber-/Verlagsmaterial in GA 255b und GA 267; GA 040a weist weitere Abgrenzungsfragen auf. Steiners Originaltexte allein belegen nicht sämtliche Bestandteile. Keine ungesicherte Ja- oder falsche Nein-Erklärung wurde gespeichert. [Fundstellen und fehlende Berechtigungsnachweise](../content-rights.md), [tatsächlicher Dialog](apple-content-rights-approval-proof.jpg).

## Geschäftskonto, Alter und CloudKit

Das bestehende Konto zeigt kostenlose und kostenpflichtige Verträge **Aktiv**, beide Steuerformulare **Aktiv**, DSA **Aktiv**, DAC7 **Aktiviert**. Ein Bankkonto ist vorhanden; Kontonummern wurden weder ausgegeben noch verändert. Eine separate Bankstatusanzeige wird nicht behauptet. Keine neuen Verträge, Zahlungen oder Änderungen von Bank-/Steuerangaben. [Statusbeleg](apple-business-readiness-proof.jpg).

Die vollständige Alterseinstufung nach Prüfung aller 324 Texte ist gespeichert: Deutschland **18+**, älteres API-Feld 17+, keine künstliche Überschreibung. [Begründung](../age-rating.de-DE.md), `artifacts/app-store/age-rating-readback.json`.

CloudKit **`iCloud.com.jonathankutscher.ga`** besitzt in Production **`GAReadingState`**, `payload: Asset`, `schemaVersion: Int64`. Der additive Diff und der Production-Readback sind bestätigt. [Schema-Beleg](apple-cloudkit-production-proof.jpg). Die App nutzt die private Datenbank; es wurden keine persönlichen Datensätze abgefragt oder zurückgesetzt. Der neue Mac-Export verwendet das passende Profil **GA Universal Mac App Store 2026-10-09 CloudKit**, UUID `bc1fa24d-e573-4120-8494-c9f6e5fc1a76`; gemeinsame Bundle-ID, Production-Entitlements und expliziter Info.plist-Containerwert sind bestätigt. Das alte Profil `9UA4W4S5JQ` gehört zur separaten Mac-ID. Der echte Synchronisierungstest auf zwei signierten Geräten steht aus.

## Archive und historische Mac-Einrichtung

Beide signierten Build-3-Exporte unter `artifacts/app-store/ios/build-3/` und `artifacts/app-store/mac/universal/build-3/` bestehen strenge Signaturprüfung und offizielle Apple-Validierung. Gemeinsame Bundle-ID, SDK-Schlüssel, URLs, expliziter CloudKit-Containerwert, Production-Entitlements, fünf Datenschutzkategorien und fehlende StoreKit-Testdatei sind bestätigt. Beide Uploads sind erfolgreich. iOS-Build `7f0ab926-cd37-4cf0-b635-082ebbbf955b` ist `VALID` / `APP_STORE_ELIGIBLE` und im manuellen Entwurf ausgewählt; [Readback](../../../artifacts/app-store/ios/build-3/validation/draft-build-selection.json). Der Mac-Build `dc3f136c-e114-497b-bc50-481b34e199ce` ist ebenfalls `VALID` / `APP_STORE_ELIGIBLE` und in der gemeinsamen Mac-Version mit `MANUAL` ausgewählt; [Mac-Readback](../../../artifacts/app-store/mac/universal/build-3/validation/draft-build-selection.json). Beide bestätigen `usesNonExemptEncryption=false`. Der frühere iOS-Build 2 unter `artifacts/app-store/ios/build-2/` bleibt historischer Prüfbeleg.

**Historisch:** Mac-App `6820968413`, Bundle `com.jonathankutscher.ga.mac`, Version `34194598-a05b-4654-bc7f-2df7737ab63e`, Build 2 `0b45ecbd-1efc-4dca-a963-24cc365c7334`, Gruppe `22458772`, Produkte `6820968686` / `6820968894`. Der Universal-Mac-Build arm64/x86_64 unter `artifacts/app-store/mac/build-2/` wurde erfolgreich signiert, offiziell validiert, hochgeladen und ausgewählt. Diese Belege bleiben erhalten, ersetzen aber **nicht** den neuen Export mit gemeinsamer Bundle-ID und gemeinsamen Produkten. [Build-Verifikation](../build-verification.md).

Apple erlaubt keine Zusammenführung bestehender App-Einträge. Die [Stilllegung des separaten Eintrags](https://developer.apple.com/help/app-store-connect/create-an-app-record/remove-an-app/) erfordert ausgeschaltete App-/IAP-Verfügbarkeit und einen zulässigen Status. Eine Entfernung gibt den Namen frei; Wiederherstellung ist nur bei weiterhin verfügbarem Namen möglich, die bereits für einen Upload verwendete alte Bundle-ID ist nicht wiederverwendbar. Die Stilllegung ist nach erfolgreicher gemeinsamer Vorbereitung abgeschlossen: alte App und zwei Produkte ausgeschaltet, drei alte Reviewitems entfernt, App `6820968413` aus dem Account entfernt. Apple bestätigt die Entfernung vom 9. Oktober 2026 und bietet „App wiederherstellen“ an. Die gemeinsamen Produkte und ihre Deutschland-Verfügbarkeit blieben unverändert. [Stilllegungsbericht](../../../artifacts/app-store/legacy-mac-retirement-applied-20261009.json), [tatsächliche Apple-Bestätigung](../../../artifacts/app-store/legacy-mac-removed-proof.jpg).

## Backend und öffentliche Seiten

Produktiver Zugangsdienst: `https://fototausch.eu/rudolf-steiner-ga`; Katalog: `https://fototausch.eu/ga-reader`. Migration, vertrauliche Speicherung, Löschfristen sowie sieben Tage verschlüsselte Sicherungen einschließlich Restore sind geprüft. Bericht: `server/deploy/deployment-20261009.md`.

[Datenschutztext](../privacy.de-DE.md), [Supporttext](../support.de-DE.md) und kanonische HTTPS-Seiten sind veröffentlicht und mit HTTP 200 / HTML bestätigt. Der Statistik-Endpunkt liefert HTTP 200 / JSON. Die Betriebsinventur enthält weiterhin die nicht technisch ableitbare Vertrags-/Hoster-Verifikation. Reale Sandbox-/TestFlight-Käufe, plattformübergreifende Wiederherstellung und iCloud-Synchronisierung sind trotz technischer Vorbereitung noch zu prüfen.
