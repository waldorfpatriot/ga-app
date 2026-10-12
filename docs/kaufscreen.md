# Kaufbildschirm: solidarisches Jahresabo

Stand: 9. Oktober 2026. Dieses Dokument beschreibt das besprochene Konzept und den Kaufbildschirm-Entwurf. Kaufabwicklung, Anfragespeicherung und Zugangserteilung sind damit noch nicht in der GA-App umgesetzt.

Die inzwischen umgesetzten Entscheidungen und der produktive Dienst sind in [access.md](access.md) dokumentiert. Die folgenden Angaben bewahren den ursprünglichen Planstand.

## Ziel

Die GA-App bietet denselben App-Zugang zu drei Beiträgen an. Menschen mit geringem Einkommen können ein kostenloses Jahr erbitten. Wer mehr beitragen möchte, unterstützt diese Zugänge mit einem Förderabo.

Der Kaufbildschirm macht Preis, Laufzeit und die Häufigkeit der drei Auswahlmöglichkeiten leicht verständlich. Er verlangt keine Rechtfertigung der finanziellen Situation.

## Festgelegte Beitragsoptionen

| Option | Beitrag | Zugang | Zweck |
| --- | --- | --- | --- |
| Jahresabo | 30 € pro Jahr | Gleiche Funktionen wie bei den anderen Optionen | Regulärer Beitrag zur GA-App |
| Förderabo | 90 € pro Jahr | Gleiche Funktionen wie bei den anderen Optionen | Der Mehrbeitrag unterstützt kostenlose Zugänge |
| Kostenloses Jahr | 0 € für zwölf Monate | Gleiche Funktionen wie bei den anderen Optionen | Für Menschen, die den Beitrag gerade nicht aufbringen können |

Das Förderabo kostet insgesamt 90 € pro Jahr. Gegenüber dem Jahresabo beträgt der Mehrbeitrag 60 €. Der Bildschirm verspricht keine feste Zahl finanzierter Gratisabos.

Die kostenlose Option benötigt eine klare Freitextbitte. Ein Einkommensnachweis, eine Einkommensgrenze oder eine ausführliche Begründung sind nicht vorgesehen. Die Bitte kann jederzeit erneut gestellt werden.

„Gleicher App-Zugang“ beschreibt den Funktionsumfang der drei Optionen. Daraus folgt keine Zusage, dass sämtliche Bände der Rudolf-Steiner-Gesamtausgabe verfügbar sind.

## Aufbau und Texte des aktuellen Entwurfs

Der aktuelle Entwurf zeigt die Häufigkeiten direkt bei den jeweiligen Optionen. Die bezahlten Angebote stehen oben; die kostenlose Option folgt etwas kleiner darunter. Auch die kleinere Option bleibt gut lesbar und leicht bedienbar.

### Einleitung

**Überschrift:** „Ein Beitrag. Gemeinsam getragen.“

**Einleitung:** „Alle erhalten den gleichen vollständigen App-Zugang. Wähle den Beitrag, der für dich passt.“

### Jahresabo

- Titel: „Jahresabo“
- Preis: „30 € / Jahr“
- Beschreibung: „Dein Beitrag für die GA-App.“
- Häufigkeit: Prozentanteil, Anzahl und ein einfacher Balken
- Schaltfläche: „Für 30 € jährlich abonnieren“

### Förderabo

- Titel: „Förderabo“
- Preis: „90 € / Jahr“
- Beschreibung: „Dein Mehrbeitrag unterstützt kostenlose Zugänge.“
- Häufigkeit: Prozentanteil, Anzahl und ein einfacher Balken
- Schaltfläche: „Für 90 € jährlich fördern“

### Kostenloses Jahr

- Einleitung: „Wenn du den Beitrag gerade nicht aufbringen kannst“
- Preis: „0 €“
- Häufigkeit: Prozentanteil, Anzahl und ein einfacher Balken
- Schaltfläche: „Ein kostenloses Jahr anfragen“

Die Schaltfläche öffnet das Formular unmittelbar unter der Option.

### Anfrageformular

**Hinweis:** „Eine klare Bitte genügt. Du brauchst keinen Einkommensnachweis. Du kannst jederzeit erneut anfragen.“

**Feldbezeichnung:** „Deine Bitte“

**Platzhalter:** „Bitte ermögliche mir ein kostenloses Jahr. Den Beitrag kann ich zurzeit nicht aufbringen.“

**Vertraulichkeit und Laufzeit:** „Deine Nachricht bleibt vertraulich. Das Gratisjahr geht ohne Zahlung zu Ende.“

**Schaltfläche:** „Bitte absenden“

Es gibt nur das Freitextfeld als inhaltliche Pflichtangabe. Der Platzhalter ist eine Formulierungshilfe; andere klare Bitten sind ebenfalls ausreichend. Ein Gratisjahr wird nicht automatisch in ein kostenpflichtiges Abo umgewandelt.

## Öffentliche Auswahlhäufigkeiten

Die Zahlen beantworten die Frage, wie häufig die drei Optionen gedrückt werden. Sie zeigen **Auswahlklicks**, keine abgeschlossenen Käufe und keine erteilten Gratiszugänge.

Der Entwurf verwendet die Beschriftung „Auswahlklicks der letzten 90 Tage · … insgesamt“. Das Zeitfenster von 90 Tagen ist ein Vorschlag und noch keine verbindliche Produktentscheidung.

Für jede Option werden Anzahl und Anteil an allen Auswahlklicks im selben Zeitraum angezeigt. Die Balken verwenden dieselbe Skala von 0 bis 100 %. Bei der kostenlosen Option bleibt ihre Häufigkeit sichtbar, auch wenn das Formular geschlossen ist.

Die Beispielzahlen des Entwurfs sind:

| Option | Beispielanzahl | Beispielanteil |
| --- | ---: | ---: |
| Jahresabo | 700 | 70 % |
| Förderabo | 100 | 10 % |
| Kostenloses Jahr | 200 | 20 % |
| Insgesamt | 1.000 | 100 % |

Diese Werte sind ausschließlich Demonstrationsdaten. In der veröffentlichten App werden echte aggregierte Zahlen angezeigt. Solange keine Daten vorliegen, erscheint beispielsweise „Noch keine Auswahlzahlen verfügbar“.

Als Alternative wurde eine gemeinsame Verteilung oberhalb der Optionen entworfen: ein gestapelter Balken mit beschrifteten Anteilen für 30 €, 90 € und 0 €. Beide Darstellungen verwenden dieselben Daten.

### Zählweise für die Umsetzung

Vorgeschlagene Ereignisse sind der Klick auf die jeweilige Abo-Schaltfläche sowie das Öffnen der kostenlosen Anfrage. Das Absenden der Bitte ist ein separates Ereignis. Ein später abgebrochener Kauf bleibt damit ein Auswahlklick, wird aber nicht zum abgeschlossenen Abo.

Die Behandlung mehrfacher Klicks ist noch festzulegen. Technische Wiederholungen derselben Ereignisübermittlung dürfen die Zahlen nicht erhöhen. Falls künftig eindeutige Personen oder abgeschlossene Vorgänge gezählt werden sollen, muss die öffentliche Beschriftung entsprechend geändert werden.

Für die Ertragsrechnung werden abgeschlossene Käufe, Verlängerungen und tatsächlich erteilte Gratiszugänge getrennt erfasst. Öffentliche Auswahlanteile sind kein Ersatz für diese Zahlen.

## Ablauf und Zustände

### Bezahlte Optionen

Die Auswahl öffnet die native Kaufabwicklung. Erst nach bestätigtem Kauf wird der entsprechende Jahreszugang aktiviert. Ein abgebrochener oder fehlgeschlagener Kauf aktiviert keinen Zugang; die Auswahl bleibt erneut möglich.

Der bisherige Entwurf enthält den Hinweis „Beide Abos verlängern sich jährlich. Jederzeit zum Laufzeitende kündbar.“ Automatische Verlängerung ist bisher eine Entwurfsannahme. Die endgültige Aboregelung muss vor Umsetzung festgelegt werden; Bildschirmtext und Kaufangebot müssen übereinstimmen.

Für die Umsetzung sind außerdem Kaufwiederherstellung, Aboverwaltung sowie Links zu Datenschutz und Nutzungsbedingungen zu ergänzen. Die tatsächlich angebotenen Preise und Laufzeiten müssen mit der Kaufabwicklung übereinstimmen.

### Kostenloses Jahr

1. Die Person öffnet das Formular und formuliert ihre Bitte.
2. Eine leere oder nur aus Leerzeichen bestehende Nachricht kann nicht abgesendet werden. Es gibt keine Prüfung von Einkommen oder Belegen.
3. Die Anfrage wird vertraulich gespeichert. Während des Absendevorgangs werden versehentliche doppelte Übermittlungen verhindert.
4. Die App bestätigt den tatsächlich erreichten Zustand: „Bitte eingegangen“ nach Speicherung; eine Freischaltungsbestätigung erst nach erteiltem Zugang.
5. Nach Freischaltung sind Beginn und Ende des kostenlosen Jahres sichtbar. Eine erneute Bitte bleibt jederzeit möglich.

Bei einem Übermittlungsfehler bleibt der eingegebene Text erhalten und die Person kann erneut absenden. Automatische oder manuelle Freigabe sowie der genaue Beginn der zwölf Monate sind noch festzulegen.

## Vertrauliche Speicherung

Freitextbitten werden in einer Datenbank gespeichert und nicht veröffentlicht. Die öffentliche Anzeige erhält nur zusammengefasste Häufigkeiten. Namen, Nachrichten und Angaben zur finanziellen Situation erscheinen dort nicht.

Für eine Anfrage werden mindestens folgende Informationen benötigt:

| Information | Zweck |
| --- | --- |
| Anfrage-ID | Eindeutiger Vorgang; Schutz vor doppelter Verarbeitung |
| Eingangszeitpunkt | Nachvollziehbarer Eingang |
| Freitextbitte | Die ausdrücklich gewünschte Anfrage |
| Zuordnung zum Zugang | Freischaltung für die richtige Person und gegebenenfalls Wiederherstellung |
| Bearbeitungsstatus | Eingang und Freischaltung unterscheiden |
| Beginn und Ende des Gratiszugangs | Laufzeit anzeigen und prüfen |

Einkommensnachweise und zusätzliche Angaben zur finanziellen Situation werden nicht angefordert. Lesedaten, Notizen und Markierungen sind kein Bestandteil der Anfrage. Zugriff auf die Nachrichten erhalten nur die für die Bearbeitung zuständigen Personen beziehungsweise Dienste. Aufbewahrung und Löschung der Freitexte sowie die technische Zugangszuordnung sind noch zu bestimmen.

## Offene Entscheidungen

- Automatische oder manuelle Freigabe einer klaren Bitte.
- Beginn des Gratisjahres und Umgang mit einer erneuten Bitte während eines noch laufenden Zugangs. Die jederzeitige Möglichkeit einer neuen Bitte bleibt bestehen.
- Automatische Verlängerung der bezahlten Jahresabos und endgültiger Verlängerungstext.
- Welche Funktionen ohne laufenden Jahreszugang nutzbar bleiben und wann der Kaufbildschirm erscheint.
- Zeitfenster und Umgang mit wiederholten Auswahlklicks.
- Endgültige Darstellung der Häufigkeiten: direkt bei den Optionen oder als gemeinsame Verteilung.
- Zuordnung und Wiederherstellung kostenloser Zugänge sowie Aufbewahrung der Anfragen.

## Abnahmekriterien

- Alle drei Preise, ihre Laufzeit und der gleiche Funktionsumfang sind verständlich dargestellt.
- Die kostenlose Option steht unter den bezahlten Angeboten und ist ohne Suche erreichbar.
- Eine klare Bitte genügt; es gibt keine Nachweispflicht und keine ausführliche Rechtfertigung.
- Eine erneute Bitte ist jederzeit möglich; es erfolgt keine automatische Umwandlung in ein bezahltes Abo.
- Die Häufigkeiten aller drei Optionen sind sichtbar und ausdrücklich als Auswahlklicks beschriftet.
- Demonstrationsdaten werden nicht als echte Nutzungszahlen veröffentlicht.
- Freitexte bleiben vertraulich; die öffentliche Anzeige enthält ausschließlich aggregierte Werte.
- Kaufabbruch, Übermittlungsfehler, Anfrageeingang und Freischaltung sind unterscheidbar.
- Der Bildschirm bleibt mit großer Schrift und auf kleinen Geräten vollständig bedienbar; Text und Zahlen erklären die Optionen auch ohne Farberkennung.

## Stand des Prototyps

Die bisherige Bildschirmvorschau enthält zwei Layoutvarianten mit Beispielzahlen. Die Abo-Schaltflächen zeigen nur eine lokale Auswahlbestätigung. Das Formular versendet oder speichert keine Nachricht und erteilt keinen Zugang. Dieses Dokument ist die Grundlage für eine spätere Umsetzung.
