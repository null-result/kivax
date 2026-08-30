#!/usr/bin/env python3
"""Canonical spec hashes and diff against the traceability lock.

Usage:
  kivax hash            # table of current hashes
  kivax hash --diff     # diff vs traceability.lock.json
  kivax hash --diff --json  # diff as JSON (for agents)

The diff classifies each ID as: unchanged | modified | new | removed.
'modified' and 'new' are the ones that must (re)go through the TDD cycle.
"""
import json
import sys

from .kivax_lib import all_spec_hashes, feature_number_of_id, load_config, load_lock, owner_of


def compute_diff(current: dict, lock: dict) -> dict:
    out: dict = {}
    for kind in ("requirements", "integration_scenarios"):
        cur = current.get(kind, {})
        old = lock.get(kind, {})
        out[kind] = {
            "new": sorted(i for i in cur if i not in old),
            "modified": sorted(i for i in cur if i in old and old[i].get("hash") != cur[i]),
            "unchanged": sorted(i for i in cur if i in old and old[i].get("hash") == cur[i]),
            "removed": sorted(i for i in old if i not in cur),
        }
    return out


def main() -> int:
    root, cfg = load_config()
    # Repo-wide by default: hashes span every feature, which is what makes an
    # edit to an old, already-shipped spec show up as `modified` here.
    hashes = all_spec_hashes(root, cfg)
    owners = owner_of(root, cfg)

    only = None
    if "--feature" in sys.argv:
        only = str(sys.argv[sys.argv.index("--feature") + 1]).zfill(2)
        hashes = {kind: {rid: h for rid, h in table.items()
                         if owners.get(rid) and owners[rid].number == only}
                  for kind, table in hashes.items()}

    def owned(rid: str) -> str:
        f = owners.get(rid)
        return f"{rid} [{f.name}]" if f else rid

    if "--diff" not in sys.argv:
        for table in hashes.values():
            for rid, h in sorted(table.items()):
                f = owners.get(rid)
                print(f"{rid}\t{h}\t{f.name if f else '-'}")
        return 0

    lock = load_lock(root, cfg)
    if only:
        # Narrow the lock to the same feature, or every other feature's entries
        # would be reported as `removed`.
        lock = {kind: {rid: v for rid, v in (lock.get(kind) or {}).items()
                       if (feature_number_of_id(rid) or "") == only}
                for kind in ("requirements", "integration_scenarios")}
    diff = compute_diff(hashes, lock)

    if "--json" in sys.argv:
        # `owners` is a sibling map, not a change to the diff's shape: anything
        # already reading diff[kind][cat] as a list of ids keeps working.
        payload = dict(diff)
        payload["owners"] = {rid: f.name for rid, f in owners.items()}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for kind, d in diff.items():
            print(f"[{kind}]")
            for cat in ("new", "modified", "removed", "unchanged"):
                ids = d[cat]
                shown = [owned(i) for i in ids] if cat != "unchanged" else ids
                print(f"  {cat:9}: {', '.join(shown) if shown else '-'}")

    affected = sum(len(diff[k][c]) for k in diff for c in ("new", "modified", "removed"))
    return 0 if affected == 0 else 2  # 2 = there is pending work (not an error)


if __name__ == "__main__":
    sys.exit(main())
