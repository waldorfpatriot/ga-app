# Inhaltsrechte: begrenzte Prüfung vor Apples Erklärung

Stand: 9. Oktober 2026. Diese Prüfung liest vorhandene Herkunftsnachweise, Umfangswarnungen und sechs konkrete Abschnitte aus den aktuellen Reader-Payloads. Sie ist keine vollständige Rechteklärung der 324 verfügbaren Texte und keine rechtliche Erklärung gegenüber Apple. Es wurden keine Quellen entfernt, keine Reader-/Backend-Daten verändert und keine Rechte-Erklärung gespeichert.

## Ergebnis

Die vorhandenen Unterlagen belegen **nicht**, dass sämtliche angebotenen Arbeitsausgaben ausschließlich geklärte, gemeinfreie Originaltexte Rudolf Steiners enthalten. In den aktuellen `text`-Feldern sind konkret Verlagstexte und Herausgeberkommentare erhalten geblieben. Das betrifft den tatsächlich angebotenen Lesetext, nicht nur das für Entwickler aufbewahrte `source_text`.

Das ist kein Nachweis, dass Jonathan keine entsprechenden Nutzungsrechte besitzt. Die benötigten Lizenz-/Berechtigungsnachweise sind aus den hier geprüften Repository-Unterlagen jedoch nicht ersichtlich. Eine pauschale Erklärung über sämtliche Inhaltsrechte kann deshalb nicht allein auf die Bezeichnung „independent-public-domain“ oder Steiners Todesjahr gestützt werden. Die vorhandenen Berechtigungen für diese Arbeitsausgaben müssen vom Inhaber geklärt bzw. nachgewiesen werden.

## Konkrete aktuelle Fundstellen

| Reader-Payload | Abschnitts-ID | Im aktuellen `text` erhalten |
| --- | --- | --- |
| `server/priv/content/ga-255b.json.gz` | `ga-255b-pdf-outline-4-2` | Titel-/Verlagsseite: erste Auflage 2003; Herausgabe durch Alexander Lüscher und Ulla Trapp unter Mitarbeit weiterer Personen; Copyright-Angaben des Rudolf Steiner Verlags und der Nachlassverwaltung sowie ein Rechtevorbehalt. |
| `server/priv/content/ga-255b.json.gz` | `ga-255b-pdf-outline-6-4` | 2.096 Zeichen zur Herstellung und Bearbeitung der Vortragsausgaben, einschließlich Erklärungen zur Bearbeitung von Mitschriften und zur Tafelzeichnung; unterschrieben mit „Die Herausgeber“. |
| `server/priv/content/ga-255b.json.gz` | `ga-255b-pdf-outline-597-102` | 46.951 Zeichen lange „Chronik“ mit zusammengestellten Ereignissen, Datierungen und Erläuterungen. Dieser Abschnitt ist keine ausschließlich als Steiner-Rede ausgewiesene Originalpassage. |
| `server/priv/content/ga-267.json.gz` | `ga-267-doc-heading-12` | Innerhalb des 96.875 Zeichen langen Abschnitts stehen ausdrücklich „Erläuterungen der Herausgeber“ zu einer Archiv-Übung. |
| `server/priv/content/ga-267.json.gz` | `ga-267-doc-heading-18` | Innerhalb eines 29.370 Zeichen langen Abschnitts bleibt ein Anhang mit „Herausgeberkommentare A Zu den Atemübungen“ erhalten. Der folgende Text erläutert und interpretiert Steiners Aussagen; er steht neben den Originalzitaten. |
| `server/priv/content/ga-040a.json.gz` | `ga-040a-pdf-outline-75-10` | Der aktuelle Seelenkalender-Abschnitt enthält weiterhin schwer lesbare Handschriften-OCR und Copyright-Fußzeilen der Nachlassverwaltung. Die bestehende Quellenprüfung nennt zusätzlich ein alphabetisches Register in `ga-040a-pdf-outline-153-16` als offene Umfangsfrage. |

Ein Copyright-Vermerk allein beweist keine Schutzfähigkeit des darunterstehenden Steiner-Originaltextes. Die zusätzlich erhaltenen Herausgebertexte sind jedoch konkrete eigenständige Umfangs-/Autorschaftsfragen, die eine bloße Entfernung des Vermerks nicht lösen würde.

## Bereits dokumentierter Prüfstand

- [README, Produktionsbibliothek](../../README.md) sagt ausdrücklich, dass vollständige Faksimile-Kollation und Prüfung gemischter Autorschaft noch ausstehen.
- [Download-Bibliothek](../download-library.md) dokumentiert 674 identifizierte Abschnittsausschlüsse und quellengebundene Anfangsmarken. Die Entfernung identifizierter Abschnitte ist keine vollständige Rechteklärung sämtlicher noch enthaltener Textanteile.
- `tools/library-scope.json` und `server/priv/library/catalog.json` enthalten für GA 255b, GA 267 und GA 040a ausdrücklich Warnungen zu weiteren unüberschriebenen Fremdtexten, redaktionellen Überleitungen sowie Dialog-/Briefanteilen. GA 255b hat zusätzlich eine nicht eindeutig gefundene manuelle Anfangsmarke; der Standardanfang wurde beibehalten.
- [GA-040-Quellenprüfung](../proofreading/ga-040-source-review.md#ga-040a-concrete-unresolved-transcription-review) hält die Copyright-/Registerfrage für GA 040a als gesondert zu prüfende Umfangsentscheidung fest. Die aktuelle Payload-Prüfung bestätigt die genannten Fußzeilen im Lesetext.
- Eine reine Durchsicht der vorhandenen Katalogwarnungen findet bei 24 verfügbaren Arbeitsausgaben den ausdrücklichen Hinweis „Gemischte Dokumentation“. Damit ist nicht behauptet, dass alle 24 Ausgaben unzulässige Inhalte enthalten; die Warnungen belegen offene Einzelprüfungen.

Die vier wiedergewonnenen Texte GA 293, 294, 296 und 299 besitzen enger dokumentierte Grenzen; [Source recovery](../source-recovery.md) nennt beispielsweise den Ausschluss von Marie Steiners Vorwort. Das klärt die genannten anderen Arbeitsausgaben nicht automatisch.

## Veröffentlichungsdaten und Nachweise

Die Angabe **erste Auflage 2003** in GA 255b bezeichnet die vorliegende Gesamtausgabe. Sie ist **kein Beweis**, dass jeder darin enthaltene Steiner-Text 2003 erstmals veröffentlicht wurde. Im selben Titelmaterial wird sogar auf einen bibliografischen Nachweis früherer Veröffentlichungen verwiesen. In den geprüften Repository-Unterlagen wurde kein textweises Verzeichnis gefunden, das für sämtliche verfügbaren Arbeitsausgaben die tatsächliche Erstveröffentlichung, die Rechte an späterem Herausgebermaterial und entsprechende Nutzungserlaubnisse dokumentiert.

Diese Unterscheidung ist sachlich relevant: [§ 71 UrhG](https://www.gesetze-im-internet.de/urhg/__71.html) behandelt unter seinen Voraussetzungen die erste Veröffentlichung nach Ablauf des ursprünglichen Urheberrechts; [§ 70 UrhG](https://www.gesetze-im-internet.de/urhg/__70.html) betrifft bestimmte wissenschaftliche Ausgaben. Ob diese Voraussetzungen auf einen einzelnen enthaltenen Text bzw. eine konkrete Ausgabe zutreffen, wurde hier nicht festgestellt. Eine moderne Auflagenzahl allein beantwortet diese Fragen nicht.

## Vor der Erklärung zu klären

Jonathan muss die bestehenden Berechtigungen bzw. die dokumentierte Rechtegrundlage für die tatsächlich verfügbaren Arbeitsausgaben bestätigen, insbesondere für das erhaltene Herausgeber-/Verlagsmaterial. Falls hierfür bereits eine Lizenz oder Zustimmung vorliegt, wird deren konkreter Nachweis benötigt. Diese begrenzte Prüfung ersetzt diese Inhaberinformation nicht und gibt keine pauschale Erklärung über sämtliche Rechte ab.
