# GA

## Solidarity access backend

The app uses RevenueCat/StoreKit for paid access and Apple's introductory subscription trial. This backend grants **only an explicitly requested free year**. Creating an installation does not activate access or create a trial. Catalog routes remain public delivery endpoints; the app gates reading on a verified RevenueCat entitlement or an active backend grant.

Before enabling the access API, configure PostgreSQL, run `mix ecto.migrate`, and provide `GA_ACCESS_ENCRYPTION_KEY` as Base64 encoding of exactly 32 cryptographically random bytes. Generate a value with `openssl rand -base64 32` and put it in the server's secret manager. It is independent of `SECRET_KEY_BASE`. Keep a secure backup; changing it without re-encrypting retained text makes old messages unreadable. Never commit keys, put credentials in URLs, or capture access request/response bodies in proxy, analytics, or error-reporting logs.

Access routes return `503 {"error":"access_unavailable"}` when `GA_SKIP_REPO=1`, the repository is disabled/unavailable, or the encryption key is missing. Existing catalog and health routes are unaffected. A malformed configured key prevents startup without printing its value. Access responses use `Cache-Control: no-store`; confidential parameters are filtered and access-route request logging is disabled. Production must terminate TLS before these endpoints.

An access-only JSON parser catches malformed-body errors without logging decoder input snippets and bounds bodies to 64 KiB. Malformed JSON returns generic `400 invalid_json`; oversized bodies return `413 request_too_large`; unsupported body media return `415 json_required`.

### API

Bodies are JSON. Private routes require `Authorization: Bearer <access_token>`. The installation UUID is also the stable `revenuecat_app_user_id`; use it to configure RevenueCat. Errors contain only a machine-readable `error` string.

| Method and path | Body | Successful response |
| --- | --- | --- |
| `POST /api/access/installations` | `{}` | `201 {installation_id, access_token, recovery_code, revenuecat_app_user_id}` |
| `POST /api/access/recover` | `{installation_id, recovery_code}` | `200 {installation_id, access_token, revenuecat_app_user_id}`; new bearer revokes old bearer |
| `GET /api/access/status` | — | `200 {status, active, grant_kind, starts_at, expires_at, revenuecat_app_user_id}` |
| `POST /api/access/free-requests` | `{request_id: UUID, message: string}` | `201` on first processing, `200` on retry; same access-status shape |
| `POST /api/access/selections` | `{event_id: UUID, option: "annual" \| "supporter" \| "free"}` | `201 {status:"recorded"}`; event retry returns `200` |
| `GET /api/access/statistics` | — | Public `200 {window_days:90, total, options:{annual:{count,percentage},supporter:{count,percentage},free:{count,percentage}}}` |
| `POST /api/access/text-reports` | `{report_id: UUID, book_id, section_id, selected_text, platform, section_title?, selection_start?, selection_end?, message?, app_version?, app_build?}` | `201` new / `200` identical retry; `{status:"received", report_id}` |
| `DELETE /api/access/installation` | — | `204`; deletes installation credentials, grants, requests, selection events and text reports |

`status` is `granted` while active and `inactive` otherwise. **`active` is the authorization decision.** `grant_kind` is `null` before a grant and `free` afterwards. Dates are ISO 8601 UTC strings or `null`; an expired grant keeps its dates and returns `active:false`. Expiry is exact, with no grace period or conversion to payment. Status does not report paid RevenueCat access.

Generate one new UUID for each intentional selection/free request and reuse it for transport retries. The server locks an installation while granting and deduplicates request UUIDs per installation. Replaying an existing request never renews access again, even after message erasure. Selection UUIDs deduplicate within the retained 90-day event window; changing an option on the same retained UUID returns `409 event_conflict`. A click counts even when a purchase is cancelled. Free-request submissions are not selection clicks.

### Text correction reports

Authenticated installations can report a selected passage without free or paid access. The canonical app base URL is `https://fototausch.eu/rudolf-steiner-ga`; append `/api/access/text-reports`. No name or email is collected. `book_id` is the canonical lowercase GA ID (`ga-001`, including suffixes such as `ga-266-1`); `section_id` is nonblank and at most 200 Unicode scalars/800 UTF-8 bytes. `selected_text` preserves the exact selection, must contain non-whitespace text and is at most 8,000 Unicode scalars/32,000 UTF-8 bytes. Optional `message` is at most 2,000 scalars/8,000 bytes; optional `section_title` is at most 500 scalars/2,000 bytes. Optional `app_version`/`app_build` are strings of at most 50 scalars/100 bytes. `platform` is `ios` or `macos`. Optional selection offsets must occur together, use UTF-16 code units and satisfy `0 <= selection_start < selection_end <= 2147483647`.

Generate a new `report_id` UUID per intentional report and preserve both UUID and payload for retries. UUIDs deduplicate per installation; identical retries return `200`, while reusing a retained UUID with changed content returns `409 report_conflict`. Invalid payloads return generic `422 invalid_report`; authentication, rate-limit, parser and backend-unavailability errors follow the access API above. There is no report-reading HTTP endpoint. The entire payload (selected text, note, bibliographic location, offsets and app metadata) is encrypted using the existing AES-256-GCM key. Receipt metadata contains installation/report UUIDs, timestamps and a keyed HMAC fingerprint for retry conflict detection; no plaintext passage or note is stored. Do not capture this payload in app, proxy or error logs.

Report ciphertext is erased at 180 days on the hourly retention pass (within the next hour while running). Minimal receipts persist until installation deletion, so delayed retries do not restore erased text. `DELETE /api/access/installation` cascades through reports and receipts. The existing protected backups can retain erased contents for up to seven additional days, giving up to 187 days from receipt while jobs run. Run retention before serving restored backups and reapply known deletion requests.

Authorized operators can read retained reports through `GA.Access.TextReports.list_for_operator(limit, offset)` in a protected local/release context; limit is 1–100, default 100, offset defaults to 0. On production, use `sudo /usr/local/sbin/ga-text-reports-export 100 0`, installed from `deploy/ga-text-reports-export.sh`. It loads the protected runtime environment, starts a listener-free release evaluation and writes JSON to a root-private mode-0600 file under `/var/lib/ga-access-reports`; stdout contains only its path. Repeat with offsets 100, 200, etc. for additional batches. These exports contain confidential selected passages and notes: restrict access, never publish them or copy them to logs/tickets, and delete them after processing. The hourly `ga-text-reports-cleanup.timer` also deletes these processing copies once they are 23 hours old, keeping them for at most 24 hours while scheduled jobs run. Creation time is encoded in each filename; reading a copy does not extend its expiry. Existing older export filenames use their modification time. The cleanup helper reads no report contents and logs only aggregate deletion counts.

### Grant and restoration policy

Any trimmed, nonempty request of at most 5,000 Unicode characters and 20,000 UTF-8 bytes is immediately granted in the same database transaction as confidential storage. There is no income check or manual approval. Missing/empty text returns `422 empty_message`; oversized text returns `422 message_too_long`; malformed UUIDs return `422 invalid_id`. Any wording is accepted.

The first grant starts at server UTC time and ends twelve calendar months later; February 29 becomes February 28, preserving the time of day. A new request is always possible. For an active grant, its original start remains and expiry becomes `max(existing expiry, now + twelve calendar months)`. Multiple requests do not stack extra years. For an expired grant, a new request starts the period again.

Bearer and recovery secrets contain 256 random bits and use Base64URL without padding. Only SHA-256 hashes are stored. Keep both in Keychain. Present a backup code as `installation_id.recovery_code`, splitting it into the API fields for recovery. The recovery secret stays reusable and is never read back from the server. Anyone holding it can restore that installation and revoke the previous bearer. Invalid recovery codes and nonexistent IDs both return `401 unauthorized`. Loss of both Keychain identity and backup code cannot be repaired through a name/email; neither is collected. A new installation is a new anonymous identity; no cross-device person identification or reinstall-abuse detection is promised.

Deletion removes the free identity and recovery capability. It does not cancel an App Store subscription or erase Apple's/RevenueCat's transaction data. Subscription management belongs to the App Store flow. A deleted free installation cannot be restored.

### Privacy and operations

Messages use AES-256-GCM with a fresh 96-bit random nonce and authentication tag. Schema inspection redacts ciphertext and credential hashes. There is no HTTP message-reading endpoint. Restrict administrative database/key access to authorized processing services/operators. Public statistics expose only aggregates, including zero counts; demonstration figures are never substituted.

`GA.Access.Retention` runs one minute after startup and then hourly. It erases ciphertext after 30 days and records `message_deleted_at`; erasure occurs within the next hourly pass while the service is running. Minimal request IDs, receipt times, granted status and grant dates remain until installation deletion so delayed retries are harmless. Selection events are deleted after 90 days. Installations hold only UUID, credential hashes, current free dates and timestamps. Installation deletion cascades through associated data, including text reports. Operators must erase expired data after restoring a backup; live deletion cannot retroactively remove stored backups. The deployed encrypted backup retains at most seven daily snapshots locally and prunes snapshots older than seven days during the daily pass. Messages can remain in protected backups for up to seven additional days after live erasure (up to 37 days from receipt while jobs run). No offsite backup is configured.

Run `mix ga.access.prune` for immediate erasure. Its output contains aggregate deletion counts only. Retention can delete expired ciphertext without an encryption key. The worker retries database failure without logging exception parameters. Monitor retention failures, database migrations, TLS and backup expiry before release.

The bounded in-memory rate limiter keeps at most 10,000 short-lived entries and persists no addresses. Limits: 20 installation creations/IP/hour; 10 recovery attempts/IP/minute; 10 free requests/installation/minute; 10 text reports/installation/minute; 120 selection events/installation/minute; 120 public-statistics reads/IP/minute. Blocked requests return `429 rate_limited` and `Retry-After`. Limits reset on process restart and apply per node; a multi-node deployment needs shared edge limiting.

Behind a reverse proxy, set `GA_ACCESS_TRUSTED_PROXY_IPS` to its comma-separated exact addresses (for example `127.0.0.1,::1`) and have it **replace** `X-Real-IP` with the remote address. Untrusted forwarding headers are ignored. Restrict the Phoenix port to proxy access. Do not record bodies or Authorization headers at the proxy. Without proper proxy trust, all users may share one IP rate-limit bucket.

The database-backed tests cover expiry boundaries, leap days, retries/renewals, hashed credentials/recovery, encryption integrity, deletion/retention, statistics, authentication, confidential logging, rate limiting and backend unavailability. Use a disposable partition, for example `MIX_TEST_PARTITION=_access_20261009 mix test`. Running tests with `GA_SKIP_REPO=1` deliberately skips persistent-access checks.

The access backend was deployed and verified on 9 October 2026 at the canonical app base URL `https://fototausch.eu/rudolf-steiner-ga`; API paths append `/api/access/...`. The previous `https://fototausch.eu/ga-access` base remains a compatibility alias for existing builds. It uses an isolated `ga-access` systemd service/user and `ga_access` Postgres database, bound to `127.0.0.1:4131`. Runtime secrets were generated on the server into a root-owned mode-0600 environment file. RevenueCat/App Store Connect products and Apple's introductory offer are configured separately.

`deploy/ga-access.nginx.conf`, `deploy/ga-access.service` and `deploy/ga-access.environment.example` document the deployed proxy/service layout. For subsequent releases, build on Linux, keep existing secrets/data, migrate before activating the new release, and validate nginx/HTTPS health. From a readable release working directory, run migrations through `bin/ga_server eval 'Ecto.Migrator.with_repo(GA.Repo, fn repo -> Ecto.Migrator.run(repo, :up, all: true) end)'` with the protected runtime environment loaded. See `deploy/deployment-20261009.md` for the initial deployment and `deploy/deployment-20261011-text-reports.md` for the current text-report release, validation and rollback.

`deploy/ga-access-backup.sh` and its service/timer create an AES-256-CBC/PBKDF2 encrypted database/environment archive with a separate HMAC-SHA-256 integrity tag. Archives/directories are root-private; the independent encryption/MAC passphrase is `/etc/ga-access/backup-key`, mode 0600, and is not included in an archive. Preserve this key separately when copying archives elsewhere. The runtime environment inside the encrypted archive preserves the message-encryption key needed after restoration. Verify HMAC before decrypting/extracting and run retention after restoring. The deployed backup passed a real scratch-database restoration test. The separate backup key and archives are currently on the same host; complete host/disk loss needs an independently secured copy.

For isolated local UI verification, use `GA_DEV_DATABASE=ga_access_ui_20261009` for `mix ecto.create`/`mix ecto.migrate`, then start with that same variable, `GA_DEV_PORT=4181`, and a freshly generated `GA_ACCESS_ENCRYPTION_KEY`. These development overrides do not affect the existing default development or test databases. The local app base URL is `http://127.0.0.1:4181`.

To start your Phoenix server:

  * Run `mix setup` to install and setup dependencies
  * Start Phoenix endpoint with `mix phx.server` or inside IEx with `iex -S mix phx.server`

Now you can visit [`localhost:4000`](http://localhost:4000) from your browser.

Ready to run in production? Please [check our deployment guides](https://hexdocs.pm/phoenix/deployment.html).

## Learn more

  * Official website: https://www.phoenixframework.org/
  * Guides: https://hexdocs.pm/phoenix/overview.html
  * Docs: https://hexdocs.pm/phoenix
  * Forum: https://elixirforum.com/c/phoenix-forum
  * Source: https://github.com/phoenixframework/phoenix
