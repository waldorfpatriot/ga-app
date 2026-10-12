# GA 034: Absätze und ursprünglicher Inhalt

GA 034 erhält eine am ursprünglichen Druck geprüfte Lesegliederung. Alle sieben
vorhandenen Passage-IDs und ihre vollständigen `source_text`-Werte bleiben erhalten.
Die beiden irreführend betitelten vorderen Importcontainer werden als zusammenhängender
Inhalt gelesen. Die 106 vorhandenen Textziele des Originalinhalts sind einzeln erreichbar;
Publikationsangaben und Druckseiten werden getrennt geführt. Gleichlautende Meditationen
sind durch Juli 1903 beziehungsweise September 1903 unterscheidbar.

## Quellen und vollständiger Review

Der importierte Textzeuge ist `research/proofreading-sources/ga-034.epub`, SHA-256
`f1e0bb3b002ce943b63904d87e560cc5800c2921960f2344c8a94ad0bf7d8b2d`.
Die [ursprüngliche DOC-Datei](http://bdn-steiner.ru/cat/ga/034.doc) ist unter
`research/proofreading-sources/ga-034-original.doc` gesichert. Ihr Hash entspricht
der bereits importierten Quelle:
`24535e9bf5094bd29d4d5693175ee8a1693d396dbc5aa567af97da7ee3382663`.
Der [Originaldruck als PDF](https://odysseetheater.org/GA/Buecher/GA_034.pdf) liegt
unter `research/proofreading-sources/ga-034-original.pdf`; SHA-256
`e2e5d87da678e8194226e4feae8b3c9bdc6263e4129f1dc85ac5acef6166cbe7`.
Die ursprünglichen Absatzmerkmale stehen in
`research/proofreading-sources/ga-034-doc-layout.json`.

Alle sieben Quelltexte sind vollständig aus 1706 geordneten EPUB-Elementen
rekonstruiert; verschachtelte Listeneinträge besitzen genaue Elementpfade.
Quellmember, rohe Absätze, ursprüngliche DOC-Indizes und Lesetextpositionen sind
gehasht beziehungsweise eindeutig verankert. Die Rekonstruktion sowie DOC- und
Zeichenpositionszuordnung weisen keine Abweichungen auf.

Die Absatzprüfung umfasst die gesamten erhaltenen Druckseiten 11–619 und 21127
zugeordnete PDF-Textzeilen. Die DOC-Einzüge und Abstände werden mit der
Druckgeometrie verglichen. Alle 27 zusätzlichen inneren Einzugskandidaten sind
visuell klassifiziert: 25 echte Prosaabsätze, ein Listenbeginn und eine zweite
Zeile desselben Buchkopfes. Sämtliche 126 auffälligen Überschriften-, Vers-,
Datums-, Signatur- und Bibliografie-Kandidaten sind nach ihrer tatsächlichen Rolle
klassifiziert. Zeilenlänge oder Satzschluss begründen keinen Absatz.

Der eingefrorene Review steht in `tools/ga034_layout_review.json`, die vollständig
abdeckende Recipe in `tools/ga034_structure.json`. Die Wiederherstellung enthält
1053 Blöcke: 901 Prosaabsätze, 112 zusammenhängende Überschriften, 33 Inhalts-,
Listen-, Anmerkungs-, Signatur- und Bibliografie-Blöcke sowie sieben Versblöcke.
Die beiden kurzen Meditationen sind nachweislich Prosa. Die echten Verse auf den
Druckseiten 31, 147, 471 und die vier Sprüche auf Seite 602 behalten zusammen
16 ursprüngliche Zeilen. Listelemente bleiben getrennt; ihre bloßen Druckumbrüche
werden innerhalb des Elements verbunden.

## Inhalt und Navigation

Die ursprünglichen Inhaltsseiten 5–10 enthalten sechs Hauptgruppen und 111
Textzeilen. Davon sind 106 Autorenbeiträge in den vorhandenen Textcontainern
erhalten; fünf weitere Zeilen verweisen auf nicht importierten Verlagsapparat.
Die beiden vorderen Inhaltspassagen geben alle ursprünglichen Inhaltszeilen in
ihrer Reihenfolge wieder. Der Verlagsapparat selbst wird dadurch nicht ergänzt.
Jede restaurierte Zeile ist an ihre vollständigen ursprünglichen DOC-/EPUB-Zeugen
und die entsprechende Inhaltsseite gebunden.

Die Navigation hat 114 Einträge: zwei getrennte Inhalt-Ziele, die sechs
ursprünglichen Hauptgruppen und 106 eindeutige Textziele. Die nachgeordnete Arbeit
in Stuttgart, Lugano, Weimar und Nürnberg bleibt unter „Von der Arbeit der Zweige“.
Die tatsächliche erste Einführung ist direkt an ihrem Lesetextanfang erreichbar.
Die 110 `reading_sections` umfassen diese Texte und die vorhandenen
Fortsetzungscontainer. Ihre Beschriftungen stammen aus den Quellenüberschriften.

Mehrzeilige Aufsatztitel und Untertitel bilden einen zusammenhängenden Kopf.
Datumsangaben, Unterschriften, Übersetzer- und Verlagszeilen werden ausdrücklich
nicht zu zusätzlichen Aufsätzen. So bleiben etwa „Flita“, ihr Untertitel und ihre
bibliografischen Angaben ein einziger ursprünglicher Buchbeitrag. Der Name
„Henry Steel Olcott“ im restaurierten Inhalt folgt dem tatsächlichen Druck;
die überlieferten OCR-Buchstaben im Autorenlesetext bleiben unmodernisiert.

## Eng begrenzte Textkorrekturen

Alle 155 vorhandenen Hyphenkandidaten sind überprüft. 105 echte Ergänzungsstriche
oder ursprüngliche Satzzeichen bleiben erhalten. 50 physische Kandidaten und der
zusätzliche nachgewiesene Anschluss „Vorur-/teil“ werden in 51 exakt gebundenen
Wortfugen verbunden. Neun getrennte DOC-Seitenfußartefakte werden ausschließlich
an ihren eingefrorenen Quellstellen ausgelassen. Dadurch können auch die vom
Seitenfuß unterbrochenen Wörter wieder innerhalb desselben Absatzes gelesen werden.

Buchstaben, Großschreibung und historische Schreibungen werden nicht geändert.
Lesarten wie `TatSachen`, `PhiloSophie`, `Handhingen` und `Vorstelhingen` sind
als verbleibende Quellenauffälligkeiten dokumentiert. Nur der Druckkopf
„Zum Beginn des neuen Jahrganges (Juniipoj)“ erhält die sichtbar belegte Datierung
„Zum Beginn des neuen Jahrganges (Juni 1905)“.

Ein 235 Zeichen langer Autorensatz auf Druckseite 303 war ausschließlich als
Titel des zehnten Containers importiert worden. Das genaue ursprüngliche
EPUB-Element `chapter-0010.xhtml`, Body 56, wird am Ende des neunten Containers
wieder gelesen. Es schließt an dessen „Vorur-“ an und endet mit
„die folgenden Sätze zu lesen sind:“. Der zehnte Container beginnt weiterhin
mit dem folgenden Zitat und erhält die tatsächliche Überschrift „VORURTEILE AUS
VERMEINTLICHER WISSENSCHAFT“. Dieser Übergang erzeugt weder eine neue Passage-ID
noch ein zweites Aufsatz-Ziel; sämtliche ursprünglichen `source_text`-Werte bleiben
auch bei dieser Wiederherstellung unverändert.

Die zwölf vorhandenen Anmerkungen werden mit ihren ursprünglichen Kennungen,
Markern, Feldern, Rücklinkzeichen und ihrer Platzierung erhalten. Ihre insgesamt
309 physischen Zeilenumbrüche und künstlichen Importleerzeilen werden innerhalb
der jeweils gedruckten Prosa-Anmerkung gefaltet. 18 genau aufgeführte physische
Wortfortsetzungen sind zusätzlich verbunden. Vorher, Nachher, unveränderte
Quellbuchstaben und alle ursprünglichen EPUB-Zeugen stehen im Review und Ledger.
Die Fortsetzungen der Anmerkungen 3 und 6, die bereits als Lesetext importiert
waren, bleiben ausdrücklich Anmerkungsblöcke und werden nicht als Aufsätze geführt.

## Bestätigte Quellenlücken

Dies ist keine Behauptung vollständiger Anmerkungen: Zwei ursprüngliche
Reinkarnations-Anmerkungen, Nr. 1 auf Druckseite 90 und Nr. 5 auf Seite 91,
fehlen schon im bisherigen Import. Ihre EPUB-Elemente `chapter-0003.xhtml`,
Body 43 und 48, sind mit Hash und Druckseite in `known_gaps` dokumentiert.
Die importierten Rückverweise führen ins künstliche Kapitel `chapter-9999` und
liefern keinen sicheren Bezugspunkt. Diese beiden Anmerkungen werden bei der
Lesegliederungsreparatur nicht neu angelegt.

## Reproduzierbare Prüfung

Nach der gemeinsamen Stufe liegt die unveränderte Eingabe unter
`research/proofreading-layout-baseline/content/ga-034.json.gz`.

```sh
python3 tools/build_ga034_recipe.py
python3 -m unittest discover -s tools -p 'test_ga034_readability.py'
python3 tools/repair_ga034_readability.py \
  --input research/proofreading-layout-baseline/content/ga-034.json.gz \
  --output /tmp/ga034-reading-preview.json
```

Der Builder liefert bei gleicher Originaleingabe dieselbe Recipe. Die unabhängige
Familienprüfung `tools/check_essay_layout.py` rekonstruiert alle rohen Quellen
selbst, vergleicht jede Absatzscheibe, Inhaltszeile und Reparatur mit dem Review
und prüft die eng begrenzte Prosa-Wiederherstellung getrennt. Alle 63 belegten
Textkorrekturen bestehen die vollständige Quellen- und Ausgabeprüfung. Die
zusätzlichen 14 lokalen Tests prüfen unter anderem vollständige Gliederung,
Verszeilen, echte Bindestriche, Titelsubgliederung, eindeutige Originalziele,
Anmerkungen, unveränderte IDs/Quelltexte, Idempotenz und abgewiesene Daten- oder
Rezeptänderungen.

Die gemeinsame Bibliotheksstufe wird von `tools/proofread_library.py` erzeugt.
Dieser bandspezifische Wrapper kann ausschließlich eine separate Vorschau schreiben;
er verändert keine bestehenden Serverdateien und exportiert nichts.
