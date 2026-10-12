# Author backend deployment — 11 October 2026

All eleven author backends are active on the existing `photo-share-prod` host.
Their HTTPS access and reader URLs are recorded in `editions/authors.json`.
For example, [Kafka's catalog](https://fototausch.eu/franz-kafka-reader/api/catalog)
and [Montessori's backend health](https://fototausch.eu/maria-montessori/api/health)
are live. This backend report does not establish Apple, RevenueCat or CloudKit
release readiness.

## Installed resources

Each author has an independent PostgreSQL role/database, Linux user, loopback
listener, systemd service, runtime encryption key, backup key and public snapshots.
All copies use the unchanged Linux GA release at
`/opt/ga-access/releases/20261009-02`, with independent protected Erlang cookies.
No original GA code, service configuration, data or release link was changed.
The original GA process continued running throughout deployment.

The shared HTTPS site received one additional include:
`/etc/nginx/snippets/author-editions.conf`. It includes only the eleven author
snippets. Original GA route snippets remain byte-identical. The site was backed
up before this change, validated before reload, and checked afterward for any
additional edits. Root-private baseline and rollback material remain at
`/var/lib/author-editions-deployment-20261011/` on the host. They are not copied
into this repository.

## Verification

The [machine-readable report](../editions/backend-deployment-verification.json)
records every author's result. All eleven passed:

- Public health and exact-byte validation of all 85 reader files, 21 complete
  downloads and 33 app pages.
- Creation of an anonymous installation, inactive initial state and an explicit
  request granting one free calendar year.
- Confidential request text encrypted in the database and absent from service logs.
- Recovery preserving the grant while replacing the access token and rejecting
  the previous token.
- Deletion removing the installation and its associated request/selection rows.
- Rejection of another author's access credential, and blocking the shared
  release's other catalog/developer routes at the author access mount.
- Enabled daily backup timers and successful encrypted backups authenticated
  with each author's independent HMAC key. Decryption and PostgreSQL archive
  inventory checks passed; this does not claim a full disaster recovery rehearsal.

Temporary grant checks were deleted immediately. No real user grant or payment
was created. Credentials, request bodies and secret values are absent from the
saved verification report.

## Capacity and operation

Preloaded release modules used about 142 MiB for a staged service. Author-only
`RELEASE_MODE=interactive` reduced the full access test to about 63 MiB without
changing any application code. With all eleven active, the measured fleet used
about 730 MiB, no fleet swap, and left about 1.3 GiB available on the 3.8 GiB host.
The original GA continues using its original settings.

`author-apps.slice` limits the author fleet to 1 GiB RAM and 128 MiB swap, with an
896 MiB memory high threshold. Each author retains a two-connection database
pool, 192 MiB memory high threshold and 256 MiB ceiling. These measurements cover
deployment and access verification, not sustained production traffic. Review
the fleet's memory, health, restart counts and PostgreSQL connections when real
usage begins. Do not enlarge its limits without checking the other services.

Backups retain at most seven daily snapshots locally. No offsite backup was
created. Runtime state, database passwords and backup keys stay on the host.
See [infrastructure instructions](author-infrastructure.md) for secure backup
handling and restore requirements.

## Withdrawal and rollback

To withdraw one author, remove only its line from `author-editions.conf`, validate
and reload nginx, then stop its service and backup timer. Preserve its database,
protected secrets and backup archives. For example:

```sh
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl disable --now author-franz-kafka.service
sudo systemctl disable --now author-franz-kafka-backup.timer
```

To withdraw the complete fleet, remove only the new author aggregate include
from the HTTPS site, validate/reload nginx, and stop the eleven author services
and timers. Existing GA routes and services require no changes. The protected
site backup is available for comparison; restoring the whole file later requires
checking that no unrelated changes have occurred since this deployment.
