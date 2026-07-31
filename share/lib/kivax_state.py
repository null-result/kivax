#!/usr/bin/env python3
"""Workflow state management (the file at paths.state, .kivax/state.yml by default).

The state lives in the repo, not in any agent's context: any new session picks
up the flow by reading this file.

Usage:
  kivax state show
  kivax state set-phase <phase>  # any phase in the config's pipeline, or 'done'
  kivax state set-req <REQ-ID|IT-ID> <pending|red|green|invalidated>
  kivax state sync-reqs   # adds the ACTIVE feature's new ids to the state
  kivax state gate <phase>  # prints 'human' or 'auto' per .kivax/config.yml
  kivax state next        # prints the phase after the current one ('done' at the end)

Features are created and switched with `kivax feature`, not here: this module
owns phase and per-requirement status, not the feature lifecycle. It owns the
SHAPE of the whole document, though — including the per-agent task lists that
`kivax task` reads and writes, since archiving a feature has to carry them.

Shape (version 2) — one ACTIVE feature (one per git branch), plus the archived
records of features already worked on:

    version: 2
    active:
      number: "02"
      slug: cancel-booking
      phase: tdd
      requirements: {REQ-02-001: {status: green, updated_at: ...}}
      tasks: {tdd: [{id: 1, agent: implementer, text: ..., status: doing}]}
      history: [...]
    features:
      "01": {slug: booking, phase: done, requirements: {...}, tasks: {...}, history: [...]}

`history` lives inside each feature record rather than at the top level on
purpose: with one active feature per branch, every branch appends to this file,
and a single shared list would conflict on every merge.
"""
import sys
from datetime import datetime, timezone

import yaml

from kivax_lib import TERMINAL_PHASE, active_feature, load_config, load_spec, path_of, pipeline_of

REQ_STATES = ["pending", "red", "green", "invalidated"]
# Task vocabulary lives here rather than in kivax_task because this module owns
# the shape of the state document (it archives and restores tasks with their
# feature). kivax_task imports these; the dependency only ever goes that way.
TASK_STATES = ["todo", "doing", "done", "skipped"]
OPEN_TASK_STATES = ("todo", "doing")


def resume_point(items: list[dict]) -> dict | None:
    """Where a fresh session picks up: whatever was in flight when the last one
    stopped, or else the first thing not yet started. An item left `doing`
    outranks a `todo` even if it sits later in the list — it's the one with
    half-finished work behind it. One definition, so 'state show', 'task list',
    and 'task next' can never disagree about where you left off."""
    for t in items:
        if t.get("status") == "doing":
            return t
    for t in items:
        if t.get("status") == "todo":
            return t
    return None


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def empty_state() -> dict:
    return {"version": 2, "active": None, "features": {}}


def load_state(root, cfg) -> dict:
    """Never fails on a missing file: an uninitialized project simply has no
    active feature yet, which the commands that need one report themselves."""
    p = path_of(root, cfg, "state")
    if not p.is_file():
        return empty_state()
    st = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    st.setdefault("version", 2)
    st.setdefault("active", None)
    st.setdefault("features", {})
    return st


def save_state(root, cfg, state: dict) -> None:
    p = path_of(root, cfg, "state")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(state, allow_unicode=True, sort_keys=False),
                 encoding="utf-8")


def log(state: dict, msg: str) -> None:
    """Appends to the ACTIVE feature's history (no global history — see module
    docstring on merge conflicts)."""
    active = state.get("active")
    if not active:
        return
    active.setdefault("history", []).append({"at": now(), "event": msg})


def require_active(state: dict) -> dict:
    active = state.get("active")
    if not active or not active.get("number"):
        sys.exit("ERROR: no active feature. Start one with 'kivax feature new <slug>', "
                 "or resume an existing one with 'kivax feature switch <NN>'.")
    return active


# --------------------------------------------------------------------------- lifecycle
# Used by `kivax feature` in the CLI. Archiving happens ONLY here (on new/switch),
# never on `set-phase done`: a finished feature stays active so `kivax state show`
# and the kivax-status skill still have something to report.
def archive_active(state: dict) -> str | None:
    active = state.get("active")
    if not active or not active.get("number"):
        state["active"] = None
        return None
    num = str(active["number"])
    state.setdefault("features", {})[num] = {
        "slug": active.get("slug", ""),
        "phase": active.get("phase", ""),
        "requirements": active.get("requirements", {}) or {},
        "tasks": active.get("tasks", {}) or {},
        "history": active.get("history", []) or [],
    }
    state["active"] = None
    return num


def make_active(state: dict, number: str, slug: str, phase: str) -> None:
    """Starts a brand-new feature as the active one."""
    state["active"] = {"number": str(number), "slug": slug, "phase": phase,
                       "requirements": {}, "tasks": {}, "history": []}
    log(state, f"init feature {number}-{slug} (phase: {phase})")


def restore_active(state: dict, number: str, slug: str, fallback_phase: str) -> None:
    """Makes an existing feature active again, restoring its archived phase and
    per-requirement status if we have them."""
    prev = (state.get("features", {}) or {}).pop(str(number), None) or {}
    state["active"] = {
        "number": str(number),
        "slug": prev.get("slug") or slug,
        "phase": prev.get("phase") or fallback_phase,
        "requirements": prev.get("requirements", {}) or {},
        "tasks": prev.get("tasks", {}) or {},
        "history": prev.get("history", []) or [],
    }
    log(state, f"switched to feature {number}-{slug}")


# --------------------------------------------------------------------------- cli
def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    root, cfg = load_config()
    phases = pipeline_of(cfg) + [TERMINAL_PHASE]

    if cmd == "gate":
        phase = sys.argv[2] if len(sys.argv) > 2 else ""
        gates = cfg.get("gates", {}) or {}
        mode = gates.get(phase, "human")  # unconfigured = human (fail-safe)
        if mode not in ("human", "auto"):
            sys.exit(f"ERROR: gates.{phase} must be 'human' or 'auto', not '{mode}'")
        print(mode)
        return 0

    if cmd == "init":
        sys.exit("'kivax state init' is gone: a feature is now a directory of its own.\n"
                 "Use 'kivax feature new <slug>' instead — it allocates the feature "
                 "number,\ncreates <paths.features>/<NN>-<slug>/, seeds spec.md, and "
                 "makes it active.")

    state = load_state(root, cfg)

    if cmd == "show":
        print(yaml.safe_dump(state, allow_unicode=True, sort_keys=False))
        active = state.get("active") or {}
        if active.get("number"):
            print(f"Active feature: {active['number']}-{active.get('slug', '')} "
                  f"(phase: {active.get('phase', '?')})")
        else:
            print("Active feature: none — 'kivax feature new <slug>' to start one.")
        counts: dict[str, int] = {}
        for info in (active.get("requirements") or {}).values():
            counts[info.get("status", "?")] = counts.get(info.get("status", "?"), 0) + 1
        print("Requirements:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
              or "no REQs yet")
        # The resume point, surfaced here because every session starts with
        # 'state show' — an agent interrupted mid-phase is invisible otherwise.
        phase_tasks = (active.get("tasks") or {}).get(active.get("phase", ""), [])
        open_tasks = [t for t in phase_tasks if t.get("status") in OPEN_TASK_STATES]
        if open_tasks:
            t = resume_point(phase_tasks)
            print(f"Open tasks in this phase: {len(open_tasks)} — resume at "
                  f"{t.get('id')}. {t.get('text', '')} <{t.get('agent', '?')}>"
                  f"\n  ('kivax task list' for the full list)")
        archived = state.get("features") or {}
        if archived:
            print("Archived features:", ", ".join(
                f"{n}-{r.get('slug', '')} ({r.get('phase', '?')})"
                for n, r in sorted(archived.items())))
        return 0

    if cmd == "next":
        current = require_active(state).get("phase", "")
        if current == TERMINAL_PHASE:
            print(TERMINAL_PHASE)
            return 0
        if current not in phases:
            sys.exit(f"ERROR: current phase '{current}' is not in the pipeline {phases}. "
                     f"Fix .kivax/state.yml or the 'pipeline' list in .kivax/config.yml.")
        idx = phases.index(current)
        print(phases[idx + 1] if idx + 1 < len(phases) else TERMINAL_PHASE)
        return 0

    if cmd == "set-phase":
        phase = sys.argv[2] if len(sys.argv) > 2 else ""
        if phase not in phases:
            sys.exit(f"Invalid phase '{phase}'. Valid (from the config's pipeline): {phases}")
        active = require_active(state)
        log(state, f"phase {active.get('phase')} -> {phase}")
        active["phase"] = phase
        save_state(root, cfg, state)
        print(f"Phase: {phase}")
        return 0

    if cmd == "set-req":
        if len(sys.argv) < 4:
            sys.exit("Usage: kivax state set-req <ID> <status>")
        rid, status = sys.argv[2], sys.argv[3]
        if status not in REQ_STATES:
            sys.exit(f"Invalid status '{status}'. Valid: {REQ_STATES}")
        active = require_active(state)
        reqs = active.setdefault("requirements", {})
        reqs.setdefault(rid, {})["status"] = status
        reqs[rid]["updated_at"] = now()
        log(state, f"{rid} -> {status}")
        save_state(root, cfg, state)
        print(f"{rid}: {status}")
        return 0

    if cmd == "sync-reqs":
        # The ONE place that must NOT span every feature: state tracks the
        # phase-driven work of the active feature. Pulling a shipped feature's
        # green requirements back in as `pending` would be wrong.
        require_active(state)
        feature = active_feature(root, cfg)
        if feature is None:
            sys.exit("ERROR: the active feature in state.yml has no matching directory "
                     "under paths.features. Run 'kivax feature list' to see what exists.")
        spec = load_spec(root, cfg, feature)
        ids = [r["id"] for r in spec.get("requirements", [])
               if r.get("status", "active") == "active"]
        ids += [s["id"] for s in spec.get("integration_scenarios", []) or []]
        reqs = state["active"].setdefault("requirements", {})
        added = 0
        for rid in ids:
            if rid not in reqs:
                reqs[rid] = {"status": "pending", "updated_at": now()}
                added += 1
        if added:
            log(state, f"sync-reqs: {added} new ids as pending")
        save_state(root, cfg, state)
        print(f"Synced {added} new ids for feature {feature.name}.")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
