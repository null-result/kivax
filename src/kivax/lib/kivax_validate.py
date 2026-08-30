#!/usr/bin/env python3
"""Validates the structure of every feature's spec.yml. Exits non-zero on errors.

Validation spans EVERY feature, not just the active one: ids must be unique
across the whole project (so a test tag resolves to exactly one requirement),
and depends_on / covers may legitimately point at a requirement in another
feature, so both are resolved against the union.

Usage: kivax validate
"""
import re
import sys

from .kivax_lib import feature_number_of_id, load_all_specs, load_config

# The canonical id form carries the owning feature's number: REQ-01-001,
# AC-01-001-01, IT-01-001. The VALIDATOR is strict about this, while the tag
# SCANNERS (id_tag_regexes, the wiki's SOURCE_RE) also accept the bare REQ-NNN
# form on purpose — that way a stray hand-written tag surfaces as an orphan in
# `kivax trace` instead of being invisible to the scan.
FF = r"\d{2,}"
REQ_ID = re.compile(rf"^REQ-{FF}-\d{{3}}$")
AC_ID = re.compile(rf"^AC-{FF}-\d{{3}}-\d{{2}}$")
IT_ID = re.compile(rf"^IT-{FF}-\d{{3}}$")
PRIORITIES = {"must", "should", "could"}
STATUSES = {"active", "deprecated"}

# Spec prose follows the project's configured spec_language (any value), so
# this heuristic only catches a couple of known languages and is best-effort.
VAGUE = re.compile(
    r"\b(fast|intuitive|easy|friendly|robust|efficient"
    r"|rápido|intuitivo|fácil|amigable|robusto|eficiente)\b", re.I)


def _check_spec(feature, spec: dict, errors: list, warns: list,
                reqs_by_id: dict, its_by_id: dict) -> None:
    """Per-feature structural checks. Populates the project-wide id maps that
    the cross-feature checks in main() then resolve against."""
    where = feature.name

    meta = spec.get("meta") or {}
    for field in ("feature", "version"):
        if not meta.get(field):
            errors.append(f"{where}: meta.{field} is required")

    reqs = spec.get("requirements") or []
    if not reqs:
        errors.append(f"{where}: the spec has no requirements")

    for i, req in enumerate(reqs):
        loc = f"{where}: requirements[{i}]"
        rid = req.get("id", "")
        if not REQ_ID.match(rid):
            errors.append(f"{loc}: id '{rid}' does not match REQ-FF-NNN "
                          f"(e.g. REQ-{feature.number}-001)")
            continue
        if feature_number_of_id(rid) != feature.number:
            errors.append(f"{loc}: id '{rid}' carries feature number "
                          f"'{feature_number_of_id(rid)}' but lives in {where}. The "
                          f"prefix must match the directory, or a test tagged '{rid}' "
                          f"would point at the wrong feature.")
            continue
        if rid in reqs_by_id:
            errors.append(f"{loc}: duplicate id {rid} (already declared by "
                          f"{reqs_by_id[rid][0].name})")
            continue
        reqs_by_id[rid] = (feature, req)

        if not req.get("title"):
            errors.append(f"{rid}: missing title")
        if not req.get("description"):
            errors.append(f"{rid}: missing description")
        if req.get("priority") not in PRIORITIES:
            errors.append(f"{rid}: priority must be one of {sorted(PRIORITIES)}")
        if req.get("status", "active") not in STATUSES:
            errors.append(f"{rid}: status must be one of {sorted(STATUSES)}")

        acs = req.get("acceptance_criteria") or []
        if req.get("status", "active") == "active" and not acs:
            errors.append(f"{rid}: an active requirement needs >=1 acceptance_criteria")
        for j, ac in enumerate(acs):
            acid = ac.get("id", "")
            if not AC_ID.match(acid):
                errors.append(f"{rid}.acceptance_criteria[{j}]: id '{acid}' does not "
                              f"match AC-FF-NNN-MM")
            elif not acid.startswith("AC-" + rid.removeprefix("REQ-") + "-"):
                errors.append(f"{rid}: AC '{acid}' does not belong to this requirement")
            for field in ("given", "when", "then"):
                if not ac.get(field):
                    errors.append(f"{rid}.{acid or j}: missing '{field}'")
            text = " ".join(str(ac.get(f, "")) for f in ("given", "when", "then"))
            if VAGUE.search(text):
                warns.append(f"{rid}.{ac.get('id')}: potentially unverifiable criterion "
                             f"(vague term: '{VAGUE.search(text).group(0)}')")

        if rid in (req.get("depends_on") or []):
            errors.append(f"{rid}: depends on itself")

    for i, sc in enumerate(spec.get("integration_scenarios") or []):
        loc = f"{where}: integration_scenarios[{i}]"
        sid = sc.get("id", "")
        if not IT_ID.match(sid):
            errors.append(f"{loc}: id '{sid}' does not match IT-FF-NNN "
                          f"(e.g. IT-{feature.number}-001)")
            continue
        if feature_number_of_id(sid) != feature.number:
            errors.append(f"{loc}: id '{sid}' carries a feature number that isn't {where}")
            continue
        if sid in its_by_id:
            errors.append(f"{loc}: duplicate id {sid} (already declared by "
                          f"{its_by_id[sid][0].name})")
            continue
        its_by_id[sid] = (feature, sc)

        if not (sc.get("covers") or []):
            errors.append(f"{sid}: missing 'covers' (the REQs it covers)")
        for field in ("given", "when", "then"):
            if not sc.get(field):
                errors.append(f"{sid}: missing '{field}'")


def main() -> int:
    root, cfg = load_config()
    pairs = load_all_specs(root, cfg)
    errors: list[str] = []
    warns: list[str] = []

    if not pairs:
        print("No features yet. Create one with 'kivax feature new <slug>'.")
        return 0

    reqs_by_id: dict[str, tuple] = {}
    its_by_id: dict[str, tuple] = {}
    uncompiled: list[str] = []
    for feature, spec in pairs:
        if spec is None:
            uncompiled.append(feature.name)
            continue
        _check_spec(feature, spec, errors, warns, reqs_by_id, its_by_id)

    # Cross-feature resolution: depends_on and covers may point at another
    # feature's requirements (features build on each other), so they only
    # resolve correctly against the union.
    for rid, (_feature, req) in reqs_by_id.items():
        for dep in req.get("depends_on") or []:
            if dep not in reqs_by_id:
                errors.append(f"{rid}: depends_on references nonexistent '{dep}'")
    for sid, (_feature, sc) in its_by_id.items():
        for rid in sc.get("covers") or []:
            if rid not in reqs_by_id:
                errors.append(f"{sid}: covers references nonexistent '{rid}'")

    # Dependency cycles, over the project-wide graph.
    graph = {rid: (req.get("depends_on") or []) for rid, (_f, req) in reqs_by_id.items()}
    seen: dict[str, int] = {}

    def dfs(node: str, path: list[str]) -> None:
        seen[node] = 1
        for nxt in graph.get(node, []):
            if seen.get(nxt) == 1:
                errors.append(f"dependency cycle: {' -> '.join(path + [nxt])}")
            elif seen.get(nxt, 0) == 0:
                dfs(nxt, path + [nxt])
        seen[node] = 2

    for node in graph:
        if seen.get(node, 0) == 0:
            dfs(node, [node])

    for name in uncompiled:
        print(f"NOTE   {name} has no spec.yml yet (not compiled)")
    for w in warns:
        print(f"WARN   {w}")
    for e in errors:
        print(f"ERROR  {e}")
    if errors:
        print(f"\nINVALID: {len(errors)} errors, {len(warns)} warnings.")
        return 1
    compiled = sum(1 for _f, s in pairs if s is not None)
    print(f"\nVALID: {len(reqs_by_id)} requirements, {len(its_by_id)} IT scenarios "
          f"across {compiled} feature(s), {len(warns)} warnings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
