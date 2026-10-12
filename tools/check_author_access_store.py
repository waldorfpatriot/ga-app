#!/usr/bin/env python3
"""Check author subscription isolation against the real RevenueCat SDK.

Uses temporary app bundles and the existing in-memory backend/Keychain doubles;
it never contacts a service or changes real purchases or personal data.
"""

import argparse
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile

from check_author_reader import expanded_info


ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "apple/AuthorReader"
MAIN = r'''
    @MainActor static func main() throws {
        expect(!AppEdition.isSteiner, "The fixture must use the real author app configuration")
        ControlledBackend.shared.reset()
        let store = AccessStore()
        let now = Date(timeIntervalSince1970: Date().timeIntervalSince1970.rounded(.down))
        let future = now.addingTimeInterval(3600)
        let expired = now.addingTimeInterval(-3600)
        let ownProducts = [AccessOption.annual.productID!, AccessOption.supporter.productID!]
        for product in ownProducts {
            store.apply(try info(subscriptionExpiry: future, grace: nil, productIdentifier: product))
            expect(store.hasAccess && store.paidExpiration == future, "This author's verified product must activate access")
            store.apply(try info(subscriptionExpiry: expired, grace: future, productIdentifier: product))
            expect(store.hasAccess && store.paidExpiration == future, "This author's verified billing grace must retain access")
        }
        let foreignPrefix = CommandLine.arguments[1]
        for product in [foreignPrefix + ".annual", foreignPrefix + ".supporter",
                        "com.jonathankutscher.ga.annual", AppEdition.productIDPrefix + ".monthly",
                        AppEdition.productIDPrefix + ".annual.extra"] {
            store.apply(try info(subscriptionExpiry: future, grace: nil, productIdentifier: ownProducts[0]))
            expect(store.hasAccess, "A valid subscription must be active before the foreign entitlement replaces it")
            store.apply(try info(subscriptionExpiry: future, grace: nil, productIdentifier: product))
            expect(!store.hasAccess && store.paidExpiration == nil, "A foreign or unknown product must revoke cached paid access")
            store.apply(try info(subscriptionExpiry: expired, grace: future, productIdentifier: product))
            expect(!store.hasAccess && store.paidExpiration == nil, "A foreign billing-grace date must not activate access")
        }
        store.apply(try info(subscriptionExpiry: future, grace: nil, active: false, productIdentifier: ownProducts[0]))
        expect(!store.hasAccess, "An inactive own entitlement must not activate access")
        store.apply(try info(subscriptionExpiry: future, grace: nil, verification: 2, productIdentifier: ownProducts[0]))
        expect(!store.hasAccess, "An unverified own entitlement must not activate access")
        print(AppEdition.authorSlug + ": own annual/supporter accepted; foreign, Steiner and unknown products rejected; grace and verification checked")
    }
}
'''


def sdk_files(requested: Path | None) -> tuple[Path, Path]:
    roots = [requested] if requested else [
        Path("/tmp/ga-author-app-builds/derived/friedrich-nietzsche"),
        Path("/tmp/ga-app-store-mac-archive-build"),
    ]
    for root in roots:
        archive = root / "Build/Intermediates.noindex/ArchiveIntermediates/GA Mac"
        layouts = [
            (root / "Build/Products/Debug", root / "Build/Products/Debug/RevenueCat.o"),
            (root / "Build/Products/Debug", root / "Build/Intermediates.noindex/RevenueCat.build/Debug/RevenueCat-t.build/Objects-normal/arm64/Binary/RevenueCat.o"),
            (archive / "BuildProductsPath/Release", archive / "IntermediateBuildFilesPath/RevenueCat.build/Release/RevenueCat-t.build/Objects-normal/arm64/Binary/RevenueCat.o"),
        ]
        for modules, object_file in layouts:
            if (modules / "RevenueCat.swiftmodule/arm64-apple-macos.swiftmodule").is_file() and object_file.is_file():
                return modules, object_file
    raise SystemExit("A built arm64 Mac RevenueCat module/object is required; build an author Mac app or pass --sdk-build-root.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-build-root", type=Path)
    options = parser.parse_args()
    modules, object_file = sdk_files(options.sdk_build_root)
    client = (SHARED / "AccessClient.swift").read_text()
    models = client.split("struct AccessClient: Sendable", 1)[0]
    models += "enum AccessClientError:" + client.split("enum AccessClientError:", 1)[1].split("\nenum AccessKeychain", 1)[0]
    store = (SHARED / "AccessStore.swift").read_text().replace("private(set) ", "").replace("private ", "")
    original_harness = (ROOT / "tools/access_store_harness.swift").read_text()
    doubles = original_harness.split("@main\nstruct AccessStoreChecks", 1)[0]
    fixture = original_harness.split("    @MainActor static func info", 1)[1].split("    @MainActor static func main", 1)[0]
    fixture = "    @MainActor static func info" + fixture
    fixture = fixture.replace("verification: Int = 1)", "verification: Int = 1, productIdentifier: String? = nil)")
    fixture = fixture.replace("let product = AccessOption.annual.productID!", "let product = productIdentifier ?? AccessOption.annual.productID!")
    fixture = fixture.replace('"entitlements": ["ga_access":', '"entitlements": [AppEdition.entitlementIdentifier:')
    harness = doubles + """@main struct AuthorAccessChecks {
    @MainActor static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        precondition(condition(), message)
    }
""" + fixture + MAIN
    authors = json.loads((ROOT / "editions/authors.json").read_text())["authors"]
    with tempfile.TemporaryDirectory(prefix="ga-author-access-check-") as scratch:
        scratch = Path(scratch)
        (scratch / "Models.swift").write_text(models)
        (scratch / "AccessStore.swift").write_text(store)
        (scratch / "Checks.swift").write_text(harness)
        binary = scratch / "checks"
        subprocess.run([
            "swiftc", "-parse-as-library", "-swift-version", "6", "-DDEBUG", "-target", "arm64-apple-macosx26.0",
            "-I", str(modules), str(SHARED / "AppEdition.swift"), str(scratch / "Models.swift"),
            str(scratch / "AccessStore.swift"), str(scratch / "Checks.swift"), str(object_file), "-o", str(binary),
        ], check=True)
        for index, author in enumerate(authors):
            bundle = scratch / (author["slug"] + ".app")
            executable = bundle / "Contents/MacOS/checks"
            executable.parent.mkdir(parents=True)
            shutil.copyfile(binary, executable)
            executable.chmod(0o755)
            (bundle / "Contents/Info.plist").write_bytes(plistlib.dumps(expanded_info(author)))
            foreign = authors[(index + 1) % len(authors)]["bundle_id"]
            subprocess.run([str(executable), foreign], check=True)
    print(f"Author subscription isolation checks passed for all {len(authors)} apps using the real RevenueCat SDK.")


if __name__ == "__main__":
    main()
