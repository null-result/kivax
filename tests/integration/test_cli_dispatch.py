"""Integration tests for bin/kivax's main() dispatch, cmd_version, and
cmd_passthrough.

cmd_passthrough calls os.execv(), which REPLACES the current process image.
In a real install that's fine (kivax and kivax_validate.py etc. are separate
processes); called in-process here, an unmocked os.execv would replace the
test runner itself. Every passthrough test below mocks it — see also
conftest.py's `set_phase` fixture and its docstring for the same hazard.
"""
import pytest

pytestmark = pytest.mark.integration


def test_no_args_prints_doc(kivax_cli, call, capsys):
    rc = call(kivax_cli.main)
    assert rc == 0
    assert "kivax init" in capsys.readouterr().out


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_flags(kivax_cli, call, capsys, flag):
    rc = call(kivax_cli.main, flag)
    assert rc == 0
    assert "kivax init" in capsys.readouterr().out


def test_unknown_command(kivax_cli, call, capsys):
    rc = call(kivax_cli.main, "bogus-command")
    assert rc == 1
    out = capsys.readouterr().out
    assert "Unknown command: bogus-command" in out


def test_link_alias_exits_with_hint(kivax_cli, call):
    rc = call(kivax_cli.main, "link")
    assert isinstance(rc, str) and "Did you mean 'kivax upgrade'" in rc


def test_version_with_version_file(kivax_cli, use_store, call, capsys):
    (use_store / "VERSION").write_text("3.1.4\n")
    rc = call(kivax_cli.main, "version")
    assert rc == 0
    out = capsys.readouterr().out
    assert "version: 3.1.4" in out
    assert str(use_store) in out


def test_version_without_version_file(kivax_cli, use_store, call, capsys):
    (use_store / "VERSION").unlink()  # the store fixture copies share/VERSION by default
    rc = call(kivax_cli.main, "version")
    assert rc == 0
    assert "version: unknown" in capsys.readouterr().out


def test_version_requires_kivax_home(kivax_cli, call, monkeypatch, tmp_path):
    monkeypatch.setattr(kivax_cli, "LIB", tmp_path / "nowhere")
    rc = call(kivax_cli.main, "version")
    assert isinstance(rc, str) and "can't find the Kivax global store" in rc


@pytest.mark.parametrize("name", sorted({"validate", "hash", "trace", "state", "wiki", "specfirst"}))
def test_passthrough_dispatch_execs_the_right_script(kivax_cli, project, use_store, call, monkeypatch, name):
    captured = {}

    def fake_execv(executable, args):
        captured["executable"] = executable
        captured["args"] = args
    monkeypatch.setattr(kivax_cli.os, "execv", fake_execv)

    rc = call(kivax_cli.main, name, "--some-flag")
    assert rc is None  # os.execv never returns in real life; the fake doesn't either
    assert captured["args"][1] == str(use_store / "lib" / f"kivax_{name}.py")
    assert captured["args"][2:] == ["--some-flag"]


def test_passthrough_missing_script_exits(kivax_cli, project, use_store, call, monkeypatch):
    (use_store / "lib" / "kivax_wiki.py").unlink()
    rc = call(kivax_cli.main, "wiki", "lint")
    assert isinstance(rc, str) and "no script found for 'wiki'" in rc
