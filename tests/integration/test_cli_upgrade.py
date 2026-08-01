"""Integration tests for `kivax upgrade` (bin/kivax's cmd_upgrade).

Upgrade has no merge and no manifest: the managed files are generated from the
global store plus .kivax/config.yml, so upstream + config is the whole truth
about what they should contain and there is never anything to reconcile. These
tests pin that contract — including the part users feel, which is that a local
edit to a generated file does NOT survive.
"""
import pytest
import yaml

pytestmark = pytest.mark.integration

SKILL_PATH = ".claude/skills/kivax-spec/SKILL.md"
STORE_SKILL_REL = "runtime/skills/kivax-spec/SKILL.md"


# --------------------------------------------------------------------------- copying in
def test_added_file_from_a_newer_store(kivax_cli, project, use_store, repo_dir, call, capsys):
    new_skill_dir = use_store / "runtime" / "skills" / "kivax-brand-new"
    new_skill_dir.mkdir(parents=True)
    (new_skill_dir / "SKILL.md").write_text("---\nname: kivax-brand-new\n---\nBody\n")
    assert call(kivax_cli.main, "upgrade") == 0
    assert "Added: 1" in capsys.readouterr().out
    assert (repo_dir / ".claude/skills/kivax-brand-new/SKILL.md").is_file()


def test_updated_when_upstream_changed(kivax_cli, project, use_store, repo_dir, call, capsys):
    store_file = use_store / STORE_SKILL_REL
    store_file.write_text(store_file.read_text() + "\nUpstream addition.\n")
    assert call(kivax_cli.main, "upgrade") == 0
    assert "Updated: 1" in capsys.readouterr().out
    assert "Upstream addition." in (repo_dir / SKILL_PATH).read_text()


def test_unchanged_when_nothing_moved(kivax_cli, project, use_store, call, capsys):
    assert call(kivax_cli.main, "upgrade") == 0
    out = capsys.readouterr().out
    assert "Updated: 0" in out
    assert "Added: 0" in out
    assert "Removed: 0" in out


# --------------------------------------------------------------------------- the breaking change
def test_a_local_edit_is_overwritten_without_a_conflict(kivax_cli, project, repo_dir,
                                                        use_store, call, capsys):
    """The point of dropping the 3-way sync: these are generated files, so a
    hand-edit is a mistake to correct, not a customization to protect."""
    upstream = (use_store / STORE_SKILL_REL).read_text()
    (repo_dir / SKILL_PATH).write_text("---\nname: kivax-spec\n---\nMy own edit.\n")
    assert call(kivax_cli.main, "upgrade") == 0
    out = capsys.readouterr().out
    assert "CONFLICT" not in out.upper()
    assert (repo_dir / SKILL_PATH).read_text() == upstream
    assert not list(repo_dir.rglob("*.upstream"))


def test_skill_removed_upstream_is_pruned(kivax_cli, project, use_store, repo_dir, call, capsys):
    """A phase driver that no longer exists upstream has to leave the project
    too, or the assistant keeps reading a skill the flow doesn't reference."""
    stale = repo_dir / ".claude/skills/kivax-gone/SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("---\nname: kivax-gone\n---\nRetired.\n")
    assert call(kivax_cli.main, "upgrade") == 0
    assert "Removed: 1" in capsys.readouterr().out
    assert not stale.exists()
    assert not stale.parent.exists(), "the emptied skill directory should go too"


def test_pruning_stays_inside_the_managed_dirs(kivax_cli, project, repo_dir, call):
    """.github holds CI workflows and issue templates that are the project's
    own; only .github/agents and .github/skills are Kivax's."""
    mine = repo_dir / ".github/workflows/ci.yml"
    mine.parent.mkdir(parents=True, exist_ok=True)
    mine.write_text("name: ci\n")
    src = repo_dir / "src/main.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("print('hi')\n")
    assert call(kivax_cli.main, "upgrade") == 0
    assert mine.is_file()
    assert src.is_file()


# --------------------------------------------------------------------------- model selection
def test_configured_model_is_baked_into_the_agent_files(kivax_cli, project, repo_dir,
                                                        use_store, call):
    cfg_path = repo_dir / ".kivax/config.yml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["agents"] = {"implementer": {"model": "opus"}}
    cfg_path.write_text(yaml.safe_dump(cfg))
    assert call(kivax_cli.main, "upgrade") == 0
    assert "model: opus" in (repo_dir / ".claude/agents/implementer.md").read_text()
    # Everyone else keeps the runtime's own "use the session model" word.
    assert "model: inherit" in (repo_dir / ".claude/agents/reviewer.md").read_text()


def test_default_model_applies_to_every_agent(kivax_cli, project, repo_dir, use_store, call):
    cfg_path = repo_dir / ".kivax/config.yml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["agents"] = {"default": {"model": "sonnet"}, "orchestrator": {"model": "opus"}}
    cfg_path.write_text(yaml.safe_dump(cfg))
    assert call(kivax_cli.main, "upgrade") == 0
    assert "model: sonnet" in (repo_dir / ".claude/agents/reviewer.md").read_text()
    assert "model: opus" in (repo_dir / ".claude/agents/orchestrator.md").read_text()


def test_changing_the_model_shows_up_as_an_update(kivax_cli, project, repo_dir,
                                                  use_store, call, capsys):
    cfg_path = repo_dir / ".kivax/config.yml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["agents"] = {"default": {"model": "opus"}}
    cfg_path.write_text(yaml.safe_dump(cfg))
    assert call(kivax_cli.main, "upgrade") == 0
    out = capsys.readouterr().out
    assert "Updated: 0" not in out, "every claude agent file should have been rewritten"


# --------------------------------------------------------------------------- dry run
def test_dry_run_writes_nothing(kivax_cli, project, use_store, repo_dir, call, capsys):
    store_file = use_store / STORE_SKILL_REL
    store_file.write_text(store_file.read_text() + "\nUpstream change.\n")
    assert call(kivax_cli.main, "upgrade", "--dry-run") == 0
    out = capsys.readouterr().out
    assert "Would update: 1" in out
    assert "--dry-run: nothing was written" in out
    assert "Upstream change." not in (repo_dir / SKILL_PATH).read_text()


def test_dry_run_reports_the_same_removals_it_would_make(kivax_cli, project, repo_dir,
                                                         use_store, call, capsys):
    stale = repo_dir / ".claude/skills/kivax-gone/SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("retired\n")
    assert call(kivax_cli.main, "upgrade", "--dry-run") == 0
    assert "Would remove: 1" in capsys.readouterr().out
    assert stale.is_file(), "--dry-run must not delete anything"


# --------------------------------------------------------------------------- config warnings
def test_legacy_tag_regex_warning_printed(kivax_cli, project, repo_dir, call, capsys):
    cfg_path = repo_dir / ".kivax/config.yml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["stack"]["profiles"]["python-pytest"]["id_tag_regexes"] = [
        r'@pytest\.mark\.req\("(?P<id>(?:REQ|IT)-\d{3})"\)']
    cfg_path.write_text(yaml.safe_dump(cfg))
    call(kivax_cli.main, "upgrade")
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "invisible" in out
    assert "upgrade never rewrites it for you" in out


def test_obsolete_config_keys_are_named(kivax_cli, project, repo_dir, call, capsys):
    """An old config still works; upgrade just says which keys stopped meaning
    anything, so nobody is left believing they still control the flow."""
    cfg_path = repo_dir / ".kivax/config.yml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["version"] = 2
    cfg["pipeline"] = ["spec", "compile"]
    cfg["gates"] = {"audit": "auto"}
    cfg["git"]["branch_prefix"] = "kivax/"
    cfg_path.write_text(yaml.safe_dump(cfg))
    assert call(kivax_cli.main, "upgrade") == 0
    out = capsys.readouterr().out
    assert "pipeline" in out
    assert "gates" in out
    assert "git.branch_prefix" in out
