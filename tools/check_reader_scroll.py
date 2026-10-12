#!/usr/bin/env python3
"""Run the native short-line scrolling regression on an installed QA simulator.

Run: python3 tools/check_reader_scroll.py --simulator-id <QA simulator UUID>
The GA app must already be installed. Only the GA 040a downloaded body is
temporarily replaced with the repository fixture; its original bytes are restored
after testing, including when Xcode relocates the app's data container. Reading
positions, notes, and other downloads are not reset.
"""

import argparse
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ID = "com.jonathankutscher.ga"
CACHE_PATH = Path("Library/Application Support/Gesamtausgabe/Content/ga-040a.json")
TEST = "GAUITests/GAReaderUITests/testReaderScrollsThroughShortLineChapter"


def cache_file(simulator_id):
    result = subprocess.run(
        ["xcrun", "simctl", "get_app_container", simulator_id, BUNDLE_ID, "data"],
        capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError("The GA app must be installed on the requested simulator.")
    return Path(result.stdout.strip()) / CACHE_PATH


def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(data)
        temporary_path = Path(temporary.name)
    try:
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulator-id", required=True, help="Dedicated QA simulator UUID")
    parser.add_argument("--derived-data-path", type=Path, help="Reuse an existing Xcode build directory")
    parser.add_argument("--output-dir", type=Path, help="Keep Xcode's log and result bundle here")
    parser.add_argument("--all-tests", action="store_true", help="Run the complete GA UI suite with the same fixture")
    args = parser.parse_args()

    output = args.output_dir.resolve() if args.output_dir else Path(tempfile.mkdtemp(prefix="ga-reader-scroll-"))
    output.mkdir(parents=True, exist_ok=True)
    log = output / "xcodebuild.log"
    result_bundle = output / "reader-scroll.xcresult"
    if log.exists() or result_bundle.exists():
        parser.error("The output directory must not already contain xcodebuild.log or reader-scroll.xcresult.")
    derived_data = (args.derived_data_path or output / "DerivedData").resolve()
    keep_output = args.output_dir is not None
    exit_code = 1
    try:
        original_cache = cache_file(args.simulator_id)
        original_bytes = original_cache.read_bytes() if original_cache.exists() else None
        with gzip.open(ROOT / "server/priv/content/ga-040a.json.gz", "rt", encoding="utf-8") as source:
            fixture = json.dumps(json.load(source)["passages"], ensure_ascii=False).encode("utf-8")
        try:
            write_atomic(original_cache, fixture)
            command = [
                "xcodebuild", "-project", str(ROOT / "apple/GA.xcodeproj"),
                "-scheme", "GA UI Tests",
                "-destination", f"platform=iOS Simulator,id={args.simulator_id}",
                "-derivedDataPath", str(derived_data),
                "-resultBundlePath", str(result_bundle),
                "-parallel-testing-enabled", "NO",
            ]
            if not args.all_tests:
                command.append(f"-only-testing:{TEST}")
            command.extend(["test", "CODE_SIGNING_ALLOWED=NO"])
            test_name = "GA UI suite" if args.all_tests else "short-line reader scrolling test"
            print(f"Running the {test_name} on the requested QA simulator.", flush=True)
            with log.open("w", encoding="utf-8") as output_log:
                exit_code = subprocess.run(command, cwd=ROOT, stdout=output_log, stderr=subprocess.STDOUT).returncode
        finally:
            # Installation can move the sandbox, so the original URL is stale.
            try:
                current_cache = cache_file(args.simulator_id)
                if original_bytes is None:
                    current_cache.unlink(missing_ok=True)
                else:
                    write_atomic(current_cache, original_bytes)
            except Exception:
                keep_output = True
                if original_bytes is not None:
                    recovery = output / "ga-040a-cache-backup.json"
                    write_atomic(recovery, original_bytes)
                    recovery.chmod(0o600)
                raise RuntimeError("Could not restore the GA 040a cache; any original bytes are preserved in the output directory.") from None
        if exit_code:
            keep_output = True
            print(f"Reader scrolling test failed. Log and result bundle: {output}", file=sys.stderr)
        else:
            print("Reader scrolling test passed; the GA 040a cache was restored.")
            if keep_output:
                print(f"Log and result bundle: {output}")
    except KeyboardInterrupt:
        keep_output = True
        exit_code = 130
        print(f"Reader scrolling check interrupted. Available diagnostics: {output}", file=sys.stderr)
    except Exception as error:
        keep_output = True
        print(f"Reader scrolling check failed: {error}\nAvailable diagnostics: {output}", file=sys.stderr)
        exit_code = 1
    finally:
        if not keep_output:
            shutil.rmtree(output)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
