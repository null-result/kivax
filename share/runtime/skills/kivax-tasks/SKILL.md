---
name: kivax-tasks
description: "Protocol for the per-agent task lists that make an interrupted session resumable mid-agent. Read by every long-running specialist (researcher, spec-analyst, tech-planner, test-writer, implementer, wiki-curator) before starting work, and by the orchestrator when picking a session back up."
---

# Task lists: resuming an interrupted session

A session can end at any moment — the human closes the terminal, the context runs out, the tool crashes. Kivax already survives that at two granularities: `kivax state show` knows which **phase** you're in, and the per-REQ status knows which requirements are red or green. Neither knows where a long-running agent got to *inside* one invocation.

That's the gap this fills. Before doing the work, you write down what the work is; as you go, you mark it off. A fresh session reads the list instead of redoing everything — or worse, redoing it *differently*.

**The list lives in `.kivax/state.yml`, and only the CLI writes it.** Never hand-edit that file, exactly as you never hand-edit the per-REQ status. Same reason: it's the flow's shared source of truth, and a malformed edit breaks every command that reads it.

## The commands

```bash
kivax task add <agent> "<step>" "<step>" ...   # declare your plan (all start as todo)
kivax task list                                # the current phase's list + the resume point
kivax task next                                # just the item to resume at
kivax task set <id> doing                      # starting this one
kivax task set <id> done                       # finished it
kivax task set <id> skipped --note "why"       # legitimately not needed
kivax task clear <agent>                       # scrap your list and re-plan from scratch
```

Items are scoped to the phase they were created in and carry the agent that owns them, so the researcher's items and the spec-analyst's coexist in the `spec` phase without colliding. Ids are unique per feature: `kivax task set 7 done` is unambiguous without naming a phase or an agent. Lists are archived and restored with their feature, so `kivax feature switch` brings back exactly what you left.

## Protocol

1. **Before working, check for a list.** Run `kivax task list`. If items exist for you, you are **resuming**: read them, verify the `done` ones really are done (check the artifact on disk, don't trust the checkbox blindly — an item can be marked done a moment before the write that failed), and continue at the resume point. Do NOT start over, and do NOT add a duplicate list.
2. **If there's no list, plan.** `kivax task add <you> "..." "..."` with the steps you're about to take. Aim for 3-8 items: one per step that produces something checkable. "Write the spec" is not an item — it's the whole job. "Draft requirements for the cancellation window" is.
3. **Mark `doing` before you start an item**, not after. That single word is what tells the next session which item has half-finished work behind it — `kivax task next` returns a `doing` item ahead of any `todo`, precisely because that's the one that needs attention.
4. **Mark `done` immediately on finishing**, before moving to the next item. A batch of updates at the end is worthless: the interruption you're protecting against happens in the middle.
5. **Use `skipped --note "why"`** when a step turns out not to apply (`ARCHITECTURE.md` doesn't exist, the module has no tests yet). Silently leaving it `todo` makes the next session think there's work left.
6. **Re-plan when reality changes.** If what you find makes your plan wrong, `kivax task add` the new steps, or `kivax task clear <you>` and start the list again. A list that no longer matches what you're doing is worse than none — it will mislead whoever resumes.

## Hard rules

- **Tasks are not requirements.** A task is your private working step, disposable once the phase ends. A REQ is the flow's public contract, tracked with `kivax state set-req` and read by traceability. Never use one in place of the other: a task marked `done` proves nothing about a requirement, and no audit will ever look at it.
- **Never use your tool's own todo list for this.** Some runtimes have one built in; it lives in the assistant's context and dies with the session, which is the exact failure this exists to prevent. If you use it, mirror it here — the repo is the only state that survives.
- **The list is a record, not an authority.** If the list says an item is done and the artifact says otherwise, the artifact wins. Fix the list and say so.
- **Don't inflate it.** Twenty items for a small change is noise that makes the real resume point harder to find. If your work genuinely has one step, one item is fine — or skip the list and say why.
