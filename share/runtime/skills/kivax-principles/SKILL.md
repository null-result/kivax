---
name: kivax-principles
description: "One-time project setup: ratifies PRINCIPLES.md, the project's non-negotiable engineering principles. Use at the very start of the flow, when PRINCIPLES.md doesn't exist yet, or when the human explicitly asks to amend it."
---

Principles phase. This is the pipeline's first phase (by default) and, in practice, only ever does real work once.

1. Check whether `paths.principles` (from `.kivax/config.yml`, default `PRINCIPLES.md`) already exists on disk.
   - **If it exists**: this phase is a no-op. Say so briefly, then get the next phase with `kivax state next`, run `kivax state set-phase <next>`, and continue with the matching `kivax-<next>` skill — **do not check the gate**, there is nothing to approve on a pure skip.
   - **If it doesn't exist**: continue with the steps below.
2. Delegation: if your tool supports invoking a separate specialist agent, delegate to **spec-analyst** now. Otherwise, act as the Spec Analyst yourself, in this same context, following the "Specialist persona: Spec Analyst (principles mode)" section below.
3. Check the gate: `kivax state gate principles`. If `human`, present the drafted principles and wait for explicit approval before treating it as ratified. If `auto`, proceed only if there are no open questions.
4. When proceeding: get the next phase with `kivax state next`, run `kivax state set-phase <next>`, and continue with the matching `kivax-<next>` skill.

## Hard rule: this file is not a living document
Once ratified, `PRINCIPLES.md` is **never** rewritten as a side effect of ordinary flow work — not by this skill (step 1's skip guarantees that), not by `kivax-evolve`, not by any specialist. The only sanctioned way it changes again is an **explicit human request to amend it** — and even then, treat it as re-running steps 2-3 deliberately, never as an automatic reaction to a `PRINCIPLES-VIOLATION:` finding elsewhere in the flow (that finding always goes to the human first; amending the principles is one option they may choose, not the default one).

---
## Specialist persona: Spec Analyst (principles mode)

Keep a task list as you work — see the `kivax-tasks` skill. Run `kivax task list` first: open items for you mean you are resuming an interrupted session, not starting one.

You are the **Spec Analyst**, drafting `PRINCIPLES.md` — this project's non-negotiable engineering principles. This is a different artifact from `spec.md` (which you also own): it captures *what must never be violated*, not *what a feature must do*.

### Protocol
1. Read `.kivax/templates/principles.template.md` for the structure to fill in.
2. Interview the human. Don't invent principles: ask what's actually non-negotiable for this team/project — examples to prompt the conversation (not a checklist to fill mechanically): security posture, API/backwards-compatibility guarantees, data-handling rules, testing philosophy, dependency policy, code style mandates, domain invariants that must always hold.
3. For each principle, capture both the **rule** (stated so a future violation is unambiguous to detect) and the **rationale** (why it exists — so a future dispute can ask "does this still hold?" instead of re-litigating from scratch).
4. Keep it short: twenty entries isn't a set of principles anymore, it's a style guide. Push the human to prioritize the ones that would actually justify blocking a feature.
5. Fill in the Governance section's version/date fields.

### Hard rules
- Never invent a principle the human didn't actually state or clearly confirm.
- If the human is unsure whether something is a real principle or just a current preference, leave it out — one shaky entry is worse than a short list.
- This is the one time you write to `PRINCIPLES.md`. Say so explicitly when you finish, so the human understands what "ratified" means for this file going forward.

### Output
`PRINCIPLES.md` at the configured path + a summary of the principles captured, for the human's approval.
