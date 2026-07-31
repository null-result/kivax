#!/usr/bin/env python3
"""The lessons store: what the flow learned while building, kept for next time.

The wiki answers "what does this system do" and is DERIVED from the spec: every
claim on a page traces back to a REQ. This store answers a different question —
"what went wrong last time, and what do we do about it" — and by construction it
has no REQ behind it. A bug that took three red/green cycles to pin down, a
migration that has to run before the test context boots, a library whose default
timeout is wrong for this project: none of that is specifiable behavior, so none
of it can live in the wiki without breaking the wiki's one rule. It lives here.

One lesson per file, under `paths.lessons`:

    specs/lessons/
      LSN-0001-migrations-before-context.md
      LSN-0002-flaky-clock-in-it.md

Ids are allocated by `kivax lessons new`, never by hand or by an agent — same
reason feature numbers are: an id that two lessons share stops being a reference.

Why the acknowledgment machinery below exists
---------------------------------------------
A knowledge store nobody reads is a diary. The thing that makes this one bind is
`check`: every lesson that still applies has to be named in the active feature's
`plan.md`, under `## Lessons applied`, with either how the plan honors it or an
explicit "not applicable, because ...". The trace-auditor runs that check as part
of the audit gate, so ignoring a lesson is a decision somebody has to write down,
not something that happens by forgetting. `relevant` is the read side: generous
on purpose (it doesn't path-filter unless asked), because a lesson you can't see
is one you're about to relearn.

Usage:
  kivax lessons list [--all] [--json]        # active lessons (--all includes retired)
  kivax lessons show <LSN-ID>
  kivax lessons new <slug> [--title "..."]   # allocates the next id, seeds the file
  kivax lessons relevant --phase <phase> [--paths a b ...] [--json]
  kivax lessons check [--json]               # are the applicable ones acknowledged in plan.md?
  kivax lessons lint [--strict] [--json]
"""
import fnmatch
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import yaml

from kivax_lib import (
    TERMINAL_PHASE,
    active_feature,
    load_config,
    pipeline_of,
)

LESSON_ID_RE = re.compile(r"^LSN-\d{4}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
STATUSES = ("active", "retired")

# The heading the acknowledgment lives under in plan.md. Fixed, not configurable:
# `check` greps for it, and the plan template ships with it already in place.
ACK_HEADING = "## Lessons applied"

# A path-ish token in plan.md: the REQ→modules mapping writes real file and
# directory paths, which is what lets a path-scoped lesson know it applies to a
# plan before a single line of that plan's code exists.
PATH_TOKEN_RE = re.compile(r"[A-Za-z0-9_.\-/]+/[A-Za-z0-9_.\-/*]+|[A-Za-z0-9_.\-]+\.[A-Za-z0-9]{1,5}")


def lessons_dir(root: Path, cfg: dict) -> Path:
    """Where the store lives. Defaults under the features root rather than
    inside `.kivax/` because these are documents people read and review in a
    PR, not flow bookkeeping."""
    paths = cfg.get("paths", {}) or {}
    if "lessons" in paths:
        return root / paths["lessons"]
    features = paths.get("features", "specs")
    return root / features / "lessons"


def _now_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def parse_lesson(path: Path) -> tuple[dict | None, str]:
    """(frontmatter, body). frontmatter is None when the file has none or it
    isn't a yaml mapping — reported by lint rather than raising, so one bad
    file doesn't take down every other command."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None, parts[2]
    return (fm if isinstance(fm, dict) else None), parts[2]


def load_lessons(root: Path, cfg: dict) -> list[dict]:
    """Every lesson on disk, as {'path', 'rel', 'fm', 'body'}, ordered by id.

    Never fails on a malformed file: it comes back with `fm: None` and lint is
    what complains. The consuming commands (`relevant`, `check`) skip those —
    enforcing an unreadable lesson would block the flow on a typo.
    """
    d = lessons_dir(root, cfg)
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.rglob("*.md")):
        if p.name.startswith("_"):
            continue  # _index.md and friends: navigation, not lessons
        fm, body = parse_lesson(p)
        out.append({"path": p, "rel": p.relative_to(root).as_posix(),
                    "fm": fm, "body": body})
    return sorted(out, key=lambda x: ((x["fm"] or {}).get("id") or "", x["rel"]))


def is_active(entry: dict) -> bool:
    fm = entry.get("fm") or {}
    return bool(fm.get("id")) and fm.get("status", "active") == "active"


def matches_any(path: str, globs: list[str]) -> bool:
    """Same glob semantics as the spec-first check, so a project only has one
    kind of path pattern to learn."""
    p = PurePosixPath(path)
    for g in globs:
        if fnmatch.fnmatch(path, g) or p.match(g):
            return True
        if "**" in g and fnmatch.fnmatch(path, g.replace("**/", "*").replace("**", "*")):
            return True
    return False


def _summary(entry: dict) -> dict:
    fm = entry.get("fm") or {}
    return {
        "id": fm.get("id"), "title": fm.get("title", ""),
        "status": fm.get("status", "active"),
        "phases": list(fm.get("phases") or []),
        "paths": list(fm.get("paths") or []),
        "tags": list(fm.get("tags") or []),
        "origin": fm.get("origin") or {},
        "seen_in": list(fm.get("seen_in") or []),
        "file": entry["rel"],
    }


# --------------------------------------------------------------------------- applicability
def changed_files(root: Path, cfg: dict) -> list[str]:
    """Files on this branch vs. the base. Empty (not an error) when git can't
    answer — on a fresh branch with no base yet, `check` should degrade to
    "only project-wide lessons apply", not refuse to run."""
    base = (cfg.get("git", {}) or {}).get("base_branch", "main")
    try:
        out = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"],
                             cwd=root, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def plan_paths(plan_file: Path) -> list[str]:
    """Path-like tokens mentioned in plan.md.

    This is what makes a path-scoped lesson fire at PLAN time, before the code
    it warns about exists: the plan's REQ→modules table already names the files
    the feature will touch. Deliberately over-inclusive — a false positive costs
    one line of "not applicable" in the plan, a false negative costs the bug
    again.
    """
    if not plan_file.is_file():
        return []
    text = plan_file.read_text(encoding="utf-8", errors="replace")
    return sorted({m.group(0) for m in PATH_TOKEN_RE.finditer(text)})


def applicable(entries: list[dict], candidates: list[str]) -> list[dict]:
    """Active lessons that this feature has to answer for: the project-wide ones
    (no `paths:`), plus the path-scoped ones whose globs match something the
    feature actually touches."""
    out = []
    for e in entries:
        if not is_active(e):
            continue
        globs = list((e["fm"] or {}).get("paths") or [])
        if not globs or any(matches_any(c, globs) for c in candidates):
            out.append(e)
    return out


def acknowledged_ids(plan_file: Path) -> set[str]:
    """Lesson ids named under `## Lessons applied` in plan.md.

    Scoped to that section on purpose: a plan that happens to mention LSN-0004
    in a paragraph about something else hasn't decided anything about it.
    """
    if not plan_file.is_file():
        return set()
    text = plan_file.read_text(encoding="utf-8", errors="replace")
    idx = text.find(ACK_HEADING)
    if idx < 0:
        return set()
    section = text[idx + len(ACK_HEADING):]
    # Up to the next heading of the same or higher level.
    end = re.search(r"^#{1,2} ", section, flags=re.MULTILINE)
    if end:
        section = section[:end.start()]
    return set(re.findall(r"\bLSN-\d{4}\b", section))


# --------------------------------------------------------------------------- commands
def cmd_list(root: Path, cfg: dict, argv: list[str]) -> int:
    entries = load_lessons(root, cfg)
    show_all = "--all" in argv
    rows = [e for e in entries if show_all or is_active(e)]
    if "--json" in argv:
        print(json.dumps([_summary(e) for e in rows], indent=2, ensure_ascii=False))
        return 0
    if not rows:
        print(f"No lessons yet in {lessons_dir(root, cfg).relative_to(root)}/ — "
              f"the retro phase writes them.")
        return 0
    for e in rows:
        s = _summary(e)
        scope = ", ".join(s["paths"]) if s["paths"] else "project-wide"
        flag = "" if s["status"] == "active" else f"  [{s['status']}]"
        print(f"{s['id'] or '(no id)'}  {s['title']}{flag}")
        print(f"    phases: {', '.join(s['phases']) or '-'} | scope: {scope}")
        print(f"    seen in: {', '.join(s['seen_in']) or s['origin'].get('feature', '-')} "
              f"| {s['file']}")
    return 0


def cmd_show(root: Path, cfg: dict, argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        sys.exit("Usage: kivax lessons show <LSN-ID>")
    wanted = argv[0].strip()
    for e in load_lessons(root, cfg):
        if (e["fm"] or {}).get("id") == wanted:
            print(e["path"].read_text(encoding="utf-8"))
            return 0
    sys.exit(f"ERROR: no lesson with id '{wanted}'. 'kivax lessons list' shows them all.")


def cmd_new(root: Path, cfg: dict, argv: list[str]) -> int:
    """Allocates the next id and seeds the file from the template.

    Ids come from here rather than from whoever is writing the lesson for the
    same reason feature numbers do: two lessons sharing an id would make every
    `## Lessons applied` reference ambiguous, and nothing downstream would
    notice. The highest id ever seen + 1, so deleting a lesson never frees its
    id for reuse.
    """
    if not argv or argv[0].startswith("-"):
        sys.exit("Usage: kivax lessons new <slug> [--title \"...\"]   "
                 "(slug in kebab-case, e.g. migrations-before-context)")
    slug = argv[0].strip().strip("/")
    if not SLUG_RE.match(slug):
        sys.exit(f"ERROR: '{slug}' isn't a valid slug. Use kebab-case: lowercase "
                 f"letters, digits and hyphens, starting with a letter or digit.")
    title = ""
    if "--title" in argv:
        try:
            title = argv[argv.index("--title") + 1]
        except IndexError:
            sys.exit("ERROR: --title needs a value")

    used = [int((e["fm"] or {}).get("id", "LSN-0000")[4:])
            for e in load_lessons(root, cfg)
            if LESSON_ID_RE.match(str((e["fm"] or {}).get("id", "")))]
    new_id = f"LSN-{(max(used) + 1) if used else 1:04d}"

    d = lessons_dir(root, cfg)
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"{new_id}-{slug}.md"
    if dest.exists():
        sys.exit(f"ERROR: {dest.relative_to(root)} already exists.")

    feature = active_feature(root, cfg)
    template = root / ".kivax" / "templates" / "lesson.template.md"
    body = (template.read_text(encoding="utf-8") if template.is_file()
            else _FALLBACK_TEMPLATE)
    body = (body.replace("LSN-XXXX", new_id)
                .replace("<title>", title or slug.replace("-", " "))
                .replace("<feature>", feature.name if feature else "")
                .replace("<date>", _now_date()))
    dest.write_text(body, encoding="utf-8")
    print(f"{new_id} created: {dest.relative_to(root)}\n"
          f"Fill in the frontmatter (phases, paths, tags) and the sections, then "
          f"run 'kivax lessons lint'.")
    return 0


def cmd_relevant(root: Path, cfg: dict, argv: list[str]) -> int:
    """What a phase should read before it starts.

    No path filtering unless the caller passes `--paths`: at plan time nobody
    knows yet which files the feature will touch, and a lesson withheld because
    of that is a lesson about to be relearned. `check` is where the filtering
    (and the enforcement) happens.
    """
    if "--phase" not in argv:
        sys.exit("Usage: kivax lessons relevant --phase <phase> [--paths a b ...] [--json]")
    phase = argv[argv.index("--phase") + 1] if len(argv) > argv.index("--phase") + 1 else ""
    known = pipeline_of(cfg) + [TERMINAL_PHASE]
    if phase not in known:
        sys.exit(f"ERROR: '{phase}' is not a phase in this project's pipeline {known}.")

    paths: list[str] = []
    if "--paths" in argv:
        for a in argv[argv.index("--paths") + 1:]:
            if a.startswith("--"):
                break
            paths.append(a)

    rows = []
    for e in load_lessons(root, cfg):
        if not is_active(e):
            continue
        declared = list((e["fm"] or {}).get("phases") or [])
        # No `phases:` at all (lint flags it) means "every phase" rather than
        # "no phase": a malformed lesson should be over-surfaced, not silenced.
        if declared and phase not in declared:
            continue
        globs = list((e["fm"] or {}).get("paths") or [])
        if paths and globs and not any(matches_any(c, globs) for c in paths):
            continue
        rows.append(e)

    if "--json" in argv:
        print(json.dumps([{**_summary(e), "body": e["body"].strip()} for e in rows],
                         indent=2, ensure_ascii=False))
        return 0
    if not rows:
        print(f"No lessons apply to the '{phase}' phase.")
        return 0
    print(f"{len(rows)} lesson(s) apply to the '{phase}' phase — read them before you start:\n")
    for e in rows:
        s = _summary(e)
        scope = ", ".join(s["paths"]) if s["paths"] else "project-wide"
        print(f"  {s['id']}  {s['title']}")
        print(f"      scope: {scope} | learned in: {s['origin'].get('feature', '?')} "
              f"({s['origin'].get('phase', '?')}) | {s['file']}")
    print(f"\nEvery one of these must appear in plan.md under '{ACK_HEADING}' — "
          f"either how you honor it, or why it doesn't apply. "
          f"'kivax lessons check' is what the audit runs.")
    return 0


def cmd_check(root: Path, cfg: dict, argv: list[str]) -> int:
    """The gate. Exit 1 when an applicable lesson isn't answered for in plan.md.

    This is the whole reason the store isn't write-only: a lesson can be
    dismissed, but only in writing, in the artifact a human reviews.
    """
    feature = active_feature(root, cfg)
    if feature is None:
        sys.exit("ERROR: no active feature. 'kivax lessons check' audits the active "
                 "feature's plan.md; start or switch to a feature first.")
    entries = load_lessons(root, cfg)
    candidates = changed_files(root, cfg) + plan_paths(feature.plan)
    todo = applicable(entries, candidates)
    acked = acknowledged_ids(feature.plan)
    missing = [e for e in todo if (e["fm"] or {}).get("id") not in acked]
    unreadable = [e["rel"] for e in entries if e["fm"] is None]

    report = {
        "feature": feature.name,
        "plan": feature.plan.relative_to(root).as_posix(),
        "applicable": [(e["fm"] or {}).get("id") for e in todo],
        "acknowledged": sorted(acked),
        "unacknowledged": [(e["fm"] or {}).get("id") for e in missing],
        "unreadable": unreadable,
        "passing": not missing,
    }
    if "--json" in argv:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1 if missing else 0

    print(f"Feature {feature.name} — {report['plan']}")
    print(f"Applicable lessons: {len(todo)}"
          + (f" ({', '.join(report['applicable'])})" if todo else ""))
    if unreadable:
        print(f"Unreadable lesson file(s), skipped: {', '.join(unreadable)} "
              f"(run 'kivax lessons lint')")
    if not missing:
        print("\nLESSONS: ACKNOWLEDGED")
        return 0
    print(f"\nNOT acknowledged in plan.md ({len(missing)}):")
    for e in missing:
        s = _summary(e)
        print(f"  {s['id']}  {s['title']}  <- {s['file']}")
    if not feature.plan.is_file():
        print(f"\n(There is no {report['plan']} yet — this feature hasn't reached the "
              f"'plan' phase. Nothing to fix until it does.)")
        print("\nLESSONS: NOT ACKNOWLEDGED")
        return 1
    print(f"\nAdd each one under '{ACK_HEADING}' in {report['plan']}, with how the plan "
          f"honors it or why it doesn't apply here. Dismissing a lesson is allowed; "
          f"dismissing it silently is not.")
    print("\nLESSONS: NOT ACKNOWLEDGED")
    return 1


def cmd_lint(root: Path, cfg: dict, argv: list[str]) -> int:
    """Structural check over the store. A lesson with no rule to follow, or with
    an id that collides with another's, is worse than no lesson at all."""
    strict = "--strict" in argv
    entries = load_lessons(root, cfg)
    known_phases = set(pipeline_of(cfg))
    problems: list[str] = []
    seen: dict[str, str] = {}
    ids = {(e["fm"] or {}).get("id") for e in entries if e["fm"]}

    for e in entries:
        rel, fm, body = e["rel"], e["fm"], e["body"]
        if fm is None:
            problems.append(f"{rel}: no readable yaml frontmatter")
            continue
        # `or ""` rather than a default: an empty `id:` / `title:` line parses
        # as None, and str(None) is the truthy string "None" — which would let
        # a blank field pass every check below.
        rid = str(fm.get("id") or "")
        if not LESSON_ID_RE.match(rid):
            problems.append(f"{rel}: id '{rid or '(missing)'}' must look like LSN-0007 "
                            f"('kivax lessons new <slug>' allocates it)")
        elif rid in seen:
            problems.append(f"{rel}: id {rid} is already used by {seen[rid]} — "
                            f"a duplicated id makes every reference to it ambiguous")
        else:
            seen[rid] = rel
        if not str(fm.get("title") or "").strip():
            problems.append(f"{rel}: missing title")
        status = fm.get("status", "active")
        if status not in STATUSES:
            problems.append(f"{rel}: status '{status}' must be one of {list(STATUSES)}")
        phases = fm.get("phases") or []
        if not isinstance(phases, list) or not phases:
            problems.append(f"{rel}: 'phases' must list at least one phase — a lesson "
                            f"nobody is told to read is a lesson nobody reads")
        else:
            for p in phases:
                if p not in known_phases:
                    problems.append(f"{rel}: phase '{p}' is not in this project's pipeline")
        origin = fm.get("origin") or {}
        if not isinstance(origin, dict) or not origin.get("feature"):
            problems.append(f"{rel}: 'origin.feature' is required — a lesson with no "
                            f"provenance can't be re-examined when it turns out wrong")
        if status == "retired":
            sup = fm.get("superseded_by")
            if sup and sup not in ids:
                problems.append(f"{rel}: superseded_by '{sup}' doesn't match any lesson")
            if not sup and not str(fm.get("retired_reason") or "").strip():
                problems.append(f"{rel}: a retired lesson needs 'superseded_by' or "
                                f"'retired_reason' — otherwise nobody knows if it stopped "
                                f"being true or just stopped being convenient")
        if not re.search(r"^##+\s*Rule\b", body, flags=re.MULTILINE | re.IGNORECASE):
            problems.append(f"{rel}: no '## Rule' section — a lesson without an "
                            f"actionable rule is a diary entry")

    if "--json" in argv:
        print(json.dumps({"lessons": len(entries), "problems": problems,
                          "passing": not problems}, indent=2, ensure_ascii=False))
    else:
        print(f"Lessons: {len(entries)}")
        for p in problems:
            print(f"  - {p}")
        print(f"\nLESSONS STORE: {'OK' if not problems else 'NEEDS ATTENTION'}")
    return 1 if (strict and problems) else 0


_FALLBACK_TEMPLATE = """---
id: LSN-XXXX
title: <title>
status: active
phases: [plan, tdd]
paths: []
tags: []
origin:
  feature: <feature>
  phase: tdd
  evidence: []
seen_in: [<feature>]
updated_at: <date>
---

## What happened

## Rule
"""

COMMANDS = {"list": cmd_list, "show": cmd_show, "new": cmd_new,
            "relevant": cmd_relevant, "check": cmd_check, "lint": cmd_lint}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return 1
    root, cfg = load_config()
    return COMMANDS[sys.argv[1]](root, cfg, sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
