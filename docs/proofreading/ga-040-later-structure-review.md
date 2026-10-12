# GA 040: Later-section structure review

Reviewed on 8 October 2026. The machine-readable plan is
`tools/ga040_later_plan.json`. It covers the thirteen retained passages numbered
28 and 30–41. Passage 29 is absent from the existing content payload because the
Marie Steiner preface was excluded earlier; this review does not silently add
that excluded material.

## Edition and provenance

The original working text is the 1991 DOC from
[bdn-steiner.ru](http://bdn-steiner.ru/cat/ga/040.doc). Its SHA-256 is
`9263a2efd8f66c17f6c686a4bf1c169f477331f1e2aa1bf4fea01fcfe950229a`,
which exactly matches the retained payload's `source_sha256`.

Converting this DOC with macOS `textutil` produces an HTML witness containing
the original paragraph margins, type sizes and indentation. In the review
session it is `/tmp/ga040-source-1991.html`; its SHA-256 is
`e415de97ae703b39d9749b3269ef71312d4f07c5f5a9eb442adda64f74adfd8c`.
The `source_doc_nodes` arrays in the plan refer to zero-based indices over all
`<p>` elements in that witness. They make every source classification and join
reviewable independently of paragraph indices in the content payload.

The printed [1998 scan](https://odysseetheater.org/GA/Buecher/GA_040.pdf) is a
corroborating witness for four narrow spelling/heading repairs. It has a
different arrangement and additional textual variants. Those variants and its
changed stanza layouts are not imported into the retained 1991 text. The PDF
currently served at `http://bdn-steiner.ru/cat/ga/040.pdf` is also the 1998
edition, although the DOC at the same source is the 1991 edition.

## Structure recovered

- Paragraphs belonging to a single verse are grouped without adding paragraph
  spacing between each line. Individual sayings and poems stay separate even
  when their original DOC paragraphs have the same zero top margin.
- Genuine stanza gaps remain separate segments. For example, the original DOC
  gives *Es ruhen in der Zukunft Schoß* the pattern 3/4/4/4/3 lines, with roughly
  15.8 px before each later stanza. The birthday verse beginning *Daß ich mit
  frohem Blick* has two eight-line stanzas, followed by an addressee note. The
  three stanzas beginning *In meinen Gedanken*, *In meinem Wollen* and *Wenn ich
  erwachsen* remain separate five-line stanzas.
- The original DOC presents *Im Menschenherzen schlagen* as twelve continuous
  lines. Its paragraph margins do not support an invented 4/4/4 stanza pattern.
  Likewise, the two school morning verses retain the contiguous verse layout
  present in the original DOC. The later 1998 edition's 4/7/2 and 10/4/5 school
  stanza patterns are not treated as facts about the 1991 source.
- Internal titles are represented as headings, including *Für Wilhelm
  Liebknecht*, *Abneigung gegen Verantwortung*, *Goethe*, *Conrad Ferdinand
  Meyer*, *Kindergebete*, the morning/evening prayer titles, *Für Haus Vreede*,
  and both dedications to Johanna Mücke. The book title following *Widmung zu*
  becomes a subordinate heading.
- The dedication beginning *Was in diesem Büchlein steht*, the history saying,
  the dedication beginning *Die menschliche Geistesentwicklung*, the teaching
  instruction and textual-variant note following the children's prayers, and
  the aphorism beginning *Anthroposophie möchte* flow as prose. The dedication
  beginning *Der Verfasser dieses Buches war bemüht* retains its intentionally
  short four-line layout.
- The date/author following the first dedication and the birthday addressee
  sentence are attributions. The explanation of the motto of social ethics is
  a prose note distinct from the preceding five-line verse.
- The *Credo* paragraph ending with *folge der* is joined with its continuation
  beginning *Stimme der Idee*. Existing true prose paragraphs remain separate.
  Residual word splits caused by printed line wraps are repaired explicitly.

## Page evidence

Numeric paragraphs in the original DOC are page footers. The EPUB conversion
frequently treats them as preceding page-start labels. For example, the verse
*Sprich nie von Grenzen* is followed by footer 191, and *Der Masse, der starren*
by footer 192. Their existing EPUB labels are one page earlier.

The plan records `source_footers_after` as footer-order evidence, rather than
pretending that every next numeric paragraph unconditionally determines a page.
Some source footers are missing or occur inside the reading order of framed
material. It also records `source_page_references` where the original
alphabetic register supports the first phrase of a segment. Ambiguous repeated
incipits can have more than one candidate reference and require resolution.

The isolated OCR token `'95` in passage 30 is a footer, not a date or part of a
dedication. Original DOC paragraph p739 is centered at 9.5 pt with 245.3 px top
margin. The alphabetic register independently places that dedication on page
195. The plan records it in `omitted_parts`, with page 195 and its original
node index, so removal from the reader text does not remove its provenance.

## Narrow text repairs

The scan visually confirms *Blüt'* on printed page 326, *Lernens* on page 330,
and *Wäre* in the matching four-line saying on page 230. Printed page 350
confirms the complete word *unteren* in the lower-class morning-verse heading.
The surrounding wording of the retained edition remains unchanged. The spaced
emphasis `e r` becomes `er`, without changing non-whitespace characters.

The remaining explicit edits remove line-end word splits in prose, including
*verzehrenden*, *Einzelausgabe*, *Weltwirkens*, *Weltwirken*, *Gotteslebens*,
*verabscheuungswürdigste* and *Strebenskeim*. Each edit is listed with source
evidence in the plan. Word and compound hyphens remain protected. The complete
GA 040 recipe additionally normalizes source-reviewed standalone literary
dashes; that profile is not enabled for arbitrary or mathematical text.

## Verification

All current blocks are consumed exactly once across segments and the one
recorded omitted page footer. Before the explicit edits and footer removal,
joining preserves every original non-whitespace character. Every explicit
replacement occurs exactly once in its rendered passage. The plan contains
206 rendered segments; 151 carry incipit references from the original register.
This establishes the later sections' source-bound structure and the listed
repairs. It does not certify every OCR word in the book.
