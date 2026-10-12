#!/usr/bin/env python3
"""Verify public RevenueCat offerings and configure isolated author SDK keys.

--apply writes only ignored editions/<slug>/apple/Purchases.local.xcconfig.
No secret API keys, customer-info endpoints, real customer identifiers, receipts
or provider settings are used. GA's public configuration is read only to protect
its existing key; GA files are never changed. The setup-state file is maintained
from authorized UI setup.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from setup_author_cloudkit import checked_authors

ROOT = Path(__file__).resolve().parents[1]
API_ORIGIN = 'https://api.revenuecat.com'
GA_PROJECT = '34fd17d0'


class RevenueCatRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        parsed = urllib.parse.urlparse(new_url)
        if parsed.scheme != 'https' or parsed.netloc != 'api.revenuecat.com':
            raise RuntimeError('Refusing RevenueCat credential redirect to a different origin')
        return super().redirect_request(request, fp, code, message, headers, new_url)


def offering_products(response):
    current = response.get('current_offering_id')
    offerings = response.get('offerings', [])
    selected = [o for o in offerings if o.get('identifier') == current]
    if len(selected) != 1 or current != 'default':
        raise ValueError('Expected one current default offering')
    packages = selected[0].get('packages', [])
    products = [p.get('platform_product_identifier') for p in packages]
    if len(products) != 2 or len(set(products)) != 2 or not all(isinstance(p, str) for p in products):
        raise ValueError('Expected exactly two different store products in default offering')
    return current, sorted(products)


def public_offering(author, key):
    user_id = 'author-configuration-readback-' + author['slug']
    url = API_ORIGIN + '/v1/subscribers/' + urllib.parse.quote(user_id, safe='') + '/offerings'
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + key,
                                                 'X-Platform': 'ios', 'Accept': 'application/json'}, method='GET')
    opener = urllib.request.build_opener(RevenueCatRedirects())
    with opener.open(request, timeout=30) as response:
        data = json.loads(response.read())
    current, products = offering_products(data)
    expected = sorted(author['bundle_id'] + '.' + option for option in ('annual', 'supporter'))
    if products != expected:
        raise ValueError('Default offering products differ from this author bundle')
    return {'status': 'verified', 'currentOffering': current, 'productIds': products,
            'entitlementIdentifier': author['entitlement_id'],
            'entitlementMappingEvidence': 'authorized management setup report; public offerings API does not expose linkage',
            'customerInfoEndpointRequested': False, 'realCustomerIdentifierUsed': False,
            'receiptsSubmitted': False, 'appleStorePriceOrPurchaseVerified': False}


def checked_records(authors, rows):
    author_map = {a['slug']: a for a in authors}
    ga_config = (ROOT / 'apple/GA/Purchases.xcconfig').read_text()
    ga_keys = set(re.findall(r'appl_[A-Za-z0-9]+', ga_config))
    seen_slugs, seen_projects, seen_keys = set(), set(), set()
    configured = {}
    for row in rows:
        slug = row.get('slug')
        key = row.get('publicKey', '')
        project = row.get('projectId')
        if slug not in author_map or slug in seen_slugs:
            raise ValueError('Unknown or duplicate RevenueCat author')
        seen_slugs.add(slug)
        if project:
            if project == GA_PROJECT or project in seen_projects:
                raise ValueError('An independent RevenueCat project is required per author')
            seen_projects.add(project)
        if not key:
            continue  # The master report is updated incrementally during UI setup.
        if not re.fullmatch(r'appl_[A-Za-z0-9]+', key) or key in ga_keys or key in seen_keys:
            raise ValueError('Invalid, protected or reused author public SDK key')
        seen_keys.add(key)
        if not project or not row.get('appId'):
            continue
        if row.get('entitlement') != author_map[slug]['entitlement_id'] or row.get('offering') != 'default':
            continue
        if not row.get('productsImported'):
            continue
        configured[slug] = row
    return configured


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--author', action='append')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--require-all', action='store_true', help='Fail until all selected author projects are configured.')
    args = parser.parse_args()
    all_authors = checked_authors(json.loads((ROOT / 'editions/authors.json').read_text()), None)
    selected = checked_authors(json.loads((ROOT / 'editions/authors.json').read_text()), args.author)
    rows = checked_records(all_authors, json.loads((ROOT / 'editions/revenuecat-setup-state.json').read_text()))
    reports = []
    for author in selected:
        row = rows.get(author['slug'])
        if not row:
            reports.append({'slug': author['slug'], 'status': 'management_setup_pending'})
            continue
        try:
            report = dict(public_offering(author, row['publicKey']), slug=author['slug'],
                          projectId=row['projectId'], appId=row['appId'])
            destination = ROOT / 'editions' / author['slug'] / 'apple/Purchases.local.xcconfig'
            ignored = subprocess.run(['git', 'check-ignore', '-q', str(destination)], cwd=ROOT).returncode == 0
            if not ignored:
                raise ValueError('Author public SDK configuration must use the ignored local file')
            if args.apply:
                destination.write_text('// Public Apple SDK key for this author app only.\nGA_REVENUECAT_IOS_SDK_KEY = ' + row['publicKey'] + '\n')
            report['localConfigurationWritten'] = args.apply
            report['localConfigurationIgnored'] = True
        except urllib.error.HTTPError as error:
            report = {'slug': author['slug'], 'status': 'public_offering_request_failed', 'httpStatus': error.code}
        except (ValueError, RuntimeError, OSError, urllib.error.URLError):
            report = {'slug': author['slug'], 'status': 'offering_or_configuration_verification_failed'}
        reports.append(report)
        print(author['slug'] + ': ' + report['status'], flush=True)
    report = {'checkedAt': datetime.now(timezone.utc).isoformat(), 'apply': args.apply,
              'configuredAuthorCount': len(rows), 'verifiedAuthorCount': sum(r['status'] == 'verified' for r in reports),
              'allSelectedVerified': all(r['status'] == 'verified' for r in reports), 'authors': reports}
    (ROOT / 'editions/revenuecat-public-verification.json').write_text(json.dumps(report, indent=2) + '\n')
    failed = any(r['status'] != 'verified' and (r['status'] != 'management_setup_pending' or args.require_all) for r in reports)
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
