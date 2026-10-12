# Author-only Apple setup

The author setup tools use `editions/authors.json` as their allowlist. They exclude the existing Steiner bundle IDs and app records. They create editable configuration only; they never select builds, submit review, publish, delete resources or modify existing provisioning capabilities.

## Credentials

Provide `ASC_KEY_ID`, `ASC_KEY_PATH` and `ASC_ISSUER_ID` through the calling process environment. Do not commit private keys, JWTs or credential files. Provisioning requires a team API key. An individual key uses `sub=user` without an issuer and cannot access provisioning endpoints.

The Apple client signs short-lived ES256 tokens and sends them only to Apple's official API origin. The author tools and their reports contain no private key material or tokens.

## Identifiers and CloudKit

```sh
python3 tools/provision_author_bundle_ids.py --plan
python3 tools/provision_author_bundle_ids.py --report editions/apple-provisioning-state.json
python3 tools/provision_author_bundle_ids.py --apply --report editions/apple-provisioning-state.json
```

The default command only reads. `--apply` creates missing exact author Bundle IDs and missing iCloud capabilities configured for CloudKit. Existing conflicting settings stop that author's setup and are preserved. Registration uses Apple's `IOS` creation value; Apple returns the resulting shared identifier as `UNIVERSAL`. One explicit App ID supports both the native iOS and macOS targets. Identifier descriptions omit punctuation that Apple's provisioning service rejects; App Store display names keep their prepared spelling.

All eleven author Bundle IDs were registered on 11 October 2026. A subsequent read-only pass verified `UNIVERSAL`, CloudKit's `XCODE_6` selection and default In-App Purchase for each. The report records Apple's public resource IDs and the expected separate iCloud containers.

The public API exposes no iCloud-container creation or association endpoints. Enabling `ICLOUD` alone does not verify a container association. Create and associate only the exact corresponding `iCloud.<author-bundle-id>` in Developer portal or Xcode, then initialize and deploy that author's production schema. Record UI/CloudKit evidence separately. The copied reader uses foreground/manual synchronization and has no push entitlement or CloudKit notification subscription.

## App records, subscriptions and metadata

Create one App Store Connect app record per author using the exact manifest bundle and German primary language. Add iOS and macOS to that same record for universal purchase. The public API cannot create the initial app record.

```sh
python3 tools/setup_author_apple.py --plan
python3 tools/setup_author_apple.py --author jane-austen --step all
python3 tools/setup_author_apple.py --author jane-austen --step all --apply \
  --report editions/jane-austen/app-store/apple-setup-state.json
```

Omit `--author` to configure all eleven records. `--app-id` can pin the expected Apple record when selecting exactly one author; the tool verifies that it belongs to the allowlisted bundle before writes. `--step products`, `prices` and `metadata` can resume a particular setup phase. `--platform ios` or `macos` limits metadata to one platform; the default covers both.

The setup creates one separate subscription group and two author products: `.annual` and `.supporter`, each for one year at €30 and €90 in Germany, with the same features and a three-month introductory free trial. The prices step adds Apple's required territory price mappings without expanding the Germany-only purchase availability or replacing existing price rows. Metadata comes from each author's prepared German release file. App versions retain manual release.

The tools stop on conflicting existing records instead of removing them. Re-running a completed phase preserves matching resources. Apply commands serialize by author on this machine; different author records can be configured independently. A prices-only apply command requires both products and their German base prices before it reports success. Saved results are credential-free API readback evidence; they do not confirm signed builds, screenshots, production CloudKit schemas, actual purchases, restore, synchronization, legal attestations, Apple review or publication.

Official references: [Apple JWTs](https://developer.apple.com/documentation/appstoreconnectapi/generating-tokens-for-api-requests), [API key roles](https://developer.apple.com/documentation/appstoreconnectapi/creating-api-keys-for-app-store-connect-api), [shared App IDs](https://developer.apple.com/help/account/identifiers/register-an-app-id/), [universal-purchase platforms](https://developer.apple.com/help/app-store-connect/create-an-app-record/add-platforms/).
