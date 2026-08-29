"""Deterministic sentence-aware chunking (no overlap).

Approximates Hindsight v0.9.2's plain-text retain chunker: split on blank
lines first, then sentence terminators, accumulate up to ``max_chars``. A
single sentence longer than ``max_chars`` is hard-split. Chunks carry source
offsets and concatenate back to the input exactly (no character loss, no
overlap) — the property that makes boundary-context benchmarks meaningful.
"""

from __future__ import annotations

import re

_SENTENCE_ENDINGS = ".!?"
_PARA_SPLIT = re.compile(r"(\n\n+)")

def _split_sentences(paragraph: str) -> list[str]:
    sentences: list[str] = []
    current: list[str] = []
    for char in paragraph:
        current.append(char)
        if char in _SENTENCE_ENDINGS:
            piece = "".join(current)
            if piece.strip():
                sentences.append(piece)
            current = []
    tail = "".join(current)
    if tail:
        # Keep trailing text (including whitespace-only tails) attached to the
        # last sentence so units concatenate back to the paragraph exactly.
        if sentences:
            sentences[-1] += tail
        else:
            sentences.append(tail)
    return sentences


def _split_units(text: str) -> list[str]:
    """Split into sentence units that concatenate back to ``text`` exactly.

    Paragraph separators (``\\n\\n+``) are attached to the end of the last
    sentence of the preceding paragraph so no character is lost and a needle
    paragraph keeps its trailing blank line.
    """
    units: list[str] = []
    pieces = _PARA_SPLIT.split(text)
    for i in range(0, len(pieces), 2):
        block = pieces[i]
        separator = pieces[i + 1] if i + 1 < len(pieces) else ""
        sentences = _split_sentences(block) if block.strip() else []
        if sentences:
            sentences[-1] = sentences[-1] + separator
            units.extend(sentences)
        elif separator and units:
            units[-1] = units[-1] + separator
        elif separator:
            units.append(separator)
    return units


def _hard_split(text: str, max_chars: int) -> list[str]:
    return [text[start : start + max_chars] for start in range(0, len(text), max_chars)]


def chunk_text(text: str, max_chars: int = 3000) -> list[dict]:
    """Split ``text`` into chunks of at most ``max_chars`` characters.

    Returns a list of ``{index, text, start_offset, end_offset}`` dicts whose
    ``text`` values concatenate back to ``text`` exactly.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    if len(text) <= max_chars:
        return [dict(index=0, text=text, start_offset=0, end_offset=len(text))]

    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for unit in _split_units(text):
        pieces = [unit] if len(unit) <= max_chars else _hard_split(unit, max_chars)
        for piece in pieces:
            if current and size + len(piece) > max_chars:
                chunks.append("".join(current))
                current, size = [], 0
            current.append(piece)
            size += len(piece)
    if current:
        chunks.append("".join(current))

    result = []
    offset = 0
    for index, chunk in enumerate(chunks):
        result.append(
            dict(index=index, text=chunk, start_offset=offset, end_offset=offset + len(chunk))
        )
        offset += len(chunk)
    return result


def chunk_stats(chunks: list[dict]) -> dict:
    sizes = [len(c["text"]) for c in chunks]
    return {
        "count": len(chunks),
        "min_chars": min(sizes),
        "max_chars": max(sizes),
        "avg_chars": round(sum(sizes) / len(sizes), 2),
    }
