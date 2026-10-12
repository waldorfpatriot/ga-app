# CloudKit-Produktionsschema

Prüfstand: 9. Oktober 2026. Team `ER7U6R25KM`, Container `iCloud.com.jonathankutscher.ga`.

Die App verwendet in der privaten CloudKit-Datenbank den Datensatz `personal-reading-state-v1` vom Typ `GAReadingState`. Er benötigt `payload` als `Asset` und `schemaVersion` als `Int64`. Die Lesedaten werden als Asset gespeichert. Für diesen Typ sind keine öffentlichen Datenbankberechtigungen erforderlich.

**Das Produktionsschema ist veröffentlicht und in der CloudKit Console geprüft.** Die angemeldete Apple-Sitzung bestätigte nach der additiven Veröffentlichung ausdrücklich „The schema is deployed to Production.“ Die anschließende Production-Ansicht zeigte `GAReadingState` mit acht Feldern einschließlich der Systemfelder, `payload` als `ASSET` und `schemaVersion` als `INT(64)`. Der [Prüfbeleg](publishing/apple-cloudkit-production-proof.jpg) wurde gespeichert. Es wurden keine persönlichen CloudKit-Datensätze abgefragt oder gelöscht und kein Schema zurückgesetzt.

Bei der Umstellung auf den gemeinsamen Apple-Eintrag wurde eine tatsächliche Konfigurationslücke entdeckt: Die alten Build-2-Pakete enthielten trotz passender CloudKit-Entitlements keinen expliziten `GACloudKitContainerIdentifier` in ihrer Info.plist. Die tatsächlichen signierten Build-3-Exporte beider Plattformen bestätigen jetzt `GACloudKitContainerIdentifier=iCloud.com.jonathankutscher.ga`, die gemeinsame Bundle-ID `com.jonathankutscher.ga` und passende Production-Entitlements. Paketbelege: [iOS](../../artifacts/app-store/ios/build-3/validation/package-verification.json), [nativer Mac](../../artifacts/app-store/mac/universal/build-3/validation/package-verification.json). Das veröffentlichte Schema bleibt unverändert; alte Signatur-/Profilbelege bestätigen allein keine funktionierende Gerätesynchronisierung.

Die unabhängige CLI-Prüfung war zuvor nicht möglich: Sowohl `cktool get-teams` als auch der konkrete Production-Export meldeten „No management token found“. Es wurde für die Veröffentlichung kein Management-Token erzeugt; die Console verwendete die bestehende Apple-Anmeldung. Die folgenden CLI-Schritte bleiben für spätere Änderungen dokumentiert. App-Store-Connect-Schlüssel ersetzen keinen CloudKit-Management-Token.

Ein Teammitglied kann in den eigenen Einstellungen der [CloudKit Console](https://icloud.developer.apple.com/) einen Management-Token erzeugen und ihn lokal durch `xcrun cktool save-token --type management` im Schlüsselbund speichern. Den Token nicht in Dokumentation, Chat, Repository oder Protokollen ablegen.

Danach zuerst beide vorhandenen Schemata exportieren:

```sh
xcrun cktool export-schema --team-id ER7U6R25KM \
  --container-id iCloud.com.jonathankutscher.ga \
  --environment production --output-file /tmp/ga-production.ckdb
xcrun cktool export-schema --team-id ER7U6R25KM \
  --container-id iCloud.com.jonathankutscher.ga \
  --environment development --output-file /tmp/ga-development.ckdb
```

Enthält Production bereits `GAReadingState` mit den beiden passenden Feldern, ist keine Schemaänderung nötig. Andernfalls den [vorbereiteten Datensatztyp](cloudkit/GAReadingState.fragment.ckdb) in eine Kopie des vollständigen Development-Exports übernehmen. Bestehende Typen, Felder, Indizes und Berechtigungen erhalten; bei einem bereits vorhandenen Typ nur die fehlenden Felder ergänzen. Der Ausschnitt ist kein vollständiger Ersatz für ein vorhandenes Containerschema.

Die vollständige ergänzte Datei zuerst mit `cktool validate-schema` für Development validieren, danach mit `cktool import-schema --validate` in Development übernehmen. Anschließend in der CloudKit Console die additive Änderung nach Production veröffentlichen und Production erneut exportieren. Apples [Schema-Dokumentation](https://developer.apple.com/documentation/cloudkit/integrating-a-text-based-schema-into-your-workflow) beschreibt die Veröffentlichung über die Console; [Authentifizierung und Werkzeug](https://developer.apple.com/icloud/ck-tool/) sind getrennt von App Store Connect eingerichtet.

Ein erfolgreicher Schemaexport bestätigt keine Geräte-Synchronisierung. Vor Veröffentlichung weiterhin einen signierten Production-/TestFlight-Build auf zwei Geräten mit demselben iCloud-Account prüfen: Leseposition, Notiz, Markierung und deren Löschung müssen auf dem zweiten Gerät ankommen. Dieser reale Synchronisierungstest wurde in dieser Sitzung nicht durchgeführt.
