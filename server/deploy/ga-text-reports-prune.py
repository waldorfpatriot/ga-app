#!/usr/bin/python3
"""Erase aged operator processing copies without reading or logging contents."""
import json
import os
from pathlib import Path
import re
import stat
import time

EXPORT_DIRECTORY = Path("/var/lib/ga-access-reports")
# Hourly cleanup at age 23h keeps copies for at most 24h while jobs run.
EXPIRY_SECONDS = 23 * 60 * 60
TIMED_NAME = re.compile(r"reports-([0-9]{10,})-[A-Za-z0-9]{8}\.json\Z")
LEGACY_NAME = re.compile(r"reports-[A-Za-z0-9]{8}\.json\Z")


def prune_exports(directory, now, expected_uid=0):
    """Use encoded creation time; older exports fall back to modification time."""
    deleted = 0
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(directory_fd)
        if info.st_uid != expected_uid or stat.S_IMODE(info.st_mode) != 0o700:
            raise RuntimeError("Unsafe operator export directory")
        for name in os.listdir(directory_fd):
            timed = TIMED_NAME.fullmatch(name)
            if not timed and not LEGACY_NAME.fullmatch(name):
                continue
            try:
                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_uid != expected_uid:
                continue
            if stat.S_IMODE(info.st_mode) != 0o600:
                raise RuntimeError("Unsafe operator export permissions")
            created_at = int(timed[1]) if timed else info.st_mtime
            if now - created_at >= EXPIRY_SECONDS:
                try:
                    os.unlink(name, dir_fd=directory_fd)
                except FileNotFoundError:
                    continue
                deleted += 1
    finally:
        os.close(directory_fd)
    return {"exports_deleted": deleted}


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise SystemExit("Run as root on the GA access host.")
    try:
        print(json.dumps(prune_exports(EXPORT_DIRECTORY, time.time())))
    except (OSError, RuntimeError):
        raise SystemExit("Operator export cleanup unavailable; check directory and permissions")
