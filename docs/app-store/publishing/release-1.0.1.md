# GA 1.0.1 — Textfehler melden

Stand: 11. Oktober 2026. Gemeinsame Apple-App `6820947669`, Bundle-ID
`com.jonathankutscher.ga`, Version 1.0.1, Build 4 für iOS/iPadOS und macOS.

## Änderung

Eine ausgewählte Textstelle lässt sich im nativen Kontextmenü über
„Fehler melden …“ melden. Das Formular zeigt Ausschnitt und Fundstelle sowie
eine freiwillige Beschreibung. Erst „Senden“ übermittelt die Meldung; eine
E-Mail-Adresse und ein bezahlter Zugang sind nicht erforderlich. Bei einem
Übertragungsfehler bleibt die Eingabe erhalten. Unveränderte Wiederholungen
verwenden dieselbe Meldungs-ID und erzeugen keinen zweiten Datenbankeintrag.

Der [Produktionsdienst](../../../server/deploy/deployment-20261011-text-reports.md)
ist deployed. Die vollständige Nutzlast wird verschlüsselt gespeichert, nach
180 Tagen im stündlichen Lauf entfernt und bei Installationslöschung mitgelöscht.
Datenschutz und Support sind auf den kanonischen HTTPS-Seiten aktualisiert.

## Alterseinstufung

Auf Anweisung des Herausgebers wurden `violenceRealistic`,
`violenceCartoonOrFantasy` und `violenceRealisticProlongedGraphicOrSadistic` im
gemeinsamen editierbaren AppInfo auf `NONE` gesetzt und zurückgelesen.
Medizinische Informationen, erwachsene Themen und die übrigen Antworten bleiben
unverändert. Es gibt keinen manuellen Alters-Override. Die territoriale Apple-API
bestätigt für Deutschland und USA `SIXTEEN_PLUS` (16+). Historische Textbezüge
wurden dadurch nicht aus dem Katalog entfernt.

Belege: `artifacts/app-store/age-rating-1.0.1-readback.json` und
`artifacts/app-store/territory-age-ratings-1.0.1.json`.

## Apple-Vorbereitung

- iOS-Version `9f7973ce-be9b-485f-9c11-6e626864f0e2` ist angelegt. Die vorhandene
  deutsche Beschreibung (4.000 Zeichen), drei Screenshot-Sets und Reviewdaten
  sind übernommen. Die Neuigkeiten beschreiben die Meldefunktion.
- Die neue Reviewanleitung ist mit 3.976 Zeichen gespeichert und enthält konkrete
  Auswahlschritte, erfolgreichen Versand, Abbrechen und Wiederholung bei
  Netzwerkausfall.
- Beide Build-4-Archive und Exporte sind signiert erstellt. Apples offizielle
  Paketvalidierung besteht für IPA und Mac-Paket ohne Fehler. Das eigene
  Datenschutzmanifest enthält sechs Kategorien; das RevenueCat-Manifest ist in
  beiden Exports enthalten. Beide verwenden CloudKit Production.
- Die zusätzliche Kategorie **Customer Support → App Functionality, mit dem
  Benutzer verknüpft, kein Tracking** muss in App Store Connect noch gespeichert
  und veröffentlicht werden. Die offizielle Apple-API bietet diesen Dialog nicht
  an; zum Zeitpunkt dieses Berichts fehlt der Zugriff auf die angemeldete
  Oberfläche.
- Beide Builds 4 sind von Apple als `VALID` und `APP_STORE_ELIGIBLE` verarbeitet
  und in Version 1.0.1 ausgewählt. iOS-Build-ID: `2ead7075-17af-48ed-a40b-4b5674753369`;
  Mac-Build-ID: `5b1f63fe-4f0b-4a99-afaa-2ac9c225f8d1`.
- Der bisherige Mac-Review wurde zurückgezogen. Beide neuen App-Store-Reviewpakete
  stehen auf `READY_FOR_REVIEW` und enthalten jeweils die neue App-Version:
  iOS `48c88df6-ad89-46c0-881d-fdcff3680c2c`,
  Mac `032fac7c-022b-474c-bc0c-590bcaad0cd5`. Sie sind noch **nicht endgültig
  übermittelt**, da die neue Datenschutzkategorie noch veröffentlicht werden muss.
- iOS-Version 1.0 (Build 3) bleibt veröffentlicht. Beim ersten Mac-Release lässt
  Apple das Feld `whatsNew` nicht bearbeiten; die neue Funktion ist dort in der
  aktualisierten Reviewanleitung beschrieben.
- Für TestFlight ist iOS-Build 4 erneut eingereicht: `WAITING_FOR_BETA_REVIEW` /
  `WAITING_FOR_REVIEW`, interne Tester `IN_BETA_TESTING`. Die vorhandene externe
  Gruppe enthält Builds 3 und 4 und benachrichtigt nach Freigabe automatisch.
  Der [Testlink](https://testflight.apple.com/join/HEFJwK5G) bleibt derselbe.

Belege: `artifacts/app-store/build4-final-status.json`,
`build4-app-review-ready.json` und `build4-testflight-review.json`.

## Prüfungen

- 34 fokussierte Backendtests bestanden.
- Produktive HTTPS-Prüfung: Authentifizierung, Erstempfang, sequenzielle und
  parallele Wiederholung, Konflikt, Unicode- und Größenlimits, Rate-Limit,
  Verschlüsselung, geschützter Operatorexport, Logs und Installationslöschung.
- iOS- und Mac-Debug-Build erfolgreich; AccessStore-Harness inklusive Versand
  ohne aktiven Zugang, Unicode, UTF-16-Positionen und unveränderter Payload grün.
- Der signierte iOS-Oberflächentest besteht: echte Auswahl/Fundstelle, Abbrechen
  ohne Versand, freiwillige Beschreibung, Eingabeerhalt nach fehlender Bestätigung,
  identischer authentifizierter Retry und Erfolgshinweis mit geschlossenem Formular.
  Ein Test, null Fehler; zusätzlich Fixture-Prüfung beider identischen POSTs.
- Beide Releasepakete bestehen Signatur-, Manifest-, Versions-, Konfigurations-
  und offizielle Apple-Validierung; der Mac enthält arm64 und x86_64.

Der Ausgangsstand wurde als `8dfec0a`, die geprüfte Meldefunktion und das Backend
als `3c5896b` committed. Kurzlebige Betreiberkopien werden bei laufender
stündlicher Bereinigung innerhalb von höchstens 24 Stunden entfernt. Produktive Testmeldungen und
vorübergehende Testzugänge wurden nach der Backendprüfung entfernt.

## Verbleibender Schritt

Den Mac entsperren und in der App-Store-Connect-Oberfläche anmelden. Dort
Customer Support mit App Functionality, Benutzerverknüpfung und ohne Tracking
veröffentlichen. Danach beide bereits fertigen Reviewpakete per
`PATCH /v1/reviewSubmissions/{id}` mit `submitted: true` übermitteln und den
Status `WAITING_FOR_REVIEW` zurücklesen. `prepare_review_drafts.py` dokumentiert
den historischen Erstversand und darf dafür nicht unverändert verwendet werden.
