#!/usr/bin/env python3
"""Configure isolated author-app subscriptions using GA's verified Apple flow.

The default is read-only. --apply configures draft groups/products only, never
submits a review or publishes. Apple app records must exist before this command.
The API client requires ASC_KEY_ID and ASC_KEY_PATH from the caller's environment.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'docs/app-store/publishing'))
from asc_client import ASCClient, relation
from setup_products import draft_version, localize, price_point, setup_availability, setup_price, setup_intro, current_prices


def run(author, client, apply):
    apps = client.rows('/v1/apps', {'filter[bundleId]':author['bundle_id'], 'limit':200})
    if not apps:
        return {'slug':author['slug'],'bundleId':author['bundle_id'],'status':'app_record_missing',
                'nextStep':'Create one Apple app record with both iOS and macOS for this bundle ID.'}
    if len(apps)!=1:
        raise RuntimeError('Ambiguous Apple records for '+author['slug'])
    app=apps[0]
    group_name=author['author_short_name']+'-App-Zugang'
    groups=client.rows(f"/v1/apps/{app['id']}/subscriptionGroups", {'limit':200})
    if len(groups)>1 or (groups and groups[0]['attributes'].get('referenceName')!=group_name):
        raise RuntimeError('Existing subscription grouping differs for '+author['slug']+'; preserved.')
    group=groups[0] if groups else None
    if group is None and apply:
        group=client.write('POST','subscriptionGroups',{'referenceName':group_name},{'app':relation('apps',app['id'])})
    report={'slug':author['slug'],'appId':app['id'],'bundleId':author['bundle_id'], 'groupId':group['id'] if group else None, 'products':[]}
    if not group:
        report['status']='group_missing'
        return report
    if apply:
        version=draft_version(client,'subscriptionGroups',group['id'],'subscriptionGroupVersions',True)
        localize(client,version,'subscriptionGroupVersions','subscriptionGroupLocalizations',{'name':group_name})
    subscriptions=client.rows(f"/v1/subscriptionGroups/{group['id']}/subscriptions",{'limit':200})
    for option,price,label in [('annual','30.00','Jahresabo'),('supporter','90.00','Förderabo')]:
        pid=author['bundle_id']+'.'+option
        sub=next((s for s in subscriptions if s['attributes'].get('productId')==pid),None)
        if not sub and apply:
            sub=client.write('POST','subscriptions',{'name':author['author_short_name']+' '+label,'productId':pid,'subscriptionPeriod':'ONE_YEAR','groupLevel':1,'reviewNote':'One year of reading access for this author app on iPhone, iPad and Mac. Both annual plans have identical features. Eligible Apple accounts receive a three-month free trial. Independent free-year requests never convert to payment.'},{'group':relation('subscriptionGroups',group['id'])})
        if not sub:
            report['products'].append({'productId':pid,'status':'missing','targetPriceEUR':price})
            continue
        if sub['attributes'].get('subscriptionPeriod')!='ONE_YEAR' or sub['attributes'].get('groupLevel')!=1:
            raise RuntimeError('Existing subscription period or level differs; preserved: '+pid)
        if apply:
            version=draft_version(client,'subscriptions',sub['id'],'subscriptionVersions',True)
            description='Ein Jahr App-Zugang.' + (' Unterstützt kostenlose Zugänge.' if option=='supporter' else ' Regulärer Beitrag.')
            localize(client,version,'subscriptionVersions','subscriptionLocalizations',{'name':label,'description':description})
            price_point(client,sub['id'],price,'DEU')
            setup_availability(client,sub['id'],'DEU')
            setup_price(client,sub['id'],price,'DEU')
            setup_intro(client,sub['id'],'DEU')
        report['products'].append({'productId':pid,'subscriptionId':sub['id'],'prices':current_prices(client,sub['id'],'DEU'),'introductoryOffers':client.rows(f"/v1/subscriptions/{sub['id']}/introductoryOffers",{'filter[territory]':'DEU','limit':200})})
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--author',action='append')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--plan',action='store_true',help='Show required products without contacting Apple or reading credentials.')
    args=parser.parse_args()
    manifest=json.loads((ROOT/'editions/authors.json').read_text())
    authors=[a for a in manifest['authors'] if not args.author or a['slug'] in args.author]
    if not authors or (args.author and set(args.author)-{a['slug'] for a in authors}):
        parser.error('Unknown author slug')
    if args.plan:
        reports=[{'slug':a['slug'],'bundleId':a['bundle_id'],'appName':a['app_name'],'group':a['author_short_name']+'-App-Zugang','products':[{'id':a['bundle_id']+'.annual','priceEUR':'30.00'},{'id':a['bundle_id']+'.supporter','priceEUR':'90.00'}],'period':'ONE_YEAR','trial':'THREE_MONTHS','platforms':['iOS','macOS']} for a in authors]
    else:
        client=ASCClient(allow_writes=args.apply)
        reports=[run(a,client,args.apply) for a in authors]
        if args.apply:
            (ROOT/'editions/apple-setup-report.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(reports,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
