#!/usr/bin/env python3
"""Traceability audit between spec and tests.

Scans test files (globs and regexes from the active stack profile(s) in
.kivax/config.yml), builds the ID -> tests mapping, and cross-checks it against
spec.yml and traceability.lock.json.

Usage:
  kivax trace                # audits; exit 1 if NOT PASSING
  kivax trace --report-only  # reports; always exit 0
  kivax trace --update-lock  # audits, and if PASSING, writes the lock
  kivax trace --json         # JSON output (for agents)
"""
import json
import re
import sys
from pathlib import Path

from kivax_lib import (
    active_profiles,
    all_spec_hashes,
    load_all_specs,
    load_config,
    load_lock,
    owner_of,
    save_lock,
)


def scan_tests(root: Path, profiles: list[dict]) -> dict[str, list[str]]:
    """Returns {ID: ['profile: file:line', ...]} for tagged REQ-IDs and IT-IDs.

    Each profile is scanned anchored to its own 'root' (subdirectory), to
    support monorepos with several stacks (e.g. backend + frontend) without
    one profile's globs leaking into the other's files.
    """
    found: dict[str, list[str]] = {}
    for profile in profiles:
        regexes = [re.compile(r) for r in profile.get("id_tag_regexes", [])]
        if not regexes:
            sys.exit(f"ERROR: profile '{profile['name']}' does not define id_tag_regexes")
        base = (root / profile["root"]) if profile.get("root") else root
        if not base.is_dir():
            sys.exit(f"ERROR: root '{profile['root']}' of profile '{profile['name']}' does not exist")
        for glob in profile.get("test_globs", []):
            for f in sorted(base.glob(glob)):
                if not f.is_file():
                    continue
                try:
                    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue
                # POSIX form: these strings are written into the committed
                # lock, so they must not differ between Windows and POSIX.
                rel = f.relative_to(root).as_posix()
                for n, line in enumerate(lines, 1):
                    for rx in regexes:
                        for m in rx.finditer(line):
                            found.setdefault(m.group("id"), []).append(
                                f"[{profile['name']}] {rel}:{n}")
    return found


def main() -> int:
    report_only = "--report-only" in sys.argv
    update_lock = "--update-lock" in sys.argv
    as_json = "--json" in sys.argv

    root, cfg = load_config()
    profiles = active_profiles(cfg)
    # The UNION of every feature's spec — this is the anchoring guarantee.
    # Editing the spec of a feature that shipped months ago still changes its
    # hashes here, so its tests are still flagged as potentially stale.
    pairs = load_all_specs(root, cfg)
    hashes = all_spec_hashes(root, cfg)
    owners = owner_of(root, cfg)
    lock = load_lock(root, cfg)
    tests = scan_tests(root, profiles)

    active_reqs: set[str] = set()
    its: set[str] = set()
    known: set[str] = set()
    for _feature, spec in pairs:
        if spec is None:
            continue
        for r in spec.get("requirements", []) or []:
            known.add(r["id"])
            if r.get("status", "active") == "active":
                active_reqs.add(r["id"])
        for s in spec.get("integration_scenarios", []) or []:
            known.add(s["id"])
            its.add(s["id"])

    def label(rid: str) -> str:
        f = owners.get(rid)
        return f"{rid} [{f.name}]" if f else rid

    problems: dict[str, list[str]] = {"uncovered": [], "stale": [], "orphaned": []}

    for rid in sorted(active_reqs | its):
        if not tests.get(rid):
            problems["uncovered"].append(label(rid))

    for kind in ("requirements", "integration_scenarios"):
        for rid, h in hashes[kind].items():
            locked = lock.get(kind, {}).get(rid)
            if locked and locked.get("hash") != h:
                problems["stale"].append(label(rid))

    for rid in sorted(tests):
        if rid not in known:
            problems["orphaned"].append(f"{rid} ({tests[rid][0]})")

    passing = not any(problems.values())

    if as_json:
        print(json.dumps({"passing": passing, "problems": problems,
                          "coverage": {k: v for k, v in sorted(tests.items())}},
                         indent=2, ensure_ascii=False))
    else:
        print(f"Active stack profile(s): {', '.join(p['name'] for p in profiles)}")
        print(f"Tagged tests found: {sum(len(v) for v in tests.values())} "
              f"({len(tests)} distinct IDs)\n")
        labels = {"uncovered": "Active IDs with NO test",
                  "stale": "IDs with a hash out of sync with the lock (tests possibly stale)",
                  "orphaned": "Tests with an ID that does not exist in the spec"}
        for key, label in labels.items():
            vals = problems[key]
            print(f"{label}: {', '.join(vals) if vals else 'none'}")
        print(f"\nVERDICT: {'PASSING' if passing else 'NOT PASSING'}")

    if update_lock:
        if not passing:
            print("Lock NOT updated: the audit is not passing.")
            return 1
        # Built from the union, so a rewrite keeps every feature's entries. The
        # lock stays a flat {id: {...}} map: ids are globally unique, and the
        # owning feature is derivable from the id's prefix.
        new_lock = {kind: {rid: {"hash": h, "tests": sorted(tests.get(rid, []))}
                           for rid, h in hashes[kind].items()}
                    for kind in ("requirements", "integration_scenarios")}
        # Guard against silent loss: this routine REPLACES the lock wholesale.
        # Two distinct ways an id can vanish from it, both refused:
        #
        #  - still declared by some spec, yet missing from the rebuild. That
        #    means `hashes` was narrower than the union — the regression this
        #    guard exists for. The next 'kivax hash --diff' would report those
        #    ids as `new`, which reads like ordinary work rather than a lost
        #    traceability baseline.
        #  - declared by no spec at all. Requirements are meant to be marked
        #    `status: deprecated`, never deleted outright, so this is either a
        #    hand-deleted requirement or an uncompiled feature.
        dropped = {rid for kind in ("requirements", "integration_scenarios")
                   for rid in (lock.get(kind) or {}) if rid not in new_lock[kind]}
        still_declared = sorted(rid for rid in dropped if rid in known)
        undeclared = sorted(rid for rid in dropped if rid not in known)
        if still_declared:
            print("\nERROR: refusing to write the lock — it would drop ids that are "
                  "still declared by a spec:\n  " + ", ".join(still_declared) +
                  "\nThat means the rebuild didn't span every feature. This is a bug; "
                  "the existing lock has been left untouched.")
            return 1
        if undeclared:
            print("\nERROR: refusing to write the lock — it would drop ids that no "
                  "spec declares:\n  " + ", ".join(undeclared) +
                  "\nRequirements are marked `status: deprecated`, not deleted, so the "
                  "baseline\nstays auditable. Recompile the affected feature, or remove "
                  "those entries from\nthe lock deliberately.")
            return 1
        p = save_lock(root, cfg, new_lock)
        print(f"Lock updated: {p.relative_to(root)} "
              f"({sum(len(v) for v in new_lock.values())} ids across "
              f"{sum(1 for _f, s in pairs if s is not None)} feature(s))")

    if report_only:
        return 0
    return 0 if passing else 1


if __name__ == "__main__":
    sys.exit(main())
