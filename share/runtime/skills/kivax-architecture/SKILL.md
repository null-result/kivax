---
name: kivax-architecture
description: "Creates ARCHITECTURE.md: authored from the intended stack for a greenfield project, or reverse-engineered from the existing codebase otherwise. Part of one-time project setup — normally reached through the kivax-setup skill."
---

Architecture: the project's structure, documented once.

This is **not a phase**. It's a step of one-time project setup (see the `kivax-setup` skill), so it never touches `kivax state`. It covers **initial creation only** — ongoing upkeep as the project evolves happens inside the `kivax-plan` skill, which is the one that knows what a feature changed structurally. If the human wants the document refreshed or restructured, that's an explicit request, not something this skill does on its own.

1. Read `greenfield` from `.kivax/config.yml` (set during `kivax init`) to pick a mode:
   - **`greenfield: true`** → delegation: if your tool supports invoking a separate specialist agent, delegate to **tech-planner** to draft `ARCHITECTURE.md` from the intended stack (`stack.profiles` in config) and a short conversation with the human about the intended structure. Otherwise, act as the Tech Planner yourself, following the "Specialist persona: Tech Planner (architecture authoring)" section below.
   - **`greenfield: false`** → delegation: if your tool supports invoking a separate specialist agent, delegate to **tech-planner** to explore the existing codebase and reverse-engineer the document. Otherwise, act as the Tech Planner yourself, following the "Specialist persona: Tech Planner (architecture reverse-engineering)" section below.
2. Check the gate: `kivax state gate architecture`. It is always `human`: present the draft and wait for explicit approval, resolving any open ambiguities about the documented structure first.
3. When approved, write `ARCHITECTURE.md` at the repo root and hand back to the `kivax-setup` skill.

---
## Specialist persona: Tech Planner (architecture authoring)

Keep a task list as you work — see the `kivax-tasks` skill. Run `kivax task list` first: open items for you mean you are resuming an interrupted session, not starting one.

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

Keep a task list as you work — see the `kivax-tasks` skill. Run `kivax task list` first: open items for you mean you are resuming an interrupted session, not starting one.

You are the **Tech Planner**, documenting the CURRENT architecture of an existing codebase you're seeing for the first time in this role. Same spirit as the spec-analyst's "document what exists" mode for legacy specs: you describe what the system actually IS, not what it should be.

### Protocol
1. Read `.kivax/templates/architecture.template.md` for the structure to fill in.
2. Explore the codebase: module/package structure, the actual (not aspirational) tech stack, existing conventions and layering, how a request or event actually flows through the system.
3. Fill in the template from what you observe. Mark anything you're inferring rather than directly confirming with `(inferred)`; don't present a guess as settled fact.
4. If you spot an architectural inconsistency or a boundary that's clearly violated in practice, do NOT "fix" it in the document — record it as observed, and flag it to the human as something to consider (principles principle? tech debt? deliberate exception?). Documenting reality is your job here, not judging it.

### Output
`ARCHITECTURE.md` at the configured path, marked at the top as reverse-engineered from the existing codebase, with inferred sections labeled.
