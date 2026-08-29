"""Hindsight benchmark suite.

Reproducible, standard-library-only benchmarks for Hindsight memory operations
(retain extraction, journal chunking, context limits, recall tracing) and for
OpenRouter reranking. Offline mode is deterministic and touches no network.

Suites:
    retain-matrix          model comparison for retain fact extraction
    retain-adversarial     negation/attribution/uncertainty extraction cases
    journal-long           long-document chunking + extraction coverage
    boundary-context       chunk-boundary qualifier/correction behavior
    context-limit          request sizing near the model context ceiling
    recall-trace           Hindsight recall phase-latency decomposition
    rerank-neutral         reranker relevance on a fixed synthetic pool
    candidate-cap-scaling  reranker quality/latency across candidate caps
"""

__version__ = "1.0.0"

SUITES = (
    "retain-matrix",
    "retain-adversarial",
    "journal-long",
    "boundary-context",
    "context-limit",
    "recall-trace",
    "rerank-neutral",
    "candidate-cap-scaling",
)
