"""Unit tests for the standalone helper functions in kivax/cli.py — the parts
that don't need a scaffolded project or store (see tests/integration/ for the
cmd_* subcommands, which do)."""
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- ask / ask_yesno
def test_ask_returns_default_on_blank(kivax_cli, feed_input):
    feed_input("")
    assert kivax_cli.ask("Prompt", "fallback") == "fallback"


def test_ask_returns_typed_answer(kivax_cli, feed_input):
    feed_input("typed")
    assert kivax_cli.ask("Prompt", "fallback") == "typed"


def test_ask_required_reprompts_until_answered(kivax_cli, feed_input, capsys):
    feed_input("", "", "finally")
    assert kivax_cli.ask("Prompt") == "finally"
    assert "an answer is required" in capsys.readouterr().out


def test_ask_treats_eof_as_blank(kivax_cli, monkeypatch):
    def raises_eof(prompt=""):
        raise EOFError
    monkeypatch.setattr("builtins.input", raises_eof)
    assert kivax_cli.ask("Prompt", "d") == "d"


@pytest.mark.parametrize("answer,default,expected", [
    ("", True, True), ("", False, False),
    ("y", False, True), ("yes", False, True),
    ("n", True, False), ("no", True, False),
])
def test_ask_yesno_variants(kivax_cli, feed_input, answer, default, expected):
    feed_input(answer)
    assert kivax_cli.ask_yesno("Q", default) is expected


def test_ask_yesno_reprompts_on_garbage(kivax_cli, feed_input, capsys):
    feed_input("maybe", "y")
    assert kivax_cli.ask_yesno("Q", False) is True
    assert "please answer y/n" in capsys.readouterr().out


def test_ask_yesno_eof_uses_default(kivax_cli, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": (_ for _ in ()).throw(EOFError))
    assert kivax_cli.ask_yesno("Q", True) is True


# --------------------------------------------------------------------------- sh
def test_sh_returns_stripped_stdout(kivax_cli, tmp_path):
    out = kivax_cli.sh(["python3", "-c", "print('  hi  ')"], tmp_path)
    assert out == "hi"


def test_sh_returns_empty_on_missing_executable(kivax_cli, tmp_path):
    assert kivax_cli.sh(["this-binary-does-not-exist-anywhere"], tmp_path) == ""


def test_sh_returns_empty_on_nonzero_exit(kivax_cli, tmp_path):
    assert kivax_cli.sh(["python3", "-c", "import sys; sys.exit(1)"], tmp_path) == ""


# --------------------------------------------------------------------------- require_kivax_home / require_project
def test_require_kivax_home_missing_exits(kivax_cli, use_store, monkeypatch, tmp_path):
    monkeypatch.setattr(kivax_cli, "AGENTS_SRC", tmp_path / "nowhere")
    with pytest.raises(SystemExit, match="can't find the Kivax global store"):
        kivax_cli.require_kivax_home()


def test_require_kivax_home_present_is_silent(kivax_cli, use_store):
    kivax_cli.require_kivax_home()  # must not raise


def test_require_project_missing_config_exits(kivax_cli, repo_dir):
    with pytest.raises(SystemExit, match="Run 'kivax init' first"):
        kivax_cli.require_project()


def test_require_project_reads_config(kivax_cli, repo_dir):
    (repo_dir / ".kivax").mkdir()
    (repo_dir / ".kivax/config.yml").write_text("paths:\n  wiki: specs/wiki\n")
    root, cfg = kivax_cli.require_project()
    assert root == repo_dir
    assert cfg["paths"]["wiki"] == "specs/wiki"


# --------------------------------------------------------------------------- find_source_files
def test_find_source_files_matches_suffixes_and_skips_excluded_dirs(kivax_cli, tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/app.py").write_text("x")
    (tmp_path / "src/app.js").write_text("x")
    (tmp_path / "src/notes.txt").write_text("x")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules/lib.js").write_text("x")
    found = kivax_cli.find_source_files(tmp_path)
    names = {p.name for p in found}
    assert names == {"app.py", "app.js"}


def test_find_source_files_respects_limit(kivax_cli, tmp_path):
    for i in range(5):
        (tmp_path / f"f{i}.py").write_text("x")
    assert len(kivax_cli.find_source_files(tmp_path, limit=3)) == 3


# --------------------------------------------------------------------------- find_existing_specs_dir
def test_find_existing_specs_dir_prefers_per_feature_layout(kivax_cli, tmp_path):
    (tmp_path / "specs/01-booking").mkdir(parents=True)
    (tmp_path / "specs/01-booking/spec.md").write_text("x")
    assert kivax_cli.find_existing_specs_dir(tmp_path) == tmp_path / "specs"


def test_find_existing_specs_dir_finds_loose_markdown(kivax_cli, tmp_path):
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec/notes.md").write_text("x")
    assert kivax_cli.find_existing_specs_dir(tmp_path) == tmp_path / "spec"


def test_find_existing_specs_dir_none_found(kivax_cli, tmp_path):
    assert kivax_cli.find_existing_specs_dir(tmp_path) is None


def test_find_existing_specs_dir_candidate_priority(kivax_cli, tmp_path):
    (tmp_path / "docs/requirements").mkdir(parents=True)
    (tmp_path / "docs/requirements/x.md").write_text("x")
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements/y.md").write_text("x")
    # 'requirements' precedes 'docs/requirements' in SPEC_DIR_CANDIDATES
    assert kivax_cli.find_existing_specs_dir(tmp_path) == tmp_path / "requirements"


# --------------------------------------------------------------------------- detect_stacks
def test_detect_stacks_root_and_subdir(kivax_cli, tmp_path):
    catalog = {
        "python-pytest": {"label": "Python", "detect_markers": ["pyproject.toml"]},
        "node-jest": {"label": "Node", "detect_markers": ["package.json"]},
    }
    (tmp_path / "pyproject.toml").write_text("x")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend/package.json").write_text("x")
    found = kivax_cli.detect_stacks(tmp_path, catalog)
    assert ("python-pytest", "") in found
    assert ("node-jest", "frontend") in found


def test_detect_stacks_excludes_known_dirs(kivax_cli, tmp_path):
    catalog = {"node-jest": {"label": "Node", "detect_markers": ["package.json"]}}
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules/package.json").write_text("x")
    assert kivax_cli.detect_stacks(tmp_path, catalog) == []


def test_detect_stacks_no_markers(kivax_cli, tmp_path):
    catalog = {"go": {"label": "Go", "detect_markers": ["go.mod"]}}
    assert kivax_cli.detect_stacks(tmp_path, catalog) == []


# --------------------------------------------------------------------------- detect_base_branch
def test_detect_base_branch_from_current_branch(kivax_cli, repo_dir, git):
    assert kivax_cli.detect_base_branch(repo_dir) == "main"


def test_detect_base_branch_falls_back_to_main(kivax_cli, tmp_path):
    # not even a git repo: both `sh()` calls return "" -> falls back to "main"
    assert kivax_cli.detect_base_branch(tmp_path) == "main"


def test_detect_base_branch_prefers_origin_head(kivax_cli, tmp_path, git):
    bare = tmp_path / "origin.git"
    bare.mkdir()
    git(bare, "init", "-q", "--bare")
    git(bare, "symbolic-ref", "HEAD", "refs/heads/trunk")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(bare), str(clone))
    assert kivax_cli.detect_base_branch(clone) == "trunk"


# Kivax's flow is gitflow's feature branch, so it has to target the INTEGRATION
# branch. origin/HEAD points at the published one — on a gitflow repo that's
# the release branch, and a feature PR against it would target production.
def test_detect_base_branch_prefers_local_develop(kivax_cli, repo_dir, git):
    git(repo_dir, "commit", "-q", "--allow-empty", "-m", "root")  # a branch needs one
    git(repo_dir, "branch", "develop")
    assert kivax_cli.detect_base_branch(repo_dir) == "develop"


def test_detect_base_branch_prefers_develop_over_origin_head(kivax_cli, tmp_path, git):
    bare = tmp_path / "origin.git"
    bare.mkdir()
    git(bare, "init", "-q", "--bare")
    git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(bare), str(clone))
    git(clone, "config", "user.email", "test@example.invalid")
    git(clone, "config", "user.name", "Test")
    git(clone, "commit", "-q", "--allow-empty", "-m", "root")
    git(clone, "branch", "develop")
    assert kivax_cli.detect_base_branch(clone) == "develop"


def test_branch_prefix_is_gitflows_own(kivax_cli):
    assert kivax_cli.BRANCH_PREFIX == "feature/"


# --------------------------------------------------------------------------- _check_forge_cli
# A pull request is a forge concept, not a git one: no git command creates one,
# so the flow's "ends in a reviewable PR" contract needs gh or glab.
def test_forge_cli_missing_is_reported(kivax_cli, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    problems = kivax_cli._check_forge_cli()
    assert len(problems) == 1
    assert "gh" in problems[0] and "glab" in problems[0]


def test_forge_cli_present_is_silent(kivax_cli, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/gh" if name == "gh" else None)
    assert kivax_cli._check_forge_cli() == []


def test_glab_alone_satisfies_the_check(kivax_cli, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/glab" if name == "glab" else None)
    assert kivax_cli._check_forge_cli() == []


# --------------------------------------------------------------------------- _looks_like_botched_feature
def test_looks_like_botched_feature_leading_digit(kivax_cli, tmp_path):
    d = tmp_path / "1-booking"
    d.mkdir()
    assert kivax_cli._looks_like_botched_feature(d) is True


def test_looks_like_botched_feature_has_spec_md(kivax_cli, tmp_path):
    d = tmp_path / "notes"
    d.mkdir()
    (d / "spec.md").write_text("x")
    assert kivax_cli._looks_like_botched_feature(d) is True


def test_looks_like_botched_feature_has_spec_yml(kivax_cli, tmp_path):
    d = tmp_path / "notes"
    d.mkdir()
    (d / "spec.yml").write_text("x")
    assert kivax_cli._looks_like_botched_feature(d) is True


def test_looks_like_botched_feature_plain_docs_dir_is_fine(kivax_cli, tmp_path):
    d = tmp_path / "payments-notes"
    d.mkdir()
    (d / "overview.md").write_text("x")
    assert kivax_cli._looks_like_botched_feature(d) is False


# --------------------------------------------------------------------------- _check_tag_regexes
def test_check_tag_regexes_flags_legacy_pattern(kivax_cli):
    cfg = {"stack": {"active": "python-pytest", "profiles": {"python-pytest": {
        "id_tag_regexes": [r'@pytest\.mark\.req\("(?P<id>(?:REQ|IT)-\d{3})"\)'],
    }}}}
    problems = kivax_cli._check_tag_regexes(cfg)
    assert len(problems) == 1
    assert "invisible" in problems[0]


def test_check_tag_regexes_accepts_prefixed_pattern(kivax_cli):
    cfg = {"stack": {"active": "python-pytest", "profiles": {"python-pytest": {
        "id_tag_regexes": [r'@pytest\.mark\.req\("(?P<id>(?:REQ|IT)-(?:\d{2,}-)?\d{3})"\)'],
    }}}}
    assert kivax_cli._check_tag_regexes(cfg) == []


def test_check_tag_regexes_invalid_regex(kivax_cli):
    cfg = {"stack": {"active": "python-pytest", "profiles": {"python-pytest": {
        "id_tag_regexes": [r"(unclosed"],
    }}}}
    problems = kivax_cli._check_tag_regexes(cfg)
    assert "not a valid regex" in problems[0]


def test_check_tag_regexes_multiple_profiles_list_form(kivax_cli):
    cfg = {"stack": {"active": ["a", "b"], "profiles": {
        "a": {"id_tag_regexes": [r'REQ-01-001']},  # contains 'REQ-01-001' literally: skipped
        "b": {"id_tag_regexes": []},
    }}}
    assert kivax_cli._check_tag_regexes(cfg) == []


def test_check_tag_regexes_no_active_profiles(kivax_cli):
    assert kivax_cli._check_tag_regexes({}) == []


# --------------------------------------------------------------------------- legacy install detection
def _make_legacy_store(root):
    """The shape install.py used to leave behind: a store with lib/kivax_lib.py."""
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "kivax_lib.py").write_text("# pre-2.1 store\n", encoding="utf-8")
    return root


def test_no_warning_when_there_is_no_legacy_store(kivax_cli, use_store):
    assert kivax_cli._check_legacy_install() == []


def test_legacy_store_is_reported(kivax_cli, monkeypatch, tmp_path):
    legacy = _make_legacy_store(tmp_path / ".kivax")
    monkeypatch.delenv("KIVAX_HOME", raising=False)
    monkeypatch.setattr(kivax_cli, "LEGACY_STORE", legacy)
    monkeypatch.setattr(kivax_cli.shutil, "which", lambda name, *a, **k: None)
    problems = kivax_cli._check_legacy_install()
    assert len(problems) == 1
    assert str(legacy) in problems[0] and "no longer used" in problems[0]


def test_legacy_store_ignored_when_kivax_home_is_set(kivax_cli, monkeypatch, tmp_path):
    """KIVAX_HOME means the user chose their own store on purpose; ~/.kivax
    being present is then their business, not a leftover to nag about."""
    legacy = _make_legacy_store(tmp_path / ".kivax")
    monkeypatch.setenv("KIVAX_HOME", str(tmp_path / "elsewhere"))
    monkeypatch.setattr(kivax_cli, "LEGACY_STORE", legacy)
    assert kivax_cli._check_legacy_install() == []


def test_legacy_cli_shadowing_the_installed_one_is_called_out(kivax_cli, monkeypatch, tmp_path):
    legacy = _make_legacy_store(tmp_path / ".kivax")
    shadow = tmp_path / "bin" / "kivax"
    shadow.parent.mkdir(parents=True)
    shadow.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    monkeypatch.delenv("KIVAX_HOME", raising=False)
    monkeypatch.setattr(kivax_cli, "LEGACY_STORE", legacy)
    monkeypatch.setattr(kivax_cli.shutil, "which", lambda name, *a, **k: str(shadow))
    assert "shadows the installed CLI" in kivax_cli._check_legacy_install()[0]


def test_cli_inside_the_current_prefix_is_not_a_shadow(kivax_cli, monkeypatch, tmp_path):
    """A `kivax` resolving inside sys.prefix IS the installed one — warning
    about it would tell every correctly-installed user to delete their CLI."""
    legacy = _make_legacy_store(tmp_path / ".kivax")
    installed = Path(sys.prefix) / "bin" / "kivax"
    monkeypatch.delenv("KIVAX_HOME", raising=False)
    monkeypatch.setattr(kivax_cli, "LEGACY_STORE", legacy)
    monkeypatch.setattr(kivax_cli.shutil, "which", lambda name, *a, **k: str(installed))
    assert "shadows the installed CLI" not in kivax_cli._check_legacy_install()[0]
