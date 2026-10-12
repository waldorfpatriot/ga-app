# App-Store-Freigabe

Stand: 9. Oktober 2026. Ein gemeinsamer Apple-Eintrag für iPhone, iPad und native Mac-App ist technisch vorbereitet: `6820947669`, Bundle-ID `com.jonathankutscher.ga`, eine Gruppe und zwei gemeinsame Abos. Beide Plattformen verwenden bestätigte, ausgewählte Builds 3 mit gemeinsamer Kaufkonfiguration und expliziter CloudKit-Laufzeitkennung. Alte getrennte Build-2-/Mac-Belege bleiben erhalten; sie bestätigen den neuen gemeinsamen Versandstand nicht. Datenschutzattest, belegbare Inhaltsrechte und echter Sandbox-/TestFlight-Kaufdurchlauf bleiben offen. Keine App-Prüfung oder Veröffentlichung wurde ausgelöst.

## Verbindliches Zugangsmodell

- Lesen, Textdownloads und EPUB-Export benötigen aktiven App-Zugang. Der Katalog kann zur Orientierung sichtbar bleiben.
- Jahresabo: bestätigter Apple-Preispunkt 30 € in Deutschland, Laufzeit ein Jahr, automatische Verlängerung.
- Förderabo: bestätigter Apple-Preispunkt 90 € in Deutschland, Laufzeit ein Jahr, automatische Verlängerung. Gleiche Funktionen; der Mehrbeitrag unterstützt kostenlose Zugänge.
- Apple-Einführungsangebot: drei Kalendermonate kostenlos, nur bei tatsächlich bestätigter Berechtigung. Anschließend berechnet Apple den Preis des gewählten Jahresabos. Kein vom Backend erteilter Testzugang. „90 Tage“ ist keine präzise Laufzeitangabe für dieses Apple-Angebot.
- Kostenloses Jahr: Jede nicht leere kurze Bitte erteilt sofort zwölf Kalendermonate Zugang. Keine Zahlung, kein Einkommensnachweis, keine automatische Verlängerung mit Zahlung. Weitere Bitten sind jederzeit möglich; sie setzen das Ende auf den späteren Zeitpunkt aus bisherigem Ende und zwölf Monaten ab der neuen Bitte. Jahre werden nicht aufgestapelt.
- Gleicher Zugang bedeutet gleicher Funktionsumfang. Zum aktuellen Stand sind 324 von 463 Katalogeinträgen als Text verfügbar; 139 Einträge sind noch nicht verfügbar.

## Apple und RevenueCat konfigurieren

1. Gemeinsamen App-Eintrag `6820947669` verwenden. Der neue `MAC_OS`-Plattformentwurf gehört zu derselben App und Bundle-ID `com.jonathankutscher.ga`. Native Mac-App neu signieren und hochladen; die alte separate App `6820968413` lässt sich nicht zusammenführen. [Apples universeller Kauf](https://developer.apple.com/help/app-store-connect/create-an-app-record/add-platforms) wird erst nach Freigabe mindestens zweier Plattformversionen verfügbar.
2. Vorhandene gemeinsame Gruppe `22458743` und genau zwei Produkte verwenden: `com.jonathankutscher.ga.annual` / `.supporter`, Apple-IDs `6820967918` / `6820968113`, beide `groupLevel=1`, `ONE_YEAR`. Deutsche Lokalisierungen und exakt 30,00 € / 90,00 € sind bestätigt. Beide besitzen Apples 175 erforderliche UPFRONT-Preise; nur Deutschland ist verfügbar und neue Territorien sind ausgeschaltet. Keine zweite Mac-Gruppe oder zusätzlichen Mac-Produkte anlegen.
3. Beide gemeinsamen Produkte haben drei Kalendermonate FREE_TRIAL, Beginn 9. Oktober 2026 ohne festes Enddatum. Apple bestimmt die Berechtigung pro Account und Gruppe. Die kostenlose Backend-Bitte ist kein Apple-Kaufprodukt und erhält kein Einführungsangebot.
4. Die zwei gemeinsamen Abo-Reviewbilder und Hinweise sind bereits COMPLETE und mit Originalprüfsummen bestätigt. Die ursprünglichen separaten Mac-Reviewbilder bleiben historische Belege. Gruppe und zwei Produkte verbleiben als drei Items im iOS-Reviewentwurf `935ba689-4148-4cfd-a308-58b5fd47edcf`; der gemeinsame Mac-Entwurf `63883c48-e34e-4bd2-9148-a8b5200a3203` ist angelegt und noch leer. Beide bleiben READY_FOR_REVIEW, submittedDate=null; Mac erhält ausschließlich seine App-Version. Beide endgültigen Builds 3 sind nach bestätigter Verarbeitung in den gemeinsamen Plattform-Entwürfen ausgewählt. Apples tatsächliche App-Validierung blockiert beide App-Elemente ausschließlich durch fehlende contentRightsDeclaration und APP_DATA_USAGES_REQUIRED; veröffentlichte Datenschutzantworten und belegbare Inhaltsrechte bleiben erforderlich. [Aktueller Validierungsbericht](../../artifacts/app-store/universal-private-review-drafts-20261009.json). **Nicht endgültig übermitteln**, solange diese Voraussetzungen und der echte Kaufdurchlauf fehlen.
5. Bestehendes Geschäftskonto: kostenlose/gebührenpflichtige Verträge und beide Steuerformulare Active, DSA Active, DAC7 Activated. Ein Bankkonto ist vorhanden; kein separater Bankstatus wird behauptet. Keine neuen Verträge oder Änderungen von Konto-/Steuerdaten vorgenommen.
6. RevenueCat-Projekt `Gesamtausgabe` (`34fd17d0`), gemeinsame Apple-Verbindung `app64fd68fa61`, Entitlement `ga_access`, Offering `default` mit `$rc_annual` / `supporter` wiederverwenden. Beide Targets laden dieselben zwei Apple-Produkte. Alte getrennte Mac-Verbindung und Produkte erst nach bestätigter Umstellung stilllegen.
7. Beide öffentlichen SDK-Konfigurationswerte verwenden denselben gültigen `appl_`-Schlüssel der gemeinsamen Apple-App. Fehlende oder `test_`-Schlüssel blockieren den Releasezustand. Secret-Keys niemals in die App übernehmen. Der identische öffentliche Schlüssel in den tatsächlichen Build-3-Exporten ist geprüft; beide Targets verwenden die zwei gemeinsamen Produktkennungen.
8. Die gemeinsame RevenueCat-Verbindung bestätigt gültige vorhandene ASC-/IAP-Credentials. Production- und Sandbox-Notifications V2 zu RevenueCat sind im gemeinsamen Apple-Eintrag bestätigt; null aktive Drittintegrationen. Kauf auf iOS und Wiederherstellung auf Mac sowie die umgekehrte Richtung mit demselben Apple-Account testen.

Aktueller Abgleich: [Einrichtungsstand](publishing/setup-state.md). Apple dokumentiert [Abogruppen und erste Abos](https://developer.apple.com/help/app-store-connect/manage-subscriptions/offer-auto-renewable-subscriptions/); RevenueCat beschreibt [Apple-Produkte](https://www.revenuecat.com/docs/getting-started/entitlements/ios-products), [Entitlements](https://www.revenuecat.com/docs/getting-started/entitlements) und [SDK-Konfiguration](https://www.revenuecat.com/docs/getting-started/configuring-sdk).

## Produktives Backend

Der dynamische Zugangsdienst wurde am 9. Oktober 2026 unter `https://fototausch.eu/rudolf-steiner-ga` bereitgestellt und über HTTPS geprüft. Installationsanlage, inaktiver Anfangszustand, Gratisjahr, wiederholte Anfrage, Status, Wiederherstellung, Klickstatistik und Löschung wurden erfolgreich geprüft; Testdaten sind entfernt. Der statische Katalog bleibt separat unter `https://fototausch.eu/ga-reader`. Der Bereitstellungsbericht steht in `server/deploy/deployment-20261009.md`.

- Phoenix mit PostgreSQL und den neuen Migrationen betreiben; `GA_SKIP_REPO=true` ist für den Zugangsdienst ungeeignet.
- `GA_ACCESS_ENCRYPTION_KEY` als Base64-kodierten geheimen Schlüssel mit exakt 32 Bytes bereitstellen. Sicher aufbewahren, sichern und bei Schlüsselwechsel vorhandene verschlüsselte Nachrichten berücksichtigen. Keine unsichere Standardbelegung verwenden.
- `GA_ACCESS_BASE_URL=https://fototausch.eu/rudolf-steiner-ga` konfigurieren. `GA_SERVER_BASE_URL` betrifft unabhängig davon den Katalog. Bearer-Tokens dürfen nicht durch Host-Weiterleitungen gesendet werden.
- Installationsanlage, kostenlosen Antrag, Status, Wiederherstellung, Auswahlklicks, aggregierte Statistik und authentifizierte Löschung gegen den Produktionsdienst prüfen. Fehlende Datenbank oder fehlender Verschlüsselungsschlüssel ergeben einen Fehlerzustand und erteilen keinen Zugang.
- Verschlüsselte Freitexte werden nach 30 Tagen durch den stündlichen Aufbewahrungsdienst gelöscht; gewöhnlich innerhalb einer zusätzlichen Stunde, während der Dienst läuft. Auswahlereignisse werden nach 90 Tagen entfernt. Verschlüsselte tägliche Backups sind eingerichtet und werden nach höchstens sieben Tagen entfernt; Restore wurde geprüft. Nginx hält 14 tägliche Rotationen plus aktuelles Tagesprotokoll. Technische Dienstprotokolle sind speicherbegrenzt, nicht auf eine feste Tagesfrist begrenzt. Minimale Zugangsmetadaten bleiben bis zur Installationslöschung.
- Wiederherstellungscodes nicht in Logs schreiben. Anfragetexte, Bearer-Tokens und Wiederherstellungscodes aus HTTP- und Fehlerprotokollen fernhalten. Zugriff auf Datenbank und Schlüssel auf erforderliche Dienste und Betreiber beschränken.

## Datenschutz, Support und Metadaten

- Die öffentliche Fassung `privacy.de-DE.md` und die Betriebsinventur mit den tatsächlich geltenden Hosting- und RevenueCat-Verträgen abgleichen. Der Text beschreibt den bestätigten Datenfluss; er ist keine juristische Garantie.
- Datenschutz und Support als öffentlich erreichbare HTTPS-Seiten veröffentlichen. URLs in App-Store-Connect und der App setzen und auf einem realen Gerät öffnen. Die kanonischen URLs `https://fototausch.eu/rudolf-steiner-ga/privacy.html` und `https://fototausch.eu/rudolf-steiner-ga/support.html` sind veröffentlicht und mit HTTP 200 bestätigt; auf realem Gerät öffnen.
- Alle fünf Datentypen mit Zwecken, Benutzerverknüpfung und ohne Tracking sind im gemeinsamen Apple-App-Eintrag vollständig gespeichert; `privacy-inventory.md` enthält die genauen Antworten und Betriebsbelege. Die tatsächlichen Exporte der neuen Builds 3 enthalten zwei Manifeste und die fünf passend abgeglichenen eigenen Datenschutzkategorien. Das abschließende Apple-Datenschutzattest ist noch nicht veröffentlicht und verlangt ausdrückliche Zustimmung zu dem konkreten Rechtsattest. „Keine Daten erfasst“ trifft nicht zu.
- Inhaltsrechte sind noch nicht erklärt. Die Ja-Auswahl bestätigt ausdrücklich vorhandene erforderliche Rechte an Drittinhalten. Die begrenzte Prüfung fand tatsächlich erhaltenes modernes Herausgeber-/Verlagsmaterial; die Gemeinfreiheit von Steiners eigenen Originaltexten allein belegt nicht die Rechte an allen ausgelieferten Bestandteilen. [Konkrete Payload-Fundstellen und offene Berechtigungsnachweise](content-rights.md), [tatsächlicher Apple-Dialog](publishing/apple-content-rights-approval-proof.jpg). Keine falsche Nein-Antwort oder ungesicherte pauschale Ja-Erklärung abgeben.
- Die App muss Datenschutz und Nutzungsbedingungen direkt zugänglich machen. Die [Apple-Standardlizenz](https://www.apple.com/legal/internet-services/itunes/dev/stdeula/) steht bereits in der Beschreibung; eine eigene EULA ist hier nicht vorbereitet.
- Die deutsche Beschreibung mit exakt 4000 Zeichen und 26 verfügbaren GA-Titeln sowie der Werbetext mit 145 Zeichen sind in beiden gemeinsamen Lokalisierungen gespeichert und exakt zurückgelesen. Namen, Keywords, Kontakt, Aboangaben und die unabhängige Ausgabe sind vorbereitet; [Textabgleich](../../artifacts/app-store/universal-copy-refresh-20261009.json).
- Alle 28 Marketingbilder sind bei Apple COMPLETE mit Original-MD5 und Reihenfolge: acht je mobiler Größenklasse, vier für Mac. Sechs Kaufbilder wurden aus der öffentlichen Galerie entfernt; die beiden gemeinsamen Abo-Reviewbilder und lokalen Kauforiginale bleiben unverändert. [Abschließender Screenshot-Abgleich](../../artifacts/app-store/marketing-screenshot-refresh-20261009.json).
- Alterseinstufung ist nach Sichtung aller 324 Texte gespeichert und erneut aus Apple gelesen: Deutschland **18+**, älteres API-Feld 17+. Begründung: `age-rating.de-DE.md`. Historische weltanschauliche Texte können problematische zeitgenössische Aussagen enthalten. Keine medizinische Anwendung oder Wirksamkeit versprechen.
- Export-Compliance anhand der signierten Pakete bestätigt: Apple verarbeitet beide Builds erfolgreich; `usesNonExemptEncryption=false` ist gespeichert. Bei späteren Änderungen an eigener Verschlüsselung erneut prüfen.

Apple verlangt zugängliche Datenschutzinformationen und vollständige Funktionsangaben: [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/). Die Dateninventur ist Grundlage der [App-Privacy-Angaben](https://developer.apple.com/app-store/app-privacy-details/).

## Signieren und Archive prüfen

- Beide signierten Build-3-Exporte sind streng geprüft, offiziell validiert und erfolgreich privat hochgeladen. Gemeinsame Bundle-ID, identischer öffentlicher SDK-Schlüssel, fünf Datenschutzkategorien und fehlende lokale StoreKit-Testdatei sind im tatsächlichen Paket bestätigt. iOS-Build `7f0ab926-cd37-4cf0-b635-082ebbbf955b` und Mac-Build `dc3f136c-e114-497b-bc50-481b34e199ce` sind VALID / APP_STORE_ELIGIBLE und jeweils mit MANUAL ausgewählt. Beide bestätigen `usesNonExemptEncryption=false`.
- `GACloudKitContainerIdentifier=iCloud.com.jonathankutscher.ga` ist in beiden exportierten Build-3-Info.plists bestätigt. Dieser Wert fehlte in beiden alten Build-2-Paketen trotz CloudKit-Entitlements; die neue Quellkonfiguration ergänzt ihn. Der gemeinsame Mac-Export trägt das passende Profil GA Universal Mac App Store 2026-10-09 CloudKit und bestätigt Production-Container sowie Sandbox-Entitlements. Das alte Profil `9UA4W4S5JQ` gehört zur separaten ID.
- Historische Pakete unter `artifacts/app-store/ios/build-2/` und `artifacts/app-store/mac/build-2/` bleiben Prüfbelege der früheren Einrichtung. Ihre erfolgreiche Validierung/Verarbeitung ersetzt den neuen gemeinsamen Export nicht; siehe [Build-Verifikation](build-verification.md).
- Mac App Sandbox und ausgehende Netzwerkverbindungen aktivieren; CloudKit-Container in beiden Targets erhalten. Tatsächliche Entitlements im signierten Archiv prüfen.
- CloudKit `GAReadingState` mit `payload` (`Asset`) und `schemaVersion` (`Int64`) in `iCloud.com.jonathankutscher.ga` ist nach Production deployed und sichtbar erneut bestätigt. Beleg: `publishing/apple-cloudkit-production-proof.jpg`.
- `PrivacyInfo.xcprivacy` in beiden Apps und das eingebundene RevenueCat-Manifest im Archiv prüfen. Eigene AppStorage-Nutzung verlangt `NSPrivacyAccessedAPICategoryUserDefaults` mit `CA92.1` für die eigenen Einstellungen. SDK-Manifeste ersetzen den App-Eintrag nicht.
- App-Icon, Marketingversion, steigende Buildnummer, unterstützte Orientierungen und Mindestversion 26 prüfen. Mac-Primärkategorie mit der Xcode-Kategorie abstimmen.
- Xcode-Archivvalidierung und TestFlight-Installation durchführen. Erfolgreiche unsignierte Simulatorbuilds ersetzen diesen Schritt nicht.

Apple erläutert Manifestangaben unter [Describing use of required reason API](https://developer.apple.com/documentation/bundleresources/describing-use-of-required-reason-api).

## Endgültiger Durchlauf auf TestFlight

Für lokale StoreKit-Tests ausdrücklich die Schemes **GA iOS StoreKit QA** beziehungsweise **GA Mac StoreKit QA** verwenden. Sie setzen `GA_USE_LOCAL_STOREKIT=1` und verwenden `GA.storekit`. Die normalen Schemes **GA iOS** und **GA Mac** prüfen die echte RevenueCat-Konfiguration. Lokale Testpreise und verifizierte lokale StoreKit-Käufe belegen keine Kaufbarkeit der Produkte in Apple Sandbox oder Produktion; nach Apple-Einrichtung den folgenden Durchlauf mit den normalen Schemes auf TestFlight wiederholen.

| Prüffall | Erwartetes Ergebnis |
| --- | --- |
| Frische Installation | Kein automatisch erteilter Server-Testzugang; Lesen führt zur Beitragsauswahl. |
| Apple-Angebot, berechtigter Account | Drei Monate kostenlos und danach gewählter Jahrespreis; aktive Entitlement-Bestätigung entsperrt Lesen. |
| Apple-Angebot, nicht berechtigter Account | Keine versprochene Testphase; regulärer Jahrespreis. |
| Kaufabbruch, Fehler oder ausstehender Kauf | Kein neuer Zugang; verständliche Rückmeldung, Wiederholung möglich. |
| Reguläres Abo und Förderabo | Beide entsperren dieselben Funktionen; keine doppelte Berechnung zweier Varianten innerhalb einer Gruppe. |
| Kündigung, Ablauf, Rückerstattung | Status aktualisiert; keine falsche erneute Kaufaufforderung bei weiter gültigem Zeitraum. |
| Kaufen und Wiederherstellen über Plattformen | Kauf auf iOS entsperrt nach Wiederherstellung Mac und umgekehrt; gemeinsames Apple-Produkt, keine zweite Berechnung und keine zweite Probephase. Neuinstallation prüfen. |
| Kostenlose Bitte | Leere Bitte blockiert; klare Bitte speichert und erteilt unmittelbar zwölf Monate. |
| Doppelte Anfrage nach Netzfehler | Gleiche Anfrage-ID erteilt keine zusätzlichen Jahre; Text bleibt bei Fehler erhalten. |
| Erneute Bitte bei aktivem Gratisjahr | Enddatum niemals verkürzt; kein Aufstapeln von Jahren. |
| Wiederherstellungscode auf zweitem Gerät | Zugang und korrekte Laufzeit erhalten; ursprüngliches Gerät erneut prüfen, da Tokenrotation relevant ist. |
| Backend ohne Netz, Datenbank oder Schlüssel | Kein erfundener Zugang; vorhandener gültiger Cache funktioniert bis zum belegten Ende. |
| Offline und abgelaufener Zugang | Heruntergeladene Werke nur mit noch aktivem Zugang lesbar. |
| Zugangsdaten löschen | Zugehörige Bitten, Klickdaten und kostenlose Freischaltung gelöscht; bezahltes Apple-Abo bleibt separat kündbar. |
| iCloud auf zwei signierten Geräten | Lesepositionen, Markierungen, Notizen und Sammlungen synchronisieren; ohne iCloud lokal nutzbar. |
| Große Schrift, VoiceOver, kleine Anzeige | Alle Preise, Laufzeiten, Bittenformular und rechtlichen Links erreichbar und verständlich. |
| Screenshots | Tatsächliche App, deutscher Text, richtige Größen, keine Transparenz oder echten persönlichen Daten. |

Erst nach diesen Schritten kann das signierte Paket zur Prüfung eingereicht werden. Die Vorbereitung und RevenueCat-Einrichtung haben keine App-Store-Einreichung oder Veröffentlichung ausgelöst.
