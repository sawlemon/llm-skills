"""Deterministic chunking invariants."""

import unittest

from hindsight_bench.chunking import chunk_stats, chunk_text


class ChunkingTests(unittest.TestCase):
    def test_short_text_single_chunk(self):
        chunks = chunk_text("Hello world.", 3000)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["text"], "Hello world.")
        self.assertEqual(chunks[0]["start_offset"], 0)

    def test_no_character_loss_with_paragraphs_and_trailing_spaces(self):
        text = "First paragraph ends here. \n\nSecond paragraph has two sentences. It also ends. \n\nThird."
        chunks = chunk_text(text, 40)
        self.assertEqual("".join(c["text"] for c in chunks), text)
        for chunk in chunks:
            self.assertLessEqual(len(chunk["text"]), 40)

    def test_offsets_are_consistent(self):
        text = "Alpha one. Beta two. Gamma three. " * 20
        chunks = chunk_text(text, 50)
        offset = 0
        for chunk in chunks:
            self.assertEqual(chunk["start_offset"], offset)
            self.assertEqual(chunk["end_offset"], offset + len(chunk["text"]))
            self.assertEqual(text[chunk["start_offset"] : chunk["end_offset"]], chunk["text"])
            offset += len(chunk["text"])

    def test_deterministic(self):
        text = "Sentence number one. Sentence number two. " * 30
        self.assertEqual(chunk_text(text, 60), chunk_text(text, 60))

    def test_oversized_sentence_is_hard_split(self):
        unit = "A" * 250
        text = unit + " Normal tail."
        chunks = chunk_text(text, 100)
        self.assertEqual("".join(c["text"] for c in chunks), text)
        self.assertLessEqual(max(len(c["text"]) for c in chunks), 100 + len(" Normal tail."))

    def test_unicode_content_preserved(self):
        text = "Emoji 🚀 sentence. Café with combining e\u0301. 中文句子。Another."
        chunks = chunk_text(text, 12)
        self.assertEqual("".join(c["text"] for c in chunks), text)

    def test_journal_needles_never_straddle_chunks(self):
        from hindsight_bench.fixtures import build_journal_chunks

        chunks, needles, _journal = build_journal_chunks(60_000)
        for needle in needles:
            containing = [c for c in chunks if needle in c["text"]]
            self.assertEqual(len(containing), 1, f"needle straddled chunks: {needle[:40]}")

    def test_journal_chunk_stats_shape(self):
        from hindsight_bench.fixtures import build_journal_chunks

        chunks, _needles, journal = build_journal_chunks(30_000)
        stats = chunk_stats(chunks)
        self.assertEqual(stats["count"], len(chunks))
        self.assertEqual(stats["max_chars"], max(len(c["text"]) for c in chunks))
        self.assertEqual(sum(len(c["text"]) for c in chunks), len(journal))


if __name__ == "__main__":
    unittest.main()
