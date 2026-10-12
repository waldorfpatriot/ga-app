# GA-App – Gesamtausgabe

Vollständiger Projektstand der GA-App: native SwiftUI-Frontends für iPhone,
iPad und Mac, Phoenix/Elixir-Backend, Korrekturwerkstatt im Browser und der
bearbeitete Rudolf-Steiner-Textkorpus mit Quellenangaben und Korrekturprotokollen.

Der Katalog enthält **463 Einträge**, davon **324 vorhandene Texte** mit
**4.988 Abschnitten** und **139 als nicht verfügbar gekennzeichnete Einträge**.
Der bearbeitete Korpus liegt vollständig in `server/priv/content`; für den
Betrieb ist kein separates Forschungsarchiv erforderlich.

Hinweise zum Repository-Umfang, den Korpusdateien und den Voraussetzungen:
[Repository und Textkorpus](docs/repository.md). Die bestehenden
[Prüfbefunde zur Textgrundlage](docs/app-store/content-rights.md) bleiben Teil
der Dokumentation; diese Ablage vergibt keine neue Lizenz für Texte oder Code.

---

# Gesamtausgabe

Native Apple apps plus an Elixir catalog backend for an independent public-domain Rudolf Steiner edition.

## Product Constraints

- Reading, downloads and EPUB sharing require active `ga_access` or a server-confirmed free year. Catalog browsing stays available.
- Annual and supporter subscriptions share all features; eligible Apple accounts receive a three-month introductory trial that renews into their chosen annual plan.
- MVP platforms: iPhone, iPad, and Mac.
- Minimum OS target: iOS/iPadOS/macOS 26.
- UX direction: current WWDC 2026 HIG paradigm, while keeping OS 27-only APIs as later progressive enhancements.
- Text scope: Rudolf Steiner original text only.
- Languages: original languages only.
- User sync: CloudKit/iCloud private database.
- Elixir backend: separate reader and developer catalogs, content manifests, source/provenance status, and library delivery. No private user notes/bookmarks/highlights on the backend.

The proposed [solidarity subscription screen](docs/kaufscreen.md) documents the
30 €/year, 90 €/year, and free-on-request options, their copy, selection statistics,
and the original implementation decisions. The implemented behavior and release
configuration are recorded in [access implementation](docs/access.md) and the
[App Store release checklist](docs/app-store/release-checklist.md).

## Structure

- `apple/GA.xcodeproj` - SwiftUI app project with iOS and macOS targets.
- `apple/GA` - shared SwiftUI app source.
- `server` - API-only Phoenix backend.
- `research` - downloaded source metadata and sample analysis artifacts.

## Apple Build

The primary app icon for both Apple targets is the saved Icon Composer file
`apple/GA/ga.icon`. Both Debug and Release compile this file as `ga`; save icon
edits in Icon Composer before rebuilding to include the latest design.

The default Apple app surface is the end-user reader. The local catalog has
463 entries: 324 downloadable texts and 139 entries explicitly marked unavailable.
Four recovered working editions (GA 293, 294, 296 and 299) are included in the
deployed reader service's 324-text release.

The internal developer overview can be launched from the same target by setting:

```sh
GA_FRONTEND=developer
```

That overview loads the complete GA status backlog and shows import/proofing
state, source summaries, and sanity-check status.

```sh
xcodebuild -project apple/GA.xcodeproj -scheme "GA iOS" -destination "generic/platform=iOS Simulator" build CODE_SIGNING_ALLOWED=NO
xcodebuild -project apple/GA.xcodeproj -scheme "GA Mac" -destination "generic/platform=macOS" build CODE_SIGNING_ALLOWED=NO
```

The iPhone installation includes five complete core works, with all 77 sections
available offline. GA 120 downloads as a complete eleven-lecture volume. Rebuild
the reader-only Apple payloads after importing content:

```sh
python3 tools/export_apple_content.py
```

The reader uses `https://fototausch.eu/ga-reader` on every platform. Its complete
metadata catalog is bundled. Texts beyond the five complete offline books download
on demand and remain available offline. Set `GA_SERVER_BASE_URL` in the launch
environment or Info.plist to override the service. The developer frontend defaults
to `http://127.0.0.1:4000`; use that explicit override for local reader development.

Build and install a signed development app on the paired iPhone:

```sh
xcodebuild -project apple/GA.xcodeproj -scheme "GA iOS" \
  -destination "platform=iOS,name=Kant" -derivedDataPath /tmp/ga-kant \
  -allowProvisioningUpdates build
xcrun devicectl device install app --device Kant "/tmp/ga-kant/Build/Products/Debug-iphoneos/GA iOS.app"
xcrun devicectl device process launch --device Kant com.jonathankutscher.ga
```

## Reading Experience

The [local Korrekturwerkstatt](http://127.0.0.1:4173/proofreading/?ga=ga-040)
provides a browser proofreading view with a separate change log, checked samples,
open flags and durable editorial notes for every GA. Start it with
`python3 tools/proofreading_server.py`; see the
[proofreading workflow](docs/proofreading/README.md) for repairs and verification.

The reader now opens on **Jetzt lesen**, with a one-tap Continue Reading card,
recent works, and curated shelves. **Bibliothek** offers the original covers from
the Kutscherei iMac's Falz app: category-colored linen, textured gold lettering,
and the original cover fonts. The SwiftUI source, material generator, textures,
and font licenses are preserved in `vendor/kutscherei-covers`; its manifest
verifies every copied file against the source machine. The native adapter is
`apple/GA/KutschereiBookCover.swift`, with bundled materials for offline use.
The library also offers grid/list layouts, sorting, reading states, offline
filtering, and personal collections. Unavailable works have grey covers and
titles with a **Coming soon** label in the library, search and book details.
Downloadable works retain their normal appearance. The earlier EPUB image extraction is
recorded separately in `docs/cover-sources.json`.
The [iPhone Home](docs/screenshots/kutscherei-covers/home-iphone.png),
[cover grid](docs/screenshots/kutscherei-covers/library-grid-iphone.png), and
[list](docs/screenshots/kutscherei-covers/library-list-iphone.png) previews show
the native layouts with those covers.

**Suchen** searches work metadata, downloaded text, and personal notes locally.
Results open at the matching text location. References such as `GA 4`, `GA 004`,
`S. 15`, and `GA 120 S. 15` are supported. Source-page lookup identifies the
containing section; the existing source data does not provide a line-level
location for every historical page.

The immersive reader includes a contents sheet, chapter navigation, persistent
themes/font/spacing/margin settings, selectable text, colored highlights,
personal notes, bookmarks, edition notes, in-book search, and citation sharing
or copying. UTF-16 text anchors preserve reading positions across relaunches and
typography changes. Personal reading state is stored atomically on the device;
the catalog server never receives it.

Downloaded books show **Update verfügbar** when the server has a new edition.
Use **Buch aktualisieren** in the book actions or details; the library menu also
offers **Nach Updates suchen** and an **Updates verfügbar** filter. The saved
edition stays readable until the verified update is installed, including after a
failed download. Text and layout changes both count as new editions.

**EPUB teilen** is available in each book's actions, its details, and the reader
menu. The native share sheet exports the book as an EPUB with its table of
contents, chapters, and edition notes. Export uses available offline text and
downloads missing sections before sharing; personal notes and highlights stay
in the app.

A single tap on a marking opens its menu beside the text. **Markierung** offers
yellow, green, blue, pink, violet, and underlining. The menu also supports note
creation/editing, removal, and a book search prefilled with the marked quote.
The native text-selection menu offers **Markierung** and **Notiz hinzufügen**.
Notes show a quote with its colored rule, the edit time, a focused text editor,
and a checkmark to save; changed notes are also saved on dismissal. Color and
underline edits retain the same annotation and its note. Existing saved
highlights without a style field still load as highlights.

**Schreibtools** invokes the platform's real Writing Tools action when the
device and text context support it. The book remains read-only; Apple presents
results for copying or sharing. See [Apple's Writing Tools documentation](https://developer.apple.com/videos/play/wwdc2024/10168/).

CloudKit support uses the private database in `iCloud.com.jonathankutscher.ga`.
Both targets declare the same container. A valid signed iCloud entitlement and
an available iCloud account are required; otherwise the app keeps working locally.
The production schema now includes `GAReadingState` with fields `payload`
(`Asset`) and `schemaVersion` (`Int64`). Both distribution packages have signed
Production CloudKit entitlements and the same container. Synchronization between
two signed devices still needs the final TestFlight check; see the
[CloudKit verification](docs/app-store/cloudkit-readiness.md).

Validation:

```sh
python3 tools/check_reading_store.py
python3 tools/check_library_search.py
python3 tools/check_epub_export.py
python3 tools/check_epub_content.py
python3 tools/check_reader_scroll.py \
  --simulator-id <your-QA-simulator-UUID> --all-tests
```

UI checks use a dedicated simulator with the GA app installed. The wrapper
temporarily provides the GA 040a scrolling fixture and restores its previous
cache afterward. Omit `--all-tests` to run only the scrolling regression.

Reading goals, animated page turns, audio, and downloadable facsimiles remain
future enhancements.

## Backend

Fetch and compile dependencies:

```sh
cd server
mix deps.get
mix compile
```

Run catalog-only development mode without a local Postgres role/database:

```sh
GA_SKIP_REPO=true mix phx.server
```

API smoke checks:

```sh
curl http://127.0.0.1:4000/api/health
curl http://127.0.0.1:4000/api/catalog
curl http://127.0.0.1:4000/api/developer/catalog
curl http://127.0.0.1:4000/api/developer/catalog/ga-004/proofing
curl http://127.0.0.1:4000/api/catalog/ga-120/manifest
curl http://127.0.0.1:4000/api/catalog/ga-003/content
```

## Production Library

The reader retains five complete, normalized, public-domain books:

- GA 003 — *Wahrheit und Wissenschaft*
- GA 004 — *Die Philosophie der Freiheit*
- GA 009 — *Theosophie*
- GA 010 — *Wie erlangt man Erkenntnisse der höheren Welten?*
- GA 013 — *Die Geheimwissenschaft im Umriß*

Rebuild the deterministic source payloads with `python3 tools/import_steiner.py`,
then apply the documented proofreading pass for the reviewed text corrections.
Reader endpoints omit the retained source text to keep downloads small. The
developer proofing endpoint and `GA_FRONTEND=developer` diff inspector expose
the original and normalized version of every section side by side.

The complete existing Kutscherei collection adds 315 working editions, including
all eleven GA 120 lectures. Four newly recovered working editions add GA 293, 294, 296 and 299, with 42
sections. The local catalog has 4,988 downloadable sections.
Imported working editions retain source hashes and review warnings. The import
removed identified publisher sections, third-party prefaces and editorial notes,
but the final App Store audit found retained modern editorial material in GA 255b
and GA 267. Complete facsimile collation and mixed-source authorship review remain
outstanding. Publication permission for this material is not documented in the
repository; see the [content-rights findings](docs/app-store/content-rights.md).
No text is invented for the 139 remaining unavailable entries.

[Source recovery](docs/source-recovery.md) records downloaded source material,
reusable recovery scripts, reviewed import boundaries and the remaining gaps.

See [download library operations](docs/download-library.md) for deterministic
imports, native Phoenix endpoints, the reader-only production snapshot, and
publication/rollback commands. Validate the whole download collection with:

```sh
python3 tools/check_download_library.py
cd server
GA_SKIP_REPO=true mix test
```
