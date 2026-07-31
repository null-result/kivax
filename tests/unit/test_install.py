"""Unit tests for install.py."""
import os

import pytest

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- ensure_pyyaml
def test_ensure_pyyaml_already_installed_is_a_noop(kivax_install):
    kivax_install.ensure_pyyaml()  # yaml is a real dependency of the test env; must not raise/print


def test_ensure_pyyaml_warns_when_every_pip_attempt_fails(kivax_install, monkeypatch, capsys):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "yaml":
            raise ImportError
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)


    def fake_run(cmd, **kwargs):
        raise FileNotFoundError
    monkeypatch.setattr(kivax_install.subprocess, "run", fake_run)

    kivax_install.ensure_pyyaml()
    out = capsys.readouterr().out
    assert "Installing PyYAML" in out
    assert "could not install PyYAML automatically" in out


def test_ensure_pyyaml_succeeds_on_first_pip_attempt(kivax_install, monkeypatch, capsys):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "yaml":
            raise ImportError
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return object()
    monkeypatch.setattr(kivax_install.subprocess, "run", fake_run)

    kivax_install.ensure_pyyaml()
    assert len(calls) == 1
    assert "Installing PyYAML" in capsys.readouterr().out


# --------------------------------------------------------------------------- copy_tree
def test_copy_tree_recurses_and_skips_cache_dirs(kivax_install, tmp_path):
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "sub" / "a.py").write_text("x")
    (src / "__pycache__").mkdir()
    (src / "__pycache__" / "a.pyc").write_text("junk")
    (src / "b.pyc").write_text("junk")
    (src / "keep.md").write_text("keep")

    dst = tmp_path / "dst"
    kivax_install.copy_tree(src, dst)

    assert (dst / "sub" / "a.py").is_file()
    assert (dst / "keep.md").is_file()
    assert not (dst / "__pycache__").exists()
    assert not (dst / "b.pyc").exists()


# --------------------------------------------------------------------------- make_executable
@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows filesystems have no executable bit: os.chmod there only toggles "
           "read-only, so S_IXUSR can never land no matter what make_executable does. "
           "Skipped because the assertion is unrepresentable on the platform, not "
           "because the code is wrong — the 'nt' branch is covered by the next test.",
)
def test_make_executable_posix(kivax_install, tmp_path, monkeypatch):
    monkeypatch.setattr(kivax_install.os, "name", "posix")
    p = tmp_path / "script"
    p.write_text("#!/bin/sh\necho hi\n")
    p.chmod(0o644)
    kivax_install.make_executable(p)
    import stat
    mode = p.stat().st_mode
    assert mode & stat.S_IXUSR


def test_make_executable_windows_noop(kivax_install, tmp_path, monkeypatch):
    monkeypatch.setattr(kivax_install.os, "name", "nt")
    p = tmp_path / "script"
    p.write_text("x")
    before = p.stat().st_mode
    kivax_install.make_executable(p)
    assert p.stat().st_mode == before


# --------------------------------------------------------------------------- link_cli_posix
def test_link_cli_posix_creates_symlink(kivax_install, tmp_path, monkeypatch):
    # link_cli_posix only ever tries two fixed candidates: ~/.local/bin and
    # /usr/local/bin — not arbitrary PATH entries — so home() is patched to
    # make the first of those resolve to a throwaway directory.
    monkeypatch.setattr(kivax_install.Path, "home", staticmethod(lambda: tmp_path))
    candidate = tmp_path / ".local" / "bin"
    candidate.mkdir(parents=True)
    monkeypatch.setenv("PATH", str(candidate) + os.pathsep + "/usr/bin")
    cli = tmp_path / "cli-script"
    cli.write_text("x")

    linked = kivax_install.link_cli_posix(cli)
    assert linked == str(candidate)
    assert (candidate / "kivax").is_symlink()
    assert (candidate / "kivax").resolve() == cli.resolve()


def test_link_cli_posix_replaces_existing_link(kivax_install, tmp_path, monkeypatch):
    monkeypatch.setattr(kivax_install.Path, "home", staticmethod(lambda: tmp_path))
    candidate = tmp_path / ".local" / "bin"
    candidate.mkdir(parents=True)
    monkeypatch.setenv("PATH", str(candidate))
    old_target = tmp_path / "old-cli"
    old_target.write_text("old")
    (candidate / "kivax").symlink_to(old_target)

    new_cli = tmp_path / "new-cli"
    new_cli.write_text("new")
    linked = kivax_install.link_cli_posix(new_cli)
    assert linked == str(candidate)
    assert (candidate / "kivax").resolve() == new_cli.resolve()


def test_link_cli_posix_no_candidate_on_path(kivax_install, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent/only")
    monkeypatch.setattr(kivax_install.Path, "home", staticmethod(lambda: tmp_path))
    assert kivax_install.link_cli_posix(tmp_path / "cli") is None


# --------------------------------------------------------------------------- main()
def test_main_posix_with_link(kivax_install, tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    (repo / "share").mkdir(parents=True)
    (repo / "share" / "VERSION").write_text("9.9.9\n")
    (repo / "bin").mkdir()
    (repo / "bin" / "kivax").write_text("#!/usr/bin/env python3\n")

    home = tmp_path / "home"
    localbin = home / ".local" / "bin"
    localbin.mkdir(parents=True)
    monkeypatch.setattr(kivax_install.Path, "home", staticmethod(lambda: home))
    monkeypatch.setenv("PATH", str(localbin))
    monkeypatch.setattr(kivax_install, "HERE", repo)
    dest = tmp_path / "kivax-home"
    monkeypatch.setattr(kivax_install, "KIVAX_HOME", dest)
    monkeypatch.setattr(kivax_install.os, "name", "posix")

    rc = kivax_install.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "9.9.9" in out
    assert "CLI linked at" in out
    assert (dest / "VERSION").read_text().strip() == "9.9.9"
    assert (localbin / "kivax").is_symlink()


def test_main_posix_no_path_candidate(kivax_install, tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    (repo / "share").mkdir(parents=True)
    (repo / "bin").mkdir()
    (repo / "bin" / "kivax").write_text("x")
    monkeypatch.setattr(kivax_install, "HERE", repo)
    monkeypatch.setattr(kivax_install, "KIVAX_HOME", tmp_path / "kivax-home")
    monkeypatch.setattr(kivax_install.os, "name", "posix")
    monkeypatch.setenv("PATH", "/nowhere/useful")
    monkeypatch.setattr(kivax_install.Path, "home", staticmethod(lambda: tmp_path / "nohome"))

    rc = kivax_install.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "couldn't find a directory on your PATH" in out
    assert "unknown" in out  # no VERSION file was shipped


def test_main_windows_prints_powershell_instructions(kivax_install, tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    (repo / "share").mkdir(parents=True)
    (repo / "bin").mkdir()
    (repo / "bin" / "kivax").write_text("x")
    (repo / "bin" / "kivax.bat").write_text("@echo off")
    monkeypatch.setattr(kivax_install, "HERE", repo)
    monkeypatch.setattr(kivax_install, "KIVAX_HOME", tmp_path / "kivax-home")
    monkeypatch.setattr(kivax_install.os, "name", "nt")

    rc = kivax_install.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "Windows detected" in out
    assert (tmp_path / "kivax-home" / "bin" / "kivax.bat").is_file()


def test_main_wipes_stale_generated_cache(kivax_install, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "share").mkdir(parents=True)
    (repo / "bin").mkdir()
    (repo / "bin" / "kivax").write_text("x")
    monkeypatch.setattr(kivax_install, "HERE", repo)
    dest = tmp_path / "kivax-home"
    (dest / "_generated" / "agents" / "claude").mkdir(parents=True)
    (dest / "_generated" / "agents" / "claude" / "stale.md").write_text("old")
    monkeypatch.setattr(kivax_install, "KIVAX_HOME", dest)
    monkeypatch.setattr(kivax_install.os, "name", "posix")
    monkeypatch.setenv("PATH", "/nowhere")
    monkeypatch.setattr(kivax_install.Path, "home", staticmethod(lambda: tmp_path / "nohome"))

    kivax_install.main()
    assert not (dest / "_generated").exists()
