#!/usr/bin/env python3
"""Reproduce all 20 early unavailable-row recovery records.

Run with a Python runtime that has lxml installed. Poppler pdftotext must be on
PATH. Existing preserved sources are reused, and the current catalog is read
only for titles and prior warnings. Run this wrapper instead of individual
stages when creating the complete research manifest from an empty checkout.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

for script in ['download_early_support.py', 'recover_early.py', 'finalize_early_recovery.py', 'verify_early_recovery.py']:
    subprocess.run([sys.executable, str(ROOT / 'tools' / script)], cwd=ROOT, check=True)
