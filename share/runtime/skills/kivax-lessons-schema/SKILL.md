---
name: kivax-lessons-schema
description: Schema of the SDD flow's lessons store — the engineering knowledge each iteration leaves behind. Use when writing a lesson in the retro phase, or when reading the applicable ones before planning or implementing.
---

# Lessons store schema

## What this store is (and what the wiki is)
Two knowledge artifacts, two different questions:

| | `wiki/` | `lessons/` |
|---|---|---|
| Answers | "what does this system do" | "what went wrong building it, and what do we do about it" |
| Derived from | `spec.yml` (every claim traces to a REQ) | what actually happened during the phases |
| Owner | wiki-curator | knowledge-curator |
| Lifecycle | reingested when its source REQ's hash changes | reinforced when the same problem recurs; retired when it stops being true |

A lesson has **no REQ behind it** — that's precisely why it can't live in the wiki, whose one non-negotiable rule is that everything on a page traces to a requirement. If something you're about to write as a lesson is really unspecified *behavior*, it isn't a lesson: it's a `GAP:`, and it goes through `kivax-evolve` into the spec.

## One lesson per file
Under `paths.lessons` (default `<paths.features>/lessons/`), named `LSN-NNNN-<slug>.md`.

**Ids are allocated by `kivax lessons new <slug>`, never by hand.** Two lessons sharing an id would make every `## Lessons applied` reference in every plan ambiguous, and nothing downstream would notice.

```markdown
---
id: LSN-0007
title: Flyway migrations must run before the Spring test context boots
status: active                # active | retired
phases: [plan, tdd, it]       # which phases get shown this lesson
paths: ["src/main/resources/db/**", "**/*IT.java"]   # empty = project-wide
tags: [flyway, testcontainers]
origin:
  feature: 03-cancel-booking
  phase: it
  evidence: ["commit 8f2a1c3", "IT-03-002 cycled red->green->red twice"]
seen_in: [03-cancel-booking, 05-refunds]
updated_at: 2026-07-31
---

# Flyway migrations must run before the Spring test context boots

## What happened
<2-4 sentences: the concrete failure, the file, the symptom, how long it took to find.>

## Rule
<One imperative sentence, followable BEFORE the mistake happens.>

## How to catch it early
<The cheapest signal it's happening again: an exact error message, a test that goes red, a command.>
```

## Field rules
- **`phases`** — required, non-empty. It's what `kivax lessons relevant --phase <p>` filters on. Be narrow: a lesson surfaced in every phase is a lesson skimmed in every phase.
- **`paths`** — optional globs, same semantics as `legacy_globs`. Empty means project-wide, so it applies to *every* feature forever; use globs whenever the lesson is really about one area of the codebase.
- **`origin`** — required `feature`, plus the phase and the concrete `evidence` (commit hashes, a REQ's status churn, an audit finding). A lesson with no provenance can't be re-examined when it later turns out to be wrong.
- **`seen_in`** — every feature that hit it again. **A lesson seen three times is not three lessons**: append to `seen_in`, sharpen the rule, bump `updated_at`. Duplicating it is the failure mode that turns this store into noise.
- **`status: retired`** — needs `superseded_by: LSN-NNNN` or a `retired_reason`. Retiring is how a lesson stops binding; deleting the file loses the record that it was ever true.

## Writing rules
- The `## Rule` section is mandatory (`kivax lessons lint` enforces it) and must be **imperative and checkable**. "Run migrations in a `@BeforeAll`" — not "be careful with migrations".
- One lesson = one mistake with one rule. If you're writing "and also", it's two lessons.
- Never write a lesson from a bug you merely *imagine* recurring: the store's value comes from every entry being something that genuinely cost this project time, traceable through `origin.evidence`.
- Write in `spec_language` from `.kivax/config.yml`, like every other content artifact.

## How a lesson binds
`kivax lessons check` (run by the trace-auditor at the audit gate) computes the lessons applicable to the active feature — the project-wide ones, plus the path-scoped ones whose globs match the branch diff or a path named in `plan.md` — and fails when any of them isn't named in `plan.md` under:

```markdown
## Lessons applied
- LSN-0007 — migrations moved into the shared test fixture's @BeforeAll.
- LSN-0002 — not applicable: this feature adds no scheduled job.
```

**A lesson can be dismissed. It cannot be dismissed silently.** That single rule is what stops this store from becoming a diary nobody reads.
