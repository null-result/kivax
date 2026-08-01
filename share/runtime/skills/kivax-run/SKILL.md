---
name: kivax-run
description: "Runs the Kivax flow chained up to the next human gate or exception. Use when the human wants to keep going through several phases at once, or says 'kivax-run'."
---

Chained flow execution. Optional argument (initial request or REQ-IDs): **$ARGUMENTS**

Runs the flow from the current phase (`kivax state show`), following the fixed pipeline (`kivax state next` gives each following phase), chaining automatically until the first of:
- a gate configured as `human` in `.kivax/config.yml`
- an exception (AMBIGUITY, DISPUTE, GAP, CONFLICT, NOT PASSING verdict, failed validation, unrecoverable test)
- the end of the flow (phase `done`)

Protocol:
1. Read the current phase and the gates. Tell the human the stretch you're about to run without stopping (e.g. "plan approved → I'll run tdd + it + audit; I'll stop at audit due to the human gate").
2. Run each phase via its matching `kivax-<phase>` skill (each phase's logic lives in its own skill; don't duplicate it here).
3. When you stop, ALWAYS say why: which human gate or which exception, and what you need from the human to continue.
4. Never chain into the merge, the release, or the deploy: none is a flow phase. The run ends at a pull request marked ready for review. Those operations live in the `kivax-git` skill and only happen when the human asks for them by name.

If the current phase is `spec` and no spec has been drafted yet, use $ARGUMENTS as the request for the `kivax-spec` skill.
