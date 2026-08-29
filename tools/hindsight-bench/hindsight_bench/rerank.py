"""Reranker benchmark pools: graded cases padded to a fixed size.

Each golden case supplies graded documents (text + relevance grade); the pool
is padded with the deterministic neutral pool up to ``pad_to`` documents.
Pool construction is a pure function so tests and scoring agree on which
index maps to which grade.
"""

from __future__ import annotations

from .fixtures import build_neutral_pool


def build_pool(case: dict, filler_pool: list[str] | None = None) -> tuple[list[str], dict[int, int]]:
    """Return ``(documents, index->grade)`` for a reranker case."""
    graded = case["graded"]
    pad_to = int(case.get("pad_to", 300))
    documents = [entry["text"] for entry in graded]
    grades = {i: int(entry["grade"]) for i, entry in enumerate(graded)}
    filler = filler_pool if filler_pool is not None else build_neutral_pool(pad_to)
    for text in filler:
        if len(documents) >= pad_to:
            break
        documents.append(text)
    while len(documents) < pad_to:
        documents.append(NEUTRAL_FALLBACK.format(i=len(documents)))
    return documents, grades


NEUTRAL_FALLBACK = "Unrelated operational note number {i} about a separate project."


def truncate_for_cap(case: dict, cap: int, filler_pool: list[str] | None = None) -> tuple[list[str], dict[int, int]]:
    """Pool truncated to ``cap`` documents, gold docs always kept first.

    For ``cap >= len(graded)`` this equals ``build_pool`` truncated; for
    smaller caps the graded documents remain so quality stays measurable.
    """
    documents, grades = build_pool(case, filler_pool)
    keep = min(cap, len(documents))
    return documents[:keep], {i: g for i, g in grades.items() if i < keep}
