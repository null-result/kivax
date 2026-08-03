---
name: kivax-yml-spec
description: Canonical schema of the SDD flow's spec.yml, ID conventions, hashing and evolution rules. Use when compiling spec.md to yml, planning from the yml, or deriving tests from it.
---

# Canonical spec.yml schema

## One spec per feature
A project keeps **one directory per feature** under `paths.features`, each holding that feature's own three artifacts:

```
specs/
  01-booking/   spec.md  spec.yml  plan.md
  02-cancel/    spec.md  spec.yml  plan.md
  wiki/         (project-wide, not a feature)
```

Never assemble those paths by hand: run **`kivax feature show --json`** for the active feature (or `--feature <NN>` for another one) and use the paths it returns.

Specs accumulate. A feature that shipped months ago keeps its directory, and `kivax validate`, `kivax hash`, and `kivax trace` all operate on the **union of every feature's spec** — which is exactly what keeps the anchor alive: editing an old spec still changes its hashes and still marks its tests as potentially stale. Only the phase workflow (which feature you're currently driving) is scoped to one feature at a time.

## Structure
See the reference template at `templates/spec.template.yml` in the global install. Top-level fields: `meta`, `context`, `requirements`, `integration_scenarios`, `non_goals`.

## ID conventions
- Every id carries its feature's number: requirements `REQ-FF-NNN`, criteria `AC-FF-NNN-MM` (NNN is the parent REQ's number), integration scenarios `IT-FF-NNN`. So the second requirement of feature 03 is `REQ-03-002`, and its first criterion is `AC-03-002-01`.
- **FF is the number of the directory the file lives in** (`specs/03-refund/spec.yml` → `03`). It never changes for the life of the feature, and a mismatch is a validation error — a test tagged `REQ-03-001` must resolve to exactly one requirement in exactly one feature.
- **NNN is allocated per feature**, from `001` upward: each feature starts its own sequence. Take the next free number above every requirement already in *this* feature's spec, deprecated ones included.
- **Ids are globally unique** across the project, which is what lets `traceability.lock.json` stay a flat `{id: {...}}` map.
- **IDs are immutable**: a requirement whose wording changes keeps its ID (its hash changes, and that's correct — it triggers invalidation of its tests).
- **Never reuse** the ID of a removed requirement: requirements get marked `status: deprecated`, not deleted from the yml (auditable history). New ones take the next free number.

## Hashing
- Each REQ/IT's hash is computed over its canonical yml subtree (sorted keys, normalized whitespace) via `kivax hash`.
- The `notes` field is EXCLUDED from the hash: free-form comments don't invalidate tests.
- `meta` is excluded too, so moving a feature's directory or rewriting `meta.source` cannot invalidate a single test.
- Hashes are NOT written into the yml: they live only in `traceability.lock.json`, updated exclusively by the auditor after a PASSING cycle.

## Retroactive specs (adoption in an existing project)
A requirement that documents ALREADY-implemented behavior (the analyst's "document what exists" mode) carries `origin: retroactive` as an extra field. Semantics: it describes the as-built, not a new design; its tests are written AFTER the code — a legitimate exception to TDD, valid only for that zone's initial migration — and serve as a safety net before modifying it. Once migrated, the zone comes out of `legacy_globs` and every subsequent change goes through the normal (spec-first) flow.

## Language
The schema's KEYS (`id`, `title`, `status`, `priority`, `depends_on`, `description`, `acceptance_criteria`, `given`/`when`/`then`, `edge_cases`, `covers`, `notes`, `meta`, `requirements`, `integration_scenarios`, `non_goals`...) are fixed and NEVER translated — they're the exchange format read literally by `kivax_validate.py`, `kivax_hash.py`, `kivax_trace.py`, `kivax_wiki.py`, and `kivax_specfirst.py`; localizing them breaks every script at once. The VALUES of those keys (the text: titles, descriptions, criteria) do follow `spec_language` from `.kivax/config.yml`, inherited directly from `spec.md` at compile time — the compiler doesn't translate anything, it only structures what's already in that language.

## Compilation rules (md → yml)
- Literal compilation: no adding, no removing, no interpreting. Ambiguity = an error returned to the analyst.
- Every active requirement needs ≥1 acceptance criterion with complete given/when/then.
- `depends_on` may only reference existing REQ-IDs; no cycles. It **may point at a requirement in another feature** (`REQ-01-003` from feature 02) — features build on each other, and both `depends_on` and `covers` are resolved against the union of every spec.
- `integration_scenarios[].covers` lists the REQ-IDs the scenario spans.
- ALWAYS validate with `kivax validate` before considering the compilation done.
