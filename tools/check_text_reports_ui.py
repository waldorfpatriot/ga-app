#!/usr/bin/env python3
"""Verify native text-report cancellation, failed receipt and idempotent retry.

The disposable localhost service keeps the test reports local. Use a dedicated
QA simulator; the UI purchases a verified local
StoreKit test entitlement for reading and the service grants no free access.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import uuid


ROOT = Path(__file__).resolve().parents[1]
TEST = "GAUITests/GAReaderUITests/testSelectedTextReportCancelFailureRetryAndConfirmation"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 4184), FixtureHandler)
        # Stable fixture credentials let repeat runs reuse this localhost-only
        # Keychain identity without deleting unrelated app data.
        self.identity = {key: str(uuid.uuid5(uuid.NAMESPACE_URL, "ga-text-report-qa/" + key)) for key in
            ("installation_id", "access_token", "recovery_code", "revenuecat_app_user_id")}
        self.reports = []
        self.authenticated = []
        self.lock = threading.Lock()


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/qa/state":
            with self.server.lock:
                return self.respond(200, {"reports": self.server.reports})
        if self.path == "/api/access/statistics":
            return self.respond(200, {"window_days": 90, "total": 0, "options": {}})
        if self.path == "/api/access/status":
            return self.respond(200, {"status": "none", "active": False,
                "revenuecat_app_user_id": self.server.identity["revenuecat_app_user_id"]})
        return self.respond(404, {"error": "Unknown fixture endpoint"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/api/access/installations":
            return self.respond(201, self.server.identity)
        if self.path == "/api/access/selections":
            return self.respond(201, {"status": "recorded"})
        if self.path != "/api/access/text-reports":
            return self.respond(404, {"error": "Unknown fixture endpoint"})
        authenticated = self.headers.get("Authorization") == "Bearer " + self.server.identity["access_token"]
        with self.server.lock:
            self.server.reports.append(body)
            self.server.authenticated.append(authenticated)
            attempt = len(self.server.reports)
        if not authenticated:
            return self.respond(401, {"error": "Unexpected installation credential"})
        # The server receives the first request but its confirmation is lost.
        # The second identical request confirms the existing logical report.
        if attempt == 1:
            return self.respond(503, {"error": "Deliberately unconfirmed receipt"})
        return self.respond(200, {"status": "received", "report_id": body["report_id"]})

    def respond(self, status, value):
        body = encoded(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-GA-Text-Report-QA", "1")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulator-id", required=True)
    parser.add_argument("--derived-data-path", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output = args.output_dir.resolve() if args.output_dir else Path(tempfile.mkdtemp(prefix="ga-text-reports-"))
    output.mkdir(parents=True, exist_ok=True)
    log = output / "xcodebuild.log"
    result = output / "text-reports.xcresult"
    if log.exists() or result.exists():
        parser.error("The output directory already contains test results.")
    derived = (args.derived_data_path or output / "DerivedData").resolve()
    server = FixtureServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        command = ["xcodebuild", "-project", str(ROOT / "apple/GA.xcodeproj"), "-scheme", "GA UI Tests",
            "-destination", f"platform=iOS Simulator,id={args.simulator_id}",
            "-derivedDataPath", str(derived), "-resultBundlePath", str(result),
            "-parallel-testing-enabled", "NO", "-collect-test-diagnostics", "never", "-test-timeouts-enabled", "YES",
            "-default-test-execution-time-allowance", "240", "-maximum-test-execution-time-allowance", "240",
            # Keep the normal Simulator signature: the real iOS Keychain
            # requires the app's signed entitlement even in a QA build.
            f"-only-testing:{TEST}", "test"]
        print("Verifying selected-text reporting on the QA simulator.", flush=True)
        with log.open("w", encoding="utf-8") as stream:
            completed = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=600)
        if completed.returncode:
            print(f"UI verification failed; diagnostics: {log}")
            raise SystemExit(completed.returncode)
        if len(server.reports) != 2 or server.reports[0] != server.reports[1] or not all(server.authenticated):
            raise RuntimeError("The native UI did not retry one identical authenticated report.")
        print(f"PASS: cancelled without sending, retained failed input, retried identical report, confirmed and closed. {result}")
    finally:
        (output / "fixture-check.json").write_bytes(encoded({
            "report_attempts": len(server.reports), "authenticated": server.authenticated,
            "identical_retry": len(server.reports) == 2 and server.reports[0] == server.reports[1]}))
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    main()
