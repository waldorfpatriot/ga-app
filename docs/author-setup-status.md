# Author setup status

Evidence snapshot: 11 October 2026, 02:55 CEST. Refresh with `python3 tools/summarize_author_setup.py` as setup progresses.

Verified setup: Apple draft configuration 11/11, CloudKit production and store profiles 11/11, RevenueCat 11/11, live backends 11/11.

| Author | Apple drafts and products | CloudKit production | RevenueCat | Backend |
| --- | --- | --- | --- | --- |
| Maria Montessori | Verified | Verified | Verified | Verified |
| Friedrich Nietzsche | Verified | Verified | Verified | Verified |
| Karl May | Verified | Verified | Verified | Verified |
| Jane Austen | Verified | Verified | Verified | Verified |
| Arthur Conan Doyle | Verified | Verified | Verified | Verified |
| H. P. Lovecraft | Verified | Verified | Verified | Verified |
| Fyodor Dostoevsky | Verified | Verified | Verified | Verified |
| Johann Wolfgang von Goethe | Verified | Verified | Verified | Verified |
| Franz Kafka | Verified | Verified | Verified | Verified |
| H. P. Blavatsky | Verified | Verified | Verified | Verified |
| Emanuel Swedenborg | Verified | Verified | Verified | Verified |

The original GA app's 94 baseline files are unchanged. The live GA process, protected configuration and release are preserved. Backend verification is recorded at `2026-10-11T00:42:19.348832+00:00`.

Each verified Apple draft has its own app record, iOS/Mac metadata, €30/€90 products and three-month introductory trials. CloudKit evidence covers the production schema and author-specific store profile entitlements; it does not establish real-device sync. RevenueCat verification covers the independent project, management entitlement mapping, public offering and ignored local SDK configuration; it does not establish a real Apple purchase.

All live backends have isolated databases/secrets and daily authenticated encrypted backups. Complete access-flow checks and catalog/page integrity results are in [the backend report](author-backend-deployment.md).

Before App Store release:

- Signed distribution build uploads and screenshots.
- Real StoreKit purchase/restore and iCloud sync checks on signed devices.
- App privacy, content-rights and age-rating declarations before review.
- App Store review and publication.

Detailed evidence: [setup JSON](../editions/setup-status.json), [Apple drafts](author-apple-setup.md), [CloudKit readback](../editions/cloudkit-readback-verification.json), [RevenueCat public verification](../editions/revenuecat-public-verification.json), [backend verification](../editions/backend-deployment-verification.json).
