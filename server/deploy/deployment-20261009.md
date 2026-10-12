# GA access deployment — 9 October 2026

Canonical production app/access base URL: **https://fototausch.eu/rudolf-steiner-ga**. API paths append `/api/access/...`, for example `/rudolf-steiner-ga/api/access/status`. The old **https://fototausch.eu/ga-access** base remains a direct compatibility alias during the transition; both use the same identities/data and neither redirects POST bodies.

## Installed service

- SSH alias: `photo-share-prod`; Debian 13, Elixir 1.18.3, Erlang/OTP 27, PostgreSQL 17, nginx.
- Isolated OS user/service: `ga-access`, `/etc/systemd/system/ga-access.service`.
- Isolated Postgres role/database: `ga_access`. No existing application database was migrated.
- Linux-built release: `/opt/ga-access/releases/20261009-02`; `/opt/ga-access/current` symlinks to it. Previous release `20261009-01` is retained. Source build is `/opt/ga-access/build-20261009`.
- The service listens only on `127.0.0.1:4131`, with two Erlang schedulers, a 512 MiB memory ceiling and 128-task ceiling.
- Runtime environment: `/etc/ga-access/environment`, owned root:root, mode 0600. Database password, Phoenix signing secret and AES message-encryption key were generated on this host and never printed or checked into source.
- nginx snippet: `/etc/nginx/snippets/ga-access.conf`, included from the existing HTTPS virtual host. Only access routes are exposed under the canonical and compatibility mounts. Exact landing/privacy/support routes under `/rudolf-steiner-ga/` are maintained independently. Proxy body ceiling is 64 KiB, body/auth-header logging is not configured, and the proxy replaces `X-Real-IP`.
- Previous virtual host snapshot: `/etc/nginx/sites-available/fototausch.eu.before-ga-access-20261009`.

Provider and hosting country have not been verified. Do not infer them from the SSH alias or domain.

## Retention, logs and backups

The app erases confidential request ciphertext after 30 days on its hourly pass and prunes option-click events after 90 days. Minimal free-request/grant identity metadata remains until installation deletion. An authenticated deletion cascades through credentials, grants, requests and click events.

Access endpoint/route logs are disabled in Phoenix. Parameter filters cover message and credentials; production logging is INFO. No QA request text appeared in the service journal. nginx's existing default access logging includes remote IP, path and status, but no body or Authorization header. Its existing rotation is daily with 14 retained rotations, plus the current log. journald has default size-bound retention, with no configured `MaxRetentionSec`; there is no claimed fixed service-journal lifetime.

`ga-access-backup.timer` runs daily. `/usr/local/sbin/ga-access-backup` makes a Postgres custom-format dump and includes the protected runtime environment, encrypts the archive using AES-256-CBC/PBKDF2 (200,000 iterations), and writes an HMAC-SHA-256 authentication tag. The independent passphrase is `/etc/ga-access/backup-key` (root:root, mode 0600); it is not inside the archive. Archives live in `/var/backups/ga-access`, with mode-0700 directories and mode-0600 files. Plain temporary contents are removed immediately after encryption. At most seven daily snapshots are retained; those older than seven days are pruned on a successful daily pass. If the job is stopped or fails, expiry is delayed until it runs again.

Messages erased from the live database may remain in protected backups for up to seven additional days (up to 37 days from receipt while scheduled jobs run). Installation deletion is subject to the same backup expiry. On restore, run retention before serving requests and reapply known deletion requests. No offsite backup is configured; store an independently secured copy of both encrypted archives and the separate backup key for recovery from total host/disk loss.

The deployed backup was authenticated, decrypted and restored into a new disposable database. All three access tables and byte-for-byte preservation of the private runtime environment were verified. The scratch database and plaintext verification files were removed.

## Verified behavior

- Full original local Phoenix suite: 58 tests passed. Final focused access tests, including malformed-body privacy regressions: 24 passed. The final expanded suite passed 59/60 tests; the unchanged all-catalog download check hit its fixed 120-second timeout while the Mac was busy. That check then passed separately under `--trace` (398.6 seconds, no assertion failure), covering all 60 final cases.
- Linux production release assembled successfully and additive migration completed on the new database.
- nginx configuration passed `nginx -t` before reload.
- Public HTTPS test covered initial inactive status; immediate calendar-year free grant; request/click retry deduplication; public aggregate statistics; recovery with new bearer and old-bearer revocation; installation deletion and recovery revocation; and `Cache-Control: no-store`.
- Release 02 also verified generic malformed-JSON and unsupported-media responses, no unintended grant from malformed input, and no raw QA body snippets in service logs.
- Local and Linux-build SHA-256 values match for the access context, endpoint, private-body parser and migration.
- QA installation, requests and selections were deleted. Production tables were empty after verification.
- `ga-access`, existing `ga-library`, and nginx services remained active. Existing `https://fototausch.eu/ga-reader/catalog.json` still returned HTTP 200.
- Local UI backend remains on `http://127.0.0.1:4181`, using disposable `ga_access_ui_20261009`. Its selection table was cleared for screenshots.

## Rollback and future releases

To withdraw the new API, remove its include from the HTTPS virtual host, validate nginx, reload, and stop/disable `ga-access.service`. The snapshot records the prior virtual-host contents; compare before restoring it so later unrelated changes are preserved. Keep the database, secret environment, backup key and encrypted backups unless deletion is explicitly intended. The existing catalog service/data do not depend on this new service.

Future code releases should be built on Linux against the pinned `mix.lock`, migrated from a readable release directory with the protected runtime environment, and activated by changing `current` before restarting this service. Preserve secret values. Do not copy a macOS-built Erlang release to this host. If a migration is destructive, plan data-compatible rollback separately; the initial migration only creates isolated tables.
