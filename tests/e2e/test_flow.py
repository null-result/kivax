"""End-to-end tests: full multi-feature flows through the real CLI, in-process
(see tests/conftest.py's module docstring for why in-process rather than
subprocess). This is the spiritual successor to the old tests/smoke.py — same
scenarios, restructured as pytest functions with a shared baseline fixture.

These deliberately overlap with tests/unit and tests/integration in which
lines they execute: the point here isn't new coverage, it's proving that long,
realistic sequences of commands — the kind a human or an agent actually
runs — behave correctly end to end, especially the anchoring guarantee this
whole project exists to enforce: editing an old feature's spec, not the one
you're working on, still has to break the build.
"""
import json

import pytest
import yaml

pytestmark = pytest.mark.e2e


def _tag_all(root, feature_numbers):
    p = root / "tests"
    p.mkdir(exist_ok=True)
    (p / "test_all.py").write_text("\n".join(
        f'@pytest.mark.req("{i}")\ndef test_{i.replace("-", "_").lower()}(): pass\n'
        for num in feature_numbers for i in (f"REQ-{num}-001", f"IT-{num}-001")))


@pytest.fixture
def three_features(project, repo_dir, spec_writer, kvalidate, ktrace, call):
    """Three compiled, fully-tested, locked features: 01-booking, 02-cancel,
    03-refund. Mirrors what a project looks like after several real feature
    cycles — the state every test in this file starts from."""
    for num, slug in (("01", "booking"), ("02", "cancel"), ("03", "refund")):
        spec_writer(repo_dir, num, slug)
    _tag_all(repo_dir, ("01", "02", "03"))
    assert call(kvalidate.main) == 0
    assert call(ktrace.main, "--update-lock") == 0
    return repo_dir


def test_validate_spans_every_feature(three_features, kvalidate, call, capsys):
    rc = call(kvalidate.main)
    assert rc == 0
    assert "3 feature(s)" in capsys.readouterr().out


def test_lock_holds_every_feature_after_update(three_features, klib):
    cfg = yaml.safe_load((three_features / ".kivax/config.yml").read_text())
    lock = klib.load_lock(three_features, cfg)
    locked = set(lock["requirements"]) | set(lock["integration_scenarios"])
    assert locked == {f"{k}-{n}-001" for n in ("01", "02", "03") for k in ("REQ", "IT")}


def test_editing_an_old_feature_spec_still_breaks_the_anchor(three_features, khash, ktrace, call, capsys):
    """The whole point of the project: a spec change on a feature that
    shipped long ago — not the one anyone is actively working on — must
    still be caught."""
    old = three_features / "specs/01-booking/spec.yml"
    doc = yaml.safe_load(old.read_text())
    doc["requirements"][0]["description"] = "Changed behavior, discovered months later."
    old.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))

    rc = call(khash.main, "--diff")
    assert rc == 2  # pending work
    out = capsys.readouterr().out
    assert "REQ-01-001" in out and "modified" in out

    rc = call(ktrace.main)
    assert rc == 1
    out = capsys.readouterr().out
    assert "NOT PASSING" in out
    assert "01-booking" in out  # names the owning feature, not just the id


def test_update_lock_refuses_when_a_feature_loses_its_spec(three_features, ktrace, call):
    """The regression guard: an uncompiled feature whose ids the lock still
    holds is a hard stop, not a silent shrink of the traceability baseline.
    It fires inside kivax_lib.load_all_specs (via sys.exit — a message, not a
    print), before kivax_trace.main even gets to compute PASSING/NOT PASSING,
    so the assertion is on the exit message `call()` returns, not on stdout."""
    hidden = three_features / "specs/02-cancel/spec.yml"
    stash = hidden.read_text()
    hidden.unlink()
    try:
        rc = call(ktrace.main, "--update-lock")
        assert isinstance(rc, str) and "REQ-02-001" in rc
    finally:
        hidden.write_text(stash)


def test_switch_to_an_older_feature_and_evolve_it(kivax_cli, three_features, klib, kstate, call, set_phase):
    """The kivax-evolve workflow: switch back to a feature that already
    shipped, and only ITS requirements sync — not the active one's."""
    rc = call(kivax_cli.main, "feature", "switch", "01", "--force")
    assert rc == 0
    cfg = yaml.safe_load((three_features / ".kivax/config.yml").read_text())
    state = kstate.load_state(three_features, cfg)
    assert state["active"]["number"] == "01"

    rc = call(kstate.main, "sync-reqs")
    assert rc == 0
    state = kstate.load_state(three_features, cfg)
    assert set(state["active"]["requirements"]) == {"REQ-01-001", "IT-01-001"}


def test_wiki_page_spanning_two_features_has_no_broken_references(three_features, khash, kwiki, call, capsys):
    call(khash.main)
    hashes = {line.split("\t")[0]: line.split("\t")[1]
             for line in capsys.readouterr().out.splitlines() if "\t" in line}
    wiki = three_features / "specs/wiki"
    wiki.mkdir(parents=True, exist_ok=True)
    (wiki / "_index.md").write_text("# Index\n- [[booking]]\n")
    (wiki / "booking.md").write_text(
        "---\nconcept: booking\nsources:\n"
        f"  - REQ-01-001@{hashes['REQ-01-001']}\n"
        f"  - REQ-02-001@{hashes['REQ-02-001']}\n"
        "---\n\n# Booking\n\nSpans two features.\n")
    rc = call(kwiki.main, "lint", "--strict")
    assert rc == 0


def test_doctor_end_to_end_on_a_healthy_multi_feature_project(kivax_cli, three_features, call, capsys):
    rc = call(kivax_cli.main, "doctor")
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_specfirst_keeps_a_specprefixed_dir_out_of_the_kivax_bucket(three_features, kspecfirst, call,
                                                                    git, capsys):
    git(three_features, "add", "-A")
    git(three_features, "commit", "-qm", "features")
    git(three_features, "checkout", "-qb", "work")
    (three_features / "specsomething").mkdir(exist_ok=True)
    (three_features / "specsomething/app.py").write_text("x = 1\n")
    (three_features / "specs/01-booking/plan.md").write_text("# plan\n")
    git(three_features, "add", "-A")
    git(three_features, "commit", "-qm", "changes")
    rc = call(kspecfirst.main, "--json")
    assert rc == 0
    buckets = json.loads(capsys.readouterr().out)
    assert "specsomething/app.py" in buckets["production"]
    assert "specs/01-booking/plan.md" in buckets["kivax"]


def test_full_feature_lifecycle_new_to_switch(kivax_cli, project, repo_dir, call, set_phase, capsys):
    """No pre-seeded specs: drives 'kivax feature' alone through three
    features end to end, the way a human actually would."""
    assert call(kivax_cli.main, "feature", "new", "booking") == 0
    set_phase("done")
    assert call(kivax_cli.main, "feature", "new", "cancel") == 0
    set_phase("done")
    assert call(kivax_cli.main, "feature", "new", "refund") == 0

    capsys.readouterr()
    assert call(kivax_cli.main, "feature", "list") == 0
    out = capsys.readouterr().out
    assert "01-booking" in out and "02-cancel" in out and "03-refund" in out

    assert call(kivax_cli.main, "feature", "switch", "01", "--force") == 0
    capsys.readouterr()
    assert call(kivax_cli.main, "feature", "show", "--json") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["number"] == "01"
