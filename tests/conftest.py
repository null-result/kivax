"""Shared fixtures for the whole suite.

Design note on why tests call code IN-PROCESS rather than via subprocess
(the previous tests/smoke.py did the latter): calling `kivax_cli.main()`
directly, with `sys.argv`/`builtins.input` monkeypatched and `SystemExit`
caught, exercises exactly the same code paths a real invocation would, is
fast, works identically on Windows/macOS/Linux, and — the reason that
actually matters here — lets coverage.py see the lines execute. A handful of
true subprocess tests remain in tests/e2e/test_subprocess_sanity.py as a
sanity check that the installed script itself runs; they aren't relied on
for coverage.

Every kivax_lib/kivax_validate/... module is imported exactly ONCE here, at
collection time, from its real path under share/lib/. This matters: if the
first `import kivax_lib` anywhere in the test run instead happened via
bin/kivax's `_lib()` (which inserts a *copied* store's lib/ onto sys.path),
Python would cache that copy as the module, and every line executed against
it afterwards — including from unit tests that assumed they were importing
the repo's own file — would be coverage-attributed to a temp-dir path that
gets deleted at teardown. Importing everything here first, before any test
runs, pins the module identity to the real repo files for the rest of the
session.
"""
import importlib.machinery
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
LIB_DIR = REPO / "share" / "lib"

sys.path.insert(0, str(LIB_DIR))

import kivax_hash as _kivax_hash_mod  # noqa: E402
import kivax_lessons as _kivax_lessons_mod  # noqa: E402
import kivax_specfirst as _kivax_specfirst_mod  # noqa: E402
import kivax_task as _kivax_task_mod  # noqa: E402
import kivax_trace as _kivax_trace_mod  # noqa: E402
import kivax_validate as _kivax_validate_mod  # noqa: E402
import kivax_wiki as _kivax_wiki_mod  # noqa: E402

import kivax_agents as _kivax_agents_mod  # noqa: E402
import kivax_lib as _kivax_lib_mod  # noqa: E402
import kivax_state as _kivax_state_mod  # noqa: E402


def _load_standalone(name: str, path: Path):
    """Imports a file with no importable package context — needed for
    bin/kivax (no .py suffix, so the default file finder can't infer a
    loader for it — SourceFileLoader is passed explicitly) and install.py (a
    top-level script, not part of the share/lib package)."""
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


_kivax_cli_mod = _load_standalone("kivax_cli", REPO / "bin" / "kivax")
_install_mod = _load_standalone("kivax_install", REPO / "install.py")


# --------------------------------------------------------------------------- module fixtures
@pytest.fixture
def kivax_cli():
    return _kivax_cli_mod


@pytest.fixture
def kivax_install():
    return _install_mod


@pytest.fixture
def klib():
    return _kivax_lib_mod


@pytest.fixture
def kvalidate():
    return _kivax_validate_mod


@pytest.fixture
def khash():
    return _kivax_hash_mod


@pytest.fixture
def ktrace():
    return _kivax_trace_mod


@pytest.fixture
def kwiki():
    return _kivax_wiki_mod


@pytest.fixture
def klessons():
    return _kivax_lessons_mod


@pytest.fixture
def kstate():
    return _kivax_state_mod


@pytest.fixture
def ktask():
    return _kivax_task_mod


@pytest.fixture
def kspecfirst():
    return _kivax_specfirst_mod


@pytest.fixture
def kagents():
    return _kivax_agents_mod


# --------------------------------------------------------------------------- invocation helpers
@pytest.fixture
def call():
    """call(some_main_function, *argv) -> whatever it returned, or whatever it
    called sys.exit(...) with (so a str message counts as failure, an int or
    None as its real exit code)."""
    def _call(fn, *argv):
        old_argv = sys.argv
        sys.argv = ["prog", *argv]
        try:
            return fn()
        except SystemExit as e:
            return e.code
        finally:
            sys.argv = old_argv
    return _call


@pytest.fixture
def feed_input(monkeypatch):
    """feed_input('y', '', 'n') makes every input() call return the next
    answer, and raise EOFError once they run out — the same behavior as
    piping a fixed block of lines into a real process's stdin."""
    def _feed(*answers):
        it = iter(answers)

        def fake_input(prompt: str = "") -> str:
            try:
                return next(it)
            except StopIteration:
                raise EOFError from None
        monkeypatch.setattr("builtins.input", fake_input)
    return _feed


# --------------------------------------------------------------------------- git / filesystem helpers
def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


@pytest.fixture
def git():
    return _git


@pytest.fixture
def repo_dir(tmp_path, monkeypatch) -> Path:
    """A bare git repo, cd'd into. Doesn't touch .kivax/ — use `project` for
    an already-`kivax init`-shaped one."""
    root = tmp_path / "proj"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    _git(root, "branch", "-M", "main")
    monkeypatch.chdir(root)
    return root


# --------------------------------------------------------------------------- global store
@pytest.fixture
def store(tmp_path) -> Path:
    """A throwaway copy of share/+bin/kivax — never install.py, which
    symlinks into ~/.local/bin and must not touch the real machine."""
    dst = tmp_path / "store"
    shutil.copytree(REPO / "share", dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (dst / "bin").mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / "bin" / "kivax", dst / "bin" / "kivax")
    return dst


@pytest.fixture
def use_store(monkeypatch, kivax_cli, store):
    """Points every one of kivax_cli's module-level path constants at a
    throwaway store, the same way KIVAX_HOME env var would at import time —
    except these are set post-import, since the module is imported once for
    the whole test session (see the module docstring)."""
    monkeypatch.setattr(kivax_cli, "KIVAX_HOME", store)
    monkeypatch.setattr(kivax_cli, "LIB", store / "lib")
    monkeypatch.setattr(kivax_cli, "RUNTIME", store / "runtime")
    monkeypatch.setattr(kivax_cli, "TEMPLATES", store / "templates")
    monkeypatch.setattr(kivax_cli, "STACK_CATALOG", store / "lib" / "stack_profiles.yml")
    monkeypatch.setattr(kivax_cli, "AGENTS_SRC", store / "agents")
    monkeypatch.setattr(kivax_cli, "AGENT_RUNTIMES_CFG", store / "lib" / "agent_runtimes.yml")
    monkeypatch.setattr(kivax_cli, "AGENT_CACHE", store / "_generated" / "agents")
    monkeypatch.setattr(kivax_cli, "AGENT_CACHE_BODY", store / "_generated" / "orchestrator-body.md")
    return store


# --------------------------------------------------------------------------- a scaffolded project
DEFAULT_INIT_ANSWERS = (
    "\n" + "\n" * 5           # runtimes: claude=default(yes), the rest default(no)
    + "y\n"                   # greenfield
    + "\n"                    # features root: default 'specs'
    + "\n"                    # spec_language: default 'en'
    + "python-pytest\n"       # manual stack profile (no markers found under tmp_path)
    + "\n"                    # base branch: default
)


@pytest.fixture(autouse=True)
def forge_cli_present(monkeypatch):
    """`kivax doctor` requires gh or glab, because the flow ends by opening a
    pull request and no git command can do that. Pinning it here keeps the
    suite from depending on whether the machine running it happens to have one
    installed — the tests that care about the check assert on _check_forge_cli
    directly (tests/unit/test_cli_helpers.py)."""
    import shutil
    real_which = shutil.which
    monkeypatch.setattr(shutil, "which",
                        lambda name, *a, **k: "/usr/bin/gh" if name == "gh"
                        else real_which(name, *a, **k))


@pytest.fixture
def uninitialized_project(repo_dir, use_store, kivax_cli, call, feed_input):
    """Straight out of 'kivax init': config and runtime files in place, but
    PRINCIPLES.md/ARCHITECTURE.md not written yet, so the project is still
    waiting on the kivax-setup skill and refuses to start a feature."""
    feed_input(*DEFAULT_INIT_ANSWERS.split("\n")[:-1])
    rc = call(kivax_cli.main, "init")
    assert rc == 0, f"fixture setup: kivax init failed: {rc!r}"
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-qm", "install kivax")
    return repo_dir


@pytest.fixture
def project(uninitialized_project):
    """A project ready to work: 'kivax init' plus the one-time setup the
    kivax-setup skill performs. Both documents are written by an assistant in
    real use, so their content is irrelevant here — only that they exist, which
    is what 'kivax feature new' gates on."""
    repo_dir = uninitialized_project
    (repo_dir / "PRINCIPLES.md").write_text("# Principles\n\n1. Spec first.\n", encoding="utf-8")
    (repo_dir / "ARCHITECTURE.md").write_text("# Architecture\n\nOne module.\n", encoding="utf-8")
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-qm", "kivax setup")
    return repo_dir


def write_spec_yml(root: Path, number: str, slug: str, *, title: str = "Behavior",
                   depends_on=None, extra_requirements=None) -> Path:
    """Writes a minimal, valid spec.yml for feature `number-slug` and returns
    its path. `extra_requirements`, if given, replaces the single default
    requirement with a caller-supplied list (each dict merged over sane
    defaults) — used by tests that need more than one REQ."""
    reqs = extra_requirements or [{}]
    out_reqs = []
    for i, override in enumerate(reqs, start=1):
        nnn = f"{i:03d}"
        req = {
            "id": f"REQ-{number}-{nnn}", "title": title, "status": "active",
            "priority": "must", "depends_on": depends_on or [],
            "description": "Observable behavior.",
            "acceptance_criteria": [{"id": f"AC-{number}-{nnn}-01", "given": "a state",
                                     "when": "an action", "then": "a result"}],
            "edge_cases": ["empty input"], "notes": "",
        }
        req.update(override)
        out_reqs.append(req)
    doc = {
        "meta": {"feature": slug, "version": 1, "status": "approved",
                 "source": f"specs/{number}-{slug}/spec.md"},
        "context": "Context.",
        "requirements": out_reqs,
        "integration_scenarios": [{
            "id": f"IT-{number}-001", "title": "End to end",
            "covers": [out_reqs[0]["id"]], "given": "system up",
            "when": "flow runs", "then": "result observed",
        }],
        "non_goals": ["Out of scope"],
    }
    d = root / "specs" / f"{number}-{slug}"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "spec.yml"
    p.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return p


@pytest.fixture
def spec_writer():
    return write_spec_yml


@pytest.fixture
def set_phase(call, kstate):
    """set_phase('done') — advances the active feature's phase without going
    through kivax_cli.main(..., "state", ...): that command is in
    bin/kivax's PASSTHROUGH set, dispatched via os.execv, which REPLACES the
    current process image. In a real install that's fine (kivax and
    kivax_state.py are separate processes); in-process, calling it through
    kivax_cli.main would kill the test runner itself. Going straight to
    kstate.main() exercises the same logic without the exec."""
    def _set(phase: str) -> None:
        rc = call(kstate.main, "set-phase", phase)
        assert rc == 0, f"set_phase({phase!r}) failed: {rc!r}"
    return _set


@pytest.fixture
def minimal_config():
    """A plain dict, the shape kivax_lib functions expect as `cfg` — for
    tests that call library functions directly without going through
    load_config()/an on-disk .kivax/config.yml."""
    def _cfg(**overrides) -> dict:
        base = {
            "version": 3,
            "runtimes": ["claude"],
            "spec_language": "en",
            "greenfield": True,
            # 'features' is the only path a project sets; the rest are derived
            # or fixed, so this dict mirrors what 'kivax init' actually writes.
            "paths": {"features": "specs"},
            "agents": {},
            "git": {"base_branch": "main"},
            "legacy_globs": [],
            "stack": {"active": ["python-pytest"], "profiles": {
                "python-pytest": {
                    "root": "", "test_globs": ["tests/**/*.py"],
                    "id_tag_regexes": [r'@pytest\.mark\.req\("(?P<id>(?:REQ|IT)-(?:\d{2,}-)?\d{3})"\)'],
                    "cmd_test_unit": "pytest -q", "cmd_test_it": "pytest -q -m it",
                },
            }},
        }
        base.update(overrides)
        return base
    return _cfg
