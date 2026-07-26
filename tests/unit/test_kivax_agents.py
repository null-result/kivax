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
    assert kagents._computed("readonly", "n", {"tools": "Read, Grep"}) == "readonly: true"


def test_computed_readonly_false_with_write(kagents):
    assert kagents._computed("readonly", "n", {"tools": "Read, Write"}) == "readonly: false"


def test_computed_opencode_tools_none_when_all_present(kagents):
    assert kagents._computed("opencode_tools", "n", {"tools": "Read, Write, Edit, Bash"}) is None


def test_computed_opencode_tools_lists_missing(kagents):
    line = kagents._computed("opencode_tools", "n", {"tools": "Read, Write"})
    assert line == "tools:\n  edit: false\n  bash: false"


def test_computed_model_default_when_unset(kagents):
    assert kagents._computed("model:auto", "n", {}) == "model: auto"


def test_computed_model_uses_fm_override(kagents):
    assert kagents._computed("model:auto", "n", {"model": "opus"}) == "model: opus"


def test_computed_unknown_spec_raises(kagents):
    with pytest.raises(ValueError, match="Unknown computed field spec"):
        kagents._computed("bogus", "n", {})


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


# --------------------------------------------------------------------------- update_canonical
def test_update_canonical_new_file(kagents, tmp_path):
    p = tmp_path / "new-agent.md"
    text = kagents.update_canonical(p, description="D", tools="Read", body="\n\nBody\n")
    assert "description: \"D\"" in text
    assert text.endswith("Body\n")


def test_update_canonical_partial_update_preserves_body(kagents, tmp_path):
    p = tmp_path / "agent.md"
    p.write_text('---\ndescription: "Old"\ntools: Read\n---\n\nOriginal body\n')
    text = kagents.update_canonical(p, model="opus")
    assert "description: \"Old\"" in text  # untouched
    assert "model: opus" in text
    assert text.endswith("Original body\n")


def test_update_canonical_model_only(kagents, tmp_path):
    p = tmp_path / "agent.md"
    p.write_text('---\ndescription: "D"\n---\n\nBody\n')
    text = kagents.update_canonical(p, model="opus")
    assert "model: opus" in text
