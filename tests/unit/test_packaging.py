"""The store ships inside the package, so 'is the store there?' stopped being
a question about the user's machine and became a question about the build.

These are the cheap structural checks: that DATA_DIR resolves next to the
imported package and still holds every kind of thing the flow reads. They
would catch a file moved out of src/kivax/data without its consumers being
updated. What they deliberately do NOT prove is that setuptools puts these
files into the wheel — a package-data glob can be wrong while the checkout is
perfectly fine. That check needs a real build and lives in the `package` job
of .github/workflows/ci.yml, which builds the wheel, inspects its contents,
and installs it into a clean virtualenv.
"""
from pathlib import Path

import pytest

import kivax

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]

def _pyproject() -> dict:
    """tomllib landed in 3.11 and the floor is 3.10. The tests that read
    pyproject.toml cross-check declarations that don't vary by interpreter, so
    skipping them on the oldest one costs nothing — and skipping only them,
    rather than the whole module, keeps the store checks running everywhere."""
    tomllib = pytest.importorskip("tomllib", reason="stdlib TOML parser needs Python 3.11+")
    return tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))


def test_data_dir_ships_with_the_package():
    assert kivax.DATA_DIR.is_dir()
    assert kivax.DATA_DIR.parent == Path(kivax.__file__).resolve().parent


@pytest.mark.parametrize("rel", [
    "VERSION",
    "stack_profiles.yml",
    "agent_runtimes.yml",
    "agents/orchestrator.md",
    "templates/spec.template.yml",
    "runtime/skills/kivax-setup/SKILL.md",
    "ci/github-actions-kivax.yml",
])
def test_store_holds_every_kind_of_asset(rel):
    assert (kivax.DATA_DIR / rel).is_file(), f"{rel} missing from the packaged store"


def test_version_is_a_plain_string():
    assert kivax.__version__ and kivax.__version__ != "unknown"
    assert "\n" not in kivax.__version__


def test_version_comes_from_the_same_file_the_cli_reports():
    """pyproject reads src/kivax/data/VERSION for the distribution version and
    `kivax version` reads it at runtime. If those ever diverge, `pip show
    kivax` and `kivax version` disagree — a bug report nobody can reproduce."""
    declared = _pyproject()["tool"]["setuptools"]["dynamic"]["version"]["file"]
    assert (REPO / declared).resolve() == (kivax.DATA_DIR / "VERSION").resolve()


def test_console_script_points_at_a_real_callable():
    assert _pyproject()["project"]["scripts"]["kivax"] == "kivax.cli:main"
    from kivax.cli import main
    assert callable(main)
