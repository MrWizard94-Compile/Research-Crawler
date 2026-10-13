"""Offline behavioral contracts for source parsing and lossless ingestion text."""

import unittest

import crawl


class ChunkTextTests(unittest.TestCase):
    def test_preserves_paragraph_separators_and_unicode(self) -> None:
        text = "ééééé\n\nabcabcabcabc\n\n🚀 end"
        chunks = crawl.chunk_text(text, 7)
        self.assertEqual(text, "".join(chunks))
        self.assertTrue(all(len(chunk.encode("utf-8")) <= 7 for chunk in chunks))
        self.assertGreater(len(chunks), 1)

    def test_preserves_text_when_it_fits(self) -> None:
        self.assertEqual(["a\n\nb"], crawl.chunk_text("a\n\nb", 4))
        self.assertEqual([""], crawl.chunk_text("", 1))

    def test_rejects_unrepresentable_byte_caps(self) -> None:
        with self.assertRaises(ValueError):
            crawl.chunk_text("x", 0)
        with self.assertRaises(ValueError):
            crawl.chunk_text("🚀", 3)

    def test_varied_lengths_remain_lossless_and_bounded(self) -> None:
        texts = ["alpha\n\nβeta\n\n" + "🌍" * 11 + "\n\nomega", "\n\nstart\n\n", "\n\n\n\n"]
        for text in texts:
            for max_bytes in range(4, 30):
                with self.subTest(text=text, max_bytes=max_bytes):
                    chunks = crawl.chunk_text(text, max_bytes)
                    self.assertEqual(text, "".join(chunks))
                    self.assertTrue(all(chunk for chunk in chunks))
                    self.assertTrue(all(len(chunk.encode("utf-8")) <= max_bytes for chunk in chunks))


class SourceParsingTests(unittest.TestCase):
    def test_slugify_bounds_and_normalizes(self) -> None:
        self.assertEqual("alpha-beta", crawl.slugify(" Alpha / Beta! "))
        self.assertEqual("item", crawl.slugify("!!!"))
        self.assertEqual(120, len(crawl.slugify("A" * 200)))

    def test_atom_entry_requires_title_and_summary(self) -> None:
        feed = b"""<feed xmlns="http://www.w3.org/2005/Atom">
          <entry><title>Useful Result</title><summary>Abstract</summary>
            <id>https://arxiv.org/abs/1234.5678</id>
            <author><name>Ada</name></author></entry>
          <entry><title>Incomplete</title></entry>
        </feed>"""
        records = crawl.parse_arxiv_atom(feed)
        self.assertEqual(1, len(records))
        self.assertEqual("Useful Result", records[0]["title"])
        self.assertEqual(["Ada"], records[0]["authors"])


if __name__ == "__main__":
    unittest.main()
