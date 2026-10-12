#!/usr/bin/env python3
"""Verify author Production schema exports and profile evidence without Apple auth."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from setup_author_cloudkit import checked_authors, mask_comments, reading_type, schema_status

ROOT = Path(__file__).resolve().parents[1]


def production_checks(schema):
    bounds, _, _ = reading_type(schema)
    body = mask_comments(schema[bounds[0]:bounds[1]]) if bounds else ''
    grants = re.findall(r'\bGRANT\s+(.*?)\s+TO\s+"([^\"]+)"', body, re.S)
    permissions = {p.strip() for permission, _ in grants for p in permission.split(',')}
    users = re.search(r'\bRECORD\s+TYPE\s+(?:Users|"Users")\s*\((.*?)\)\s*;', mask_comments(schema), re.S)
    return {
        'requiredReadingStateFields': schema_status(schema)['ready'],
        'readingStatePublicPermissionsCreatorOnly': bool(grants) and all(role == '_creator' for _, role in grants),
        'readingStatePublicPermissionsReadWriteOnly': permissions == {'READ', 'WRITE'},
        'existingUsersTypeRetained': users is not None and bool(re.search(r'\broles\s+LIST\s*<\s*INT64\s*>', users.group(1))),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-incomplete', action='store_true', help='Report remaining Console work without failing.')
    args = parser.parse_args()
    authors = checked_authors(json.loads((ROOT / 'editions/authors.json').read_text()), None)
    completed = set(json.loads((ROOT / 'editions/cloudkit-console-verification.json').read_text())['completed'])
    profiles = json.loads((ROOT / 'editions/cloudkit/app-store-profile-report.json').read_text())
    profile_authors = {a['slug']: a for a in profiles['authors']}
    results = []
    for author in authors:
        schema_file = ROOT / 'editions' / author['slug'] / 'cloudkit/production.ckdb'
        result = {'slug': author['slug'], 'containerId': author['cloudkit_container'],
                  'consoleProductionDeploymentRecorded': author['slug'] in completed,
                  'productionExportPresent': schema_file.is_file()}
        if schema_file.is_file():
            data = schema_file.read_bytes()
            result['productionSchemaSHA256'] = hashlib.sha256(data).hexdigest()
            result['checks'] = production_checks(data.decode())
        entry = profile_authors.get(author['slug'], {})
        result['bothStoreProfilesVerified'] = (entry.get('bundleId') == author['bundle_id']
            and entry.get('containerId') == author['cloudkit_container'] and entry.get('status') == 'verified'
            and {p['profileType'] for p in entry.get('profiles', [])} == {'IOS_APP_STORE', 'MAC_APP_STORE'}
            and all(all(p['checks'].values()) for p in entry.get('profiles', [])))
        result['verified'] = (result['consoleProductionDeploymentRecorded'] and result['productionExportPresent']
                              and all(result.get('checks', {}).values()) and result['bothStoreProfilesVerified'])
        results.append(result)
    report = {'checkedAt': datetime.now(timezone.utc).isoformat(), 'teamId': 'ER7U6R25KM',
              'authorCount': len(authors), 'verifiedCount': sum(r['verified'] for r in results),
              'allVerified': all(r['verified'] for r in results), 'originalGAIncluded': False,
              'scope': 'Console Production schema exports and verified author profiles; no device sync claim',
              'authors': results}
    (ROOT / 'editions/cloudkit-readback-verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Verified author Production readbacks and Store profiles: ' + str(report['verifiedCount']) + '/' + str(len(authors)))
    if not args.allow_incomplete and not report['allVerified']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
