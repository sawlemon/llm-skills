# TDD mocking guidance

Mock only a boundary that is slow, nondeterministic, unavailable, or outside the behavior under test. Keep the real code path for the behavior being verified.

Prefer small fakes or fixtures when they make the test clearer. Do not mock the unit's own logic, duplicate production code in a mock, or assert incidental call details. If a mock is required, state which external boundary it replaces and what contract the test still exercises.
