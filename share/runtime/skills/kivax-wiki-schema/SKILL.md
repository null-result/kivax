---
name: kivax-wiki-schema
description: Schema of the SDD flow's knowledge wiki (Karpathy's LLM-wiki pattern adapted to specs). Use when ingesting specs into the wiki, answering queries from it, or auditing its freshness.
---

# SDD wiki schema

## Three-layer architecture (LLM-wiki pattern adaptation)
1. **Sources**: every feature's `spec.yml` and `plan.md` (`<paths.features>/NN-slug/`, e.g. `specs/01-booking/spec.yml`). Resolve a specific one with `kivax feature show --feature <NN> --json`. Immutable to the curator — read, never touched.
2. **Wiki**: `wiki/*.md`, pages compiled per concept. Exclusive property of the wiki-curator.
3. **Schema**: this skill. Defines conventions and operations.

The wiki COMPILES knowledge (built once, queried many times); it is not RAG (rediscovering on every query). And it is **derived**: on any discrepancy with the spec, the spec wins and the page gets reingested.

## Page structure
Filename: `kebab-case` of the concept (`capacity.md`, `booking.md`, `retry-policy.md`).

```markdown
---
concept: capacity
sources:
  - REQ-01-001@sha256:a1b2c3d4e5f6a7b8
  - REQ-02-004@sha256:9f8e7d6c5b4a3f2e
  - plan:bookings          # plan sections, no hash (weak provenance)
updated_at: 2026-07-18
---

# Capacity

<Definition of the concept in 2-4 sentences.>

## Invariants
- Capacity is never negative (REQ-01-001).
- ...

## Relationships
- Consumed when a [[booking]] is confirmed (REQ-01-001) and released when it's cancelled (REQ-02-004).

## Relevant decisions
- <Plan decision that affects the concept, with reference.>
```

## Provenance rules
- Source format: `ID@hash`, where the hash is that ID's current one per `kivax hash` (format `sha256:` + 16 hex chars).
- **A page may cite requirements from several features** — the wiki is project-wide, and that cross-feature context is precisely its value. `kivax hash` prints each id's owning feature alongside it.
- Every relevant claim must be traceable to an ID listed in `sources`. The curator's own inferences: marked `(inference, no REQ)` and used as sparingly as possible.
- `kivax wiki lint` compares the hashes in `sources` against the spec's current ones: a different hash = stale page → reingest that page; a nonexistent or deprecated ID = broken reference.

## Content rules
- **One page per domain concept, not per REQ**: REQs are sources, concepts are pages. A typical REQ feeds 2-4 pages, and a mature concept page draws on several features.
- Short, dense pages: the wiki compresses, it doesn't duplicate specs.
- `[[concept]]` links between related pages; `wiki/_index.md` lists every page with a one-line description.
- The wiki never contains new requirements: if unspecified knowledge emerges while compiling, propose the `kivax-evolve` skill, don't write it into the wiki as fact.

## Consumption by other agents
spec-analyst and tech-planner may READ the wiki as domain context (detecting contradictions with existing invariants, understanding cross-cutting concepts), but never cite it as justification: the justification is always the underlying REQ, which they must verify in `spec.yml`.
