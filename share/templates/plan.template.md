# Technical plan: FF-<feature-slug> (spec v<N>)

> Covers ONE feature: the requirements in `<paths.features>/FF-<slug>/spec.yml`.

## Approach summary
<2-4 sentences: overall strategy and how it fits the existing architecture.>

## Contracts and interfaces
<Concrete port/interface/DTO signatures the tests will be written against.
The test-writer will use EXACTLY these signatures.>

## Traceability mapping
| REQ | Affected modules/files | Expected tests |
|-----|-------------------------|-----------------|
| REQ-FF-001 | ... | ... |

## Implementation order
1. **Phase 1** (no dependencies): REQ-FF-001, REQ-FF-002
2. **Phase 2** (depends on phase 1): REQ-FF-003

## Lessons applied
<Every lesson `kivax lessons check` finds applicable must appear here, with
either how this plan honors it or why it doesn't apply. The audit fails on a
missing one — a lesson may be dismissed, but not silently. Delete nothing from
this heading: `kivax lessons check` looks for it by name.>

- LSN-XXXX — <how this plan honors it>
- LSN-YYYY — not applicable: <why>

## Technical decisions and discarded alternatives
- <Decision>: <why, and what was discarded.>

## Risks
- <Risk and mitigation.>
