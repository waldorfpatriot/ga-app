# GA 040 – source review and readability repairs

Reviewed on 8 October 2026. These checks establish the formatting repairs below;
they are not a full textual collation of every poem or a certification of OCR.

## Source evidence

The retained working edition is the 1991 *Wahrspruchworte* DOC from
[the original collection](http://bdn-steiner.ru/cat/ga/040.doc), SHA-256
`9263a2efd8f66c17f6c686a4bf1c169f477331f1e2aa1bf4fea01fcfe950229a`.
Its companion EPUB comes from
[the existing GA source collection](https://fototausch.eu/api/ga/books/ga-40/download).
Its SHA-256 is
`5693d6d6f9586f73f1e68a00fe16492f90d12fc080d384ae95730a19c4e763ee`,
identical to the source hash already recorded in the content payload and
`tools/library-scope.json`.

In `EPUB/chapter-0001.xhtml`, the source contains ordinary text-node wrapping
such as `So\nfinde im Niedergang`, and an explicit `<br/>` after the completed
verse. HTML treats the first LF as a space and the `<br/>` as the actual verse
boundary. The old extractor retained both source whitespace and an additional
LF before the `<br/>` tail. This created mid-verse line breaks and blank lines
between verse lines. Re-extraction now follows the HTML distinction.

The [rendered 1998 edition](https://odysseetheater.org/GA/Buecher/GA_040.pdf)
was also inspected at PDF pages 23, 34 and 48 (weekly poems 1/2, 23/24 and
51/52). Each numbered calendar poem has contiguous verse lines; dates and
successive poems have separate spacing. This corroborates the stanza grouping
present inconsistently as `<p>` per verse and `<br/>` inside a stanza in the
bound EPUB. The 1998 edition has different date labels and some textual variants;
its wording and dates were not substituted into the 1991 working edition.

## Repairs and scope

`tools/import_library.py` collapses normal raw HTML whitespace, preserves actual
`<br/>` line breaks, and retains paragraph boundaries. Literal whitespace in
`<pre>`, `xml:space="preserve"`, and supported CSS `white-space` modes is retained.
Linked local stylesheets and embedded style rules support deterministic simple
tag, class and ID selectors with inheritance, specificity and `!important`.
Unsupported CSS selectors or conditions are recorded as `whitespace_warnings`.

A corpus scan of all 319 source EPUBs found one external whitespace rule:
`.source-lines {white-space:pre-line}`, in 315 stylesheets. The class is actually
used in 26 volumes: GA 014, 027, 040a, 073a, 100, 104a, 105, 163, 164, 165,
168, 170, 171, 172, 173, 174, 195, 253, 255b, 260, 261, 262, 301, 331a,
335 and 338. Those literal source lines are preserved. GA 040 does not use this
class. The source-aware importer was independently checked on all 26 affected
volumes and produced no non-whitespace drift.

`tools/ga040_readability.py` adds source-reviewed rules:

- The two author prefaces in `ga-040-doc-heading-2` reflow only before the unique
  `FRÜHLING` boundary. The talk in `ga-040-doc-heading-6` reflows only before
  `PLANETENTANZ`. The remainder of both mixed sections remains verse.
- The bibliographic prose in sections 5, 7, 28 and 40, and the *Credo* prose in
  section 41, reflows inside existing paragraphs. Opening-text guards prevent
  silently applying these rules to a changed edition.
- The 52 calendar poems in section 2 retain each verse line, but blank lines
  accidentally introduced by `<p>` per verse become single LF inside the
  numbered stanza. Date/season headings and boundaries between poems remain
  double LF. The rule verifies all 52 sequential poem numbers, all 52 date
  headings, the four seasons, and the known line count of every stanza.

The initial calendar helper removes 80 accidental internal blank lines. The
following source-bound structure pass then separates every number into its own
heading, corrects `5 2` to `52`, and links the source's two `*` markers to their
footnotes. The visually checked narrow calendar repairs are `rinden.` →
`finden.`, `WinterhorTnung` → `Winterhoffnung`, and `heiPge` → `heil'ge`.
The retained 1991 wording, including historical spelling, remains the basis.

## Complete structure recipe

`tools/ga040_structure.json` covers all 38 retained passages. It preserves the
five main divisions of the original 1991 edition; the later 1998 edition's
changed structure is not imposed on this text. Source DOCX paragraph spacing,
indentation and explicit page breaks distinguish verse lines, genuine stanza
gaps, separate sayings, prose and internal headings. The portable layout file
maps 1,723 of 1,724 original reading blocks to source paragraphs; the remaining
block is the seven inscriptions in the source table on page 85. Its separate
lines and original letter case are restored explicitly.

The recipe contains 779 semantic blocks: 498 verse blocks, 193 headings,
44 prose blocks and 44 attributions. The contents tree has 241 entries. The
52 weekly poem numbers, seasons and dates are headings; zodiac and satire
labels are attributions following their own verse. Real verse boundaries,
including the separate indented line `Unvergängliche,`, remain intact. Source-reviewed
independent poem boundaries become explicit metadata instead of blank lines
between every verse. Physical page breaks retain page anchors and never create
a work boundary by themselves. `tools/ga040_poem_boundaries.json` documents
142 separate sayings against their original register entries and explicitly
excludes ten continuing sections. These include the four pictures of
*Planetentanz*, *Den Berliner Freunden*, *Grundsteinlegung* and *Ur-Weihenacht*.
All 150 candidates produced by the earlier spacing/page-break assumption were
resolved against source evidence; that assumption has been removed from the
builder.

The four column sayings on page 74 are four complete two-line sayings, two
under `J` and two under `B`. The second saying under each column also has its
own original register entry (`Wandelst zum Bilde`, paragraph 2729, and
`Verdinglichst du den Willen`, paragraph 2720). These two additional boundaries
are explicit poem starts. The following independent sayings begin on page 75;
they do not belong to the title *Die vier Sprüche der Säulenweisheit*. A retained
import passage can contain several works, so its title is not a reliable work
boundary. `tools/ga040_work_sections.json` records seven source-bound works
within this one passage; `reading_sections` preserves their exact ranges without
changing the passage ID or text. The contents promotes all seven to siblings,
and each reader visibly separates these units. Actual source headings retain
heading typography; incipits remain ordinary verses and identify units only in
the contents. Artificial import-order numbers are omitted from the contents;
authentic source numbers remain. *Tischgebet*
keeps both stanzas, and *Erkenne dich selbst* keeps all three lines together.

The same container correction applies to the calendar: the first preface does
not contain the second preface or the seasons. The original contents lists both
prefaces under the calendar, and their body headings use identical formatting.
Six source-title ranges cover the two prefaces and four seasons. All six are
siblings; weekly dates and numbered poems are children of their season. The
first inner heading of each explicit reading section uses the next outline
level rather than retaining a skipped level from the old container.

Six stray numeric footers leave the reading text with documented source
provenance. The original DOC's labels are page footers; the converted EPUB often
assigned them to the following text and produced page ranges one page too early.
The corrected 246 page anchors use observed footer labels, exact original
contents titles, and cautiously inferred pages between consistent anchors.
Page positions remain precise through joined paragraphs: the page 42 boundary
lies inside `wer|den` and page 275 inside `Reli|gion`. Observed and inferred page
identities retain distinct confidence values. The bibliography page 188 has an
explicitly reviewed original-contents/facing-page anchor.

The original note IDs and markers stay unchanged. Their cleaned definitions
have UTF-16 reference spans, and the original note text is retained in the
internal provenance. Web/native readers and EPUB provide note links and
backlinks. The public delivery excludes internal `source_text` recursively.

Every non-whitespace source character must be consumed exactly once or be an
explicit numeric-footer omission. Each lexical repair has source evidence and
must match its exact context; all input and output text hashes are frozen.
The 108 documented replacements/footer removals include the narrow OCR edits,
residual line-end word splits and isolated literary Gedankenstriche. Compound
hyphens remain intact. In the prefaces, original DOC paragraphs 57 and 61
confirm `Willenswelt`, `Gedankenrhythmus`, `Sich-eins-Fühlen` and `erstehendes`.

The complete importer applies this recipe after its earlier whitespace/word
steps. The work-independent engine can also apply the saved recipe directly:

```sh
python3 tools/repair_source_structure.py --output /tmp/ga040-new-stage
python3 tools/check_proofreading_samples.py --stage /tmp/ga040-new-stage
python3 tools/proofread_library.py --apply-stage /tmp/ga040-new-stage
```

The recipe builder uses the unchanged pre-layout input, rather than already
structured reader text. Regenerating portable layout evidence additionally
requires the original DOC converted to DOCX:

```sh
python3 tools/source_layout.py --docx /path/to/ga040-source-1991.docx \
  --source-doc research/proofreading-sources/ga-040.doc \
  --source-url http://bdn-steiner.ru/cat/ga/040.doc \
  --payload research/proofreading-layout-baseline/content/ga-040.json.gz \
  --compact --output /tmp/ga040-source-layout.json
python3 tools/build_ga040_recipe.py \
  --payload research/proofreading-layout-baseline/content/ga-040.json.gz \
  --evidence /tmp/ga040-source-layout.json --output /tmp/ga040-reviewed-recipe.json
```

Review changed evidence before replacing the frozen recipe. Neither font size
nor a small paragraph gap can decide a poem's structure without its content
classification. The [later-section review](ga-040-later-structure-review.md)
records the additional source decisions for dedications, prayers and *Credo*.

## Checked examples

The *Wintersonnenwende* sample now contains these completed lines with a single
verse boundary:

```text
So finde im Niedergang
Und in des Todes Nacht
Der Schöpfung neuen Anfang,
Des Morgens junge Macht.
```

The first calendar stanza now retains its eight lines as one stanza:

```text
1

Wenn aus den Weltenweiten
Die Sonne spricht zum Menschensinn
Und Freude aus den Seelentiefen
Dem Licht sich eint im Schauen,
Dann ziehen aus der Selbstheit Hülle
Gedanken in die Raumesfernen
Und binden dumpf
Des Menschen Wesen an des Geistes Sein.
```

The `PLANETENTANZ` boundary was checked separately: the preceding talk reflows,
while the following poem keeps its existing line and stanza boundaries. The
school morning verse in `ga-040-doc-heading-37` retains genuine verse LF while
mid-line source wrapping disappears.

## Verification

Before later word repairs, the source-aware GA 040 rebuild has all 38 original
passage IDs in their original order, all retained `source_text` values unchanged,
and no changes to non-whitespace characters. It reduces characters from 116,495
to 114,833 and double-LF boundaries from 3,430 to 1,768. The prose and calendar
helpers separately preserve all non-whitespace characters and are idempotent.

The final structural pass preserves every original passage ID and source text.
Its independent full-corpus check passes 324 works and 4,942 passages, including
all 38 GA 040 plans and their exact 108 replacement records. A repeat stage has
no byte differences in content, catalog or proofreading reports. Native and
browser checks cover all 38 sections, UTF-16 selections and linked notes; EPUB
checks cover every navigation, note and page target. Both Apple targets build.
No current GA 040 audit flags remain; this is structural verification and the
listed evidenced repairs, rather than a full manual OCR collation.

The focused checks passed:

```sh
python3 tools/test_import_library.py            # 15 tests, requires lxml
python3 tools/test_import_recovered_volumes.py  # 3 tests, requires lxml
python3 tools/ga040_readability.py --self-test   # 6 tests
python3 tools/source_layout.py --self-test      # 12 tests
python3 tools/test_source_structure.py          # 6 tests
python3 tools/test_check_proofreading_samples.py # 10 tests
```

These cover source LF versus `<br/>`, paragraph/stanza separation, source-tree
immutability, literal whitespace and inheritance, local stylesheet rules,
CSS specificity, source macro headers, mixed prose/verse guards, all 52 calendar
stanza boundaries, malformed calendar rejection, and repeat-run stability.

The source macro checks also verify that `#SE561<br/>§ 3` and
`#SE260a-s646<br/>August 1924` retain the first original token after the page
macro. Internal break markers must delimit a macro, rather than be consumed as
part of it. This was checked against the complete GA 260a source.

## Additional source-supported OCR samples

Independent review of recurring malformed full tokens found a systematic OCR
problem in GA 104a and GA 105. Six narrow replacements were checked visually,
using rendered printed pages, rather than inferred from German spelling alone:

| Source token | Confirmed printed spelling | Evidence |
| --- | --- | --- |
| `dafi` | `daß` | GA 105 p. 17 opening; GA 104a p. 63 opening |
| `erfiillt` | `erfüllt` | GA 105 p. 17 opening; GA 104a p. 63 final paragraph |
| `grofien` | `großen` | GA 105 p. 17 opening; GA 104a p. 63 second paragraph |
| `iiber` | `über` | GA 105 p. 17, lecture subject; GA 104a p. 63, Christian centuries |
| `fiir` | `für` | GA 105 p. 17, the present time; GA 104a p. 72, future suitability |
| `miissen` | `müssen` | GA 105 p. 17, ideas and views |

The rendered sources are the original German printed editions:
[GA 105](https://432hertz.de/wp-content/uploads/GA105.pdf) and
[GA 104a](https://432hertz.de/wp-content/uploads/GA104a.pdf). The German
[GA 105 lecture dated 4 August 1908 at the Rudolf Steiner Archive](https://rsarchive.org/Lectures/GA105/Compare_01.php?version=DE)
also corroborates the first lecture's checked spellings. These observations
support exact full-token substitutions; they do not authorize global `ii` → `ü`
or `fi` → `ß` character replacements. Other malformed spellings remain source
review tasks.

## GA 040a: concrete unresolved transcription review

`ga-040a-pdf-outline-75-10`, beginning *Anthroposophischer Seelenkalender*,
contains unrecognizable OCR strings from handwritten facsimiles, for example
`A. &s4Gf-f-h~*r,m£~4`. This text is not a reliable transcription and cannot be
repaired by joining lines or substituting a few recurring tokens. It needs
comparison with the manuscript image and an editorial decision to provide a
verified transcription or identify the material as a facsimile. The middle
sample must therefore remain a concrete proofreading issue in the web view.
The same section includes printed copyright labels, and
`ga-040a-pdf-outline-153-16` includes an alphabetic register. Scope decisions
about these materials require separate source review.

## Independent reader samples from the completed stage

The completed `/tmp/ga-proofreading-complete` candidate was reviewed in 13
volumes: GA 040 plus 12 cross-corpus volumes. Beginning, middle and end passages
were sampled separately (39 reader samples). Additional GA 040 checks covered
the first calendar stanza, the prose/`PLANETENTANZ` transition,
*Wintersonnenwende*, and the school morning verse. In all 269 passages of this
cohort, source text, IDs, order, page metadata and annotations remain unchanged;
every new text checksum matches its content, and no internal extraction markers
remain. The independent whole-library checksum/page verifier also passed all
324 available works and 4,942 passages.

This is a sample review of readability and repair behavior, not a complete
manual proofreading of these books. A separate strict whole-library validator
checks the recorded lexical replacements.

| GA | Sample passage suffixes (beginning / middle / end) | Reader sample finding |
| --- | --- | --- |
| 001 | `heading-0002` / `heading-0018` / `heading-0033` | Prose and paragraph boundaries remain coherent. |
| 014 | `pdf-outline-9-3` / `pdf-outline-271-32` / `pdf-outline-538-61` | Dialogue and verse LF remain intact; source-lines CSS is honored. |
| 040 | `doc-heading-2` / `doc-heading-23` / `doc-heading-41` | Prefaces and Credo flow as prose; calendar lines form stanzas. The later structure pass restores all retained source-supported stanza boundaries. |
| 040a | `pdf-outline-9-5` / `pdf-outline-75-10` / `pdf-outline-153-16` | Printed verse LF is intact. Middle facsimile OCR is unrecognizable; register/editorial scope needs review. |
| 051 | `doc-heading-4` / `doc-heading-21` / `doc-heading-33` | Raw source wraps are removed; paragraphs and inner titles remain distinct. |
| 073a | `source-heading-1` / `source-heading-9` / `source-heading-17` | Source-lines and speaker/section boundaries remain readable. |
| 105 | `text-heading-2` / `text-heading-7` / `text-heading-11` | The six approved OCR tokens are corrected; printed p. 17 corroborates the repaired opening. Other lost umlauts and spellings still require source review. |
| 120 | `page-15` / `doc-heading-6` / `doc-heading-11` | Prose now flows naturally inside existing paragraphs. |
| 163 | `source-heading-1` / `source-heading-5` / `source-heading-8` | Source line structure remains intact. Spaced heading letters such as `ERSTE R VORTRA G` still need review. |
| 259 | `heading-0006` / `heading-0025` / `heading-0044` | Soft-hyphen repairs preserve readable prose and numbered points. Source illustration markers and `Sruttgart` remain review candidates. |
| 265 | `heading-0036` / `heading-0066` / `heading-0080` | Latin formula and later prose remain intact. First sample is only a source page label; substantive opening text needs a better sample anchor. |
| 293 | `section-1` / `section-8` / `section-15` | Recovered lecture prose and paragraphs remain intact. `Zusasnmenhang` in the opening still needs source review. |
| 341 | `heading-0003` / `heading-0006` / `heading-0012` | Question/answer and appendix structure remains intact. `wirklichkeitsgcmäß` in the opening still needs source review. |
