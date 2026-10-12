# GA 033: Originalinhalt und Lesegliederung

Die Reparatur bewahrt alle 15 vorhandenen Passage-IDs und ihre vollständigen
`source_text`-Werte. Die beiden ersten Container enthalten ausschließlich
Fragmente des ursprünglichen Inhaltsverzeichnisses. Sie werden als eigene
Lesebereiche „Inhalt — Biographische Skizzen“ und „Inhalt — Vier Biographien“
lesbar; ihre vorherigen Quelltexte bleiben erhalten.

## Originale Navigation

Die Originalseiten 5–6 gliedern den Autorenbestand in **Biographische Skizzen**
mit fünf Haupttexten und **Vier Biographien** mit vier Haupttexten. Die neun
Haupttexte und 60 dort aufgeführten Unterpunkte erhalten genau diese Hierarchie.
Die sechs tatsächlichen Roman-Kapitel von „Lyrik der Gegenwart“ stehen zusätzlich
als Unterpunkte dieses einen Aufsatzes. Bibliografische Untertitel werden an den
Haupttitel angefügt; sie erzeugen keinen weiteren Aufsatz.

Die Navigation umfasst 79 Zeilen: zwei Inhaltsbereiche, zwei Originalgruppen,
neun Haupttexte und 66 Unterpunkte. `original_table_of_contents` bewahrt die
vollständigen Originaleinträge mit Druckseiten und Quellzeugen;
`original_toc_target_review` bindet jedes echte Textziel an seine Zeile,
Hierarchie und Quelle. Originale Verlagsanhänge bleiben als geprüfte Einträge
ohne erfundene Textziele dokumentiert. Sie gehören nicht zu dieser Ergänzung.

Der ursprüngliche Import hatte „Bibliographisches und Textbehandlung“ unter
Arthur Schopenhauer versehentlich als Herausgeberapparat ausgeschlossen.
Genau dieser Autorenabschnitt auf S. 265–268 wird als eine neue Passage
`ga-033-schopenhauer-bibliographisches` vor Jean Paul ergänzt. Seine sechs
EPUB-Elemente, Roh- und Lesetexte, Memberhashes und Einfügeposition sind exakt
gebunden. Der historische Ausschluss wird archiviert; die beiden wirklichen
Herausgeberausschlüsse bleiben bestehen. `content_completeness` behält seinen
bisherigen Vertrag.

## Absatz-, Vers- und Quellenprüfung

Die unveränderte Original-DOC-Datei besitzt den importierten Quellenhash
`f43545098e6b0247a31fec051b9aa43de3276bdf9630dbcbd031ab0dc3581828`.
Das Original-PDF besitzt 413 Seiten und den Hash
`7c1139bf54772360f34e52ce10268207be7e0c08d6896cdfb1aeda1554c9a152`.
PDF- und Druckseiten stimmen hier überein. Original-DOC, Original-PDF und
DOC-Absatzlayout liegen unverändert und mit Bytehash unter
`research/proofreading-sources/ga-033-original.*` beziehungsweise
`ga-033-original-layout.json`. Die DOC- und PDF-Downloads stammen aus dem
[Originalquellenarchiv](https://archive.org/details/rudolf-steiner-ga-033).

Alle 1504 DOC-/EPUB-Quellenabsätze sind exakt zugeordnet. Die 819 ursprünglichen
importierten Textteile rekonstruieren alle 15 `source_text`-Werte vollständig;
sechs ergänzte Teile bilden den einen Autorenabschnitt. Der systematische
PDF-Geometrieabgleich umfasst die Inhaltsseiten 5–6 und den vollständigen
Autorenbereich 9–385: 375 Seiten mit Autorentext; 228–229 sind Leer-/Abteilungsseiten.
11426 Quellenzeilen und 367 positive Einzüge wurden abgeglichen. Vier echte
Prosaabsätze innerhalb zusammengezogener DOC-/EPUB-Elemente sind zusätzlich am
Druck visuell bestätigt (S. 18, 137, 233, 295). Die elf verbleibenden
OCR-Geometrieausnahmen sind einzeln zugeordnet: Inhaltsnummern, Titel,
Fußnote oder bereits vorhandene echte Absätze.

Die Lesegliederung enthält 459 Blöcke: 384 Prosaabsätze, 64 Überschriften,
neun Versgruppen und zwei Inhaltsbereiche. Alle 54 tatsächlichen Verszeilen
stehen an exakt belegten Quellpositionen. Die zwölf Zeilen des Gedichts auf
S. 195–196 bleiben eine durchgehende Gruppe; der Seitenwechsel erzeugt keine
Strophenlücke. Kurze echte Verse wie „Nachtumhüllt.“ und „Ihr sollt sprechen:
willekommen!»“ bleiben eigene Zeilen. Die Quelle-Lesarten „Idi“ und „Nidit“
werden bei dieser Formatierungsreparatur nicht umgeschrieben.

42 physische Wortfugen werden exakt geschlossen. 39 betreffen Seitenfugen;
drei ausschließlich den ergänzten Schopenhauer-Abschnitt („Frauen-städt“,
„Schopen-hauerschen“, „Gwin-ners“). Vollständige Originalzeilen, BBoxes,
EPUB-Elementhashes und native Seitenraster binden die Belege. Echte
Ergänzungsbindestriche bleiben erhalten; beim Kompositum
„furchtbar-sdimerzliche“ entfällt nur der physische Leerraum. Die vorhandenen
OCR-Buchstaben und Großschreibungen der Prosa bleiben unverändert.

13 eng belegte OCR-Überschriften werden an ihren ursprünglichen Grenzen
korrigiert, darunter die Jahresabschnitte 1840–1871 und 1871–1899 sowie das
Roman-Kapitel V. Diese Ersetzungen wirken ausschließlich auf den genau
belegten Überschriftenblock. Die eine vorhandene Autorenanmerkung auf S. 252
verliert nur drei physische Prosaumbrüche; Wörter, Marker, ID und beide
wörtlichen Rücklinkzeichen bleiben erhalten.

## Wiederaufbau und Prüfung

`tools/ga033_layout_review.json` friert sämtliche Starts, Originaltitel,
Inhaltszeilen, Textziele, Rohtexte und Quellenzeugen ein.
`tools/build_ga033_recipe.py` erzeugt daraus `tools/ga033_structure.json`.
Der Builder rekonstruiert alle Rohquellen erneut und kontrolliert die
Originaldateien sowie native Scanpixel. Der gemeinsame unabhängige Prüfer
verwendet eigene XML-Extraktion und Poppler für den Raster-/Zeilenvergleich.

```sh
python3 tools/build_ga033_recipe.py
python3 tools/test_ga033_readability.py
python3 tools/repair_ga033_readability.py --output /tmp/ga033-preview.json.gz --events /tmp/ga033-events.json
```

Die Python-Umgebung benötigt `pypdf`; die gebündelte Codex-Umgebung stellt es
bereit. Der lokale Wrapper bearbeitet ausschließlich eine GA033-Eingabedatei.
Die gemeinsame Pipeline erstellt erst nach dem Review aller vier Bände eine
frische Gesamtstufe. Anwendung, Export und Veröffentlichung sind kein Teil des
GA033-Builders.

Die fokussierten Prüfungen decken Originalhierarchie, vollständige Quelle,
den einzelnen ergänzten Abschnitt, alle vier internen Absätze, die 54
Verszeilen, Anmerkungs-Leerraum, Zeicheninventar und Idempotenz ab. Negative
Fälle verwerfen fremde Quellhashes, erweiterte Ergänzungen, einen als Inhalt
getarnten Prosatext, falsche Originalpixel sowie veränderte Inhaltsziele.
Diese vollständige Layoutprüfung ersetzt keine Wort-für-Wort-Kollation der
historischen OCR-Lesarten.
