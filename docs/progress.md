# Progress

Last updated: 2026-10-09

## 2026-10 GA 039: Briefnummern und Inhaltsverzeichnis

- 68 am Originalscan belegte Nummern- und Punktfehler korrigiert;
  die ausgewählte Überschrift `45^.` lautet jetzt `452.`.
- 41 beim Import übersprungene Briefe aus der Quelle wiederhergestellt.
  Die ursprünglichen 102 Abschnittskennungen und Quelltexte bleiben erhalten.
- Alle 403 Briefköpfe in der originalen Folge 253–651 mit vier Nachträgen
  sowie drei redaktionelle Einträge bilden ein Inhaltsverzeichnis mit
  406 gültigen Sprungzielen. Der falsche Titel `1920 645…` heißt jetzt
  `Verzeichnis der Briefe`.
- Quellenbelege und unabhängige Rekonstruktion sind im
  [GA-039-Review](proofreading/ga-039-heading-review.md) dokumentiert.
- Gesamtabgleich aller 324 Bände, EPUB-Export, lokale Leseansicht und native
  Downloadprüfung bestanden; lokaler Leserexport und Apple-Katalog aktualisiert.
  Die 323 anderen kanonischen Bände bleiben unverändert.

## 2026-10 GA 038: Bindestriche

- 86 am Originaldruck belegte Trennungsfehler in 24 Abschnitten korrigiert;
  echte Bindestriche und die historische ck-Trennregel berücksichtigt.
- Zwei im Scan vorhandene, im übernommenen Text fehlende Satzfortsetzungen
  ergänzt. Alle 49 Quelltexte und Abschnittskennungen bleiben erhalten.
- Originalbelege, eingefrorene Prüfsummen und unabhängige Rekonstruktion sind
  im [GA-038-Review](proofreading/ga-038-hyphen-review.md) dokumentiert.
- Gesamtabgleich aller 324 Bände, EPUB-Export, lokale Leseansicht und native
  Downloadprüfung bestanden; lokaler Leserexport und Apple-Katalog aktualisiert.

## 2026-10 Satzumbrüche ab GA 050

- Alle 283 vorhandenen Bände ab GA 050 mit 3.854 Abschnitten sind geprüft; 65 weitere
  Katalogeinträge in diesem Bereich haben noch keinen Lesetext.
- 616.230 Prosaumbrüche mitten im Satz sind verbunden. 8.102 geprüfte Schutzbereiche
  erhalten Verse, Mantren, Sprachübungen, Tabellen, Listen und Notationen.
  Gemischte Notizblöcke wurden granular geprüft, sodass ihre Prosa ebenfalls
  zusammenhängend lesbar ist.
- 1.316 exakt belegte Druckköpfe und Seitenzahlen sind entfernt. 71 zusätzliche
  Zahlenspannen wurden unabhängig an 30 hashgleichen EPUBs überprüft;
  echte Registerverweise, Jahreszahlen, Rechnungen und Fußnoten bleiben erhalten.
- 19 belegte Satzfortsetzungen an falschen Abschnittsgrenzen sind repariert, in
  GA 061, 079, 084, 227, 255b, 261, 267 und 331a. Abschnittskennungen,
  originale Quellentexte, Seiten und Anmerkungen bleiben erhalten.
- Rezept, bewahrter Eingang, unabhängige Rekonstruktion und bisherige
  Korrekturgeschichte sind im [Prüfablauf](proofreading/README.md) dokumentiert.
  Die Korrektur bleibt lokal, bis ein neuer Leser-Release veröffentlicht wird.
- Die unabhängige Satzprüfung besteht für alle 283 Bände ohne Befund. Der lokale
  Leserexport und Apple-Katalog sind aktualisiert; alle 324 vollständigen Downloads
  bestehen die Prüfung mit den tatsächlichen Swift-Lesermodellen.
  Der historische Gesamtabgleich aller 4.942 Abschnitte und 39 gezielte
  Regressionstests bestehen ebenfalls.

## 2026-10 Readability Pass and Korrekturwerkstatt

- Audited all 463 catalog entries: 324 available GAs with 4,942 sections and
  139 entries without text. Corrected 296 volumes and 4,131 sections locally.
- Verified all 319 imported EPUB witnesses against their recorded SHA-256.
  Fixed the shared importer error that treated HTML source whitespace as text
  line breaks and doubled explicit verse breaks. The source-aware pass removed
  2,139,314 extraction line breaks, while preserving source-defined paragraphs,
  verse lines, and CSS `source-lines` in 26 volumes.
- Removed 119,803 discretionary hyphens. Joined 126,819 source-wrapped words
  using independent corpus attestations and a conservative frequency ratio,
  plus 280 occurrences of reviewed recurring syllabic forms. Kept meaningful
  compounds, suspended compounds, historical spelling and uncertain splits.
- Corrected 1,937 occurrences of six printed-source-verified OCR words, including
  `fiir` → `für` and `dafi` → `daß`. Seven affected words became recognizable
  only after the documented word joins.
- GA 040 now has readable prose within the verified preface/talk boundaries,
  genuine verse lines and all 52 calendar stanzas. Removed 80 extra internal
  blank lines from the weekly poems and 279 confirmed prose line wraps. Other
  uncertain poem boundaries and OCR readings remain flagged.
- Added the [local Korrekturwerkstatt](http://127.0.0.1:4173/proofreading/?ga=ga-040)
  with a separate change log, before/after samples, full reader text, source
  checks and open review flags for every GA. Notes support exact quotations,
  UTF-16 anchors, editing, resolved status and JSON/Markdown export. Private
  SQLite notes survive restarts and stay outside Git and reader user state.
- Independent validation passed all 324 payloads and 4,942 sections: original
  source text, IDs/order, titles, pages, annotations and metadata were retained;
  every lexical edit was accounted for by a documented correction. Reviewed
  39 reading samples across 13 volumes, plus separate changed-word samples in
  15 representative GAs and structural checks of all 52 weekly stanzas.
- Passed 15 importer, three recovery, six GA 040 and eight proofreading/notes
  regressions; all 27 Phoenix tests and the complete native download-library
  checks. Real-library browser QA passed selection anchors, notes, review status,
  drafts, reports, mobile layout and absence of JavaScript errors. Screenshots
  were visually inspected. A fresh-cache rerun preserved all 324 content files,
  six library files and 464 report files byte for byte.
- Refreshed the Apple content/catalog exports and generated a validated local
  reader snapshot at `/tmp/ga-proofreading-reader-export`. This local correction
  pass has not published a new reader release.
- The per-GA reports retain 30,603 review-lead matches in 290 volumes; these are
  uncertain patterns, not confirmed errors. The 139 absent texts are explicit.
  GA 040a's unrecognizable manuscript OCR requires source transcription; remaining
  source/OCR and illustration gaps are visible in the web workspace.
- Reproduction, source evidence and sample checks are documented in the
  [proofreading workflow](proofreading/README.md),
  [corpus audit](proofreading/corpus-pattern-audit.md),
  [GA 040 source review](proofreading/ga-040-source-review.md) and
  [independent sample validation](proofreading/sample-validation.md).

## 2026-10 Availability Labels and Reader Release

- Unavailable works have grey covers and titles with a **Coming soon** label in
  the library grid, list, search results and book details. Available downloads
  keep their normal appearance; details and collection actions remain accessible.
- Published the recovered library as `20261008T153608Z-7cf95c1c9ab7`, with 463
  catalog entries, 324 readable volumes and 139 unavailable entries. All 1,252
  uploaded files passed remote hash checks; the preceding release remains intact.
- iOS and macOS builds, the signed Kant build, all 27 server tests, native
  library download checks and library search checks passed.
- The deployed library passed all 324 download HEAD/manifest checks, 15 complete
  public JSON checksum samples, unavailable/private 404s and conditional requests.

## 2026-10 Recovery of Unavailable Sources

- Recovered original German source texts, EPUBs, scans and lecture witnesses for
  previously unavailable entries; detailed provenance and remaining gaps are in
  [source-recovery.md](source-recovery.md) and [unavailable-sources.json](unavailable-sources.json).
- Added four scoped working editions locally: GA 293 (15 sections), GA 294 (15),
  GA 296 (6) and GA 299 (6). The local catalog now has 324 readable works,
  4,942 sections and 139 unavailable entries. The live reader service also has 324.
- Source hashes bind import boundaries. Publisher/Marie Steiner sections and an
  editorial transition are excluded. Preserved bare EPUB body text that the
  prepared-library importer otherwise omitted, plus actual source page markers.
- All 320 previous content files remain byte-identical. The five normalized
  offline books retain their section IDs and content. Recovered editions carry
  explicit outstanding collation warnings; source images remain in the EPUBs.
- Passed 27 server tests, the native full-library checks and three focused recovery
  regressions. The 324-book public snapshot is now published in the release above.

## 2026-10 Complete Server Download Library

- Included the full existing collection: 463 catalog entries, 320 downloadable
  books with 4,900 sections, and 143 explicitly unavailable entries.
- Preserved the five complete normalized offline books (77 sections). Removed
  the GA 120 excerpt; its complete eleven lectures download as one volume.
- Imported the prepared Kutscherei EPUBs without changing the source collection.
  Source-bound starts and 674 exclusions remove identified publisher/editorial
  sections. The 315 imported working editions retain review warnings, source
  hashes, actual page anchors, author annotations and developer source diffs.
- Added compact deterministic gzip payloads and a release-contained catalog;
  server runtime no longer relies on external research metadata. Manifests and
  downloads provide valid section/bundle checksums and fail safely on bad data.
- Bundled the full lightweight catalog, enabled the public server on every
  reader platform, supported unavailable entries and full-volume downloads, and
  preserved private reading state. Explicit partial payloads and old excerpt
  caches cannot be offered as readable books.
- Published the reader-only snapshot at `https://fototausch.eu/ga-reader`, release
  `20261008T125549Z-754dd3543583`. All 1,248 uploaded files passed remote hashes.
  The existing EPUB service remains available with its 463/320 catalog.
- Passed 27 server tests, six import/finalization regressions, all 320 Swift
  payload checks, 17 source-scope checks, all source hashes, iOS/Mac builds,
  all 320 live HEAD/manifest checks and eleven full public JSON checksum samples.
- The native QA test removed only its GA 001 download, freshly downloaded all
  28 sections from the public server, relaunched against an unreachable server,
  and reopened its saved text. It passed with no runtime warnings.
- Installed the signed update on Kant, preserving app data. The existing source
  collection is trusted for volume completeness; source provenance is retained.
- Operations and validation commands are in [download-library.md](download-library.md).

## Product Direction

- Build an independent public-domain Rudolf Steiner Gesamtausgabe app.
- Start with iPhone, iPad, and Mac.
- Deployment target: iOS/iPadOS/macOS 26.
- Design direction: WWDC 2026 HIG/UX paradigm, with OS 27-only APIs left as progressive enhancements.
- Business model: freemium, but no paywall boundaries implemented yet.
- Text policy: only Rudolf Steiner's original text is eligible for publication.
- Languages: original languages only.
- User data sync: CloudKit/iCloud private database.
- Backend role: Elixir/Phoenix server for a reader-safe catalog, a complete developer status catalog, content manifests, source/provenance status, and library delivery. The backend should not own private user notes, highlights, bookmarks, or reading positions.

## Source Research

Internet Archive research artifacts were downloaded into `research/`.

Findings:

- Internet Archive advanced search found 335 `rudolf-steiner-ga-*` items.
- 334 item manifests were cached during research.
- The cached metadata summary reports:
  - 332 items with full text, DjVu XML, ABBYY GZ, PDF, JP2 ZIP, and scandata.
  - 207 items with Word documents.
  - 155 items with EPUBs.
  - 329 items with page counts, totaling 92,265 pages.
- Raw IA `_djvu.txt` OCR is not reader-quality for German display text. Sampled files were ASCII-only and contained artifacts such as `dafi`, `fiir`, and `Nachlafiverwaltung`.
- PDF embedded text and Word document extraction are much better candidate sources because they preserve umlauts and `ß`, but they still include publisher/editorial/front-matter material and require scope cleanup.
- Facsimile/page images are useful for verification and page anchoring, not as the primary accessibility layer.

Committed research artifacts:

- `research/ia_advancedsearch.json`
- `research/ia_metadata_summary.json`

Ignored local research artifacts:

- Raw PDFs, DOCs, OCR XML, extracted full-volume text, rendered page images, and per-item manifests.
- These are intentionally ignored until a rights/scope-clean ingestion workflow exists.

## Apple App

Created a native SwiftUI app in `apple/GA.xcodeproj`.

Targets:

- `GA iOS`
- `GA Mac`

Implemented:

- Separate SwiftUI frontends for the two audiences:
  - End-user reader app: only shows works with a current usable text bundle.
  - Developer overview: shows the complete GA backlog with publication/proofing/source status.
- Adaptive `NavigationSplitView` library/detail/reader shell.
- Seed catalog with important/popular MVP candidates:
  - GA 004 `Die Philosophie der Freiheit`
  - GA 010 `Wie erlangt man Erkenntnisse der höheren Welten?`
  - GA 013 `Die Geheimwissenschaft im Umriß`
  - GA 009 `Theosophie`
  - GA 003 `Wahrheit und Wissenschaft`
  - GA 120 `Die Offenbarungen des Karma`
  - GA 293 `Allgemeine Menschenkunde als Grundlage der Pädagogik`
- On-demand full-text download for GA 003 `Wahrheit und Wissenschaft`.
- Readable seed passage for GA 120.
- Import/proofing states for queued works in the developer overview.
- AI sanity-check status shown in the developer volume detail UI.
- Reader typography using a calm serif text surface and selectable text.
- Compact iPhone navigation moves into the reader after a passage download or passage selection.
- Placeholder toolbar actions for bookmarks and facsimile jump.
- App Intents entity/query scaffold for GA volumes.

Verified:

```sh
xcodebuild -project apple/GA.xcodeproj -scheme "GA iOS" -destination "generic/platform=iOS Simulator" build CODE_SIGNING_ALLOWED=NO
xcodebuild -project apple/GA.xcodeproj -scheme "GA Mac" -destination "generic/platform=macOS" build CODE_SIGNING_ALLOWED=NO
```

Manual launch:

- Mac app built and opened from `/tmp/ga-mac-run-dd/Build/Products/Debug/GA Mac.app`.
- iOS app installed and launched on the booted iPhone 17 simulator.
- Bundle id: `com.jonathankutscher.ga`.

## Elixir Backend

Created an API-only Phoenix app in `server/`.

Implemented endpoints:

- `GET /api/health`
- `GET /api/catalog` for the reader-safe catalog.
- `GET /api/catalog/:id`
- `GET /api/catalog/:id/manifest`
- `GET /api/catalog/:id/content`
- `GET /api/developer/catalog` for the complete GA status overview.
- `GET /api/developer/catalog/:id`

Implemented backend modules:

- `GA.Catalog`
  - Reader-safe catalog data.
  - Complete developer catalog synthesized from the Internet Archive research backlog plus curated work status overrides.
  - Content policy metadata.
  - Content manifest generation.
  - Complete GA 003 JSON text payload served from `priv/content/ga-003.json`.
- `GA.ContentPipeline`
  - Deterministic contract for future AI-first sanity checks.
  - Checks include source provenance, original-text scope, German diacritics, OCR artifacts, page anchors, dehyphenation, and duplicate paragraphs.

Development note:

- Local Postgres did not have the default `postgres` role.
- Added `GA_SKIP_REPO=true` so catalog/API development can run before the local database is configured.
- Normal Repo startup remains available when `GA_SKIP_REPO` is not set.

Verified:

```sh
cd server
mix deps.get
mix compile
GA_SKIP_REPO=true mix phx.server
curl http://127.0.0.1:4000/api/health
curl 'http://127.0.0.1:4000/api/catalog?q=freedom'
curl http://127.0.0.1:4000/api/catalog/ga-120/manifest
curl http://127.0.0.1:4000/api/catalog/ga-003/content
```

## Current Commit

Initial implementation commit:

```text
12d8677 Initial GA app and catalog backend
```

## Next Slice

Recommended next implementation slice:

1. Complete scan-aligned human review using the developer diff inspector.
2. Provision Mac iCloud signing, deploy the production CloudKit schema, and
   verify reading-state sync between real devices.
3. Introduce a SQLite/FTS5 index when the downloaded library grows beyond the
   current local text-search scope.
4. Add downloadable facsimile page bundles and page-to-scan navigation.

## 2026-07 Production Content Pass

- Published five complete core works: GA 003, 004, 009, 010 and 013.
- Added a deterministic importer with 77 structured sections, checksums,
  provenance, page anchors, safe normalization and automated OCR checks.
- Retained the untouched section source for audit while excluding it from
  reader downloads.
- Added `/api/developer/catalog/:id/proofing` and an in-app developer
  side-by-side normalization inspector.
- Added persistent reader text sizing and previous/next section navigation.

## 2026-10 iPhone UI Repair and Kant Installation

- Applied the iPhone findings from `docs/ui-audit-2026-07-24.md`.
- Added a generated launch screen, app icons and accessible accent colors.
- Compact launch now keeps the library visible until explicit work selection;
  search/filter changes clear hidden selections.
- Removed title truncation, repaired library row sizing and made metadata and
  section navigation adapt to accessibility text sizes.
- Replaced the crowded reader toolbar with Reading Settings and a notes sheet;
  unavailable bookmark/facsimile actions are absent.
- Promoted the current section heading, added German speech-language metadata,
  selected/heading traits and larger touch targets, and reset passage scrolling.
- Included the five complete works plus the GA 120 excerpt as reader-only
  bundled text: all 78 sections decode and round-trip through the cache format.
- Physical installations use the bundled library unless a server is explicitly
  configured. Simulator/Mac development retain the local catalog connection.
- Built the iOS simulator, signed iOS device and Mac targets successfully.
- Installed and launched `com.jonathankutscher.ga` on Kant (iPhone 17 Pro).
- Verified library launch, compact rows, settings/page numbers and fresh section
  navigation on the simulator; reviewed Accessibility XXXL in light/dark.
- Preserved the existing content/backend work and local reading data.

## 2026-10 Apple Books Reading Experience

- Added **Jetzt lesen**, **Bibliothek**, and **Suchen** with Continue Reading,
  recent works, curated shelves, cover/list layouts, sorting, reading states,
  offline filtering, and personal collections.
- Extracted the six original cover images from the existing EPUB collection on
  the Kutscherei iMac. They are bundled unchanged; `docs/cover-sources.json`
  records their source paths, checksums, dimensions, and title verification.
- Added local metadata, full-text, personal-note, GA-number, and source-page
  search. Text hits open at their UTF-16 location; historical page references
  identify the containing section because the source has no exact per-page
  text offsets.
- Replaced the reader with selectable native text, hideable controls, contents,
  progress, typography/themes, highlights, notes, bookmarks, source notes,
  in-book search, and citation sharing/copying. Recoloring a selected range
  updates its existing annotation and preserves its note.
- Added atomic local personal-state storage, reading-position restoration,
  private CloudKit synchronization, conflict/deletion merges, and protection
  against uploading previous-account notes after an iCloud-account change.
  Unavailable iCloud leaves local reading fully functional.
- Preserved downloaded books and cached catalog metadata during catalog
  outages, along with the existing bundled texts and developer surface.
- Passed persistence/merge/recovery checks and bundled-content/search/Unicode
  checks. Native iPhone UI tests exercised grid/list/filter/search navigation,
  chapter selection, settings, bookmarks, resume after dismissal and process
  relaunch, edition notes, and saving/reopening/deleting a note from real text
  selection. The selection-toolbar overlap found during QA was repaired.
- Verified yellow-to-green recoloring followed by note creation preserves the
  selected color, reuses one annotation, and survives reopening. Bookmark and
  note rows use compact actions with 44-point touch targets; the final row
  spacing check passes. UI tests remove only their uniquely named test notes.
- Reviewed dark mode at accessibility text sizes, including the transition
  from Papier to Automatisch. Reader theme overrides now stay within the reader
  instead of changing the modal presentation's system appearance. Settings use
  the full-height sheet at accessibility sizes.
- Built the signed iOS device and unsigned Mac targets without compiler
  warnings. Launched the iPadOS 26.5 app and reviewed its home layout; see
  [iPad home](screenshots/reading-experience/home-ipad.png) and the
  [iPhone cover library](screenshots/reading-experience/library-iphone.png).
- Installed the updated app on Kant. Automatic launch was denied because the
  phone was locked; the installed app can be opened normally after unlocking.
- Live two-device CloudKit sync remains unverified. Mac needs an iCloud-capable
  signing profile, and production distribution requires deploying the
  `GAReadingState` schema documented in `README.md`.
- Reading goals, page-turn animation, audio, and downloadable facsimiles remain
  later work.

## 2026-10 Kutscherei Cover Source

- Retrieved the actual SwiftUI cloth-and-gold cover renderer over SSH from the
  Falz app at `/Volumes/iMac/programmier-projekte/ga` on Kutscherei. The earlier
  EPUB image extraction remains documented separately.
- Preserved 44 unchanged source, metadata, texture, generator, research, font,
  and font-license files under `vendor/kutscherei-covers`. Every copied file's
  SHA-256 matches the source machine; paths and checksums are recorded in its
  `source-manifest.json`. The source app directory has no Git metadata.
- Added `KutschereiBookCover.swift` and connected the Home and library covers.
  The original cloth/gold composition, 180-point texture tiles, spine shading,
  gold masks, and font faces are retained. Covers use the original category
  ranges, including blue works and rose member lectures such as GA 120.
- Bundled all 14 linen tiles, shared gold foil, category metadata, four fonts,
  and both SIL font licenses in the iOS and Mac targets. Artwork typography uses
  fixed sizes; the semantic labels beside it still follow Dynamic Type.
- The original texture verifier passes for all 29 source tiles. Signed iOS and
  unsigned Mac builds pass without compiler warnings, and all 22 bundled
  material/font/license files match the source resource copies. iOS signature
  verification passes.
- Two focused iPhone UI checks pass. Rendered Home, grid, and list previews show
  the original linen and gold materials with no clipping at 64-point list or
  100-point Continue Reading widths. GA 120 correctly uses the member-lecture
  rose color. Previews are under `screenshots/kutscherei-covers`.
- Installed the signed cover update on Kant successfully, preserving the
  existing app's reading data.

## 2026-10 Annotation Menus

- Added a menu on a single tap of an existing marking. Its actions cover the
  marking palette, adding/editing a note, removal, selected-quote book search,
  and the system Writing Tools action.
- Moved new marking/note actions into the native text-selection menu. The
  marking palette offers yellow, green, blue, pink, violet, and underlining.
  Captured UTF-16 ranges survive responder and menu changes.
- Added a persistent annotation style with legacy decoding: existing records
  without a style still load as highlights. Recoloring and changing to/from an
  underline preserve the annotation ID and note.
- Reworked the note editor around the colored quote rule, edit time, focused
  text entry, and save checkmark. Changed drafts also save on dismissal.
- Connected UIKit/AppKit's native Writing Tools presentation with contextual
  availability checks. Book text stays read-only; the platform supplies the
  limited panel and copy/share results.
- Store checks cover legacy state/position preservation, purple underline
  persistence, same-ID edits, and sync merges/deletions. Library search and
  Unicode-position checks also pass.
- Preserved native long-press selection over existing markings. Mac mouse
  tracking completes before opening the single-click menu, so a marking can
  still be the starting point of a drag selection.
- Anchored the popup to the marked text and sized both palette and action
  pages to show every control. Reviewed light and dark previews under
  `screenshots/annotations`, including the focused quote note with its keyboard.
- The iOS note editor requests focus after its native controller appears,
  avoiding focus loss when a marking popover opens the note sheet. Checkmark
  saving and reopening preserve the original quote, note, color, and underline.
- Signed iOS and unsigned Mac builds pass without compiler warnings. iOS
  signature verification passes, and the final signed update is installed on
  Kant without resetting its reading data.
- Writing Tools' unavailable state is verified in the simulator. Presentation
  of the live Apple Intelligence panel still requires a supported device and
  system configuration.
- The focused native iPhone UI test passes end to end: text selection, all five
  colors and underlining, single-tap editing, automatic keyboard focus,
  checkmark saving, exact quote/note/style persistence on reopening, prefilled
  book search, and removal through the marking menu. The edits retain one
  annotation, and the test removes only its uniquely named QA note.
