#!/usr/bin/env bash
set -euo pipefail
umask 0077

# Dedicated service data only. No secrets or SQL contents are written to stdout.
backup_root=/var/backups/ga-access
backup_name=$(date -u +%Y%m%dT%H%M%SZ)
backup_path="$backup_root/$backup_name"
install -d -m 0700 "$backup_root"
mkdir -m 0700 "$backup_path"
trap 'rm -rf -- "$backup_path"' ERR
runuser -u postgres -- pg_dump --format=custom ga_access > "$backup_path/database.dump"
install -m 0600 /etc/ga-access/environment "$backup_path/environment"
pg_restore --list "$backup_path/database.dump" > /dev/null
tar -cf "$backup_path/contents.tar" -C "$backup_path" database.dump environment
openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 \
  -pass file:/etc/ga-access/backup-key \
  -in "$backup_path/contents.tar" -out "$backup_path/backup.tar.enc"
python3 - "$backup_path" <<'PY'
from pathlib import Path
import hashlib, hmac, sys
path = Path(sys.argv[1])
key = Path('/etc/ga-access/backup-key').read_bytes().strip()
tag = hmac.new(key, b'ga-access-backup-v1:' + (path / 'backup.tar.enc').read_bytes(), hashlib.sha256).hexdigest()
(path / 'backup.tar.enc.hmac').write_text(tag + '\n')
PY
rm -- "$backup_path/database.dump" "$backup_path/environment" "$backup_path/contents.tar"

# Keep at most seven daily snapshots; prune older than seven days as well.
python3 - "$backup_root" <<'PY'
from pathlib import Path
import re, shutil, sys, time
root = Path(sys.argv[1])
entries = sorted((p for p in root.iterdir() if p.is_dir() and not p.is_symlink()
                  and re.fullmatch(r"\d{8}T\d{6}Z", p.name)), reverse=True)
cutoff = time.time() - 7 * 86400
for index, path in enumerate(entries):
    if index >= 7 or path.stat().st_mtime <= cutoff:
        shutil.rmtree(path)
PY
printf 'GA access backup completed; seven daily snapshots retained locally.\n'
