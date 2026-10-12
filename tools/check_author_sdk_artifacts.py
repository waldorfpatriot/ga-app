#!/usr/bin/env python3
"""Read author app Info.plists and verify their public RevenueCat configuration.

Defaults to the app paths in editions/build-verification.json. Additional
distribution apps can be supplied using --artifact SLUG PLATFORM APP_PATH.
Public SDK key values are compared in memory and never included in output.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import plistlib

from configure_author_revenuecat import ROOT, checked_records
from setup_author_cloudkit import checked_authors


def inspect_artifact(author, row, platform, app):
    if platform not in {'ios', 'macos'}:
        raise ValueError('Expected ios or macos author artifact')
    result = {'slug': author['slug'], 'platform': platform, 'app': str(app)}
    if not row:
        return dict(result, status='management_setup_pending', verified=False)
    info_path = app / 'Contents/Info.plist' if platform == 'macos' else app / 'Info.plist'
    try:
        info = plistlib.loads(info_path.read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException):
        return dict(result, status='artifact_info_unavailable', verified=False)
    checks = {
        'authorBundleIdentifier': info.get('CFBundleIdentifier') == author['bundle_id'],
        'authorSlug': info.get('GAAuthorSlug') == author['slug'],
        'authorProductIdentifierPrefix': info.get('GAProductIDPrefix') == author['bundle_id'],
        'authorCloudKitContainer': info.get('GACloudKitContainerIdentifier') == author['cloudkit_container'],
        'authorPublicSDKKey': info.get('GARevenueCatPublicSDKKey') == row['publicKey'],
    }
    verified = all(checks.values())
    return dict(result, status='verified' if verified else 'artifact_configuration_mismatch',
                verified=verified, checks=checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', nargs=3, action='append', metavar=('SLUG', 'PLATFORM', 'APP_PATH'))
    parser.add_argument('--allow-incomplete', action='store_true')
    args = parser.parse_args()
    authors = checked_authors(json.loads((ROOT / 'editions/authors.json').read_text()), None)
    author_map = {a['slug']: a for a in authors}
    rows = checked_records(authors, json.loads((ROOT / 'editions/revenuecat-setup-state.json').read_text()))
    if args.artifact:
        entries = [{'slug': slug, 'platform': platform, 'app': path} for slug, platform, path in args.artifact]
    else:
        entries = json.loads((ROOT / 'editions/build-verification.json').read_text())['builds']
    seen = set()
    reports = []
    for entry in entries:
        slug, platform = entry['slug'], entry['platform']
        if slug not in author_map or (slug, platform) in seen:
            parser.error('Unknown or duplicate author artifact')
        seen.add((slug, platform))
        report = inspect_artifact(author_map[slug], rows.get(slug), platform, Path(entry['app']))
        reports.append(report)
        print(slug + ' ' + platform + ': ' + report['status'])
    expected = {(a['slug'], p) for a in authors for p in ('ios', 'macos')}
    all_verified = bool(reports) and all(r['verified'] for r in reports)
    report = {'checkedAt': datetime.now(timezone.utc).isoformat(), 'publicKeyValuesIncluded': False,
              'originalGAIncluded': False, 'verifiedArtifactCount': sum(r['verified'] for r in reports),
              'artifactCount': len(reports), 'allArtifactsVerified': all_verified,
              'all22AuthorPlatformsCovered': seen == expected, 'artifacts': reports}
    (ROOT / 'editions/revenuecat-artifact-verification.json').write_text(json.dumps(report, indent=2) + '\n')
    if not args.allow_incomplete and (not all_verified or (not args.artifact and seen != expected)):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
