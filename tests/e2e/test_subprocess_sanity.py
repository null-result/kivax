"""A small number of TRUE subprocess invocations of the real bin/kivax
script — everything else in this suite calls kivax_cli.main() in-process
(see conftest.py's module docstring for why: speed, cross-platform
consistency, and coverage.py visibility). Subprocess-executed code isn't
seen by our in-process coverage instrumentation, so these exist purely as a
belt-and-suspenders check that the actual standalone script — real argv, a
real __main__ guard, no monkeypatching — still works, independent of
whatever the in-process tests exercise.

Deliberately narrow: install.py itself (which symlinks into ~/.local/bin) is
exercised by the separate "install" job in .github/workflows/ci.yml, in a
disposable CI runner — not here, where it would touch the developer's own
machine.
"""
import json
import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.e2e


def _run(store, cwd, *args, stdin=None):
    env = {**os.environ, "KIVAX_HOME": str(store)}
    return subprocess.run([sys.executable, str(store / "bin" / "kivax"), *args],
                          cwd=cwd, capture_output=True, text=True, input=stdin, env=env)


def test_version_via_real_subprocess(store):
    r = _run(store, store, "version")
    assert r.returncode == 0
    assert "kivax store:" in r.stdout


def test_full_init_and_doctor_via_real_subprocess(store, repo_dir, git):
    answers = "\n" * 6 + "y\n" + "\n" + "\n" + "\n" + "python-pytest\n" + "\n"
    r = _run(store, repo_dir, "init", stdin=answers)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (repo_dir / ".kivax/config.yml").is_file()

    r = _run(store, repo_dir, "feature", "new", "checkout")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (repo_dir / "specs/01-checkout/spec.md").is_file()

    r = _run(store, repo_dir, "feature", "show", "--json")
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    assert payload["number"] == "01"

    r = _run(store, repo_dir, "doctor")
    assert r.returncode == 0
    assert "OK" in r.stdout


def test_unknown_command_via_real_subprocess(store):
    r = _run(store, store, "this-is-not-a-command")
    assert r.returncode == 1
    assert "Unknown command" in r.stdout
