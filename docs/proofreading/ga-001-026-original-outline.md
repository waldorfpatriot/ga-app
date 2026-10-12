# Originale Gliederung: GA 001–026

Am 8. Oktober 2026 wurden die Nummerierung, Kapitelhierarchie und Einschübe der 25 verfügbaren Bände in GA 001–026 mit den jeweils erhaltenen Quellen abgeglichen. GA 019 bleibt mangels freigegebenem Text als nicht verfügbar gekennzeichnet.

Die Korrekturwerkstatt ergänzt keine laufende Abschnittsnummer mehr. Die quelleneigenen römischen und arabischen Ziffern bleiben erhalten; Vorreden, Nachträge und unnummerierte Werke erhalten keine künstliche Nummer. Übergeordnete Teile, interne Vorbemerkungen und Zusätze sind über eigene Originaleinträge navigierbar. Ein importierter Textcontainer ist dabei nicht automatisch ein Kapitel.

Die 607 Inhaltsverzeichniseinträge greifen auf 508 unveränderte Textcontainer zu. Alle bisherigen Passagekennungen, Textzeichen, Prüfsummen, Quellenfassungen, Seitenmetadaten und Anmerkungen bleiben erhalten. Neue Überschriftenrollen und UTF-16-Sprungziele ändern die Darstellung, nicht den Buchtext. In GA 026 sind alle 185 Leitsätze und 71 ursprünglichen Datumszeilen berücksichtigt; zwei reine Fortsetzungscontainer erzeugen keine zusätzlichen Kapitel.

| Band | Originaleinträge | Besonderheiten |
| --- | ---: | --- |
| GA 001 | 39 | Römische Hauptkapitel; X und XVI mit arabischen Unterkapiteln; 1–9 in XVII. |
| GA 002 | 30 | Unnummerierte Vorreden; Teile A–G mit durchgehenden Unterkapiteln 1–21. |
| GA 003 | 10 | Unnummerierte Vorrede und Einleitung; I–VIII. |
| GA 004 | 32 | Zwei Hauptteile; I–XIV; elf originale Zusätze; letzte Fragen und Anhänge. |
| GA 005 | 54 | I–III, darunter 1–41; weitere Aufsätze mit eigenen römischen Unterabschnitten. |
| GA 006 | 17 | Unnummerierte Vorreden und Kapitel; zwei originale übergeordnete Teilüberschriften. |
| GA 007 | 10 | Unnummerierte Vorworte und Kapitel. |
| GA 008 | 15 | Unnummeriertes Vorwort; I–XIII; unnummerierte Bemerkungen. |
| GA 009 | 17 | I–IV als Hauptteile; eigene römische Unterabschnitte in I und III. |
| GA 010 | 19 | Unnummerierte Kapitel, Bedingungen/Innere Ruhe und Vorbereitung/Erleuchtung als Untergliederung. |
| GA 011 | 20 | Unnummerierte Aufsätze; wiederhergestellte übergreifende Überschrift. |
| GA 012 | 5 | Vorredenauszug und Hauptkapitel als getrennte Originaleinträge im ersten Container. |
| GA 013 | 20 | I–VI; weitere Vorbemerkungen; neun Unterabschnitte unter Einzelheiten. |
| GA 014 | 59 | Vier Mysteriendramen mit ihren Personen, Bildern, Vor- und Zwischenspielen. |
| GA 015 | 4 | Vorwort und I–III. |
| GA 016 | 10 | Einleitung, ausgeschriebene erste bis achte Meditation, Nachwort. |
| GA 017 | 18 | Unnummerierte Kapitel mit originalen Zusammenfassungen an ihrer Stelle. |
| GA 018 | 21 | ERSTER BAND und ZWEITER BAND mit ihren jeweiligen Kapiteln. |
| GA 019 | — | Kein freigegebener Text vorhanden. |
| GA 020 | 5 | Unnummeriertes Vorwort und unnummerierte Kapitel. |
| GA 021 | 14 | I–IV; unter IV die ursprünglichen Unterabschnitte 1–8; Schlussbemerkung. |
| GA 022 | 3 | I–III. |
| GA 023 | 8 | Unnummerierte Vorbemerkungen; I–IV und V. Anhang. |
| GA 024 | 69 | Fünf übergeordnete Aufsatz-/Dokumentgruppen mit ihrer eigenen Gliederung. |
| GA 025 | 10 | I–X. |
| GA 026 | 98 | Originale Inhaltstitel mit LS-Bereichen; eigener Inhaltseintrag, 62 Unterüberschriften und separate Datumszeilen. |

## Belege und Grenzen

Die portable, editionsgebundene Gliederung steht in `tools/ga001_026_structure.json`. Sie enthält die Quellenbelege und Hashes, die erhaltenen Text- und Quellenprüfsummen sowie jeden Originaltitel, seine Ebene, Elternbeziehung und Sprungposition. Die Hauptquellen sind die importierten EPUBs in `research/proofreading-sources` und die erhaltenen Archiv-DOC-Auszüge in `research/doc_text`; für schwierige Stellen wurden die ursprünglichen DOC-Dateien zusätzlich abgeglichen.

Die vollständige textliche Kollation ist davon getrennt. Bereits bestehende Quelllücken werden weder mit fremden Ausgaben aufgefüllt noch durch erfundene Sprungziele verdeckt:

- GA 009: „Zur Neuauflage dieser Schrift“ ist im Quelltext enthalten, wurde vom früheren Import jedoch ausgelassen; die erwähnte Vorrede zur dritten Auflage fehlt bereits im erhaltenen Quellzeugen.
- GA 011: „Die Trennung der Geschlechter“ ist im Quellinhaltsverzeichnis genannt, fehlt aber im erhaltenen Textkörper.
- GA 013: Die Vorrede zur 7.–15. Auflage ist in der erhaltenen Quelle nicht enthalten.
GA 026 verwendet die 35 Haupttitel des originalen Inhaltsverzeichnisses einschließlich ihrer Leitsatzbereiche und behält alle 62 untergeordneten Originalüberschriften. Der erhaltene Inhalt im ersten Container ist als „Inhalt“ separat auswählbar; „Vorbemerkung“ springt weiterhin zum eigentlichen Autorentext. Text, Seiten und Anmerkungspositionen bleiben unverändert. Nur die fehlende schließende Klammer bei LS 88–102 wird im Navigationslabel ergänzt; die Quelle bleibt erhalten. Die Quellenprüfung und der reproduzierbare Aufbau stehen in `tools/ga026_contents_review.json` und `tools/build_ga026_contents.py`.

Abweichende OCR-Schreibungen in Titeln werden nur bei eindeutigem Beleg in derselben Edition korrigiert. So ist GA 005 „I. Der Charakter“ in deren eigenem Inhaltsverzeichnis belegt.

## Wiederholung und Prüfung

Die eingefrorene Gliederung lässt sich ohne Quellenkonvertierung oder Netzwerk wiederholen:

```sh
python3 tools/repair_early_structure.py --output /tmp/ga-original-outline-new-stage
python3 tools/check_proofreading_samples.py --stage /tmp/ga-original-outline-new-stage
python3 tools/proofread_library.py --apply-stage /tmp/ga-original-outline-new-stage
python3 tools/export_apple_content.py
```

Der vollständige Korrekturlauf berücksichtigt dieselbe Gliederung automatisch nach den Wort- und Leerraumkorrekturen. Eine geänderte Quelle oder verschobene Textposition stoppt die Anwendung. Der unveränderte Zustand vor der Gliederung liegt lokal unter `research/proofreading-outline-baseline`; Revisionen werden daraus wiederholt und behalten den vorherigen Gliederungsverlauf im Korrekturbericht.

Der unabhängige Prüfer vergleicht jedes zulässige Metadatenfeld und jeden Sprung mit dem eingefrorenen Rezept und verifiziert die gesamte Textkorrekturhistorie separat. Browserprüfungen prüfen alle 25 Bände und ihre Originaleinträge einschließlich Auswahl, Textidentität, Datumsanzeige und Neuladen. Die lokale Korrekturwerkstatt übernimmt die Korrektur; die öffentliche Bibliothek erfordert weiterhin einen eigenen Veröffentlichungsschritt.
