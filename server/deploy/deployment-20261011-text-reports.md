# GA text correction reports — 11 October 2026

The GA access backend now receives confidential selected-passage corrections at
`POST https://fototausch.eu/rudolf-steiner-ga/api/access/text-reports`.
The existing anonymous installation bearer authenticates a report; a free grant,
paid entitlement, name or email is not required. The API contract and limits are
in [server README](../README.md#text-correction-reports).

## Production release

- Linux-built release: `/opt/ga-access/releases/20261011-text-reports`.
  `/opt/ga-access/current` points to it; the prior `20261009-02` is retained.
- Linux source/build directory: `/opt/ga-access/build-20261011-text-reports`.
  Dependencies were resolved without changing pinned `mix.lock`; compilation
  passed with warnings treated as errors.
- Additive migration `20261011000000_create_text_reports.exs` created the isolated
  `access_text_reports` table and indexes in the existing `ga_access` database.
- A successful protected GA backup was made immediately before migration.
  Existing environment secrets were preserved byte-for-byte. The existing GA
  Erlang cookie was preserved and protected in the new release.
- The existing access proxy already exposes the new report route. An exact
  `/rudolf-steiner-ga/api/health` proxy to `127.0.0.1:4131/api/health` was added:
  this previously absent route had fallen through to the unrelated main service.
  No other GA access route changed. nginx validation passed before reload.
- `ga-access`, `ga-library`, nginx and all eleven author services were active after
  verification. Authors still use the unchanged `20261009-02` release; their
  aggregate nginx include remained byte-identical. Existing reader catalog
  `https://fototausch.eu/ga-reader/catalog.json` returned HTTP 200.
- Private baseline/rollback records are under
  `/var/lib/ga-textreports-deployment-20261011` on the host. Runtime secrets and
  backups remain in their existing protected locations.

## Confidentiality and retention

Selected text, optional note, book/section IDs and title, UTF-16 selection offsets,
platform and app version/build are stored together as AES-256-GCM ciphertext.
No plaintext report contents are stored in database columns. The installation and
report UUIDs, receipt/deletion timestamps and a keyed HMAC fingerprint are retained
for retry/conflict handling. Schema inspection redacts ciphertext and fingerprint;
request/route logging remains disabled for access endpoints. Debug-log regression
checks and production service-journal checks found no test passages or notes.

The hourly retention pass erases the whole report payload at 180 days; while the
service runs, erasure occurs within the next hourly pass. Minimal receipts remain
until installation deletion, so delayed retries cannot restore erased contents.
Installation deletion cascades through reports. Existing protected backups can
retain erased contents for up to seven additional days (up to 187 days from report
receipt while scheduled jobs run). Restoration must run retention before serving
and reapply known deletion requests.

There is no public or authenticated HTTP report-reading endpoint. Authorized
operators use `sudo /usr/local/sbin/ga-text-reports-export [limit] [offset]`, installed
from [export script](ga-text-reports-export.sh). It exports up to 100 decrypted
reports to a root-private mode-0600 JSON file under `/var/lib/ga-access-reports` and
prints only that path. Exports are short-lived processing copies and must be deleted
after processing. The hourly `ga-text-reports-cleanup.timer` deletes copies at age
23 hours, keeping them for at most 24 hours while scheduled jobs run. Creation time
is encoded in new filenames and is unaffected by reading the file; older filenames
use modification time. The root-only helper reads no contents and logs only aggregate
deletion counts. Its service creates/preserves the root-private mode-0700 directory
and runs independently of the access database or encryption key. The context supports paging with
`GA.Access.TextReports.list_for_operator(limit, offset)`.

The canonical public privacy and support pages were updated from
`docs/app-store/web/privacy.html` and `support.html`. Both returned HTTP 200 and
matched the repository contents byte-for-byte after publication. The privacy page
explains explicit report submission, data fields, 180-day erasure, installation
deletion and backup expiry.

## Verification

34 local focused tests passed, covering the existing access API and the new report
context/controller: encryption and authorized decryption, independent installation
UUID scopes, identical retry/changed-content conflict, scalar/byte limits and UTF-16
offset pairs, authentication without a paid grant, generic validation errors, 180-day
retention boundary and unchanged retry receipts, cascading deletion, confidential
debug logging, rate limits, JSON/media/body limits and backend-unavailability.

Public HTTPS verification covered:

- Initially inactive anonymous installation and successful authenticated report.
- HTTP 201 first receipt, HTTP 200 identical sequential and three concurrent retries,
  HTTP 409 changed content under the same UUID, and `Cache-Control: no-store`.
- HTTP 401 missing bearer, HTTP 422 invalid report, HTTP 400 malformed JSON,
  HTTP 415 non-JSON body, and HTTP 429 after ten report attempts per minute.
- Database ciphertext containing neither the test selection nor note in plaintext,
  and authorized operator decryption reproducing the exact submitted payload.
- No test selection, note, title or malformed body marker in the service journal.
- HTTP 204 installation deletion, subsequent HTTP 401 bearer rejection and confirmed
  absence of the QA installation and associated report in the database.
- Protected operator-export JSON format, root-only file permissions and deletion of
  the temporary export. Temporary QA credentials/expectations were removed.
- Canonical health endpoint HTTP 200 after the nginx reload completed.
- Operator cleanup tested around the 23-hour boundary, including reading and altered
  file timestamps, legacy filenames, symlink/unrelated-file preservation, and root-only
  permissions. The hourly persistent cleanup timer was installed and its service ran
  successfully without reading or logging report contents.

## Rollback

The new table is additive and does not affect the previous release. To roll back
application code, point `/opt/ga-access/current` to `20261009-02` and restart only
`ga-access`. The previous code will not accept reports or prune the new ciphertext;
retain a functioning report retention job or erase expired report payloads before
leaving that code active long-term. Preserve database data, runtime keys and backups.
Remove only the exact health block if withdrawing its proxy, then validate/reload
nginx. Existing author deployments and other services need no change.
