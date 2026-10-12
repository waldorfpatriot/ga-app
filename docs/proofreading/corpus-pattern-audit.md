# Corpus readability pattern audit

Baseline: 8 October 2026, before the new readability correction pass.

The read-only script `tools/audit_readability_patterns.py` inspected all **324 available GA payloads and 4,942 passages**. It reads the reader `text` field, keeps the sources unchanged, and records exact counts and bounded samples for every GA. This is an inventory of proofreading leads, not a declaration that every match is an error or that the source OCR has been fully proofread.

Source families: 315 existing EPUB working editions, 4 recovered EPUB editions (GA 293, 294, 296, 299), and 5 archive DOC/text editions (GA 3, 4, 9, 10, 13).

Reproduce the audit with:

```sh
python3 tools/audit_readability_patterns.py --output /tmp/ga-readability-patterns.json
```

Use `--field source_text` to inspect the retained source text separately. The JSON report provides one entry for every GA, payload hashes, passage IDs, source members, offsets, sample contexts, and the leading lexical candidates. Its output can be compared with a later pass without modifying the corpus.

## Baseline counts

| Pattern | Matches | GAs affected | Interpretation |
|---|---:|---:|---|
| Soft hyphen (`U+00AD`) | 119,803 | 88 | Discretionary source wrapping inside words; usually safe to remove the codepoint. |
| Soft hyphen followed by whitespace | 73 | 16 | Inspect joining separately; includes real OCR errors, table layout, and possible compound notation. |
| Letters, hard hyphen, newline, lowercase letters | 155,188 | 213 | Large source wrapping problem; also includes legitimate suspended compounds. |
| Reviewed syllabic forms, including inline splits | 12,519 | 245 | Examples such as `Men-schen`, `kön-nen`, `be-wußtsein`; a conservative candidate list, not applied by this audit. |
| Hyphen followed by a space and lowercase letters | 12,064 | 323 | Mostly legitimate forms such as `Denk- und Forschungsweisen`; retain. |
| Literal `#Bild` illustration placeholders | 1,082 | 54 | Missing illustration or source transcription marker; needs a visible review flag. |
| Font-dependent private-use characters | 11 | 2 | Symbol interpretation requires the source font/image. |
| Publisher copyright page footer | 9 | 5 | Narrow source-specific furniture pattern, distinct from original copyright statements. |
| ISBN lines | 2 | 2 | GA 174 and 255b have retained title/edition-page content; scope review. |
| Standalone numeric lines | 1,150 | 130 | Many are legitimate dates, numbered sections, formulas, or page references; do not blanket-remove. |
| Spaced sequences of at least six letters | 21 | 9 | Often intentional eurythmy/phonetic notation; some emphasized words or OCR noise. |
| Adjacent identical paragraphs of at least 120 characters | 0 | 0 | This narrow duplicate test found none; it does not rule out other duplication. |
| Replacement character (`U+FFFD`), common mojibake, import macros, Word `PAGE` fields | 0 each | 0 each | These encoding/import defects were not found in the current reader text. |

## Samples checked and decisions

| GA / passage | Observed sample | Decision supported by the sample |
|---|---|---|
| GA 1 / `ga-001-heading-0033` | `zu-nächst verbirgt` | An inline source syllable split remains even without a newline. A newline-only rule cannot repair every split. |
| GA 12 / `ga-012-chapter-0001` | `Er-kenntnis verfolgt` | Preserve historical spelling while joining a verified syllabic split. |
| GA 27 / `ga-027-source-heading-1` | `Be-\n\nwußtsein` | Source layout must not create a paragraph boundary inside a word. |
| GA 30 / `ga-030-doc-heading-3` | `Mensch-\n\nheit,` | The long-line prose source supplies many repetitive layout splits. GA 30 has 5,158 hard-hyphen/newline matches. |
| GA 40 / `ga-040-doc-heading-2` | `sinnbildlich-pedan-\n\ntische` | Only the syllabic hyphen after `pedan` should disappear; the meaningful compound hyphen before it remains. Verse and prose occur in this volume. |
| GA 259 / `ga-259-heading-0040` | `Gebäude-Schat­\nzungskommission` | A discretionary hyphen inside `Schatzungskommission` must not remove the preceding meaningful compound hyphen. GA 259 has 4,114 soft hyphens. |
| GA 294 / recovered EPUB family | 1,242 soft hyphens | The same safe-character correction should include recovered EPUBs. GA 296 has 679 and GA 299 has 575. |
| GA 326 / `ga-326-heading-0004` | `Goethe­anum`, `gesell­schaftliches Zusammen- und Ineinanderwirken` | Remove discretionary hyphens, retain the suspended compound `Zusammen- und`. |
| GA 277a / `ga-277a-heading-0005` | `i i I i i I, e e E` | Spaced sound notation is meaningful and must remain. This GA also has 107 `#Bild` placeholders. |
| GA 266/1 / `ga-266-1-doc-heading-7` | `Geruch` / `U+F045`, `Gesicnt` / `U+F04A`, `qebunaen` | Font-dependent symbols and obvious OCR noise need source comparison; a generic character deletion would lose information. Ten private-use characters occur in this GA. |
| GA 28 / `ga-028-heading-0020` | `U+F0B7` followed by `Nach mir erhob sich ...` | Likely a font-dependent bullet. Review or map with source evidence; preserve the sentence. |
| GA 73 / `ga-073-doc-heading-7` | `Copyright\nRudolf Steiner Nachlass-Verwaltung Buch: 7 3 Seite:\n10 9` | A targeted publisher-footer rule can remove furniture, but must include its following page number line. |
| GA 255b / original press article | `Copyright. 1921. Von den Chicago Daily News Co.` | This copyright statement belongs to the reproduced document. A blanket `Copyright` rule would damage text. |
| GA 4 and GA 10 / archive DOC family | No soft-hyphen or hard-hyphen/newline matches | Repetitive EPUB layout fixes should not invent changes in the five separately imported core books. Their OCR still needs human review. |

Other publisher footer matches occur in GA 40a, 108, 255b and 335. GA 40a includes OCR of handwritten material with extensive unreadable letter/mark sequences. Layout cleanup alone cannot make those transcriptions reliable; the proofreading view should keep the source context and mark those passages for review.

## Conservative correction boundaries

The source-aware whitespace fix should collapse ordinary HTML text-node whitespace while retaining explicit `<br>` boundaries and protected preformatted text. That repairs the extraction problem without guessing whether a line is a poem, drama, mantra, list, or prose. In mixed volumes such as GA 40, a blanket newline-to-space replacement would erase verse structure. Conversely, treating every text-node newline as a verse line recreates the current mid-line breaks. Explicit source line breaks are retained pending comparison.

Soft hyphens can be removed as discretionary codepoints. The 73 cases followed by whitespace require separate lexical/source checks: `geisteswissen­\n\nschaftlich` is a clear word split, but `Geist­ Seelenieben` and `un­\n\nunserer` contain additional OCR defects. Do not join arbitrary whitespace solely because a soft hyphen occurred before it.

Hard dehyphenation needs more evidence than an attested joined token. For example, the corpus contains all of the following:

| Hyphenated form | Occurrences | Joined spelling attestations | Why attestation alone is unsafe |
|---|---:|---:|---|
| `Archiv-Nr.` | 1,841 | 20 (`archivnr`) | Archive references require the abbreviation/compound punctuation. |
| `geistig-seelischen` | 1,603 | 56 | A genuine compound adjective, including historical typography. |
| `geistig-seelische` | 1,461 | 32 | Same issue; a rare joined variant is not proof of a bad hyphen. |
| `Christus-Impuls` | 1,419 | 31 | Meaningful noun compound. |
| `göttlich-geistigen` | 1,176 | 41 | Genuine compound adjective. |
| `Ich-Organisation` | 814 | 18 | Established technical compound. |

These counts include all inline and newline-bearing hyphenated pairs. They are lexical evidence, not counts of proposed corrections.

Recommended safeguards for automatic hard-hyphen joining:

1. Start with a hard hyphen followed by a newline in the retained original passage, and locate the same pair after source-aware reconstruction.
2. Require a joined spelling independently attested in more than one GA. Also compare its frequency against **all** instances of the hyphenated pair; a large joined/hyphenated ratio filters many true compounds.
3. Preserve `- und`, `- oder`, `- bzw.`, `- bis`, and uppercase second components. Preserve known meaningful prefixes such as `geistig-`, `göttlich-`, `physisch-`, `sinnlich-`, `seelisch-`, `Ich-`, `Christus-`, `Äther-`, and archive references.
4. Prefer a reviewed list of obvious syllabic pairs. High-volume examples are `Men-schen` (2,226), `wer-den` (1,040), `das-jenige` (635), `kön-nen` (614), `eigent-lich` (538), `son-dern` (527), and `mensch-lichen` (486).
5. Keep unresolved splits visible as per-GA proofreading leads. Do not silently modernize German spelling, edit uncertain OCR substitutions, remove dates/page-like numbers, or delete missing-illustration markers.

## Verification of this audit

The inventory was run against all 324 payloads, and the quantities above were checked against an independent initial regex scan. A synthetic sample verified the hard split, soft hyphen, missing illustration, and private-use glyph counters, as well as the exclusion of an original Chicago Daily News copyright statement from the publisher-footer category. Its payload SHA-256 was identical before and after the audit. The examples distinguish ordinary prose, verse-containing material, sound notation, tables/symbols, existing EPUBs, recovered EPUBs, and the archive DOC family. The JSON includes SHA-256 hashes of the payload bytes so an audit can be tied to the exact inputs. This script does not write payloads or catalog data; only an explicitly requested output report is written.

The post-correction report and individual GA change records should state which rules were applied and show original/corrected samples. Remaining OCR, illustration, symbol, and source-scope issues should remain open for human proofreading.
