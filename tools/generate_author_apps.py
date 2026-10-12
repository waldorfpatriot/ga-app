#!/usr/bin/env python3
"""Generate separate Apple projects that compile the existing GA reader sources.

No source copies, store registrations or publication. Per-author catalogs,
StoreKit fixtures, app identity, icons and private CloudKit containers are owned
by each edition. Re-run after the GA project or author library changes.
"""
from __future__ import annotations
import argparse
import copy
import html
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'editions/authors.json'
IOS_TARGET = 'A00500000000000000000001'
MAC_TARGET = 'A00500000000000000000002'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def openstep(value, level=0):
    """Serialize Xcode's property-list structure without an external generator."""
    indent = '\t' * level
    if isinstance(value, dict):
        return '{\n' + ''.join(indent + '\t' + json.dumps(str(k)) + ' = ' + openstep(v, level+1) + ';\n' for k,v in value.items()) + indent + '}'
    if isinstance(value, list):
        return '(\n' + ''.join(indent+'\t'+openstep(v,level+1)+',\n' for v in value) + indent + ')'
    return json.dumps(str(value), ensure_ascii=False)


def read_project():
    raw = subprocess.check_output(['plutil','-convert','json','-o','-', str(ROOT/'apple/GA.xcodeproj/project.pbxproj')])
    return json.loads(raw)


def generate_project(author, base):
    project = copy.deepcopy(base)
    objects = project['objects']
    # Steiner UI fixtures refer to its specific corpus. The new apps have their
    # own integration verification; do not attach misleading fixture targets.
    test_ids = {key for key in objects if key.startswith('B0')}
    for key in test_ids:
        del objects[key]
    for obj in objects.values():
        for key,val in list(obj.items()):
            if isinstance(val, list):
                obj[key] = [x for x in val if not isinstance(x,str) or x not in test_ids]
    project_attributes = objects[project['rootObject']]['attributes'].get('TargetAttributes', {})
    for key in test_ids:
        project_attributes.pop(key, None)
    objects['A00400000000000000000002']['path'] = '../../../apple/AuthorReader'
    objects['A00400000000000000000002']['name'] = 'Shared Reader'
    # Only author projects include the edition-aware identity source.
    ref = 'D00200000000000000000001'
    objects[ref] = {'isa':'PBXFileReference','lastKnownFileType':'sourcecode.swift','path':'AppEdition.swift','sourceTree':'<group>'}
    objects['A00400000000000000000002']['children'].append(ref)
    for index,phase in enumerate(['A00600000000000000000001','A00600000000000000000002'],start=1):
        build_id='D0010000000000000000000'+str(index)
        objects[build_id]={'isa':'PBXBuildFile','fileRef':ref}
        objects[phase]['files'].append(build_id)
    # Author resources live next to each project. Source remains shared.
    resource_paths = {
        'Assets.xcassets':'Assets.xcassets', 'BundledCatalog':'BundledCatalog',
        'BundledContent':'BundledContent', 'ga.icon':'author.icon',
        'Info.plist':'Info.plist', 'Purchases.xcconfig':'Purchases.xcconfig',
        'GA.storekit':'Author.storekit', 'GAMac.entitlements':'Mac.entitlements',
    }
    for obj in objects.values():
        if obj.get('isa') == 'PBXFileReference' and obj.get('path') in resource_paths:
            obj['path'] = resource_paths[obj['path']]
            obj['sourceTree'] = 'SOURCE_ROOT'
    for target_id, platform in [(IOS_TARGET,'iOS'),(MAC_TARGET,'Mac')]:
        target = objects[target_id]
        name = author['author_short_name'] + ' ' + platform
        target['name'] = target['productName'] = name
        objects[target['productReference']]['path'] = name + '.app'
        configurations = objects[target['buildConfigurationList']]['buildConfigurations']
        for cid in configurations:
            settings = objects[cid]['buildSettings']
            settings.update({
                'PRODUCT_BUNDLE_IDENTIFIER':author['bundle_id'],
                'INFOPLIST_FILE':'Info.plist',
                'CODE_SIGN_ENTITLEMENTS':'iOS.entitlements' if platform=='iOS' else 'Mac.entitlements',
                'INFOPLIST_KEY_CFBundleDisplayName':author['display_name'],
                'INFOPLIST_KEY_GACloudKitContainerIdentifier':author['cloudkit_container'],
                'GA_CLOUDKIT_ENVIRONMENT': {'Debug':'Development','Release':'Production'}[objects[cid]['name']],
                'ASSETCATALOG_COMPILER_APPICON_NAME':'author',
                'CURRENT_PROJECT_VERSION':'1',
            })
    return project


def scheme(author, platform, storekit=False):
    name = author['author_short_name'] + ' ' + platform
    source = ROOT/'apple/GA.xcodeproj/xcshareddata/xcschemes'/('GA '+platform+'.xcscheme')
    tree = ET.parse(source)
    for node in tree.iter('BuildableReference'):
        node.set('BuildableName',name+'.app')
        node.set('BlueprintName',name)
        node.set('ReferencedContainer','container:Author.xcodeproj')
    if storekit:
        launch=tree.find('LaunchAction')
        ET.SubElement(launch, 'StoreKitConfigurationFileReference', {'identifier':'../../Author.storekit'})
        variables=ET.SubElement(launch,'EnvironmentVariables')
        ET.SubElement(variables,'EnvironmentVariable',{'key':'GA_USE_LOCAL_STOREKIT','value':'1','isEnabled':'YES'})
    ET.indent(tree, space='   ')
    return ET.tostring(tree.getroot(),encoding='unicode')+'\n'


def configure(author, directory):
    # Never inherit Steiner's RevenueCat key: a new App Store record requires
    # its own public key. StoreKit remains usable during setup and offline QA.
    values = {
        'GA_AUTHOR_NAME':author['author_name'], 'GA_AUTHOR_SHORT_NAME':author['author_short_name'],
        'GA_EDITION_TITLE':'Werke', 'GA_AUTHOR_SLUG':author['slug'],
        'GA_WORK_PREFIX':author['work_prefix'], 'GA_DEFAULT_LANGUAGE':author['language'],
        'GA_PRODUCT_ID_PREFIX':author['bundle_id'], 'GA_ENTITLEMENT_IDENTIFIER':author['entitlement_id'],
        'GA_CLOUDKIT_CONTAINER_IDENTIFIER':author['cloudkit_container'],
        'GA_REVENUECAT_IOS_SDK_KEY':'',
        'GA_SERVER_BASE_URL':author['reader_base_url'], 'GA_ACCESS_BASE_URL':author['access_base_url'],
        'GA_PRIVACY_URL':author['access_base_url']+'/privacy.html', 'GA_SUPPORT_URL':author['access_base_url']+'/support.html',
    }
    lines=['// Generated author identity; the reader source and access model are shared.',
           '// Add this app\'s public RevenueCat Apple SDK key in Purchases.local.xcconfig.']
    for key,val in values.items():
        if '\n' in val:
            raise ValueError('Unexpected newline in configuration')
        lines.append(key+' = '+val.replace('https://','https:/$()/'))
    lines += ['','#include? "Purchases.local.xcconfig"','']
    (directory/'Purchases.xcconfig').write_text('\n'.join(lines))
    (directory/'Purchases.local.xcconfig.example').write_text('// The public Apple SDK key for this author app only.\nGA_REVENUECAT_IOS_SDK_KEY = appl_REPLACE_WITH_THIS_APP_PUBLIC_KEY\n')
    shutil.copyfile(ROOT/'apple/AuthorReader/Info.plist',directory/'Info.plist')
    for source,name in [('GA.entitlements','iOS.entitlements'),('GAMac.entitlements','Mac.entitlements')]:
        data=plistlib.loads((ROOT/'apple/GA'/source).read_bytes())
        data['com.apple.developer.icloud-container-identifiers']=[author['cloudkit_container']]
        data['com.apple.developer.icloud-container-environment']='$(GA_CLOUDKIT_ENVIRONMENT)'
        (directory/name).write_bytes(plistlib.dumps(data,sort_keys=False))
    fixture=json.loads((ROOT/'apple/GA/GA.storekit').read_text())
    fixture['identifier']=author['slug']+'_ACCESS_QA'
    group=fixture['subscriptionGroups'][0]
    group['id']=author['slug']+'_ACCESS'
    group['name']=author['author_short_name']+'-App-Zugang'
    group['localizations'][0].update(description='Zugang zur '+author['display_name']+'-App',displayName=group['name'])
    for sub in group['subscriptions']:
        option=sub['productID'].rsplit('.',1)[-1]
        sub.update(productID=author['bundle_id']+'.'+option,subscriptionGroupID=group['id'],internalID=author['slug']+'-'+option)
        sub['introductoryOffer']['internalID']=author['slug']+'-trial-'+option
    write_json(directory/'Author.storekit',fixture)
    assets=directory/'Assets.xcassets'
    write_json(assets/'Contents.json',{'info':{'author':'xcode','version':1}})
    shutil.copytree(ROOT/'apple/GA/Assets.xcassets/AccentColor.colorset',assets/'AccentColor.colorset',dirs_exist_ok=True)


def package_library(author, directory):
    library=ROOT/'editions'/author['slug']/'library'
    catalog_path=library/'catalog.json'
    if not catalog_path.exists():
        raise RuntimeError('Missing complete starter library: '+author['slug'])
    # Bundled and hosted catalogs must advertise the very same content revision.
    # Reuse the public exporter so transport formatting cannot cause a false update.
    from generate_author_infrastructure import export_reader
    public_files,_,_=export_reader(author,library.parent)
    catalog=json.loads(public_files['catalog.json'])
    if not catalog.get('works'):
        raise RuntimeError('Empty starter library: '+author['slug'])
    output=directory/'BundledContent'
    output.mkdir(exist_ok=True)
    expected=set()
    sections=0
    for work in catalog['works']:
        payload=json.loads(public_files['api/catalog/'+work['id']+'/content'])
        passages=payload['passages']
        if payload.get('content_completeness')!='complete' or not passages or any(not p['text'].strip() for p in passages):
            raise RuntimeError('Incomplete starter work: '+work['id'])
        expected.add(work['id']+'.json')
        write_json(output/(work['id']+'.json'),payload)
        sections+=len(passages)
    for old in output.glob('*.json'):
        if old.name not in expected:
            old.unlink()
    write_json(directory/'BundledCatalog/catalog.json',catalog)
    return len(expected),sections



def generate_store_metadata(author, works, sections):
    directory=ROOT/'editions'/author['slug']/'app-store'
    directory.mkdir(exist_ok=True)
    catalog=json.loads((ROOT/'editions'/author['slug']/'library/catalog.json').read_text()) if works else {'works':[]}
    titles='\n'.join('• '+title for title in author.get('library_highlights', [w['title'] for w in catalog['works']]))
    original_texts='1 vollständiger Originaltext' if works==1 else str(works)+' vollständige Originaltexte'
    description=(author['author_name']+' auf iPhone, iPad und Mac.\n\n'
        +(author['library_description'].format(works=works) if author.get('library_description') else original_texts+' zum Start, offline in der App enthalten.')+'\n'+titles
        +'\n\nPasse Schrift, Zeilenabstand und Erscheinungsbild an. Suche in Texten und persönlichen Notizen, markiere Stellen, setze Lesezeichen und ordne Werke in Sammlungen. Teile Zitate und exportiere Werke als EPUB. Mit iCloud können Lesepositionen, Notizen und Markierungen über deine private Datenbank synchronisiert werden.'
        +'\n\nAlle Beitragsoptionen ermöglichen dieselben Funktionen in dieser Autor-App:\n• Jahresabo: 30 € pro Jahr.\n• Förderabo: 90 € pro Jahr.\n• Kostenloses Jahr auf eine kurze, vertrauliche Bitte: zwölf Monate Zugang, ohne Einkommensnachweis, jederzeit erneut anfragbar. Der kostenlose Zugang endet ohne Zahlung.'
        +'\n\nBerechtigte Apple-Accounts können das gewählte Jahresabo drei Monate kostenlos testen. Danach berechnet Apple den ausgewählten Jahrespreis. Beide Abos verlängern sich automatisch jährlich, sofern sie nicht rechtzeitig im App Store gekündigt werden. Verbindlich sind Preis und Bedingungen, die Apple vor dem Kauf anzeigt.'
        +'\n\nEine unabhängige digitale Leseausgabe. Kein offizielles Angebot des Autors, seiner Erben oder einer Autorengesellschaft.\n\nSupport: jonathan@kutscher.club\nNutzungsbedingungen: https://www.apple.com/legal/internet-services/itunes/dev/stdeula/')
    metadata={'locale':'de-DE','name':author['app_name'],'subtitle':'Lesen, suchen, Notizen sammeln',
        'description':description,'keywords':'Bücher,Lesen,Notizen,Offline,Lesezeichen,Originaltexte',
        'copyright':'2026 Jonathan Kutscher','primary_category':'Books','secondary_category':'Reference',
        'bundle_id':author['bundle_id'],'apple_app_id':None,'platforms':['iOS','macOS'],
        'support_url':author['access_base_url']+'/support.html','privacy_policy_url':author['access_base_url']+'/privacy.html',
        'marketing_url':author['access_base_url']+'/',
        'terms_of_use_url':'https://www.apple.com/legal/internet-services/itunes/dev/stdeula/',
        'review_contact':{'first_name':'Jonathan','last_name':'Kutscher','email':'jonathan@kutscher.club','phone':'+491799439545'},
        'subscription_group_localization':{'display_name':author['author_short_name']+'-App-Zugang'},
        'subscriptions':[{'product_id':author['bundle_id']+'.'+option,'display_name':label,'duration':'P1Y','target_price_de_eur':price,'introductory_offer':'P3M free trial for eligible Apple accounts','platforms':['iOS','macOS']} for option,label,price in [('annual','Jahresabo','30.00'),('supporter','Förderabo','90.00')]],
        'publication_status':'draft_local_metadata','revenuecat_project_scope':'one_independent_project_per_author','content_scope':author.get('content_scope','starter_original_texts'),'starter_works':works,'starter_sections':sections}
    if len(metadata['name'])>30 or len(metadata['subtitle'])>30 or len(description)>4000:
        raise RuntimeError('Apple metadata character limit exceeded')
    write_json(directory/'metadata.de-DE.json',metadata)
    web=ROOT/'editions'/author['slug']/'web'
    web.mkdir(exist_ok=True)
    library_text=('Die App enthält zum Start einen vollständigen Originaltext. Der Starttext ist in der App enthalten. Mit aktivem App-Zugang bleibt er offline lesbar.' if works==1 else f'Die App enthält zum Start {works} vollständige Originaltexte. Alle Starttexte sind in der App enthalten. Mit aktivem App-Zugang bleiben sie offline lesbar.')
    if author.get('library_description'):
        library_text=html.escape(author['library_description'].format(works=works))
    for filename in ['privacy.html','support.html']:
        text=(ROOT/'docs/app-store/web'/filename).read_text()
        text=text.replace('fototausch.eu/rudolf-steiner-ga',author['access_base_url'].removeprefix('https://'))
        text=text.replace('GA-Nummer','Werknummer').replace('Rudolf Steiner Gesamtausgabe',author['author_name']+'-Ausgabe').replace('GA-App',author['author_short_name']+'-App')
        text=text.replace('Der Katalog umfasst derzeit 463 Einträge. 324 Texte sind verfügbar; noch fehlende Werke sind als „Coming soon“ gekennzeichnet. Fünf vollständige Grundwerke sind bereits in der App enthalten. Weitere verfügbare Texte lädst du bei Bedarf herunter. Mit aktivem Zugang bleiben heruntergeladene Texte auch offline lesbar.',library_text)
        (web/filename).write_text(text)
    name=html.escape(author['app_name'])
    (web/'index.html').write_text('<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+name+'</title><style>body{max-width:760px;margin:64px auto;padding:0 24px;background:#f5f3ed;color:#252521;font:18px/1.65 system-ui}h1{font:600 44px Georgia}a{color:#285e71}</style><h1>'+name+'</h1><p>Für iPhone, iPad und Mac.</p><p>'+library_text+'</p><p>Lesen, suchen, markieren und persönliche Notizen sammeln. Gleiche Funktionen mit 30 € Jahresabo, 90 € Förderabo oder zwölf Monaten kostenlosem Zugang auf eine vertrauliche Bitte. Berechtigte Apple-Accounts erhalten drei Monate kostenlose Testphase für das gewählte Jahresabo.</p><p><a href="support.html">Kontakt und Hilfe</a> · <a href="privacy.html">Datenschutz</a></p><p>Unabhängige digitale Leseausgabe. © 2026 Jonathan Kutscher · Einzelunternehmen.</p></html>\n')


def generate(author, base, require_content=True):
    directory=ROOT/'editions'/author['slug']/'apple'
    directory.mkdir(parents=True,exist_ok=True)
    project=generate_project(author,base)
    project_dir=directory/'Author.xcodeproj'
    project_dir.mkdir(exist_ok=True)
    (project_dir/'project.pbxproj').write_text('// !$*UTF8*$!\n'+openstep(project)+'\n')
    schemes=project_dir/'xcshareddata/xcschemes'
    schemes.mkdir(parents=True,exist_ok=True)
    for platform in ['iOS','Mac']:
        for qa in [False,True]:
            filename=author['author_short_name']+' '+platform+(' StoreKit QA' if qa else '')+'.xcscheme'
            (schemes/filename).write_text(scheme(author,platform,qa))
    resolved=ROOT/'apple/GA.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved'
    if resolved.exists():
        target=project_dir/'project.xcworkspace/xcshareddata/swiftpm/Package.resolved'
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(resolved,target)
    configure(author,directory)
    counts=package_library(author,directory) if require_content else (0,0)
    if require_content:
        generate_store_metadata(author,*counts)
    return dict(slug=author['slug'],bundle_id=author['bundle_id'],works=counts[0],sections=counts[1],project=str(project_dir.relative_to(ROOT)))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--author',action='append',help='Generate selected slug(s), otherwise all 11.')
    parser.add_argument('--prepare',action='store_true',help='Prepare project/configuration before text imports complete.')
    parser.add_argument('--skip-icons',action='store_true')
    args=parser.parse_args()
    manifest=json.loads(MANIFEST.read_text())
    authors=[a for a in manifest['authors'] if not args.author or a['slug'] in args.author]
    if not authors or (args.author and set(args.author)-{a['slug'] for a in authors}):
        parser.error('Unknown author slug')
    reports=[generate(author,read_project(),not args.prepare) for author in authors]
    workspace=ROOT/'editions/AuthorApps.xcworkspace'
    workspace.mkdir(exist_ok=True)
    root=ET.Element('Workspace',{'version':'1.0'})
    for author in manifest['authors']:
        ET.SubElement(root,'FileRef',{'location':'group:'+author['slug']+'/apple/Author.xcodeproj'})
    ET.indent(root,space='   ')
    (workspace/'contents.xcworkspacedata').write_text(ET.tostring(root,encoding='unicode')+'\n')
    resolved=ROOT/'apple/GA.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved'
    target=workspace/'xcshareddata/swiftpm/Package.resolved'
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(resolved,target)
    if not args.skip_icons:
        subprocess.run(['swift',str(ROOT/'tools/render_author_icons.swift'),str(MANIFEST),str(ROOT)],check=True)
    write_json(ROOT/'editions/generation-report.json',{'authors':reports,'publication_status':'local_projects_only'})
    print(json.dumps(reports,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
