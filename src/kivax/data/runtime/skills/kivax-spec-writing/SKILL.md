---
name: kivax-spec-writing
description: How to write high-quality narrative specifications (spec.md) for the spec-anchored SDD flow. Use when creating or modifying a spec in markdown format, before compiling it to yml.
---

# Writing SDD specifications

## Principles
1. **One requirement = one observable, verifiable behavior.** If the sentence needs "and" to describe the behavior, it's almost certainly two requirements.
2. **Verifiable or it doesn't exist.** "The system must be fast" is not a requirement; "the endpoint responds in <200ms p95 with 100 concurrent users" is. Forbidden unquantified terms: fast, intuitive, easy, robust, efficient, friendly.
3. **Behavior, not implementation.** The spec says WHAT the system does, never HOW (that's the technical plan's job). "Stored in Redis" is implementation; "the session survives a service restart" is behavior.
4. **Non-goals matter as much as requirements.** Making explicit what will NOT be built prevents speculative implementation.

## Given/When/Then format
- **Given**: complete, reproducible initial state (data, configuration, context).
- **When**: ONE action or event.
- **Then**: externally observable result (response, persisted state, emitted event, concrete error with its code/message).
- One criterion per relevant combination. Error cases are first-class criteria, not footnotes.

## Edge cases: minimum checklist
Empty/null values · numeric boundaries (0, 1, max, negative) · duplicates · concurrency · timeouts/dependency failures · insufficient permissions · malformed data · retry idempotency.

## Evolving an existing spec
- Existing requirements keep their ID even if their wording changes.
- New requirements: mark them [NEW] (the compiler assigns the ID, of the form `REQ-<feature number>-<NNN>`, e.g. `REQ-02-004`).
- Removed requirements: mark them [REMOVED] with justification, don't silently delete them.
- Note every assumption in the "Assumptions" section for explicit human validation.
