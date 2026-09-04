---
name: diagnosing-bugs
description: Diagnose hard bugs and performance regressions with a reproducible evidence loop. Use when the user asks to debug or diagnose something broken, failing, throwing, slow, or incorrect.
---

# Diagnosing bugs

Do not theorize from a vague symptom. Establish evidence first.

1. Build and run a tight feedback loop for the user's exact symptom. Use a focused test, command, HTTP request, browser script, trace replay, fixture, differential check, or another direct reproduction. If no loop can go red, state the blocker.
2. Reproduce and minimise the failure. Record the exact command and observed result.
3. Generate three to five ranked, falsifiable hypotheses. Each hypothesis must say what evidence would support or reject it.
4. If the reproduction does not isolate the cause, instrument one variable at a time. Mark temporary logs or probes with a unique prefix, redact secrets, and avoid changing unrelated behavior.
5. Add a regression test at the correct public seam when one exists. If no defensible seam exists, report that limitation.
6. Make the smallest fix, rerun the regression test, and rerun the original reproduction loop.
7. Remove temporary instrumentation and throwaway artifacts. Run the relevant project checks and report exact results.

Read the target project's instructions before acting. Discover its actual commands. Prefer `rg` for search. Do not assume `CONTEXT.md`, ADRs, a human-in-the-loop script, a commit, or a push. Never include credentials or sensitive data in commands, logs, reports, or artifacts. Do not claim diagnosis or verification without a reproduced result.
