# Repository und Textkorpus

Dieses Repository enthält den Arbeitsstand der GA-App vom 12. Oktober 2026.
Es wurde als eigenständiger Git-Stand aus den aktuellen Projektdateien erstellt.
Die vorherige lokale Git-Historie und private Betriebsdaten sind nicht enthalten.

## Enthaltene Bestandteile

| Pfad | Inhalt |
| --- | --- |
| `apple/GA` | Gemeinsame SwiftUI-App einschließlich Lesemodellen, Zugriff, Käufen, CloudKit, Textfehlermeldungen und EPUB-Export |
| `apple/GA.xcodeproj` | Projekt, gemeinsame Schemes und gepinnte Swift-Package-Abhängigkeiten für iOS/iPadOS und macOS |
| `apple/GAUITests` | Vorhandene UI-Regressionstests |
| `apple/AuthorReader` | Zusätzlich vorhandener gemeinsamer Reader-Quellcode |
| `server/lib`, `server/config`, `server/mix.exs`, `server/mix.lock` | Phoenix-Backend und dessen Build-Konfiguration |
| `server/priv/repo` | Datenbankschema, Migrationen und Seeds für den Backendbetrieb |
| `server/priv/static/proofreading` | HTML-, CSS- und JavaScript-Frontend der Korrekturwerkstatt |
| `server/deploy` | Deployment-Skripte und Konfigurationsvorlagen |
| `server/priv/content` | 324 vollständig gespeicherte bearbeitete Textausgaben mit insgesamt 4.988 Abschnitten |
| `server/priv/library` | Katalog mit 463 Einträgen, Importberichte und Quellenprüfungen |
| `server/priv/proofreading` | Katalog und Protokolle der durchgeführten Korrekturen |
| `apple/GA/BundledCatalog`, `apple/GA/BundledContent` | App-Katalog und fünf vollständig enthaltene Offline-Bücher |
| `tools` | Vorhandene Import-, Korrektur-, Export-, Validierungs- und Einrichtungsskripte samt Korrekturregeln |
| `vendor/kutscherei-covers`, `design/icons` | Verwendete Cover-/Icon-Quellen, Materialien, Schriften und vorhandene Lizenz-/Herkunftsnachweise |
| `docs` | Projekt-, Betriebs-, Korrektur- und App-Store-Dokumentation samt bestehenden Screenshots |
| `docs/app-store/web` | HTML-Quellen der App-, Support- und Datenschutzseiten |
| `research/ia_advancedsearch.json`, `research/ia_metadata_summary.json` | Bereits versionierte Recherche-Metadaten |

Die 139 noch nicht verfügbaren Einträge bleiben als Metadaten erhalten.
Für sie existieren keine bearbeiteten Lesetexte im Projekt.

## Textformat und Nachvollziehbarkeit

Die fünf Kernwerke werden als JSON gespeichert, die übrigen 319 Textausgaben
als deterministische `.json.gz`-Dateien. Python-Beispiel zum Lesen:

```python
from pathlib import Path
import gzip
import json

path = Path("server/priv/content/ga-120.json.gz")
work = json.loads(gzip.decompress(path.read_bytes()))
print(work["work_id"], len(work["passages"]))
```

Die Textdateien enthalten die bearbeiteten Abschnitte und die im Projekt
vorhandenen Quellen-, Prüfsummen- und Herkunftsdaten. Wo bisher vorhanden,
bleibt der ursprüngliche Abschnittstext für den Entwicklervergleich erhalten.
Die per Werk gespeicherten Korrekturprotokolle liegen unter
`server/priv/proofreading/works`.

[corpus-manifest.json](repository/corpus-manifest.json) verzeichnet jedes
vorhandene Werk mit Pfad, Abschnittszahl, Dateigröße und SHA-256.
[source-manifest.json](repository/source-manifest.json) dokumentiert die
kopierten Projektdateien und ihre ursprünglichen Prüfsummen. README und
Gitignore wurden anschließend um Repository-Hinweise ergänzt.

## Start und Prüfung

Die bestehenden Build- und Betriebsanweisungen stehen in der
[Projekt-README](../README.md), die Korpusverarbeitung unter
[Download-Bibliothek](download-library.md) und
[Korrekturwerkstatt](proofreading/README.md).

```sh
# Konsistenz von bearbeitetem Korpus, Korrekturprotokollen und Apple-Ressourcen
python3 tools/check_apple_build_content.py

# Vollständige Downloads mit den tatsächlichen Swift-Lesemodellen prüfen
python3 tools/check_download_library.py

# Backendabhängigkeiten holen und Katalogdienst lokal starten
cd server
mix deps.get
GA_SKIP_REPO=true mix phx.server
```

Die Swift-Prüfung und die Apple-Builds benötigen macOS mit Xcode.
Das Phoenix-Backend benötigt Elixir/Erlang gemäß `server/mix.exs` und
`server/mix.lock`. Der lokale Katalogmodus benötigt keine Datenbank.
Zugriffsverwaltung, kostenlose Freischaltungen und Textfehlermeldungen benötigen
PostgreSQL, die Migrationen und eigene Laufzeitgeheimnisse. Die Vorlage dafür
ist `server/deploy/ga-access.environment.example`.

Die lokale Korrekturwerkstatt startet mit:

```sh
python3 tools/proofreading_server.py
```

Sie legt ihre eigenen lokalen Notizen unter `server/var` an. Die vorhandenen
Import- und Strukturrekonstruktionsskripte benötigen teilweise Python mit
`lxml` sowie Originalquellen. Quell-EPUBs, Scans und historische Baseline-Caches
sind separate Eingaben und gehören nicht zum bearbeiteten Lesekorpus.

Weitere Autoren-Werkzeuge sind als vorhandener Quellcode mit archiviert;
ihre erzeugten Editionen und Konfigurationen werden in diesem GA-Repository
nicht mitgeliefert.

## Nicht enthaltene lokale Daten

Private Konfigurationen, API-Geheimnisse, Signierschlüssel, die lokale
Notizdatenbank, heruntergeladene Abhängigkeiten, Build-Artefakte,
Forschungs-Caches, Presseverteiler und E-Mail-Entwürfe sind nicht übernommen.
Andere eigenständige Apps und deren generierte Autoreneditionen liegen
außerhalb dieses Repository-Umfangs.

Die enthaltenen Textausgaben behalten ihren dokumentierten Bearbeitungs- und
Prüfstatus. Die bestehenden Befunde zur Quellenabgrenzung und Rechteprüfung
stehen in [content-rights.md](app-store/content-rights.md). Dieses Repository
vergibt keine zusätzliche pauschale Lizenz für den Korpus oder den Quellcode.
