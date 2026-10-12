# GA 014 dramatic line breaks

The retained 1998 *Vier Mysteriendramen* EPUB stores each PDF page as a
`source-lines` paragraph. It preserves printed line endings even in prose,
and includes alternating running heads inside continuous speeches. The early
outline pass restored contents, but did not distinguish dramatic verse from
prose or remove page furniture.

The 8 October 2026 repair binds all 59 passages to the original EPUB SHA-256
`658bfbcd00a8d0f2515b5c48d97ffe09d8052e6150cc3b7f21260eea541b8e7f`.
Every canonical paragraph matches its EPUB page witness exactly. Embedded
facsimiles on PDF pages 13, 14, 21, 118, 215 and 538 corroborate the prose,
verse, speaker and running-head roles. The frozen recipe consumes every source
character exactly once, except for 484 individually evidenced running heads
and the exact facsimile repairs recorded in `ga014_reviewed_repairs.json`.

The result has 2,862 semantic blocks: 1,215 verse blocks, 1,181 speaker labels,
407 prose blocks and 59 original headings. The children's song keeps its nine
verse lines. Vorspiel/Zwischenspiel speeches and closed stage directions reflow;
the scene dialogues keep their verse line endings. A page boundary introduces
no artificial stanza break. Speaker labels stay immediately above their speech,
with space between successive speakers. The fused source token
`VorspielSOPHIA:` is split at its verified role boundary without altering letters.

All original passage IDs, retained `source_text`, contents entries and
`source_outline` history survive. Reading blocks receive fresh UTF-16 offsets
in the corrected canonical text. EPUB PDF page indexes are evidence identities;
they are not exposed as unverified printed-page reader anchors.

The reported `Band,` overrun in Maria's opening speech led to collation of all
63 remaining review leads. Fifty-nine source scans support 67 exact repairs:
53 logical verse continuations (including the original `Band,` and an unflagged
`GlückErlebnis`), eight stage directions, one speaker cue, one inline explanatory
parenthesis, the missing full stop at the fused `VorspielSOPHIA:` boundary,
and three prose words split across pages (`Darstel- lung`, `Wiederga- be`,
`erschei- nen`).
The 51 remaining bracketed fragments are restored to their parent verses;
all 17 associated merged verse boundaries are separated. Some continuations
appear above their parent verse, so a blanket next-line join would misplace them.
The historical spelling `zehen` remains.

At PDF page 379, the continuation `[weinen.` shares a physical row with
`(Geht schnell ab.)`. Exact source slices place the continuation before the
separate prose direction. At page 149, the fused OCR also lost `Ich`; the scan
restores `darzustellen.\nIch konnte …`. The exact old/new contexts and individual
source-page evidence are recorded in the repair inventory and frozen recipe.
Revising the recipe replays the protected intermediate input and archives the
previous layout ledger in `readability_history`.

No overrun or uncertain-stage-parenthesis review leads remain. Other OCR wording
and cast-list lines remain, including intentional cast-group braces. These
repairs complete the identified layout artefacts; full OCR collation remains
outside this pass.

`build_ga014_recipe.py` builds `ga014_structure.json` from the exact source.
`repair_ga014_readability.py` stages the pass after the original outline. Its
separate `research/proofreading-ga014-baseline` preserves that intermediate
input. The independent sample checker validates this last layer first, then
the historical outline and corpus repairs. The complete rebuild includes the
same pass; rerunning the outline preserves the later dramatic layout.

```sh
python3 tools/repair_ga014_readability.py --output /tmp/ga014-new-stage
python3 tools/check_proofreading_samples.py --stage /tmp/ga014-new-stage
python3 tools/proofread_library.py --apply-stage /tmp/ga014-new-stage
python3 tools/test_ga014_readability.py
```

Focused checks cover source identity, exact omission and repair coverage,
continuations above their parent verse, restored words at fused boundaries,
separate stage cues, protected verse lines, prose reflow, page continuity,
original contents, drift rejection and idempotence. The native reader,
proofreading browser and EPUB renderer support the resulting semantic block kinds.
