#!/usr/bin/env python3
"""Contract and privacy checks for isolated author delivery and host setup."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import generate_author_infrastructure as generator


class AuthorInfrastructureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.author = {"slug": "franz-kafka", "author_name": "Franz Kafka", "bundle_id": "com.jonathankutscher.franzkafka",
                       "service_name": "author-franz-kafka", "database": "author_franz_kafka", "port": 4148,
                       "reader_base_url": "https://fototausch.eu/franz-kafka-reader", "access_base_url": "https://fototausch.eu/franz-kafka"}
        self.manifest = self.root / "authors.json"
        self.manifest.write_text(json.dumps({"schema_version": 1, "authors": [self.author]}))
        self.author = generator.load_authors(self.manifest)[0]
        self.edition = self.root / self.author["slug"]
        (self.edition / "library").mkdir(parents=True)
        (self.edition / "library/content").mkdir()
        (self.edition / "web").mkdir()
        for name in ["index.html", "privacy.html", "support.html"]:
            (self.edition / "web" / name).write_text("<!doctype html><html lang=\"de\"><title>Franz Kafka Werke</title><body>Franz Kafka Werke</body></html>")
        text = "Als Gregor Samsa eines Morgens aus unruhigen Träumen erwachte."
        passage = {"id": "fk-001-p001", "title": "I", "ga_page": None, "source_label": "Die Verwandlung", "text": text,
                   "checksum": hashlib.sha256(text.encode()).hexdigest()}
        metadata = {key: value for key, value in passage.items() if key != "text"}
        self.catalog = {"schema_version": 1, "generated_at": "2026-10-10T00:00:00Z", "works": [{"id": "fk-001", "author": "Franz Kafka",
                        "title": "Die Verwandlung", "language": "de", "state": "published", "proofing_state": "needs_ai_sanity_check",
                        "content_completeness": "complete", "content_path": "/api/catalog/fk-001/content", "catalog_passage_count": 1,
                        "passages": [metadata]}]}
        self.payload = {"work_id": "fk-001", "content_completeness": "complete", "passage_count": 1, "passages": [passage]}
        self.save()

    def tearDown(self):
        self.temporary.cleanup()

    def save(self):
        (self.edition / "library/catalog.json").write_text(json.dumps(self.catalog, ensure_ascii=False))
        (self.edition / "library/content/fk-001.json").write_text(json.dumps(self.payload, ensure_ascii=False))

    def test_exact_download_contract_and_reproducible_output(self):
        first = generator.generate_files(self.author, self.edition)
        self.assertEqual(first, generator.generate_files(self.author, self.edition))
        content = first["reader/api/catalog/fk-001/content"]
        manifest = json.loads(first["reader/api/catalog/fk-001/manifest"])
        catalog = json.loads(first["reader/catalog.json"])
        bundle = manifest["bundles"][0]
        self.assertEqual(bundle["checksum"], hashlib.sha256(content).hexdigest())
        self.assertEqual(bundle["byte_size"], len(content))
        self.assertEqual(bundle["passages"], ["fk-001-p001"])
        self.assertEqual(catalog["works"][0]["content_revision"], bundle["checksum"])
        self.assertEqual(catalog["content_policy"]["author_scope"], "franz_kafka_original_text_only")
        self.assertEqual(first["reader/catalog.json"], first["reader/api/catalog/index.json"])
        compile(first["initialize-host.py"], "initialize-host.py", "exec")

    def test_author_isolation_in_deployment_files(self):
        files = generator.generate_files(self.author, self.edition)
        service = files["access.service"].decode()
        self.assertIn("User=ga-franz-kafka", service)
        self.assertIn("WorkingDirectory=/opt/author-franz-kafka/current", service)
        self.assertIn("+S 1:1 +SDcpu 1 +SDio 1 +A 1", service)
        self.assertIn("MemoryHigh=192M", service)
        self.assertIn("Environment=RELEASE_MODE=interactive", service)
        self.assertIn("Slice=author-apps.slice", service)
        self.assertIn("MemoryMax=1024M", files["author-apps.slice"].decode())
        installer = files["initialize-host.py"].decode()
        self.assertIn('cookie = destination / "releases/COOKIE"', installer)
        self.assertIn('private_write(cookie, secrets.token_urlsafe(48)', installer)
        self.assertIn('path.chmod(0o600)', installer)
        environment = files["environment.example"].decode()
        self.assertIn("PORT=4148", environment)
        self.assertIn("POOL_SIZE=2", environment)
        self.assertIn("localhost/author_franz_kafka", environment)
        nginx = files["nginx.conf"].decode()
        self.assertIn("location ^~ /franz-kafka/api/access/", nginx)
        self.assertIn("location = /franz-kafka/api/health", nginx)
        self.assertIn("location ^~ /franz-kafka/api/ { return 404; }", nginx)
        self.assertIn("root /var/lib/author-franz-kafka-reader/current", nginx)
        self.assertIn("location = /franz-kafka/privacy.html", nginx)
        self.assertIn("location = /franz-kafka/support.html", nginx)
        self.assertIn("root /var/lib/author-franz-kafka-web/current", nginx)
        self.assertIn("try_files /index.html =404;", nginx)
        backup = files["backup.sh"].decode()
        self.assertIn("pg_dump --format=custom author_franz_kafka", backup)
        self.assertIn("author-franz-kafka-backup-v1:", backup)
        self.assertNotIn("/etc/ga-access", backup)
        self.assertNotIn("rudolf-steiner", nginx)

    def test_stale_text_or_catalog_checksums_rejected(self):
        self.payload["passages"][0]["text"] += " geändert"
        self.save()
        with self.assertRaisesRegex(ValueError, "Stale text checksum"):
            generator.export_reader(self.author, self.edition)

    def test_catalog_cannot_advertise_missing_passages(self):
        self.catalog["works"][0]["catalog_passage_count"] = 2
        self.save()
        with self.assertRaisesRegex(ValueError, "passage mismatch"):
            generator.export_reader(self.author, self.edition)

    def test_private_source_rejected_recursively(self):
        self.payload["passages"][0]["metadata"] = {"annotations": [{"source_text": "private editorial input"}]}
        self.save()
        with self.assertRaisesRegex(ValueError, "Private data"):
            generator.export_reader(self.author, self.edition)

    def test_partial_work_cannot_be_advertised_complete(self):
        self.payload["completeness"] = "excerpt"
        self.save()
        with self.assertRaisesRegex(ValueError, "Incomplete reader bundle"):
            generator.export_reader(self.author, self.edition)

    def test_wrong_author_is_rejected(self):
        self.catalog["works"][0]["author"] = "Rudolf Steiner"
        self.save()
        with self.assertRaisesRegex(ValueError, "author mismatch"):
            generator.export_reader(self.author, self.edition)

    def test_declared_original_languages_allow_latin_but_reject_undeclared_text(self):
        self.author.update(language="de", original_languages=["de", "la", "grc"])
        self.catalog["works"][0]["language"] = "la"
        self.payload["language"] = "la"
        self.save()
        files, _, _ = generator.export_reader(self.author, self.edition)
        self.assertEqual(json.loads(files["api/catalog/fk-001/content"])["language"], "la")
        self.author.pop("original_languages")
        with self.assertRaisesRegex(ValueError, "original-language"):
            generator.export_reader(self.author, self.edition)

    def test_catalog_and_content_languages_must_agree(self):
        self.author.update(language="de", original_languages=["de", "la"])
        self.payload["language"] = "la"
        self.save()
        with self.assertRaisesRegex(ValueError, "language mismatch"):
            generator.export_reader(self.author, self.edition)

    def test_work_date_and_download_bytes_survive_collection_expansion(self):
        self.catalog["works"][0]["content_updated_at"] = self.catalog["generated_at"]
        self.save()
        before, _, _ = generator.export_reader(self.author, self.edition)
        self.catalog["generated_at"] = "2026-10-11T09:00:00Z"
        self.save()
        after, _, _ = generator.export_reader(self.author, self.edition)
        self.assertEqual(before["api/catalog/fk-001/content"], after["api/catalog/fk-001/content"])
        self.assertEqual(before["api/catalog/fk-001/manifest"], after["api/catalog/fk-001/manifest"])
        self.assertEqual(json.loads(after["catalog.json"])["works"][0]["content_updated_at"], "2026-10-10T00:00:00Z")
        self.catalog["works"][0]["content_updated_at"] = "2026-02-30T00:00:00Z"
        self.save()
        with self.assertRaisesRegex(ValueError, "timestamp"):
            generator.export_reader(self.author, self.edition)

    def test_author_original_languages_are_validated(self):
        self.author.update(language="de", original_languages=["de", "de"])
        self.manifest.write_text(json.dumps({"schema_version": 1, "authors": [self.author]}))
        with self.assertRaisesRegex(ValueError, "original_languages"):
            generator.load_authors(self.manifest)

    def test_snapshot_does_not_follow_content_symlinks(self):
        path = self.edition / "library/content/fk-001.json"
        original = path.read_text()
        path.unlink()
        outside = self.root / "outside.json"
        outside.write_text(original)
        path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "Symlink"):
            generator.export_reader(self.author, self.edition)

    def test_cross_app_identity_and_steiner_port_rejected(self):
        duplicate = copy.deepcopy(self.author)
        self.manifest.write_text(json.dumps({"schema_version": 1, "authors": [self.author, duplicate]}))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            generator.load_authors(self.manifest)
        duplicate["port"] = 4131
        self.manifest.write_text(json.dumps({"schema_version": 1, "authors": [duplicate]}))
        with self.assertRaisesRegex(ValueError, "isolated port"):
            generator.load_authors(self.manifest)

    def test_dry_run_writes_nothing_and_check_detects_withdrawn_downloads(self):
        destination = self.edition / "deploy"
        files = generator.generate_files(self.author, self.edition)
        generator.write_files(destination, files, dry_run=True)
        self.assertFalse(destination.exists())
        generator.write_files(destination, files)
        generator.write_files(destination, files, check=True)
        (destination / "reader/withdrawn-content.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "stale"):
            generator.write_files(destination, files, check=True)
        generator.write_files(destination, files)
        self.assertFalse((destination / "reader/withdrawn-content.json").exists())

    def test_host_private_command_failure_cannot_echo_secret(self):
        files = generator.generate_files(self.author, self.edition)
        scope = {"__name__": "host_installer_test", "__file__": str(self.edition / "deploy/initialize-host.py")}
        exec(compile(files["initialize-host.py"], "initialize-host.py", "exec"), scope)
        with patch.object(scope["subprocess"], "run", return_value=SimpleNamespace(returncode=1, stderr="PASSWORD 'sensitive'", stdout="")):
            with self.assertRaises(RuntimeError) as error:
                scope["run"](["psql"], input="CREATE ROLE x PASSWORD 'sensitive';", private=True)
        self.assertNotIn("sensitive", str(error.exception))
        self.assertIn("private command failed", str(error.exception))

    def test_regeneration_preserves_unexpected_operational_files(self):
        destination = self.edition / "deploy"
        files = generator.generate_files(self.author, self.edition)
        generator.write_files(destination, files)
        protected = destination / "environment"
        protected.write_text("SECRET_KEY_BASE=private-runtime-key\n")
        with self.assertRaisesRegex(ValueError, "Unexpected operational files"):
            generator.write_files(destination, files)
        self.assertTrue(protected.exists())


if __name__ == "__main__":
    unittest.main()
