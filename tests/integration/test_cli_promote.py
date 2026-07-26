"""Integration tests for `kivax promote` (bin/kivax's cmd_promote + _promote_agent)."""
import pytest

pytestmark = pytest.mark.integration


def test_usage_when_too_few_args(kivax_cli, project, call):
    rc = call(kivax_cli.main, "promote", "agent")
    assert isinstance(rc, str) and "Usage: kivax promote" in rc


def test_unknown_kind_exits(kivax_cli, project, call):
    rc = call(kivax_cli.main, "promote", "bogus", "x")
    assert isinstance(rc, str) and "Unknown kind" in rc


def test_model_only_rejected_for_skill(kivax_cli, project, call):
    rc = call(kivax_cli.main, "promote", "skill", "kivax-spec", "--model-only")
    assert isinstance(rc, str) and "only applies to agents" in rc


def test_runtime_not_active_in_project_is_skipped(kivax_cli, project, call, capsys):
    rc = call(kivax_cli.main, "promote", "skill", "kivax-spec", "--runtime", "cursor")
    assert rc == 1
    out = capsys.readouterr().out
    assert "isn't an active runtime" in out
    assert "Nothing promoted." in out


def test_missing_project_file_skill(kivax_cli, project, call, capsys):
    rc = call(kivax_cli.main, "promote", "skill", "does-not-exist")
    assert rc == 1
    out = capsys.readouterr().out
    assert "doesn't exist in this project" in out
    assert "Nothing promoted." in out


def test_promote_new_skill(kivax_cli, project, repo_dir, use_store, call, capsys):
    d = repo_dir / ".claude/skills/my-custom-skill"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: my-custom-skill\n---\n\nBrand new.\n")
    rc = call(kivax_cli.main, "promote", "skill", "my-custom-skill")
    assert rc == 0
    out = capsys.readouterr().out
    assert "NEW upstream file" in out
    upstream = use_store / "runtime/skills/my-custom-skill/SKILL.md"
    assert upstream.read_text() == "---\nname: my-custom-skill\n---\n\nBrand new.\n"


def test_promote_unchanged_skill(kivax_cli, project, call, capsys):
    rc = call(kivax_cli.main, "promote", "skill", "kivax-spec")
    assert rc == 0
    out = capsys.readouterr().out
    assert "unchanged, already up to date" in out


def test_promote_updated_skill(kivax_cli, project, repo_dir, use_store, call, capsys):
    p = repo_dir / ".claude/skills/kivax-spec/SKILL.md"
    p.write_text(p.read_text() + "\nA local addition.\n")
    rc = call(kivax_cli.main, "promote", "skill", "kivax-spec")
    assert rc == 0
    out = capsys.readouterr().out
    assert "updated" in out
    upstream = use_store / "runtime/skills/kivax-spec/SKILL.md"
    assert "A local addition." in upstream.read_text()
    # the project's own manifest is kept consistent, so a later upgrade sees no conflict
    import json
    manifest = json.loads((repo_dir / ".kivax/sync.json").read_text())
    assert manifest[".claude/skills/kivax-spec/SKILL.md"].startswith("sha256:")


def test_promote_full_agent_claude_passthrough_tools(kivax_cli, project, repo_dir, use_store, call, capsys):
    p = repo_dir / ".claude/agents/reviewer.md"
    text = p.read_text()
    text = text.replace("tools: Read, Grep, Glob, Bash", "tools: Read, Grep, Glob, Bash, Write")
    p.write_text(text)
    rc = call(kivax_cli.main, "promote", "agent", "reviewer")
    assert rc == 0
    out = capsys.readouterr().out
    assert "updated" in out
    canonical = (use_store / "agents/reviewer.md").read_text()
    assert "Write" in canonical.split("---")[2] or "tools:" in canonical


def test_promote_agent_non_passthrough_runtime_leaves_tools_untouched(kivax_cli, use_store, repo_dir,
                                                                       call, feed_input):
    # Install with cursor active too, so a cursor agent file exists to promote from.
    answers = ["", "", "y", "", "", "", "y", "", "", "python-pytest", ""]
    feed_input(*answers)
    call(kivax_cli.main, "init")
    before = (use_store / "agents/reviewer.md").read_text()
    rc = call(kivax_cli.main, "promote", "agent", "reviewer", "--runtime", "cursor")
    assert rc == 0
    after = (use_store / "agents/reviewer.md").read_text()
    assert before.split("---")[2].strip() and "tools:" in before  # sanity: canonical had tools
    # cursor's format is lossy for tools, so the canonical tools: line is untouched
    assert ("tools:" in before) == ("tools:" in after)


def test_promote_agent_model_only_with_model(kivax_cli, project, repo_dir, use_store, call, capsys):
    p = repo_dir / ".claude/agents/reviewer.md"
    text = p.read_text()
    # claude-rendered agents always carry a 'model:' line (defaulted to
    # "inherit" by agent_runtimes.yml) — replace it in place, rather than
    # inserting a second 'model:' key (that would just create a YAML
    # duplicate key, which PyYAML resolves to whichever occurrence comes
    # LAST, silently ignoring the inserted one).
    assert text.count("model: inherit") == 1
    text = text.replace("model: inherit", "model: opus", 1)
    p.write_text(text)
    rc = call(kivax_cli.main, "promote", "agent", "reviewer", "--model-only")
    assert rc == 0
    out = capsys.readouterr().out
    assert "(model only)" in out
    canonical = (use_store / "agents/reviewer.md").read_text()
    assert "model: opus" in canonical


def test_promote_agent_model_only_without_model_field(kivax_cli, project, repo_dir, call, capsys):
    # claude-rendered agents always carry a 'model:' line by default — strip
    # it so this project's file genuinely has none, to reach the WARNING path.
    p = repo_dir / ".claude/agents/reviewer.md"
    text = p.read_text().replace("model: inherit\n", "")
    assert "model:" not in text
    p.write_text(text)
    rc = call(kivax_cli.main, "promote", "agent", "reviewer", "--model-only")
    assert rc == 1
    out = capsys.readouterr().out
    assert "has no model: field" in out
    assert "Nothing promoted." in out


def test_promote_agent_missing_project_file(kivax_cli, project, call, capsys):
    rc = call(kivax_cli.main, "promote", "agent", "does-not-exist")
    assert rc == 1
    assert "Nothing promoted." in capsys.readouterr().out


def test_promote_creates_brand_new_canonical_agent(kivax_cli, project, repo_dir, use_store, call, capsys):
    d = repo_dir / ".claude/agents"
    (d / "custom-helper.md").write_text(
        '---\ndescription: "A one-off project agent."\ntools: Read\n---\n\nBody.\n')
    rc = call(kivax_cli.main, "promote", "agent", "custom-helper")
    assert rc == 0
    out = capsys.readouterr().out
    assert "NEW upstream file" in out
    assert (use_store / "agents/custom-helper.md").is_file()
