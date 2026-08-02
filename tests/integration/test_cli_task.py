"""Integration tests for `kivax task` (share/lib/kivax_task.py's main)."""
import json

import pytest
import yaml

pytestmark = pytest.mark.integration


@pytest.fixture
def feature(kivax_cli, project, call):
    """An active feature, so the task commands have somewhere to write."""
    call(kivax_cli.main, "feature", "new", "booking")
    return "01-booking"


def _state(repo_dir) -> dict:
    return yaml.safe_load((repo_dir / ".kivax/state.yml").read_text())


# --------------------------------------------------------------------------- add
def test_add_appends_items_as_todo_under_the_current_phase(ktask, feature, repo_dir, call, capsys):
    assert call(ktask.main, "add", "researcher", "first step", "second step") == 0
    assert "Added 2 task(s)" in capsys.readouterr().out
    tasks = _state(repo_dir)["active"]["tasks"]
    items = tasks["spec"]          # the feature's starting phase
    assert [t["text"] for t in items] == ["first step", "second step"]
    assert {t["status"] for t in items} == {"todo"}
    assert {t["agent"] for t in items} == {"researcher"}


def test_add_without_text_prints_usage(ktask, feature, call):
    rc = call(ktask.main, "add", "researcher")
    assert isinstance(rc, str) and "Usage" in rc


def test_commands_require_an_active_feature(ktask, project, call):
    rc = call(ktask.main, "list")
    assert isinstance(rc, str) and "no active feature" in rc


# --------------------------------------------------------------------------- set
def test_set_updates_status_and_note(ktask, feature, repo_dir, call):
    call(ktask.main, "add", "researcher", "a step")
    assert call(ktask.main, "set", "1", "doing", "--note", "half done") == 0
    task = _state(repo_dir)["active"]["tasks"]["spec"][0]
    assert task["status"] == "doing" and task["note"] == "half done"


def test_set_rejects_an_unknown_status(ktask, feature, call):
    call(ktask.main, "add", "researcher", "a step")
    rc = call(ktask.main, "set", "1", "finished")
    assert isinstance(rc, str) and "Invalid status" in rc


def test_set_rejects_a_non_numeric_id(ktask, feature, call):
    rc = call(ktask.main, "set", "abc", "done")
    assert isinstance(rc, str) and "not a task id" in rc


def test_set_rejects_an_unknown_id(ktask, feature, call):
    rc = call(ktask.main, "set", "42", "done")
    assert isinstance(rc, str) and "no task with id 42" in rc


# --------------------------------------------------------------------------- list / next
def test_list_reports_the_resume_point(ktask, feature, call, capsys):
    call(ktask.main, "add", "researcher", "one", "two", "three")
    call(ktask.main, "set", "1", "done")
    call(ktask.main, "set", "3", "doing")
    capsys.readouterr()
    assert call(ktask.main, "list") == 0
    out = capsys.readouterr().out
    assert "1/3 closed." in out
    # `doing` wins over the earlier `todo` — that's the item with work behind it.
    assert "Resume at: 3. three" in out


def test_list_json_carries_the_resume_item(ktask, feature, call, capsys):
    call(ktask.main, "add", "researcher", "one", "two")
    call(ktask.main, "set", "1", "done")
    capsys.readouterr()
    call(ktask.main, "list", "--json")
    payload = json.loads(capsys.readouterr().out)
    assert payload["resume"]["id"] == 2
    assert payload["feature"] == "01-booking"


def test_list_filters_by_agent(ktask, feature, call, capsys):
    call(ktask.main, "add", "researcher", "r-step")
    call(ktask.main, "add", "spec-analyst", "s-step")
    capsys.readouterr()
    call(ktask.main, "list", "--agent", "spec-analyst")
    out = capsys.readouterr().out
    assert "s-step" in out and "r-step" not in out


def test_next_reports_nothing_when_all_closed(ktask, feature, call, capsys):
    call(ktask.main, "add", "researcher", "only step")
    call(ktask.main, "set", "1", "skipped")
    capsys.readouterr()
    call(ktask.main, "next")
    assert "No open tasks." in capsys.readouterr().out


# --------------------------------------------------------------------------- clear
def test_clear_drops_only_that_agents_items(ktask, feature, repo_dir, call):
    call(ktask.main, "add", "researcher", "r-step")
    call(ktask.main, "add", "spec-analyst", "s-step")
    assert call(ktask.main, "clear", "researcher") == 0
    items = _state(repo_dir)["active"]["tasks"]["spec"]
    assert [t["agent"] for t in items] == ["spec-analyst"]


# --------------------------------------------------------------------------- lifecycle
def test_tasks_survive_archive_and_restore(ktask, kivax_cli, feature, repo_dir, call):
    """A switch away and back must return the list intact — otherwise resuming
    an older feature silently loses the record of what was in flight."""
    call(ktask.main, "add", "researcher", "in flight")
    call(ktask.main, "set", "1", "doing", "--note", "keep me")
    call(kivax_cli.main, "feature", "new", "second", "--force")

    archived = _state(repo_dir)["features"]["01"]["tasks"]["spec"]
    assert archived[0]["note"] == "keep me"

    call(kivax_cli.main, "feature", "switch", "01", "--force")
    restored = _state(repo_dir)["active"]["tasks"]["spec"]
    assert restored[0]["status"] == "doing" and restored[0]["note"] == "keep me"


def test_state_show_surfaces_the_resume_point(kstate, ktask, feature, call, capsys):
    """Every session starts with `state show`, so the resume point has to be
    visible there and agree with `task list`."""
    call(ktask.main, "add", "implementer", "one", "two")
    call(ktask.main, "set", "2", "doing")
    capsys.readouterr()
    call(kstate.main, "show")
    out = capsys.readouterr().out
    assert "Open tasks in this phase: 2" in out
    assert "resume at 2. two" in out
