# GA 032: quellengebundene Lesegliederung

Die Reparatur richtet den vorhandenen Lesetext an den ursprünglichen Absätzen,
Artikelüberschriften und Verszeilen aus. Die 57 Passage-IDs, ihre vollständigen
`source_text`-Werte sowie die Kennungen und Marker aller zehn vorhandenen
Annotationen bleiben erhalten. 15 durch die frühere Seitenmarker-Erkennung
unterdrückte Jahreszahlen werden aus ihren exakten Quellstellen wieder gelesen.
Die vorherigen Korrekturschichten werden bewahrt.

## Quellen und Verfahren

Die importierte EPUB-Datei `research/proofreading-sources/ga-032.epub` ist der
exakte Textzeuge. Ihr SHA-256 ist
`b7ddbc4423ba323c1b6b88a6e406f48033e2bf34d55f8f9c593ea168f1203175`.
Die [ursprüngliche DOC-Datei](http://bdn-steiner.ru/cat/ga/032.doc) wurde erneut
beschafft und besitzt den bereits importierten Quellenhash
`656c0177f2b15e86ba5aba230c8c66545bb00792bd946009526f1bbc98a99c6d`.
Die unabhängige PDF-Prüfung verwendet die ursprüngliche Ausgabe mit 559
PDF-Seiten und dem Hash
`1155b523ddfece69a51a2c75a29f752a2c48742fad1eae03509835e8f6ac6bd7`.
Die Druckseite 11 entspricht PDF-Seite 15.

Alle 57 ursprünglichen Quelltexte sind unabhängig aus 1590 geordneten
EPUB-Elementen rekonstruiert. Acht verschachtelte Listeneinträge sind über ihre
genauen Elementpfade gebunden. Der Review hält die Member- und Paragraphhashes
fest; der Builder und der unabhängige Prüfer kontrollieren diese Zeugen jeweils
direkt aus der EPUB-Datei.

Der vollständige Review umfasst 501 physische Druckseiten, darunter vier leere
Seiten. Die 497 Seiten mit Inhalt sind hinsichtlich Absätzen, Versen,
Überschriften und Wortfugen klassifiziert. 615 ursprüngliche Verszeilen sind
einzeln an ihre Quellpositionen gebunden.

Die ursprünglichen DOC-Absatzmerkmale und die Druckgliederung entscheiden über
echte Grenzen. Physische Seitenfortsetzungen werden innerhalb desselben Absatzes
verbunden. Selbstständige Überschriften und Versgruppen erhalten eigene Rollen.
Ein kurzer Absatz oder ein Satzende allein ist kein Gliederungsbeleg. Die
zugehörigen Quellenpositionen und Entscheidungen stehen vollständig im eingefrorenen
Review; die Recipe enthält keine allgemeine Regel zum Zusammenziehen einzelner
Zeilen.

Physische Wortfugen werden ausschließlich mit exakt aufgeführten Quellbelegen
geschlossen. Beispielsweise verbindet die Fortsetzung von „Farben-“ auf
Druckseite 12 mit „harmonie“ auf Seite 13 das Wort „Farbenharmonie“. Echte
Kompositum- und Ergänzungsbindestriche sowie historische Schreibungen bleiben
erhalten. Alle 47 alphabetischen Wortfugenkandidaten wurden am Druck geprüft:
39 werden exakt verbunden, sieben Ergänzungsbindestriche bleiben bestehen,
und „Puls-“ gehört zum gesondert belegten Versüberlauf. 13 verbleibende
OCR-Lesarten werden als Quellenauffälligkeiten dokumentiert; ihre Buchstaben
und Schreibungen bleiben erhalten. Die zehn Annotationseinträge enthalten 40 physische Prosaumbrüche.
Diese werden an exakt gebundenen EPUB-Fußnotenstellen als Leerzeichen gelesen.
Ihre Wörter, Satzzeichen, Marker, Reihenfolge und sämtlichen wörtlichen
Rücklinkzeichen „↩“ bleiben unverändert. Der vollständige vorherige Text steht
in den Annotationenbelegen des Review und im Änderungsprotokoll. Die vorhandenen
zehn Einträge verweisen auf acht verschiedene Quellfußnoten; diese geerbte
Zuordnung bleibt erhalten.

## Struktur und Navigation

`reading_blocks` unterscheidet Prosa, Verse, Überschriften und andere ausdrücklich
belegte Rollen: 725 Prosaabsätze, 104 Überschriften, 105 Versgruppen und 30
Quellenlisten ergeben 964 Blöcke. Die Navigation umfasst 120 Zeilen: die drei
ursprünglichen Abteilungen I/II/III und 117 genaue Textziele. Alle 97 erhaltenen
Ziele des ursprünglichen Inhaltsverzeichnisses sind eindeutig abgedeckt.
Unabhängige Artikel innerhalb der erhaltenen großen Textcontainer
werden durch `reading_sections` und genaue Navigationseinträge zugänglich.
Die Beschriftungen stammen aus den tatsächlichen Quellenüberschriften. Versehentlich
als Seitenzahlen gelesene Jahresangaben werden nur an einzeln belegten Metadatenstellen
korrigiert. Die 15 tatsächlich gedruckten Jahresangaben bleiben im Originalquelltext
als `[Jahr]` erhalten; der Lesetext stellt sie als Ziffern dar, damit sie nicht
erneut als Seitenmarker verschwinden. Druckseitenanker erfordern eine genaue Textposition und einen
Quellenbeleg; unbestätigte Seitenangaben erzeugen keine Anker.

Alle Block-, Abschnitts- und Inhaltsverzeichnisziele verwenden UTF-16. Sie werden
erst nach der vollständigen Formatierung und den expliziten Wortfugen aufgebaut.
Jeder Nichtleerraumcharakter des vorhandenen Eingabetextes wird genau einmal
verbraucht; nur im Review ausdrücklich belegte Textkorrekturen dürfen davon
abweichen. Neben den 15 Jahreszahlen wird genau ein im DOC- und EPUB-OCR
ausgelassener Wortfortsetzungsteil restauriert: „ent-“ vor dem Gedicht
„In Wasserstiefeln“ wird als „enthalten:“ gelesen. „halten:“ steht sichtbar
auf Druckseite 447 (PDF-Seite 451). Da auch die PDF-Textebene dieses Fragment
auslässt, bindet der Beleg das originale eingebettete Seitenbild und einen
exakten Pixelausschnitt an ihre Hashes und Selektoren. Builder und Prüfer
verifizieren diese Bildbytes unabhängig. Die vollständige Zeugenstelle und
Vorher/Nachher stehen als eigene `source_fragment_restorations` im
Layoutprotokoll. Es werden keine weiteren Artikel oder Quellteile ergänzt.
Die bisherige Kennzeichnung und die dokumentierten Importausschlüsse bleiben
erhalten.

## Reproduzierbare Stufe und Prüfung

`tools/ga032_layout_review.json` enthält den vollständigen Quellenreview.
`tools/build_ga032_recipe.py` erzeugt daraus die eingefrorene
`tools/ga032_structure.json`. Zum Wiederaufbau werden nur das gespeicherte
Eingabe-JSON, das unveränderte EPUB, das erhaltene Original-PDF und der Review
benötigt. Für den direkten Bitmapbeleg wird eine Python-Umgebung mit `pypdf`
verwendet, wie sie die gebündelte Codex-Umgebung bereitstellt.

```sh
python3 tools/build_ga032_recipe.py
python3 tools/test_ga032_readability.py
python3 tools/repair_ga032_readability.py --output /tmp/ga032-linebreak-stage-20261009
```

Die Stufe bewahrt alle anderen Bände und deren bisherige Absatz- und
Satzkorrekturen. Ihre Änderungshistorie trennt den Hash der aktuellen komprimierten
Eingabebytes (`application_base_sha256`) vom Hash der gespeicherten ursprünglichen
Layout-Eingabe (`layout_input_sha256`). Unterschiedliche gzip-Header dürfen diese
Hashes bei identischem JSON unterscheiden.

Fünf typografische Versüberläufe werden an exakten Quellzeilen rekonstruiert.
Beispielsweise gehört „[schlag“ zum vorherigen „Puls-“ und wird als
„Pulsschlag“ gelesen; „Des Seins:“ beginnt weiterhin eine eigene Verszeile.
Nur die belegten Überlaufklammern und Trennstriche entfallen. Echte kurze Verse
wie „Hier,“ und „laut“ sowie die gedruckten Strophenlücken bleiben erhalten.

Die fokussierten Tests prüfen Quellen- und Inventardrift, sämtliche 15
Jahresrestaurationen, 40 Annotationenfugen, fünf Versüberläufe, den exakten
Bitmapbeleg für „halten:“, vollständige
Zeichendeckung, echte Absatz- und Versgrenzen, Metadaten, Idempotenz und beide
Hashbindungen. Der unabhängige Stichprobenprüfer rekonstruiert den gesamten
Quellbestand und die Recipe-Grenzen selbst aus den eingefrorenen Zeugen und prüft
die tatsächliche Stufe. Apply und Export folgen erst nach dieser Prüfung.
Diese vollständige Layoutprüfung ersetzt keine Wort-für-Wort-Kollation sämtlicher
historischer OCR-Lesarten.
