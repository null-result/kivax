"""Unit tests for share/lib/kivax_trace.py."""
import json

import pytest

pytestmark = pytest.mark.unit


def _tag_file(root, path, ids):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(f'@pytest.mark.req("{i}")\ndef test_{n}(): pass\n'
                          for n, i in enumerate(ids)))


# --------------------------------------------------------------------------- scan_tests
def test_scan_tests_finds_tagged_ids(ktrace, tmp_path, minimal_config):
    _tag_file(tmp_path, "tests/test_a.py", ["REQ-01-001", "IT-01-001"])
    cfg = minimal_config()
    profiles = [{"name": "python-pytest", "root": "",
                "test_globs": ["tests/**/*.py"],
                "id_tag_regexes": cfg["stack"]["profiles"]["python-pytest"]["id_tag_regexes"]}]
    found = ktrace.scan_tests(tmp_path, profiles)
    assert "REQ-01-001" in found and "IT-01-001" in found
    assert found["REQ-01-001"][0].startswith("[python-pytest] tests/test_a.py:")


def test_scan_tests_anchors_to_profile_root_for_monorepos(ktrace, tmp_path):
    _tag_file(tmp_path, "backend/tests/test_a.py", ["REQ-01-001"])
    profiles = [{"name": "backend", "root": "backend", "test_globs": ["tests/**/*.py"],
                "id_tag_regexes": [r'@pytest\.mark\.req\("(?P<id>(?:REQ|IT)-\d{2,}-\d{3})"\)']}]
    found = ktrace.scan_tests(tmp_path, profiles)
    assert "REQ-01-001" in found
    assert found["REQ-01-001"][0] == "[backend] backend/tests/test_a.py:1"


def test_scan_tests_missing_regexes_exits(ktrace, tmp_path):
    with pytest.raises(SystemExit, match="does not define id_tag_regexes"):
        ktrace.scan_tests(tmp_path, [{"name": "p", "test_globs": []}])


def test_scan_tests_missing_root_dir_exits(ktrace, tmp_path):
    with pytest.raises(SystemExit, match="does not exist"):
        ktrace.scan_tests(tmp_path, [{"name": "p", "root": "nope",
                                      "id_tag_regexes": [r"x"], "test_globs": ["*.py"]}])


# --------------------------------------------------------------------------- main()
def _setup(tmp_path, minimal_config, monkeypatch, ktrace, spec_writer, *, feature="01", slug="booking"):
    spec_writer(tmp_path, feature, slug)
    cfg = minimal_config()
    monkeypatch.setattr(ktrace, "load_config", lambda: (tmp_path, cfg))
    return cfg


def test_uncovered_when_no_tests(ktrace, call, tmp_path, minimal_config, monkeypatch, spec_writer, capsys):
    _setup(tmp_path, minimal_config, monkeypatch, ktrace, spec_writer)
    rc = call(ktrace.main)
    assert rc == 1
    out = capsys.readouterr().out
    assert "REQ-01-001" in out and "NOT PASSING" in out


def test_passing_with_full_coverage(ktrace, call, tmp_path, minimal_config, monkeypatch, spec_writer):
    _setup(tmp_path, minimal_config, monkeypatch, ktrace, spec_writer)
    _tag_file(tmp_path, "tests/test_a.py", ["REQ-01-001", "IT-01-001"])
    rc = call(ktrace.main)
    assert rc == 0


def test_report_only_always_returns_0(ktrace, call, tmp_path, minimal_config, monkeypatch, spec_writer):
    _setup(tmp_path, minimal_config, monkeypatch, ktrace, spec_writer)
    rc = call(ktrace.main, "--report-only")
    assert rc == 0


def test_orphaned_test_tag(ktrace, call, tmp_path, minimal_config, monkeypatch, spec_writer, capsys):
    _setup(tmp_path, minimal_config, monkeypatch, ktrace, spec_writer)
    _tag_file(tmp_path, "tests/test_a.py", ["REQ-01-001", "IT-01-001", "REQ-01-999"])
    rc = call(ktrace.main)
    assert rc == 1
    assert "REQ-01-999" in capsys.readouterr().out


def test_stale_hash_names_owning_feature(ktrace, call, tmp_path, minimal_config, monkeypatch,
                                         spec_writer, capsys):
    from kivax.lib.kivax_lib import all_spec_hashes, save_lock
    cfg = _setup(tmp_path, minimal_config, monkeypatch, ktrace, spec_writer)
    _tag_file(tmp_path, "tests/test_a.py", ["REQ-01-001", "IT-01-001"])
    hashes = all_spec_hashes(tmp_path, cfg)
    stale = {kind: {rid: {"hash": "sha256:0000000000000000", "tests": []} for rid in table}
            for kind, table in hashes.items()}
    save_lock(tmp_path, cfg, stale)
    rc = call(ktrace.main)
    assert rc == 1
    out = capsys.readouterr().out
    assert "01-booking" in out


def test_json_output_shape(ktrace, call, tmp_path, minimal_config, monkeypatch, spec_writer, capsys):
    _setup(tmp_path, minimal_config, monkeypatch, ktrace, spec_writer)
    _tag_file(tmp_path, "tests/test_a.py", ["REQ-01-001", "IT-01-001"])
    call(ktrace.main, "--json")
    payload = json.loads(capsys.readouterr().out)
    assert payload["passing"] is True
    assert payload["problems"] == {"uncovered": [], "stale": [], "orphaned": []}


def test_update_lock_not_passing_message(ktrace, call, tmp_path, minimal_config, monkeypatch,
                                         spec_writer, capsys):
    _setup(tmp_path, minimal_config, monkeypatch, ktrace, spec_writer)
    rc = call(ktrace.main, "--update-lock")
    assert rc == 1
    assert "Lock NOT updated" in capsys.readouterr().out


def test_update_lock_writes_and_keeps_every_feature(ktrace, call, tmp_path, minimal_config, monkeypatch,
                                                     spec_writer, capsys):
    cfg = minimal_config()
    spec_writer(tmp_path, "01", "booking")
    spec_writer(tmp_path, "02", "cancel")
    monkeypatch.setattr(ktrace, "load_config", lambda: (tmp_path, cfg))
    _tag_file(tmp_path, "tests/test_a.py", ["REQ-01-001", "IT-01-001", "REQ-02-001", "IT-02-001"])
    rc = call(ktrace.main, "--update-lock")
    assert rc == 0
    out = capsys.readouterr().out
    assert "2 feature(s)" in out
    from kivax.lib.kivax_lib import load_lock
    lock = load_lock(tmp_path, cfg)
    assert set(lock["requirements"]) == {"REQ-01-001", "REQ-02-001"}


def test_update_lock_refuses_to_drop_still_declared_ids(ktrace, call, tmp_path, minimal_config,
                                                         monkeypatch, spec_writer, capsys):
    """Regression guard for the exact failure this guard exists to catch: if
    `all_spec_hashes` were ever narrower than the real set of features (a bug,
    not a real state a healthy run reaches), the rebuild must refuse rather
    than silently drop the other feature's still-declared ids. Simulated by
    monkeypatching `all_spec_hashes` alone — `load_all_specs` (which `known`
    is built from) stays real, so the two diverge exactly like the bug would."""
    from kivax.lib import kivax_lib
    cfg = minimal_config()
    spec_writer(tmp_path, "01", "booking")
    spec_writer(tmp_path, "02", "cancel")
    monkeypatch.setattr(ktrace, "load_config", lambda: (tmp_path, cfg))
    _tag_file(tmp_path, "tests/test_a.py",
             ["REQ-01-001", "IT-01-001", "REQ-02-001", "IT-02-001"])  # everything covered

    full_hashes = kivax_lib.all_spec_hashes(tmp_path, cfg)
    kivax_lib.save_lock(tmp_path, cfg, {kind: {rid: {"hash": h, "tests": []} for rid, h in table.items()}
                                        for kind, table in full_hashes.items()})
    narrowed = {"requirements": {"REQ-01-001": full_hashes["requirements"]["REQ-01-001"]},
               "integration_scenarios": {"IT-01-001": full_hashes["integration_scenarios"]["IT-01-001"]}}
    monkeypatch.setattr(ktrace, "all_spec_hashes", lambda root, cfg: narrowed)

    rc = call(ktrace.main, "--update-lock")
    assert rc == 1
    out = capsys.readouterr().out
    assert "didn't span every feature" in out
    assert "REQ-02-001" in out
    # And the existing lock must be untouched.
    assert set(kivax_lib.load_lock(tmp_path, cfg)["requirements"]) == {"REQ-01-001", "REQ-02-001"}


def test_update_lock_refuses_to_drop_undeclared_ids(ktrace, call, tmp_path, minimal_config, monkeypatch,
                                                     spec_writer, capsys):
    from kivax.lib import kivax_lib
    cfg = minimal_config()
    spec_writer(tmp_path, "01", "booking")
    monkeypatch.setattr(ktrace, "load_config", lambda: (tmp_path, cfg))
    _tag_file(tmp_path, "tests/test_a.py", ["REQ-01-001", "IT-01-001"])
    hashes = kivax_lib.all_spec_hashes(tmp_path, cfg)
    # Real, matching hashes for the declared ids (so they're neither stale nor
    # what triggers NOT PASSING) plus one id no spec declares at all.
    kivax_lib.save_lock(tmp_path, cfg, {
        "requirements": {"REQ-01-001": {"hash": hashes["requirements"]["REQ-01-001"], "tests": []},
                         "REQ-99-999": {"hash": "sha256:0000000000000000", "tests": []}},
        "integration_scenarios": {"IT-01-001": {"hash": hashes["integration_scenarios"]["IT-01-001"],
                                                "tests": []}},
    })
    rc = call(ktrace.main, "--update-lock")
    assert rc == 1
    out = capsys.readouterr().out
    assert "no spec declares" in out
    assert "REQ-99-999" in out
