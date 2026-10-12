#!/usr/bin/env python3
"""Integrity, isolation and original-division checks for the author libraries."""

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import import_author_library as importer


class TranscriptTests(unittest.TestCase):
    def test_soft_wraps_do_not_merge_paragraphs(self):
        self.assertEqual(importer.normalize_prose(" One\n two.\r\n\r\n Three\xa0four. "),
                         "One two.\n\nThree four.")

    def test_both_archive_boundaries_are_required(self):
        start = "*** START OF THE PROJECT GUTENBERG EBOOK EXAMPLE ***"
        end = "*** END OF THE PROJECT GUTENBERG EBOOK EXAMPLE ***"
        self.assertEqual(importer.gutenberg_body(start + "\nOriginal.\n" + end), "Original.")
        for malformed in (start + "\nOriginal.", "Original.\n" + end, end + start):
            with self.assertRaises(ValueError):
                importer.gutenberg_body(malformed)
        with self.assertRaises(ValueError):
            importer.gutenberg_body("Posted with permission\n" + start + "Text" + end)

    def test_reader_offsets_use_utf16(self):
        blocks = importer.blocks_for("A😀\n\nB", heading_indexes={0})
        self.assertEqual(blocks, [
            {"kind": "heading", "start_offset": 0, "end_offset": 3},
            {"kind": "prose", "start_offset": 5, "end_offset": 6},
        ])

    def test_mixed_prose_and_verse_preserve_utf16_ranges_and_heading_precedence(self):
        text = "Heading\n\nA😀\nB\n\nProse."
        blocks = importer.blocks_for(text, heading_indexes={0}, verse_indexes={0, 1})
        self.assertEqual(blocks, [
            {"kind": "heading", "start_offset": 0, "end_offset": 7},
            {"kind": "verse", "start_offset": 9, "end_offset": 14},
            {"kind": "prose", "start_offset": 16, "end_offset": 22},
        ])
        self.assertEqual([b["kind"] for b in importer.blocks_for(text, verse=True, heading_indexes={0})],
                         ["heading", "verse", "verse"])
        self.assertEqual(importer.blocks_for(text), importer.blocks_for(text, verse_indexes=[]))

    def test_large_paragraph_is_kept_whole(self):
        source = "a" * 25000 + "\n\n" + "b" * 5000
        parts = importer.split_transcript(source)
        self.assertEqual(len(parts), 2)
        self.assertEqual("\n\n".join(parts), source)

    def test_original_chapter_and_subparts_keep_every_character(self):
        source = "First chapter\n\n" + "a" * 20000 + "\n\n" + "b" * 5000 + "\n\nSecond chapter\n\nEnd."
        entry = {"work_id": "test", "title": "Book", "heading_paragraphs": [0, 3],
                 "sections": [{"start_paragraph": 0, "title": "First chapter", "first_paragraph": "First chapter"},
                              {"start_paragraph": 3, "title": "Second chapter", "first_paragraph": "Second chapter"}]}
        parts = list(importer.section_parts(source, entry))
        self.assertEqual([p[0] for p in parts], ["First chapter · 1", "First chapter · 2", "Second chapter"])
        self.assertEqual("\n\n".join(p[1] for p in parts), source)
        self.assertEqual([p[2] for p in parts], [{0}, set(), {0}])

    def test_section_anchor_and_order_fail_closed(self):
        for sections in ([{"start_paragraph": 1, "title": "B"}],
                         [{"start_paragraph": 0, "title": "A"}, {"start_paragraph": 0, "title": "B"}],
                         [{"start_paragraph": 0, "title": "A", "first_paragraph": "Wrong"}]):
            with self.assertRaises(ValueError):
                list(importer.section_parts("A\n\nB", {"work_id": "test", "title": "Book", "sections": sections}))


class SourceManifestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.edition = self.root / "test-author"
        (self.edition / "library/sources").mkdir(parents=True)
        self.manifest = {
            "author": {"slug": "test-author", "name": "Test Author", "language": "de",
                       "original_languages": ["de", "la", "grc"]},
            "works": [],
        }
        for index, (language, source) in enumerate((
            ("de", "Ein kurzer Text."),
            ("la", "De fontibus Diogenis.\n\nConclusio."),
            ("grc", "Ἑλληνικά.\n\nΤέλος."),
        ), start=1):
            work_id = f"test-{index:03d}"
            relative = f"library/sources/{work_id}.txt"
            (self.edition / relative).write_text(source + "\n", encoding="utf-8")
            self.manifest["works"].append({
                "work_id": work_id, "work_label": f"T {index:03d}", "title": f"Work {index}",
                "language": language, "is_original_language": True, "original_publication_year": 1870,
                "priority": index, "source_label": "Historical original text",
                "normalized_source_path": relative, "normalized_text_sha256": importer.sha256(source),
                "minimum_characters": len(source), "first_text_anchor": source[:8], "last_text_anchor": source[-8:],
                "edition_note": "Original text", "quality_note": "Collation pending",
                "rights": {"status": "public_domain_original"},
            })
        self.save()

    def tearDown(self):
        self.temporary.cleanup()

    def save(self):
        (self.edition / "source-manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_declared_original_languages_and_short_works_are_preserved(self):
        importer.build_edition("test-author", editions_root=self.root)
        catalog = json.loads((self.edition / "library/catalog.json").read_text())
        self.assertEqual([work["language"] for work in catalog["works"]], ["de", "la", "grc"])
        for work in catalog["works"]:
            payload = json.loads((self.edition / "library/content" / (work["id"] + ".json")).read_text())
            self.assertEqual(payload["language"], work["language"])
        importer.build_edition("test-author", check=True, editions_root=self.root)

    def test_collected_work_titles_are_searchable_without_changing_author_text(self):
        self.manifest["works"][0]["search_terms"] = ["Der Antichrist", "Nietzsche contra Wagner"]
        self.save()
        importer.build_edition("test-author", editions_root=self.root)
        catalog = json.loads((self.edition / "library/catalog.json").read_text())
        self.assertIn("Der Antichrist", catalog["works"][0]["tags"])
        payload = json.loads((self.edition / "library/content/test-001.json").read_text())
        self.assertEqual("\n\n".join(p["text"] for p in payload["passages"]), "Ein kurzer Text.")

    def test_global_verse_indexes_cross_chapters_and_bounded_subparts(self):
        source = "First heading\n\n" + "a" * 20000 + "\n\n" + "b" * 5000 + "\n\nFirst line\nSecond line\n\nSecond heading\n\nFinal verse."
        author = self.manifest["author"]
        entry = dict(self.manifest["works"][0], heading_paragraphs=[0, 4], verse_paragraphs=[0, 3, 5],
                     sections=[{"start_paragraph": 0, "title": "First chapter"},
                               {"start_paragraph": 4, "title": "Second chapter"}])
        work, payload = importer.package_work(author, entry, source)
        self.assertEqual(payload["passage_count"], 3)
        self.assertEqual([[b["kind"] for b in p["metadata"]["reading_blocks"]] for p in payload["passages"]],
                         [["heading", "prose"], ["prose", "verse"], ["heading", "verse"]])
        self.assertEqual("\n\n".join(p["text"] for p in payload["passages"]), source)
        self.assertEqual(work["passages"][1]["metadata"], payload["passages"][1]["metadata"])
        entry["verse"] = True
        _, entirely_verse = importer.package_work(author, entry, source)
        self.assertTrue(all(b["kind"] in {"heading", "verse"}
                            for p in entirely_verse["passages"] for b in p["metadata"]["reading_blocks"]))

    def test_empty_verse_indexes_do_not_change_legacy_payload_bytes(self):
        _, author, entry, source = next(importer.load_sources("test-author", self.root))
        work, payload = importer.package_work(author, entry, source)
        with_empty = dict(entry, verse_paragraphs=[])
        same_work, same_payload = importer.package_work(author, with_empty, source)
        self.assertEqual(importer.json_bytes(payload), importer.json_bytes(same_payload))
        self.assertEqual(importer.json_bytes(work), importer.json_bytes(same_work))

    def test_invalid_global_verse_indexes_are_rejected(self):
        _, author, entry, source = next(importer.load_sources("test-author", self.root))
        for indexes in (None, "0", [True], [-1], [1], [0, 0], ["0"]):
            with self.subTest(indexes=indexes), self.assertRaisesRegex(ValueError, "verse paragraph indexes"):
                importer.package_work(author, dict(entry, verse_paragraphs=indexes), source)

    def test_undeclared_languages_and_translations_are_rejected(self):
        self.manifest["author"].pop("original_languages")
        self.save()
        with self.assertRaisesRegex(ValueError, "Translation or wrong language"):
            list(importer.load_sources("test-author", self.root))
        self.manifest["author"]["original_languages"] = ["de", "la", "grc"]
        self.manifest["works"][1]["is_original_language"] = False
        self.save()
        with self.assertRaisesRegex(ValueError, "Translation or wrong language"):
            list(importer.load_sources("test-author", self.root))

    def test_original_language_declaration_is_validated(self):
        for languages in ("de", [], ["de", "de"], ["la"], ["de", 1], ["de", ""]):
            with self.subTest(languages=languages):
                self.manifest["author"]["original_languages"] = languages
                self.save()
                with self.assertRaisesRegex(ValueError, "original_languages"):
                    list(importer.load_sources("test-author", self.root))

    def test_manifest_defaults_and_work_overrides_keep_existing_revisions(self):
        self.manifest.update(generated_at="2026-10-11T09:00:00Z", collection_tag="collected-works")
        self.manifest["works"][0].update(content_updated_at=importer.UPDATED_AT, collection_tag="starter-collection")
        self.save()
        importer.build_edition("test-author", editions_root=self.root)
        catalog = json.loads((self.edition / "library/catalog.json").read_text())
        self.assertEqual(catalog["generated_at"], self.manifest["generated_at"])
        first, second = catalog["works"][:2]
        self.assertEqual(first["content_updated_at"], importer.UPDATED_AT)
        self.assertIn("starter-collection", first["tags"])
        self.assertEqual(second["content_updated_at"], self.manifest["generated_at"])
        self.assertIn("collected-works", second["tags"])
        before = (self.edition / "library/content/test-001.json").read_bytes()
        self.manifest["generated_at"] = "2026-10-12T09:00:00Z"
        self.manifest["content_updated_at"] = "2026-10-11T12:00:00Z"
        self.save()
        importer.build_edition("test-author", editions_root=self.root)
        after = (self.edition / "library/content/test-001.json").read_bytes()
        self.assertEqual(before, after)
        updated = json.loads((self.edition / "library/catalog.json").read_text())["works"]
        self.assertEqual(updated[0]["content_updated_at"], importer.UPDATED_AT)
        self.assertEqual(updated[1]["content_updated_at"], self.manifest["content_updated_at"])

    def test_absent_optional_metadata_keeps_legacy_defaults(self):
        _, author, entry, source = next(importer.load_sources("test-author", self.root))
        work, _ = importer.package_work(author, entry, source)
        self.assertEqual(work["content_updated_at"], importer.UPDATED_AT)
        self.assertEqual(work["tags"], ["original-language", "public-domain", "starter-collection", "test-author"])

    def test_invalid_dates_minima_and_collection_tags_are_rejected(self):
        for invalid in ("2026-10-11", "2026-02-30T00:00:00Z", None):
            with self.subTest(timestamp=invalid):
                self.manifest["generated_at"] = invalid
                self.save()
                with self.assertRaisesRegex(ValueError, "timestamp"):
                    list(importer.load_sources("test-author", self.root))
        self.manifest.pop("generated_at")
        for minimum in (0, -1, True, "16"):
            with self.subTest(minimum=minimum):
                self.manifest["works"][0]["minimum_characters"] = minimum
                self.save()
                with self.assertRaisesRegex(ValueError, "minimum"):
                    list(importer.load_sources("test-author", self.root))
        self.manifest["works"][0]["minimum_characters"] = len("Ein kurzer Text.")
        self.manifest["collection_tag"] = "wrong collection"
        self.save()
        _, author, entry, source = next(importer.load_sources("test-author", self.root))
        with self.assertRaisesRegex(ValueError, "collection tag"):
            importer.package_work(author, entry, source)


class RealLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = [row for slug in importer.EDITION_SLUGS for row in importer.load_sources(slug)]

    def test_all_eleven_authors_have_real_original_work(self):
        root = json.loads((importer.ROOT / "editions" / "authors.json").read_text())
        expected = {a["slug"]: (a["author_name"], a["language"]) for a in root["authors"]}
        declared_ids = {
            entry["work_id"]
            for author in root["authors"]
            for entry in json.loads((importer.ROOT / "editions" / author["slug"] / "source-manifest.json").read_text())["works"]
        }
        actual = {}
        ids = set()
        for edition, author, entry, source in self.rows:
            actual[author["slug"]] = (author["name"], author["language"])
            self.assertNotIn(entry["work_id"], ids)
            ids.add(entry["work_id"])
            self.assertNotIn("ga", entry["work_id"].split("-")[:1])
            self.assertTrue(entry["is_original_language"])
            self.assertEqual(entry["rights"]["status"], "public_domain_original")
            self.assertTrue(entry["source_url"].startswith(("https://", "http://")))
            self.assertIn(entry["language"], importer.original_languages(author))
            self.assertGreater(entry["minimum_characters"], 0)
            self.assertGreaterEqual(len(source), entry["minimum_characters"])
            self.assertTrue(source.strip())
        self.assertEqual(expected, actual)
        self.assertEqual(ids, declared_ids)

    def test_every_payload_reconstructs_entire_checked_transcript(self):
        for edition, author, entry, source in self.rows:
            work, payload = importer.package_work(author, entry, source)
            actual = json.loads((edition / "library" / "content" / f'{entry["work_id"]}.json').read_text())
            self.assertEqual(payload, actual)
            self.assertEqual("\n\n".join(p["text"] for p in actual["passages"]), source)
            self.assertEqual(actual["content_completeness"], "complete")
            self.assertEqual(work["catalog_passage_count"], actual["passage_count"])
            data = (edition / "library" / "content" / f'{entry["work_id"]}.json').read_bytes()
            self.assertEqual(work["content_revision"], hashlib.sha256(data).hexdigest())
            for p in actual["passages"]:
                self.assertEqual(p["checksum"], importer.sha256(p["text"]))
                self.assertNotIn("source_text", p)
                length = importer.utf16_length(p["text"])
                self.assertTrue(all(0 <= b["start_offset"] < b["end_offset"] <= length
                                    for b in p["metadata"]["reading_blocks"]))

    def test_source_divisions_have_expected_book_counts(self):
        entries = {e["work_id"]: e for _, _, e, _ in self.rows}
        for wid, count in (("austen-001", 61), ("austen-002", 50), ("doyle-001", 12),
                           ("doyle-002", 15), ("may-002", 12), ("kafka-001", 3)):
            self.assertEqual(len(entries[wid]["sections"]), count, wid)
        self.assertIn("CHAPTER LXI.", entries["austen-001"]["sections"][-1]["title"])
        self.assertIn("Chapter 15.", entries["doyle-002"]["sections"][-1]["title"])
        self.assertIn("[X.]", entries["swedenborg-001"]["sections"][-1]["title"])

    def test_archive_wrappers_and_editorial_advertising_are_absent(self):
        prohibited = ("PROJECT GUTENBERG", "Project Gutenberg", "504 Metropolitan Building",
                      "Books Recommended to Inquirers", "The policy of this Lodge is independent",
                      "Комментарии:", "PraHFATIUNXULA Editoris", "INDEX LOCORUM SCRIPTURAE")
        for _, _, entry, source in self.rows:
            for marker in prohibited:
                self.assertNotIn(marker, source, entry["work_id"])

    def test_scan_limitations_and_complete_boundaries_are_recorded(self):
        entries = {e["work_id"]: e for _, _, e, _ in self.rows}
        self.assertEqual(entries["montessori-001"]["source_page_numbers"], [3, 4, 5, 6, 7])
        self.assertIn("terminal rule", entries["montessori-001"]["boundary_evidence"])
        self.assertEqual(entries["montessori-002"]["source_page_numbers"], list(range(169, 183)))
        for wid in ("montessori-001", "montessori-002", "swedenborg-001"):
            self.assertIn("OCR", entries[wid]["quality_note"])
        swed = next(s for _, _, e, s in self.rows if e["work_id"] == "swedenborg-001")
        self.assertIn("72. Verum enim vero", swed)
        self.assertTrue(swed.endswith("usque mala ut peccata fugerunt."))

    def test_rebuild_is_deterministic_for_all_authors(self):
        for slug in importer.EDITION_SLUGS:
            importer.build_edition(slug, check=True)

    def test_translation_and_source_mutation_are_rejected(self):
        edition, author, entry, source = self.rows[0]
        manifest = json.loads((edition / "source-manifest.json").read_text())
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            target = base / author["slug"]
            target.mkdir()
            source_path = target / entry["normalized_source_path"]
            source_path.parent.mkdir(parents=True)
            source_path.write_text(source + "\n")
            local = copy.deepcopy(manifest)
            local["works"] = [copy.deepcopy(entry)]
            path = target / "source-manifest.json"
            local["works"][0]["is_original_language"] = False
            path.write_text(json.dumps(local))
            with self.assertRaisesRegex(ValueError, "Translation"):
                list(importer.load_sources(author["slug"], base))
            local["works"][0]["is_original_language"] = True
            path.write_text(json.dumps(local))
            source_path.write_text(source + "Changed.\n")
            with self.assertRaisesRegex(ValueError, "checksum"):
                list(importer.load_sources(author["slug"], base))


if __name__ == "__main__":
    unittest.main()
