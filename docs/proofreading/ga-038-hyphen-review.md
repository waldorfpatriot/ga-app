# GA 038: Bindestriche und Wortfortsetzungen

88 Stellen in 24 der 49 Lesetextabschnitte sind am Originaldruck geprüft:
81 physische Worttrennungen, drei historische ck-Trennungen, zwei falsche
Leerraumunterbrechungen hinter echten Bindestrichen und zwei ausgefallene
Satzfortsetzungen. Zum Beispiel wird `National-Lite-ratur` zu
`National-Literatur`; der echte Bindestrich bleibt erhalten. `schik-ken`
wird entsprechend der damaligen Druckregel zu `schicken`.

Die letzten Satzzeilen `lenkten?` (PDF-Seite 66) und `gen sein.`
(PDF-Seite 189) stehen deutlich im Scan, fehlen aber im PDF-Textlayer
und im daraus abgeleiteten EPUB/DOC. Deshalb sind ausschließlich
`hin-` → `hinlenkten?` und `unterzubrin-` → `unterzubringen sein.` ergänzt.
Die eingerückten Grußformeln bleiben eigene Absätze.

Der [eingefrorene Review](../../tools/ga038_hyphen_review.json) bindet
Original-DOC, EPUB und PDF an ihre SHA256-Prüfsummen. Jede Stelle hat exakte
EPUB-Absatzbelege, gedruckte Vor-/Folgezeilen und ursprüngliche Scanpixel.
Bei den beiden fehlenden Textlayer-Zeilen ist die visuelle Transkription
zusätzlich eng auf den konkreten Abschnitt, Wortlaut und Scan gebunden.
Der [unabhängige Prüfer](../../tools/check_ga038_hyphens.py) rekonstruiert die
Änderungen ohne den Reparaturcode. Alle 49 Eingang-/Ausgangsprüfsummen sind
festgehalten; Quelltexte, Kennungen, Titel und sonstige Metadaten bleiben erhalten.

Echte Zusammensetzungen und Ergänzungsstriche sind erhalten. Andere
OCR-Buchstaben und die im Review separat vermerkten Nummerierungsartefakte
sind nicht Bestandteil dieser Worttrennungskorrektur.

Der Gesamtabgleich aller 324 Bände, 13 gezielte Reparaturtests, drei unabhängige
Scope-Prüfungen, die bestehenden gemeinsamen Regressionen, der echte Swift-
EPUB-Export und die native Downloadprüfung sind erfolgreich. Die lokale
Leseansicht zeigt die geprüften Stellen vollständig; Leserexport und Apple-
Katalog enthalten alle 49 korrigierten Abschnitte. Die übrigen 323 kanonischen
Inhaltsdateien sind bytegleich mit dem Eingang dieser Korrektur.
