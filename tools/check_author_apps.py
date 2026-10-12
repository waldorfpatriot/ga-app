#!/usr/bin/env python3
"""Verify independent app projects, identical subscription terms and GA preservation."""
import hashlib
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import xml.etree.ElementTree as ET

from import_author_library import original_languages

ROOT=Path(__file__).resolve().parents[1]


def ga_snapshot():
    files=[p for directory in ['apple/GA','apple/GA.xcodeproj'] for p in (ROOT/directory).rglob('*') if p.is_file() and not any(part in {'xcuserdata','.DS_Store'} for part in p.parts)]
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def verify():
    manifest=json.loads((ROOT/'editions/authors.json').read_text())
    authors=manifest['authors']
    assert len(authors)==11
    for field in ['slug','bundle_id','cloudkit_container','database','service_name','port','reader_base_url','access_base_url']:
        assert len({a[field] for a in authors})==11, field
    expected=json.loads((ROOT/'editions/ga-baseline.json').read_text())
    actual=ga_snapshot()
    assert expected==actual, 'Original GA changed: '+str([k for k in set(expected)|set(actual) if expected.get(k)!=actual.get(k)])
    total=0
    for author in authors:
        edition=ROOT/'editions'/author['slug']
        app=edition/'apple'
        raw=subprocess.check_output(['plutil','-convert','json','-o','-',str(app/'Author.xcodeproj/project.pbxproj')])
        project=json.loads(raw);objects=project['objects']
        assert objects['A00400000000000000000002']['path']=='../../../apple/AuthorReader'
        targets=[o for o in objects.values() if o.get('isa')=='PBXNativeTarget']
        assert len(targets)==2
        for target in targets:
            for cid in objects[target['buildConfigurationList']]['buildConfigurations']:
                config=objects[cid]['buildSettings']
                assert config['PRODUCT_BUNDLE_IDENTIFIER']==author['bundle_id']
                assert config['CURRENT_PROJECT_VERSION']=='1'
                assert config['ASSETCATALOG_COMPILER_APPICON_NAME']=='author'
                assert config['INFOPLIST_KEY_GACloudKitContainerIdentifier']==author['cloudkit_container']
                assert config['GA_CLOUDKIT_ENVIRONMENT']=={'Debug':'Development','Release':'Production'}[objects[cid]['name']]
        for name in ['iOS.entitlements','Mac.entitlements']:
            entitlements=plistlib.loads((app/name).read_bytes())
            assert entitlements['com.apple.developer.icloud-container-identifiers']==[author['cloudkit_container']]
            assert entitlements['com.apple.developer.icloud-container-environment']=='$(GA_CLOUDKIT_ENVIRONMENT)'
        fixture=json.loads((app/'Author.storekit').read_text())
        subs=fixture['subscriptionGroups'][0]['subscriptions']
        assert {s['productID'] for s in subs}=={author['bundle_id']+'.annual',author['bundle_id']+'.supporter'}
        assert len(subs)==2
        for sub in subs:
            assert sub['displayPrice']==('90' if sub['productID'].endswith('.supporter') else '30')
            assert sub['groupNumber']==1 and sub['recurringSubscriptionPeriod']=='P1Y'
            intro=sub['introductoryOffer']
            assert intro['paymentMode']=='free' and intro['subscriptionPeriod']=='P3M' and intro['numberOfPeriods']==1
        config=(app/'Purchases.xcconfig').read_text()
        assert 'appl_REhGNbpSKvBhaMwFLFusDLhAavA' not in config
        assert 'GA_REVENUECAT_IOS_SDK_KEY = \n' in config
        assert author['bundle_id'] in config and author['slug'] in config
        icon=json.loads((app/'author.icon/icon.json').read_text())
        for group in icon['groups']:
            for layer in group.get('layers',[]):
                assert (app/'author.icon/Assets'/layer['image-name']).is_file()
                assert 'steiner' not in layer['image-name'].lower()
        catalog=json.loads((app/'BundledCatalog/catalog.json').read_text())
        assert catalog['works']
        for work in catalog['works']:
            assert not work['id'].startswith('ga-')
            assert work.get('author')==author['author_name']
            assert work['language'] in original_languages(author)
            payload=json.loads((app/'BundledContent'/(work['id']+'.json')).read_text())
            assert payload['work_id']==work['id'] and payload['content_completeness']=='complete'
            assert payload['language']==work['language']
            assert payload['passage_count']==len(payload['passages'])>0
            assert len({p['id'] for p in payload['passages']})==len(payload['passages'])
            assert all(p['text'].strip() for p in payload['passages'])
            assert 'source_text' not in json.dumps(payload)
            total+=1
        metadata=json.loads((edition/'app-store/metadata.de-DE.json').read_text())
        assert len(metadata['name'])<=30 and len(metadata['description'])<=4000
        assert metadata['starter_works']==len(catalog['works'])
        assert metadata['apple_app_id'] is None
        assert metadata['bundle_id']==author['bundle_id']
        for filename in ['support.html','privacy.html','index.html']:
            page=(edition/'web'/filename).read_text()
            assert 'rudolf-steiner-ga' not in page and '324 Texte' not in page and '463 Einträge' not in page
        assert len(list((app/'Author.xcodeproj/xcshareddata/xcschemes').glob('*.xcscheme')))==4
        for scheme in (app/'Author.xcodeproj/xcshareddata/xcschemes').glob('*StoreKit QA.xcscheme'):
            tree=ET.parse(scheme)
            assert tree.find('.//EnvironmentVariable[@key="GA_USE_LOCAL_STOREKIT"]').get('value')=='1'
            assert tree.find('.//StoreKitConfigurationFileReference').get('identifier')=='../../Author.storekit'
        hosted=json.loads((edition/'deploy/reader/catalog.json').read_text())
        assert {w['id']:w['content_revision'] for w in hosted['works']}=={w['id']:w['content_revision'] for w in catalog['works']}
    print(f'Verified 11 isolated apps, 22 targets, {total} complete bundled works, subscription parity and unchanged GA.')

if __name__=='__main__':
    if '--snapshot-ga' in sys.argv:
        path=ROOT/'editions/ga-baseline.json'
        if path.exists():
            raise SystemExit('Refusing to replace the protected GA baseline.')
        path.write_text(json.dumps(ga_snapshot(),indent=2)+'\n')
        print('Saved existing GA fingerprint without changing its files.')
    else:
        verify()
