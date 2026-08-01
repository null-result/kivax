"""Unit tests for share/lib/kivax_agents.py."""
import pytest

pytestmark = pytest.mark.unit

CLAUDE_CFG = {
    "dir": ".claude/agents", "filename": "{name}.md",
    "fields": [["name", "field:name"], ["description", "field:description"],
              ["tools", "field:tools"], ["model", "computed:model:inherit"]],
}
CURSOR_CFG = {
    "dir": ".cursor/agents", "filename": "{name}.md",
    "fields": [["name", "field:name"], ["description", "field:description"],
              ["model", "computed:model:auto"], ["readonly", "computed:readonly"],
              ["is_background", "value:false"]],
}
OPENCODE_CFG = {
    "dir": ".opencode/agent", "filename": "{name}.md",
    "fields": [["description", "field:description"], ["mode", "value:subagent"],
              ["tools", "computed:opencode_tools"]],
}


# --------------------------------------------------------------------------- split_frontmatter
def test_split_frontmatter_present(kagents):
    fm, body = kagents.split_frontmatter("---\ndescription: hi\ntools: Read\n---\n\nBody text.\n")
    assert fm == {"description": "hi", "tools": "Read"}
    assert body.strip() == "Body text."


def test_split_frontmatter_absent(kagents):
    fm, body = kagents.split_frontmatter("Just a body, no frontmatter.\n")
    assert fm == {}
    assert body == "Just a body, no frontmatter.\n"


def test_parse_canonical(kagents, tmp_path):
    p = tmp_path / "spec-analyst.md"
    p.write_text('---\ndescription: "d"\ntools: Read, Write\n---\n\nBody\n')
    name, fm, body = kagents.parse_canonical(p)
    assert name == "spec-analyst"
    assert fm["tools"] == "Read, Write"


def test_load_runtime_configs(kagents, tmp_path):
    p = tmp_path / "agent_runtimes.yml"
    p.write_text("claude:\n  dir: .claude/agents\n")
    cfg = kagents.load_runtime_configs(p)
    assert cfg["claude"]["dir"] == ".claude/agents"


# --------------------------------------------------------------------------- _tools_list / _yaml_scalar
def test_tools_list_splits_and_strips(kagents):
    assert kagents._tools_list({"tools": "Read, Write , Bash"}) == ["Read", "Write", "Bash"]


def test_tools_list_empty(kagents):
    assert kagents._tools_list({}) == []


def test_yaml_scalar_description_is_json_dumped(kagents):
    line = kagents._yaml_scalar("description", 'has "quotes" in it')
    assert line == 'description: "has \\"quotes\\" in it"'


def test_yaml_scalar_plain(kagents):
    assert kagents._yaml_scalar("model", "inherit") == "model: inherit"


# --------------------------------------------------------------------------- _computed
def test_computed_readonly_true_without_write_or_edit(kagents):
    assert kagents._computed("readonly", {"tools": "Read, Grep"}, None) == "readonly: true"


def test_computed_readonly_false_with_write(kagents):
    assert kagents._computed("readonly", {"tools": "Read, Write"}, None) == "readonly: false"


def test_computed_opencode_tools_none_when_all_present(kagents):
    assert kagents._computed("opencode_tools", {"tools": "Read, Write, Edit, Bash"}, None) is None


def test_computed_opencode_tools_lists_missing(kagents):
    line = kagents._computed("opencode_tools", {"tools": "Read, Write"}, None)
    assert line == "tools:\n  edit: false\n  bash: false"


def test_computed_model_default_when_unset(kagents):
    assert kagents._computed("model:auto", {}, None) == "model: auto"


def test_computed_model_uses_fm_override(kagents):
    assert kagents._computed("model:auto", {"model": "opus"}, None) == "model: opus"


def test_computed_model_config_beats_the_agents_own_suggestion(kagents):
    assert kagents._computed("model:auto", {"model": "opus"}, "haiku") == "model: haiku"


def test_computed_model_omitted_when_runtime_has_no_inherit_word(kagents):
    """opencode has no literal for 'use the session model', so the field goes."""
    assert kagents._computed("model:", {}, None) is None


def test_computed_model_emitted_on_opencode_when_configured(kagents):
    assert kagents._computed("model:", {}, "opus") == "model: opus"


def test_computed_unknown_spec_raises(kagents):
    with pytest.raises(ValueError, match="Unknown computed field spec"):
        kagents._computed("bogus", {}, None)


# --------------------------------------------------------------------------- render
def test_render_claude(kagents):
    out = kagents.render("orchestrator", {"description": "d", "tools": "Read, Write"}, "\n\nBody\n",
                         CLAUDE_CFG)
    assert "name: orchestrator" in out
    assert "model: inherit" in out
    assert out.endswith("Body\n")


def test_render_cursor_readonly(kagents):
    out = kagents.render("reviewer", {"description": "d", "tools": "Read"}, "\n\nBody\n", CURSOR_CFG)
    assert "readonly: true" in out
    assert "is_background: false" in out


def test_render_opencode(kagents):
    out = kagents.render("implementer", {"description": "d", "tools": "Read, Write"}, "\n\nBody\n",
                         OPENCODE_CFG)
    assert "mode: subagent" in out
    assert "edit: false" in out  # write present, edit/bash missing


def test_render_unknown_field_source_raises(kagents):
    bad_cfg = {"fields": [["x", "bogus:y"]]}
    with pytest.raises(ValueError, match="Unknown field source"):
        kagents.render("n", {}, "\n", bad_cfg)


# --------------------------------------------------------------------------- models
def test_generate_all_bakes_the_configured_model_in(kagents, tmp_path):
    src, cache = tmp_path / "agents", tmp_path / "cache"
    src.mkdir()
    (src / "implementer.md").write_text('---\ndescription: "D"\ntools: Read\n---\n\nBody\n')
    kagents.generate_all(src, {"claude": CLAUDE_CFG}, cache, {"implementer": "opus"})
    assert "model: opus" in (cache / "claude" / "implementer.md").read_text()


def test_generate_all_falls_back_to_the_runtime_default(kagents, tmp_path):
    src, cache = tmp_path / "agents", tmp_path / "cache"
    src.mkdir()
    (src / "implementer.md").write_text('---\ndescription: "D"\ntools: Read\n---\n\nBody\n')
    kagents.generate_all(src, {"claude": CLAUDE_CFG}, cache, {})
    assert "model: inherit" in (cache / "claude" / "implementer.md").read_text()


# --------------------------------------------------------------------------- generate_all
def test_generate_all_writes_and_prunes_stale(kagents, tmp_path):
    src = tmp_path / "agents"
    src.mkdir()
    (src / "a.md").write_text('---\ndescription: "A"\ntools: Read\n---\n\nBody A\n')
    cache = tmp_path / "cache"
    runtimes_cfg = {"claude": CLAUDE_CFG}
    kagents.generate_all(src, runtimes_cfg, cache)
    assert (cache / "claude" / "a.md").is_file()

    # A stale file left over from a previous run (agent renamed/removed
    # upstream) must be pruned on the next generation.
    (cache / "claude" / "stale.md").write_text("leftover")
    kagents.generate_all(src, runtimes_cfg, cache)
    assert not (cache / "claude" / "stale.md").exists()
    assert (cache / "claude" / "a.md").is_file()
