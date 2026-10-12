#!/usr/bin/env python3
"""Run the native book-update regression with a disposable localhost server.

Use a dedicated QA simulator with GA already installed. The fixture temporarily
replaces only the GA 001 text cache and reader catalog, restores their exact
original bytes after the run, and never resets notes or the app's reading store.
The server deliberately fails the first update before serving current source
text. The UI then verifies retry, corrected text, and offline process relaunch.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ID = "com.jonathankutscher.ga"
PORT = 4178
TEST = "GAUITests/GAReaderUITests/testBookUpdateKeepsOldEditionUntilVerifiedAndPersistsOffline"
CACHE_ROOT = Path("Library/Application Support/Gesamtausgabe")
CACHE_FILES = (Path("Content/ga-001.json"), Path("reader-catalog.json"))
LEGACY_MARKER = "Veraltete QA-Textfassung."


def reader_safe(value):
    if isinstance(value, dict):
        return {key: reader_safe(child) for key, child in value.items() if key != "source_text"}
    if isinstance(value, list):
        return [reader_safe(child) for child in value]
    return value


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def app_cache_root(simulator_id):
    result = subprocess.run(["xcrun", "simctl", "get_app_container", simulator_id, BUNDLE_ID, "data"],
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("The GA app must already be installed on the dedicated QA simulator.")
    return Path(result.stdout.strip()) / CACHE_ROOT


def terminate_app(simulator_id):
    for bundle_id in (BUNDLE_ID + ".uitests.xctrunner", BUNDLE_ID):
        subprocess.run(["xcrun", "simctl", "terminate", simulator_id, bundle_id], capture_output=True)


def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(data)
        replacement = Path(temporary.name)
    try:
        replacement.replace(path)
    finally:
        replacement.unlink(missing_ok=True)


def fixture():
    with gzip.open(ROOT / "server/priv/content/ga-001.json.gz", "rt", encoding="utf-8") as stream:
        current = reader_safe(json.load(stream))
    current["content_completeness"] = "complete"
    current["content_path"] = "/api/catalog/ga-001/content"
    current["passage_count"] = len(current["passages"])
    body = encoded(current)
    revision = hashlib.sha256(body).hexdigest()
    catalog = json.loads((ROOT / "apple/GA/BundledCatalog/catalog.json").read_bytes())
    work = next(work for work in catalog["works"] if work["id"] == "ga-001")
    work["content_revision"] = revision
    work["content_updated_at"] = "2026-10-09T12:00:00Z"
    work["catalog_passage_count"] = len(current["passages"])
    work["passages"] = [{key: passage[key] for key in
                         ("id", "title", "ga_page", "source_label", "checksum", "metadata") if key in passage}
                        for passage in current["passages"]]
    legacy = copy.deepcopy(current["passages"])
    legacy[0]["text"] = LEGACY_MARKER + "\n\n" + legacy[0]["text"]
    legacy[0]["checksum"] = hashlib.sha256(legacy[0]["text"].encode("utf-8")).hexdigest()
    return catalog, current, body, revision, legacy


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, catalog, current, body, revision, simulator_id=None, legacy_bytes=None):
        super().__init__(("127.0.0.1", PORT), FixtureHandler)
        self.catalog = encoded(catalog)
        self.work = encoded({"work": next(work for work in catalog["works"] if work["id"] == "ga-001")})
        self.body = body
        self.current = current
        self.revision = revision
        self.requests = []
        self.content_attempts = 0
        self.lock = threading.Lock()
        self.simulator_id = simulator_id
        self.legacy_bytes = legacy_bytes
        self.legacy_preserved_at_retry = None


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") == "/api/catalog":
            return self.respond(200, self.server.catalog)
        if self.path.rstrip("/") == "/api/catalog/ga-001":
            return self.respond(200, self.server.work)
        if self.path == "/api/catalog/ga-001/content":
            with self.server.lock:
                self.server.content_attempts += 1
                attempt = self.server.content_attempts
            if attempt == 1:
                return self.respond(503, encoded({"error": "Deliberate update regression failure"}))
            if attempt == 2 and self.server.simulator_id:
                try:
                    path = app_cache_root(self.server.simulator_id) / CACHE_FILES[0]
                    preserved = path.read_bytes() == self.server.legacy_bytes
                    self.server.legacy_preserved_at_retry = {"preserved": preserved}
                except Exception as error:
                    self.server.legacy_preserved_at_retry = {"preserved": False, "error": str(error)}
            return self.respond(200, self.server.body)
        return self.respond(404, encoded({"error": "No unrelated fixture downloads"}))

    def respond(self, status, body):
        with self.server.lock:
            self.server.requests.append({"path": self.path, "status": status})
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-GA-Update-QA", "1")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def check_saved_edition(cache_root, current, revision):
    saved = json.loads((cache_root / CACHE_FILES[0]).read_bytes())
    if not isinstance(saved, dict) or saved.get("work_id") != "ga-001":
        raise RuntimeError("The verified update did not replace the legacy array with a GA 001 edition cache.")
    if saved.get("content_revision") != revision or saved.get("passage_count") != len(current["passages"]):
        raise RuntimeError("The saved update has the wrong verified revision or section count.")
    keys = ("id", "title", "ga_page", "source_label", "text")
    expected = [{key: passage.get(key) for key in keys} for passage in current["passages"]]
    actual = [{key: passage.get(key) for key in keys} for passage in saved["passages"]]
    if actual != expected:
        raise RuntimeError("The saved corrected text differs from the update server's current source edition.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulator-id", required=True, help="Dedicated QA simulator UUID")
    parser.add_argument("--derived-data-path", type=Path, help="Reuse an existing Xcode build directory")
    parser.add_argument("--output-dir", type=Path, help="Keep the Xcode log and result bundle")
    args = parser.parse_args()
    output = args.output_dir.resolve() if args.output_dir else Path(tempfile.mkdtemp(prefix="ga-book-update-"))
    output.mkdir(parents=True, exist_ok=True)
    log = output / "xcodebuild.log"
    result_bundle = output / "book-update.xcresult"
    if log.exists() or result_bundle.exists():
        parser.error("The output directory already contains a test log or result bundle.")
    derived_data = (args.derived_data_path or output / "DerivedData").resolve()
    keep_output = args.output_dir is not None
    exit_code = 1
    server = None
    server_thread = None
    originals = None
    try:
        catalog, current, body, revision, legacy = fixture()
        legacy_bytes = encoded(legacy)
        server = FixtureServer(catalog, current, body, revision, args.simulator_id, legacy_bytes)
        terminate_app(args.simulator_id)
        initial_root = app_cache_root(args.simulator_id)
        originals = {relative: (initial_root / relative).read_bytes() if (initial_root / relative).exists() else None
                     for relative in CACHE_FILES}
        try:
            write_atomic(initial_root / CACHE_FILES[0], legacy_bytes)
            write_atomic(initial_root / CACHE_FILES[1], encoded(catalog["works"]))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            command = ["xcodebuild", "-project", str(ROOT / "apple/GA.xcodeproj"), "-scheme", "GA UI Tests",
                       "-destination", f"platform=iOS Simulator,id={args.simulator_id}",
                       "-derivedDataPath", str(derived_data), "-resultBundlePath", str(result_bundle),
                       "-parallel-testing-enabled", "NO", "-test-timeouts-enabled", "YES",
                       "-default-test-execution-time-allowance", "240",
                       "-maximum-test-execution-time-allowance", "240",
                       f"-only-testing:{TEST}", "test", "CODE_SIGNING_ALLOWED=NO"]
            print("Running failed-update, retry, corrected-text and offline-relaunch checks on the QA simulator.", flush=True)
            with log.open("w", encoding="utf-8") as stream:
                exit_code = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                           timeout=480).returncode
            terminate_app(args.simulator_id)
            write_atomic(output / "fixture-requests.json", encoded(server.requests))
            write_atomic(output / "fixture-cache-check.json", encoded(server.legacy_preserved_at_retry))
            if exit_code == 0:
                statuses = [request["status"] for request in server.requests
                            if request["path"] == "/api/catalog/ga-001/content"]
                if statuses != [503, 200]:
                    raise RuntimeError(f"The expected failed update and successful retry were not exercised: {statuses}")
                if not server.legacy_preserved_at_retry or not server.legacy_preserved_at_retry["preserved"]:
                    raise RuntimeError("The failed update did not preserve the exact seeded legacy cache bytes before retry.")
                check_saved_edition(app_cache_root(args.simulator_id), current, revision)
        finally:
            terminate_app(args.simulator_id)
            try:
                restored_root = app_cache_root(args.simulator_id)
                for relative, original in originals.items():
                    if original is None:
                        (restored_root / relative).unlink(missing_ok=True)
                    else:
                        write_atomic(restored_root / relative, original)
                for relative, original in originals.items():
                    restored = (restored_root / relative).read_bytes() if (restored_root / relative).exists() else None
                    if restored != original:
                        raise RuntimeError("Original cache bytes did not restore exactly.")
            except Exception:
                keep_output = True
                for relative, original in originals.items():
                    if original is not None:
                        backup = output / (relative.name + ".backup")
                        write_atomic(backup, original)
                        backup.chmod(0o600)
                raise RuntimeError("Could not restore the two QA caches; original bytes are preserved in the output directory.") from None
        if exit_code:
            keep_output = True
            print(f"Book update UI test failed. Log and result bundle: {output}", file=sys.stderr)
        else:
            print("Book update checks passed: failed update preserved old text, retry saved current revision, "
                  "corrected text reopened offline; both original caches restored exactly.")
            if keep_output:
                print(f"Log and result bundle: {output}")
    except KeyboardInterrupt:
        keep_output = True
        exit_code = 130
        print(f"Book update check interrupted. Diagnostics: {output}", file=sys.stderr)
    except Exception as error:
        keep_output = True
        exit_code = 1
        print(f"Book update check failed: {error}\nDiagnostics: {output}", file=sys.stderr)
    finally:
        if server:
            if server_thread is not None and server_thread.is_alive():
                server.shutdown()
            server.server_close()
        if not keep_output:
            shutil.rmtree(output)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
