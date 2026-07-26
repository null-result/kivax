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


def test_missing_required_path_key(kivax_cli, project, repo_dir, call, capsys):
    cfg_path = repo_dir / ".kivax/config.yml"
    cfg = yaml.safe_load(cfg_path.read_text())
    del cfg["paths"]["wiki"]
    cfg_path.write_text(yaml.safe_dump(cfg))
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "missing paths.wiki" in capsys.readouterr().out


def test_legacy_single_spec_path_keys_are_flagged(kivax_cli, project, repo_dir, call, capsys):
    cfg_path = repo_dir / ".kivax/config.yml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["paths"]["spec_md"] = "specs/spec.md"
    cfg_path.write_text(yaml.safe_dump(cfg))
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "no longer uses" in capsys.readouterr().out


def test_broken_pipeline_reported(kivax_cli, project, repo_dir, call, capsys):
    cfg_path = repo_dir / ".kivax/config.yml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["pipeline"] = ["plan", "tdd"]  # missing mandatory spec/compile
    cfg_path.write_text(yaml.safe_dump(cfg))
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "must continue with" in capsys.readouterr().out


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


def test_invalid_gate_reported(kivax_cli, project, repo_dir, call, capsys):
    cfg_path = repo_dir / ".kivax/config.yml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["gates"]["spec"] = "maybe"
    cfg_path.write_text(yaml.safe_dump(cfg))
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "gates.spec is 'maybe'" in capsys.readouterr().out


def test_missing_sync_manifest_reported(kivax_cli, project, repo_dir, call, capsys):
    (repo_dir / ".kivax/sync.json").unlink()
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "sync.json is missing" in capsys.readouterr().out


def test_stale_upstream_files_reported(kivax_cli, project, repo_dir, call, capsys):
    (repo_dir / ".claude/agents/reviewer.md.upstream").write_text("x")
    rc = call(kivax_cli.main, "doctor")
    assert rc == 1
    assert "unresolved .upstream conflict" in capsys.readouterr().out


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
