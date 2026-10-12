# App-Zugang und RevenueCat

Stand: 9. Oktober 2026.

## Umgesetzte Produktentscheidungen

Alle Lesetexte, Downloads und EPUB-Exporte erfordern einen aktiven Zugang. Die Bibliothek kann ohne Zugang durchstöbert werden. Die fünf mitgelieferten Bücher sind offline enthalten, unterliegen aber derselben Zugangsprüfung wie heruntergeladene Texte.

Jahresabo und Förderabo haben identische Funktionen. Die deutschen Jahrespreise von 30 € und 90 € sind für die zwei gemeinsamen Apple-Produkte bestätigt, einschließlich drei Monaten kostenloser Einführung für berechtigte Accounts. iPhone, iPad und die native Mac-App verwenden jetzt die gemeinsame Bundle-ID `com.jonathankutscher.ga` und werden unter App-Eintrag `6820947669` vorbereitet. Die App zeigt ausschließlich den tatsächlich gelieferten lokalisierten App-Store-Preis und prüft, dass das Produkt ein jährlich verlängerndes Abo ist. Das Förderabo verspricht keine bestimmte Anzahl finanzierter Gratisjahre.

Die gewünschte „90-Tage-Probezeit“ wird als Apples **dreimonatiges Einführungsangebot** umgesetzt. Drei Kalendermonate sind nicht immer genau 90 Tage. Ein berechtigtes Apple-Konto sieht das tatsächliche kostenlose Angebot, den anschließend fälligen Jahrespreis und den Verlängerungshinweis. Beide Angebote liegen für alle Plattformen in derselben Abogruppe und auf derselben Stufe; ein Wechsel soll kein zweites paralleles Abo und keine zweite Probephase eröffnen. Apple bestimmt die Berechtigung. Die plattformübergreifende Wiederherstellung muss noch mit den gemeinsamen Produkten auf signierten Geräten geprüft werden.

Das kostenlose Jahr beginnt nach der erfolgreichen Speicherung einer nicht leeren Bitte sofort. Es umfasst zwölf Kalendermonate, endet ohne Zahlung und wird nie automatisch in ein Abo umgewandelt. Eine erneute Bitte ist jederzeit möglich. Während eines laufenden Gratisjahres gilt mindestens das bestehende Enddatum und sonst zwölf Monate ab der erneuten Bitte; die App stapelt keine zusätzlichen Jahre. Es werden weder Nachweise noch eine Einkommensgrenze verlangt.

## Apple-App

`AccessStore` prüft RevenueCats Berechtigung `ga_access`, beobachtet Kundenänderungen, stellt Käufe wieder her und prüft Ablaufdaten auch offline. Fehlgeschlagene Verifikation, Abbruch, ausstehende Freigabe und bestätigter Zugang werden unterschieden. Ein abgelaufener Zugang sperrt auch eine noch offene Lesesitzung. Suchergebnisse enthalten ohne Zugang keine Buchtextauszüge. Die Servermetadaten bleiben öffentlich; dies ist eine App-Zugangsschranke und kein DRM für die öffentlich ausgelieferten Bibliothekstexte. Ihre Inhaltsrechte sind gesondert in `docs/app-store/content-rights.md` dokumentiert.

`PurchaseScreen` zeigt die drei Optionen, echte Auswahlzahlen, Freitextanfrage, Wiederherstellung, Verwaltung, Datenschutzhinweise und Apples Standard-EULA. Die Bitte bleibt bei einem Übermittlungsfehler im Textfeld. Leere Bitten werden nicht abgesendet.

Die Serverkennung und Zugangstoken werden im gerätelokalen Schlüsselbund gespeichert. Die App veröffentlicht nur aggregierte Klickzahlen der letzten 90 Tage. Mehrfache bewusste Auswahlen sind einzelne Klicks; technische Wiederholungen derselben Ereignis-ID werden nur einmal gezählt. Auswahlklicks sind keine abgeschlossenen Käufe.

## Konfiguration

Siehe `apple/GA/Purchases.xcconfig` und optional die ignorierte Datei `Purchases.local.xcconfig`:

| Einstellung | Bedeutung |
| --- | --- |
| `GA_REVENUECAT_IOS_SDK_KEY` | Öffentlicher Apple-SDK-Schlüssel für die iOS-App |
| `GA_REVENUECAT_MAC_SDK_KEY` | Derselbe öffentliche Apple-SDK-Schlüssel wie auf iOS, für die gemeinsame Apple-App |
| `GA_ACCESS_BASE_URL` | HTTPS-Dienstpräfix des dynamischen Zugangsdiensts; die App ergänzt `/api/access` |
| `GA_SERVER_BASE_URL` | Optionaler unabhängiger Katalogdienst; Standard bleibt `https://fototausch.eu/ga-reader` |

Die Release-App benötigt einen richtigen `appl_`-Schlüssel. Ohne Konfiguration bleiben Kaufaktionen gesperrt; ein bestehender, gültiger Gratiszugang ist unabhängig davon nutzbar. Im Debug-Modus kann `GA_USE_LOCAL_STOREKIT=1` die mitgelieferte StoreKit-Konfiguration aktivieren. Die Freischaltung erfolgt dabei nur nach einem von StoreKit verifizierten Testkauf; es gibt keinen simulierten lokalen Gratiszugang.

Die Produktschlüssel lauten auf allen Plattformen `com.jonathankutscher.ga.annual` und `com.jonathankutscher.ga.supporter`. Beide hängen an RevenueCats `ga_access`; native Mac- und iOS-Targets verwenden dieselbe Apple-Verbindung und denselben öffentlichen SDK-Schlüssel. Die früheren separaten Mac-Produkte gehören zum historischen Eintrag und werden nicht mehr durch die Versandkonfiguration verwendet. Apples universeller Kauf wird erst nach Freigabe mindestens zweier Plattformversionen verfügbar; die technische Umstellung ist noch kein Nachweis eines echten plattformübergreifenden Kaufs.

## Kostenlosen Zugang wiederherstellen

Unter „Gratiszugang wiederherstellen“ kann der persönliche Code gesichert und auf einem neuen Gerät eingefügt werden. Der Code besteht aus Zugangs-ID und einem zufälligen Geheimnis. Bei Wiederherstellung wird das alte Server-Zugangstoken ungültig. Auf dem bisherigen Gerät ist bei der nächsten Serverprüfung eine erneute Wiederherstellung nötig. Es handelt sich nicht um eine automatische Kontosynchronisierung.

„Zugangsdaten löschen“ entfernt Gratiszugang, Anfragen und zugeordnete Klickereignisse auf dem Server sowie lokale Zugangskennungen. Apple-Abos werden dadurch nicht gekündigt. Bücher und persönliche Lesedaten bleiben erhalten. Bereits gesicherte Offline-Zugänge auf anderen Geräten können bis zur nächsten erfolgreichen Serverprüfung oder ihrem Ablauf weiter gültig sein.

## Backend und Veröffentlichung

Migrationen, vertrauliche Speicherung, API und Aufbewahrung sind in `server/README.md` dokumentiert. Ein Postgres-Repository und ein gesonderter AES-Schlüssel sind erforderlich. Katalogbetrieb mit `GA_SKIP_REPO=true` stellt keine Gratiszugänge aus.

Der bisherige Produktionskatalog ist eine statische JSON-Auslieferung. Er kann keine Bitten speichern. Der dynamische Zugangsdienst wurde am 9. Oktober 2026 unter `https://fototausch.eu/rudolf-steiner-ga` bereitgestellt und über HTTPS geprüft. `GA_ACCESS_BASE_URL` verwendet diesen separaten Dienst. Er läuft auf derselben Maschine in einem eigenen Dienst und einer eigenen Datenbank; die statische Bibliothek bleibt separat.

Öffentliche Datenschutzerklärung und Supportseite, CloudKit-Produktionsschema, Apple-/RevenueCat-Produkte sowie ein signiertes Archiv sind eigenständige Veröffentlichungsvoraussetzungen. Die App-Store-Dateien unter `docs/app-store` enthalten Texte, Screenshots und den aktuellen Prüfstand.

Die öffentliche App-Seite ist unter [fototausch.eu/rudolf-steiner-ga](https://fototausch.eu/rudolf-steiner-ga/) erreichbar. Datenschutz und Hilfe liegen darunter als `privacy.html` und `support.html`.
