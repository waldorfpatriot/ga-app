#!/usr/bin/env python3
"""Build every isolated author target without signing or contacting publishing APIs."""
import argparse
import json
import platform as host_platform
import plistlib
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]


def verify_artifact(author,platform,output):
    """Check the actual compiled app's identity and offline starter library."""
    name=author['author_short_name']+' '+('Mac' if platform=='macos' else 'iOS')
    derived=output/'derived'/'friedrich-nietzsche'
    app=derived/'Build/Products'/('Debug' if platform=='macos' else 'Debug-iphonesimulator')/(name+'.app')
    info_path=app/'Contents/Info.plist' if platform=='macos' else app/'Info.plist'
    resources=app/'Contents/Resources' if platform=='macos' else app
    errors=[]
    try:
        info=plistlib.loads(info_path.read_bytes())
        for key,expected in {'CFBundleIdentifier':author['bundle_id'],'GAAuthorSlug':author['slug'],'GAAuthorName':author['author_name'],'GAProductIDPrefix':author['bundle_id'],'GACloudKitContainerIdentifier':author['cloudkit_container'],'GA_SERVER_BASE_URL':author['reader_base_url'],'GAAccessBaseURL':author['access_base_url']}.items():
            if info.get(key)!=expected: errors.append('Built app identity mismatch: '+key)
        bundled=json.loads((resources/'BundledCatalog/catalog.json').read_text())
        expected_catalog=json.loads((ROOT/'editions'/author['slug']/'apple/BundledCatalog/catalog.json').read_text())
        if bundled!=expected_catalog: errors.append('Built app starter catalog mismatch')
        for work in bundled['works']:
            if (resources/'BundledContent'/(work['id']+'.json')).read_bytes()!=(ROOT/'editions'/author['slug']/'apple/BundledContent'/(work['id']+'.json')).read_bytes():
                errors.append('Built app starter text mismatch: '+work['id'])
    except (OSError,ValueError,KeyError,plistlib.InvalidFileException) as error:
        errors.append('Could not verify built app: '+str(error))
    return {'app':str(app),'artifact_verified':not errors,'errors':errors}


def build(author,platform,output):
    started=time.monotonic()
    name=author['author_short_name']+' '+('Mac' if platform=='macos' else 'iOS')
    derived=output/'derived'/'friedrich-nietzsche'
    logfile=output/(author['slug']+'-'+platform+'.log')
    destination='generic/platform=macOS' if platform=='macos' else 'generic/platform=iOS Simulator'
    command=['xcodebuild','-workspace',str(ROOT/'editions/AuthorApps.xcworkspace'),'-scheme',name,'-configuration','Debug',
             '-destination',destination,'-derivedDataPath',str(derived),
             '-clonedSourcePackagesDirPath',str(output/'packages'),'-disableAutomaticPackageResolution',
             '-jobs','4','CODE_SIGNING_ALLOWED=NO','build']
    if host_platform.machine()=='arm64':
        command.insert(-1,'ARCHS=arm64')
    with logfile.open('w') as log:
        result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
    errors=[line.strip() for line in logfile.read_text().splitlines() if ': error:' in line or 'error:' in line][:5]
    artifact=verify_artifact(author,platform,output) if result.returncode==0 else {'artifact_verified':False,'errors':[]}
    errors.extend(artifact.pop('errors'))
    report={'slug':author['slug'],'platform':platform,'scheme':name,'native_build_passed':result.returncode==0,'passed':result.returncode==0 and not errors,'seconds':round(time.monotonic()-started,1),'log':str(logfile),'errors':errors,**artifact}
    print(author['slug']+' '+platform+': '+('passed' if report['passed'] else 'FAILED'),flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--author',action='append')
    parser.add_argument('--platform',choices=['ios','macos','both'],default='both')
    parser.add_argument('--jobs',type=int,default=1)
    parser.add_argument('--output',type=Path,default=Path('/tmp/ga-author-app-builds'))
    parser.add_argument('--verify-only',action='store_true',help='Verify existing compiled apps without rebuilding or resolving packages.')
    args=parser.parse_args()
    if args.jobs!=1: parser.error('Use --jobs 1: all projects reuse one dependency cache and build database.')
    authors=[a for a in json.loads((ROOT/'editions/authors.json').read_text())['authors'] if not args.author or a['slug'] in args.author]
    if not authors or (args.author and set(args.author)-{a['slug'] for a in authors}): parser.error('Unknown author slug')
    args.output.mkdir(parents=True,exist_ok=True)
    platforms=['ios','macos'] if args.platform=='both' else [args.platform]
    report_path=ROOT/'editions/build-verification.json'
    previous=json.loads(report_path.read_text()).get('builds',[]) if report_path.exists() else []
    reports=[]
    if args.verify_only:
        existing={(r['slug'],r['platform']):r for r in previous}
        for author in authors:
            for platform in platforms:
                key=(author['slug'],platform)
                if key not in existing: parser.error('No recorded native build for '+author['slug']+' '+platform)
                report=dict(existing[key])
                artifact=verify_artifact(author,platform,args.output)
                native_passed=report.get('native_build_passed',report['passed'])
                errors=artifact.pop('errors')
                if not native_passed: errors=report.get('errors',[])+errors
                report.update(artifact,native_build_passed=native_passed,passed=native_passed and not errors,errors=errors)
                reports.append(report)
                print(author['slug']+' '+platform+': '+('verified' if report['passed'] else 'FAILED'),flush=True)
    else:
        # Resolve dependencies once. Xcode's shared database requires serial builds.
        first=authors[0]
        resolve=['xcodebuild','-resolvePackageDependencies','-workspace',str(ROOT/'editions/AuthorApps.xcworkspace'),'-scheme',first['author_short_name']+' iOS','-clonedSourcePackagesDirPath',str(args.output/'packages')]
        with (args.output/'package-resolution.log').open('w') as log:
            subprocess.run(resolve,stdout=log,stderr=subprocess.STDOUT,check=True)
        for author in authors:
            for platform in platforms: reports.append(build(author,platform,args.output))
    requested_passed=all(r['passed'] for r in reports)
    refreshed={(r['slug'],r['platform']) for r in reports}
    reports=sorted([r for r in previous if (r['slug'],r['platform']) not in refreshed]+reports,key=lambda r:(r['slug'],r['platform']))
    report_path.write_text(json.dumps({'signing':'disabled','publication':'none','builds':reports},indent=2)+'\n')
    raise SystemExit(0 if requested_passed else 1)

if __name__=='__main__': main()
