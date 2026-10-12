# Separate author infrastructure

The eleven author apps use the existing Phoenix access backend code and the
Steiner static-reader API format. The Steiner deployment and its data are not
changed. Each author has an independent PostgreSQL role/database, Linux user,
service, loopback port, reader snapshot, runtime message-encryption key and
backup key. Paid access is configured separately for each app in App Store
Connect and RevenueCat; the backend continues to grant only the requested free
year. A grant or subscription in one author's app does not unlock another app.

The authoritative configuration is `editions/authors.json`. Every edition's
`deploy/identity.json` records its derived host paths. The corresponding app has
its own bundle identity and CloudKit container. App Keychain and local reading
storage isolation are implemented in the shared author reader configuration.

## Generate and validate locally

```sh
python3 tools/generate_author_infrastructure.py --dry-run
python3 tools/generate_author_infrastructure.py
python3 tools/generate_author_infrastructure.py --check
python3 -m unittest discover -s tools -p test_author_infrastructure.py -v
```

Use `--slug franz-kafka` to generate or check one author. Generation validates
every selected input before writing any output. It only replaces the selected
edition's managed `deploy/` tree. Regeneration removes obsolete reader files,
so withdrawing a work also removes its public download. Do not store private
keys or untracked operational material in this generated tree.

Inputs are `editions/<slug>/library/catalog.json` and
`editions/<slug>/library/content/<work-id>.json`. Output under `deploy/reader/` matches
the existing JSON API:

| Reader-relative path | Response |
| --- | --- |
| `catalog.json` and `api/catalog/index.json` | Public catalog |
| `api/catalog/<work-id>/index.json` | Individual work |
| `api/catalog/<work-id>/manifest` | Exact bundle checksum, byte count and passage list |
| `api/catalog/<work-id>/content` | Complete text bundle |

The exporter verifies passage IDs/counts, text checksums, complete-work labels
and catalog/content agreement. It rejects private source text, credentials,
symlinked inputs, partial bundles and an incorrect author. Catalog revisions
hash the exact bytes exported to the download endpoint; dates come from the
input catalog's stable UTC timestamp. Generated manifests do not claim human
proofreading when the source catalog has not recorded it. Editorial source and
edition checks remain documented in each author's source manifest.

## Host layout

For `franz-kafka`, the generated layout is:

| Resource | Value |
| --- | --- |
| systemd service | `author-franz-kafka.service` |
| OS user/group | `ga-franz-kafka` |
| PostgreSQL role/database | `author_franz_kafka` |
| Listener | `127.0.0.1:4148` |
| Shared-code release | `/opt/author-franz-kafka/current` |
| Protected configuration | `/etc/author-franz-kafka/` |
| Runtime state | `/var/lib/author-franz-kafka/` |
| Public reader snapshot | `/var/lib/author-franz-kafka-reader/current` |
| Public app pages | `/var/lib/author-franz-kafka-web/current` |
| Protected backup archive | `/var/backups/author-franz-kafka/` |
| Access base URL | `https://fototausch.eu/franz-kafka` |
| Reader base URL | `https://fototausch.eu/franz-kafka-reader` |

The nginx snippet proxies only `/franz-kafka/api/access/...` and the exact
`/franz-kafka/api/health` runtime check. Other Phoenix API routes, including its
Steiner catalog and developer routes, return 404 at this author mount. The
separate reader mount serves the author's validated static tree. Health is the
shared Phoenix runtime response, not evidence that App Store subscriptions have
been configured or that an access database has passed an end-to-end check.

The public `index.html`, `privacy.html` and `support.html` files come from the
edition's `web/` folder. Only exact landing/index/privacy/support routes are
served beneath the access base URL, using a separately verified static web
snapshot and a restrictive content-security policy. The installer verifies
both reader and web snapshots before copying either onto the host.

## Initialize on the Linux host

Build one Linux `ga_server` release from the unchanged `server/` directory and
its pinned lockfile. The same release bytes are copied into independent author
release directories. A macOS Erlang release is not suitable for the Linux host.
Copy an author's generated `deploy/` directory onto the host. By default its
installer performs only read-only checks:

```sh
sudo python3 deploy/initialize-host.py --release /path/to/linux/ga_server
```

It verifies tool availability, nginx syntax, the exact reader inventory, port
availability, managed-resource ownership, PostgreSQL connection headroom and
available memory. Existing unknown users, databases or deployment paths cause
a stop. It prints aggregate capacity information and never prints a secret.

After host capacity and the concrete generated layout have been reviewed,
initialize the isolated service:

```sh
sudo python3 deploy/initialize-host.py --release /path/to/linux/ga_server --apply
```

This generates three independent secret values plus the database password on
the host, writes root-owned private configuration, creates the new role/database
and OS user, copies the Linux release, runs migrations and retention, installs
the validated reader snapshot and service/backup/nginx files, and reloads
systemd's unit inventory. Service and backup-timer activation, nginx inclusion
and nginx reload are subsequent explicit steps. The installer does not activate
them itself. A recorded incomplete first initialization can resume using the
same secrets; subsequent updates preserve both runtime and backup keys.

For this example, activation commands are:

```sh
sudo systemctl enable --now author-franz-kafka.service
sudo systemctl enable --now author-franz-kafka-backup.timer
sudo systemctl start author-franz-kafka-backup.service
```

Include `/etc/nginx/snippets/author-franz-kafka.conf` once inside the existing
HTTPS server block, run `nginx -t`, and reload nginx only after that passes.
Keep a copy of the previous site configuration for rollback. Check the public
health/catalog endpoints and complete an anonymous installation/free-grant/
recovery/deletion check before treating this edition as live. Never log those
requests' bodies, Authorization values or recovery credentials.

### Capacity before activating all eleven

The generated defaults use a two-connection pool, one scheduler and a 256 MiB
service memory ceiling. Author releases use `RELEASE_MODE=interactive`, loading
the unchanged modules on demand rather than preloading the whole release. This
is the [documented Elixir release mode](https://mix.hexdocs.pm/Mix.Tasks.Release.html)
for reducing startup memory. This preserves the same backend architecture and access behavior while
reducing the aggregate pool from 110 to 22 possible connections. Eleven service
ceilings total 2.75 GiB, in addition to PostgreSQL, nginx, the existing GA service
and other applications. A ceiling is not an estimate of typical resident memory.

The host inspection on 10 October 2026 found about 3.8 GiB total RAM, 1.2 GiB
available RAM, 1.5 GiB swap already in use, and PostgreSQL's `max_connections`
set to 100. On 11 October, a staged author service with preloaded modules used
about 142 MiB. Switching only author services to interactive loading reduced
the tested full access flow to about 63 MiB. All eleven were then activated
incrementally, checking available memory and the original GA process and files
at every step. The final verified fleet used about 730 MiB, zero fleet swap,
and the host retained about 1.3 GiB available memory. No host upgrade was needed.

All author services belong to `author-apps.slice`, with an aggregate 896 MiB
memory high threshold, 1 GiB ceiling and 128 MiB swap ceiling. Original GA and
other applications do not belong to this slice. This contains author memory
growth; exceeding its ceilings can terminate an author service. Measure real
traffic before increasing these limits. A passing individual preflight remains
insufficient for a future fleet expansion. Current deployment and end-to-end
evidence are in [the deployment report](author-backend-deployment.md) and
`editions/backend-deployment-verification.json`.

Copied releases replace the source deployment's Erlang cookie with a new
independent cookie owned by the author user and readable only by that user.
The remaining release file bytes are shared code. Runtime secrets, database
passwords and backup keys remain root-private and are never included in reports.

## Same privacy and retention behavior

Each isolated service runs the unchanged backend: immediately granted free
calendar years only after an explicit request, hashed access/recovery secrets,
AES-256-GCM confidential request text, ciphertext erasure after 30 days on the
hourly worker, selection-event erasure after 90 days, and cascading installation
deletion. Personal notes/bookmarks/highlights remain in the app's private
CloudKit database and are not stored by this catalog or access service.

Backups use the same encrypted-archive plus separate HMAC design as Steiner.
Each author has its own root-private `/etc/<service>/backup-key`; its independent
HMAC domain includes the service name. The runtime environment is inside the
encrypted archive; the backup key is outside it. Daily jobs are staggered from
03:15 through 03:25 UTC for the current eleven ports. Each service retains at
most seven local daily snapshots and prunes snapshots older than seven days on
a successful daily pass. Live-erased messages can persist in protected backups
for up to seven additional days while these jobs run. Stopped or failed jobs
delay erasure. No offsite backup is created.

Preserve an independently secured copy of encrypted archives and their separate
backup keys for host-loss recovery. Authenticate the HMAC before decrypting or
extracting an archive. Run retention after restoring a database and before
serving requests; reapply known installation-deletion requests. Never restore an
author's database or secrets into another author's service.

## Updates and rollback

Regenerate and check the local deploy tree after changing a catalog or content
bundle. Re-run the host initializer with a new Linux-built shared release to
migrate and install it; the release path is derived from all release-file bytes.
Restart only the selected author's service after reviewing the completed
initialization. Current and prior reader/code release directories remain
available for rollback. Keep an independently recorded current-link target
before updating.

To withdraw an author temporarily, remove its nginx include, validate/reload
nginx, and stop that author's service and backup timer. Preserve its database,
runtime environment, backup key and archives. Repointing a code release is safe
only when migrations remain compatible; a destructive migration requires a
separate database rollback plan. No withdrawal or update command needs to touch
the Steiner deployment.
