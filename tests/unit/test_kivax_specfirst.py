"""Unit tests for share/lib/kivax_specfirst.py."""
import json

import pytest

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- matches_any
@pytest.mark.parametrize("path,globs,expected", [
    ("src/app.py", ["src/**"], True),
    ("src/nested/deep/app.py", ["src/**"], True),
    ("other/app.py", ["src/**"], False),
    ("tests/test_a.py", ["tests/**/*.py"], True),
    ("tests/test_a.js", ["tests/**/*.py"], False),
    ("README.md", [], False),
    ("exact/match.txt", ["exact/match.txt"], True),
])
def test_matches_any(kspecfirst, path, globs, expected):
    assert kspecfirst.matches_any(path, globs) is expected


# --------------------------------------------------------------------------- main()
def _init_git_repo(root, git):
    """Base branch 'main' with one commit, then a 'work' branch checked out —
    'git diff base...HEAD' is empty otherwise, since committing straight onto
    main leaves main and HEAD pointing at the same commit."""
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.invalid")
    git(root, "config", "user.name", "T")
    (root / ".gitkeep").write_text("")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "empty")
    git(root, "branch", "-M", "main")
    git(root, "checkout", "-qb", "work")


def _commit_all(root, git, msg):
    git(root, "add", "-A")
    git(root, "commit", "-qm", msg)


def test_buckets_kivax_tests_legacy_production(kspecfirst, call, tmp_path, minimal_config,
                                               monkeypatch, git, capsys):
    _init_git_repo(tmp_path, git)
    cfg = minimal_config(legacy_globs=["legacy/**"])
    monkeypatch.setattr(kspecfirst, "load_config", lambda: (tmp_path, cfg))

    (tmp_path / ".kivax").mkdir()
    (tmp_path / ".kivax/marker.txt").write_text("x")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_a.py").write_text("x")
    (tmp_path / "legacy").mkdir()
    (tmp_path / "legacy/old.py").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/app.py").write_text("x")
    _commit_all(tmp_path, git, "changes")

    rc = call(kspecfirst.main, "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert ".kivax/marker.txt" in payload["kivax"]
    assert "tests/test_a.py" in payload["tests"]
    assert "legacy/old.py" in payload["legacy"]
    assert "src/app.py" in payload["production"]


def test_paths_cfg_directory_entries_get_trailing_slash(kspecfirst, call, tmp_path, minimal_config,
                                                         monkeypatch, git, capsys):
    """features: specs must not let 'specsomething/' escape the kivax bucket
    via a bare-prefix match."""
    _init_git_repo(tmp_path, git)
    cfg = minimal_config()
    monkeypatch.setattr(kspecfirst, "load_config", lambda: (tmp_path, cfg))

    (tmp_path / "specsomething").mkdir()
    (tmp_path / "specsomething/app.py").write_text("x")
    (tmp_path / "specs" / "01-booking").mkdir(parents=True)
    (tmp_path / "specs/01-booking/plan.md").write_text("x")
    _commit_all(tmp_path, git, "changes")

    call(kspecfirst.main, "--json")
    payload = json.loads(capsys.readouterr().out)
    assert "specsomething/app.py" in payload["production"]
    assert "specs/01-booking/plan.md" in payload["kivax"]


def test_text_output_lists_files_and_notes_production(kspecfirst, call, tmp_path, minimal_config,
                                                       monkeypatch, git, capsys):
    _init_git_repo(tmp_path, git)
    cfg = minimal_config()
    monkeypatch.setattr(kspecfirst, "load_config", lambda: (tmp_path, cfg))
    (tmp_path / "app.py").write_text("x")
    _commit_all(tmp_path, git, "changes")
    rc = call(kspecfirst.main)
    assert rc == 0
    out = capsys.readouterr().out
    assert "PRODUCTION" in out
    assert "app.py" in out
    assert "trace-auditor must verify" in out


def test_base_branch_override(kspecfirst, call, tmp_path, minimal_config, monkeypatch, git, capsys):
    _init_git_repo(tmp_path, git)  # leaves "work" checked out, branched off "main"
    git(tmp_path, "checkout", "-qb", "other-base", "main")
    _commit_all(tmp_path, git, "on other-base")
    git(tmp_path, "checkout", "-q", "work")
    cfg = minimal_config()
    monkeypatch.setattr(kspecfirst, "load_config", lambda: (tmp_path, cfg))
    (tmp_path / "app.py").write_text("x")
    _commit_all(tmp_path, git, "work changes")
    call(kspecfirst.main, "--json", "--base", "other-base")
    payload = json.loads(capsys.readouterr().out)
    assert payload["base"] == "other-base"


def test_bad_base_branch_exits(kspecfirst, call, tmp_path, minimal_config, monkeypatch, git):
    _init_git_repo(tmp_path, git)
    cfg = minimal_config()
    monkeypatch.setattr(kspecfirst, "load_config", lambda: (tmp_path, cfg))
    rc = call(kspecfirst.main, "--base", "does-not-exist")
    assert isinstance(rc, str) and "ERROR running git diff" in rc


def test_monorepo_test_glob_prefix(kspecfirst, call, tmp_path, minimal_config, monkeypatch, git, capsys):
    _init_git_repo(tmp_path, git)
    cfg = minimal_config(stack={"active": "backend", "profiles": {
        "backend": {"root": "backend", "test_globs": ["tests/**/*.py"], "id_tag_regexes": [r"x"]},
    }})
    monkeypatch.setattr(kspecfirst, "load_config", lambda: (tmp_path, cfg))
    (tmp_path / "backend/tests").mkdir(parents=True)
    (tmp_path / "backend/tests/test_a.py").write_text("x")
    _commit_all(tmp_path, git, "changes")
    call(kspecfirst.main, "--json")
    payload = json.loads(capsys.readouterr().out)
    assert "backend/tests/test_a.py" in payload["tests"]
