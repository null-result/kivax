"""Integration tests for `kivax feature` (bin/kivax's cmd_feature)."""
import json

import pytest
import yaml

pytestmark = pytest.mark.integration


def test_new_creates_feature_and_seeds_spec(kivax_cli, project, repo_dir, call, capsys):
    rc = call(kivax_cli.main, "feature", "new", "booking")
    assert rc == 0
    out = capsys.readouterr().out
    assert "Feature 01-booking created" in out
    assert "REQ-01-001" in out
    spec_md = repo_dir / "specs/01-booking/spec.md"
    assert spec_md.is_file()
    assert "REQ-01-001" in spec_md.read_text()
    state = yaml.safe_load((repo_dir / ".kivax/state.yml").read_text())
    assert state["active"]["number"] == "01"
    assert state["active"]["phase"] == "spec"  # first pipeline phase


def test_new_rejects_bad_slug(kivax_cli, project, call):
    rc = call(kivax_cli.main, "feature", "new", "Not_Valid!")
    assert isinstance(rc, str) and "isn't a valid slug" in rc


def test_new_no_slug_prints_usage(kivax_cli, project, call):
    rc = call(kivax_cli.main, "feature", "new")
    assert isinstance(rc, str) and "Usage: kivax feature new" in rc


def test_new_refuses_while_previous_is_in_flight(kivax_cli, project, call):
    call(kivax_cli.main, "feature", "new", "booking")
    rc = call(kivax_cli.main, "feature", "new", "cancel")
    assert isinstance(rc, str) and "one feature at a time" in rc


def test_new_force_archives_and_starts_next(kivax_cli, project, repo_dir, call):
    call(kivax_cli.main, "feature", "new", "booking")
    rc = call(kivax_cli.main, "feature", "new", "cancel", "--force")
    assert rc == 0
    state = yaml.safe_load((repo_dir / ".kivax/state.yml").read_text())
    assert state["active"]["number"] == "02"
    assert "01" in state["features"]


def test_new_after_done_allocates_next_number(kivax_cli, project, repo_dir, call, set_phase):
    call(kivax_cli.main, "feature", "new", "booking")
    set_phase("done")
    rc = call(kivax_cli.main, "feature", "new", "cancel")
    assert rc == 0
    assert (repo_dir / "specs/02-cancel").is_dir()


def test_new_duplicate_slug_rejected(kivax_cli, project, call, set_phase):
    call(kivax_cli.main, "feature", "new", "booking")
    set_phase("done")
    rc = call(kivax_cli.main, "feature", "new", "booking")
    assert isinstance(rc, str) and "already exists" in rc


def test_new_does_not_overwrite_existing_spec_md(kivax_cli, project, repo_dir, call, klib, monkeypatch):
    """The 'if not spec_md.is_file(): ...write...' guard in cmd_feature's
    'new' branch is unreachable through a single clean CLI call — a
    directory matching NN-slug is always caught by the earlier duplicate-slug
    check first. It's defensive (idempotency after a crash mid-run), so it's
    exercised here by monkeypatching that check away rather than via a
    scenario the real CLI can produce."""
    d = repo_dir / "specs" / "01-booking"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("hand-written content, do not clobber")
    monkeypatch.setattr(klib, "list_features", lambda root, cfg: [])
    rc = call(kivax_cli.main, "feature", "new", "booking")
    assert rc == 0
    assert (d / "spec.md").read_text() == "hand-written content, do not clobber"


def test_list_no_features(kivax_cli, project, call, capsys):
    rc = call(kivax_cli.main, "feature", "list")
    assert rc == 0
    assert "No features yet" in capsys.readouterr().out


def test_list_shows_phase_and_active_marker(kivax_cli, project, call, capsys):
    call(kivax_cli.main, "feature", "new", "booking")
    rc = call(kivax_cli.main, "feature", "list")
    assert rc == 0
    out = capsys.readouterr().out
    assert "01-booking" in out
    assert "not compiled yet" in out
    assert "* = active feature" in out


def test_list_shows_stale_count(kivax_cli, project, repo_dir, spec_writer, call, capsys):
    spec_writer(repo_dir, "01", "booking")
    from kivax.lib.kivax_lib import all_spec_hashes, save_lock
    cfg = yaml.safe_load((repo_dir / ".kivax/config.yml").read_text())
    hashes = all_spec_hashes(repo_dir, cfg)
    stale = {kind: {rid: {"hash": "sha256:0000000000000000", "tests": []} for rid in table}
            for kind, table in hashes.items()}
    save_lock(repo_dir, cfg, stale)
    call(kivax_cli.main, "feature", "list")
    out = capsys.readouterr().out
    assert "STALE" in out


def test_show_no_active_feature_text(kivax_cli, project, call):
    rc = call(kivax_cli.main, "feature", "show")
    assert isinstance(rc, str) and "no active feature" in rc


def test_show_no_active_feature_json(kivax_cli, project, call, capsys):
    rc = call(kivax_cli.main, "feature", "show", "--json")
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert "error" in payload


def test_show_active_json(kivax_cli, project, repo_dir, call, capsys):
    call(kivax_cli.main, "feature", "new", "booking")
    capsys.readouterr()  # discard the "Feature ... created" output
    rc = call(kivax_cli.main, "feature", "show", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["number"] == "01"
    assert payload["active"] is True
    assert payload["compiled"] is False
    assert payload["spec_yml"] == "specs/01-booking/spec.yml"


def test_show_explicit_feature_plain_text(kivax_cli, project, call, capsys, set_phase):
    call(kivax_cli.main, "feature", "new", "booking")
    set_phase("done")
    call(kivax_cli.main, "feature", "new", "cancel")
    rc = call(kivax_cli.main, "feature", "show", "--feature", "01")
    assert rc == 0
    out = capsys.readouterr().out
    assert "number: 01" in out
    assert "active: False" in out


def test_switch_already_active_is_a_noop(kivax_cli, project, call, capsys):
    call(kivax_cli.main, "feature", "new", "booking")
    rc = call(kivax_cli.main, "feature", "switch", "01")
    assert rc == 0
    assert "already active" in capsys.readouterr().out


def test_switch_refuses_mid_flow(kivax_cli, project, call, set_phase):
    call(kivax_cli.main, "feature", "new", "booking")
    set_phase("done")
    call(kivax_cli.main, "feature", "new", "cancel")
    rc = call(kivax_cli.main, "feature", "switch", "01")
    assert isinstance(rc, str) and "still" in rc


def test_switch_force_and_restores_phase(kivax_cli, project, repo_dir, call, set_phase):
    call(kivax_cli.main, "feature", "new", "booking")
    set_phase("tdd")
    call(kivax_cli.main, "feature", "new", "cancel", "--force")
    rc = call(kivax_cli.main, "feature", "switch", "01", "--force")
    assert rc == 0
    state = yaml.safe_load((repo_dir / ".kivax/state.yml").read_text())
    assert state["active"]["number"] == "01"
    assert state["active"]["phase"] == "tdd"  # restored, not the pipeline default
    assert "02" in state["features"]


def test_switch_no_number_prints_usage(kivax_cli, project, call):
    rc = call(kivax_cli.main, "feature", "switch")
    assert isinstance(rc, str) and "Usage: kivax feature switch" in rc


def test_switch_unknown_number_exits(kivax_cli, project, call):
    rc = call(kivax_cli.main, "feature", "switch", "99")
    assert isinstance(rc, str) and "no feature numbered" in rc


def test_unknown_subcommand_prints_usage(kivax_cli, project, call):
    rc = call(kivax_cli.main, "feature", "bogus")
    assert rc == 1


def test_no_subcommand_prints_usage(kivax_cli, project, call, capsys):
    rc = call(kivax_cli.main, "feature")
    assert rc == 1
    assert "kivax feature <new|list|show|switch>" in capsys.readouterr().out


# --------------------------------------------------------------------------- setup is a precondition
# PRINCIPLES.md and ARCHITECTURE.md describe the project, so they're written
# once by the kivax-setup skill before any feature exists — not checked at the
# head of every feature. 'feature new' is where that becomes mandatory.
def test_feature_new_refuses_until_the_project_is_set_up(kivax_cli, uninitialized_project, call):
    rc = call(kivax_cli.main, "feature", "new", "booking")
    assert isinstance(rc, str)
    assert "hasn't been set up yet" in rc
    assert "PRINCIPLES.md" in rc and "ARCHITECTURE.md" in rc
    assert "kivax-setup" in rc


def test_feature_new_names_only_the_missing_document(kivax_cli, uninitialized_project, call):
    (uninitialized_project / "PRINCIPLES.md").write_text("# Principles\n")
    rc = call(kivax_cli.main, "feature", "new", "booking")
    assert isinstance(rc, str)
    assert "ARCHITECTURE.md is missing" in rc
    assert "PRINCIPLES.md" not in rc


def test_feature_new_proceeds_once_setup_is_done(kivax_cli, uninitialized_project, call):
    (uninitialized_project / "PRINCIPLES.md").write_text("# Principles\n")
    (uninitialized_project / "ARCHITECTURE.md").write_text("# Architecture\n")
    assert call(kivax_cli.main, "feature", "new", "booking") == 0


def test_the_first_phase_of_a_feature_is_spec(kivax_cli, project, call, capsys):
    """Setup left the pipeline, so a feature starts on real work immediately."""
    assert call(kivax_cli.main, "feature", "new", "booking") == 0
    assert "phase:   spec" in capsys.readouterr().out
