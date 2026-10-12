# Recovery of unavailable GA sources

The 2026-10-08 recovery audited all 143 entries that were unavailable in the
original local catalog. Source material was downloaded for 65 entries. Four
reviewed text volumes are now included in the local reader library; 61 recovered
entries remain research candidates. Another 65 entries have no usable source
recovered, 11 are blank catalog numbers, and two are superseded publication plans.

The local catalog has **324 readable volumes, 4,942 sections and 139 unavailable
entries**. The deployed reader service also serves all 324 volumes. The public
snapshot at `/tmp/ga-recovered-reader-delivery-clean-20261008` was published as
release `20261008T153608Z-7cf95c1c9ab7`; all 1,252 uploaded files passed remote
hash verification.

## Reader imports

| GA | Recovered original text | Sections |
| --- | --- | ---: |
| 293 | Fourteen lectures and the address of 20 August 1919 | 15 |
| 294 | Fourteen lectures and closing words of 6 September 1919 | 15 |
| 296 | Six lectures, Dornach, 9–17 August 1919 | 6 |
| 299 | Six lectures, Stuttgart, 26 December 1919–3 January 1920 | 6 |

The imports use unchanged [FVN EPUB sources](https://steiner.wiki/Die_Rudolf_Steiner_Gesamtausgabe)
hosted by Odysseetheater. Exact URLs, source SHA-256 values and reviewed boundaries
are in [recovered-reader-scope.json](../tools/recovered-reader-scope.json).
The server retains the original source text for developer comparison. Identified
publisher sections, Marie Steiner's introduction and the editorial transition
before GA 294's closing words are excluded from the reader text.

GA 293's seventh lecture contains substantial prose outside paragraph tags. The
recovery adapter preserves those bare text nodes and tails rather than silently
truncating the lecture. Source page macros provide actual page labels. Technical
image placeholders are removed from reader prose; source text and images remain
in the original EPUB. The imported texts retain spelling/OCR imperfections and
explicit working-edition warnings. Complete facsimile collation remains open.

All 320 prior content files remain byte-identical. The five normalized offline
books retain their content and section IDs. Validation passed 27 server tests,
the native whole-library download checks and three focused recovery regressions.

## Recovered research collection

The sources are stored under `research/unavailable-recovery/`, which is ignored
by Git like the existing source cache. Small provenance manifests and scripts
are retained in the repository.

- [Early writings](../tools/recovery-early.json): original German web text for
  GA 1f, 18a, 19, 37, 41a, 41b, 42, 43 and 46; historical Goethe edition scans
  and a GA 4a document facsimile. Current GA 38/1–6 have separate unresolved
  identities and are not replaced with the older GA 38/39 volumes.
- [Art and education](../tools/recovery-education-art.json): sources for all 21
  missing entries from GA 281–300, including DOC, EPUB, scan OCR and the readable
  GA 287 PDF. Seventeen have scoped text candidates. GA 289's old source does not
  cover its expanded current edition. GA 283's fuller 1989 DOC contains the
  lecture absent from the older EPUB; GA 282's Marie Steiner language course is
  excluded from the candidate.
- [Newer lecture volumes](../tools/recovery-new-lectures.json): original German
  lecture witnesses for 32 entries, plus secondary OCR witnesses covering 23
  entries, the GA 69a PDF and a partial related blackboard selection. Some archive
  links remain broken or have empty German containers. Newspaper reports,
  protocols, other speakers and programmes require original-text scope review.

The collection has **1,597 unique German web sections** across the early and
newer lecture sources. Bilingual archive pages are restricted to their original
German containers; automatic translations are excluded. Web-index coverage is
recorded separately from complete-volume proof. No unreviewed research candidate
is offered as a complete reader book.

[unavailable-sources.json](unavailable-sources.json) summarizes every original
gap and links to its detailed provenance. The audit verifies source and extracted
text hashes, including nested lecture manifests. K entries require their actual
artwork/facsimiles, and eGA 47/48 is a manuscript edition. GA 86 and 247 were
planned divisions consolidated into GA 85 and 246, according to the
[archive's annual report](https://www.rudolf-steiner.com/wp-content/uploads/2025/04/250307_RSA_Jahresbericht_24-klein.pdf).
These rows remain visible without inventing independent text volumes.

## Reproduce and verify

The recovery scripts use the source URLs and preserve downloaded originals.
The early and reader import scripts require `lxml`; DOC conversion uses macOS
`textutil`, and PDF extraction uses `pdftotext`.

```sh
python3 tools/recover_education_art.py
python3 tools/recover_all_early.py
python3 tools/recover_new_lectures.py
python3 tools/recover_rsarchive_new.py
python3 tools/recover_new_lectures_mirror.py
python3 tools/finalize_new_lectures_recovery.py
python3 tools/audit_recovered_sources.py
```

The configured dependency Python includes `lxml`. To rebuild the four reviewed
reader imports, use a fresh staging directory:

```sh
python3 tools/import_recovered_volumes.py /tmp/ga-recovery-import
python3 tools/finalize_library.py /tmp/ga-recovery-import
python3 tools/test_import_recovered_volumes.py
```

The importer rejects changed source hashes and refuses to replace an unrelated
existing edition. Review the staging output before copying its `content/` and
`library/` into `server/priv`, then run the export and validation commands in
[download-library.md](download-library.md). Publishing is a separate operation;
the live-library checker verifies the deployed 324-volume release.
