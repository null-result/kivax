"""Unit tests for share/lib/kivax_hash.py."""
import json

import pytest

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- compute_diff (pure)
def test_compute_diff_categorizes_everything(khash):
    current = {
        "requirements": {"REQ-01-001": "sha256:aaaa", "REQ-01-002": "sha256:bbbb",
                         "REQ-01-003": "sha256:cccc"},
        "integration_scenarios": {},
    }
    lock = {
        "requirements": {"REQ-01-001": {"hash": "sha256:aaaa"},   # unchanged
                         "REQ-01-002": {"hash": "sha256:zzzz"},   # modified
                         "REQ-01-004": {"hash": "sha256:dddd"}},  # removed
        "integration_scenarios": {},
    }
    diff = khash.compute_diff(current, lock)
    r = diff["requirements"]
    assert r["unchanged"] == ["REQ-01-001"]
    assert r["modified"] == ["REQ-01-002"]
    assert r["new"] == ["REQ-01-003"]
    assert r["removed"] == ["REQ-01-004"]


def test_compute_diff_empty_lock_is_all_new(khash):
    diff = khash.compute_diff({"requirements": {"REQ-01-001": "h"}, "integration_scenarios": {}}, {})
    assert diff["requirements"]["new"] == ["REQ-01-001"]


# --------------------------------------------------------------------------- main()
def test_plain_table_includes_owner(khash, call, tmp_path, minimal_config, monkeypatch, spec_writer, capsys):
    spec_writer(tmp_path, "01", "booking")
    monkeypatch.setattr(khash, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(khash.main)
    assert rc == 0
    out = capsys.readouterr().out
    assert "REQ-01-001" in out and "01-booking" in out


def test_diff_text_output(khash, call, tmp_path, minimal_config, monkeypatch, spec_writer, capsys):
    spec_writer(tmp_path, "01", "booking")
    monkeypatch.setattr(khash, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(khash.main, "--diff")
    assert rc == 2  # pending work, not an error
    out = capsys.readouterr().out
    assert "[requirements]" in out
    assert "new" in out


def test_diff_no_pending_work_returns_0(khash, call, tmp_path, minimal_config, monkeypatch, spec_writer):
    from kivax.lib.kivax_lib import all_spec_hashes, save_lock
    spec_writer(tmp_path, "01", "booking")
    cfg = minimal_config()
    hashes = all_spec_hashes(tmp_path, cfg)
    save_lock(tmp_path, cfg, {kind: {rid: {"hash": h, "tests": []} for rid, h in table.items()}
                              for kind, table in hashes.items()})
    monkeypatch.setattr(khash, "load_config", lambda: (tmp_path, cfg))
    rc = call(khash.main, "--diff")
    assert rc == 0


def test_diff_json_includes_owners(khash, call, tmp_path, minimal_config, monkeypatch, spec_writer, capsys):
    spec_writer(tmp_path, "01", "booking")
    monkeypatch.setattr(khash, "load_config", lambda: (tmp_path, minimal_config()))
    call(khash.main, "--diff", "--json")
    payload = json.loads(capsys.readouterr().out)
    assert payload["owners"]["REQ-01-001"] == "01-booking"
    assert "REQ-01-001" in payload["requirements"]["new"]


def test_feature_filter_narrows_table_and_diff(khash, call, tmp_path, minimal_config, monkeypatch,
                                                spec_writer, capsys):
    spec_writer(tmp_path, "01", "booking")
    spec_writer(tmp_path, "02", "cancel")
    monkeypatch.setattr(khash, "load_config", lambda: (tmp_path, minimal_config()))
    call(khash.main, "--feature", "01")
    out = capsys.readouterr().out
    assert "REQ-01-001" in out
    assert "REQ-02-001" not in out

    call(khash.main, "--diff", "--feature", "1")  # unpadded form must also work
    out = capsys.readouterr().out
    assert "REQ-01-001" in out
    assert "REQ-02-001" not in out
