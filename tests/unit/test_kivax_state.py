"""Unit tests for share/lib/kivax_state.py."""
import pytest
import yaml

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- state shape helpers
def test_empty_state_shape(kstate):
    assert kstate.empty_state() == {"version": 2, "active": None, "features": {}}


def test_load_state_missing_file_returns_empty(kstate, tmp_path, minimal_config):
    assert kstate.load_state(tmp_path, minimal_config()) == kstate.empty_state()


def test_load_state_fills_defaults(kstate, tmp_path, minimal_config):
    cfg = minimal_config()
    (tmp_path / ".kivax").mkdir()
    (tmp_path / ".kivax/state.yml").write_text(yaml.safe_dump({"version": 2}))
    st = kstate.load_state(tmp_path, cfg)
    assert st["active"] is None and st["features"] == {}


def test_save_and_load_state_roundtrip(kstate, tmp_path, minimal_config):
    cfg = minimal_config()
    st = {"version": 2, "active": {"number": "01", "slug": "x", "phase": "spec",
                                   "requirements": {}, "history": []}, "features": {}}
    kstate.save_state(tmp_path, cfg, st)
    assert kstate.load_state(tmp_path, cfg) == st


# --------------------------------------------------------------------------- log
def test_log_noop_without_active(kstate):
    st = {"active": None}
    kstate.log(st, "should not crash")
    assert st == {"active": None}


def test_log_appends_to_active_history(kstate):
    st = {"active": {"history": []}}
    kstate.log(st, "an event")
    assert st["active"]["history"][0]["event"] == "an event"
    assert "at" in st["active"]["history"][0]


# --------------------------------------------------------------------------- require_active
def test_require_active_missing_exits(kstate):
    with pytest.raises(SystemExit, match="no active feature"):
        kstate.require_active({"active": None})


def test_require_active_missing_number_exits(kstate):
    with pytest.raises(SystemExit, match="no active feature"):
        kstate.require_active({"active": {"number": None}})


def test_require_active_returns_it(kstate):
    active = {"number": "01"}
    assert kstate.require_active({"active": active}) is active


# --------------------------------------------------------------------------- lifecycle
def test_archive_active_none_sets_none(kstate):
    st = {"active": None}
    assert kstate.archive_active(st) is None
    assert st["active"] is None


def test_archive_active_moves_into_features(kstate):
    st = {"active": {"number": "01", "slug": "booking", "phase": "done",
                     "requirements": {"REQ-01-001": {"status": "green"}}, "history": [{"e": 1}]},
          "features": {}}
    num = kstate.archive_active(st)
    assert num == "01"
    assert st["active"] is None
    assert st["features"]["01"]["slug"] == "booking"
    assert st["features"]["01"]["phase"] == "done"
    assert st["features"]["01"]["requirements"] == {"REQ-01-001": {"status": "green"}}


def test_make_active(kstate):
    st = {}
    kstate.make_active(st, "02", "cancel", "spec")
    active = st["active"]
    assert active["number"] == "02"
    assert active["slug"] == "cancel"
    assert active["phase"] == "spec"
    assert active["requirements"] == {}
    assert len(active["history"]) == 1
    assert "init feature 02-cancel" in active["history"][0]["event"]


def test_restore_active_from_archived_record(kstate):
    st = {"features": {"01": {"slug": "booking", "phase": "tdd",
                              "requirements": {"REQ-01-001": {"status": "red"}},
                              "history": [{"e": "old"}]}}}
    kstate.restore_active(st, "01", "booking", "spec")
    assert st["active"]["phase"] == "tdd"  # restored, not the fallback
    assert "01" not in st["features"]  # popped out of archive
    assert len(st["active"]["history"]) == 2  # old + the "switched to" entry


def test_restore_active_falls_back_when_no_record(kstate):
    st = {"features": {}}
    kstate.restore_active(st, "03", "refund", "spec")
    assert st["active"]["phase"] == "spec"
    assert st["active"]["slug"] == "refund"


# --------------------------------------------------------------------------- main() — gate
def test_gate_unconfigured_defaults_human(kstate, call, tmp_path, minimal_config, monkeypatch, capsys):
    cfg = minimal_config(gates={})
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, cfg))
    rc = call(kstate.main, "gate", "spec")
    assert rc == 0
    assert capsys.readouterr().out.strip() == "human"


def test_gate_configured_value(kstate, call, tmp_path, minimal_config, monkeypatch, capsys):
    cfg = minimal_config(gates={"tdd": "auto"})
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, cfg))
    call(kstate.main, "gate", "tdd")
    assert capsys.readouterr().out.strip() == "auto"


def test_gate_invalid_value_exits(kstate, call, tmp_path, minimal_config, monkeypatch):
    cfg = minimal_config(gates={"spec": "maybe"})
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, cfg))
    rc = call(kstate.main, "gate", "spec")
    assert isinstance(rc, str) and "must be 'human' or 'auto'" in rc


# --------------------------------------------------------------------------- main() — init removed
def test_init_command_is_gone(kstate, call, tmp_path, minimal_config, monkeypatch):
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(kstate.main, "init", "slug")
    assert isinstance(rc, str) and "kivax feature new" in rc


# --------------------------------------------------------------------------- main() — show
def test_show_no_active_feature(kstate, call, tmp_path, minimal_config, monkeypatch, capsys):
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(kstate.main, "show")
    assert rc == 0
    assert "none" in capsys.readouterr().out


def test_show_with_active_and_archived(kstate, call, tmp_path, minimal_config, monkeypatch, capsys):
    cfg = minimal_config()
    st = {"version": 2,
         "active": {"number": "02", "slug": "cancel", "phase": "tdd",
                    "requirements": {"REQ-02-001": {"status": "green"},
                                     "REQ-02-002": {"status": "pending"}}, "history": []},
         "features": {"01": {"slug": "booking", "phase": "done"}}}
    kstate.save_state(tmp_path, cfg, st)
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, cfg))
    rc = call(kstate.main, "show")
    assert rc == 0
    out = capsys.readouterr().out
    assert "02-cancel" in out
    assert "green=1" in out and "pending=1" in out
    assert "01-booking (done)" in out


# --------------------------------------------------------------------------- main() — next
def test_next_terminal_phase(kstate, call, tmp_path, minimal_config, monkeypatch, capsys):
    cfg = minimal_config()
    kstate.save_state(tmp_path, cfg, {"version": 2, "active": {"number": "01", "phase": "done",
                                                               "requirements": {}, "history": []},
                                     "features": {}})
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, cfg))
    rc = call(kstate.main, "next")
    assert rc == 0
    assert capsys.readouterr().out.strip() == "done"


def test_next_advances(kstate, call, tmp_path, minimal_config, monkeypatch, capsys):
    cfg = minimal_config()
    kstate.save_state(tmp_path, cfg, {"version": 2, "active": {"number": "01", "phase": "spec",
                                                               "requirements": {}, "history": []},
                                     "features": {}})
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, cfg))
    call(kstate.main, "next")
    assert capsys.readouterr().out.strip() == "compile"


def test_next_phase_not_in_pipeline_exits(kstate, call, tmp_path, minimal_config, monkeypatch):
    cfg = minimal_config()
    kstate.save_state(tmp_path, cfg, {"version": 2, "active": {"number": "01", "phase": "ghost-phase",
                                                               "requirements": {}, "history": []},
                                     "features": {}})
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, cfg))
    rc = call(kstate.main, "next")
    assert isinstance(rc, str) and "is not in the pipeline" in rc


def test_next_without_active_exits(kstate, call, tmp_path, minimal_config, monkeypatch):
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(kstate.main, "next")
    assert isinstance(rc, str) and "no active feature" in rc


# --------------------------------------------------------------------------- main() — set-phase
def test_set_phase_invalid_exits(kstate, call, tmp_path, minimal_config, monkeypatch):
    cfg = minimal_config()
    kstate.save_state(tmp_path, cfg, {"version": 2, "active": {"number": "01", "phase": "spec",
                                                               "requirements": {}, "history": []},
                                     "features": {}})
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, cfg))
    rc = call(kstate.main, "set-phase", "bogus")
    assert isinstance(rc, str) and "Invalid phase" in rc


def test_set_phase_valid(kstate, call, tmp_path, minimal_config, monkeypatch, capsys):
    cfg = minimal_config()
    kstate.save_state(tmp_path, cfg, {"version": 2, "active": {"number": "01", "phase": "spec",
                                                               "requirements": {}, "history": []},
                                     "features": {}})
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, cfg))
    rc = call(kstate.main, "set-phase", "compile")
    assert rc == 0
    assert "Phase: compile" in capsys.readouterr().out
    assert kstate.load_state(tmp_path, cfg)["active"]["phase"] == "compile"


# --------------------------------------------------------------------------- main() — set-req
def test_set_req_invalid_status_exits(kstate, call, tmp_path, minimal_config, monkeypatch):
    cfg = minimal_config()
    kstate.save_state(tmp_path, cfg, {"version": 2, "active": {"number": "01", "phase": "tdd",
                                                               "requirements": {}, "history": []},
                                     "features": {}})
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, cfg))
    rc = call(kstate.main, "set-req", "REQ-01-001", "bogus")
    assert isinstance(rc, str) and "Invalid status" in rc


def test_set_req_valid_creates_entry(kstate, call, tmp_path, minimal_config, monkeypatch, capsys):
    cfg = minimal_config()
    kstate.save_state(tmp_path, cfg, {"version": 2, "active": {"number": "01", "phase": "tdd",
                                                               "requirements": {}, "history": []},
                                     "features": {}})
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, cfg))
    rc = call(kstate.main, "set-req", "REQ-01-001", "green")
    assert rc == 0
    assert "REQ-01-001: green" in capsys.readouterr().out
    st = kstate.load_state(tmp_path, cfg)
    assert st["active"]["requirements"]["REQ-01-001"]["status"] == "green"


# --------------------------------------------------------------------------- main() — sync-reqs
def test_sync_reqs_requires_active(kstate, call, tmp_path, minimal_config, monkeypatch):
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(kstate.main, "sync-reqs")
    assert isinstance(rc, str) and "no active feature" in rc


def test_sync_reqs_no_matching_feature_directory_exits(kstate, call, tmp_path, minimal_config, monkeypatch):
    cfg = minimal_config()
    kstate.save_state(tmp_path, cfg, {"version": 2, "active": {"number": "99", "phase": "tdd",
                                                               "requirements": {}, "history": []},
                                     "features": {}})
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, cfg))
    rc = call(kstate.main, "sync-reqs")
    assert isinstance(rc, str) and "no matching directory" in rc


def test_sync_reqs_adds_new_ids_only_for_active(kstate, call, tmp_path, minimal_config, monkeypatch,
                                                spec_writer, capsys):
    cfg = minimal_config()
    spec_writer(tmp_path, "01", "booking")
    spec_writer(tmp_path, "02", "cancel")  # a different feature — must NOT get synced
    kstate.save_state(tmp_path, cfg, {"version": 2, "active": {"number": "01", "phase": "tdd",
                                                               "requirements": {}, "history": []},
                                     "features": {}})
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, cfg))
    rc = call(kstate.main, "sync-reqs")
    assert rc == 0
    assert "01-booking" in capsys.readouterr().out
    st = kstate.load_state(tmp_path, cfg)
    assert set(st["active"]["requirements"]) == {"REQ-01-001", "IT-01-001"}


def test_sync_reqs_does_not_readd_existing(kstate, call, tmp_path, minimal_config, monkeypatch,
                                           spec_writer, capsys):
    cfg = minimal_config()
    spec_writer(tmp_path, "01", "booking")
    kstate.save_state(tmp_path, cfg, {
        "version": 2,
        "active": {"number": "01", "phase": "tdd",
                  "requirements": {"REQ-01-001": {"status": "green"}}, "history": []},
        "features": {}})
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, cfg))
    call(kstate.main, "sync-reqs")
    st = kstate.load_state(tmp_path, cfg)
    assert st["active"]["requirements"]["REQ-01-001"]["status"] == "green"  # untouched
    assert "IT-01-001" in st["active"]["requirements"]


def test_sync_reqs_skips_deprecated_requirements(kstate, call, tmp_path, minimal_config, monkeypatch):
    cfg = minimal_config()
    d = tmp_path / "specs/01-booking"
    d.mkdir(parents=True)
    (d / "spec.yml").write_text(yaml.safe_dump({
        "meta": {"feature": "booking", "version": 1},
        "requirements": [{"id": "REQ-01-001", "status": "deprecated"}],
        "integration_scenarios": [],
    }))
    kstate.save_state(tmp_path, cfg, {"version": 2, "active": {"number": "01", "phase": "tdd",
                                                               "requirements": {}, "history": []},
                                     "features": {}})
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, cfg))
    call(kstate.main, "sync-reqs")
    st = kstate.load_state(tmp_path, cfg)
    assert "REQ-01-001" not in st["active"]["requirements"]


# --------------------------------------------------------------------------- main() — unknown
def test_unknown_command_prints_doc(kstate, call, tmp_path, minimal_config, monkeypatch, capsys):
    monkeypatch.setattr(kstate, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(kstate.main, "bogus")
    assert rc == 1


def test_no_args_prints_doc(kstate, call, capsys):
    rc = call(kstate.main)
    assert rc == 1
    assert "kivax state show" in capsys.readouterr().out
