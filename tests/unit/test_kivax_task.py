"""Unit tests for share/lib/kivax_task.py (the per-agent task lists)."""
import pytest

pytestmark = pytest.mark.unit


def _active(tasks=None) -> dict:
    return {"number": "01", "slug": "cancel", "phase": "spec", "tasks": tasks or {}}


def _item(tid, status, agent="researcher", text="step") -> dict:
    return {"id": tid, "agent": agent, "text": text, "status": status}


# --------------------------------------------------------------------------- containers
def test_tasks_of_creates_the_phase_bucket_on_demand(ktask):
    active = _active()
    assert ktask.tasks_of(active, "spec") == []
    assert active["tasks"] == {"spec": []}


def test_all_tasks_spans_every_phase(ktask):
    active = _active({"spec": [_item(1, "done")], "plan": [_item(2, "todo")]})
    assert sorted(t["id"] for t in ktask.all_tasks(active)) == [1, 2]


# --------------------------------------------------------------------------- ids
def test_next_id_starts_at_one(ktask):
    assert ktask.next_id(_active()) == 1


def test_next_id_is_unique_across_phases(ktask):
    active = _active({"spec": [_item(1, "done")], "plan": [_item(7, "todo")]})
    assert ktask.next_id(active) == 8


def test_next_id_never_reuses_a_cleared_id(ktask):
    """Ids stay meaningful in notes and commit messages, so a cleared list must
    not hand the same number to a different task."""
    active = _active({"spec": [_item(3, "done")]})
    active["tasks"]["spec"] = []          # what `task clear` does
    active["tasks"]["plan"] = [_item(3, "done")]
    assert ktask.next_id(active) == 4


# --------------------------------------------------------------------------- lookup
def test_find_locates_a_task_in_any_phase(ktask):
    active = _active({"spec": [_item(1, "done")], "plan": [_item(2, "todo")]})
    phase, task = ktask.find(active, 2)
    assert phase == "plan" and task["id"] == 2


def test_find_returns_none_when_absent(ktask):
    assert ktask.find(_active({"spec": [_item(1, "todo")]}), 99) is None


# --------------------------------------------------------------------------- resume point
def test_resume_point_prefers_doing_over_an_earlier_todo(ktask):
    """The whole point: an item left `doing` has half-finished work behind it,
    so it outranks a `todo` that sits earlier in the list."""
    items = [_item(1, "todo"), _item(2, "doing")]
    assert ktask.resume_point(items)["id"] == 2


def test_resume_point_falls_back_to_first_todo(ktask):
    items = [_item(1, "done"), _item(2, "todo"), _item(3, "todo")]
    assert ktask.resume_point(items)["id"] == 2


def test_resume_point_none_when_everything_is_closed(ktask):
    items = [_item(1, "done"), _item(2, "skipped")]
    assert ktask.resume_point(items) is None


def test_resume_point_empty_list(ktask):
    assert ktask.resume_point([]) is None


# --------------------------------------------------------------------------- rendering
@pytest.mark.parametrize("status,mark", [
    ("todo", " "), ("doing", "~"), ("done", "x"), ("skipped", "-"),
])
def test_format_item_marks_each_status(ktask, status, mark):
    assert ktask.format_item(_item(1, status)).startswith(f"  [{mark}] 1.")


def test_format_item_shows_the_note(ktask):
    t = _item(1, "doing")
    t["note"] = "3 of 6 sources"
    assert "(3 of 6 sources)" in ktask.format_item(t)


# --------------------------------------------------------------------------- flag parsing
def test_flag_reads_its_value(ktask):
    assert ktask._flag(["set", "1", "done", "--note", "why"], "--note") == "why"


def test_flag_absent_is_none(ktask):
    assert ktask._flag(["set", "1", "done"], "--note") is None


def test_flag_without_a_value_exits(ktask):
    with pytest.raises(SystemExit, match="needs a value"):
        ktask._flag(["set", "1", "done", "--note"], "--note")
