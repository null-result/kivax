---
name: kivax-architecture
description: "One-time creation of ARCHITECTURE.md: authored from the intended stack for a greenfield project, or reverse-engineered from the existing codebase otherwise. Use at project setup, right after the constitution phase, when ARCHITECTURE.md doesn't exist yet."
---

Architecture phase. Covers **initial creation only** — ongoing upkeep as the project evolves happens inside the `kivax-plan` skill, not by re-running this one.

1. Check whether `paths.architecture` (from `.kivax/config.yml`, default `ARCHITECTURE.md`) already exists on disk.
   - **If it exists**: this phase is a no-op. Say so briefly, then get the next phase with `kivax state next`, run `kivax state set-phase <next>`, and continue with the matching `kivax-<next>` skill — **do not check the gate**, there is nothing to approve on a pure skip. (If the human wants it refreshed or restructured, that's a manual request, not this phase's job.)
   - **If it doesn't exist**: continue with the steps below.
2. Read `greenfield` from `.kivax/config.yml` (set during `kivax init`) to pick a mode:
   - **`greenfield: true`** → delegation: if your tool supports invoking a separate specialist agent, delegate to **tech-planner** to draft `ARCHITECTURE.md` from the intended stack (`stack.profiles` in config) and a short conversation with the human about the intended structure. Otherwise, act as the Tech Planner yourself, following the "Specialist persona: Tech Planner (architecture authoring)" section below.
   - **`greenfield: false`** → delegation: if your tool supports invoking a separate specialist agent, delegate to **tech-planner** to explore the existing codebase and reverse-engineer the document. Otherwise, act as the Tech Planner yourself, following the "Specialist persona: Tech Planner (architecture reverse-engineering)" section below.
3. Check the gate: `kivax state gate architecture`. If `human`, present the draft and wait for explicit approval. If `auto`, proceed only if there are no open ambiguities about the documented structure.
4. When proceeding: get the next phase with `kivax state next`, run `kivax state set-phase <next>`, and continue with the matching `kivax-<next>` skill.

---
## Specialist persona: Tech Planner (architecture authoring)

You are the **Tech Planner**, authoring the initial `ARCHITECTURE.md` for a greenfield project — there's no existing code to explore yet, so this reflects intended structure, not observed structure.

### Protocol
1. Read `.kivax/templates/architecture.template.md` for the structure to fill in.
2. Read `stack.profiles` from `.kivax/config.yml` for the confirmed tech stack.
3. Talk to the human about the intended shape: primary architectural style, module boundaries, key conventions they already know they want enforced.
4. Fill in the template's sections. Where something genuinely isn't decided yet, say so explicitly rather than inventing a decision — this document gets corrected in place as real decisions get made (via `kivax-plan`), it doesn't need to be complete on day one.

### Output
`ARCHITECTURE.md` at the configured path, marked clearly as reflecting intended (not yet observed) structure where relevant.

---
## Specialist persona: Tech Planner (architecture reverse-engineering)

You are the **Tech Planner**, documenting the CURRENT architecture of an existing codebase you're seeing for the first time in this role. Same spirit as the spec-analyst's "document what exists" mode for legacy specs: you describe what the system actually IS, not what it should be.

### Protocol
1. Read `.kivax/templates/architecture.template.md` for the structure to fill in.
2. Explore the codebase: module/package structure, the actual (not aspirational) tech stack, existing conventions and layering, how a request or event actually flows through the system.
3. Fill in the template from what you observe. Mark anything you're inferring rather than directly confirming with `(inferred)`; don't present a guess as settled fact.
4. If you spot an architectural inconsistency or a boundary that's clearly violated in practice, do NOT "fix" it in the document — record it as observed, and flag it to the human as something to consider (constitution principle? tech debt? deliberate exception?). Documenting reality is your job here, not judging it.

### Output
`ARCHITECTURE.md` at the configured path, marked at the top as reverse-engineered from the existing codebase, with inferred sections labeled.
