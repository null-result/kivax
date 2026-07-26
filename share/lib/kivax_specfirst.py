#!/usr/bin/env python3
"""Spec-first check over the branch diff.

Classifies files changed relative to git.base_branch into:
  - tests        : match test_globs of some active profile
  - kivax        : flow artifacts (config, state, lock, the per-runtime agent
                   and skill files Kivax installs, and the spec/plan/wiki
                   deliverables declared in paths.* — their lifecycle is
                   governed by the kivax-spec, kivax-compile, and kivax-plan
                   skills, not this gate)
  - legacy       : match legacy_globs (pre-existing code NOT yet migrated
                   into the flow; exempt from REQ-traceability)
  - production   : everything else — every file here must be justified by
                   the plan's mapping (the trace-auditor cross-checks this
                   list against plan.md; a production file changed without a
                   traceable REQ is a spec-first violation)

Usage:
  kivax specfirst           # readable report
  kivax specfirst --json    # for agents
  kivax specfirst --base <branch>   # override base_branch
"""
import fnmatch
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

from kivax_lib import active_profiles, load_config


def matches_any(path: str, globs: list[str]) -> bool:
    p = PurePosixPath(path)
    for g in globs:
        if fnmatch.fnmatch(path, g) or p.match(g):
            return True
        # supports pathlib-style ** globs over relative paths
        if "**" in g and fnmatch.fnmatch(path, g.replace("**/", "*").replace("**", "*")):
            return True
    return False


def main() -> int:
    root, cfg = load_config()
    base = cfg.get("git", {}).get("base_branch", "main")
    if "--base" in sys.argv:
        base = sys.argv[sys.argv.index("--base") + 1]

    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            cwd=root, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(f"ERROR running git diff against '{base}': {e.stderr.strip()}\n"
                 f"Does the base branch exist? Adjust git.base_branch in .kivax/config.yml "
                 f"or use --base.")
    changed = [line.strip() for line in out.stdout.splitlines() if line.strip()]

    profiles = active_profiles(cfg)
    test_globs: list[str] = []
    for p in profiles:
        prefix = f"{p['root']}/" if p.get("root") else ""
        test_globs += [prefix + g for g in p.get("test_globs", [])]

    paths_cfg = cfg.get("paths", {})
    # Paths that belong to the Kivax flow itself, not project code: the
    # project data folder (.kivax/), the agent/skill files Kivax copies in for
    # each active runtime, the ambient context files, and any path explicitly
    # declared under paths.* in the config (spec, plan, wiki, constitution,
    # architecture...).
    #
    # .github/ is listed by its Kivax-owned subpaths only, never as a bare
    # prefix: that directory usually also holds CI workflows and issue
    # templates, which are the project's own files and stay auditable.
    kivax_prefixes = [".kivax/", ".claude/", ".opencode/", ".cursor/", ".codex/",
                      ".github/agents/", ".github/skills/",
                      ".github/copilot-instructions.md",
                      "CLAUDE.md", "AGENTS.md", ".gitignore"]
    # Directory-valued path entries get a trailing slash: `features: specs`
    # would otherwise make the bare prefix "specs" also swallow `specsomething/`,
    # letting real production files escape the audit.
    for raw in paths_cfg.values():
        value = str(raw)
        kivax_prefixes.append(value if value.endswith("/") or Path(value).suffix
                              else value + "/")
    legacy_globs = cfg.get("legacy_globs") or []

    buckets: dict[str, list[str]] = {"tests": [], "kivax": [], "legacy": [], "production": []}
    for f in changed:
        if any(f == pre or f.startswith(pre) for pre in kivax_prefixes):
            buckets["kivax"].append(f)
        elif matches_any(f, test_globs):
            buckets["tests"].append(f)
        elif matches_any(f, legacy_globs):
            buckets["legacy"].append(f)
        else:
            buckets["production"].append(f)

    if "--json" in sys.argv:
        print(json.dumps({"base": base, **buckets}, indent=2, ensure_ascii=False))
    else:
        print(f"Diff against '{base}': {len(changed)} files changed\n")
        labels = {"tests": "Tests (traced via REQ/IT tags)",
                  "kivax": "Kivax flow artifacts",
                  "legacy": "Legacy (exempt via legacy_globs)",
                  "production": "PRODUCTION — must be justified by the plan's mapping"}
        for key, label in labels.items():
            print(f"{label}: {len(buckets[key])}")
            for f in buckets[key]:
                print(f"  {f}")
        if buckets["production"]:
            print("\nThe trace-auditor must verify that every PRODUCTION file appears "
                  "in the REQ→module mapping in plan.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
