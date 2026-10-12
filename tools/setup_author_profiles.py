#!/usr/bin/env python3
"""Create author-only App Store profiles with an existing local signing identity.

Default is read-only. --apply creates missing profiles, downloads and installs
only verified author profiles. No certificates, keys, devices or GA resources
are created or modified. ASC_KEY_ID/ASC_KEY_PATH/ASC_ISSUER_ID provide Apple auth.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import plistlib
import re
import subprocess
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import NameOID

from setup_author_cloudkit import checked_authors

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'docs/app-store/publishing'))
from asc_client import ASCClient, APIError, relation

TEAM = 'ER7U6R25KM'
PROFILE_TYPES = {'ios': 'IOS_APP_STORE', 'macos': 'MAC_APP_STORE'}


def existing_distribution_certificate(client):
    identities = subprocess.run(['security', 'find-identity', '-v', '-p', 'codesigning'],
                                capture_output=True, text=True, check=True).stdout
    valid = set(re.findall(r'\b([A-Fa-f0-9]{40})\b', identities))
    candidates = []
    for resource in client.rows('/v1/certificates', {'limit': 200}):
        attributes = resource['attributes']
        if attributes.get('certificateType') != 'DISTRIBUTION':
            continue
        certificate = x509.load_der_x509_certificate(base64.b64decode(attributes['certificateContent']))
        teams = [value.value for value in certificate.subject.get_attributes_for_oid(NameOID.ORGANIZATIONAL_UNIT_NAME)]
        fingerprint = certificate.fingerprint(hashes.SHA1()).hex().upper()
        if TEAM in teams and fingerprint in valid and certificate.not_valid_after_utc > datetime.now(timezone.utc):
            candidates.append((resource, fingerprint))
    if len(candidates) != 1:
        raise RuntimeError('Expected exactly one existing usable team Apple Distribution certificate; refusing certificate creation')
    return candidates[0]


def decoded_profile(content):
    result = subprocess.run(['security', 'cms', '-D'], input=content, capture_output=True, check=True)
    return plistlib.loads(result.stdout)


def verify_profile(profile, author, fingerprint):
    entitlements = profile['Entitlements']
    identifier = entitlements.get('application-identifier', entitlements.get('com.apple.application-identifier'))
    services = entitlements.get('com.apple.developer.icloud-services', [])
    environments = entitlements.get('com.apple.developer.icloud-container-environment', [])
    if isinstance(environments, str):
        environments = [environments]
    fingerprints = [x509.load_der_x509_certificate(data).fingerprint(hashes.SHA1()).hex().upper()
                    for data in profile.get('DeveloperCertificates', [])]
    checks = {
        'team': profile.get('TeamIdentifier') == [TEAM],
        'appIdentifier': identifier == TEAM + '.' + author['bundle_id'],
        'containerOnlyOwnAuthor': entitlements.get('com.apple.developer.icloud-container-identifiers') == [author['cloudkit_container']],
        'cloudKitAllowed': 'CloudKit' in services or '*' in services,
        'productionAllowed': 'Production' in environments,
        'existingDistributionCertificate': fingerprint in fingerprints,
        'notExpired': profile['ExpirationDate'].replace(tzinfo=timezone.utc) > datetime.now(timezone.utc),
        'storeProfileWithoutDevices': not profile.get('ProvisionedDevices'),
    }
    if not all(checks.values()):
        failed = ','.join(name for name, passed in checks.items() if not passed)
        raise RuntimeError('Profile isolation/signing verification failed: ' + failed)
    return checks


def author_profiles(author, client, certificate, fingerprint, apply, output):
    bundles = client.rows('/v1/bundleIds', {'filter[identifier]': author['bundle_id'], 'limit': 200})
    if len(bundles) != 1:
        return {'slug': author['slug'], 'status': 'bundle_registration_missing_or_ambiguous'}
    bundle = bundles[0]
    existing = client.rows('/v1/bundleIds/' + bundle['id'] + '/profiles', {'limit': 200})
    reports = []
    for platform, profile_type in PROFILE_TYPES.items():
        resources = [p for p in existing if p['attributes'].get('profileType') == profile_type
                     and p['attributes'].get('profileState') == 'ACTIVE']
        profile_resource = None
        profile = None
        for resource in resources:
            try:
                decoded = decoded_profile(base64.b64decode(resource['attributes']['profileContent']))
                verify_profile(decoded, author, fingerprint)
            except (ValueError, KeyError, RuntimeError, subprocess.CalledProcessError):
                continue
            profile_resource, profile = resource, decoded
            break
        created = False
        if profile_resource is None and apply:
            profile_resource = client.write('POST', 'profiles', {
                'name': 'Author ' + author['author_short_name'] + ' ' + platform + ' App Store',
                'profileType': profile_type,
            }, {'bundleId': relation('bundleIds', bundle['id']),
                'certificates': {'data': [{'type': 'certificates', 'id': certificate['id']}]}})
            profile = decoded_profile(base64.b64decode(profile_resource['attributes']['profileContent']))
            created = True
        if profile_resource is None:
            reports.append({'platform': platform, 'profileType': profile_type, 'status': 'profile_missing'})
            continue
        checks = verify_profile(profile, author, fingerprint)
        extension = '.mobileprovision' if platform == 'ios' else '.provisionprofile'
        filename = profile['UUID'] + extension
        downloaded = output / author['slug'] / filename
        installed = Path.home() / 'Library/Developer/Xcode/UserData/Provisioning Profiles' / filename
        if apply:
            content = base64.b64decode(profile_resource['attributes']['profileContent'])
            downloaded.parent.mkdir(parents=True, exist_ok=True)
            downloaded.write_bytes(content)
            installed.parent.mkdir(parents=True, exist_ok=True)
            if installed.exists() and installed.read_bytes() != content:
                raise RuntimeError('Refusing to overwrite a different installed provisioning profile')
            installed.write_bytes(content)
            export_options = ROOT / 'editions' / author['slug'] / 'cloudkit' / ('export-options-' + platform + '.plist')
            export_options.parent.mkdir(parents=True, exist_ok=True)
            export_options.write_bytes(plistlib.dumps({
                'method': 'app-store-connect', 'destination': 'export',
                'teamID': TEAM, 'signingStyle': 'manual', 'signingCertificate': fingerprint,
                'cloudKitEnvironment': 'Production', 'manageAppVersionAndBuildNumber': False,
                'provisioningProfiles': {author['bundle_id']: profile['UUID']},
            }, sort_keys=False))
        reports.append({'platform': platform, 'profileType': profile_type,
                        'status': 'verified_installed' if apply else 'verified', 'created': created,
                        'profileId': profile_resource['id'], 'uuid': profile['UUID'], 'name': profile['Name'],
                        'expiresAt': profile['ExpirationDate'].isoformat(), 'checks': checks,
                        'downloadedProfile': str(downloaded) if apply else None,
                        'installedProfile': str(installed) if apply else None})
    return {'slug': author['slug'], 'bundleId': author['bundle_id'], 'containerId': author['cloudkit_container'],
            'status': 'verified' if all(r['status'].startswith('verified') for r in reports) else 'profiles_missing',
            'profiles': reports}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--author', action='append')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('/tmp/author-provisioning-profiles'))
    args = parser.parse_args()
    authors = checked_authors(json.loads((ROOT / 'editions/authors.json').read_text()), args.author)
    client = ASCClient(allow_writes=args.apply)
    certificate, fingerprint = existing_distribution_certificate(client)
    reports = []
    for author in authors:
        try:
            result = author_profiles(author, client, certificate, fingerprint, args.apply, args.output)
        except APIError as error:
            result = {'slug': author['slug'], 'status': 'apple_profile_request_failed', 'httpStatus': error.status}
        except (RuntimeError, ValueError, KeyError, subprocess.CalledProcessError):
            result = {'slug': author['slug'], 'status': 'profile_verification_failed'}
        reports.append(result)
        print(author['slug'] + ': ' + result['status'], flush=True)
    report = {'checkedAt': datetime.now(timezone.utc).isoformat(), 'teamId': TEAM,
              'existingDistributionCertificateId': certificate['id'], 'createdKeysOrCertificates': False,
              'apply': args.apply, 'authors': reports}
    (ROOT / 'editions/cloudkit/app-store-profile-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    if any(r['status'] != 'verified' for r in reports):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
