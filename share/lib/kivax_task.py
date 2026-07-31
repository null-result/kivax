#!/usr/bin/env python3
"""Per-agent task lists, so an interrupted session can be resumed mid-agent.

The flow already survives an interruption at two granularities: `kivax state`
knows which PHASE you're in, and the per-REQ status knows which requirements
are red/green. What neither knows is where a long-running agent got to INSIDE
one invocation — the researcher four sources into eight, the tech-planner
halfway through exploring the modules a REQ touches. That's what this file
tracks: an agent declares its plan up front, marks items off as it goes, and a
fresh session reads the list instead of redoing the work.

Usage:
  kivax task add <agent> <text> [<text> ...]  # append items for the current phase
  kivax task list [--phase P] [--agent A] [--json]
  kivax task set <id> <todo|doing|done|skipped> [--note "why"]
  kivax task next [--agent A]   # the item to resume at (first doing, else first todo)
  kivax task clear <agent>      # drop that agent's items in the current phase

Tasks hang off the ACTIVE feature, keyed by the phase they were created in, and
are archived and restored with it (`kivax feature switch`) exactly like the
per-REQ status. Ids are unique per feature, so `kivax task set 7 done` is
unambiguous without naming the phase or the agent.

Shape, inside state.yml's `active`:

    tasks:
      spec:                                   # the phase the items belong to
        - {id: 1, agent: researcher, text: "...", status: done, updated_at: ...}
        - {id: 2, agent: spec-analyst, text: "...", status: doing, updated_at: ...}

Deliberately NOT a substitute for `kivax state set-req`: a task is one agent's
private working step, disposable once its phase is finished. A requirement's
status is the flow's public contract, and traceability reads it.
"""
import json
import sys

from kivax_lib import load_config
from kivax_state import (
    OPEN_TASK_STATES,
    TASK_STATES,
    load_state,
    log,
    now,
    require_active,
    resume_point,
    save_state,
)


def tasks_of(active: dict, phase: str) -> list[dict]:
    """The active feature's task items for one phase (created empty on demand)."""
    return active.setdefault("tasks", {}).setdefault(phase, [])


def all_tasks(active: dict) -> list[dict]:
    """Every item across every phase, for id allocation and lookup."""
    return [t for items in (active.get("tasks") or {}).values() for t in items]


def next_id(active: dict) -> int:
    """Ids are per-feature and monotonic: a cleared list never reuses an id, so
    an id in a note or a commit message keeps pointing at one thing."""
    used = [int(t.get("id", 0)) for t in all_tasks(active)]
    return max(used, default=0) + 1


def find(active: dict, tid: int) -> tuple[str, dict] | None:
    for phase, items in (active.get("tasks") or {}).items():
        for t in items:
            if int(t.get("id", 0)) == tid:
                return phase, t
    return None


def format_item(t: dict) -> str:
    mark = {"todo": " ", "doing": "~", "done": "x", "skipped": "-"}.get(t.get("status", "todo"), "?")
    note = f"  ({t['note']})" if t.get("note") else ""
    return f"  [{mark}] {t.get('id')}. {t.get('text', '')}  <{t.get('agent', '?')}>{note}"


def _flag(argv: list[str], name: str) -> str | None:
    """Value of '--name X', or None. Unknown flags are the caller's problem."""
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
        sys.exit(f"ERROR: {name} needs a value")
    return None


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd, argv = sys.argv[1], sys.argv[2:]
    root, cfg = load_config()
    state = load_state(root, cfg)
    active = require_active(state)
    phase = active.get("phase", "")

    if cmd == "add":
        if len(argv) < 2:
            sys.exit("Usage: kivax task add <agent> <text> [<text> ...]")
        agent, texts = argv[0], argv[1:]
        items = tasks_of(active, phase)
        added = []
        for text in texts:
            tid = next_id(active)
            items.append({"id": tid, "agent": agent, "text": text,
                          "status": "todo", "updated_at": now()})
            added.append(tid)
        log(state, f"task add ({agent}, {phase}): {len(added)} item(s)")
        save_state(root, cfg, state)
        print(f"Added {len(added)} task(s) for {agent} in phase '{phase}': "
              f"{', '.join(str(i) for i in added)}")
        return 0

    if cmd == "list":
        want_phase = _flag(argv, "--phase") or phase
        want_agent = _flag(argv, "--agent")
        items = [t for t in tasks_of(active, want_phase)
                 if not want_agent or t.get("agent") == want_agent]
        if "--json" in argv:
            print(json.dumps({"feature": f"{active.get('number')}-{active.get('slug', '')}",
                              "phase": want_phase, "tasks": items,
                              "resume": resume_point(items)}, ensure_ascii=False, indent=2))
            return 0
        if not items:
            print(f"No tasks for phase '{want_phase}'"
                  f"{f' and agent {want_agent}' if want_agent else ''}.")
            return 0
        print(f"Phase '{want_phase}' ({active.get('number')}-{active.get('slug', '')}):")
        for t in items:
            print(format_item(t))
        open_items = [t for t in items if t.get("status") in OPEN_TASK_STATES]
        print(f"\n{len(items) - len(open_items)}/{len(items)} closed.")
        nxt = resume_point(items)
        if nxt:
            print(f"Resume at: {nxt['id']}. {nxt['text']}  <{nxt.get('agent', '?')}>")
        return 0

    if cmd == "set":
        if len(argv) < 2:
            sys.exit(f"Usage: kivax task set <id> <{'|'.join(TASK_STATES)}> [--note \"why\"]")
        try:
            tid = int(argv[0])
        except ValueError:
            sys.exit(f"ERROR: '{argv[0]}' is not a task id. 'kivax task list' shows them.")
        status = argv[1]
        if status not in TASK_STATES:
            sys.exit(f"Invalid status '{status}'. Valid: {TASK_STATES}")
        found = find(active, tid)
        if found is None:
            sys.exit(f"ERROR: no task with id {tid} in feature "
                     f"{active.get('number')}-{active.get('slug', '')}.")
        _, task = found
        note = _flag(argv, "--note")
        task["status"] = status
        task["updated_at"] = now()
        if note:
            task["note"] = note
        log(state, f"task {tid} -> {status}")
        save_state(root, cfg, state)
        print(f"{tid}: {status}")
        return 0

    if cmd == "next":
        want_agent = _flag(argv, "--agent")
        items = [t for t in tasks_of(active, phase)
                 if not want_agent or t.get("agent") == want_agent]
        nxt = resume_point(items)
        if nxt is None:
            print("No open tasks.")
            return 0
        print(f"{nxt['id']}. {nxt['text']}  <{nxt.get('agent', '?')}> [{nxt['status']}]")
        return 0

    if cmd == "clear":
        if not argv:
            sys.exit("Usage: kivax task clear <agent>")
        agent = argv[0]
        items = tasks_of(active, phase)
        kept = [t for t in items if t.get("agent") != agent]
        dropped = len(items) - len(kept)
        active["tasks"][phase] = kept
        log(state, f"task clear ({agent}, {phase}): {dropped} item(s)")
        save_state(root, cfg, state)
        print(f"Cleared {dropped} task(s) for {agent} in phase '{phase}'.")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
