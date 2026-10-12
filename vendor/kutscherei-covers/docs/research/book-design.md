# Buchgestaltung der Rudolf-Steiner-Gesamtausgabe

## Ergebnis und Datenvertrag

Die Bibliothek verwendet 14 stabile Kategorie-IDs. Sie decken alle 463 Einträge aus dem vorhandenen Katalog `/Volumes/GEHIRN II/ga/data/ga_selection_matrix.json` ab. Die dort getrennt vorkommenden Labels `Schriften · Veröffentlichungen aus dem Nachlass` und `Veröffentlichungen aus dem Nachlass` werden bewusst auf dieselbe ID `estate-publications` abgebildet.

Die maschinenlesbare Quelle ist [`assets/textures/categories.json`](../../assets/textures/categories.json). Jeder Eintrag enthält Anzeigename, Kurzname, angenäherten sRGB-Wert, GA-Bereich, alle akzeptierten Kataloglabels sowie die relativen Pfade der Leinen- und Goldkachel.

| ID | Katalogzuordnung | Einträge | Bereich |
|---|---|---:|---|
| `works` | Schriften · Werke | 32 | GA 1–28 einschließlich Teilbände |
| `collected-essays` | Schriften · Gesammelte Aufsätze | 9 | GA 29–37 |
| `estate-publications` | Schriften · Veröffentlichungen aus dem Nachlass; Veröffentlichungen aus dem Nachlass | 20 | GA 38–49, eGA 47/48 |
| `public-lectures` | Vorträge · Öffentliche Vorträge | 47 | GA 51–86; im lokalen Bestand bis GA 84 |
| `member-lectures` | Vorträge · vor Mitgliedern der Anthroposophischen Gesellschaft | 189 | GA 87–270/4 |
| `art` | Vorträge · Kunst | 22 | GA 271–292 |
| `education` | Vorträge · Erziehung | 24 | GA 293–311 |
| `medicine` | Vorträge · Medizin | 8 | GA 312–319 |
| `natural-science` | Vorträge · Naturwissenschaft | 9 | GA 320–327 |
| `social-life` | Vorträge · Soziales Leben und Dreigliederung | 18 | GA 328–341 |
| `christian-religious` | Vorträge · Christlich-religiöses Wirken | 5 | GA 342–346 |
| `workers` | Vorträge · Arbeiter am Goetheanum | 8 | GA 347–354 |
| `artistic-work` | Künstlerisches Werk | 53 | K 1–58 und Teilbände |
| `catalogue-status` | Katalog- und Statusabgleich 2026 | 19 | technischer Bestand, kein Verlagsbereich |

## Verifizierte Gliederung

Der offizielle Verlagskatalog beschreibt drei Hauptabteilungen: geschriebenes Werk, mündliches Werk und künstlerisches Werk. Er nennt für die Schriften Werke GA 1–28, Aufsätze GA 29–37 und den schriftlichen Nachlass; die Vorträge gliedert er in öffentliche Vorträge GA 51–86, Vorträge vor Mitgliedern GA 87–270 und Vorträge zu einzelnen Lebensgebieten GA 271–354. Die Inhaltsübersicht und die Abschnittsüberschriften differenzieren die Fachgebiete Kunst, Erziehung, Medizin, Naturwissenschaft, soziale und wirtschaftliche Themen, christlich-religiöses Wirken und Arbeitervorträge. Quelle: [Rudolf Steiner Verlag, Gesamtverzeichnis 2022](https://steinerverlag.com/wp-content/uploads/RudolfSteinerVerlag_GV_2022.pdf), besonders S. 2–8 und die Fachabschnitte S. 66–91.

Die Kategorie `catalogue-status` ist eine Funktion des lokalen 463er Bestands und keine Kategorie des Verlags. `artistic-work` ist eine offizielle Hauptabteilung; ihre Einträge sind Reproduktionen und Dokumentationen unterschiedlicher Art, nicht eine einheitliche Reihe von Leinenbänden. Deshalb haben diese beiden IDs neutrale Ersatzfarben.

## Farbfamilien und Beleglage

Der Verlag veröffentlicht keine in diesem Projekt auffindbare verbindliche Palette mit Pantone-, RAL-, CMYK- oder HEX-Werten. Die Farbfamilien wurden daher aus repräsentativen, vom Verlag bereitgestellten Produktabbildungen abgeleitet. Die Werte sind Mittelwerte aus unbeschrifteten Einbandflächen in den veröffentlichten JPEGs und anschließend auf sechsstellige sRGB-HEX-Werte gerundet. Licht, Scan, Kamera, Alter des Exemplars, Gewebe und Auflage verändern die Darstellung. Die HEX-Werte sind folglich digitale Gestaltungswerte, keine behaupteten Produktionsfarben.

| ID | Näherung | Repräsentativer Verlagsbeleg | Einordnung |
|---|---|---|---|
| `works` | `#4D6EA7` | [GA 5 – Friedrich Nietzsche](https://anthroposophische-verlage.com/wp-content/uploads/00051-Steiner-Friedrich-Nietzsche-ein-Kaempfer-gegen-seine-Zeit-9783727400513.jpg) | blau |
| `collected-essays` | `#4C6DA6` | [GA 37 – Schriften zur Geschichte](https://anthroposophische-verlage.com/wp-content/uploads/00370-Steiner-Schriften-zur-Geschichte-der-anthroposophischen-Bewegung-und-Gesellschaft-1902-1925-9783727403705.jpg) | blau; nahezu identisch mit Werke |
| `estate-publications` | `#2C597F` | [GA 46 – Nachgelassene Abhandlungen](https://anthroposophische-verlage.com/wp-content/uploads/00460-Steiner-Nachgelassene-Abhandlungen-und-Fragmente-1879-1924-9783727404603.jpg) | tiefes Blau |
| `public-lectures` | `#ECC87B` | [GA 54 – Die Welträtsel und die Anthroposophie](https://anthroposophische-verlage.com/wp-content/uploads/00540-Steiner-Die-Weltraetsel-und-die-Anthroposophie-9783727405402.jpg) | gelb-ocker; Beleg zeigt die farbige Reihengestaltung, keine freiliegende Leinenstruktur |
| `member-lectures` | `#994D5D` | [GA 88 – Über die astrale Welt](https://anthroposophische-verlage.com/wp-content/uploads/00880-Steiner-Ueber-die-astrale-Welt-und-das-Devachan-9783727408809.jpg) | Bordeaux |
| `art` | `#E8B5C5` | [GA 275 – Kunst im Lichte der Mysterienweisheit](https://anthroposophische-verlage.com/wp-content/uploads/02750-Steiner-Kunst-im-Lichte-der-Mysterienweisheit-9783727427503.jpg) | Rosa |
| `education` | `#428A78` | [GA 293 – Allgemeine Menschenkunde](https://anthroposophische-verlage.com/wp-content/uploads/02931-Steiner-Allgemeine-Menschenkunde-als-Grundlage-der-Paedagogik-9783727429316.jpg) | Grün |
| `medicine` | `#4D6EA7` | [GA 316 – Vertiefung der Heilkunst](https://anthroposophische-verlage.com/wp-content/uploads/03161-Steiner-Meditative-Betrachtungen-und-Anleitungen-zur-Vertiefung-der-Heilkunst-9783727431616.jpg) | Blau |
| `natural-science` | `#A7A477` | [GA 325 – Naturwissenschaft und Weltgeschichte](https://anthroposophische-verlage.com/wp-content/uploads/03250-Steiner-Die-Naturwissenschaft-und-die-weltgeschichtliche-Entwickelung-der-Menschheit-seit-dem-Altertum-9783727432507.jpg) | Olivgrau |
| `social-life` | `#793531` | [GA 328 – Die soziale Frage](https://anthroposophische-verlage.com/wp-content/uploads/03280-Steiner-Die-soziale-Frage-9783727432804.jpg) | Dunkelrot |
| `christian-religious` | `#1F2846` | [GA 342 – Christlich-religiöses Wirken I](https://anthroposophische-verlage.com/wp-content/uploads/03420-Steiner-Vortraege-und-Kurse-ueber-christlich-religioeses-Wirken-9783727434204.jpg) | Nachtblau |
| `workers` | `#6085A1` | [GA 347 – Erkenntnis des Menschenwesens](https://anthroposophische-verlage.com/wp-content/uploads/03470-Steiner-Die-Erkenntnis-des-Menschenwesens-nach-Leib-Seele-und-Geist.-Ueber-fruehe-Erdzustaende-9783727434709.jpg) | Hellblau |
| `artistic-work` | `#8B8176` | kein einheitlicher Leinenbeleg | redaktioneller neutraler Ersatz |
| `catalogue-status` | `#6F7480` | keine Verlagskategorie | funktionaler neutraler Ersatz |

Einzelne neue oder neu fotografierte Ausgaben können von diesen Familien abweichen. Die Produktseite [Von Jesus zu Christus](https://steinerverlag.com/shop/kategorie/rudolf-steiner-ga/von-jesus-zu-christus/) bestätigt beispielhaft die Bindungsangabe `Leinen`; der Verlagskatalog weist bei den einzelnen Bänden ebenfalls `Leinen` oder `Gebunden` aus.

## Materialerzeugung

Die Kacheln sind deterministisch und prozedural erzeugt. Das ist für dieses Material geeigneter als ein generatives Einzelbild: Alle Farbvarianten besitzen dasselbe kontrollierte Gewebe, die Textur lässt sich reproduzieren, und jede mathematische Komponente ist über 512 Pixel periodisch. Das Muster kombiniert Kett- und Schussfäden, kleine diagonale Bindung, breitwellige Faservariation und schwaches Korn. Die Goldkacheln kombinieren längs gerichtete Bürstung, feines Korn und seltene helle Flocken. Sie sind für eine Text- oder Ornamentmaske gedacht.

[`assets/textures/generate.swift`](../../assets/textures/generate.swift) erzeugt 14 Leinenkacheln, 14 Kategorie-Goldkacheln, eine neutrale Goldkachel und die Übersicht. [`assets/textures/verify.swift`](../../assets/textures/verify.swift) prüft Dekodierung, 512 × 512 Pixel und die statistische Unauffälligkeit der horizontalen und vertikalen Kante gegenüber normalen Nachbarpixeln. Der aktuelle Lauf meldet 29 von 29 Texturdateien als bestanden; die gemessenen Nahtquotienten liegen zwischen 0,93 und 1,54 bei einer Grenze von 1,75.

![Übersicht aller Materialkacheln](../../assets/textures/overview.png)
