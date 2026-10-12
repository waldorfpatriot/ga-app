#!/usr/bin/env python3
"""Read-only provenance and German extraction checks for early recovery."""
from pathlib import Path
import hashlib
import json
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'tools/recovery-early.json'
report = json.loads(REPORT.read_text())
errors = []
checked = 0
pairs = [('local_path', 'sha256'), ('original_path', 'original_sha256'),
         ('text_path', 'text_sha256'), ('index_path', 'index_sha256'),
         ('metadata_path', 'metadata_sha256'), ('combined_text_path', 'combined_text_sha256'),
         ('reader_candidate_path', 'reader_candidate_sha256'), ('local_original_path', 'original_sha256')]


def audit(value):
    global checked
    if isinstance(value, dict):
        for path_key, hash_key in pairs:
            if path_key in value and hash_key in value:
                path = ROOT / value[path_key]
                if not path.exists():
                    errors.append('Missing source: ' + str(path))
                elif hashlib.sha256(path.read_bytes()).hexdigest() != value[hash_key]:
                    errors.append('Hash mismatch: ' + str(path))
                else:
                    checked += 1
        for item in value.values():
            audit(item)
    elif isinstance(value, list):
        for item in value:
            audit(item)


audit(report)
if len(report['works']) != 20:
    errors.append('Expected all 20 assigned catalog rows')
automatic_pages = 0
for work in report['works']:
    if not work.get('chapters'):
        continue
    candidate = json.loads((ROOT / work['reader_candidate_path']).read_text())
    for passage in candidate['passages']:
        if passage['text'] != passage['source_text'] or hashlib.sha256(passage['text'].encode()).hexdigest() != passage['checksum']:
            errors.append('Candidate text/checksum mismatch: ' + passage['id'])
    for chapter in work['chapters'] + work.get('related_chapters', []):
        if not chapter.get('text_path'):
            continue
        source = html.fromstring((ROOT / chapter['original_path']).read_bytes())
        normalized = ' '.join((ROOT / chapter['text_path']).read_text().split())
        for node in source.xpath('//*[@id="autoTranslation"]'):
            automatic_pages += 1
            chunk = ' '.join(node.text_content().split())[:150]
            if len(chunk) > 40 and chunk in normalized:
                errors.append('Automatic English translation retained: ' + chapter['text_path'])
result = {'hashes_checked': checked, 'nested_automatic_translation_pages_audited': automatic_pages,
          'work_rows': len(report['works']), 'errors': errors, 'summary': report['summary']}
target = ROOT / 'research/unavailable-recovery/early/verification.json'
target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False))
if errors:
    raise SystemExit(1)
