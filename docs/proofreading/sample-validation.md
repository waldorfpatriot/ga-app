# Independent sample validation

Stage: `/tmp/ga-proofreading-complete`

Result: **PASSED**. 324 available GAs and 4942 passages compared with the preserved baseline.

Verified 119,803 soft-hyphen removals, 127,099 documented hard-hyphen joins, and 1,937 approved OCR substitutions. 4,131 passages changed. No unexpected changes were found.

The validator compares actual staged characters and metadata independently; it does not rerun the correction functions. It checks original source text, passage identity/order, pages, annotations, other payload fields, checksums, report counts, lexical evidence, and protected compounds. Only whitespace, explicitly documented hyphen deletions, and six source-approved case-sensitive full-token OCR maps are accepted: fiir→für, dafi→daß, grofien→großen, erfiillt→erfüllt, iiber→über, miissen→müssen.

GA 40 calendar: 52 contiguous weekly stanzas; numbers 1–52 remain in order. Each stanza has 5–8 physical verse lines. Poems 1, 26 and 52 were inspected; the source numeral `5 2` is retained.

## Representative samples

Beginning/middle/end passages are included for writings, poetry/drama, lectures, high soft-hyphen volumes, recovered EPUBs, and the five core editions. Changed-word samples below give exact original/corrected contexts. Automated preservation and these samples do not replace a complete manual source collation.

Changed-word contexts cover 15 requested representative GAs. GAs without a word correction still have beginning/middle/end passage and preservation checks.

### ga-001 — Einleitungen zu Goethes Naturwissenschaftlichen Schriften (1884 - 1897)

passed; 28 passages; 1 hard-hyphen joins.

- beginning: `ga-001-heading-0002` — Zur Einführung
- middle: `ga-001-heading-0018` — 5. Ethische und historische Wissenschaften
- end: `ga-001-heading-0033` — XVIII. Goethes Weltanschauung in seinen «SPRÜCHEN IN PROSA»

`ga-001-heading-0009` (soft_hyphen)

Before:

```text
ibt. Er weist die bloß mechanische Naturauffassung und den am Äußerlichen haftenden Hyper-­Darwinismus zurück. Er ist in der Wissenschaft Begründer eines konkreten Monismus. In der Geschichte und Ästhetik sucht er die konkrete Idee. Das all
```

After:

```text
ibt. Er weist die bloß mechanische Naturauffassung und den am Äußerlichen haftenden Hyper-Darwinismus zurück. Er ist in der Wissenschaft Begründer eines konkreten Monismus. In der Geschichte und Ästhetik sucht er die konkrete Idee. Das alle
```

`ga-001-heading-0010` (soft_hyphen)

Before:

```text
cht gleich jenen Weg betreten habe, der sich vor allem zu empfehlen scheint: die allgemein­naturwissenschaftlichen Schriften im 1. Bande, die organischen, mineralogischen und meteorologischen im 2. und die physikalischen Schriften im 3. Ban
```

After:

```text
cht gleich jenen Weg betreten habe, der sich vor allem zu empfehlen scheint: die allgemeinnaturwissenschaftlichen Schriften im 1. Bande, die organischen, mineralogischen und meteorologischen im 2. und die physikalischen Schriften im 3. Band
```

`ga-001-heading-0033` (hard_hyphen)

Before:

```text
ltigkeit ihrer Schöpfungen hervorzubringen, Triebkräfte braucht, die sie dem Beobachter zu-nächst verbirgt. Die Natur spricht ihr letztes Wort nicht selbst aus. Unsere Erfahrung zeigt uns, was die Natur schaffen kann, aber sie sagt uns nich
```

After:

```text
ltigkeit ihrer Schöpfungen hervorzubringen, Triebkräfte braucht, die sie dem Beobachter zunächst verbirgt. Die Natur spricht ihr letztes Wort nicht selbst aus. Unsere Erfahrung zeigt uns, was die Natur schaffen kann, aber sie sagt uns nicht
```

### ga-002 — Grundlinien einer Erkenntnistheorie der Goetheschen Weltanschauung mit besonderer Rücksicht auf Schiller (1886)

passed; 23 passages; 0 hard-hyphen joins.

- beginning: `ga-002-heading-0002` — Vorrede zur Neuauflage
- middle: `ga-002-heading-0016` — 10. Innere Natur des Denkens
- end: `ga-002-heading-0031` — 21. Erkennen und künstlerisches Schaffen

No word-split correction occurred in this GA; beginning/middle/end payload samples and preservation checks were included.

### ga-003 — Wahrheit und Wissenschaft

passed; 10 passages; 0 hard-hyphen joins.

- beginning: `ga-003-01-vorrede-zur-1-auflage-1892` — Vorrede zur 1. Auflage 1892
- middle: `ga-003-06-iv-die-ausgangspunkte-der-erkenntnistheorie` — IV. Die Ausgangspunkte der Erkenntnistheorie
- end: `ga-003-10-viii-praktische-schlussbetrachtung` — VIII. Praktische Schlussbetrachtung

No word-split correction occurred in this GA; beginning/middle/end payload samples and preservation checks were included.

### ga-004 — Die Philosophie der Freiheit

passed; 18 passages; 0 hard-hyphen joins.

- beginning: `ga-004-01-vorrede-zur-neuausgabe-1918` — Vorrede zur Neuausgabe 1918
- middle: `ga-004-10-ix-die-idee-der-freiheit` — IX. Die Idee der Freiheit
- end: `ga-004-18-zweiter-anhang-vorrede-zur-1-auflage-von-1884` — Zweiter Anhang (Vorrede zur 1. Auflage von 1884)

No word-split correction occurred in this GA; beginning/middle/end payload samples and preservation checks were included.

### ga-009 — Theosophie

passed; 16 passages; 0 hard-hyphen joins.

- beginning: `ga-009-01-vorrede-zur-6-auflage` — Vorrede zur 6. Auflage
- middle: `ga-009-09-i-die-seelenwelt` — I. Die Seelenwelt
- end: `ga-009-16-einzelne-bemerkungen-und-erganzungen` — Einzelne Bemerkungen und Ergänzungen

No word-split correction occurred in this GA; beginning/middle/end payload samples and preservation checks were included.

### ga-010 — Wie erlangt man Erkenntnisse der höheren Welten?

passed; 16 passages; 0 hard-hyphen joins.

- beginning: `ga-010-01-vorrede-zum-achten-bis-elften-tausend` — Vorrede zum achten bis elften Tausend
- middle: `ga-010-09-die-bedingungen-der-geheimschulung` — Die Bedingungen der Geheimschulung
- end: `ga-010-16-nachwort-zum-achten-bis-zwolften-tausend` — Nachwort zum achten bis zwölften Tausend

No word-split correction occurred in this GA; beginning/middle/end payload samples and preservation checks were included.

### ga-013 — Die Geheimwissenschaft im Umriß

passed; 17 passages; 0 hard-hyphen joins.

- beginning: `ga-013-01-vorrede-zur-16-20-auflage` — Vorrede zur 16. – 20. Auflage
- middle: `ga-013-09-die-astralische-welt` — Die astralische Welt
- end: `ga-013-17-besondere-bemerkungen` — Besondere Bemerkungen

No word-split correction occurred in this GA; beginning/middle/end payload samples and preservation checks were included.

### ga-014 — Vier Mysteriendramen

passed; 59 passages; 0 hard-hyphen joins.

- beginning: `ga-014-pdf-outline-9-3` — DIE PFORTE DER EINWEIHUNG (INITIATION)
- middle: `ga-014-pdf-outline-271-32` — DREIZEHNTES BILD
- end: `ga-014-pdf-outline-538-61` — FÜNFZEHNTES BILD

No word-split correction occurred in this GA; beginning/middle/end payload samples and preservation checks were included.

### ga-030 — Methodische Grundlagen der Anthroposophie 1884 - 1901

passed; 3 passages; 4188 hard-hyphen joins.

- beginning: `ga-030-doc-heading-3` — GOETHE ALS VATER EINER NEUEN ÄSTHETIK
- middle: `ga-030-doc-heading-4` — EINHEITLICHE NATURANSCHAUUNG UND ERKENNTNISGRENZEN
- end: `ga-030-doc-heading-5` — ANMERKUNGEN

`ga-030-doc-heading-3` (hard_hyphen)

Before:

```text
r Auflage erscheint, ist vor

mehr
als zwanzig Jahren im Wiener Goethe-Verein gehalten wor-

den.
Anläßlich dieser Neuausgabe einer meiner früheren Schriften

darf
vielleicht das Folgende gesagt werden. Es ist vorgekommen,

daß
man Änderung
```

After:

```text
er Auflage erscheint, ist vor
mehr als zwanzig Jahren im Wiener Goethe-Verein gehalten worden. Anläßlich dieser Neuausgabe einer meiner früheren Schriften
darf vielleicht das Folgende gesagt werden. Es ist vorgekommen,
daß man Änderungen me
```

`ga-030-doc-heading-4` (hard_hyphen)

Before:

```text
ollständigsten Auslöschung

seiner
Persönlichkeit, seines Ich erkauft. Den Verlust des Per-

sönlichen
fühlten Jakob Böhme und die Mystiker, die seiner An-

schauung
waren, nicht. Im Gegenteil: sie empfanden etwas beson-

ders
Erhebendes be
```

After:

```text
vollständigsten Auslöschung
seiner Persönlichkeit, seines Ich erkauft. Den Verlust des Persönlichen fühlten Jakob Böhme und die Mystiker, die seiner Anschauung waren, nicht. Im Gegenteil: sie empfanden etwas besonders Erhebendes bei dem Ged
```

`ga-030-doc-heading-5` (hard_hyphen)

Before:

```text
 der physikalischen
Untersu-

chungsmethoden
für die Chemie neue Grundstoffe gefunden, son-

dern
es hat das Studium der zusammengesetzten unorganischen

Stoffe
auf das Wesen der Materie Streiflichter geworfen, die nur

im
Sinne einer philo
```

After:

```text
g der physikalischen Untersu-
chungsmethoden für die Chemie neue Grundstoffe gefunden, sondern es hat das Studium der zusammengesetzten unorganischen
Stoffe auf das Wesen der Materie Streiflichter geworfen, die nur
im Sinne einer philosophi
```

### ga-040 — Wahrspruchworte

passed; 38 passages; 99 hard-hyphen joins.

- beginning: `ga-040-doc-heading-2` — VORWORT ZUR ERSTEN AUSGABE 1912/13
- middle: `ga-040-doc-heading-23` — MYSTERIENUNTERRICHT IM GRIECHISCHEN ALTERTUM
- end: `ga-040-doc-heading-41` — CREDO DER EINZELNE UND DAS ALL

`ga-040-doc-heading-2` (hard_hyphen)

Before:

```text
empfindet er das Abbild des

Welten-Urbildes.
Doch ist das Abbild nicht sinnbildlich-pedan-

tische
Nachahmung des Urbildes. Was die große Welt im Zei-

tenlaufe
offenbart, entspricht einem Pendelschlage des Men-

schenwesens,
der nicht im 
```

After:

```text
 empfindet er das Abbild des Welten-Urbildes. Doch ist das Abbild nicht sinnbildlich-pedantische Nachahmung des Urbildes. Was die große Welt im Zeitenlaufe offenbart, entspricht einem Pendelschlage des Menschenwesens, der nicht im Elemente 
```

`ga-040-doc-heading-30` (hard_hyphen)

Before:

```text

GOETHESCHEN WELTANSCHAUUNG»

Was
in diesem Büchlein steht: ich habe es nicht nur geschrie-

ben,
ich habe es gelebt,
wenn
meines Innern Mächte im verzeh-

renden
Kampfe einander begegneten; mit Worten
sucht ich
des

ringenden
Geistes Bahne
```

After:

```text
 GOETHESCHEN WELTANSCHAUUNG»

Was in diesem Büchlein steht: ich habe es nicht nur geschrieben, ich habe es gelebt, wenn meines Innern Mächte im verzeh-
renden Kampfe einander begegneten; mit Worten sucht ich des
ringenden Geistes Bahnen nac
```

`ga-040-doc-heading-41` (hard_hyphen)

Before:

```text
wahre Bestimmung. Wer aber im

Geiste
lebt, lebt frei. Denn er hat sich alles Untergeordne-

ten
entwunden. Nichts bezwingt ihn, als wovon er gerne

den
Zwang erleidet, denn er hat es als das Höchste erkannt.

Lasse
die Wahrheit zum Leben w
```

After:

```text
 wahre Bestimmung. Wer aber im Geiste lebt, lebt frei. Denn er hat sich alles Untergeordneten entwunden. Nichts bezwingt ihn, als wovon er gerne den Zwang erleidet, denn er hat es als das Höchste erkannt.

Lasse die Wahrheit zum Leben werde
```

### ga-040a — Sprüche, Dichtungen, Mantren. Ergänzungsband

passed; 11 passages; 0 hard-hyphen joins.

- beginning: `ga-040a-pdf-outline-9-5` — Nachträge zu «Wahrspruchworte» GA 40
- middle: `ga-040a-pdf-outline-75-10` — Anthroposophischer Seelenkalender
- end: `ga-040a-pdf-outline-153-16` — nach Überschriften und Spruchanfängen (mit Quellenangaben bei den Spruchanfängen)

No word-split correction occurred in this GA; beginning/middle/end payload samples and preservation checks were included.

### ga-083 — Westliche und östliche Weltgegensätzlichkeit. Wege zu ihrer Verständigung durch Anthroposophie.

passed; 16 passages; 2823 hard-hyphen joins.

- beginning: `ga-083-doc-heading-3` — ERSTER VORTRAG — ANTHROPOSOPHIE UND NATURWISSENSCHAFT Wien, 1. Juni 1922
- middle: `ga-083-doc-heading-12` — SIEBENTER VORTRAG
- end: `ga-083-doc-heading-23` — WEST-OST-APHORISMEN

`ga-083-doc-heading-3` (hard_hyphen)

Before:

```text
an den Weltanschauungskonsequenzen,

welche
diese Naturwissenschaft gebracht hat. Diese Na-

turwissenschaft
ist ja in einem gewissen Sinne seit Jahr-

hunderten,
man darf sagen, seit dem 15., 16. Jahrhun-

dert,
immer mehr und mehr die Beh
```

After:

```text
 an den Weltanschauungskonsequenzen,
welche diese Naturwissenschaft gebracht hat. Diese Naturwissenschaft ist ja in einem gewissen Sinne seit Jahrhunderten, man darf sagen, seit dem 15., 16. Jahrhundert, immer mehr und mehr die Beherrscheri
```

`ga-083-doc-heading-13` (hard_hyphen)

Before:

```text
ergingen, wenn man an all das erin-

nert, dann
kann man sagen: Was in unserer Zeit von ge-

wissen
Kreisen als eine soziale Gestaltung in Europa ge-

sucht
wird, das war vor achthundert Jahren in einem

hohen
Grad durch dreißig Jahre hindu
```

After:

```text
 übergingen, wenn man an all das erinnert, dann kann man sagen: Was in unserer Zeit von gewissen Kreisen als eine soziale Gestaltung in Europa gesucht wird, das war vor achthundert Jahren in einem
hohen Grad durch dreißig Jahre hindurch ver
```

`ga-083-doc-heading-23` (hard_hyphen)

Before:

```text
hen,
dann wird der Westmensch ihn

in
der Arbeit für den Menschenfortschritt als einen Mit-

arbeiter
begrüßen müssen, der leisten kann, was er selbst

nicht
vermag.

FÜNFUNDZWANZIG
JAHRE SPÄTER

Einige
Gedanken zur Herausgabe der zweiten A
```

After:

```text
hen, dann wird der Westmensch ihn

in der Arbeit für den Menschenfortschritt als einen Mitarbeiter begrüßen müssen, der leisten kann, was er selbst
nicht vermag.

FÜNFUNDZWANZIG JAHRE SPÄTER
Einige Gedanken zur Herausgabe der zweiten Auflag
```

### ga-120 — Die Offenbarungen des Karma.

passed; 11 passages; 26 hard-hyphen joins.

- beginning: `ga-120-page-15` — ERSTER VORTRAG Hamburg, 16. Mai 1910
- middle: `ga-120-doc-heading-6` — SECHSTER VORTRAG — Hamburg, 21. Mai 1910
- end: `ga-120-doc-heading-11` — ELFTER VORTRAG Hamburg, 28. Mai 1910

`ga-120-page-15` (hard_hyphen)

Before:

```text

oder jenes auszugleichen! -, so wird er doch durch die Kraft, die in
ihm sitzt, zu irgend-

einer Handlung hingetrieben,
die ein Ausgleich ist. Und jetzt können
wir uns eine Vorstellung machen, was vor sich geht, wenn einen
Menschen zum Be
```

After:

```text
 oder jenes auszugleichen! -, so wird er doch durch die Kraft, die in ihm sitzt, zu irgendeiner Handlung hingetrieben, die ein Ausgleich ist. Und jetzt können wir uns eine Vorstellung machen, was vor sich geht, wenn einen Menschen zum Beisp
```

`ga-120-doc-heading-6` (hard_hyphen)

Before:

```text
 Ätherleib, muß eine Störung auftreten. Nun
haben wir aber in den letzten Betrachtungen ge-

rn

sehen, daß
das, was wir jetzt folgern, wirklich geschieht. Wir haben den ganzen
Vorgang nur von der andern Seite her dargestellt. Wann geschieh
```

After:

```text
 Ätherleib, muß eine Störung auftreten. Nun haben wir aber in den letzten Betrachtungen gern

sehen, daß das, was wir jetzt folgern, wirklich geschieht. Wir haben den ganzen Vorgang nur von der andern Seite her dargestellt. Wann geschieht e
```

`ga-120-doc-heading-11` (hard_hyphen)

Before:

```text
eisheit der äußeren Welt eingetaucht ist. Wenn wir
nach und nach der andern Hälfte der Ent-wickelung teilhaftig werden
sollen, Luzifer und Ahriman wieder zu überwinden, dann müssen wir
uns durchdringen mit Weisheit und Liebe. Indem wir Weis
```

After:

```text
eisheit der äußeren Welt eingetaucht ist. Wenn wir nach und nach der andern Hälfte der Entwickelung teilhaftig werden sollen, Luzifer und Ahriman wieder zu überwinden, dann müssen wir uns durchdringen mit Weisheit und Liebe. Indem wir Weish
```

### ga-159 — (GA 159/160) Das Geheimnis des Todes. Wesen und Bedeutung Mitteleuropas und die europäischen Volksgeister.

passed; 15 passages; 2 hard-hyphen joins.

- beginning: `ga-159-heading-0003` — DIE VIER PLATONISCHEN TUGENDEN UND IHR ZUSAMMENHANG MIT DEN MENSCHLICHEN WESENSGLIEDERN - DAS HEREINWIRKEN GEISTIGER MÄCHTE IN DIE PHYSISCHE WELT Zürich, 31. Januar 1915
- middle: `ga-159-heading-0011` — DER KRIEG, EIN KRANKHEITSPROZESS MITTELEUROPA UND DER SLAWISCHE OSTEN DIE TOTEN ALS HELFER DES MENSCHHEITSFORTSCHRITTES Wien, 9. Mai 1915
- end: `ga-159-heading-0020` — DIE ERKENNTNISGEMÄSSE ÜBERWINDUNG DES TODES VORGEBURTLICHE UND NACHTODLICHE SEELENERLEBNISSE UNSERE VERBINDUNG MIT DEN TOTEN Köln, 19. Juni 1915

`ga-159-heading-0003` (soft_hyphen)

Before:

```text
en, jene Kluft, die sich aufrichtet für das äußere menschliche Bewußtsein zwischen der phy­sischen Welt, in welcher der Mensch die Zeit verbringt zwischen der Geburt und dem Tode, und der geistigen Welt, in welcher der Mensch die andere Zei
```

After:

```text
en, jene Kluft, die sich aufrichtet für das äußere menschliche Bewußtsein zwischen der physischen Welt, in welcher der Mensch die Zeit verbringt zwischen der Geburt und dem Tode, und der geistigen Welt, in welcher der Mensch die andere Zeit
```

`ga-159-heading-0011` (soft_hyphen)

Before:

```text
das gewissermaßen wie ein Losungsruf war und so wirken sollte, wie wenn die Kultur von Ost­europa etwa jetzt beginnen sollte, sich über das wenig wertvolle Westeuropa auszudehnen, es zu überströmen? Sehen wir denn nicht, wie die Slawophlien
```

After:

```text
das gewissermaßen wie ein Losungsruf war und so wirken sollte, wie wenn die Kultur von Osteuropa etwa jetzt beginnen sollte, sich über das wenig wertvolle Westeuropa auszudehnen, es zu überströmen? Sehen wir denn nicht, wie die Slawophlien,
```

`ga-159-heading-0020` (soft_hyphen)

Before:

```text
fte und um so stärker wir­ken können. Und fruchtbar für die Erdenseelen in der Zukunft wer­den diese unverbrauchten Ätherleiberkräfte derjenigen sein, die heute auf den Feldern von Blut und Tod ihre Opfer dargebracht haben.
Aus diesem Grund
```

After:

```text
äfte und um so stärker wirken können. Und fruchtbar für die Erdenseelen in der Zukunft werden diese unverbrauchten Ätherleiberkräfte derjenigen sein, die heute auf den Feldern von Blut und Tod ihre Opfer dargebracht haben.
Aus diesem Grunde
```

### ga-259 — Das Schicksalsjahr 1923 in der Geschichte der Anthroposophischen Gesellschaft.

passed; 18 passages; 1 hard-hyphen joins.

- beginning: `ga-259-heading-0006` — II Aus der Arbeit für den Wiederaufbau des Goetheanum und die Neubildung der Anthroposophischen Gesellschaft
- middle: `ga-259-heading-0025` — Mittwoch, den 28. Februar 1923, nachmittags Herr Emil Leinhas eröffnet die Versammlung um 1/2 3 Uhr.
- end: `ga-259-heading-0044` — Die »Nicht-anthroposophischen Kenner der Anthroposophie»*

`ga-259-heading-0006` (soft_hyphen)

Before:

```text
dig; denn ohne diese wäre ein Wiederaufbau nicht möglich. Also es muß einfach eine Konsoli­dierung, eine innere Festigung, ein deutliches Wol­len der Anthroposophischen Gesellschaft zustande kommen.
Rudolf Steiner, Dornach, 9. Februar 1923

```

After:

```text
dig; denn ohne diese wäre ein Wiederaufbau nicht möglich. Also es muß einfach eine Konsolidierung, eine innere Festigung, ein deutliches Wollen der Anthroposophischen Gesellschaft zustande kommen.
Rudolf Steiner, Dornach, 9. Februar 1923
#B
```

`ga-259-heading-0025` (soft_hyphen)

Before:

```text
einsamen Arbeit speziell auf medizinischem Gebiet. Man müsse als Mediziner beim Anthroposo­phischen beginnen. Das Moralische, die Liebeskräfte, seien das, wovon ausge­gangen werden müsse. Mit der Verbreitung der Heilmittel können wir nur Er
```

After:

```text
einsamen Arbeit speziell auf medizinischem Gebiet. Man müsse als Mediziner beim Anthroposophischen beginnen. Das Moralische, die Liebeskräfte, seien das, wovon ausgegangen werden müsse. Mit der Verbreitung der Heilmittel können wir nur Erfo
```

`ga-259-heading-0044` (soft_hyphen)

Before:

```text
seine Arbeit und sein Werk. Er wußte, daß die Gegner nicht umsonst gerade seine Persönlich­keit in den Schmutz ziehen, um das Werk zu vernichten. Und er sah - daß die Anthroposophen dies nicht sahen. Sie zogen sich in die Anthroposophenburg
```

After:

```text
seine Arbeit und sein Werk. Er wußte, daß die Gegner nicht umsonst gerade seine Persönlichkeit in den Schmutz ziehen, um das Werk zu vernichten. Und er sah - daß die Anthroposophen dies nicht sahen. Sie zogen sich in die Anthroposophenburg 
```

### ga-260a — Die Konstitution der Allgemeinen Anthroposophischen Gesellschaft und der Freien Hochschule für Geisteswissenschaft. Der Wiederaufbau des Goetheanum.

passed; 20 passages; 12 hard-hyphen joins.

- beginning: `ga-260a-heading-0004` — Nachrichtenblatt, 13. Januar 1924 DIE BILDUNG DER ALLGEMEINEN ANTHROPOSOPHISCHEN GESELLSCHAFT DURCH DIE WEIHNACHTSTAGUNG 1923
- middle: `ga-260a-heading-0018` — IV Auswirkungen der Weihnachtstagung in Verwaltungsfragen und der Wiederaufbau des Goetheanums
- end: `ga-260a-heading-0031` — NOVEMBER 1924 Tätigkeit Rudolf Steiners vom Krankenlager aus

`ga-260a-heading-0004` (soft_hyphen)

Before:

```text
htlinien oder Statuten haben. Denn ihre Grundlage ist gegeben in den Einsichten in die gei­stige Welt, die als Anthroposophie vorliegen. In diesen findet schon bis heute eine große Zahl von Menschen eine sie befriedigende Anregung für ihre 
```

After:

```text
htlinien oder Statuten haben. Denn ihre Grundlage ist gegeben in den Einsichten in die geistige Welt, die als Anthroposophie vorliegen. In diesen findet schon bis heute eine große Zahl von Menschen eine sie befriedigende Anregung für ihre g
```

`ga-260a-heading-0018` (soft_hyphen)

Before:

```text
rte (siehe Beilage S. 9)

Der Vorstand mödite das Folgende zur Ausführung der Statuten vor­bringen:
1. Man ist Mitglied geworden in dem Augenblicke, in dem der Leiter der Anthroposophisdien Gesellschaft die von den Gruppenfunktionären vorge
```

After:

```text
te (siehe Beilage S. 9)


Der Vorstand mödite das Folgende zur Ausführung der Statuten vorbringen:
1. Man ist Mitglied geworden in dem Augenblicke, in dem der Leiter der Anthroposophisdien Gesellschaft die von den Gruppenfunktionären vorgel
```

`ga-260a-heading-0031` (soft_hyphen)

Before:

```text
chung
260    Die Weihnachtstagung zur Begründung der Allgemeinen Anthroposophischen Gesell­schaft 1923/24
261    Unsere Toten
274    Ansprachen zu den Weihnachtspielen aus altem Volkstum
277    Eurvthmie - Die Offenbarung der sprechenden Se
```

After:

```text
chung
260    Die Weihnachtstagung zur Begründung der Allgemeinen Anthroposophischen Gesellschaft 1923/24
261    Unsere Toten
274    Ansprachen zu den Weihnachtspielen aus altem Volkstum
277    Eurvthmie - Die Offenbarung der sprechenden See
```

### ga-264 — Zur Geschichte und aus den Inhalten der ersten Abteilung der Esoterischen Schule von 1904 bis 1914. Briefe, Rundbriefe, Dokumente, Vorträge.

passed; 12 passages; 3 hard-hyphen joins.

- beginning: `ga-264-heading-0004` — I ZUR ENTSTEHUNGSGESCHICHTE UND AUS DEM LEHRGUT DER ERSTEN ABTEILUNG DER ESOTERISCHEN SCHULE 1904 - 1914
- middle: `ga-264-heading-0013` — ANHANG Die Meister der Weisheit und des Zusammenklan ges der Empfindungeri im Werk Rudolf Steiners
- end: `ga-264-heading-0021` — EIN ESOTERISCH-SOZIALER ZUKUNFTSIMPULS VERSUCH ZUR «STIFTUNG. EINER GESELLSCHAFT FÜR THEOSOPHISCHE ART UND KUNST Ansprache, Berlin 15. Dezember 1911 (vormittags)l)

`ga-264-heading-0004` (soft_hyphen)

Before:

```text
Bei der Neubegründung der Anthroposophischen Gesellschaft zu Weih­nachten 1923/24 sprach Rudolf Steiner von seinem Plan, die neue esoteri­sche Schule künftig als «Freie Hochschule für Geisteswissenschaft» mit drei K
```

After:

```text
Bei der Neubegründung der Anthroposophischen Gesellschaft zu Weihnachten 1923/24 sprach Rudolf Steiner von seinem Plan, die neue esoterische Schule künftig als «Freie Hochschule für Geisteswissenschaft» mit drei Kla
```

`ga-264-heading-0013` (soft_hyphen)

Before:

```text
Sektion im Oktober 1903 skizzierte Rudolf Steiner sein zukünftiges Lehrprogramm als «okkul­te Geschichtsforschung», als deren Teil die Lehre von den großen Geistes-führern der Menschheit genannt wurde. Denn nach den Aspekten der gro­ßen Dre
```

After:

```text
Sektion im Oktober 1903 skizzierte Rudolf Steiner sein zukünftiges Lehrprogramm als «okkulte Geschichtsforschung», als deren Teil die Lehre von den großen Geistes-führern der Menschheit genannt wurde. Denn nach den Aspekten der großen Dreih
```

`ga-264-heading-0021` (soft_hyphen)

Before:

```text
ners dürfte der Sinn des von ihm einmal niedergeschriebenen Meditationssatzes gelten: «Wel­tenwerden ist das Verschwinden des Geistes auf einer Seite in den Abgrund und Aufglänzen auf der anderen Seite aus dem Abgrund.»
```

After:

```text
ners dürfte der Sinn des von ihm einmal niedergeschriebenen Meditationssatzes gelten: «Weltenwerden ist das Verschwinden des Geistes auf einer Seite in den Abgrund und Aufglänzen auf der anderen Seite aus dem Abgrund.»
```

### ga-293 — Allgemeine Menschenkunde als Grundlage der Pädagogik.

passed; 15 passages; 13 hard-hyphen joins.

- beginning: `ga-293-section-1` — ERSTER VORTRAG
- middle: `ga-293-section-8` — ACHTER VORTRAG
- end: `ga-293-section-15` — ANHANG Ansprache am Vorabend des Kurses Stuttgart, 20. August 1919

`ga-293-section-2` (hard_hyphen)

Before:

```text
g, so weisen Sie eigentlich den ganzen Menschen auf das Vorgehurtliche zurück, und Sie wer- den ihm schaden, wenn Sie ihn rationalistisch erziehen, weil

Sie dann seinen Willen einspannen in das, was er eigentlich schon absolviert hat: in d
```

After:

```text
g, so weisen Sie eigentlich den ganzen Menschen auf das Vorgehurtliche zurück, und Sie werden ihm schaden, wenn Sie ihn rationalistisch erziehen, weil

Sie dann seinen Willen einspannen in das, was er eigentlich schon absolviert hat: in das
```

`ga-293-section-8` (hard_hyphen)

Before:

```text
otwendig ist, wenn nicht das Ich- Bewußtsein immer unkräftiger und unkräftiger gemacht wer- den soll, wenn es nicht den Charakter annehmen soll, den man so bezeichnen könnte, daß es durch einen gestörten Schlafzustand zu stark hingegeben wi
```

After:

```text
otwendig ist, wenn nicht das Ich- Bewußtsein immer unkräftiger und unkräftiger gemacht werden soll, wenn es nicht den Charakter annehmen soll, den man so bezeichnen könnte, daß es durch einen gestörten Schlafzustand zu stark hingegeben wird
```

`ga-293-section-15` (hard_hyphen)

Before:

```text
Schulen, die eine wahre Begräbnisstätte sind für alles wirkliche Unterricbtswesen. Wir wer- den einem harten Kampf entgegengehen, und müssen doch diese Kulturtat tun.
zwei widersprechende Kräfte sind dabei in Einklang zu bringen. Auf der ei
```

After:

```text
Schulen, die eine wahre Begräbnisstätte sind für alles wirkliche Unterricbtswesen. Wir werden einem harten Kampf entgegengehen, und müssen doch diese Kulturtat tun.
zwei widersprechende Kräfte sind dabei in Einklang zu bringen. Auf der eine
```

### ga-294 — Erziehungskunst. Methodisch-Didaktisches.

passed; 15 passages; 0 hard-hyphen joins.

- beginning: `ga-294-section-1` — ERSTER VORTRAG Stuttgart, 21. August 1919
- middle: `ga-294-section-8` — ACHTER VORTRAG Stuttgart, 29. August 1919
- end: `ga-294-section-15` — SCHLUSSWORTE Stuttgart, 6. September 1919

`ga-294-section-1` (soft_hyphen)

Before:

```text
 herausgebildet haben, als denjenigen, die wir machen müssen. Wahrhaftig nicht deshalb wer­den sich die Methoden, die wir anwenden, von denjenigen unterschei­den, die bisher eingehalten worden sind, weil wir aus Eigensinn etwas Neues oder A
```

After:

```text
 herausgebildet haben, als denjenigen, die wir machen müssen. Wahrhaftig nicht deshalb werden sich die Methoden, die wir anwenden, von denjenigen unterscheiden, die bisher eingehalten worden sind, weil wir aus Eigensinn etwas Neues oder And
```

`ga-294-section-8` (soft_hyphen)

Before:

```text
Man kann notdürftig dem Intellektuellen des Menschen geschichtliche oder physiologische Be­griffe vor dem 12. Lebensjahr beibringen, aber man verdirbt dadurch die menschliche Natur, man macht sie im Grunde genommen für das ganze Leben ungee
```

After:

```text
Man kann notdürftig dem Intellektuellen des Menschen geschichtliche oder physiologische Begriffe vor dem 12. Lebensjahr beibringen, aber man verdirbt dadurch die menschliche Natur, man macht sie im Grunde genommen für das ganze Leben ungeei
```

`ga-294-section-15` (soft_hyphen)

Before:

```text
erde immer wieder und wie­derum mit meinen Gedanken sorgend auf diese Waldorfschule zurück­kommen müssen. Aber wir können, wenn wir den ganzen Ernst der Lage betrachten, wirklich gut zusammenarbeiten. Halten wir uns namentlich an den Gedank
```

After:

```text
werde immer wieder und wiederum mit meinen Gedanken sorgend auf diese Waldorfschule zurückkommen müssen. Aber wir können, wenn wir den ganzen Ernst der Lage betrachten, wirklich gut zusammenarbeiten. Halten wir uns namentlich an den Gedanke
```

### ga-296 — Die Erziehungsfrage als soziale Frage.

passed; 6 passages; 0 hard-hyphen joins.

- beginning: `ga-296-section-1` — ERSTER VORTRAG Dornach, 9. August 1919
- middle: `ga-296-section-4` — VIERTER VORTRAG Dornach, 15. August 1919
- end: `ga-296-section-6` — SECHSTER VORTRAG Dornach, 17. August 1919

`ga-296-section-1` (soft_hyphen)

Before:

```text
nach und nach umzuentwickeln.
Zu keiner Zeit vielleicht war eigentlich weniger Neigung vor­handen, in wahrem und echtem Sinne des Wortes die Seele zu er­heben zu den geistigen Welten, und notwendig ist es ganz besonders in dieser Zeit, die 
```

After:

```text
nach und nach umzuentwickeln.
Zu keiner Zeit vielleicht war eigentlich weniger Neigung vorhanden, in wahrem und echtem Sinne des Wortes die Seele zu erheben zu den geistigen Welten, und notwendig ist es ganz besonders in dieser Zeit, die Se
```

`ga-296-section-4` (soft_hyphen)

Before:

```text
tellung in sich schließt als hauptsächlichstes Moment gerade die Erziehungsfrage. Und nach­dem ich einiges vor acht Tagen angedeutet habe über die Umgestaltung, die Umwandlung des Erziehungswesens, werden Sie es begreiflich finden, daß wied
```

After:

```text
tellung in sich schließt als hauptsächlichstes Moment gerade die Erziehungsfrage. Und nachdem ich einiges vor acht Tagen angedeutet habe über die Umgestaltung, die Umwandlung des Erziehungswesens, werden Sie es begreiflich finden, daß wiede
```

`ga-296-section-6` (soft_hyphen)

Before:

```text
ufbesserung der Menschheits­kräfte; daß die Menschen wieder mehr zugänglich werden für das­jenige, wovon man möchte, daß die Menschen es wissen, damit es sie erhebt, nicht nur bis zum Engelhaften: bis zum Erzengelhaften, zum Zeitgeistmäßige
```

After:

```text
Aufbesserung der Menschheitskräfte; daß die Menschen wieder mehr zugänglich werden für dasjenige, wovon man möchte, daß die Menschen es wissen, damit es sie erhebt, nicht nur bis zum Engelhaften: bis zum Erzengelhaften, zum Zeitgeistmäßigen
```

### ga-299 — Geisteswissenschaftliche Sprachbetrachtungen

passed; 6 passages; 0 hard-hyphen joins.

- beginning: `ga-299-section-1` — ERSTER VORTRAG Stuttgart, 26. Dezember 1919
- middle: `ga-299-section-4` — VIERTER VORTRAG Stuttgart, 31. Dezember 1919
- end: `ga-299-section-6` — SECHSTER VORTRAG Stuttgart, 3. Januar 1920

`ga-299-section-1` (soft_hyphen)

Before:

```text
n werden kann, nur ganz episodisch sein. Noch mehr als die naturwissenschaftlichen Betrach­tungen müssen diese Sprachbetrachtungen mit einer gewissen Nachsicht genommen werden, weil sie durchaus eine improvisierte Sache sind. Es kann sich a
```

After:

```text
n werden kann, nur ganz episodisch sein. Noch mehr als die naturwissenschaftlichen Betrachtungen müssen diese Sprachbetrachtungen mit einer gewissen Nachsicht genommen werden, weil sie durchaus eine improvisierte Sache sind. Es kann sich al
```

`ga-299-section-4` (soft_hyphen)

Before:

```text
Sie haben gesehen, daß in diesen Betrachtungen es zunächst darauf an­kommt, die sprachgeschichtlichen Momente auf das Seelische zurückzuführen. Man kann in der Tat kein Verständnis des Vorganges der Sprachbildung und a
```

After:

```text
Sie haben gesehen, daß in diesen Betrachtungen es zunächst darauf ankommt, die sprachgeschichtlichen Momente auf das Seelische zurückzuführen. Man kann in der Tat kein Verständnis des Vorganges der Sprachbildung und au
```

`ga-299-section-6` (soft_hyphen)

Before:

```text
nigen unter Ihnen hier, die Lehrer an der Waldorfschule sind, denen sei es in aller Freund­schaft gesagt -, es wäre mir recht, wenn dieses Zweifache bemerkt worden wäre in diesen improvisierten Stunden: erstens die Anregung zur Selbsterzieh
```

After:

```text
nigen unter Ihnen hier, die Lehrer an der Waldorfschule sind, denen sei es in aller Freundschaft gesagt -, es wäre mir recht, wenn dieses Zweifache bemerkt worden wäre in diesen improvisierten Stunden: erstens die Anregung zur Selbsterziehu
```

### ga-319 — Anthroposophische Menschenerkenntnis und Medizin.

passed; 16 passages; 2066 hard-hyphen joins.

- beginning: `ga-319-doc-heading-3` — AUFGEBAUTE HEILMETHODE
- middle: `ga-319-doc-heading-12` — FÜNFTER VORTRAG Den Haag, 15. November 1923
- end: `ga-319-doc-heading-19` — ELFTER VORTRAG London, 29. August 1924

`ga-319-doc-heading-3` (hard_hyphen)

Before:

```text
England), 28. August 1923

Krankheitsvorgänge
als Naturprozesse. Die Gliederung der mensch-

lichen
Organisation in drei Grundprozesse medizinischer Anschau-

ung.
Migräne. Typhus abdominalis. Polarität Nerven- und Leber-

zelle.
Antimonpro
```

After:

```text
(England), 28. August 1923
Krankheitsvorgänge als Naturprozesse. Die Gliederung der menschlichen Organisation in drei Grundprozesse medizinischer Anschauung. Migräne. Typhus abdominalis. Polarität Nerven- und Leber-
zelle. Antimonprozeß. Al
```

`ga-319-doc-heading-12` (hard_hyphen)

Before:

```text
t an dem
Ausdruck

zu
stoßen — durchorganisiert. Also es handelt sich nicht bei der
anthro-

posophischen
Forschungsmethode darum, daß man nun schwefelt von

einem
ausgedachten ätherischen Leib, sondern darum, daß man in der

Tat
— ich kann
```

After:

```text
ht an dem Ausdruck
zu stoßen — durchorganisiert. Also es handelt sich nicht bei der anthroposophischen Forschungsmethode darum, daß man nun schwefelt von
einem ausgedachten ätherischen Leib, sondern darum, daß man in der
Tat — ich kann hier
```

`ga-319-doc-heading-19` (hard_hyphen)

Before:

```text
ür Ihre Aufmerksam-

keit,
die ich zu würdigen weiß, da dasjenige, was ich Ihnen
vorzubrin-

gen
habe, wirklich nicht bloß ein theoretisch Angestrebtes ist,
sondern

etwas,
woran man, wenn man es in der heutigen Zeit vertreten will,

wirkli
```

After:

```text
n für Ihre Aufmerksamkeit, die ich zu würdigen weiß, da dasjenige, was ich Ihnen vorzubringen habe, wirklich nicht bloß ein theoretisch Angestrebtes ist, sondern
etwas, woran man, wenn man es in der heutigen Zeit vertreten will,
wirklich mi
```

### ga-343 — Vorträge und Kurse über christlich-religiöses Wirken, II. Spirituelles Erkennen – Religiöses Empfinden – Kultisches Handeln.

passed; 29 passages; 3765 hard-hyphen joins.

- beginning: `ga-343-doc-heading-3` — ERSTER VORTRAG Dornach, 26. September 1921, nachmittags
- middle: `ga-343-doc-heading-17` — FÜNFZEHNTER VORTRAG Dornach, 3. Oktober 1921, nachmittags
- end: `ga-343-doc-heading-31` — NEUNUNDZWANZIGSTER VORTRAG Dornach, 10. Oktober 1921, nachmittags

`ga-343-doc-heading-3` (hard_hyphen)

Before:

```text
 Sie während
dieses

Ihres
Aufenthaltes hier wirklich, wenigstens teilweise, dasjenige fin-

den
können, was Sie suchen.

Heute
möchte ich zunächst einiges Orientierendes besprechen,

damit
wir uns im richtigen Sinne verstehen können. Denn 
```

After:

```text
ß Sie während dieses
Ihres Aufenthaltes hier wirklich, wenigstens teilweise, dasjenige finden können, was Sie suchen.

Heute möchte ich zunächst einiges Orientierendes besprechen,
damit wir uns im richtigen Sinne verstehen können. Denn das 
```

`ga-343-doc-heading-17` (hard_hyphen)

Before:

```text
 Lehre des Christus Jesus

war
zwar etwas, was in seiner Umgebung völlig als wohltätig
emp-

funden
wurde, aber es war nicht dasjenige, was man in erster Linie

als
das Wichtigste empfand. Für viel wichtiger hielt man es, für
die

Nachfolge
```

After:

```text
e Lehre des Christus Jesus
war zwar etwas, was in seiner Umgebung völlig als wohltätig empfunden wurde, aber es war nicht dasjenige, was man in erster Linie
als das Wichtigste empfand. Für viel wichtiger hielt man es, für die
Nachfolge zu b
```

`ga-343-doc-heading-31` (hard_hyphen)

Before:

```text
ieben Freunde, denn ich

sehe
Ihr Werk als ein außerordentlich wichtiges und bedeutungsvol-

les
für die Gegenwart an. Wenn es Ihnen gelingt, die nötige Stärke

zu
finden, dann wird es so sein — wollen wir hoffen, daß wir
alle

dazu
die nöt
```

After:

```text
lieben Freunde, denn ich
sehe Ihr Werk als ein außerordentlich wichtiges und bedeutungsvolles für die Gegenwart an. Wenn es Ihnen gelingt, die nötige Stärke
zu finden, dann wird es so sein — wollen wir hoffen, daß wir alle
dazu die nötige S
```
