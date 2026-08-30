"""kivax — Kivax CLI (spec-anchored SDD flow).

Usage:
  kivax init [--force]     Install/configure Kivax in the current project (wizard).
                             Copies agents/skills into the project as
                             real, editable, git-committed files — no symlinks.
  kivax feature <new|list|show|switch> [args]
                             Feature lifecycle. Kivax keeps ONE spec per feature,
                             each in its own directory under paths.features:
                               specs/01-booking/{spec.md,spec.yml,plan.md}
                             'new <slug>' allocates the next number and seeds it;
                             'show --json' is how the agents resolve paths;
                             'switch <NN>' picks which feature the flow drives
                             (one active feature per git branch).
  kivax upgrade [--dry-run] Re-copy the agents, skills, and templates from the
                             global store, replacing this project's copies and
                             removing any Kivax file that no longer exists
                             upstream. They're generated files, so this never
                             asks and never conflicts.
  kivax doctor               Diagnose the current project's installation.
  kivax version               Version of the installed global store.
  kivax task <add|list|set|next|clear> [args]
                             Per-agent task lists for the active feature, so an
                             interrupted session resumes mid-agent instead of
                             redoing the phase. 'list' shows the resume point.
  kivax lessons <list|show|new|relevant|check|lint> [args]
                             The lessons store: what past iterations cost.
                             'relevant --phase <p>' is what a phase reads before
                             working; 'check' is the audit gate (exit 1 when an
                             applicable lesson isn't answered for in plan.md).
  kivax validate|hash|trace|state|task|wiki|lessons|specfirst [args...]
                              Passes control to the matching script.

The global store — the agents, skills, templates, and stack catalog that init
and upgrade materialize into a project — ships inside the installed package,
so 'pip install --upgrade kivax' updates the CLI and the store as one thing.
KIVAX_HOME overrides it, which is how a contributor points the CLI at a
checkout's src/kivax/data.

Design note: Kivax owns the workflow. The phase sequence, the approval gates,
and the specialist agents that run each phase are fixed — they're what the tool
IS, not settings. The agent and skill files copied into your project are
GENERATED from the global store: commit them so a teammate's checkout has the
same flow, but don't edit them, because 'kivax upgrade' replaces them wholesale.
Everything a project genuinely needs to decide lives in .kivax/config.yml — and
that includes which model each agent runs on, via the 'agents:' block.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - pip guarantees it; a broken env doesn't
    sys.exit("ERROR: PyYAML is missing. Reinstall Kivax: pipx install --force kivax")

from . import DATA_DIR


def _default_store() -> Path:
    """Where the global store lives.

    Normally it's the `data/` directory inside this installed package, which is
    what makes `pip install --upgrade kivax` the entire upgrade path: the CLI
    and the store it reads ship as one artifact, so they cannot drift apart.
    KIVAX_HOME still overrides it — that's the contributor flow (point it at a
    checkout's src/kivax/data) and the escape hatch for anyone vendoring a
    modified store."""
    env = os.environ.get("KIVAX_HOME")
    return Path(env).expanduser() if env else DATA_DIR


def _cache_root() -> Path:
    """A writable directory for derived files.

    The packaged store lives in site-packages, which must be treated as
    read-only, so the rendered-agent cache can't go there. When KIVAX_HOME is
    set the user has handed us a writable store of their own, and keeping the
    cache inside it means two stores (a checkout and the installed package)
    never share one cache and serve each other stale renders."""
    if os.environ.get("KIVAX_HOME"):
        return KIVAX_HOME
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "kivax"


KIVAX_HOME = _default_store()
RUNTIME = KIVAX_HOME / "runtime"
TEMPLATES = KIVAX_HOME / "templates"
STACK_CATALOG = KIVAX_HOME / "stack_profiles.yml"

# Agents are not stored pre-rendered per runtime: AGENTS_SRC holds one
# canonical file per specialist (description + tools + body only), and
# AGENT_RUNTIMES_CFG declares the frontmatter shape each runtime needs.
# AGENT_CACHE is where they get rendered into on every 'init'/'upgrade' —
# regenerated fresh each time, never hand-edited.
AGENTS_SRC = KIVAX_HOME / "agents"
AGENT_RUNTIMES_CFG = KIVAX_HOME / "agent_runtimes.yml"
AGENT_CACHE = _cache_root() / "_generated" / "agents"
# Body-only orchestrator for AGENTS.md / copilot-instructions.md (runtimes that
# use an ambient context file instead of a dedicated agent directory).
AGENT_CACHE_BODY = _cache_root() / "_generated" / "orchestrator-body.md"

# Where install.py used to put the store, before Kivax was a pip package.
# Only read to warn that it's stale — never written to. A module constant so
# the suite can point it somewhere harmless instead of the real home dir.
LEGACY_STORE = Path.home() / ".kivax"


def agent_names() -> list[str]:
    """The specialists Kivax ships, from the canonical sources. The single
    answer to 'what can appear under agents: in config.yml'."""
    return sorted(p.stem for p in AGENTS_SRC.glob("*.md"))


def models_of(cfg: dict) -> dict[str, str]:
    """{agent_name: model} from the project config's `agents:` block, plus the
    reserved 'default' entry that applies to every agent without one of its own.

        agents:
          default:      {model: sonnet}
          orchestrator: {model: opus}

    Rendering, not runtime: the value is written into each agent file's
    frontmatter at init/upgrade, in whatever spelling the runtime expects.
    Kivax doesn't validate the string — model names are the assistant's
    vocabulary, and hardcoding a list here would go stale on their release
    schedule, not ours."""
    block = cfg.get("agents") or {}
    if not isinstance(block, dict):
        sys.exit("ERROR: 'agents' in .kivax/config.yml must be a mapping of "
                 "agent name -> {model: <model>}")
    out: dict[str, str] = {}
    for name, entry in block.items():
        if not isinstance(entry, dict):
            sys.exit(f"ERROR: agents.{name} in .kivax/config.yml must be a mapping "
                     f"like '{name}: {{model: opus}}'")
        model = entry.get("model")
        if model:
            out[str(name)] = str(model)
    default = out.pop("default", None)
    if default:
        for name in agent_names():
            out.setdefault(name, default)
    return out


def regenerate_agents(models: dict[str, str] | None = None) -> None:
    from .lib import kivax_agents
    cfg = kivax_agents.load_runtime_configs(AGENT_RUNTIMES_CFG)
    kivax_agents.generate_all(AGENTS_SRC, cfg, AGENT_CACHE, models or {})
    # Strip frontmatter from the orchestrator for runtimes that need a plain
    # markdown ambient context file (AGENTS.md, copilot-instructions.md).
    orch_src = AGENTS_SRC / "orchestrator.md"
    if orch_src.is_file():
        _, _, body = kivax_agents.parse_canonical(orch_src)
        AGENT_CACHE_BODY.parent.mkdir(parents=True, exist_ok=True)
        AGENT_CACHE_BODY.write_text(body.lstrip("\n"), encoding="utf-8")

PASSTHROUGH = {"validate", "hash", "trace", "state", "task", "wiki", "lessons", "specfirst"}

# Bumped when .kivax/config.yml changes shape in a way an existing project has
# to be told about. 'kivax doctor' compares it and says what to do; nothing
# rewrites a project's config automatically.
CONFIG_VERSION = 3


def klib_pipeline() -> list[str]:
    """The per-feature phase sequence, from kivax_lib."""
    from .lib.kivax_lib import PIPELINE
    return PIPELINE


def klib_setup_phases() -> list[str]:
    """The one-time project setup phases, from kivax_lib."""
    from .lib.kivax_lib import SETUP_PHASES
    return SETUP_PHASES

# (key, human label, default answer) — key is what ends up in .kivax/config.yml's
# 'runtimes' list and every runtime-keyed dict in this file. 'vscode-copilot' and
# 'copilot-cli' are deliberately distinct keys (never bare 'copilot'): they're
# different products (VS Code extension vs. terminal CLI) with different file
# conventions.
RUNTIME_CHOICES = [
    ("claude", "Claude Code", True),
    ("opencode", "opencode", False),
    ("cursor", "Cursor", False),
    ("vscode-copilot", "GitHub Copilot in VS Code", False),
    ("copilot-cli", "GitHub Copilot CLI", False),
    ("codex", "OpenAI Codex CLI", False),
]

SOURCE_MARKER_EXTS = {
    ".java", ".kt", ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rb", ".php",
    ".c", ".cpp", ".cs", ".rs", ".scala", ".swift",
}
SPEC_DIR_CANDIDATES = ["specs", "spec", "docs/specs", "docs/spec", "requirements",
                       "docs/requirements"]


# --------------------------------------------------------------------------- helpers
def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        try:
            ans = input(f"{prompt}{suffix}: ").strip()
        except EOFError:
            ans = ""
        if ans:
            return ans
        if default is not None:
            return default
        print("  (an answer is required)")


def ask_yesno(prompt: str, default: bool) -> bool:
    d = "Y/n" if default else "y/N"
    while True:
        try:
            ans = input(f"{prompt} [{d}]: ").strip().lower()
        except EOFError:
            ans = ""
        if not ans:
            return default
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("  please answer y/n")


def sh(cmd: list[str], cwd: Path) -> str:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)
        return r.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def require_kivax_home() -> None:
    """The store normally ships inside the package, so this can only fail when
    KIVAX_HOME points somewhere wrong — or, rarely, when an installer dropped
    the package data."""
    # The orchestrator is the sentinel, not VERSION: it's the agent the whole
    # flow enters through, so a store without it is unusable, whereas a store
    # without VERSION merely can't name itself ('kivax version' says unknown).
    if not (AGENTS_SRC / "orchestrator.md").is_file():
        hint = (f"KIVAX_HOME is set to {os.environ['KIVAX_HOME']!r}, which isn't a Kivax "
                f"store. Unset it to use the one that ships with the package."
                if os.environ.get("KIVAX_HOME") else
                "Reinstall Kivax: pipx install --force kivax")
        sys.exit(f"ERROR: can't find the Kivax global store at {KIVAX_HOME}.\n{hint}")


def require_project() -> tuple[Path, dict]:
    root = Path.cwd()
    config_path = root / ".kivax" / "config.yml"
    if not config_path.is_file():
        sys.exit("ERROR: .kivax/config.yml does not exist. Run 'kivax init' first.")
    return root, yaml.safe_load(config_path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- detection
def find_source_files(root: Path, limit: int = 20) -> list[Path]:
    out = []
    for p in root.rglob("*"):
        if len(out) >= limit:
            break
        if not p.is_file():
            continue
        parts = set(p.relative_to(root).parts)
        if parts & {".git", "node_modules", "target", "build", "dist", "venv",
                    ".venv", "__pycache__", ".kivax"}:
            continue
        if p.suffix in SOURCE_MARKER_EXTS:
            out.append(p)
    return out


def find_existing_specs_dir(root: Path) -> Path | None:
    """A directory that already looks like it holds specs — either Kivax's own
    per-feature layout (<dir>/NN-slug/spec.md) or a pre-existing corpus of loose
    markdown. Either way it's only a suggestion the human confirms."""
    for cand in SPEC_DIR_CANDIDATES:
        d = root / cand
        if d.is_dir() and (any(d.glob("*/spec.md")) or any(d.glob("*.md"))):
            return d
    return None


def detect_stacks(root: Path, catalog: dict) -> list[tuple[str, str]]:
    """Returns [(profile, relative_root)] detected via markers, searching the
    root and its first-level subdirectories (monorepo support)."""
    found: list[tuple[str, str]] = []
    search_dirs = [root] + [d for d in root.iterdir()
                            if d.is_dir() and d.name not in
                            {".git", "node_modules", ".kivax", "target", "build", "dist"}]
    for d in search_dirs:
        rel = "" if d == root else d.name
        for name, prof in catalog.items():
            if any((d / marker).exists() for marker in prof.get("detect_markers", [])):
                if (name, rel) not in found:
                    found.append((name, rel))
    return found


def detect_base_branch(root: Path) -> str:
    """The branch features are cut from and merged back into.

    'develop' wins when it exists, because Kivax's flow is gitflow's feature
    branch: `origin/HEAD` points at the published branch (usually `main`), and
    on a gitflow repo that's the release branch, not the integration one — a
    feature PR opened against it would be targeting production.
    """
    if any(_ref_exists(root, ref) for ref in
           ("refs/heads/develop", "refs/remotes/origin/develop")):
        return "develop"
    out = sh(["git", "symbolic-ref", "refs/remotes/origin/HEAD"], root)
    if out:
        return out.rsplit("/", 1)[-1]
    out = sh(["git", "branch", "--show-current"], root)
    return out or "main"


def _ref_exists(root: Path, ref: str) -> bool:
    try:
        return subprocess.run(["git", "show-ref", "--verify", "--quiet", ref],
                              cwd=root, capture_output=True).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# Gitflow's own name for what Kivax produces. Fixed, like the pipeline: the
# flow always cuts a feature branch, so a project choosing its own prefix would
# only make every doc, skill, and error message in the system wrong about
# itself. The base it branches FROM is configurable (git.base_branch) because
# that genuinely varies; what the branch is called does not.
BRANCH_PREFIX = "feature/"


# --------------------------------------------------------------------------- sync (copy-based)
def sync_pairs(runtimes: list[str], models: dict[str, str] | None = None) -> list[tuple[Path, Path]]:
    """(project_relative_path, upstream_source_path) for every file Kivax
    manages in a project. This is the single definition consumed by init,
    upgrade, and doctor, so all three agree on what's managed.

    There are two kinds of runtime-specific content: agents (specialist
    personas with isolated context — only for runtimes that support real
    subagent delegation) and skills (everything else, including the
    phase-driver workflows — SKILL.md is a cross-tool standard, so one set
    of files serves every runtime). Agents are generated fresh from the
    canonical sources on every call (cheap — regenerate_agents() just
    re-renders ~30 small files), so they're never stale relative to
    agents/*.md, agent_runtimes.yml, or the project's model choices."""
    regenerate_agents(models)
    runtimes_set = set(runtimes)
    pairs: list[tuple[Path, Path]] = []

    if "claude" in runtimes:
        pairs += [(Path(".claude/agents") / p.name, p)
                 for p in sorted((AGENT_CACHE / "claude").glob("*.md"))]
        # Claude Code doesn't read AGENTS.md natively (only CLAUDE.md) — so
        # CLAUDE.md is generated too, from the exact same source as AGENTS.md
        # below (same body, two destination filenames, never out of sync).
        pairs.append((Path("CLAUDE.md"), AGENT_CACHE_BODY))
    if "opencode" in runtimes:
        pairs += [(Path(".opencode/agent") / p.name, p)
                 for p in sorted((AGENT_CACHE / "opencode").glob("*.md"))]
    if "cursor" in runtimes:
        pairs += [(Path(".cursor/agents") / p.name, p)
                 for p in sorted((AGENT_CACHE / "cursor").glob("*.md"))]
    if "copilot-cli" in runtimes:
        pairs += [(Path(".github/agents") / p.name, p)
                 for p in sorted((AGENT_CACHE / "copilot-cli").glob("*.agent.md"))]
    if "vscode-copilot" in runtimes:
        pairs.append((Path(".github/copilot-instructions.md"), AGENT_CACHE_BODY))

    # AGENTS.md is the shared orchestrator body for every runtime that uses an
    # ambient context file (all except vscode-copilot, which uses copilot-
    # instructions.md — claude gets both AGENTS.md and CLAUDE.md, above). The
    # body is stripped of frontmatter since AGENTS.md is plain markdown, not
    # an agent definition file.
    if {"claude", "opencode", "cursor", "copilot-cli", "codex"} & runtimes_set:
        pairs.append((Path("AGENTS.md"), AGENT_CACHE_BODY))

    # Skills: 6 shared reference skills + 14 phase-driver skills, copied
    # unchanged into every active runtime's own skills directory.
    skill_dest_dirs: list[Path] = []
    if "claude" in runtimes:
        skill_dest_dirs.append(Path(".claude/skills"))
    if "opencode" in runtimes:
        skill_dest_dirs.append(Path(".opencode/skills"))
    if "cursor" in runtimes:
        skill_dest_dirs.append(Path(".cursor/skills"))
    if "codex" in runtimes:
        skill_dest_dirs.append(Path(".codex/skills"))
    if {"vscode-copilot", "copilot-cli"} & runtimes_set:
        skill_dest_dirs.append(Path(".github/skills"))
    for dest_dir in skill_dest_dirs:
        pairs += [(dest_dir / p.parent.name / p.name, p)
                 for p in sorted((RUNTIME / "skills").glob("*/SKILL.md"))]

    pairs += [(Path(".kivax/templates") / p.name, p)
             for p in sorted(TEMPLATES.glob("*"))]
    return pairs


def write_managed(root: Path, pairs: list[tuple[Path, Path]]) -> tuple[list[Path], list[Path]]:
    """Copies every managed file into the project, overwriting whatever is
    there. Returns (added, updated) — 'updated' counts only files whose bytes
    actually changed, so 'kivax upgrade' can report something honest.

    Overwriting is safe precisely because these files are generated: the flow
    is Kivax's, and the one thing a project legitimately varies about an agent
    — its model — comes from config.yml and is baked in at render time."""
    added, updated = [], []
    for rel, source in pairs:
        dest = root / rel
        data = source.read_bytes()
        if not dest.is_file():
            added.append(rel)
        elif dest.read_bytes() != data:
            updated.append(rel)
        else:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return added, updated


# Directories whose entire contents Kivax owns. Anything inside one of these
# that isn't in sync_pairs() was put there by a Kivax version that shipped it
# and no longer does — a renamed skill, a retired agent — and has to go, or the
# assistant keeps reading a phase driver that the flow no longer references.
# These are the exact destination dirs used in sync_pairs(); nothing else in
# the project is ever pruned.
MANAGED_DIRS = [
    Path(".claude/agents"), Path(".claude/skills"),
    Path(".opencode/agent"), Path(".opencode/skills"),
    Path(".cursor/agents"), Path(".cursor/skills"),
    Path(".codex/skills"),
    Path(".github/agents"), Path(".github/skills"),
    Path(".kivax/templates"),
]


def prune_managed(root: Path, pairs: list[tuple[Path, Path]]) -> list[Path]:
    """Deletes files under MANAGED_DIRS that this version doesn't ship, plus
    any directory left empty by that. Returns what was removed."""
    keep = {(root / rel).resolve() for rel, _ in pairs}
    removed: list[Path] = []
    for rel_dir in MANAGED_DIRS:
        base = root / rel_dir
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.resolve() not in keep:
                removed.append(p.relative_to(root))
                p.unlink()
        # Deepest-first, so a skill directory emptied above disappears too.
        for d in sorted((p for p in base.rglob("*") if p.is_dir()), reverse=True):
            if not any(d.iterdir()):
                d.rmdir()
    return removed


# --------------------------------------------------------------------------- kivax init
def cmd_init(argv: list[str]) -> int:
    require_kivax_home()
    root = Path.cwd()
    kivax_dir = root / ".kivax"
    config_path = kivax_dir / "config.yml"
    force = "--force" in argv

    if config_path.is_file() and not force:
        print("'.kivax/config.yml' already exists in this project. Nothing to do here —\n"
              "use 'kivax upgrade' to pull updates from the global store, or\n"
              "'kivax doctor' to check the project's status.")
        return 0

    print("== Installing Kivax in this project ==\n")

    # 1) runtimes
    print("Which AI coding assistant(s) do you use in this project?")
    runtimes = []
    for key, label, default in RUNTIME_CHOICES:
        if ask_yesno(f"  Do you use {label}?", default):
            runtimes.append(key)
    if not runtimes:
        runtimes = [key for key, _, _ in RUNTIME_CHOICES]
        print("You picked none; I'll install for all supported runtimes just in case.")

    # 2) greenfield vs existing
    sources = find_source_files(root)
    heuristic_greenfield = len(sources) < 3
    print(f"\nI found {len(sources)}{'+' if len(sources) >= 20 else ''} source code "
          f"file(s) in this repo.")
    greenfield = ask_yesno("Is this a greenfield project (no meaningful existing code)?",
                           heuristic_greenfield)

    # 3) features folder — Kivax keeps ONE directory per feature under this
    # root (specs/01-booking/, specs/02-cancel/...), so it must be a folder
    # Kivax can own the layout of. If the project already has a corpus of loose
    # spec documents, point this somewhere else and keep that corpus as
    # reference material: Kivax never reads or migrates it.
    print("\nKivax keeps one spec per feature: one directory per feature "
          "(e.g. 01-booking/)\nholding its own spec.md, spec.yml, and plan.md, "
          "all under a single root folder.")
    existing_specs = None if greenfield else find_existing_specs_dir(root)
    if existing_specs:
        rel = existing_specs.relative_to(root)
        loose = [p.name for p in existing_specs.glob("*.md")]
        if loose:
            print(f"\nNOTE: '{rel}' already contains loose markdown "
                  f"({', '.join(loose[:3])}{'...' if len(loose) > 3 else ''}).\n"
                  f"Kivax won't read, move, or migrate those files — it would just "
                  f"create its\nper-feature directories alongside them. A separate "
                  f"folder is usually cleaner.")
        if ask_yesno(f"Use '{rel}' as the features root anyway?", not loose):
            specs_dir = rel.as_posix()
        else:
            specs_dir = ask("Where should the features root be?", "specs/features"
                            if loose else "specs")
    else:
        specs_dir = ask("\nWhere should the features root be?", "specs")
    specs_dir = specs_dir.strip("/")

    # 4) spec language — decoupled from every other language in the system
    # (the CLI, agents, and skills are always English; only the
    # prose CONTENT of spec.md follows this, regardless of what language you
    # write your requests in). Any value works: the spec-analyst translates
    # on the fly, no per-language files needed.
    spec_language = ask(
        "\nWhat language should spec.md content be written in? (e.g. en, es, fr, ja...)\n"
        "This only affects spec content, not this CLI or the agents themselves.",
        "en")

    # 5) stack
    catalog = yaml.safe_load(STACK_CATALOG.read_text(encoding="utf-8"))
    detected = [] if greenfield else detect_stacks(root, catalog)
    stack_profiles: dict[str, dict] = {}
    active: list[str] = []
    if detected:
        print("\nDetected stacks:")
        for name, rel in detected:
            label = catalog[name]["label"]
            where = rel or "(root)"
            print(f"  - {label}  [{where}]")
        if ask_yesno("Confirm these profiles?", True):
            for name, rel in detected:
                prof_name = name if not rel else f"{name}-{rel}"
                prof = {k: v for k, v in catalog[name].items() if k != "label"}
                prof["root"] = rel
                stack_profiles[prof_name] = prof
                active.append(prof_name)
    if not stack_profiles:
        print("\nAvailable profiles:", ", ".join(catalog.keys()))
        chosen = ask("Which profile to use? (comma-separate if several)", "java-spring")
        for name in [c.strip() for c in chosen.split(",") if c.strip()]:
            if name not in catalog:
                print(f"  '{name}' isn't in the catalog; adding it empty, edit it by hand later.")
                stack_profiles[name] = {"root": "", "test_globs": [], "id_tag_regexes": [],
                                        "cmd_test_unit": "", "cmd_test_it": ""}
            else:
                prof = {k: v for k, v in catalog[name].items() if k != "label"}
                prof["root"] = ""
                stack_profiles[name] = prof
            active.append(name)

    # 6) git base branch
    base_branch = detect_base_branch(root)
    base_branch = ask("\nBase branch for PRs and diff comparisons", base_branch)

    # 7) legacy_globs (only if not greenfield)
    legacy_globs: list[str] = []
    if not greenfield:
        proposed = sorted({f"{rel}/**" if rel else "src/**"
                           for _, rel in (detected or [("", "src")])})
        # A pre-existing corpus of spec documents living OUTSIDE the features
        # root belongs here too. Those are documents, not production code, and
        # without this the first edit to one of them lands in the audit's
        # `production` bucket and reads as a spec-first violation. Skipped when
        # the corpus IS the features root, since everything under that root is
        # already recognized as a Kivax artifact.
        corpus_glob = None
        if existing_specs is not None:
            corpus_rel = existing_specs.relative_to(root).as_posix()
            if corpus_rel != specs_dir:
                corpus_glob = f"{corpus_rel}/**"
                proposed = sorted(set(proposed) | {corpus_glob})
        print(f"\nPre-existing files proposed as exempt from REQ-traceability "
              f"(legacy_globs): {proposed}")
        if corpus_glob:
            print(f"  '{corpus_glob}' covers the spec documents that were already in "
                  f"this project,\n  so editing one isn't reported as untraced code. "
                  f"Kivax's own features under\n  '{specs_dir}/' stay audited normally.")
        if ask_yesno("Use this proposal as-is?", True):
            legacy_globs = proposed
        else:
            raw = ask("Enter the globs separated by commas (empty = none)", "")
            legacy_globs = [g.strip() for g in raw.split(",") if g.strip()]
        print("Remember: once you migrate a zone (retroactive spec + tests), remove it from this list.")

    # 8) write config
    cfg = {
        "version": CONFIG_VERSION,
        "runtimes": runtimes,
        "spec_language": spec_language,
        # Whether this project started from no meaningful existing code —
        # the kivax-architecture skill uses this to decide whether to author
        # ARCHITECTURE.md from the intended stack or reverse-engineer it from
        # the codebase. Re-derive by hand if you ever need to flip it.
        "greenfield": greenfield,
        # 'features' is the root holding one directory per feature, and the
        # only path a project chooses. The filenames inside each directory
        # (spec.md / spec.yml / plan.md) and every other Kivax path are fixed —
        # feature discovery works by globbing, which varying names would break.
        "paths": {"features": specs_dir},
        # Which model each agent runs on. Empty means every agent inherits
        # whatever the assistant is already using. Add a 'default' entry to set
        # them all at once, then override the ones worth more:
        #   agents:
        #     default:      {model: sonnet}
        #     orchestrator: {model: opus}
        # Takes effect on the next 'kivax init'/'kivax upgrade', which is what
        # writes the model into the generated agent files.
        "agents": {},
        "git": {"base_branch": base_branch},
        "legacy_globs": legacy_globs,
        "stack": {"active": active, "profiles": stack_profiles},
    }
    kivax_dir.mkdir(exist_ok=True)
    config_path.write_text(
        "# Kivax project configuration. Generated by 'kivax init'; edit by hand anytime.\n"
        "# The phase pipeline, the approval gates, and the specialist agents are not\n"
        "# here: Kivax owns the workflow. What a project decides is below.\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8")

    # 9) features root + initial state. No spec.md is written here: at init
    # time no feature exists yet. The first one is created by
    # 'kivax feature new <slug>', which is also what allocates its number.
    (root / specs_dir).mkdir(parents=True, exist_ok=True)
    (kivax_dir / "state.yml").write_text(
        (TEMPLATES / "state.template.yml").read_text(encoding="utf-8"), encoding="utf-8")

    # 10) copy runtime files (agents, skills, orchestrator, templates) as real,
    # ordinary, git-committed files — no symlinks, so a teammate's checkout has
    # the flow without installing anything. They're generated: commit them,
    # read them, but change the flow upstream rather than in place, because
    # 'kivax upgrade' rewrites them from the store.
    write_managed(root, sync_pairs(runtimes, models_of(cfg)))

    print(f"""
== Installation complete ==
  Config:        .kivax/config.yml
  Features:      {specs_dir}/  (one directory per feature; content language: {spec_language})
  Runtime:       {', '.join(runtimes)} — copied into this project as real files
  Pipeline:      {' -> '.join(klib_pipeline())}

Next step: open your assistant in this project and ask it to set the project up (the 'kivax-setup' skill).
It writes PRINCIPLES.md and ARCHITECTURE.md with you — once, for the whole project, not per feature.
Then ask it to start your first feature (the 'kivax-new' skill), which creates {specs_dir}/01-<slug>/ with its own spec.md.
{"To migrate a legacy zone before touching it, ask your assistant to document the current behavior of <module> (the 'kivax-spec' skill)." if not greenfield else ""}
""")
    return 0


# --------------------------------------------------------------------------- kivax feature
# Feature lifecycle: allocating a number, creating the directory, seeding
# spec.md, and choosing which feature the phase workflow drives. Deliberately
# separate from 'kivax state', whose remit is phase and per-requirement status.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _lib():
    """The lib modules, imported on demand — they pull in PyYAML and are only
    needed by the subcommands that touch specs."""
    from .lib import kivax_lib, kivax_state
    return kivax_lib, kivax_state


def _next_feature_number(root: Path, cfg: dict, klib, kstate) -> str:
    """Highest number seen anywhere + 1. Scanning the LOCK's id prefixes too is
    what stops a number being reused after its directory was deleted — the same
    principle as never reusing a removed requirement's id."""
    used: set[int] = set()
    for f in klib.list_features(root, cfg):
        used.add(int(f.number))
    st = kstate.load_state(root, cfg)
    active = st.get("active") or {}
    if active.get("number"):
        used.add(int(active["number"]))
    for n in (st.get("features") or {}):
        try:
            used.add(int(n))
        except (TypeError, ValueError):
            continue
    lock = klib.load_lock(root, cfg)
    for kind in ("requirements", "integration_scenarios"):
        for rid in (lock.get(kind) or {}):
            ff = klib.feature_number_of_id(rid)
            if ff:
                used.add(int(ff))
    return f"{(max(used) + 1) if used else 1:02d}"


def _feature_payload(root: Path, cfg: dict, klib, kstate, feature) -> dict:
    st = kstate.load_state(root, cfg)
    active = st.get("active") or {}
    if str(active.get("number")) == feature.number:
        phase = active.get("phase", "")
    else:
        phase = ((st.get("features") or {}).get(feature.number) or {}).get("phase", "")
    def rel(p: Path) -> str:
        # POSIX form: this is an API the agents consume, and it must read the
        # same on every platform.
        return p.relative_to(root).as_posix()

    return {
        "number": feature.number, "slug": feature.slug, "name": feature.name,
        "dir": rel(feature.dir), "spec_md": rel(feature.spec_md),
        "spec_yml": rel(feature.spec_yml), "plan": rel(feature.plan),
        "phase": phase,
        "active": str(active.get("number")) == feature.number,
        "compiled": feature.spec_yml.is_file(),
    }


def cmd_feature(argv: list[str]) -> int:
    require_kivax_home()
    root, cfg = require_project()
    klib, kstate = _lib()
    sub = argv[0] if argv else ""
    rest = argv[1:]

    if sub == "new":
        if not rest or rest[0].startswith("-"):
            sys.exit("Usage: kivax feature new <slug>   (kebab-case, e.g. cancel-booking)")
        slug = rest[0].strip().strip("/")
        if not SLUG_RE.match(slug):
            sys.exit(f"ERROR: '{slug}' isn't a valid slug. Use kebab-case: lowercase "
                     f"letters, digits and hyphens, starting with a letter or digit.")
        st = kstate.load_state(root, cfg)
        active = st.get("active") or {}
        if active.get("number") and active.get("phase") != "done" and "--force" not in rest:
            sys.exit(f"ERROR: feature {active['number']}-{active.get('slug', '')} is still "
                     f"in progress (phase: {active.get('phase')}). Kivax drives one feature "
                     f"at a time per branch.\nFinish it, or pass --force to archive it as-is "
                     f"and start the new one anyway.")
        if any(f.slug == slug for f in klib.list_features(root, cfg)):
            sys.exit(f"ERROR: a feature with slug '{slug}' already exists.")

        # Setup is a precondition of the FIRST feature, not a step inside every
        # one. Blocking here is what makes it mandatory without costing a check
        # per feature: the plan phase reads both documents, so starting without
        # them means planning against principles nobody wrote down yet.
        pending = klib.pending_setup(root, cfg)
        if pending:
            missing = ", ".join(klib.paths_of(cfg)[p] for p in pending)
            sys.exit(f"ERROR: this project hasn't been set up yet — {missing} "
                     f"{'is' if len(pending) == 1 else 'are'} missing.\n"
                     f"Open your assistant in this project and ask it to set the "
                     f"project up (the 'kivax-setup' skill); it writes "
                     f"{'that document' if len(pending) == 1 else 'those documents'} "
                     f"once, with you. Then create the feature.")

        number = _next_feature_number(root, cfg, klib, kstate)
        fdir = klib.features_root(root, cfg) / f"{number}-{slug}"
        fdir.mkdir(parents=True, exist_ok=True)
        spec_md = fdir / "spec.md"
        if not spec_md.is_file():
            body = (TEMPLATES / "spec.template.md").read_text(encoding="utf-8")
            spec_md.write_text(body.replace("FF", number), encoding="utf-8")

        first_phase = klib.PIPELINE[0]
        archived = kstate.archive_active(st)
        kstate.make_active(st, number, slug, first_phase)
        kstate.save_state(root, cfg, st)
        if archived:
            print(f"Archived feature {archived} (it stays in state.yml and on disk).")
        print(f"Feature {number}-{slug} created.\n"
              f"  spec.md: {spec_md.relative_to(root).as_posix()}\n"
              f"  phase:   {first_phase}\n"
              f"  ids:     REQ-{number}-001, REQ-{number}-002, ... (IT-{number}-NNN "
              f"for integration scenarios)")
        return 0

    if sub == "list":
        features = klib.list_features(root, cfg)
        if not features:
            print("No features yet. Create one with 'kivax feature new <slug>'.")
            return 0
        lock = klib.load_lock(root, cfg)
        st = kstate.load_state(root, cfg)
        active_num = str((st.get("active") or {}).get("number") or "")
        for f in features:
            payload = _feature_payload(root, cfg, klib, kstate, f)
            if not f.spec_yml.is_file():
                detail = "not compiled yet"
            else:
                spec = yaml.safe_load(f.spec_yml.read_text(encoding="utf-8")) or {}
                hashes = klib.spec_hashes(spec)
                n = sum(len(t) for t in hashes.values())
                stale = sum(1 for kind, table in hashes.items()
                            for rid, h in table.items()
                            if (lock.get(kind, {}).get(rid) or {}).get("hash") not in (None, h))
                detail = f"{n} ids" + (f", {stale} STALE vs lock" if stale else "")
            mark = "*" if f.number == active_num else " "
            print(f"{mark} {f.name:<28} phase={payload['phase'] or '-':<14} {detail}")
        print("\n* = active feature (the one the phase workflow drives)")
        return 0

    if sub == "show":
        number = None
        if "--feature" in rest:
            number = rest[rest.index("--feature") + 1]
        feature = (klib.feature_by_number(root, cfg, number) if number
                   else klib.active_feature(root, cfg))
        if feature is None:
            msg = ("no active feature — start one with 'kivax feature new <slug>' "
                   "or resume one with 'kivax feature switch <NN>'")
            if "--json" in rest:
                print(json.dumps({"error": msg}, indent=2))
                return 1
            sys.exit(f"ERROR: {msg}")
        payload = _feature_payload(root, cfg, klib, kstate, feature)
        if "--json" in rest:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            for k, v in payload.items():
                print(f"{k}: {v}")
        return 0

    if sub == "switch":
        if not rest or rest[0].startswith("-"):
            sys.exit("Usage: kivax feature switch <NN> [--force]")
        feature = klib.feature_by_number(root, cfg, rest[0])
        st = kstate.load_state(root, cfg)
        active = st.get("active") or {}
        if str(active.get("number")) == feature.number:
            print(f"Feature {feature.name} is already active.")
            return 0
        if active.get("number") and active.get("phase") != "done" and "--force" not in rest:
            sys.exit(f"ERROR: feature {active['number']}-{active.get('slug', '')} is still "
                     f"in progress (phase: {active.get('phase')}). Switching now would "
                     f"leave it mid-flow.\nFinish it, or pass --force.")
        kstate.archive_active(st)
        kstate.restore_active(st, feature.number, feature.slug, klib.PIPELINE[0])
        kstate.save_state(root, cfg, st)
        print(f"Active feature: {feature.name} (phase: {st['active']['phase']})")
        return 0

    print("Usage: kivax feature <new|list|show|switch> [args]\n"
          "  new <slug>              allocate a number, create the directory, seed spec.md\n"
          "  list                    every feature with its phase and staleness\n"
          "  show [--feature NN] [--json]\n"
          "                          resolved paths for the active (or given) feature\n"
          "  switch <NN> [--force]   make an existing feature the active one")
    return 1


# --------------------------------------------------------------------------- kivax upgrade
def cmd_upgrade(argv: list[str]) -> int:
    """Re-materializes every Kivax-managed file from the global store.

    There is no merge, no conflict, and no manifest, because there is nothing
    to reconcile: agents and skills are rendered from upstream sources plus
    this project's config.yml, so upstream + config is always the whole truth
    about what they should contain. Whatever a project needs to differ about
    goes in config.yml, which upgrade never touches."""
    require_kivax_home()
    root, cfg = require_project()
    runtimes = cfg.get("runtimes", ["claude"])
    dry_run = "--dry-run" in argv

    pairs = sync_pairs(runtimes, models_of(cfg))
    if dry_run:
        # Compare without writing: same bookkeeping write_managed does, minus
        # the copy, so --dry-run and the real run can never disagree.
        added = [rel for rel, _ in pairs if not (root / rel).is_file()]
        updated = [rel for rel, src in pairs
                   if (root / rel).is_file() and (root / rel).read_bytes() != src.read_bytes()]
        keep = {(root / rel).resolve() for rel, _ in pairs}
        removed = [p.relative_to(root) for d in MANAGED_DIRS if (root / d).is_dir()
                   for p in sorted((root / d).rglob("*"))
                   if p.is_file() and p.resolve() not in keep]
    else:
        added, updated = write_managed(root, pairs)
        removed = prune_managed(root, pairs)

    for infinitive, past, items in (("add", "Added", added), ("update", "Updated", updated),
                                    ("remove", "Removed", removed)):
        print(f"{f'Would {infinitive}' if dry_run else past}: {len(items)}"
              + (f" — {', '.join(p.as_posix() for p in items)}" if items else ""))
    print(f"Unchanged: {len(pairs) - len(added) - len(updated)}")

    # 'kivax upgrade' deliberately never rewrites config.yml — a project's
    # answers are its own. Nothing here would fail on a stale one; new
    # requirements would just silently read as uncovered — so say so here,
    # where the user is already looking at what changed.
    for warning in _check_tag_regexes(cfg) + _check_config_version(cfg):
        print(f"\nWARNING: {warning}\n(edit .kivax/config.yml — upgrade never "
              f"rewrites it for you)")

    if dry_run:
        print("\n(--dry-run: nothing was written)")
    return 0


# --------------------------------------------------------------------------- kivax doctor
def _looks_like_botched_feature(d: Path) -> bool:
    """Whether a directory under paths.features that Kivax doesn't recognize is
    worth complaining about.

    A project may deliberately keep its own documentation under the same root —
    a pre-existing corpus of spec documents, say — and nagging about those on
    every run just teaches people to ignore `kivax doctor`. So only flag the
    case that is actually a mistake: a directory that was *meant* to be a
    feature, betrayed either by a leading digit (a mistyped number, `1-booking`
    or `01_booking`) or by carrying the spec files a feature would hold."""
    if d.name[:1].isdigit():
        return True
    return (d / "spec.md").is_file() or (d / "spec.yml").is_file()


def _check_features(root: Path, cfg: dict) -> list[str]:
    """Feature-layout and id invariants. These are the things that fail
    silently — a wrong answer rather than a crash — if nobody checks them."""
    problems: list[str] = []
    try:
        klib, kstate = _lib()
    except ImportError as e:  # pragma: no cover - broken install
        return [f"can't import the Kivax lib: {e}"]

    paths = cfg.get("paths", {}) or {}
    if "features" not in paths:
        return problems  # already reported as a missing required key
    base = root / paths["features"]
    if not base.is_dir():
        return [f"paths.features points at '{paths['features']}', which doesn't exist"]

    wiki_rel = str(paths.get("wiki", "")).rstrip("/")
    for d in sorted(base.iterdir()):
        if not d.is_dir() or klib.FEATURE_DIR_RE.match(d.name):
            continue
        if d.relative_to(root).as_posix() == wiki_rel:
            continue
        if not _looks_like_botched_feature(d):
            continue  # somebody's own documentation, deliberately co-located
        problems.append(f"{d.relative_to(root).as_posix()}/ looks like a feature directory Kivax "
                        f"can't read: the name must be NN-slug (two or more digits, a "
                        f"hyphen, then lowercase words) — e.g. 01-booking. As it stands "
                        f"it is invisible to validate, trace, and hash")

    features = klib.list_features(root, cfg)
    by_number: dict[str, list[str]] = {}
    for f in features:
        by_number.setdefault(f.number, []).append(f.name)
    for number, names in sorted(by_number.items()):
        if len(names) > 1:
            problems.append(f"duplicate feature number {number}: {', '.join(names)} — "
                            f"their ids would collide. Renumber the one that hasn't "
                            f"been merged yet (its tests aren't on the base branch, so "
                            f"rewriting its tags is still local and safe)")

    # Ids: unique project-wide, and each one's prefix must match its directory.
    seen: dict[str, str] = {}
    for feature in features:
        if not feature.spec_yml.is_file():
            continue
        try:
            spec = yaml.safe_load(feature.spec_yml.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            problems.append(f"{feature.spec_yml.relative_to(root).as_posix()} is not valid yml: {e}")
            continue
        for item in ((spec.get("requirements") or []) +
                     (spec.get("integration_scenarios") or [])):
            rid = item.get("id", "")
            if not rid:
                continue
            if rid in seen:
                problems.append(f"id '{rid}' is declared by both {seen[rid]} and "
                                f"{feature.name} — a test tagged '{rid}' would be ambiguous")
            seen[rid] = feature.name
            ff = klib.feature_number_of_id(rid)
            if ff is not None and ff != feature.number:
                problems.append(f"id '{rid}' lives in {feature.name} but carries feature "
                                f"number '{ff}'")

    # Lock entries whose feature no longer has a directory.
    numbers = {f.number for f in features}
    lock = klib.load_lock(root, cfg)
    stranded = sorted({rid for kind in ("requirements", "integration_scenarios")
                       for rid in (lock.get(kind) or {})
                       if (klib.feature_number_of_id(rid) or "") not in numbers
                       and klib.feature_number_of_id(rid)})
    if stranded:
        problems.append(f"the traceability lock holds ids whose feature directory is "
                        f"gone: {', '.join(stranded[:6])}"
                        f"{'...' if len(stranded) > 6 else ''}")

    # The highest-value check: id_tag_regexes live in THIS file and 'kivax
    # upgrade' never rewrites config.yml, so a project can silently keep
    # regexes that only match the old flat form. New REQ-FF-NNN tags would then
    # be invisible to the scan and every new requirement would read as
    # uncovered — a wrong answer, not an error.
    problems += _check_tag_regexes(cfg)

    # The active feature must resolve to a real directory.
    st = kstate.load_state(root, cfg)
    active = (st.get("active") or {})
    if active.get("number") and str(active["number"]) not in numbers:
        problems.append(f"state.yml's active feature is '{active['number']}-"
                        f"{active.get('slug', '')}' but no such directory exists under "
                        f"paths.features")
    return problems


def _check_tag_regexes(cfg: dict) -> list[str]:
    problems: list[str] = []
    stack = cfg.get("stack", {}) or {}
    profiles = stack.get("profiles", {}) or {}
    active = stack.get("active")
    names = [active] if isinstance(active, str) else list(active or [])
    for name in names:
        prof = profiles.get(name) or {}
        for rx in prof.get("id_tag_regexes", []) or []:
            try:
                compiled = re.compile(rx)
            except re.error as e:
                problems.append(f"profile '{name}': id_tag_regexes entry {rx!r} is not a "
                                f"valid regex ({e})")
                continue
            # A synthetic tag in each stack's own syntax isn't worth building;
            # testing the id fragment against a prefixed id is enough to tell
            # whether the pattern was updated for the per-feature form.
            if not re.search(r"\(\?:\\d\{2,\}-\)\?", rx) and "REQ-01-001" not in rx:
                probe = compiled.search('@Tag("REQ-01-001") REQ-01-001 [REQ-01-001] '
                                        'kivax:REQ-01-001 mark.req("REQ-01-001")')
                if probe is None:
                    problems.append(
                        f"profile '{name}': id_tag_regexes only match the old flat "
                        f"REQ-NNN form, so tags like REQ-01-001 are invisible and every "
                        f"new requirement will read as uncovered. Replace \\d{{3}} with "
                        f"(?:\\d{{2,}}-)?\\d{{3}} in: {rx}")
    return problems


# Keys a project's config.yml may still carry from before Kivax took ownership
# of the workflow. None of them break anything — they're simply ignored now —
# but a config that still lists a pipeline reads as if it controlled one, so
# doctor names each and says what replaced it.
OBSOLETE_CONFIG_KEYS = {
    "pipeline": "the phase sequence is fixed; every phase runs for every feature",
    "gates": "approval gates are fixed (spec/compile/plan/audit/retro ask a human, "
             "tdd/it don't)",
    "paths.wiki": "derived from paths.features",
    "paths.lessons": "derived from paths.features",
    "paths.state": "always .kivax/state.yml",
    "paths.lock": "always .kivax/traceability.lock.json",
    "paths.principles": "always PRINCIPLES.md",
    "paths.architecture": "always ARCHITECTURE.md",
    "paths.spec_md": "one spec per feature, under paths.features",
    "paths.spec_yml": "one spec per feature, under paths.features",
    "paths.plan": "one plan per feature, under paths.features",
    "git.branch_prefix": "branches are always kivax/<feature>",
}


# The flow's contract is that a feature ends as a pull request a human can
# review and merge. A pull request is a forge concept, not a git one: no git
# command opens one, so without a forge CLI the flow cannot deliver what it
# promises. Checked here rather than discovered at the plan phase, where the
# branch and commits already exist and the failure is expensive.
FORGE_CLIS = ("gh", "glab")


def _check_forge_cli() -> list[str]:
    if any(shutil.which(cli) for cli in FORGE_CLIS):
        return []
    return ["no forge CLI on PATH (looked for: " + ", ".join(FORGE_CLIS) + "). "
            "The plan phase opens the feature's draft pull request, and git alone "
            "cannot create one — install GitHub's 'gh' or GitLab's 'glab' and "
            "authenticate it ('gh auth login')"]


def _check_config_version(cfg: dict) -> list[str]:
    found = cfg.get("version")
    if found == CONFIG_VERSION:
        return []
    stale = [f"{key} ({why})" for key, why in OBSOLETE_CONFIG_KEYS.items()
             if _has_config_key(cfg, key)]
    stale += [f"stack.profiles.{name}.cmd_lint (never used by anything)"
              for name, prof in ((cfg.get("stack") or {}).get("profiles") or {}).items()
              if isinstance(prof, dict) and "cmd_lint" in prof]
    msg = (f".kivax/config.yml says version: {found!r}, but this Kivax expects "
           f"{CONFIG_VERSION}. Set 'version: {CONFIG_VERSION}' once you've reviewed it.")
    if stale:
        msg += ("\n    Keys that no longer do anything — delete them:\n      - "
                + "\n      - ".join(stale))
    return [msg]


def _has_config_key(cfg: dict, dotted: str) -> bool:
    node = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def cmd_doctor(argv: list[str]) -> int:
    require_kivax_home()
    root = Path.cwd()
    problems = []
    config_path = root / ".kivax" / "config.yml"
    if not config_path.is_file():
        print("NOT INSTALLED: .kivax/config.yml is missing in this project.")
        return 1
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    problems += _check_config_version(cfg)
    if "features" not in (cfg.get("paths") or {}):
        problems.append("missing paths.features in config.yml — it's the root Kivax "
                        "keeps one directory per feature under (e.g. 'specs')")

    # Model choices are the one thing config.yml says about agents, so a typo
    # here is silent: the agent renders with no model and nobody finds out.
    known_agents = set(agent_names())
    for name in (cfg.get("agents") or {}):
        if name != "default" and name not in known_agents:
            problems.append(f"agents.{name} in config.yml isn't a Kivax agent. "
                            f"Known: {', '.join(sorted(known_agents))}")

    pipeline = klib_pipeline()
    runtimes = cfg.get("runtimes", [])
    dir_checks = {
        "claude": [root / ".claude/agents", root / ".claude/skills"],
        "opencode": [root / ".opencode/agent", root / ".opencode/skills"],
        "cursor": [root / ".cursor/agents", root / ".cursor/skills"],
        "vscode-copilot": [root / ".github/skills"],
        "copilot-cli": [root / ".github/agents", root / ".github/skills"],
        "codex": [root / ".codex/skills"],
    }
    file_checks = {
        "claude": [root / "AGENTS.md"],
        "opencode": [root / "AGENTS.md"],
        "cursor": [root / "AGENTS.md"],
        "vscode-copilot": [root / ".github/copilot-instructions.md"],
        "copilot-cli": [root / "AGENTS.md"],
        "codex": [root / "AGENTS.md"],
    }
    for runtime in runtimes:
        for d in dir_checks.get(runtime, []):
            if not d.is_dir() or not any(d.iterdir()):
                problems.append(f"{d.relative_to(root).as_posix()} is empty or missing "
                                f"(missing 'kivax init'/'kivax upgrade'?)")
        for c in file_checks.get(runtime, []):
            if not c.is_file():
                problems.append(f"{c.relative_to(root).as_posix()} is missing")

    # Every phase needs its kivax-<phase> skill in each active runtime's skills
    # dir, or the flow dead-ends there at runtime. Since 'kivax upgrade' writes
    # all of them, a miss here means a file was deleted by hand or an upgrade
    # never ran after the store changed.
    skills_dirs = {
        "claude": Path(".claude/skills"), "opencode": Path(".opencode/skills"),
        "cursor": Path(".cursor/skills"), "codex": Path(".codex/skills"),
        "vscode-copilot": Path(".github/skills"), "copilot-cli": Path(".github/skills"),
    }
    checked: set[tuple[str, str]] = set()  # (skills_dir, phase) — copilot runtimes share a dir
    for runtime in runtimes:
        rel_dir = skills_dirs.get(runtime)
        if rel_dir is None:
            continue
        # Phase drivers, plus 'setup' — not a phase, but the entry point to the
        # project bootstrap, so without it there's no way to write the two
        # documents 'feature new' demands. A miss in either dead-ends the flow.
        for name in pipeline + klib_setup_phases() + ["setup"]:
            if (str(rel_dir), name) in checked:
                continue
            checked.add((str(rel_dir), name))
            if not (root / rel_dir / f"kivax-{name}" / "SKILL.md").is_file():
                problems.append(f"{rel_dir.as_posix()}/kivax-{name}/SKILL.md is missing, "
                                f"so the flow dead-ends at '{name}' — run 'kivax upgrade'")
        # 'git' is the merge/release/hotfix skill. It never runs as part of the
        # flow, so its absence dead-ends nothing — but the human who asks to
        # merge a reviewed PR would get an improvised answer instead of the
        # confirm-before-each-irreversible-step protocol.
        if not (root / rel_dir / "kivax-git" / "SKILL.md").is_file():
            problems.append(f"{rel_dir.as_posix()}/kivax-git/SKILL.md is missing, so "
                            f"merge/release/hotfix requests have no defined "
                            f"procedure — run 'kivax upgrade'")

    problems += _check_features(root, cfg)
    problems += _check_forge_cli()
    # A warning, not a problem: it says nothing about THIS project, and doctor's
    # exit code is what CI gates on.
    for line in _check_legacy_install():
        print(f"WARNING: {line}")

    # Not a problem on a freshly-init'd project — it's the next step. It only
    # becomes one once features exist, which means someone wrote a spec against
    # principles and an architecture that were never written down.
    from .lib.kivax_lib import list_features, paths_of, pending_setup
    pending = pending_setup(root, cfg)
    if pending:
        missing = ", ".join(paths_of(cfg)[p] for p in pending)
        note = (f"{missing} missing — run the 'kivax-setup' skill in your assistant "
                f"to write the project's principles and architecture")
        if list_features(root, cfg):
            problems.append(note + " (features already exist, so this should have "
                                   "happened before the first one)")
        else:
            print(f"NEXT STEP: {note}.")

    if problems:
        print("PROBLEMS FOUND:")
        for p in dict.fromkeys(problems):  # de-dupe (e.g. AGENTS.md checked by several runtimes)
            print(f"  - {p}")
        return 1
    print("OK: project installation looks correct.")
    return 0


def cmd_version(argv: list[str]) -> int:
    require_kivax_home()
    v = KIVAX_HOME / "VERSION"
    print(f"kivax store: {KIVAX_HOME}")
    print(f"version: {v.read_text(encoding='utf-8').strip() if v.is_file() else 'unknown'}")
    for line in _check_legacy_install():
        print(f"\nWARNING: {line}")
    return 0


def _check_legacy_install() -> list[str]:
    """Kivax used to be installed by cloning the repo and running install.py,
    which copied a store to ~/.kivax and symlinked a `kivax` script into
    ~/.local/bin or /usr/local/bin. Those files outlive a `pip install`, and if
    the old symlink sits earlier on PATH it keeps winning — so the user edits
    a spec with a new Kivax and runs an old one. Say so rather than let them
    debug a version that doesn't match the one they installed."""
    if os.environ.get("KIVAX_HOME") or not (LEGACY_STORE / "lib" / "kivax_lib.py").is_file():
        return []
    msg = (f"a pre-2.1 installation is still at {LEGACY_STORE} (left by the old "
           f"install.py). It's no longer used — Kivax now ships its store inside "
           f"the package. Remove it with: rm -rf {LEGACY_STORE}")
    shadow = shutil.which("kivax")
    if shadow and not Path(shadow).resolve().is_relative_to(Path(sys.prefix)):
        msg += (f"\n  '{shadow}' also shadows the installed CLI on your PATH — "
                f"delete it too, or this warning is the last thing you'll see "
                f"from the new version.")
    return [msg]


def cmd_passthrough(name: str, argv: list[str]) -> int:
    """Hands the subcommand to its lib module as a fresh process.

    Still an exec rather than a call: these modules own their own exit codes
    and argument parsing, and replacing the process image keeps that contract
    exactly as it was when they were standalone scripts in the store."""
    require_kivax_home()
    module = f"{__package__}.lib.kivax_{name}"
    if importlib.util.find_spec(module) is None:
        sys.exit(f"ERROR: no module found for '{name}' ({module})")
    os.execv(sys.executable, [sys.executable, "-m", module, *argv])


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "init":
        return cmd_init(rest)
    if cmd == "feature":
        return cmd_feature(rest)
    if cmd == "upgrade":
        return cmd_upgrade(rest)
    if cmd == "doctor":
        return cmd_doctor(rest)
    if cmd == "version":
        return cmd_version(rest)
    if cmd == "link":
        sys.exit("'kivax link' isn't a command. Did you mean 'kivax upgrade'?")
    if cmd in PASSTHROUGH:
        return cmd_passthrough(cmd, rest)
    print(f"Unknown command: {cmd}\n")
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
