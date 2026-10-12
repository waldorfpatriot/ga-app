# App-Store-Vorbereitung

Ziel ist ein gemeinsamer Apple-Eintrag **`6820947669`** für iPhone, iPad und Mac, Bundle-ID **`com.jonathankutscher.ga`**. Die Werkzeuge verwenden zwei gemeinsame Jahresabos und eine Gruppe. Der separate Mac-Eintrag `6820968413` wurde nach erfolgreicher gemeinsamer Vorbereitung aus dem Account entfernt; Apple bietet Wiederherstellung an. Seine App und zwei Produkte sind nicht mehr verfügbar, sein früherer Reviewentwurf ist leer. [Bestätigter Stilllegungsbericht](../../../artifacts/app-store/legacy-mac-retirement-applied-20261009.json). Alte Builds, Produkte und Uploadberichte bleiben historische Belege.

Ohne `--apply` verwenden die Werkzeuge ausschließlich GET-Anfragen. Sie laden keine Builds hoch und übermitteln keine endgültige App-Prüfung. [Aktueller Einrichtungsstand](setup-state.md), [Release-Voraussetzungen](../release-checklist.md).

| Werkzeug | Aufgabe |
| --- | --- |
| `app_config.py` | Gemeinsame App-, Bundle-, Versions-, Lokalisierungs- und Build-Zuordnung; unbekannte neue Mac-IDs bleiben gesperrt |
| `setup_products.py` | Zwei gemeinsame Abos, deutsche Lokalisierungen, Preise, Verfügbarkeit und Einführungsangebote |
| `complete_subscription_pricing.py` | Apples Pflichtpreise für alle Territorien ergänzen; Verkauf bleibt auf Deutschland beschränkt |
| `upload_metadata.py` | Gemeinsame App-Information und plattformspezifische Versionstexte, Review-Kontakt/-Hinweise |
| `upload_screenshots.py` | Mobile und Mac-Marketingbilder; gemeinsame Abo-Reviewassets ausschließlich über iOS |
| `prepare_review_drafts.py` | Private Plattform-Reviewentwürfe: Gruppe und beide Abos nur im bestehenden iOS-Entwurf, Mac ausschließlich App-Version |

## Zugang

Python 3 und `cryptography` werden benötigt. Der private Apple-Schlüssel bleibt außerhalb des Projekts. Zugang ausschließlich über Umgebungsvariablen:

```sh
export ASC_KEY_ID='<vorhandene Schlüssel-ID>'
export ASC_KEY_PATH='<absoluter Pfad zur privaten .p8-Datei>'
# Für Team-Schlüssel erforderlich; bei individuellen Schlüsseln nicht setzen:
export ASC_ISSUER_ID='<Issuer-ID des vorhandenen Team-Schlüssels>'
```

`ASC_ISSUER_ID` aktiviert ein Team-JWT; ohne diese Variable wird Apples individuelles JWT mit `sub=user` verwendet. Programme geben weder private Schlüssel noch JWTs aus und senden Apple-Zugangsdaten ausschließlich an `api.appstoreconnect.apple.com`.

Verwaltungsbelege (`*-proof.jpg`) enthalten private Kontodaten und bleiben wie signierte Pakete und Prüfberichte unter `artifacts/app-store/` ausschließlich lokal. Die App-Aufnahmen unter [screenshots/](../screenshots/) werden mit dem Projekt gespeichert. Lokale Beleglinks sind nur im ursprünglichen Arbeitsverzeichnis verfügbar.

## Gemeinsame Produkte

| Objekt | Kennung |
| --- | --- |
| App / Bundle | `6820947669` / `com.jonathankutscher.ga` |
| Name / Kategorien | Rudolf Steiner: Gesamtausgabe / Books, Reference |
| Gruppe | `22458743`, GA-App-Zugang |
| Jahresabo | `6820967918`, `com.jonathankutscher.ga.annual` |
| Förderabo | `6820968113`, `com.jonathankutscher.ga.supporter` |

Beide Produkte gelten für iOS und macOS. `--platform` wählt den Prüfkontext; es erstellt keine zweite Gruppe und keine zusätzlichen Mac-Produkte:

```sh
python3 docs/app-store/publishing/setup_products.py --platform ios --app-id 6820947669 --status
python3 docs/app-store/publishing/setup_products.py --platform macos --app-id 6820947669 --status
```

Mit `--apply` werden passende Ressourcen beibehalten. Konflikte, fremde App-Zuordnungen, doppelte Produkte und nicht editierbare Änderungen führen zum Abbruch. Bereits reviewbereite Lokalisierungen werden nur unverändert wiederverwendet. Laufzeit `ONE_YEAR`, Leistungsstufe `groupLevel=1`, deutsche Lokalisierungen, exakte deutsche Preise **30,00 € / 90,00 €**, drei Kalendermonate `FREE_TRIAL` für berechtigte Accounts. Nur Deutschland ist verfügbar; neue Territorien werden nicht automatisch aktiviert. Es wird kein Ersatzpreis wie 29,99 € gewählt.

Apple verlangt für die Reviewvalidierung dennoch Preise in sämtlichen **175 Territorien**. `complete_subscription_pricing.py` ergänzt ausschließlich fehlende `UPFRONT`-Pläne anhand Apples Equalisierungen des vorhandenen exakten deutschen Basispreises. Vorhandene abweichende Pläne bleiben erhalten und blockieren den Vorgang:

```sh
python3 docs/app-store/publishing/complete_subscription_pricing.py \
  --subscription-id 6820967918 --subscription-id 6820968113 \
  --report artifacts/app-store/shared-subscription-pricing-status.json
```

Die vorhandenen gemeinsamen Produkte besitzen bereits alle Pflichtpreise. Der [unabhängige historische Preis-Readback](../../../artifacts/app-store/subscription-price-coverage-readback.json) enthält auch die beiden früheren separaten Mac-Produkte; seine vier Produkte sind kein neues Vier-Produkte-Ziel.

## Plattform und Texte

Apple dokumentiert [das Hinzufügen einer Plattform](https://developer.apple.com/help/app-store-connect/create-an-app-record/add-platforms) und [die API-Erstellung der ersten Version auf einer neuen Plattform](https://developer.apple.com/documentation/appstoreconnectapi/post-v1-appstoreversions). Ein neuer `MAC_OS`-Versionsentwurf wird unter derselben App angelegt. Die native Mac-App benötigt dieselbe Bundle-ID und einen neu signierten Upload; der alte separate Mac-Build kann nicht in den gemeinsamen Eintrag verschoben werden. Universeller Kauf wird erst nach Freigabe mindestens zweier Plattformversionen verfügbar.

```sh
python3 docs/app-store/publishing/upload_metadata.py --platform ios --app-id 6820947669 --status
python3 docs/app-store/publishing/upload_metadata.py --platform macos --app-id 6820947669 --status
```

Mit `--apply` werden ausschließlich editierbare Entwurfsfelder aus `metadata.de-DE.json` gespeichert. Beide Plattformen verwenden denselben Namen und Books / Reference in der gemeinsamen App-Information. Beschreibung, Werbetext und Screenshots müssen für die neue Mac-Plattform separat gespeichert werden. Die Version ist standardmäßig 1.0; Veröffentlichung bleibt `MANUAL`. Die endgültige Beschreibung mit **4000 Zeichen und 26 verfügbaren GA-Titeln bis GA 27** sowie der unveränderte Werbetext mit **145 Zeichen** sind in beiden gemeinsamen Entwürfen gespeichert und exakt zurückgelesen: [Textabgleich](../../../artifacts/app-store/universal-copy-refresh-20261009.json).

## Bilder prüfen und abgleichen

`upload_screenshots.py` prüft App, Plattform, deutsche Lokalisierung, editierbare Version, Anzahl, RGB ohne Transparenz und native Pixelmaße. Bestätigt sind **acht Bilder je mobiler Größenklasse und vier Mac-Bilder**, insgesamt 28 COMPLETE mit Originalprüfsummen und Reihenfolge. Die [Bildinventur](../screenshots/README.md) trennt lokale Dateien, neue Uploads und historische Belege.

```sh
python3 docs/app-store/publishing/upload_screenshots.py --kind marketing --status
python3 docs/app-store/publishing/upload_screenshots.py --kind review --status
```

Ohne besonderen Austauschmodus verweigert `--apply` fremde oder abweichende vorhandene Dateien. Die sechs alten mobilen Kaufbilder können ausschließlich mit ausdrücklichem `--remove-purchase-marketing` ersetzt werden:

```sh
python3 docs/app-store/publishing/upload_screenshots.py \
  --platform ios --kind marketing --status --remove-purchase-marketing
```

Mit zusätzlichem `--apply` werden sämtliche neuen Marketingbilder aller Slots nacheinander reserviert, übertragen und bestätigt, bevor auf Apples Verarbeitung gewartet wird. Erst wenn alle Slots vollständig `COMPLETE` mit Originalprüfsummen sind und erneut geprüft wurden, beginnt der Austausch. Erst dann entfernt das Werkzeug die beiden bekannten Kaufdateien je mobilem Slot. Name, Dateigröße und MD5 müssen exakt zu den erhaltenen Originalen unter `screenshots/review/<Gerät>/` passen; unbekannte oder doppelte Assets blockieren den Vorgang. Acht Zielbilder und zwei alte Kaufbilder belegen vorübergehend Apples zehn Plätze. Abschließend werden Inventur und Reihenfolge bestätigt. Ein erneuter Aufruf setzt nach teilweisem Austausch sicher fort; alle Originale bleiben lokal wieder hochladbar.

Die **zwei gemeinsamen Abo-Reviewassets** sind erneut als COMPLETE mit identischen MD5-Prüfsummen und Dateigrößen bestätigt: [aktueller Readback](../../../artifacts/app-store/universal-subscription-review-assets-20261009.json). Ihre Quellen bleiben unverändert: `review/iphone-6.9/AppStore-04-Solidarischer-Zugang.png` und `review/iphone-6.9/AppStore-05-Kostenloses-Jahr.png`. Der Mac-Kontext erstellt keine zusätzlichen Abo-Reviewbilder. Die zwei früheren Mac-Produktbilder bleiben historische Belege am alten Eintrag. Der Austauschschalter greift niemals auf `subscriptionAppStoreReviewScreenshots` zu.

Historische Berichte: [18 ursprüngliche Marketingbilder](../../../artifacts/app-store/marketing-screenshot-upload-report.json), [vier damalige Abo-Reviewassets](../../../artifacts/app-store/subscription-review-screenshot-upload-report.json), [damalige Review-Hinweise](../../../artifacts/app-store/subscription-review-notes-report.json). Auch [vier neue Mac-Bilder am bisherigen separaten Eintrag](../../../artifacts/app-store/mac-screenshot-refresh-20261009.json) sind historische Belege. Der [neue gemeinsame Mac-Readback](../../../artifacts/app-store/universal-mac-screenshots-20261009.json) bestätigt zusätzlich alle vier Bilder im gemeinsamen Eintrag mit COMPLETE, Originalprüfsummen und Reihenfolge. Der [abschließende gemeinsame Marketingabgleich](../../../artifacts/app-store/marketing-screenshot-refresh-20261009.json) bestätigt alle 28 Bilder, sechs entfernte öffentliche Kaufassets und die unveränderten separaten Abo-Reviewbilder.

## Private Review-Entwürfe

```sh
python3 docs/app-store/publishing/prepare_review_drafts.py \
  --apply --include-app --report artifacts/app-store/universal-private-review-drafts.json
```

Das Werkzeug implementiert ausschließlich private Erstellung und „Zur Prüfung hinzufügen“. Es kann keine endgültige Übermittlung, Veröffentlichung, Löschung oder Build-Auswahl ausführen. Es prüft Apples tatsächliche Plattform, gemeinsame App-Zuordnung, erwarteten ausgewählten Build und `MANUAL`. Gruppe und beide gemeinsamen Abos bleiben ausschließlich im vorhandenen iOS-Entwurf. Der gemeinsame Mac-Entwurf `63883c48-e34e-4bd2-9148-a8b5200a3203` ist angelegt und bleibt ohne Items. Der iOS-Entwurf `935ba689-4148-4cfd-a308-58b5fd47edcf` enthält die gemeinsame Gruppe und zwei Abos. Beide sind READY_FOR_REVIEW mit submittedDate=null. Das Hinzufügen beider bestätigter App-Versionen wird ausschließlich durch die fehlende `contentRightsDeclaration` und nicht veröffentlichte Datenschutzantworten (`APP_DATA_USAGES_REQUIRED`) blockiert; [tatsächliche private Validierung](../../../artifacts/app-store/universal-private-review-drafts-20261009.json).

Die abschließende Veröffentlichung gespeicherter Datenschutzantworten wartet auf die Zustimmung zum konkreten Apple-Rechtsattest. Die Inhaltsrechtserklärung benötigt belegbare Rechte an den tatsächlich ausgelieferten Bestandteilen; siehe [Fundstellen](../content-rights.md). Auch reale Sandbox-/TestFlight-Käufe und Gerätesynchronisierung bleiben erforderlich. Keine dieser Voraussetzungen wird durch die Vorbereitung privater Entwürfe ersetzt.

Apple unterscheidet [private Vorbereitung und endgültige Übermittlung](https://developer.apple.com/help/app-store-connect/manage-submissions-to-app-review/submit-an-app) und beschreibt [erste Abos im passenden Entwurf](https://developer.apple.com/help/app-store-connect/manage-submissions-to-app-review/submit-an-in-app-purchase). Die [Pflichtpreise](https://developer.apple.com/documentation/appstoreconnectapi/configuring-subscription-prices-across-territories) erweitern das Verkaufsgebiet nicht. API-Referenz: [offizielle OpenAPI-Spezifikation](https://developer.apple.com/sample-code/app-store-connect/app-store-connect-openapi-specification.zip), Version 4.5.1, geprüft am 9. Oktober 2026.
