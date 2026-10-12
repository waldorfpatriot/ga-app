#!/usr/bin/env python3
"""Static publication and recovery fixtures; every remote surface is simulated."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch

import publish_author_library as publisher


class PublishAuthorLibraryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="author-publication-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.edition = self.root / "editions" / "fixture-author"
        self.report_path = self.edition / "library-deployment.json"
        self.author = {
            "slug": "fixture-author",
            "reader_root": str(self.root / "remote-reader"),
            "web_root": str(self.root / "remote-web"),
            "reader_base_url": "https://fixture.invalid/fixture-author-reader",
            "access_base_url": "https://fixture.invalid/fixture-author",
        }
        catalog = json.dumps({"works": [{"id": "fixture-one"}]}).encode()
        self.files = {
            "reader": {"catalog.json": catalog, "api/catalog/index.json": catalog,
                       "api/catalog/fixture-one/content": b"Fixture prose"},
            "web": {"index.html": b"fixture index", "privacy.html": b"fixture privacy",
                    "support.html": b"fixture support"},
        }
        self.expected = {}
        self.previous = {}
        for tree, files in self.files.items():
            for name, body in files.items():
                target = self.edition / "deploy" / tree / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
                self.expected[tree + "/" + name] = body
            inventory = {"files": {
                name: {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
                for name, body in files.items()
            }}
            self.expected[tree + "-inventory.json"] = json.dumps(inventory, sort_keys=True).encode()
            server = Path(self.author[tree + "_root"])
            old = server / "releases" / "old"
            old.mkdir(parents=True)
            (old / "old-file").write_text("old")
            # Both relative and absolute previous targets must be preserved.
            previous = "releases/old" if tree == "reader" else str(old)
            (server / "current").symlink_to(previous)
            self.previous[tree] = previous
        self.remote_calls = []
        self.http_calls = []
        self.output = io.StringIO()
        self.activation_completed = False
        self.rollback_completed = False
        self.mode = "success"

    def read_report(self):
        self.assertTrue(self.report_path.is_file(), "Recovery targets must be persisted before mutation")
        report = json.loads(self.report_path.read_text())
        self.assertEqual(report["previous"], self.previous)
        self.assertEqual(report["roots"], {tree: self.author[tree + "_root"] for tree in self.files})
        return report

    def current_targets(self):
        return {tree: os.readlink(Path(self.author[tree + "_root"]) / "current") for tree in self.files}

    def fake_remote(self, host, code):
        self.assertEqual(host, "fixture-host")
        self.remote_calls.append(code)
        activation = "activated=[]" in code
        rollback = "results={}" in code
        if "destination.mkdir" in code:
            self.assertEqual(self.read_report()["status"], "preparing")
        if activation:
            self.assertEqual(self.read_report()["status"], "activating")
        if rollback and self.mode == "rollback-unreachable":
            raise RuntimeError("fixture rollback SSH unreachable")
        original_replace = os.replace
        second_link_failed = False

        def replace(source, target):
            nonlocal second_link_failed
            if (self.mode == "second-link-failure" and activation and not second_link_failed
                    and Path(target) == Path(self.author["web_root"]) / "current"):
                second_link_failed = True
                raise OSError("fixture second link failure")
            return original_replace(source, target)

        # Run the exact remote Python against this test's temporary directories.
        # No subprocess, SSH connection or real author path is available here.
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch("os.replace", side_effect=replace):
            exec(compile(code, "fixture-remote", "exec"), {})
        result = json.loads(output.getvalue())
        if activation:
            self.activation_completed = True
            if self.mode in ("activation-response-lost", "rollback-unreachable", "rollback-response-lost"):
                raise RuntimeError("fixture SSH activation response lost")
        if rollback:
            self.rollback_completed = True
            if self.mode == "rollback-response-lost":
                raise RuntimeError("fixture rollback response lost")
        return result

    def fake_rsync(self, arguments, **kwargs):
        self.assertEqual(arguments[:2], ["rsync", "-az"])
        self.assertFalse(any(argument.startswith("--chmod") for argument in arguments))
        self.read_report()
        source = Path(arguments[-2])
        self.assertIn(source, [self.edition / "deploy" / tree for tree in self.files])
        host, destination = arguments[-1].split(":", 1)
        self.assertEqual(host, "fixture-host")
        target = Path(destination)
        self.assertTrue(target.is_relative_to(self.root))
        shutil.copytree(source, target, dirs_exist_ok=True)
        # Simulate restrictive upload permissions; activation must normalize them.
        target.chmod(0o700)
        for path in target.rglob("*"):
            path.chmod(0o700 if path.is_dir() else 0o600)
        if self.mode == "remote-file-mismatch" and source.name == "reader":
            (target / "catalog.json").write_bytes(b"bad fixture bytes")
        if self.mode == "concurrent-target-change" and source.name == "web":
            current = Path(self.author["web_root"]) / "current"
            current.unlink()
            other = current.parent / "releases" / "concurrent"
            other.mkdir()
            current.symlink_to(other)

    def fake_urlopen(self, request, **kwargs):
        url = request if isinstance(request, str) else request.full_url
        self.http_calls.append(url)
        if self.mode == "public-file-mismatch":
            return io.BytesIO(b"bad HTTP bytes")
        for tree in self.files:
            base = self.author["reader_base_url" if tree == "reader" else "access_base_url"]
            if url.startswith(base + "/"):
                relative = url[len(base) + 1:]
                if relative == "api/catalog":
                    if self.mode == "public-route-mismatch":
                        return io.BytesIO(b"bad route bytes")
                    relative = "api/catalog/index.json"
                return io.BytesIO((Path(self.author[tree + "_root"]) / "current" / relative).read_bytes())
        self.fail("Unexpected external HTTP request: " + url)

    def publish_fixture(self, mode="success"):
        self.mode = mode
        error = None
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(self.output))
            stack.enter_context(patch.object(publisher, "ROOT", self.root))
            stack.enter_context(patch.object(publisher, "load_authors", return_value=[self.author]))
            stack.enter_context(patch.object(publisher, "generate_files", return_value=self.expected))
            stack.enter_context(patch.object(publisher, "remote", side_effect=self.fake_remote))
            stack.enter_context(patch.object(publisher.subprocess, "run", side_effect=self.fake_rsync))
            stack.enter_context(patch.object(publisher.urllib.request, "urlopen", side_effect=self.fake_urlopen))
            try:
                publisher.publish("fixture-author", "fixture-host")
            except Exception as exception:
                error = exception
        report = self.read_report()
        if mode == "success":
            self.assertIsNone(error)
            self.assertEqual(report["status"], "published")
        else:
            self.assertIsNotNone(error, "The injected publication failure must propagate")
            self.assertEqual(report["status"], "failed")
        return report, error

    def assert_restored(self, report):
        self.assertEqual(self.current_targets(), self.previous)
        self.assertEqual(report["recovery"]["status"], "restored")
        self.assertTrue(all(tree["status"] in ("restored", "unchanged")
                            for tree in report["recovery"]["trees"].values()))

    def test_success_verifies_public_files_and_normalizes_release_permissions(self):
        report, _ = self.publish_fixture()
        self.assertEqual(report["verified_public_files"], 6)
        self.assertTrue(report["catalog_route_verified"])
        self.assertFalse(report["backend_changes"])
        self.assertEqual(self.current_targets(), report["releases"])
        self.assertEqual(len(self.http_calls), 7)
        for release in report["releases"].values():
            root = Path(release)
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o755)
            for path in root.rglob("*"):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755 if path.is_dir() else 0o644)

    def test_remote_hash_mismatch_preserves_both_previous_targets(self):
        report, error = self.publish_fixture("remote-file-mismatch")
        self.assertIsInstance(error, AssertionError)
        self.assert_restored(report)
        self.assertFalse(self.activation_completed)
        self.assertEqual(self.http_calls, [])

    def test_second_link_failure_restores_first_link(self):
        report, error = self.publish_fixture("second-link-failure")
        self.assertIsInstance(error, OSError)
        self.assert_restored(report)

    def test_public_file_hash_mismatch_restores_both_targets(self):
        report, error = self.publish_fixture("public-file-mismatch")
        self.assertIsInstance(error, ValueError)
        self.assert_restored(report)
        self.assertTrue(self.activation_completed)

    def test_public_catalog_route_mismatch_restores_both_targets(self):
        report, error = self.publish_fixture("public-route-mismatch")
        self.assertIsInstance(error, ValueError)
        self.assertIn("catalog route", str(error))
        self.assert_restored(report)

    def test_lost_activation_response_uses_previously_persisted_targets(self):
        report, error = self.publish_fixture("activation-response-lost")
        self.assertIn("activation response lost", str(error))
        self.assertTrue(self.activation_completed)
        self.assert_restored(report)
        self.assertEqual(self.http_calls, [])

    def test_unreachable_rollback_records_unknown_state_and_recovery_paths(self):
        report, _ = self.publish_fixture("rollback-unreachable")
        self.assertTrue(self.activation_completed)
        self.assertFalse(self.rollback_completed)
        self.assertEqual(self.current_targets(), report["releases"])
        self.assertEqual(report["recovery"]["status"], "unknown")
        self.assertIn("rollback SSH unreachable", report["recovery"]["error"])
        for previous in self.previous.values():
            self.assertIn(previous, self.output.getvalue())
        self.assertIn(str(self.report_path), self.output.getvalue())

    def test_lost_rollback_response_does_not_claim_confirmed_recovery(self):
        report, _ = self.publish_fixture("rollback-response-lost")
        self.assertTrue(self.rollback_completed)
        self.assertEqual(self.current_targets(), self.previous)
        self.assertEqual(report["recovery"]["status"], "unknown")
        self.assertIn("rollback response lost", report["recovery"]["error"])

    def test_concurrent_target_change_is_preserved_and_reported(self):
        report, error = self.publish_fixture("concurrent-target-change")
        self.assertIsInstance(error, AssertionError)
        self.assertEqual(self.current_targets()["reader"], self.previous["reader"])
        self.assertEqual(self.current_targets()["web"], str(self.root / "remote-web/releases/concurrent"))
        self.assertEqual(report["recovery"]["status"], "manual_review_required")
        self.assertEqual(report["recovery"]["trees"]["web"]["status"], "manual_review_required")
        self.assertIn("/releases/concurrent", report["recovery"]["trees"]["web"]["observed"])
        self.assertFalse(self.activation_completed)
        self.assertEqual(self.http_calls, [])


if __name__ == "__main__":
    unittest.main()
