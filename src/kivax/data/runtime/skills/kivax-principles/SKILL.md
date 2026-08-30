---
name: kivax-principles
description: "Ratifies PRINCIPLES.md, the project's non-negotiable engineering principles. Part of one-time project setup — normally reached through the kivax-setup skill, or run directly when the human explicitly asks to amend the principles."
---

Principles: the project's non-negotiable engineering rules, ratified once.

This is **not a phase**. It's a step of one-time project setup (see the `kivax-setup` skill), so it never touches `kivax state`: there is no gate to advance and no next phase to move to. A project's principles belong to the repository, not to whichever feature happened to be first.

1. Delegation: if your tool supports invoking a separate specialist agent, delegate to **spec-analyst** now. Otherwise, act as the Spec Analyst yourself, in this same context, following the "Specialist persona: Spec Analyst (principles mode)" section below.
2. Check the gate: `kivax state gate principles`. It is always `human`: present the drafted principles and wait for explicit approval before treating them as ratified. Principles nobody agreed to are worse than none, because `plan` and `audit` will enforce them.
3. When approved, write `PRINCIPLES.md` at the repo root and hand back to the `kivax-setup` skill (or, if the human ran this directly to amend the file, just report what changed).

## Hard rule: this file is not a living document
Once ratified, `PRINCIPLES.md` is **never** rewritten as a side effect of ordinary flow work — not by `kivax-evolve`, not by any specialist, and not by setup running again (setup only writes it when it's missing). The only sanctioned way it changes is an **explicit human request to amend it** — and even then, treat it as re-running steps 1-3 deliberately, never as an automatic reaction to a `PRINCIPLES-VIOLATION:` finding elsewhere in the flow (that finding always goes to the human first; amending the principles is one option they may choose, not the default one).

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
