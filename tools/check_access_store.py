#!/usr/bin/env python3
"""Compile the current AccessStore with a controlled test backend and the real RevenueCat SDK.

The test doubles and exposed private members exist only in a temporary executable;
no production backend, Keychain item or purchase is changed by this check.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--sdk-build-root', type=Path, default=Path('/tmp/ga-app-store-mac-archive-build'))
args = parser.parse_args()
archive = args.sdk_build_root / 'Build/Intermediates.noindex/ArchiveIntermediates/GA Mac'
modules = archive / 'BuildProductsPath/Release'
object_file = archive / 'IntermediateBuildFilesPath/RevenueCat.build/Release/RevenueCat-t.build/Objects-normal/arm64/Binary/RevenueCat.o'
if not object_file.exists():
    raise SystemExit('Build the GA Mac Release archive first; its real RevenueCat module/object is required.')
client = (ROOT / 'apple/GA/AccessClient.swift').read_text()
models = client.split('struct AccessClient: Sendable', 1)[0]
models += 'enum AccessClientError:' + client.split('enum AccessClientError:', 1)[1].split('\nenum AccessKeychain', 1)[0]
store = (ROOT / 'apple/GA/AccessStore.swift').read_text().replace('private(set) ', '').replace('private ', '')
ui = (ROOT / 'apple/GA/PurchaseScreen.swift').read_text()
if 'if await access.submitFreeRequest(request)' not in ui:
    raise SystemExit('PurchaseScreen must clear its text only after an explicit successful submit outcome.')
with tempfile.TemporaryDirectory(prefix='ga-access-state-') as work:
    work = Path(work)
    (work/'Models.swift').write_text(models)
    (work/'AccessStore.swift').write_text(store)
    binary = work/'verify-access-state'
    subprocess.run(['swiftc', '-parse-as-library', '-swift-version', '6', '-DDEBUG',
                    '-target', 'arm64-apple-macosx26.0', '-I', str(modules),
                    str(work/'Models.swift'), str(work/'AccessStore.swift'),
                    str(ROOT/'tools/access_store_harness.swift'), str(object_file),
                    '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
