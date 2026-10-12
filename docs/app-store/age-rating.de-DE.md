# Inhaltsbewertung für die Alterseinstufung

Stand: 11. Oktober 2026. Diese Bewertung bezieht sich auf die 324 tatsächlich verfügbaren Textdateien des aktuellen Katalogs, einschließlich der fünf mitgelieferten Werke. Die 139 noch nicht verfügbaren Einträge sind keine auslieferbaren Lesetexte. Der gespeicherte Apple-Fragebogen und die von Apple berechnete Einstufung stehen im [Einrichtungsstand](publishing/setup-state.md).

Alle 324 JSON-/Gzip-Dateien wurden nach Themenbegriffen durchsucht; anschließend wurden Fundstellen und ihr Kontext gezielt gelesen. Die Wortsuche dient der Auswahl von Prüfstellen, nicht der automatischen Einstufung. Insbesondere sind metaphorische Waffen, anatomische Begriffe und philosophische Hinweise auf Sexualität keine erotischen Darstellungen. Die App ist eine historische Lesebibliothek für Erwachsene, keine Kinder-App.

| Apple-Inhaltsfeld | Bewertung | Konkrete Grundlage |
| --- | --- | --- |
| `medicalOrTreatmentInformation` | `FREQUENT_OR_INTENSE` | Vollständige medizinische und therapeutische Vortragsbände, insbesondere GA 312, 313, 314, 317 und 319. Historischer Kontext beseitigt den medizinischen Inhalt nicht. |
| `matureOrSuggestiveThemes` | `FREQUENT_OR_INTENSE` | Wiederkehrende politische, weltanschauliche, rassistische und kriegsbezogene historische Aussagen, unter anderem GA 173/174 und die Vorträge zur Zeitlage. |
| `violenceRealistic` | `NONE` | Redaktionelle Korrektur für Version 1.0.1 auf Anweisung des Herausgebers: Die Gewaltangabe wird deaktiviert. Die historischen Textbezüge zu Krieg und Tötung bleiben im unveränderten Katalog enthalten; die frühere konservative Angabe war `FREQUENT_OR_INTENSE`. |
| `violenceCartoonOrFantasy` | `NONE` | Für Version 1.0.1 deaktiviert. Keine Spielmechanik oder animierten Kampfszenen; mythologische und übersinnliche Textbezüge bleiben unverändert. |
| `horrorOrFearThemes` | `INFREQUENT_OR_MILD` | Übersinnliche, Todes- und Angstthemen in historischen Darstellungen. |
| `alcoholTobaccoOrDrugUseOrReferences` | `INFREQUENT_OR_MILD` | Hinweise auf Konsum und Wirkungen, beispielsweise in GA 348, 349, 352 und 354. |
| `gunsOrOtherWeapons` | `INFREQUENT_OR_MILD` | Historische und mythologische Waffenbezüge, einschließlich Schwertern in den Apokalypse-Vorträgen. |
| `profanityOrCrudeHumor` | `INFREQUENT_OR_MILD` | Vereinzelte abwertende historische Sprache und diskriminierende Begriffe; keine humoristische oder werbliche Nutzung. |
| `sexualContentOrNudity` | `NONE` | Geprüfte Fundstellen behandeln Sexualität begrifflich oder anatomisch; keine erotische Darstellung oder Nacktbilder gefunden. |
| `sexualContentGraphicAndNudity` | `NONE` | Keine expliziten sexuellen Darstellungen gefunden. |
| `violenceRealisticProlongedGraphicOrSadistic` | `NONE` | Keine anhaltende grafische Gewaltdarstellung in den geprüften Stellen. GA 171, `ga-171-pdf-outline-55-7`, wurde wegen des schweren Inhalts gesondert gelesen: Die knappe Verletzungsbeschreibung steht in einer historischen beziehungsweise mystischen Erörterung, die die Tötung verurteilt. Die zuvor höhere Angabe bei realistischer Gewalt wurde am 11. Oktober 2026 auf Anweisung des Herausgebers deaktiviert. Dies ist eine redaktionelle Einordnung, keine Garantie von Apples Reviewentscheidung. |

`healthOrWellnessTopics` ist wahr. Werbung, öffentlicher Nutzerinhalt, soziale Feeds, Chat, unbeschränkter eingebetteter Webbrowser, Glücksspiele, Lootboxen, Wettbewerbe und app-eigene Alters-/Elternkontrollen sind nicht vorhanden. Private Notizen und vertrauliche Gratisbitten werden nicht als öffentlicher Nutzerinhalt verbreitet. Der Abo-Kaufbildschirm ist keine Werbefläche für fremde Produkte.

Die drei Gewaltfelder wurden am 11. Oktober 2026 im editierbaren gemeinsamen Apple-AppInfo auf `NONE` gespeichert und exakt zurückgelesen; Beleg: `artifacts/app-store/age-rating-1.0.1-readback.json`. Medizinische Informationen und erwachsene Themen bleiben unverändert angegeben. Die territoriale Apple-Abfrage bestätigt bereits `SIXTEEN_PLUS` für Deutschland und die USA; Beleg: `artifacts/app-store/territory-age-ratings-1.0.1.json`. Das veraltete globale API-Feld zeigte direkt nach der Änderung noch `SEVENTEEN_PLUS` und ist dafür kein maßgeblicher Readback. Die neue Einstufung wird mit dem überarbeiteten AppInfo zur Prüfung übermittelt. Es wurde keine Altersüberschreibung gesetzt. Es wurden keine Texte gekürzt oder ausgeblendet, um eine niedrigere Altersfreigabe zu erreichen. Bei neuen oder korrigierten Texten die Inhaltsbewertung erneut prüfen.

Grundlage für die Kategorien und die automatische Berechnung sind Apples [Alterskategorien und Definitionen](https://developer.apple.com/help/app-store-connect/reference/app-information/age-ratings-values-and-definitions/) und [Anleitung zum Altersfragebogen](https://developer.apple.com/help/app-store-connect/manage-app-information/set-an-app-age-rating/).
