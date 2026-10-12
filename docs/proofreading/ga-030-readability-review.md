# GA 030: Umfang und Lesegliederung

Die Reparatur stellt die nachweislich fehlenden Quellteile wieder her und richtet
Absätze, Verse und Navigation an der ursprünglichen Ausgabe aus. Die drei alten
Passage-IDs und ihre vollständigen `source_text`-Werte bleiben unverändert.

## Quellen und Umfang

Die gespeicherte EPUB-Datei `research/proofreading-sources/ga-030.epub` ist der
exakte Textzeuge. Ihr SHA-256 ist
`1c2c1ebc018227733eb2a4bc77c56d28895c407674b80dfc956c1ddff4894e07`.
Die Original-DOC-Datei `research/ia_samples/rudolf-steiner-ga-030.doc` besitzt den
bereits importierten Quellenhash
`531ae1927d45534748b3c2d3dfb18f486584c19c4cc200953189d54eb40bcab5`.
Die dritte Auflage von 1989 im [Originalscan](https://odysseetheater.org/GA/Buecher/GA_030.pdf)
diente zur unabhängigen Prüfung der Druckgliederung. Ihr SHA-256 ist im Review
gespeichert; die Wiedergabe endet auf Seite 658.

Alle 92 Einträge der originalen Werkgliederung sind einzeln quellengebunden
zugeordnet. 91 Textanfänge waren bereits vorhanden. Tatsächlich fehlten:

- „Zur Einführung“, Seiten 17–20;
- zehn Autorenanmerkungen zu Haeckel, Seiten 196–200, deren Fortsetzungen teilweise
  schon im alten dritten Haupttext standen;
- die zweite Sternchenfußnote auf Seite 306;
- „Zu dieser Ausgabe“, Seiten 595–596;
- „Hinweise zum Text“, Seiten 597–645;
- das Namenregister, Seiten 647–658;
- die Jahreszahl `[1895]` nach „Leiden“ auf Seite 183, die zuvor als Seitenmarke
  behandelt worden war.

Die Einführung und die drei letzten Quellteile werden als vier neue Passagen
ergänzt. Die fehlenden Autorenanmerkungen werden an drei exakt gebundenen Stellen
des alten dritten Textes eingefügt; die bereits vorhandenen Fortsetzungen bleiben
erhalten. Die fehlende Sternchenfußnote wird als Annotation ergänzt. Die Jahreszahl
wird ausschließlich an ihrer belegten Stelle als `1895` gelesen; ihr ursprünglicher
Token `[1895]` bleibt im originalen Quellentext und im Additionsbeleg erhalten. Das
falsche Seitenmetadatum `1895` wird exakt gebunden entfernt. Der allgemeine
Normalisierer wird dafür nicht geändert.

Die im Inhaltsverzeichnis angekündigte Verlagsübersicht ab Seite 659 fehlt bereits
in EPUB und Originalscan. Diese Grenze ist als `proofing.known_source_gaps`
dokumentiert. Der verfügbare Autoren- und Quellentext ist vollständig restauriert;
der bestehende Wert `content_completeness: complete` und die Downloadfähigkeit
bleiben erhalten. Frühere Importausschlüsse stehen historisch unter
`source_import_excluded_sections`; die wiederhergestellten Herausgeberhinweise sind
kein aktueller Ausschluss mehr.

## Absatz- und Quellenprüfung

Die ursprünglichen DOC-Absatzeinzüge, selbstständige Überschriften und die
Druckseiten entscheiden über Grenzen. Ein systematischer Abgleich der PDF-Geometrie
auf Seiten 17–646 ordnete 858 positive Einzüge zu. Daraus wurden 24 zusätzliche
Prosaabsätze innerhalb zusammengezogener EPUB-Elemente visuell bestätigt. Alle
19 OCR-Ausnahmen des Geometrieabgleichs sind einzeln aufgelöst. Es gibt keine
satzbasierte Absatzregel.

17 Versgruppen wurden separat am Druckbild geprüft. Das zweispaltige Namenregister
bewahrt seine Quellenfolge und seine verschachtelten Eintragszeilen. Reine
Fortsetzungszahlen, darunter `221` und `109`, bleiben Registerinhalt. Physische
Zeilen- und Seitenfugen werden nur mit exaktem Quellbeleg geschlossen. Echte
Ergänzungs- und Kompositumbindestriche bleiben erhalten; vorhandene OCR-Buchstaben
werden dabei nicht umgeschrieben.

15 im bisherigen Lesetext enthaltene OCR-Seitenfüße werden an exakt gehashten
Quellstellen entfernt. Zwei weitere Seitenfüße waren bereits aus den neuen
Quellspannen ausgeschlossen. Ihre Original-DOC-Rolle und der unabhängig passende
PDF-Textkontext belegen die Entfernung. Die falsche EPUB-Seitenmarke `785` wird
quellengebunden als Druckseite 285 eingeordnet. Unbestätigte Quellenmarken werden
nicht als Leseseitenanker ausgegeben.

Das Ergebnis besitzt sieben Passagen und 101 Navigationseinträge. Neben den
92 ursprünglichen Einträgen enthalten sie deren Gruppen, die Autorenanmerkungen
und den restaurierten Herausgeberapparat. `reading_sections` stellt die einzelnen
Artikel innerhalb der erhaltenen großen Passagen dar. Alle Reader-Anker verwenden
UTF-16 und werden nach sämtlichen belegten Textkorrekturen aufgebaut.

## Reproduzierbare Stufe

`tools/ga030_layout_review.json` hält Quellhashes, genaue EPUB-Elementspannen,
Original-TOC, Absatzzeugen, physische Wortfugen und die dokumentierte Quellgrenze
fest. Der Builder bindet jede Ergänzung an den unveränderten Quellenbestand. Die
Recipe verbraucht jeden Nichtleerraumcharakter des ergänzten Eingabetextes genau
einmal; nur die expliziten Quellenkorrekturen und Seitenfüße dürfen davon abweichen.

Mit einer Python-Umgebung, die `lxml` enthält:

```sh
python3 tools/build_ga030_recipe.py
python3 tools/test_ga030_readability.py
python3 tools/repair_ga030_readability.py --output /tmp/ga030-readability-stage-20261008
```

Die Stufe bewahrt andere Bände. Ihre Änderungshistorie unterscheidet die aktuellen
komprimierten Eingabebytes (`application_base_sha256`) vom gespeicherten
ursprünglichen Drei-Passagen-Eingang (`layout_input_sha256`). Diese Hashes dürfen
wegen unterschiedlicher gzip-Header auch bei identischem JSON verschieden sein.

Der unabhängige Stichprobenprüfer rekonstruiert die Ergänzungen selbst aus EPUB und
prüft anschließend alle tatsächlichen Zeichen, Source-Werte, Metadaten und
Änderungsereignisse gegen die erhaltene Baseline. Er ruft den Builder nicht auf.
Die fokussierten Reparaturtests prüfen Quellen- und Inventardrift, vollständige
Absatzdeckung, Artikel- und Registergrenzen, Jahreszahl/Seitenmetadaten, den
Downloadvertrag, Idempotenz und beide gzip-Hashbindungen. Apply und Export sind
gesonderte Schritte nach Prüfung der Stufe.

Die Struktur- und Umfangsprüfung ersetzt keine vollständige Wort-für-Wort-Kollation
aller historischen OCR-Lesarten. Die bestehende Kennzeichnung als Arbeitsausgabe
bleibt bestehen.
