#!/usr/bin/env python3
"""Lint for the knowledge wiki (LLM-wiki pattern over the Kivax specs).

For each page under wiki/, checks:
  - that it declares provenance (frontmatter 'sources' with ID@hash entries)
  - that referenced IDs exist in spec.yml and are not deprecated
  - that provenance hashes match the current ones in the spec
    (a different hash = stale page -> selective reingest of that page)

Usage:
  kivax wiki lint            # report; exit 0
  kivax wiki lint --strict   # exit 1 if there are problems
  kivax wiki lint --json     # JSON output (for agents)
  kivax wiki stale           # only stale pages (for the kivax-evolve skill)
"""
import json
import re
import sys
from pathlib import Path

import yaml

from kivax_lib import all_spec_hashes, load_all_specs, load_config

SOURCE_RE = re.compile(
    r"^(?P<id>(?:REQ|IT)-(?:\d{2,}-)?\d{3})@(?P<hash>sha256:[0-9a-f]{16})$")


def wiki_dir(root, cfg) -> Path:
    return root / cfg.get("paths", {}).get("wiki", "specs/wiki")


def parse_frontmatter(text: str) -> dict | None:
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1])
        return fm if isinstance(fm, dict) else None
    except yaml.YAMLError:
        return None


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("lint", "stale"):
        print(__doc__)
        return 1
    mode = sys.argv[1]
    strict = "--strict" in sys.argv
    as_json = "--json" in sys.argv

    root, cfg = load_config()
    wdir = wiki_dir(root, cfg)
    if not wdir.is_dir():
        print(f"{wdir.relative_to(root)} does not exist yet: the wiki hasn't been "
              f"initialized (use the kivax-wiki skill: ingest).")
        return 0

    # Across every feature: the wiki is project-wide and a single page routinely
    # cites requirements from several features. Checking one spec at a time
    # would report every cross-feature citation as a broken reference.
    hashes = all_spec_hashes(root, cfg)
    current = {**hashes["requirements"], **hashes["integration_scenarios"]}
    deprecated = {r["id"]
                  for _feature, spec in load_all_specs(root, cfg) if spec
                  for r in (spec.get("requirements") or [])
                  if r.get("status", "active") == "deprecated"}

    pages = [p for p in sorted(wdir.rglob("*.md")) if not p.name.startswith("_")]
    report = {"pages": len(pages), "stale": {}, "broken": {}, "no_provenance": [],
              "malformed": []}

    for page in pages:
        rel = str(page.relative_to(root))
        fm = parse_frontmatter(page.read_text(encoding="utf-8", errors="replace"))
        if fm is None:
            report["malformed"].append(rel)
            continue
        sources = fm.get("sources") or []
        ids_stale, ids_broken = [], []
        has_hashed_source = False
        for src in sources:
            if not isinstance(src, str) or src.startswith("plan:"):
                continue  # weak provenance (plan), no hash: not audited
            m = SOURCE_RE.match(src.strip())
            if not m:
                report["malformed"].append(f"{rel}: invalid source '{src}'")
                continue
            has_hashed_source = True
            rid, h = m.group("id"), m.group("hash")
            if rid not in current:
                ids_broken.append(f"{rid} (nonexistent)")
            elif rid in deprecated:
                ids_broken.append(f"{rid} (deprecated)")
            elif current[rid] != h:
                ids_stale.append(rid)
        if not has_hashed_source:
            report["no_provenance"].append(rel)
        if ids_stale:
            report["stale"][rel] = sorted(set(ids_stale))
        if ids_broken:
            report["broken"][rel] = sorted(set(ids_broken))

    if mode == "stale":
        out = report["stale"]
        print(json.dumps(out, indent=2, ensure_ascii=False) if as_json else
              ("\n".join(f"{p}: {', '.join(ids)}" for p, ids in out.items()) or
               "no stale pages"))
        return 0

    problems = bool(report["stale"] or report["broken"] or
                    report["no_provenance"] or report["malformed"])
    if as_json:
        report["passing"] = not problems
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Wiki pages: {report['pages']}")
        print(f"Stale (reingest needed): "
              f"{', '.join(report['stale']) if report['stale'] else 'none'}")
        for p, ids in report["stale"].items():
            print(f"  {p} <- {', '.join(ids)}")
        print(f"Broken references: "
              f"{', '.join(report['broken']) if report['broken'] else 'none'}")
        for p, ids in report["broken"].items():
            print(f"  {p} <- {', '.join(ids)}")
        print(f"No hashed provenance: "
              f"{', '.join(report['no_provenance']) or 'none'}")
        if report["malformed"]:
            print(f"Malformed: {'; '.join(report['malformed'])}")
        print(f"\nWIKI: {'UP TO DATE' if not problems else 'NEEDS ATTENTION'}")

    return 1 if (strict and problems) else 0


if __name__ == "__main__":
    sys.exit(main())
