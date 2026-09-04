---
name: tdd
description: Use test-driven development for a feature or bug fix. Trigger when the user asks for test-first work, red-green-refactor, integration tests, or a regression test before implementation.
---

# Test-driven development

Test public behavior through the narrowest defensible seam.

1. Inspect the code and identify the behavior and test boundary. Ask one seam question only if its answer materially changes the test; otherwise choose and state the boundary.
2. Write one focused test that expresses the desired behavior and confirm that it fails for the intended reason.
3. Make the smallest implementation that passes the test.
4. Work in one independently verifiable vertical slice at a time. Keep tests independent of private implementation details.
5. Run the focused test, then the relevant broader project checks.
6. Refactor only after the behavior is green. Keep refactoring separate from the red-green loop.

Discover the target project's test commands and conventions instead of assuming a language or runner. Use real interfaces where practical. Avoid tautological tests, tests that merely mirror implementation details, and broad mocks that hide the behavior under test.

For detailed guidance, read `tests.md` and `mocking.md` in this directory when the test boundary or mock strategy needs more explanation.
