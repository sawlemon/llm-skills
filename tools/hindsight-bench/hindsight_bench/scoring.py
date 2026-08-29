"""Scoring: criteria-based fact evaluation and rank metrics.

Fact criteria are corpus-level and alias-tolerant: a required group passes if
any of its aliases appears anywhere in the joined fact text. This replaces
the session's brittle per-fact substring checks — the manual review corrections
(e.g. "User completed the migration..." was valid even though the literal
phrase differed) are encoded as aliases in the goldens, not as expected prose.

Forbidden entries may carry ``unless`` aliases: mentioning a superseded date
is only a violation when no correction qualifier co-occurs.
"""

from __future__ import annotations

import math
import re
from statistics import median

_WS = re.compile(r"\s+")
_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


def normalize(text: str) -> str:
    return _WS.sub(" ", str(text).translate(_QUOTES)).strip().lower()


def joined_fact_text(facts: list[dict]) -> str:
    return normalize("\n".join(f.get("what", f.get("text", "")) for f in facts))


def _group_matches(group: dict, corpus: str) -> bool:
    """A group passes when every ``all`` alias AND at least one ``any`` alias match."""
    if group.get("all") and not all(normalize(alias) in corpus for alias in group["all"]):
        return False
    if group.get("any"):
        return any(normalize(alias) in corpus for alias in group["any"])
    return True


def _forbidden_present(entry, corpus: str) -> bool:
    if isinstance(entry, str):
        return normalize(entry) in corpus
    if entry.get("regex"):
        return re.search(entry["text"], corpus, flags=re.IGNORECASE) is not None
    return normalize(entry["text"]) in corpus


def evaluate_fact_criteria(facts: list[dict], case: dict) -> dict:
    """Score extracted facts against a golden case's criteria.

    Returns ``{passed, criteria, violations, unsupported_count}``.
    """
    corpus = joined_fact_text(facts)
    criteria: dict[str, dict] = {}
    violations: list[str] = []

    for group in case.get("required", []):
        passed = _group_matches(group, corpus)
        criteria[group["id"]] = {"passed": passed, "kind": "required"}
        if not passed:
            violations.append(f"required group {group['id']!r} not satisfied")

    for entry in case.get("forbidden", []):
        name = entry if isinstance(entry, str) else entry.get("id", entry.get("text", ""))
        unless = [] if isinstance(entry, str) else entry.get("unless", [])
        if _forbidden_present(entry, corpus) and not any(normalize(u) in corpus for u in unless):
            criteria[f"forbidden:{name}"] = {"passed": False, "kind": "forbidden"}
            violations.append(f"forbidden content present without qualifier: {name!r}")
        else:
            criteria[f"forbidden:{name}"] = {"passed": True, "kind": "forbidden"}

    limits = case.get("limits", {})
    count = len(facts)
    if "min_facts" in limits and count < limits["min_facts"]:
        violations.append(f"fact count {count} < min_facts {limits['min_facts']}")
    if "max_facts" in limits and count > limits["max_facts"]:
        violations.append(f"fact count {count} > max_facts {limits['max_facts']}")

    unsupported = 0
    if "max_unsupported" in limits:
        allowed_aliases = [alias for group in case.get("required", []) for alias in group.get("any", [])]
        allowed_aliases += [alias for group in case.get("required", []) for alias in group.get("all", [])]
        allowed_aliases += [a for entry in case.get("permitted_extra", []) for a in ([entry] if isinstance(entry, str) else entry.get("any", []))]
        for fact in facts:
            text = normalize(fact.get("what", fact.get("text", "")))
            if text and not any(normalize(alias) in text for alias in allowed_aliases):
                unsupported += 1
        if unsupported > limits["max_unsupported"]:
            violations.append(f"unsupported facts {unsupported} > max_unsupported {limits['max_unsupported']}")

    return {"passed": not violations, "criteria": criteria, "violations": violations, "unsupported_count": unsupported}


# ---------------------------------------------------------------------------
# Rank metrics for reranker evaluation
# ---------------------------------------------------------------------------

def dcg(grades: list[int]) -> float:
    return sum((2**g - 1) / math.log2(rank + 2) for rank, g in enumerate(grades))


def ndcg_at_k(ranked_grades: list[int], ideal_grades: list[int], k: int = 10) -> float:
    ideal = dcg(sorted(ideal_grades, reverse=True)[:k])
    return dcg(ranked_grades[:k]) / ideal if ideal else 0.0


def mrr(ranked_grades: list[int], relevant: int = 2) -> float:
    for rank, grade in enumerate(ranked_grades):
        if grade >= relevant:
            return 1.0 / (rank + 1)
    return 0.0


def hit_at_k(ranked_grades: list[int], k: int, relevant: int = 2) -> bool:
    return any(g >= relevant for g in ranked_grades[:k])


def rank_metrics(ranked_grades: list[int], ideal_grades: list[int]) -> dict:
    return {
        "ndcg10": round(ndcg_at_k(ranked_grades, ideal_grades, 10), 6),
        "mrr": round(mrr(ranked_grades), 6),
        "hit1": hit_at_k(ranked_grades, 1),
        "top1_grade": ranked_grades[0] if ranked_grades else 0,
    }


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def summarize(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    return {
        "n": len(values),
        "median": round(median(values), 6),
        "mean": round(sum(values) / len(values), 6),
        "min": round(ordered[0], 6),
        "max": round(ordered[-1], 6),
        "p95": round(ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))], 6),
    }
