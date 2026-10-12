# App Review notes

Prepared for version 1.0.1, build 4 of shared Apple app 6820947669, iOS/iPadOS and native macOS, on 11 October 2026. iOS/iPadOS 1.0, build 3 has already been approved and published; the original Mac 1.0, build 3 submission has been withdrawn and both replacement App Store review packages are ready for final submission. These notes describe the updated implementation and do not confirm a new submission. The build 4 privacy manifest contains six data categories; Customer Support still needs to be added and published in App Store Connect with App Functionality, linked to the user, and no tracking. Earlier references to private platform drafts describe the original preparation, and separate Mac-app notes are historical. Do not include this preparation notice in the App Review Notes field.

The app is an independent German-language reader for Rudolf Steiner's writings and lectures, not an official Gesamtausgabe app. Unavailable books show “Coming soon”; five complete core works are bundled. A subscription does not promise every catalog entry.

Catalog browsing is free. Reading, text downloads and EPUB export require active app access. Open an available book or “App-Zugang” in the library menu to see the access screen.

“GA Jahresabo” and “GA Förderabo” are annual auto-renewing subscriptions with identical features. The higher voluntary contribution supports free access. iPhone, iPad and native Mac use one app record, bundle ID and subscription group with two products: com.jonathankutscher.ga.annual and com.jonathankutscher.ga.supporter. German prices are EUR 30 and EUR 90 per year; the actual Store price appears before purchase. Eligible Apple accounts receive three calendar months of free trial, renewing into the chosen annual subscription unless cancelled through Apple. StoreKit/RevenueCat checks eligibility; there is no separate server-issued trial.

The solidarity option “Ein kostenloses Jahr anfragen” requires only a nonempty private request, without income evidence or email sign-up. Enter “Bitte ermögliche mir ein kostenloses Jahr.” and tap “Bitte absenden”. The server immediately grants twelve months of identical access, without payment or conversion to a paid subscription. New requests are possible at any time.

“Käufe wiederherstellen” restores Apple purchases; “Abo verwalten” opens Apple subscription management. A private recovery code restores free access. “Zugangsdaten löschen” deletes installation data, free requests, reports and selection events, without cancelling Apple subscriptions. No developer sign-in is required. Access statistics show 90 days of selection clicks, not purchases.

Reading progress, notes, highlights and collections stay on device and optionally in the user's private CloudKit database. They are not automatically sent to our backend. Purchases use Apple and RevenueCat with a pseudonymous app user ID. Support and privacy links are in the access screen.

New: select text and choose “Fehler melden …” in the context menu. The form displays the excerpt and reference, with an optional description. Only “Senden” submits it; “Abbrechen” sends nothing. Reporting has no payment gate, email requirement or active-entitlement check. It authenticates the random pseudonymous installation ID; this is linked data, not anonymous data. Reader access is separate and can be obtained through the free option above.

Reports include the selected excerpt, book/section identifiers, optional section title and selection offsets, optional description, report ID, platform, app version and build. Other notes and highlights are not included; reports are not sent to RevenueCat. The database payload is AES-256-GCM encrypted and erased after 180 days by hourly retention, normally within one additional hour while running. Minimal receipt IDs/timestamps and a keyed HMAC remain until installation deletion to deduplicate retries. Backups may retain erased content seven days longer. Authorized operators can make private copies (erased within 24 hours by hourly cleanup while running); no HTTP read endpoint exists.

Test: open “Die Philosophie der Freiheit” (GA 004), using the free-year request above if needed. Select a short phrase; use the selection menu on iPhone/iPad or right-click on Mac. Choose “Fehler melden …”, check the excerpt/reference, and optionally enter “Testmeldung für App Review – keine Korrektur erforderlich.”. Tap “Senden”: after confirmed receipt, the form closes and “Meldung gesendet” appears. Try “Abbrechen” with another selection. For a network failure, disable the connection before sending: the input remains available for retry.

EPUB export is in the book actions and excludes personal annotations.

Review contact: Jonathan Kutscher, jonathan@kutscher.club, +49 179 9439545.
