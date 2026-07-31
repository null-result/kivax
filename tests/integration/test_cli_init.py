"""Integration tests for `kivax init` (bin/kivax's cmd_init).

Answers are explicit per-prompt lists (never a newline-joined string split by
hand) — cmd_init's number of prompts depends on which branch each answer
takes, so miscounting a joined string is an easy, silent way to feed the
wrong answer to the wrong prompt. Each list below is commented prompt-by-prompt.
"""
import pytest
import yaml

pytestmark = pytest.mark.integration

BLANK6 = ["", "", "", "", "", ""]  # the 6 RUNTIME_CHOICES, all defaulted


def test_already_installed_is_a_noop(kivax_cli, project, call, capsys):
    rc = call(kivax_cli.main, "init")
    assert rc == 0
    assert "already exists" in capsys.readouterr().out


def test_force_reinstalls(kivax_cli, project, repo_dir, call, feed_input):
    answers = [
        *BLANK6,            # runtimes
        "",                  # greenfield (heuristic default True)
        "",                  # principles/architecture (default yes)
        "",                  # features root (existing 'specs/' is empty -> single ask)
        "",                  # spec_language
        "python-pytest",     # manual stack profile (greenfield -> nothing detected)
        "",                  # base branch
    ]
    feed_input(*answers)
    rc = call(kivax_cli.main, "init", "--force")
    assert rc == 0


def test_greenfield_skips_legacy_globs_block(kivax_cli, use_store, repo_dir, call, feed_input, capsys):
    answers = [*BLANK6, "y", "", "", "", "python-pytest", ""]
    feed_input(*answers)
    rc = call(kivax_cli.main, "init")
    assert rc == 0
    out = capsys.readouterr().out
    assert "legacy_globs" not in out
    cfg = yaml.safe_load((repo_dir / ".kivax/config.yml").read_text())
    assert cfg["legacy_globs"] == []
    assert cfg["greenfield"] is True


def test_non_greenfield_with_detected_stack_confirmed(kivax_cli, use_store, repo_dir, call, feed_input):
    (repo_dir / "pyproject.toml").write_text("[project]\nname='x'\n")
    (repo_dir / "src").mkdir()
    (repo_dir / "src/app.py").write_text("x = 1\n")
    answers = [
        *BLANK6,
        "n",                 # not greenfield
        "",                  # principles/architecture
        "",                  # features root (no existing specs dir -> single ask)
        "",                  # spec_language
        "",                  # confirm the detected 'python-pytest' profile
        "",                  # base branch
        "",                  # accept the proposed legacy_globs
    ]
    feed_input(*answers)
    rc = call(kivax_cli.main, "init")
    assert rc == 0
    cfg = yaml.safe_load((repo_dir / ".kivax/config.yml").read_text())
    assert "python-pytest" in cfg["stack"]["active"]
    assert cfg["legacy_globs"] == ["src/**"]


def test_non_greenfield_no_detected_stack_manual_entry_including_unknown(kivax_cli, use_store,
                                                                          repo_dir, call, feed_input):
    (repo_dir / "src").mkdir()
    (repo_dir / "src/app.rs").write_text("fn main() {}\n")  # no catalog marker matches
    answers = [
        *BLANK6,
        "n", "", "", "",
        "made-up-profile",   # not in the catalog
        "", "",
    ]
    feed_input(*answers)
    rc = call(kivax_cli.main, "init")
    assert rc == 0
    cfg = yaml.safe_load((repo_dir / ".kivax/config.yml").read_text())
    assert "made-up-profile" in cfg["stack"]["profiles"]
    assert cfg["stack"]["profiles"]["made-up-profile"]["test_globs"] == []


def test_runtimes_all_declined_installs_every_runtime(kivax_cli, use_store, repo_dir, call, feed_input, capsys):
    answers = [
        "n", "n", "n", "n", "n", "n",  # every runtime declined
        "y", "", "", "python-pytest", "",
    ]
    feed_input(*answers)
    rc = call(kivax_cli.main, "init")
    assert rc == 0
    out = capsys.readouterr().out
    assert "picked none" in out
    cfg = yaml.safe_load((repo_dir / ".kivax/config.yml").read_text())
    assert len(cfg["runtimes"]) == 6


def test_principles_and_architecture_declined(kivax_cli, use_store, repo_dir, call, feed_input):
    answers = [*BLANK6, "y", "n", "", "", "python-pytest", ""]
    feed_input(*answers)
    rc = call(kivax_cli.main, "init")
    assert rc == 0
    cfg = yaml.safe_load((repo_dir / ".kivax/config.yml").read_text())
    assert "principles" not in cfg["pipeline"]
    assert "principles" not in cfg["paths"]


def test_existing_specs_dir_used_as_is_when_it_is_the_kivax_layout(kivax_cli, use_store, repo_dir,
                                                                    call, feed_input):
    (repo_dir / "specs/01-booking").mkdir(parents=True)
    (repo_dir / "specs/01-booking/spec.md").write_text("x")
    (repo_dir / "src").mkdir()
    (repo_dir / "src/app.py").write_text("x")
    answers = [
        *BLANK6,
        "n",                 # not greenfield
        "",                  # principles/architecture
        "",                  # confirm using 'specs' as the features root (no loose .md -> default yes)
        "",                  # spec_language
        "python-pytest",     # no stack markers under src/ -> manual entry
        "", "",
    ]
    feed_input(*answers)
    rc = call(kivax_cli.main, "init")
    assert rc == 0
    cfg = yaml.safe_load((repo_dir / ".kivax/config.yml").read_text())
    assert cfg["paths"]["features"] == "specs"


def test_existing_loose_corpus_declined_goes_to_separate_folder_and_legacy_globs(kivax_cli, use_store,
                                                                                 repo_dir, call,
                                                                                 feed_input, capsys):
    (repo_dir / "specs").mkdir()
    (repo_dir / "specs/auth.md").write_text("# Auth\n")
    (repo_dir / "src").mkdir()
    (repo_dir / "src/app.py").write_text("x")
    answers = [
        *BLANK6,
        "n",                 # not greenfield
        "",                  # principles/architecture
        "n",                 # decline using 'specs' as the features root (loose .md present)
        "",                  # accept the suggested 'specs/features'
        "",                  # spec_language
        "python-pytest",     # manual stack entry
        "",                  # base branch
        "",                  # accept the proposed legacy_globs (includes the corpus)
    ]
    feed_input(*answers)
    rc = call(kivax_cli.main, "init")
    assert rc == 0
    out = capsys.readouterr().out
    assert "already contains loose markdown" in out
    cfg = yaml.safe_load((repo_dir / ".kivax/config.yml").read_text())
    assert cfg["paths"]["features"] == "specs/features"
    assert "specs/**" in cfg["legacy_globs"]
    assert not (repo_dir / "specs/spec.md").exists()
    assert (repo_dir / "specs/auth.md").read_text().startswith("# Auth")


def test_custom_legacy_globs_entry(kivax_cli, use_store, repo_dir, call, feed_input):
    (repo_dir / "src").mkdir()
    (repo_dir / "src/app.py").write_text("x")
    answers = [
        *BLANK6, "n", "", "", "",
        "python-pytest",
        "",
        "n",                          # decline the proposed legacy_globs
        "custom/**, other/**",        # type a custom list
    ]
    feed_input(*answers)
    rc = call(kivax_cli.main, "init")
    assert rc == 0
    cfg = yaml.safe_load((repo_dir / ".kivax/config.yml").read_text())
    assert cfg["legacy_globs"] == ["custom/**", "other/**"]


def test_init_writes_no_spec_md_and_creates_empty_features_dir(kivax_cli, project, repo_dir):
    assert (repo_dir / "specs").is_dir()
    assert not (repo_dir / "specs/spec.md").exists()
    assert (repo_dir / ".kivax/state.yml").is_file()
    state = yaml.safe_load((repo_dir / ".kivax/state.yml").read_text())
    assert state["active"] is None


def test_init_copies_runtime_files_for_claude(kivax_cli, project, repo_dir):
    assert (repo_dir / ".claude/agents/orchestrator.md").is_file()
    assert (repo_dir / ".claude/skills/kivax-spec/SKILL.md").is_file()
    assert (repo_dir / "CLAUDE.md").is_file()
    assert (repo_dir / "AGENTS.md").is_file()
    assert (repo_dir / ".kivax/sync.json").is_file()
