---
name: research
description: Research a question using high-trust primary sources and return a concise cited answer. Use when the user asks to investigate a topic, gather documentation facts, compare sources, or do research.
---

# Research

Answer the question the research is meant to resolve. Do not research indefinitely.

1. State the decision, claim, or uncertainty the research must support.
2. Prefer primary sources: official documentation, specifications, source code, first-party APIs, original papers, and direct statements. Use secondary sources only to locate or corroborate evidence.
3. Search from more than one angle when the question has multiple constraints. Deduplicate sources and distinguish verified facts from interpretation.
4. Cite factual claims directly. Name material disagreements, missing evidence, and confidence limits.
5. Stop when the minimum evidence needed to support the decision or answer is sufficient. Put worthwhile but nonessential questions in a short follow-up list instead of expanding the main search.
6. Lead with the answer and return concise findings in chat by default. Do not create files unless the user explicitly requests a durable research artifact.

When the Exa search skill is available, use its research orchestration, source-quality checks, coverage validation, and source-counting rules rather than inventing a second search process. If background agents are available, they may do independent source review; otherwise work in the foreground.

For artifact mode, confirm or infer a suitable repository location, write a cited Markdown report, and report the path. Do not commit or push it automatically.
