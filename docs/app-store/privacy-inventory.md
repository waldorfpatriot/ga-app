# Datenschutz-Inventur für den Release

Stand: 11. Oktober 2026. Grundlage: `apple/GA/ReadingStore.swift`, `AccessClient.swift`, `AccessStore.swift`, `PurchaseScreen.swift`, `ReaderTextReportSheet.swift`, `ReaderView.swift` sowie `server/lib/ga_server/access`. Die Angaben beschreiben den implementierten Datenfluss für den gemeinsamen Apple-App-Eintrag **`6820947669`** für iPhone, iPad und native Mac-App. iOS/iPadOS 1.0 mit Build 3 ist bereits freigegeben und veröffentlicht; die ursprüngliche Mac-Version 1.0 mit Build 3 wartet bei der Statusprüfung vom 11. Oktober auf Review. Frühere Angaben zu ausschließlich privaten Entwürfen und noch unveröffentlichten Datenschutzantworten beschreiben die Vorbereitung vom 9. Oktober, nicht den aktuellen Veröffentlichungsstand.

Die fünf bisherigen Datenschutzkategorien sind für den gemeinsamen Eintrag gespeichert. Build 4 ergänzt im eigenen Manifest **Customer Support** als sechste Kategorie für freiwillige Textfehlermeldungen. Die entsprechende App-Store-Connect-Antwort **App Functionality, mit dem Benutzer verknüpft: Ja, Tracking: Nein** muss vor der erneuten Einreichung noch ergänzt und veröffentlicht werden; eine erfolgte Änderung oder Einreichung wird hier nicht behauptet. Die früher zusätzlich gespeicherten Antworten im separaten Mac-Eintrag bleiben historische Belege.

| Daten | Ort / Empfänger | Zweck | App-Store-Kategorie / Zwecke |
| --- | --- | --- | --- |
| Zufällige Installations-ID, RevenueCat-App-User-ID | Zugangsdatenbank, RevenueCat; Schlüsselbund auf dem Gerät | Zugang zuordnen und wiederherstellen | User ID; App Functionality und Analytics |
| Kaufhistorie, Produkt, Status und Ende des Abos | Apple und RevenueCat; SDK-Cache auf dem Gerät | Kauf prüfen, freischalten, wiederherstellen, RevenueCat-Auswertung | Purchase History; App Functionality und Analytics |
| Freitextbitte | Eigener PostgreSQL-Server, AES-256-GCM verschlüsselt | Ausdrücklich angefragtes Gratisjahr erteilen | Other User Content; App Functionality |
| Anfrage-ID, Eingang, Gratiszeitraum | Eigener PostgreSQL-Server | Doppelverarbeitung verhindern, Laufzeit belegen | Zusammen mit User ID / Other User Content; App Functionality |
| Ausdrücklich gemeldete Textstelle, Buch- und Abschnittskennung, optional Abschnittstitel, UTF-16-Auswahlpositionen und Beschreibung, Plattform, App-Version und Buildnummer | Eigener PostgreSQL-Server; gesamter Meldungsinhalt AES-256-GCM verschlüsselt | Freiwillig gemeldeten Textfehler bearbeiten und Bibliothek korrigieren | Customer Support; App Functionality; in ASC noch zu ergänzen |
| Zufällige Meldungs-ID, Installationszuordnung, Eingang, Löschzeitpunkt und HMAC-Prüfwert | Eigener PostgreSQL-Server | Technische Wiederholungen erkennen und Doppelmeldungen verhindern, auch nach Inhaltslöschung | User ID / Customer Support; App Functionality |
| Auswahlklick, Ereignis-ID, Option und Zeit | Eigener Server, zu Installations-ID gehörend; öffentlich nur Summen | Verteilung der Auswahlklicks für 90 Tage anzeigen | Product Interaction; Analytics und App Functionality |
| Lesepositionen, Lesestatus, Markierungen, Notizen, Sammlungen | Lokal; bei verfügbarem iCloud-Account Apples private CloudKit-Datenbank | Persönliches Lesen und Synchronisation | Geräteinterne Daten sind keine Sammlung im Apple-Fragebogen; private CloudKit-Synchronisation ohne Zugriff des App-Betreibers. Nur bei ausdrücklich abgesendeter Fehlermeldung erhält der eigene Dienst die ausgewählte Textstelle und deren Fundstelle, nicht die übrigen persönlichen Lesedaten. |
| Verbindung/IP, HTTP-Fehler, Hosting-Protokolle | Produktionshost und Reverse Proxy | Betrieb und Sicherheit | Other Diagnostic Data; App Functionality |

Die fünf bisherigen Kategorien sind im gemeinsamen Eintrag für beide Plattformen gespeichert: **mit dem Benutzer verknüpft**, **kein Tracking**. Dieselben Antworten gelten für die noch in ASC zu ergänzende Kategorie Customer Support. Die Verknüpfung berücksichtigt Installationskennung, Bitte, Fehlermeldung, Zugang und Verbindung/IP; die zufällige Installationskennung ist pseudonym und keine Anonymisierung. Die App verlangt weder Namen noch E-Mail-Adresse für Gratiszugang oder Textfehlermeldung. Fehlermeldungen werden nicht veröffentlicht oder an RevenueCat gesendet. Kein Kontaktattribut an RevenueCat senden. Zahlungskartendaten erhält die App nicht.

RevenueCat verlangt für Kaufhistorie die Zwecke App Functionality und Analytics und erläutert Kennungen und Identitätsverknüpfung unter [Apple App Privacy](https://www.revenuecat.com/docs/platform-resources/apple-platform-resources/apple-app-privacy). Apple erklärt Freitextfelder, CloudKit, rein lokale Daten und das Erfassen von Daten unter [App Privacy Details](https://developer.apple.com/app-store/app-privacy-details/). Die kostenlose Bitte bleibt Other User Content als Teil des Zugangsmodells. Freiwillige Textfehlermeldungen sind Customer Support. Die Ausnahme für gelegentliche Supportmeldungen wird nicht beansprucht: Das Meldungsformular zeigt keinen Namen oder Accountnamen prominent neben den übermittelten Daten an, wie Apple es für diese Ausnahme verlangt.

## Freiwillige Textfehlermeldungen

Nach einer Textauswahl öffnet „Fehler melden …“ im Kontextmenü ein Formular mit der ausgewählten Textstelle, deren Fundstelle und einer optionalen Beschreibung. Erst „Senden“ übermittelt die Meldung. Abbrechen sendet nichts. Die Meldungsfunktion benötigt eine authentifizierte zufällige Installation, aber weder ein bezahltes Abo noch einen aktiven Gratiszugang; der bestehende Zugangsschutz des Lesebildschirms bleibt davon getrennt. Der Server prüft keine Kaufberechtigung für Meldungen. Es werden keine anderen Markierungen oder Notizen mitgesendet.

`POST /api/access/text-reports` speichert den gesamten Meldungsinhalt verschlüsselt. Eine unveränderte Wiederholung derselben Meldungs-ID wird bestätigt, ohne eine zweite Meldung zu erzeugen. Eine geänderte Beschreibung erhält im App-Formular eine neue Meldungs-ID. Nach einer unbestätigten Übertragung bleibt die Eingabe für einen erneuten Versuch erhalten. Es gibt kein HTTP-Leseendpoint für Meldungen; befugte Betreiber können erhaltene Inhalte über `GA.Access.TextReports.list_for_operator/2` im geschützten Serverkontext lesen.

## Konkrete Aufbewahrung

- Kurzlebige geschützte Betreiberkopien von Textmeldungen: stündliche Bereinigung nach 23 Stunden, bei laufenden Jobs spätestens innerhalb von 24 Stunden; Lesen verlängert die Frist nicht.

- Verschlüsselte Bitten: nach 30 Tagen Entfernung des Nachrichteninhalts; stündlicher Dienst, gewöhnlich bis zu eine zusätzliche Stunde bei laufendem Server. Kein öffentliches oder administratives HTTP-Leseendpoint für Nachrichten.
- Verschlüsselte Textfehlermeldungen: nach 180 Tagen Entfernung des gesamten Meldungsinhalts einschließlich Textstelle, Beschreibung, Fundstelle und App-Metadaten; stündlicher Dienst, gewöhnlich bis zu eine zusätzliche Stunde bei laufendem Server. Installations- und Meldungs-ID, Eingang, Löschzeitpunkt und ein mit geheimem Schlüssel erzeugter HMAC-Prüfwert bleiben bis zur Installationslöschung erhalten. Eine spätere technische Wiederholung stellt bereits gelöschten Text nicht wieder her.
- Auswahlereignisse: 90 Tage; technische Wiederholung mit gleicher Ereignis-ID erhöht die Zahl nicht. Mehrere echte Klicks bleiben mehrere Auswahlklicks, keine eindeutigen Personen oder Käufe.
- Minimale Anfrage-, Meldungs- und Zugangsmetadaten: bis authentifizierte Installationslöschung. Kein automatisches Ende dieser Metadaten-Aufbewahrung implementiert.
- Bearer- und Wiederherstellungsgeheimnisse: serverseitig nur Hashes, geräteseitig im nicht synchronisierenden Schlüsselbund. Ein Wiederherstellungscode ist ein Zugangsgeheimnis und gehört nicht in Logs oder Screenshots.
- Löschung im Kaufbildschirm: eigene Gratiszugangsdaten, Bitten, Fehlermeldungen einschließlich Empfangsmetadaten und Klickdaten. Der Datenbank-Fremdschlüssel löscht Meldungen zusammen mit der Installation. Sie kündigt kein Apple-Abo und löscht noch keine RevenueCat-Kaufhistorie, persönliche Lesedaten oder CloudKit-Einträge.
- Tägliche eigene Backups: verschlüsselt, root-only, höchstens sieben tägliche Sicherungen und Löschung älterer Sicherungen beim täglichen Lauf; Restore geprüft. Gelöschter Live-Nachrichteninhalt kann bis sieben Tage länger in Backups vorhanden sein, bei laufenden Jobs insgesamt bis 37 Tage für Bitten und bis 187 Tage für Textfehlermeldungen, jeweils zuzüglich des möglichen stündlichen Löschlaufversatzes. Nginx: 14 tägliche Rotationen plus aktueller Tag, IP/HTTP-Pfad/Status, keine Bodies oder Authorization. Phoenix-Parameterlogging deaktiviert; Nachricht, Meldungsinhalt und Geheimnisse gefiltert; Journald speicherbegrenzt ohne feste Tagesfrist. RevenueCat-Aufbewahrung und Löschprozess separat prüfen.

## Apple-Antworten und verbleibende Ergänzung

| Apple-Datentyp | Zwecke | Mit Benutzer verknüpft | Tracking | ASC-Stand |
| --- | --- | --- | --- | --- |
| Other User Content | App Functionality | Ja | Nein | Bisherige Antwort gespeichert |
| User ID | App Functionality, Analytics | Ja | Nein | Bisherige Antwort gespeichert |
| Purchase History | App Functionality, Analytics | Ja | Nein | Bisherige Antwort gespeichert |
| Product Interaction | App Functionality, Analytics | Ja | Nein | Bisherige Antwort gespeichert |
| Other Diagnostic Data | App Functionality | Ja | Nein | Bisherige Antwort gespeichert |
| Customer Support | App Functionality | Ja | Nein | Für Build 4 noch ergänzen und veröffentlichen |

User-ID-Auswertung umfasst die RevenueCat-Aboübersicht und installationsbezogene Auswahlstatistik. Produktinteraktion dient auch der in der App sichtbaren Beitragsstatistik. Sonstige Diagnosedaten beziehen sich auf tatsächlich aufbewahrte IP-/Pfad-/Status- und technische Fehlerprotokolle für Sicherheit und Serververfügbarkeit; eine zusätzliche App-Absturzsammlung wird damit nicht behauptet.

## Tracking und Manifest

Im geprüften App-Code gibt es keine Werbung, IDFA-Erfassung oder weiteren externen Analyse-SDKs. Das RevenueCat-Dashboard bestätigt **null aktive Integrationen**; es wurden keine zusätzlichen Personenattribute eingerichtet. Die gespeicherten Tracking-Antworten sind deshalb Nein. Diese Aussage gilt für die geprüfte Konfiguration; bei späteren Werbe-/Datenintegrationen müssen Antworten und Manifest neu geprüft werden. Beleg: `publishing/revenuecat-integrations-proof.jpg`. „Data Not Collected“ ist mit Kaufhistorie und Zugangsdienst nicht zutreffend.

Die App nutzt `@AppStorage` für eigene Einstellungen: Manifestgrund `NSPrivacyAccessedAPICategoryUserDefaults` / `CA92.1`. Keine direkten Dateizeit-, Systemlaufzeit- oder Speicherplatz-Abfragen wurden im gelesenen App-Code gefunden. RevenueCats eigenes Manifest muss mit dem SDK ins Archiv gelangen; dessen Bericht ersetzt nicht das eigene App-Manifest.

Das eigene Manifest für Build 4 enthält die sechs oben aufgeführten Kategorien, einschließlich `NSPrivacyCollectedDataTypeCustomerSupport` mit `NSPrivacyCollectedDataTypePurposeAppFunctionality`, verknüpft Ja und Tracking Nein. Die bisherigen Build-3-Exporte enthielten fünf Kategorien. Die Erweiterung des lokalen Manifests ändert die ASC-Datenschutzantworten nicht automatisch; Customer Support muss dort separat ergänzt und veröffentlicht werden.

## Noch zu vervollständigen

Produktionshoster und Verarbeitungsort, tatsächlich geltende Vereinbarungen zur Auftragsverarbeitung, Übermittlungsmechanismen in Drittländer sowie Löschprozess bei RevenueCat. Diese Vertragsfakten lassen sich nicht aus einer technischen Bereitstellung oder einem gültigen API-Schlüssel ableiten. Die private CloudKit-Datenbank und Gerätespeicherung sind von der eigenen Zugangsdatenbank getrennt; die UI muss den Umfang der jeweiligen Löschaktion erklären.
