"""Regression checks for literary content previously lost by archive cleanup."""
import hashlib
import json
from pathlib import Path
import unittest


EDITION = Path(__file__).resolve().parents[1] / "editions/friedrich-nietzsche"


class NietzscheTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = {e["work_id"]: e for e in json.loads((EDITION / "source-manifest.json").read_text())["works"]}

    def source(self, number):
        return (EDITION / self.entries[f"nietzsche-{number:03d}"]["normalized_source_path"]).read_text().rstrip("\n")

    def test_ecce_homo_keeps_birthday_prelude_and_final_author_words(self):
        text = self.source(6)
        self.assertLess(text.index("An diesem vollkommnen Tage"), text.index("Warum ich so weise bin."))
        self.assertNotIn("\n\nInhalt\n\n", text)
        self.assertTrue(text.endswith("Dionysos gegen den Gekreuzigten..."))

    def test_birth_of_tragedy_keeps_all_twenty_five_chapters_after_preface(self):
        sections = self.entries["nietzsche-003"]["sections"]
        titles = [s["title"] for s in sections]
        self.assertEqual([title for title in titles if title[:-1].isdigit()], [f"{i}." for i in range(1, 26)])
        self.assertGreater(titles.index("1."), titles.index("Vorwort an Richard Wagner."))

    def test_closing_poem_is_lineated_and_marked_as_verse(self):
        paragraphs = self.source(4).split("\n\n")
        entry = self.entries["nietzsche-004"]
        stanza = next(i for i, p in enumerate(paragraphs) if "Lernt aus diesem Narrenbuche," in p)
        self.assertIn('\nWie Vernunft kommt - "zur Vernunft"!', paragraphs[stanza])
        self.assertIn(stanza, entry["verse_paragraphs"])

    def test_existing_passage_payloads_keep_annotation_identity(self):
        expected = {
            1: "e62e1a02bbd1bf51d0164c49e56271fd6768b7cb4ff47fde9b748e9ef1a6d1d2",
            2: "449fa3ac3394bcb83a77ecb91a2a98d60a0d955abde5aa7ccee16a663972aafc",
        }
        for number, checksum in expected.items():
            with self.subTest(work=number):
                body = (EDITION / f"library/content/nietzsche-{number:03d}.json").read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(), checksum)


if __name__ == "__main__":
    unittest.main()
