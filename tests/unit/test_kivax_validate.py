"""Unit tests for share/lib/kivax_validate.py."""
import pytest
import yaml

pytestmark = pytest.mark.unit


def _valid_spec(number="01", slug="booking"):
    return {
        "meta": {"feature": slug, "version": 1},
        "context": "ctx",
        "requirements": [{
            "id": f"REQ-{number}-001", "title": "T", "status": "active", "priority": "must",
            "depends_on": [], "description": "d",
            "acceptance_criteria": [{"id": f"AC-{number}-001-01", "given": "g",
                                     "when": "w", "then": "t"}],
        }],
        "integration_scenarios": [{
            "id": f"IT-{number}-001", "covers": [f"REQ-{number}-001"],
            "given": "g", "when": "w", "then": "t",
        }],
    }


def _write(root, number, slug, doc):
    d = root / "specs" / f"{number}-{slug}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.yml").write_text(yaml.safe_dump(doc, sort_keys=False))


def test_valid_single_feature(kvalidate, call, tmp_path, minimal_config, monkeypatch):
    _write(tmp_path, "01", "booking", _valid_spec())
    monkeypatch.setattr(kvalidate, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(kvalidate.main)
    assert rc == 0


def test_no_features_prints_and_returns_0(kvalidate, call, tmp_path, minimal_config, monkeypatch, capsys):
    monkeypatch.setattr(kvalidate, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(kvalidate.main)
    assert rc == 0
    assert "No features yet" in capsys.readouterr().out


def test_uncompiled_feature_is_a_note_not_an_error(kvalidate, call, tmp_path, minimal_config, monkeypatch, capsys):
    (tmp_path / "specs/01-booking").mkdir(parents=True)
    monkeypatch.setattr(kvalidate, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(kvalidate.main)
    assert rc == 0
    assert "NOTE" in capsys.readouterr().out


@pytest.mark.parametrize("mutate,expected_snippet", [
    (lambda d: d["meta"].pop("feature"), "meta.feature is required"),
    (lambda d: d["meta"].pop("version"), "meta.version is required"),
    (lambda d: d.__setitem__("requirements", []), "no requirements"),
    (lambda d: d["requirements"][0].__setitem__("id", "REQ-999"), "does not match REQ-FF-NNN"),
    (lambda d: d["requirements"][0].__setitem__("id", "REQ-02-001"), "carries feature number"),
    (lambda d: d["requirements"][0].pop("title"), "missing title"),
    (lambda d: d["requirements"][0].pop("description"), "missing description"),
    (lambda d: d["requirements"][0].__setitem__("priority", "urgent"), "priority must be one of"),
    (lambda d: d["requirements"][0].__setitem__("status", "sunset"), "status must be one of"),
    (lambda d: d["requirements"][0].__setitem__("acceptance_criteria", []), ">=1 acceptance_criteria"),
    (lambda d: d["requirements"][0]["acceptance_criteria"][0].__setitem__("id", "AC-bad"),
     "does not match AC-FF-NNN-MM"),
    (lambda d: d["requirements"][0]["acceptance_criteria"][0].__setitem__("id", "AC-01-002-01"),
     "does not belong to this requirement"),
    (lambda d: d["requirements"][0]["acceptance_criteria"][0].pop("given"), "missing 'given'"),
    (lambda d: d["requirements"][0].__setitem__("depends_on", ["REQ-01-001"]), "depends on itself"),
    (lambda d: d["integration_scenarios"][0].__setitem__("id", "IT-bad"), "does not match IT-FF-NNN"),
    (lambda d: d["integration_scenarios"][0].__setitem__("id", "IT-02-001"), "carries a feature number"),
    (lambda d: d["integration_scenarios"][0].__setitem__("covers", []), "missing 'covers'"),
    (lambda d: d["integration_scenarios"][0].pop("when"), "missing 'when'"),
    (lambda d: d["requirements"][0]["depends_on"].append("REQ-01-999"), "references nonexistent"),
    (lambda d: d["integration_scenarios"][0]["covers"].append("REQ-01-999"), "references nonexistent"),
])
def test_structural_errors(kvalidate, call, tmp_path, minimal_config, monkeypatch, capsys,
                           mutate, expected_snippet):
    doc = _valid_spec()
    mutate(doc)
    _write(tmp_path, "01", "booking", doc)
    monkeypatch.setattr(kvalidate, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(kvalidate.main)
    assert rc == 1
    assert expected_snippet in capsys.readouterr().out


def test_duplicate_req_id_across_features(kvalidate, call, tmp_path, minimal_config, monkeypatch, capsys):
    _write(tmp_path, "01", "booking", _valid_spec("01"))
    dup = _valid_spec("01")
    dup["meta"]["feature"] = "dup"
    _write(tmp_path, "02", "dup", dup)  # id says 01, directory says 02: two errors, not a crash
    monkeypatch.setattr(kvalidate, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(kvalidate.main)
    assert rc == 1


def test_duplicate_req_id_same_prefix_two_dirs(kvalidate, call, tmp_path, minimal_config, monkeypatch, capsys):
    doc1 = _valid_spec("01")
    _write(tmp_path, "01", "booking", doc1)
    # A second '01-' directory won't happen via list_features's uniqueness of
    # dir names, but the compiler-level duplicate-id check is exercised by
    # planting the same id twice inside ONE feature's requirements list.
    doc = _valid_spec("01")
    doc["requirements"].append(dict(doc["requirements"][0]))
    _write(tmp_path, "01", "booking", doc)
    monkeypatch.setattr(kvalidate, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(kvalidate.main)
    assert rc == 1
    assert "duplicate id" in capsys.readouterr().out


def test_duplicate_it_id(kvalidate, call, tmp_path, minimal_config, monkeypatch, capsys):
    doc = _valid_spec("01")
    doc["requirements"].append({
        "id": "REQ-01-002", "title": "T2", "status": "active", "priority": "should",
        "depends_on": [], "description": "d2",
        "acceptance_criteria": [{"id": "AC-01-002-01", "given": "g", "when": "w", "then": "t"}],
    })
    doc["integration_scenarios"].append(dict(doc["integration_scenarios"][0]))
    _write(tmp_path, "01", "booking", doc)
    monkeypatch.setattr(kvalidate, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(kvalidate.main)
    assert rc == 1
    assert "duplicate id" in capsys.readouterr().out


def test_cross_feature_depends_on_is_valid(kvalidate, call, tmp_path, minimal_config, monkeypatch):
    _write(tmp_path, "01", "booking", _valid_spec("01"))
    doc2 = _valid_spec("02")
    doc2["meta"]["feature"] = "cancel"
    doc2["requirements"][0]["depends_on"] = ["REQ-01-001"]  # legit: another feature's REQ
    _write(tmp_path, "02", "cancel", doc2)
    monkeypatch.setattr(kvalidate, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(kvalidate.main)
    assert rc == 0


def test_dependency_cycle_detected(kvalidate, call, tmp_path, minimal_config, monkeypatch, capsys):
    doc = _valid_spec("01")
    doc["requirements"][0]["depends_on"] = ["REQ-01-002"]
    doc["requirements"].append({
        "id": "REQ-01-002", "title": "T2", "status": "active", "priority": "should",
        "depends_on": ["REQ-01-001"], "description": "d2",
        "acceptance_criteria": [{"id": "AC-01-002-01", "given": "g", "when": "w", "then": "t"}],
    })
    _write(tmp_path, "01", "booking", doc)
    monkeypatch.setattr(kvalidate, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(kvalidate.main)
    assert rc == 1
    assert "dependency cycle" in capsys.readouterr().out


def test_vague_term_is_a_warning_not_an_error(kvalidate, call, tmp_path, minimal_config, monkeypatch, capsys):
    doc = _valid_spec()
    doc["requirements"][0]["acceptance_criteria"][0]["then"] = "the response is fast"
    _write(tmp_path, "01", "booking", doc)
    monkeypatch.setattr(kvalidate, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(kvalidate.main)
    assert rc == 0
    out = capsys.readouterr().out
    assert "WARN" in out and "vague term" in out


def test_deprecated_requirement_may_have_no_acceptance_criteria(kvalidate, call, tmp_path,
                                                                 minimal_config, monkeypatch):
    doc = _valid_spec()
    doc["requirements"][0]["status"] = "deprecated"
    doc["requirements"][0]["acceptance_criteria"] = []
    _write(tmp_path, "01", "booking", doc)
    monkeypatch.setattr(kvalidate, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(kvalidate.main)
    assert rc == 0
