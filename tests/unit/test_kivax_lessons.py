"""Unit tests for share/lib/kivax_lessons.py.

The store's whole value rests on `check` being un-skippable, so most of what's
here is about applicability and acknowledgment: which lessons a feature has to
answer for, and what counts as answering.
"""
import json

import pytest

pytestmark = pytest.mark.unit


LESSON = """---
id: {id}
title: {title}
status: {status}
phases: {phases}
paths: {paths}
origin:
  feature: 01-booking
  phase: tdd
  evidence: ["commit deadbee"]
seen_in: [01-booking]
updated_at: 2026-07-31
---

# {title}

## What happened
It broke.

## Rule
Do the thing before the other thing.
"""


def _lesson(root, name, *, id="LSN-0001", title="A lesson", status="active",
            phases="[plan, tdd]", paths="[]", body=None):
    d = root / "specs" / "lessons"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(body if body is not None else LESSON.format(
        id=id, title=title, status=status, phases=phases, paths=paths), encoding="utf-8")
    return p


@pytest.fixture
def store(klessons, tmp_path, minimal_config, monkeypatch):
    """kivax_lessons wired to a throwaway root, with no git and no active
    feature unless a test sets one up."""
    cfg = minimal_config()
    monkeypatch.setattr(klessons, "load_config", lambda: (tmp_path, cfg))
    monkeypatch.setattr(klessons, "changed_files", lambda root, cfg: [])
    return tmp_path, cfg


# --------------------------------------------------------------------------- lessons_dir
def test_lessons_dir_from_config(klessons, tmp_path):
    assert klessons.lessons_dir(tmp_path, {"paths": {"lessons": "docs/lsn"}}) == tmp_path / "docs/lsn"


def test_lessons_dir_falls_back_under_features(klessons, tmp_path):
    """No paths.lessons is a config that predates the retro phase, not an
    error: the store still resolves so nothing breaks mid-migration."""
    assert klessons.lessons_dir(tmp_path, {"paths": {"features": "docs/specs"}}) == \
        tmp_path / "docs/specs/lessons"


# --------------------------------------------------------------------------- loading
def test_missing_dir_is_empty_not_an_error(klessons, tmp_path, minimal_config):
    assert klessons.load_lessons(tmp_path, minimal_config()) == []


def test_underscore_files_are_not_lessons(klessons, store):
    root, cfg = store
    _lesson(root, "_index.md")
    assert klessons.load_lessons(root, cfg) == []


def test_malformed_file_loads_with_null_frontmatter(klessons, store):
    """A typo in one lesson must not take down `list`/`relevant`/`check` —
    lint is what complains about it."""
    root, cfg = store
    _lesson(root, "LSN-0001-x.md", body="no frontmatter here\n")
    entries = klessons.load_lessons(root, cfg)
    assert len(entries) == 1 and entries[0]["fm"] is None


# --------------------------------------------------------------------------- applicability
def test_project_wide_lesson_always_applies(klessons, store):
    root, cfg = store
    _lesson(root, "LSN-0001-x.md", paths="[]")
    entries = klessons.load_lessons(root, cfg)
    assert len(klessons.applicable(entries, [])) == 1


def test_path_scoped_lesson_only_applies_on_match(klessons, store):
    root, cfg = store
    _lesson(root, "LSN-0001-x.md", paths='["src/db/**"]')
    entries = klessons.load_lessons(root, cfg)
    assert klessons.applicable(entries, ["src/api/Thing.java"]) == []
    assert len(klessons.applicable(entries, ["src/db/V2__x.sql"])) == 1


def test_retired_lesson_never_applies(klessons, store):
    root, cfg = store
    _lesson(root, "LSN-0001-x.md", status="retired")
    entries = klessons.load_lessons(root, cfg)
    assert klessons.applicable(entries, []) == []


def test_plan_paths_feed_applicability(klessons, tmp_path):
    """A path-scoped lesson has to fire at PLAN time, before the code it warns
    about exists — the plan's REQ→modules table is what makes that possible."""
    plan = tmp_path / "plan.md"
    plan.write_text("| REQ-01-001 | src/db/migrations/V3__add.sql | tests/db_test.py |\n")
    found = klessons.plan_paths(plan)
    assert "src/db/migrations/V3__add.sql" in found


def test_plan_paths_missing_file_is_empty(klessons, tmp_path):
    assert klessons.plan_paths(tmp_path / "nope.md") == []


# --------------------------------------------------------------------------- acknowledgment
def test_acknowledged_ids_reads_only_its_section(klessons, tmp_path):
    """An id mentioned in a paragraph about something else hasn't been decided
    about — only the `## Lessons applied` section counts."""
    plan = tmp_path / "plan.md"
    plan.write_text("## Lessons applied\n- LSN-0001 — done.\n\n## Risks\n- LSN-0009 might bite.\n")
    assert klessons.acknowledged_ids(plan) == {"LSN-0001"}


def test_acknowledged_ids_without_the_heading(klessons, tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("# Plan\n- LSN-0001 was considered, honest.\n")
    assert klessons.acknowledged_ids(plan) == set()


# --------------------------------------------------------------------------- check
@pytest.fixture
def feature(klessons, store, monkeypatch):
    """An active feature whose plan.md the test can rewrite at will."""
    root, cfg = store
    d = root / "specs" / "01-booking"
    d.mkdir(parents=True, exist_ok=True)
    plan = d / "plan.md"
    plan.write_text("# Plan\n")

    class _F:
        number, slug, name = "01", "booking", "01-booking"
        dir = d
        spec_md, spec_yml = d / "spec.md", d / "spec.yml"
    _F.plan = plan
    monkeypatch.setattr(klessons, "active_feature", lambda root, cfg: _F)
    return root, cfg, plan


def test_check_passes_with_no_lessons(klessons, call, feature, capsys):
    rc = call(klessons.main, "check")
    assert rc == 0
    assert "ACKNOWLEDGED" in capsys.readouterr().out


def test_check_fails_on_unacknowledged_lesson(klessons, call, feature, capsys):
    root, _cfg, _plan = feature
    _lesson(root, "LSN-0001-x.md")
    rc = call(klessons.main, "check")
    assert rc == 1
    assert "NOT ACKNOWLEDGED" in capsys.readouterr().out


def test_check_passes_once_the_plan_answers_for_it(klessons, call, feature):
    root, _cfg, plan = feature
    _lesson(root, "LSN-0001-x.md")
    plan.write_text("# Plan\n\n## Lessons applied\n- LSN-0001 — not applicable: no db here.\n")
    assert call(klessons.main, "check") == 0


def test_check_ignores_lessons_scoped_elsewhere(klessons, call, feature):
    root, _cfg, _plan = feature
    _lesson(root, "LSN-0001-x.md", paths='["frontend/**"]')
    assert call(klessons.main, "check") == 0


def test_check_json_reports_the_unacknowledged_ids(klessons, call, feature, capsys):
    root, _cfg, _plan = feature
    _lesson(root, "LSN-0001-x.md")
    rc = call(klessons.main, "check", "--json")
    assert rc == 1
    report = json.loads(capsys.readouterr().out)
    assert report["unacknowledged"] == ["LSN-0001"] and report["passing"] is False


def test_check_before_the_plan_exists_says_so(klessons, call, feature, capsys):
    """Running the gate early shouldn't read as "you forgot something" — there
    is simply nothing to acknowledge in yet."""
    root, _cfg, plan = feature
    plan.unlink()
    _lesson(root, "LSN-0001-x.md")
    assert call(klessons.main, "check") == 1
    assert "hasn't reached the 'plan' phase" in capsys.readouterr().out


def test_check_without_active_feature_exits(klessons, call, store, monkeypatch):
    monkeypatch.setattr(klessons, "active_feature", lambda root, cfg: None)
    rc = call(klessons.main, "check")
    assert isinstance(rc, str) and "no active feature" in rc


# --------------------------------------------------------------------------- relevant
def test_relevant_filters_by_phase(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", id="LSN-0001", phases="[plan]")
    _lesson(root, "LSN-0002-y.md", id="LSN-0002", phases="[it]")
    call(klessons.main, "relevant", "--phase", "plan", "--json")
    assert [x["id"] for x in json.loads(capsys.readouterr().out)] == ["LSN-0001"]


def test_relevant_does_not_path_filter_by_default(klessons, call, store, capsys):
    """At plan time nobody knows which files the feature will touch; a lesson
    withheld for that reason is a lesson about to be relearned."""
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", paths='["nowhere/**"]')
    call(klessons.main, "relevant", "--phase", "plan", "--json")
    assert len(json.loads(capsys.readouterr().out)) == 1


def test_relevant_path_filter_when_asked(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", paths='["nowhere/**"]')
    call(klessons.main, "relevant", "--phase", "plan", "--paths", "src/a.py", "--json")
    assert json.loads(capsys.readouterr().out) == []


def test_relevant_rejects_a_phase_outside_the_pipeline(klessons, call, store):
    rc = call(klessons.main, "relevant", "--phase", "deploy")
    assert isinstance(rc, str) and "not a phase" in rc


# --------------------------------------------------------------------------- new
def test_new_allocates_the_next_id(klessons, call, store, monkeypatch, capsys):
    root, _cfg = store
    monkeypatch.setattr(klessons, "active_feature", lambda root, cfg: None)
    _lesson(root, "LSN-0007-x.md", id="LSN-0007")
    assert call(klessons.main, "new", "another-thing") == 0
    assert (root / "specs/lessons/LSN-0008-another-thing.md").is_file()


def test_new_rejects_a_bad_slug(klessons, call, store):
    rc = call(klessons.main, "new", "Not A Slug")
    assert isinstance(rc, str) and "valid slug" in rc


def test_new_never_reuses_a_deleted_id(klessons, call, store, monkeypatch):
    """Same rule as feature numbers: an id that comes back means every old
    reference to it now points somewhere else."""
    root, _cfg = store
    monkeypatch.setattr(klessons, "active_feature", lambda root, cfg: None)
    _lesson(root, "LSN-0003-x.md", id="LSN-0003")
    call(klessons.main, "new", "second")
    (root / "specs/lessons/LSN-0003-x.md").unlink()
    call(klessons.main, "new", "third")
    assert (root / "specs/lessons/LSN-0005-third.md").is_file()


# --------------------------------------------------------------------------- lint
def test_lint_clean_store(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md")
    rc = call(klessons.main, "lint", "--strict")
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_lint_catches_a_lesson_with_no_rule(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", body="---\nid: LSN-0001\ntitle: T\nphases: [plan]\n"
                                        "origin:\n  feature: 01-booking\n---\n\n## What happened\nStuff.\n")
    rc = call(klessons.main, "lint", "--strict")
    assert rc == 1
    assert "diary entry" in capsys.readouterr().out


def test_lint_catches_duplicate_ids(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-a.md", id="LSN-0001")
    _lesson(root, "LSN-0001-b.md", id="LSN-0001")
    rc = call(klessons.main, "lint", "--strict")
    assert rc == 1
    assert "ambiguous" in capsys.readouterr().out


def test_lint_catches_a_phase_outside_the_pipeline(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", phases="[deploy]")
    rc = call(klessons.main, "lint", "--strict")
    assert rc == 1
    assert "not in this project's pipeline" in capsys.readouterr().out


def test_lint_requires_origin_feature(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", body="---\nid: LSN-0001\ntitle: T\nphases: [plan]\n---\n\n## Rule\nDo it.\n")
    rc = call(klessons.main, "lint", "--strict")
    assert rc == 1
    assert "origin.feature" in capsys.readouterr().out


def test_lint_retired_needs_a_reason(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", status="retired")
    rc = call(klessons.main, "lint", "--strict")
    assert rc == 1
    assert "retired_reason" in capsys.readouterr().out


def test_lint_non_strict_reports_without_failing(klessons, call, store):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", phases="[deploy]")
    assert call(klessons.main, "lint") == 0


# --------------------------------------------------------------------------- list / show
def test_list_empty_store(klessons, call, store, capsys):
    assert call(klessons.main, "list") == 0
    assert "No lessons yet" in capsys.readouterr().out


def test_list_hides_retired_unless_asked(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", status="retired")
    call(klessons.main, "list", "--json")
    assert json.loads(capsys.readouterr().out) == []
    call(klessons.main, "list", "--all", "--json")
    assert len(json.loads(capsys.readouterr().out)) == 1


def test_show_unknown_id_exits(klessons, call, store):
    rc = call(klessons.main, "show", "LSN-9999")
    assert isinstance(rc, str) and "no lesson with id" in rc


def test_show_prints_the_file(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", title="Freeze the clock")
    assert call(klessons.main, "show", "LSN-0001") == 0
    assert "Freeze the clock" in capsys.readouterr().out


def test_show_without_an_id_exits(klessons, call, store):
    rc = call(klessons.main, "show")
    assert isinstance(rc, str) and "Usage" in rc


def test_unknown_command_prints_doc(klessons, call, capsys):
    rc = call(klessons.main, "bogus")
    assert rc == 1
    assert "kivax lessons" in capsys.readouterr().out


# --------------------------------------------------------------------------- readable output
# The text mode is what a human actually sees at a gate; the JSON mode is what
# the agents parse. Both are load-bearing, so both get exercised.
def test_list_text_output_names_scope_and_provenance(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", title="Freeze the clock", paths='["src/booking/**"]')
    assert call(klessons.main, "list") == 0
    out = capsys.readouterr().out
    assert "LSN-0001" in out and "src/booking/**" in out and "01-booking" in out


def test_list_text_marks_retired(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", status="retired")
    call(klessons.main, "list", "--all")
    assert "[retired]" in capsys.readouterr().out


def test_relevant_text_output_points_at_the_gate(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", title="Freeze the clock")
    assert call(klessons.main, "relevant", "--phase", "plan") == 0
    out = capsys.readouterr().out
    assert "Freeze the clock" in out and "Lessons applied" in out


def test_relevant_text_when_nothing_applies(klessons, call, store, capsys):
    assert call(klessons.main, "relevant", "--phase", "plan") == 0
    assert "No lessons apply" in capsys.readouterr().out


def test_relevant_without_the_phase_flag_exits(klessons, call, store):
    rc = call(klessons.main, "relevant")
    assert isinstance(rc, str) and "Usage" in rc


def test_relevant_paths_flag_stops_at_the_next_option(klessons, call, store, capsys):
    """`--paths a b --json` must not swallow `--json` as a path."""
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", paths='["src/**"]')
    call(klessons.main, "relevant", "--phase", "plan", "--paths", "src/a.py", "--json")
    assert len(json.loads(capsys.readouterr().out)) == 1


def test_check_reports_unreadable_files_without_enforcing_them(klessons, call, feature, capsys):
    """A typo in one lesson can't be allowed to block the gate — it's reported,
    and lint is what makes you fix it."""
    root, _cfg, _plan = feature
    _lesson(root, "LSN-0001-x.md", body="not a lesson at all\n")
    rc = call(klessons.main, "check")
    assert rc == 0
    assert "Unreadable" in capsys.readouterr().out


def test_lint_json_output(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md")
    call(klessons.main, "lint", "--json")
    report = json.loads(capsys.readouterr().out)
    assert report == {"lessons": 1, "problems": [], "passing": True}


# --------------------------------------------------------------------------- more lint cases
def test_lint_catches_unreadable_frontmatter(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", body="---\nid: [unclosed\n---\nbody\n")
    assert call(klessons.main, "lint", "--strict") == 1
    assert "no readable yaml frontmatter" in capsys.readouterr().out


def test_lint_catches_a_hand_written_id(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "lesson.md", id="lesson-7")
    assert call(klessons.main, "lint", "--strict") == 1
    assert "must look like LSN-0007" in capsys.readouterr().out


def test_lint_catches_a_missing_title(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", title="")
    assert call(klessons.main, "lint", "--strict") == 1
    assert "missing title" in capsys.readouterr().out


def test_lint_catches_a_bad_status(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", status="maybe")
    assert call(klessons.main, "lint", "--strict") == 1
    assert "must be one of" in capsys.readouterr().out


def test_lint_catches_empty_phases(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", phases="[]")
    assert call(klessons.main, "lint", "--strict") == 1
    assert "at least one phase" in capsys.readouterr().out


def test_lint_catches_a_dangling_superseded_by(klessons, call, store, capsys):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", status="retired",
            body=LESSON.format(id="LSN-0001", title="T", status="retired",
                               phases="[plan]", paths="[]") + "\nsuperseded_by: LSN-9999\n")
    (root / "specs/lessons/LSN-0001-x.md").write_text(
        "---\nid: LSN-0001\ntitle: T\nstatus: retired\nphases: [plan]\n"
        "superseded_by: LSN-9999\norigin:\n  feature: 01-booking\n---\n\n## Rule\nDo it.\n")
    assert call(klessons.main, "lint", "--strict") == 1
    assert "doesn't match any lesson" in capsys.readouterr().out


def test_lint_accepts_a_properly_retired_lesson(klessons, call, store):
    root, _cfg = store
    _lesson(root, "LSN-0001-x.md", body="---\nid: LSN-0001\ntitle: T\nstatus: retired\n"
            "phases: [plan]\nretired_reason: the library was replaced\n"
            "origin:\n  feature: 01-booking\n---\n\n## Rule\nDo it.\n")
    assert call(klessons.main, "lint", "--strict") == 0


# --------------------------------------------------------------------------- new (edge cases)
def test_new_rejects_a_title_flag_with_no_value(klessons, call, store):
    rc = call(klessons.main, "new", "thing", "--title")
    assert isinstance(rc, str) and "--title needs a value" in rc


def test_new_refuses_to_overwrite(klessons, call, store, monkeypatch):
    root, _cfg = store
    monkeypatch.setattr(klessons, "active_feature", lambda root, cfg: None)
    (root / "specs/lessons").mkdir(parents=True, exist_ok=True)
    (root / "specs/lessons/LSN-0001-thing.md").write_text("mine\n")
    rc = call(klessons.main, "new", "thing")
    assert isinstance(rc, str) and "already exists" in rc


def test_new_without_a_slug_exits(klessons, call, store):
    rc = call(klessons.main, "new")
    assert isinstance(rc, str) and "Usage" in rc


# --------------------------------------------------------------------------- parsing / git
def test_parse_lesson_invalid_yaml(klessons, tmp_path):
    p = tmp_path / "l.md"
    p.write_text("---\nid: [unclosed\n---\nbody\n")
    assert klessons.parse_lesson(p)[0] is None


def test_parse_lesson_frontmatter_not_a_mapping(klessons, tmp_path):
    p = tmp_path / "l.md"
    p.write_text("---\n- a\n- list\n---\nbody\n")
    assert klessons.parse_lesson(p)[0] is None


def test_parse_lesson_unterminated_frontmatter(klessons, tmp_path):
    p = tmp_path / "l.md"
    p.write_text("---\nid: LSN-0001\n")
    assert klessons.parse_lesson(p)[0] is None


def test_changed_files_degrades_to_empty_without_a_base(klessons, tmp_path, minimal_config):
    """A branch with no base yet must fall back to 'only project-wide lessons
    apply', not refuse to run the gate."""
    assert klessons.changed_files(tmp_path, minimal_config()) == []


def test_changed_files_reads_the_diff(klessons, tmp_path, minimal_config, git):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@t.invalid")
    git(tmp_path, "config", "user.name", "T")
    git(tmp_path, "branch", "-M", "main")
    (tmp_path / "a.py").write_text("x = 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "checkout", "-qb", "work")
    (tmp_path / "b.py").write_text("y = 2\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "work")
    assert klessons.changed_files(tmp_path, minimal_config()) == ["b.py"]


def test_matches_any_double_star_glob(klessons):
    assert klessons.matches_any("src/db/x.sql", ["src/**"])
    assert not klessons.matches_any("web/x.ts", ["src/**"])
