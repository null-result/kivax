"""Integration tests for `kivax doctor` (bin/kivax's cmd_doctor + _check_features)."""
import pytest
import yaml

pytestmark = pytest.mark.integration


def test_not_installed(kivax_cli, use_store, repo_dir, call, capsys):
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "NOT INSTALLED" in capsys.readouterr().out


def test_clean_project_is_ok(kivax_cli, project, call, capsys):
    rc = call(kivax_cli.main, "doctor")
    assert rc == 0
    assert "OK: project installation looks correct." in capsys.readouterr().out


def test_missing_features_path_key(kivax_cli, project, repo_dir, call, capsys):
    cfg_path = repo_dir / ".kivax/config.yml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["paths"] = {}
    cfg_path.write_text(yaml.safe_dump(cfg))
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "missing paths.features" in capsys.readouterr().out


def test_obsolete_keys_are_named_with_what_replaced_them(kivax_cli, project, repo_dir,
                                                         call, capsys):
    """An old config isn't broken — it's just no longer in charge. Doctor's job
    is to make sure nobody keeps believing otherwise."""
    cfg_path = repo_dir / ".kivax/config.yml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["version"] = 2
    cfg["pipeline"] = ["plan", "tdd"]
    cfg["paths"]["spec_md"] = "specs/spec.md"
    cfg_path.write_text(yaml.safe_dump(cfg))
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    out = capsys.readouterr().out
    assert "expects 3" in out
    assert "pipeline" in out
    assert "paths.spec_md" in out


def test_a_stale_pipeline_key_cannot_break_the_flow(kivax_cli, project, repo_dir, call, capsys):
    """The phases still all have to be there, whatever the config claims."""
    cfg_path = repo_dir / ".kivax/config.yml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["pipeline"] = ["spec", "compile"]
    cfg_path.write_text(yaml.safe_dump(cfg))
    call(kivax_cli.main, "doctor")
    assert "kivax-retro/SKILL.md is missing" not in capsys.readouterr().out


def test_unknown_agent_in_the_models_block_reported(kivax_cli, project, repo_dir, call, capsys):
    """A typo here is otherwise silent: the agent renders with no model set."""
    cfg_path = repo_dir / ".kivax/config.yml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["agents"] = {"implementor": {"model": "opus"}}  # sic
    cfg_path.write_text(yaml.safe_dump(cfg))
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    out = capsys.readouterr().out
    assert "agents.implementor" in out
    assert "implementer" in out, "the message should list the real agent names"


def test_default_is_accepted_in_the_models_block(kivax_cli, project, repo_dir, call, capsys):
    cfg_path = repo_dir / ".kivax/config.yml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["agents"] = {"default": {"model": "sonnet"}}
    cfg_path.write_text(yaml.safe_dump(cfg))
    call(kivax_cli.main, "doctor")
    assert "agents.default" not in capsys.readouterr().out


def test_missing_runtime_dir_reported(kivax_cli, project, repo_dir, call, capsys):
    import shutil
    shutil.rmtree(repo_dir / ".claude/skills")
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert ".claude/skills" in capsys.readouterr().out


def test_missing_ambient_file_reported(kivax_cli, project, repo_dir, call, capsys):
    (repo_dir / "AGENTS.md").unlink()
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "AGENTS.md is missing" in capsys.readouterr().out


def test_missing_phase_skill_reported(kivax_cli, project, repo_dir, call, capsys):
    import shutil
    shutil.rmtree(repo_dir / ".claude/skills/kivax-tdd")
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    out = capsys.readouterr().out
    assert "kivax-tdd/SKILL.md is missing" in out


def test_every_pipeline_phase_is_checked_for_its_skill(kivax_cli, project, repo_dir,
                                                       call, capsys):
    """principles/architecture are mandatory now, so their skills are too."""
    import shutil
    shutil.rmtree(repo_dir / ".claude/skills/kivax-principles")
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "kivax-principles/SKILL.md is missing" in capsys.readouterr().out


# --------------------------------------------------------------------------- _check_features via doctor
def test_features_root_missing_directory(kivax_cli, project, repo_dir, call, capsys):
    import shutil
    shutil.rmtree(repo_dir / "specs")
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "doesn't exist" in capsys.readouterr().out


def test_botched_feature_directory_reported(kivax_cli, project, repo_dir, call, capsys):
    (repo_dir / "specs/1-typo").mkdir(parents=True)
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "1-typo" in capsys.readouterr().out


def test_plain_documentation_folder_is_not_flagged(kivax_cli, project, repo_dir, call, capsys):
    (repo_dir / "specs/notes").mkdir(parents=True)
    (repo_dir / "specs/notes/overview.md").write_text("x")
    rc = call(kivax_cli.main, "doctor")
    assert rc == 0


def test_duplicate_feature_number_reported(kivax_cli, project, repo_dir, spec_writer, call, capsys):
    spec_writer(repo_dir, "01", "booking")
    spec_writer(repo_dir, "01", "booking-dup")
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "duplicate feature number 01" in capsys.readouterr().out


def test_duplicate_id_across_features_reported(kivax_cli, project, repo_dir, spec_writer, call, capsys):
    spec_writer(repo_dir, "01", "booking")
    doc = yaml.safe_load((repo_dir / "specs/01-booking/spec.yml").read_text())
    doc["meta"]["feature"] = "dup"
    d = repo_dir / "specs/02-dup"
    d.mkdir(parents=True)
    (d / "spec.yml").write_text(yaml.safe_dump(doc))
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "declared by both" in capsys.readouterr().out


def test_id_prefix_mismatch_reported(kivax_cli, project, repo_dir, spec_writer, call, capsys):
    spec_writer(repo_dir, "01", "booking")
    d = repo_dir / "specs/02-cancel"
    d.mkdir(parents=True)
    doc = yaml.safe_load((repo_dir / "specs/01-booking/spec.yml").read_text())
    doc["meta"]["feature"] = "cancel"
    (d / "spec.yml").write_text(yaml.safe_dump(doc))  # ids still say REQ-01-*
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    out = capsys.readouterr().out
    assert "lives in 02-cancel but carries feature number '01'" in out


def test_invalid_yaml_spec_reported(kivax_cli, project, repo_dir, call, capsys):
    d = repo_dir / "specs/01-booking"
    d.mkdir(parents=True)
    (d / "spec.yml").write_text("key: [unclosed\n")
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "not valid yml" in capsys.readouterr().out


def test_stranded_lock_ids_reported(kivax_cli, project, repo_dir, spec_writer, call, capsys):
    spec_writer(repo_dir, "01", "booking")
    from kivax_lib import all_spec_hashes, save_lock
    cfg = yaml.safe_load((repo_dir / ".kivax/config.yml").read_text())
    hashes = all_spec_hashes(repo_dir, cfg)
    hashes["requirements"]["REQ-99-001"] = "sha256:0000000000000000"
    save_lock(repo_dir, cfg, {kind: {rid: {"hash": h, "tests": []} for rid, h in table.items()}
                              for kind, table in hashes.items()})
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "feature directory is" in capsys.readouterr().out


def test_legacy_tag_regex_reported(kivax_cli, project, repo_dir, call, capsys):
    cfg_path = repo_dir / ".kivax/config.yml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["stack"]["profiles"]["python-pytest"]["id_tag_regexes"] = [
        r'@pytest\.mark\.req\("(?P<id>(?:REQ|IT)-\d{3})"\)']
    cfg_path.write_text(yaml.safe_dump(cfg))
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "invisible" in capsys.readouterr().out


def test_active_feature_directory_gone_reported(kivax_cli, project, repo_dir, call, capsys):
    call(kivax_cli.main, "feature", "new", "booking")
    import shutil
    shutil.rmtree(repo_dir / "specs/01-booking")
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "no such directory exists" in capsys.readouterr().out


# --------------------------------------------------------------------------- one-time setup
def test_pending_setup_is_a_next_step_not_a_problem_before_any_feature(
        kivax_cli, uninitialized_project, call, capsys):
    """A freshly-init'd project is not broken; it just hasn't been set up yet."""
    rc = call(kivax_cli.main, "doctor")
    out = capsys.readouterr().out
    assert "NEXT STEP" in out
    assert "kivax-setup" in out
    assert rc == 0


def test_pending_setup_is_a_problem_once_features_exist(kivax_cli, project, repo_dir,
                                                        call, capsys):
    """Features planned without them were planned against principles nobody
    wrote down — that's a real finding, not a next step."""
    call(kivax_cli.main, "feature", "new", "booking")
    (repo_dir / "PRINCIPLES.md").unlink()
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    out = capsys.readouterr().out
    assert "PRINCIPLES.md missing" in out
    assert "before the first one" in out


def test_setup_skills_are_checked_even_though_they_are_not_phases(
        kivax_cli, project, repo_dir, call, capsys):
    import shutil
    shutil.rmtree(repo_dir / ".claude/skills/kivax-setup")
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "kivax-setup/SKILL.md is missing" in capsys.readouterr().out


def test_missing_git_skill_reported(kivax_cli, project, repo_dir, call, capsys):
    """kivax-git isn't a phase, so its absence dead-ends nothing — but a human
    asking to merge would get an improvised answer instead of the protocol."""
    import shutil
    shutil.rmtree(repo_dir / ".claude/skills/kivax-git")
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    out = capsys.readouterr().out
    assert "kivax-git/SKILL.md is missing" in out
    assert "merge/release/hotfix" in out
