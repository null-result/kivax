---
name: kivax-setup
description: "One-time project setup: writes PRINCIPLES.md and ARCHITECTURE.md with the human, before the first feature exists. Use right after 'kivax init', or when 'kivax feature new' refuses because one of those documents is missing."
---

Project setup. This runs **once per repository**, before the first feature — not once per feature.

Both documents describe the project, not the thing being built this week, so they are written here and then maintained elsewhere: `ARCHITECTURE.md` is kept current by the `plan` phase, which is the only place that knows what a feature changed structurally, and `PRINCIPLES.md` changes only on an explicit human request to amend it.

`kivax feature new` refuses while either document is missing, so this is a precondition of the flow, not an optional preamble. It is also why neither of these is a phase: `kivax state` never sees them, they never appear in a feature's history, and there is nothing to skip past on feature 2.

## Steps
1. Work out what's missing: `PRINCIPLES.md` and `ARCHITECTURE.md` at the repo root. If both exist, say so and stop — this skill has nothing to do. If the human wants one of them rewritten, that's an explicit amendment request, handled by re-running the relevant step below deliberately.
2. If `PRINCIPLES.md` is missing: run the `kivax-principles` skill.
3. If `ARCHITECTURE.md` is missing: run the `kivax-architecture` skill. Do this after the principles, never before — the architecture is one of the first things the principles constrain.
4. When both exist, tell the human the project is ready and that the next step is their first feature (the `kivax-new` skill).

## Hard rules
- **Never invent either document to unblock a feature.** Both are ratified with the human; a principles file nobody agreed to is worse than none, because the `plan` and `audit` phases will enforce it.
- Each step keeps its own human gate. Setup isn't a phase, but its two steps are the kind of decision a person signs off on.
- If the human wants to start a feature first and write these later, say no and explain why: the `plan` phase reads both, so a feature planned without them is planned against principles nobody wrote down yet. Writing them takes one conversation.
