# GA 027 prose line breaks

The retained 1991 *Grundlegendes für eine Erweiterung der Heilkunst* EPUB
contains page OCR with hard physical line endings. The previous correction
pass joined attested word divisions, but left page-sized paragraphs and
artificial page-seam breaks in prose.

The 8 October 2026 layout review visually checked all 134 retained body pages
(source-page-7 through source-page-141, excluding the blank page 138). It binds
each paragraph start to the original scan, exact OCR line and canonical input.
The source EPUB SHA-256 is
`fa7122ad236473714f2d44739b0cabfcd354a4b64c49d3faacae7d21c60f3528`.
Printed indentation and standalone placement establish genuine paragraph and
heading boundaries. A full stop or physical page boundary does not establish
a new paragraph. Chapter I now has its 38 original prose paragraphs.

The frozen recipe retains all 20 passage IDs and titles and produces 355 reading
blocks: 275 prose paragraphs, 43 headings, 35 note/table entries and 2 attribution
lines. The original 20 chapter navigation targets remain. Source text, source
identity, existing page metadata and annotations are unchanged. Scan page
indexes are evidence identities, not newly invented reader page anchors.
Canonical checksums and UTF-16 reading ranges are rebuilt together.

Six remaining words split at page seams are joined: Knorpelsubstanz,
Knochengebilde, Antimonprozesse, wichtigstes, Anwendüng and exsudativen.
`Anwendüng` retains the existing OCR vowel; this pass does not silently alter
spelling. Deliberate compound ellipses, including
`Wachstums-, Ernährungs- etc. -Vorgängen`, remain.
The source footnote, case headings, six remedy headings, preface/postscript,
dateline/signature, publisher notes and name register keep their separate
roles. On source-page-140 the detached page/line columns return to their 14
original correction-table rows. Each source token, including every number,
is consumed exactly once. Original OCR such as `ha`, `2»` and
`NAMENREGISTE R` remains for a separate spelling review.

`ga027_layout_review.json` records exact source anchors, page/scan hashes,
canonical input hashes and the six word-seam/table observations.
`build_ga027_recipe.py` reproducibly builds `ga027_structure.json` from those
observations and the retained source. `repair_ga027_readability.py` preserves
the intermediate input in `research/proofreading-layout-baseline`, then stages
the common source-layout pass. The complete library build and independent
sample checker use the same frozen recipe. Source or text drift fails closed;
a repeated pass is byte-identical and creates no additional correction events.

```sh
python3 tools/build_ga027_recipe.py
python3 tools/repair_ga027_readability.py --output /tmp/ga027-new-stage
python3 tools/check_proofreading_samples.py --stage /tmp/ga027-new-stage
python3 tools/proofread_library.py --apply-stage /tmp/ga027-new-stage
python3 -m unittest discover -s tools -p test_ga027_readability.py
```

Focused regression checks cover the source witness, reproducible build,
all retained characters, explicit table-cell order, original paragraph
indentation, false paragraph seams, headings/footnote/register, protected
metadata, UTF-16 ranges, idempotence and source/input/coverage drift rejection.
Full OCR collation remains outside this layout repair.
