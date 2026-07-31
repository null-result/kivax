"""Integration tests for `kivax upgrade` (bin/kivax's cmd_upgrade)."""
import json

import pytest
import yaml

pytestmark = pytest.mark.integration

SKILL_PATH = ".claude/skills/kivax-spec/SKILL.md"
STORE_SKILL_REL = "runtime/skills/kivax-spec/SKILL.md"


# --------------------------------------------------------------------------- manifest portability
# .kivax/sync.json is committed to git, so its keys have to mean the same thing
# on every teammate's machine. They used to come from str(Path), which is
# OS-dependent: a manifest written on Windows carried '\' keys that matched
# nothing on a Linux checkout, and every managed file then read as untracked.
def test_manifest_keys_are_always_posix(kivax_cli, project, use_store, repo_dir, call):
    call(kivax_cli.main, "upgrade")
    manifest = json.loads((repo_dir / ".kivax/sync.json").read_text())
    assert manifest, "expected a populated manifest"
    offenders = [k for k in manifest if "\\" in k]
    assert not offenders, f"OS-specific separators leaked into the manifest: {offenders}"


def test_legacy_backslash_manifest_is_normalized_on_load(kivax_cli, project, repo_dir):
    """A sync.json written by a pre-fix Windows install must still resolve, so
    the repair needs no migration step from the user."""
    (repo_dir / ".kivax/sync.json").write_text(
        json.dumps({r".claude\skills\kivax-spec\SKILL.md": "sha256:deadbeef"}))
    assert kivax_cli.load_manifest(repo_dir) == {SKILL_PATH: "sha256:deadbeef"}


def test_windows_written_manifest_does_not_cause_a_spurious_conflict(
        kivax_cli, project, use_store, repo_dir, call, capsys):
    """The end-to-end symptom, on a file the user customized while upstream
    stayed put. Read correctly, that's a no-op (h_up == h_synced). With the
    keys taken at face value the entry is invisible, so the file reads as
    untracked-and-differing — a conflict the user never caused."""
    manifest = json.loads((repo_dir / ".kivax/sync.json").read_text())
    assert SKILL_PATH in manifest
    (repo_dir / SKILL_PATH).write_text("---\nname: kivax-spec\n---\nMy own edit.\n")
    (repo_dir / ".kivax/sync.json").write_text(
        json.dumps({k.replace("/", "\\"): v for k, v in manifest.items()}))

    capsys.readouterr()
    assert call(kivax_cli.main, "upgrade") == 0
    out = capsys.readouterr().out
    assert "Conflicts: 0" in out or "Conflicts" not in out, out


def test_added_file_from_a_newer_store(kivax_cli, project, use_store, repo_dir, call, capsys):
    new_skill_dir = use_store / "runtime" / "skills" / "kivax-brand-new"
    new_skill_dir.mkdir(parents=True)
    (new_skill_dir / "SKILL.md").write_text("---\nname: kivax-brand-new\n---\nBody\n")
    rc = call(kivax_cli.main, "upgrade")
    assert rc == 0
    out = capsys.readouterr().out
    assert "Added: 1" in out
    assert (repo_dir / ".claude/skills/kivax-brand-new/SKILL.md").is_file()
    manifest = __import__("json").loads((repo_dir / ".kivax/sync.json").read_text())
    assert ".claude/skills/kivax-brand-new/SKILL.md" in manifest


def test_updated_when_project_never_touched_it(kivax_cli, project, use_store, repo_dir, call, capsys):
    store_file = use_store / STORE_SKILL_REL
    store_file.write_text(store_file.read_text() + "\nUpstream addition.\n")
    rc = call(kivax_cli.main, "upgrade")
    assert rc == 0
    out = capsys.readouterr().out
    assert "Updated: 1" in out
    assert "Upstream addition." in (repo_dir / SKILL_PATH).read_text()


def test_unchanged_when_neither_side_touched_it(kivax_cli, project, use_store, call, capsys):
    rc = call(kivax_cli.main, "upgrade")
    assert rc == 0
    out = capsys.readouterr().out
    assert "Updated: 0" in out
    assert "Added: 0" in out


def test_untracked_file_matching_upstream_gets_silently_tracked(kivax_cli, project, repo_dir, call):
    import json
    manifest_path = repo_dir / ".kivax/sync.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest[SKILL_PATH]
    manifest_path.write_text(json.dumps(manifest))
    rc = call(kivax_cli.main, "upgrade")
    assert rc == 0
    manifest = json.loads(manifest_path.read_text())
    assert SKILL_PATH in manifest  # re-tracked, not reported as a conflict


def test_untracked_file_differing_from_upstream_is_a_conflict(kivax_cli, project, repo_dir, call, capsys):
    import json
    manifest_path = repo_dir / ".kivax/sync.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest[SKILL_PATH]
    manifest_path.write_text(json.dumps(manifest))
    (repo_dir / SKILL_PATH).write_text("Locally hand-edited, never tracked.\n")
    rc = call(kivax_cli.main, "upgrade")
    assert rc == 1
    out = capsys.readouterr().out
    assert "CONFLICTS (1)" in out
    assert "untracked and differs" in out


def test_both_changed_writes_upstream_sidecar_and_conflicts(kivax_cli, project, use_store, repo_dir,
                                                             call, capsys):
    (repo_dir / SKILL_PATH).write_text("Local edit.\n")
    store_file = use_store / STORE_SKILL_REL
    store_file.write_text("Upstream edit, different from local.\n")
    rc = call(kivax_cli.main, "upgrade")
    assert rc == 1
    out = capsys.readouterr().out
    assert "CONFLICTS (1)" in out
    assert "you customized it AND upstream changed it" in out
    sidecar = repo_dir / (SKILL_PATH + ".upstream")
    assert sidecar.is_file()
    assert sidecar.read_text() == "Upstream edit, different from local.\n"
    assert (repo_dir / SKILL_PATH).read_text() == "Local edit.\n"  # local edit preserved


def test_dry_run_writes_nothing(kivax_cli, project, use_store, repo_dir, call, capsys):
    store_file = use_store / STORE_SKILL_REL
    original = store_file.read_text()
    store_file.write_text(original + "\nUpstream change.\n")
    rc = call(kivax_cli.main, "upgrade", "--dry-run")
    assert rc == 0
    out = capsys.readouterr().out
    assert "Would update: 1" in out
    assert "--dry-run: nothing was written" in out
    assert "Upstream change." not in (repo_dir / SKILL_PATH).read_text()


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
