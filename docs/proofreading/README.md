# GA-Korrekturwerkstatt

The local proofreading workspace shows **every GA separately**: reader text,
applied changes with before/after excerpts, replacement lists, automated samples,
source checks, open review flags, and your editorial notes. The unavailable
catalog entries remain visible with a clear missing-text status.

Start it from the repository root:

```sh
python3 tools/proofreading_server.py
```

Open [the Korrekturwerkstatt](http://127.0.0.1:4173/proofreading/?ga=ga-040).
Select a passage, mark a quotation and write a note, or create a general note
for the volume. Notes can be edited, marked resolved and exported as JSON or
Markdown. The reading view preserves verse lines and offers adjustable type.
The changes and review tabs link back to the relevant passage.

The visible contents selector includes source-derived internal headings. In
GA 040, the four seasons contain `Spruch 1` through `Spruch 52` with their
week/date labels and exact text targets. A selected heading survives a page
reload through its passage/UTF-16 offset in the URL. The native contents view
shows the calendar outline immediately, with the dates beneath each poem.

The review selector records your reading progress independently from automatic
checks. An automatically checked passage is not marked as manually proofread.
The source's original spelling is retained, including historical `ß` forms.

The 8 October pass checked 324 texts and corrected 296 volumes (4,131 sections).
It removed 119,803 discretionary hyphens, joined 127,099 documented word splits,
and corrected 1,937 verified OCR words. Source whitespace repairs removed more
than two million extraction breaks. Every GA has its own record, including the
139 unavailable entries. The current open flags are proofreading leads rather
than confirmed errors; full human reading remains separate from these checks.

## Source-bound structure and machine-readable metadata

The [GA 014 dramatic line-break review](ga-014-readability-review.md) removes
484 source-page running heads and separates verse dialogue, prose speeches,
speaker labels and stage directions across all 59 sections. The children's song
and genuine verse line endings survive. This reproducible pass runs after the
original-outline layer and keeps its intermediate input for independent checks;
All 63 overrun/OCR-parenthesis review leads have now been collated against the
scans. The source-bound inventory records 53 reconstructed verse continuations,
including the reported `Band,` and a previously unflagged `GlückErlebnis`,
11 stage-cue/punctuation repairs and three prose word joins across page seams.
Exact replacements and individual scan
evidence remain in the correction ledger; no leads of this class remain.

The [GA 001–026 original-outline review](ga-001-026-original-outline.md)
restores 607 edition-bound contents entries in the 25 available early volumes.
The proofreading view preserves original Roman/Arabic labels and unnumbered
front matter without adding an automatic section number. Its frozen recipe
also restores omitted parent headings and original internal insertions while
keeping every existing text character and note anchor. GA 019 remains unavailable.
`repair_early_structure.py` applies this metadata-only pass; the complete
`proofread_library.py` build and independent sample checker include it as well.

The [GA 027 prose line-break review](ga-027-readability-review.md) restores
the original printed paragraphs across all 20 chapters, preserves separate
headings, footnote and appendix entries, joins six evidenced page-seam words
and reconstructs the source correction-table rows. Its frozen recipe consumes
every retained character once and keeps the original source and chapter IDs.

The [GA 030 completeness and line-break review](ga-030-readability-review.md)
restores the missing introduction, author notes, editorial apparatus and name
index from exact EPUB spans. Its original three passage IDs and raw sources
remain intact; 92 original contents targets, printed paragraphs and reviewed
word divisions are bound to the frozen edition. The documented publisher
appendix gap after page 658 leaves the existing download contract intact.

The [GA 032 paragraph and verse review](ga-032-readability-review.md) restores
source-supported paragraphs and article navigation throughout all 57 retained
text containers. Every original source and annotation identity is preserved;
physical word seams, footnote wraps and mistaken year/page metadata require
exact original evidence.
The independent checker reconstructs all 1590 retained source elements.

The [GA 034 paragraph and original contents review](ga-034-readability-review.md)
restores the six original groups and 106 retained author targets, repairs false
physical wraps throughout all seven existing text containers, and preserves true
verse lines. Two already missing original notes remain explicitly documented
source gaps; all twelve existing notes retain their source identities.

The [GA 045 paragraph and word-seam review](ga-045-readability-review.md)
repairs physical prose wraps throughout all eleven retained containers,
preserves lists and the appendix's schematic lines, and restores one exact
main paragraph mistakenly excluded as a footnote. Its 181 semantic blocks and
299 word-seam corrections are bound to the retained 1980 DOC/EPUB; a revised
PDF edition is recorded separately. Original IDs, raw source text and all five
existing annotations remain unchanged.

GA 040 is the reference case for the reproducible structure pipeline. The
retained 1991 edition now has five main divisions, 52 separately headed calendar
poems, source-supported verse/stanza boundaries and continuous prose. Its 38
original passage IDs and `source_text` values remain unchanged. The result has
779 semantic blocks, 241 contents entries, 246 page anchors and two linked
source footnotes. All currently detected GA 040 repair flags are resolved;
manual full-text collation remains a separate review state.

`tools/source_layout.py` extracts paragraph spacing, explicit page breaks,
printed footer labels and exact text positions from a source DOCX. The portable
`tools/ga040_source_layout.json` keeps layout, mappings and hashes without
copying the source prose. `tools/build_ga040_recipe.py` binds those observations
to the reviewed prose, verse and heading roles. Separate poems require explicit
source-reviewed boundaries; a page break alone never creates a new poem.
`tools/ga040_poem_boundaries.json` records 142 register-supported starts and ten
excluded continuations; the 52 calendar weeks are handled separately. The work-independent
`tools/repair_source_structure.py` applies the frozen recipe, records every
lexical edit and checks that every source character is consumed exactly once
or is an explicitly documented numeric page footer.

An import passage is a stable text container, not necessarily one literary work.
`tools/ga040_work_sections.json` binds the two calendar prefaces and four seasons,
plus seven independent units on pages 74–78,
to the original body and register. The portable recipe turns them into validated
`reading_sections` with complete UTF-16 ranges. Only the four column sayings
belong to *Die vier Sprüche der Säulenweisheit*; the following sayings and
*Tischgebet* are siblings in the contents. A `source_title` is an actual source
heading; an `incipit` is the exact first verse used for orientation in the
contents. That verse retains ordinary body typography and is never promoted to
a heading. Readers keep work separators without adding an invented title or
repeating the line. Import-order numbers are not contents labels; source poem
numbers, including the 52 calendar weeks, remain. All original passage IDs,
text, selection offsets and notes survive.
The calendar prefaces and seasons are siblings under the calendar main division;
weekly dates and poem numbers descend from their season. Explicit reading
sections normalize their first child heading to the next outline level, avoiding
a skipped level inherited from the old import container.

To apply or repeat the GA 040 structure pass on the existing library:

```sh
python3 tools/repair_source_structure.py --output /tmp/ga040-new-stage
python3 tools/check_proofreading_samples.py --stage /tmp/ga040-new-stage
python3 tools/proofread_library.py --apply-stage /tmp/ga040-new-stage
```

The complete `proofread_library.py` rebuild also runs the structure recipe after
source whitespace and word repairs. It saves that intermediate input in
`research/proofreading-layout-baseline`; the independent checker uses it to
verify the structural pass separately from the historical corpus corrections.
Use matching `--layout-baseline` options on builder and checker when choosing a
different cache. Source acquisition needs `lxml`; the frozen structure engine
and independent checker use the Python standard library. Applying the frozen
recipe requires neither Word nor LibreOffice.

Source and input hashes stop an unreviewed edition or text change. Repeating the
GA 040 pass produces identical payloads, catalog and change reports. A revised
recipe is replayed from its hash-checked intermediate input; prior structural
change records remain in `structure_history`, while `layout_input_sha256` and
`application_base_sha256` protect the input and current applied result separately. A changed
edition requires new evidence and an explicitly reviewed recipe. Small gaps or
repeated words alone never authorize joining poems or replacing their wording.

Reader JSON contains the following fields, all anchored in the final canonical
text with UTF-16 offsets:

| Field | Meaning |
| --- | --- |
| `table_of_contents` | Ordered tree of divisions, passages and internal headings; unique IDs, parent IDs and passage/offset targets. |
| `passages[].metadata.reading_blocks` | Complete nonoverlapping heading, prose, verse and attribution ranges; heading levels and independent-poem starts. |
| `passages[].metadata.page_anchors` | Printed page and exact text position, original-source section, source kind and observed/inferred confidence. |
| `passages[].metadata.annotations` | Original note ID, marker, cleaned definition and exact marker range for links and backlinks. |
| `metadata.source_layout` | Original DOC hash, source URL, recipe revision and offset unit. |

Page positions survive prose reflow and word repair, including a page boundary
inside a word. The page identity can be observed or inferred between consistent
original footer labels; the confidence stays visible. Web and native readers
use the semantic ranges, while EPUB exposes nested navigation, pagebreaks,
a page list and footnotes. Source metadata does not replace the canonical text;
selection and personal notes use the same UTF-16 coordinate system.

The server validates the metadata and retains the canonical anchored text.
Malformed ranges, unknown contents targets, page-order errors and broken note
markers are rejected. Older unstructured books remain readable through the
existing text path.

## Satzumbrüche ab GA 050

Der zusätzliche Durchgang vom 8. Oktober 2026 umfasst alle **283 vorhandenen
Bände ab GA 050 mit 3.854 Abschnitten**. Die 65 weiteren Katalogeinträge in
diesem Nummernbereich haben keinen Lesetext und wurden nicht als geprüft
ausgegeben.

616.230 nicht abschließende Prosaumbrüche wurden verbunden. Dazu gehören
druckbedingte Zeilen- und Seitenwechsel, getrennte EPUB-Absätze,
Abkürzungen und fortgesetzte Zitatsätze. Echte Satzenden bleiben erhalten.
8.102 eingefrorene Schutzbereiche bewahren Verse, Mantren, Sprachübungen,
Tabellen, Listen, Überschriften und Notationen; gemischte Notizblöcke wurden
auf ihre tatsächlichen strukturierten Zeilen begrenzt, damit die Prosa darin
ebenfalls lesbar wird. Bewusste Strophenabstände bleiben unverändert.

1.316 störende Druckköpfe und Seitenzahlen wurden exakt quellengebunden
entfernt. Die 71 zusätzlichen Zahlenspannen sind mit Originalposition,
Eingabehash und EPUB-Beleg in `tools/ga050_plus_page_labels.json` dokumentiert;
Registerverweise, Jahreszahlen, Rechnungen, Fußnotenzeichen und Diagrammziffern
bleiben erhalten. Alle 30 betroffenen EPUB-Hashes und sämtliche Belegauszüge
wurden unabhängig geprüft.

19 fehlerhafte Abschnittsgrenzen wurden repariert. Dazu gehören OCR-Seitenzahlen,
die als Überschrift erkannt wurden, verfrüht angesetzte Unterabschnitte in
GA 255b und GA 261 sowie die als Überschrift importierte Fortsetzung in GA 227.
Die belegte Fortsetzung steht nun am Ende des vorherigen Abschnitts. Kennungen,
Reihenfolge, originale `source_text`-Felder, Seitenmetadaten und Anmerkungen
bleiben bestehen. Nur nachgewiesene falsche Abschnittstitel erhalten einen
passenden Fortsetzungstitel. Bereits in der Quelle fehlende oder beschädigte
Wörter werden durch diesen Formatdurchgang nicht erfunden.

Die portable, editionsgebundene Rezeptdatei ist
`tools/ga050_plus_sentence_breaks.json`. Sie fixiert jede verbundene
Umbruchstelle und jeden Schutzbereich. Der unveränderte Eingang steht lokal in
`research/proofreading-sentence-baseline`. Der unabhängige Prüfer rekonstruiert
alle Eingriffe, vergleicht den Zeichenbestand und prüft Verse einschließlich
der an Abschnittsgrenzen verschobenen Fragmente. Der bisherige Korrekturverlauf
wird als eigene historische Schicht weiter geprüft.

```sh
python3 tools/repair_sentence_breaks.py --output /tmp/ga-sentence-new-stage
python3 tools/check_sentence_breaks.py --stage /tmp/ga-sentence-new-stage
python3 tools/check_proofreading_samples.py --stage /tmp/ga-sentence-new-stage
python3 tools/repair_sentence_breaks.py --apply-stage /tmp/ga-sentence-new-stage
python3 tools/test_sentence_breaks.py
```

Die Anwendung überprüft alle betroffenen Bände vor dem Schreiben und erhält
gleichzeitige Änderungen an früheren Bänden. Katalog, Einzelprüfberichte und
Prüfsummen werden gemeinsam aktualisiert. Dieser Durchgang ist lokal;
die Veröffentlichung des Leserkatalogs bleibt ein eigener Release-Schritt.

Die Abschlussprüfung besteht ohne Befund: unabhängige Satzrekonstruktion für
alle 283 Bände, historischer Gesamtabgleich aller 324 vorhandenen Texte mit
4.942 Abschnitten und 39 gezielte Regressionstests. Der lokale Leserexport
und der Apple-Katalog sind aktualisiert; die tatsächlichen Swift-Lesermodelle
prüfen alle 324 vollständigen Downloads erfolgreich.

## Saved notes and future correction passes

Editorial notes and review states are stored in
`server/var/proofreading.sqlite3`, excluded from Git. They survive browser and
server restarts. Export through **Notizen exportieren** before moving to another
computer. This local service is bound to `127.0.0.1`; it does not publish notes
or change the Apple reader's private CloudKit reading state.

Each quotation keeps its passage ID, original checksum and UTF-16 offsets.
Offsets distinguish repeated quotations and support German text and emoji.
The server rejects mismatched new quotation anchors and outdated checksums.
Unsaved drafts also survive passage/band navigation in the browser.

The notes are a correction backlog, rather than direct text edits. Exported
notes contain the GA, passage and quotation needed for a subsequent correction
pass. The full text stays selectable for proofreading.

## Repeat the automated work

The acquisition and build scripts require the same Python with `lxml` used for
the existing EPUB importer. The local workspace itself uses Python's standard
library only.

```sh
python3 tools/fetch_proofreading_sources.py
python3 tools/proofread_library.py --output /tmp/ga-proofreading-new-stage
python3 tools/check_proofreading_samples.py --stage /tmp/ga-proofreading-new-stage
python3 tools/proofread_library.py --apply-stage /tmp/ga-proofreading-new-stage
python3 tools/export_apple_content.py
```

Choose a fresh staging directory each time. Before applying, inspect the samples
and reports. The first-run source cache is `research/proofreading-sources`, and
the unchanged before-state is `research/proofreading-baseline`; both are local,
ignored research artifacts. Source EPUB hashes must match the reading editions.
The source originals, passage IDs and publication scope are preserved.
Source-bound structure repairs can correct page metadata and note presentation;
the original evidence and exact changes remain in their own ledger. Unexpected source, lexical or content drift stops the pass before
application. A stage with a complete `proofreading/catalog.json` is eligible for
application; a partial stage is not.

Reruns retain the original per-GA history. An already cleaned checkout without
the local before-cache reuses its committed report after verifying the payload
hashes. Text edited outside that history is rejected for explicit review. For a
new edition/import, preserve the old report and choose a separate baseline with
`--baseline` rather than overwriting the old comparison.

The generated `server/priv/proofreading/catalog.json` and
`server/priv/proofreading/works/ga-*.json` are the web view's per-GA records.
Reader payloads and catalog checksums are updated together. Refresh the public
snapshot and bundled catalog with the existing export workflow after applying
and verifying a pass. Publishing that snapshot remains a separate release step.

## What was checked

- [Corpus pattern audit](corpus-pattern-audit.md): inventory, representative
  defects, and conservative correction rules.
- [GA 040 source review](ga-040-source-review.md): actual verse/prose boundaries,
  52 calendar stanzas, facsimile evidence and confirmed OCR words.
- [Sample validation](sample-validation.md): independent checks on the staged
  corpus and examples across source families.

The remaining flags identify uncertain splits, possible repeated paragraphs,
OCR defects, source-font symbols, missing illustrations and doubtful page
metadata. Some hits are intentional typography; a flag is a review lead rather
than an instruction to delete or replace the text. GA 040a includes manuscript
OCR that needs a new transcription from the facsimile. Formatting repairs alone
cannot certify that source.

## Verification commands

```sh
python3 tools/test_import_library.py
python3 tools/test_import_recovered_volumes.py
python3 tools/ga040_readability.py --self-test
python3 tools/test_proofreading.py
python3 tools/source_layout.py --self-test
python3 tools/test_source_structure.py
python3 tools/test_ga014_readability.py
python3 tools/test_check_proofreading_samples.py
python3 tools/check_reading_structure.py --content server/priv/content/ga-040.json.gz
python3 tools/check_download_library.py
cd server
GA_SKIP_REPO=true mix test
```

For browser interaction QA, use a separate notes database and port. The check
script requires Playwright and an installed Chrome/Chromium; it otherwise checks
read-only behavior by default.

```sh
python3 tools/proofreading_server.py --port 4175 --database /tmp/ga-proofreading-qa.sqlite3
# In a separate terminal, with Playwright available:
node tools/check_proofreading_ui.mjs --url http://127.0.0.1:4175 --allow-test-writes
```

This test creates only its uniquely named notes in the disposable database,
removes them and restores the prior review status. It checks the real catalog,
selection anchors, editing/resolving notes, drafts, report tabs and mobile layout.
