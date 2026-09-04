---
name: code-review
description: Review changes from an explicit Git fixed point along separate standards and specification axes. Use when the user asks to review a branch, diff, pull request, work in progress, or changes since a commit, tag, or merge-base.
---

# Code review

Review evidence, not impressions.

1. Require a fixed point such as a commit, branch, tag, or merge-base. If none is supplied, ask for one. Confirm it resolves with `git rev-parse`.
2. Define the review scope explicitly: branch diff, staged changes, or working-tree changes. Do not silently substitute one for another.
3. Read the repository's instructions and find the originating specification, issue, or request. If no specification exists, say that the specification axis lacks evidence. Never invent requirements.
4. Review two independent axes:
   - **Standards:** repository rules, correctness, security, maintainability, and relevant code-quality smells.
   - **Specification:** whether the change satisfies the originating request and its acceptance criteria.
5. Use `git diff <fixed-point>...HEAD` and `git log <fixed-point>..HEAD --oneline` for branch review. Use the exact equivalent for another explicit scope.
6. Run independent review passes in parallel when the runtime supports it; otherwise run them sequentially without merging their reasoning prematurely.
7. Report findings with severity, file and line references, evidence, and a concrete fix. Keep standards and specification findings separate. Report what was checked and what could not be checked.

Do not edit files, post review comments, create issues, commit, or push. This skill produces a review report only. Do not claim a clean review without inspecting the diff and relevant tests or checks.
