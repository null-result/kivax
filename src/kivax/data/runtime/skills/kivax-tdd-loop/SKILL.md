---
name: kivax-tdd-loop
description: Red-green protocol of the SDD flow and per-stack REQ-ID test-tagging conventions. Use when writing tests from acceptance criteria or implementing code to turn them green.
---

# SDD flow TDD protocol

## Cycle per requirement
1. **Red**: the test-writer derives tests ONLY from the yml's acceptance_criteria and the plan's contracts. Run them and verify they fail for the right reason (a behavioral assert, not an unrelated compilation error).
2. **Green**: the implementer writes the minimum code that satisfies the tests. Run the REQ's tests first, then the full suite.
3. **Refactor**: only with the suite green, without changing behavior.

## Test tagging (essential for traceability)
The auditor locates tests via regex (see `id_tag_regexes` for each active profile in `.kivax/config.yml`; in a monorepo there are several at once, one per stack). Ids carry their feature's number — `REQ-02-001` is the first requirement of feature 02 — which is what makes a tag resolve to exactly one requirement across the whole project. Per-stack conventions:
- **java-spring (JUnit 5)**: `@Tag("REQ-02-001")` on the class or method. A test can carry several tags.
- **python-pytest**: `@pytest.mark.req("REQ-02-001")` (register the `req` marker in conftest/pyproject). IT tests additionally use `@pytest.mark.it`.
- **node-jest**: the ID in brackets in the name: `describe("[REQ-02-001] seat booking", ...)`.
- **go**: comment `// kivax:REQ-02-001` on the test's line.

Tags of features that already shipped stay exactly as they are — never rewrite an old test's tag to a different form. If `kivax trace` suddenly reports every new requirement as uncovered, the project's `id_tag_regexes` predate the per-feature id form: run `kivax doctor`, which detects that specific case and prints the replacement pattern.

## Test names
Describe behavior, not implementation: `rejects_booking_when_at_capacity` ✔ · `testBooking2` ✘. At least one test per acceptance criterion; the yml's edge_cases also generate tests.

## Prohibitions
- The test-writer never writes production code; the implementer never touches tests, spec, or plan.
- No @Disabled/skip/xit to make something "pass": an inconvenient test gets disputed with the orchestrator, not silenced.
- Behavior with no REQ = GAP that gets reported; the spec evolves first.
