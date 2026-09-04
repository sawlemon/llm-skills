# TDD test guidance

Test observable behavior at a public interface or stable seam. A useful test should fail when the promised behavior is missing and pass when the smallest correct implementation exists.

Prefer one behavior per test and one vertical slice per change. Use fixtures that resemble real inputs. Avoid asserting private call order, internal variables, or implementation details unless they are part of the public contract.

Before writing the test, name the behavior, input, expected result, and reason the chosen seam is stable. Run the test and capture the failure before changing production code.
