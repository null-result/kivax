"""Unit tests for share/lib/kivax_lib.py: config/feature discovery, the
canonical spec loaders, the traceability lock, and hashing. Pure functions —
everything here takes a tmp_path as `root` and an in-memory dict as `cfg`,
never going through the CLI or an on-disk .kivax/config.yml."""
import json

import pytest
import yaml

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- feature_number_of_id
@pytest.mark.parametrize("rid,expected", [
    ("REQ-01-001", "01"),
    ("IT-12-003", "12"),
    ("REQ-001", None),          # legacy flat form: no feature prefix
    ("", None),
    (None, None),
    ("not-an-id", None),
])
def test_feature_number_of_id(klib, rid, expected):
    assert klib.feature_number_of_id(rid) == expected


# --------------------------------------------------------------------------- find_root / load_config
def test_find_root_walks_up_parents(klib, tmp_path):
    (tmp_path / ".kivax").mkdir()
    (tmp_path / ".kivax" / "config.yml").write_text("paths: {}\n")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    assert klib.find_root(nested) == tmp_path


def test_find_root_missing_exits(klib, tmp_path):
    with pytest.raises(SystemExit, match="config.yml not found"):
        klib.find_root(tmp_path)


def test_load_config_reads_yaml(klib, tmp_path):
    (tmp_path / ".kivax").mkdir()
    (tmp_path / ".kivax" / "config.yml").write_text("paths:\n  wiki: specs/wiki\n")
    root, cfg = klib.load_config(tmp_path)
    assert root == tmp_path
    assert cfg["paths"]["wiki"] == "specs/wiki"


# --------------------------------------------------------------------------- path_of
def test_path_of_resolves_relative_to_root(klib, tmp_path, minimal_config):
    cfg = minimal_config()
    assert klib.path_of(tmp_path, cfg, "wiki") == tmp_path / "specs/wiki"


def test_path_of_missing_key_exits(klib, tmp_path, minimal_config):
    cfg = minimal_config(paths={})
    with pytest.raises(SystemExit, match="missing paths.wiki"):
        klib.path_of(tmp_path, cfg, "wiki")


# --------------------------------------------------------------------------- active_profiles
def test_active_profiles_string_form(klib, minimal_config):
    cfg = minimal_config(stack={"active": "python-pytest",
                                "profiles": {"python-pytest": {"test_globs": []}}})
    out = klib.active_profiles(cfg)
    assert [p["name"] for p in out] == ["python-pytest"]
    assert out[0]["root"] == ""


def test_active_profiles_list_form_monorepo(klib, minimal_config):
    cfg = minimal_config(stack={"active": ["backend", "frontend"], "profiles": {
        "backend": {"root": "back", "test_globs": []},
        "frontend": {"root": "front", "test_globs": []},
    }})
    out = klib.active_profiles(cfg)
    assert [p["name"] for p in out] == ["backend", "frontend"]
    assert out[0]["root"] == "back"


def test_active_profiles_empty_exits(klib, minimal_config):
    cfg = minimal_config(stack={"active": None, "profiles": {}})
    with pytest.raises(SystemExit, match="stack.active is empty"):
        klib.active_profiles(cfg)


def test_active_profiles_unknown_profile_exits(klib, minimal_config):
    cfg = minimal_config(stack={"active": "ghost", "profiles": {}})
    with pytest.raises(SystemExit, match="does not exist in stack.profiles"):
        klib.active_profiles(cfg)


# --------------------------------------------------------------------------- Feature / features_root
def test_feature_name_property(klib, tmp_path):
    f = klib.Feature(number="02", slug="cancel", dir=tmp_path, spec_md=tmp_path / "spec.md",
                     spec_yml=tmp_path / "spec.yml", plan=tmp_path / "plan.md")
    assert f.name == "02-cancel"


def test_features_root_missing_key_exits(klib, tmp_path, minimal_config):
    cfg = minimal_config(paths={})
    with pytest.raises(SystemExit, match="missing paths.features"):
        klib.features_root(tmp_path, cfg)


def test_features_root_resolves(klib, tmp_path, minimal_config):
    cfg = minimal_config()
    assert klib.features_root(tmp_path, cfg) == tmp_path / "specs"


# --------------------------------------------------------------------------- list_features
def test_list_features_empty_when_dir_missing(klib, tmp_path, minimal_config):
    assert klib.list_features(tmp_path, minimal_config()) == []


def test_list_features_filters_non_feature_dirs_and_sorts(klib, tmp_path, minimal_config):
    specs = tmp_path / "specs"
    for name in ("02-cancel", "01-booking", "wiki", "not_a_feature", "10-refund"):
        (specs / name).mkdir(parents=True)
    (specs / "loose.md").write_text("x")  # a file, not a dir — must be skipped
    out = klib.list_features(tmp_path, minimal_config())
    assert [f.name for f in out] == ["01-booking", "02-cancel", "10-refund"]


def test_list_features_paths_are_correct(klib, tmp_path, minimal_config):
    (tmp_path / "specs" / "01-booking").mkdir(parents=True)
    f = klib.list_features(tmp_path, minimal_config())[0]
    assert f.spec_md == tmp_path / "specs/01-booking/spec.md"
    assert f.spec_yml == tmp_path / "specs/01-booking/spec.yml"
    assert f.plan == tmp_path / "specs/01-booking/plan.md"


# --------------------------------------------------------------------------- feature_by_number
def test_feature_by_number_exact_and_zero_padded(klib, tmp_path, minimal_config):
    (tmp_path / "specs" / "01-booking").mkdir(parents=True)
    cfg = minimal_config()
    assert klib.feature_by_number(tmp_path, cfg, "01").slug == "booking"
    assert klib.feature_by_number(tmp_path, cfg, "1").slug == "booking"


def test_feature_by_number_not_found_exits(klib, tmp_path, minimal_config):
    (tmp_path / "specs" / "01-booking").mkdir(parents=True)
    with pytest.raises(SystemExit, match="no feature numbered '99'"):
        klib.feature_by_number(tmp_path, minimal_config(), "99")


def test_feature_by_number_not_found_when_none_exist(klib, tmp_path, minimal_config):
    with pytest.raises(SystemExit, match=r"\(none yet\)"):
        klib.feature_by_number(tmp_path, minimal_config(), "01")


# --------------------------------------------------------------------------- read_state / active_feature
def test_read_state_missing_file_returns_empty(klib, tmp_path, minimal_config):
    assert klib.read_state(tmp_path, minimal_config()) == {}


def test_active_feature_none_when_state_has_no_active(klib, tmp_path, minimal_config):
    cfg = minimal_config()
    (tmp_path / ".kivax").mkdir()
    (tmp_path / ".kivax/state.yml").write_text(yaml.safe_dump({"active": None}))
    assert klib.active_feature(tmp_path, cfg) is None


def test_active_feature_resolves_to_directory(klib, tmp_path, minimal_config):
    cfg = minimal_config()
    (tmp_path / "specs/01-booking").mkdir(parents=True)
    (tmp_path / ".kivax").mkdir()
    (tmp_path / ".kivax/state.yml").write_text(yaml.safe_dump({"active": {"number": "01"}}))
    f = klib.active_feature(tmp_path, cfg)
    assert f is not None and f.slug == "booking"


def test_active_feature_none_when_directory_gone(klib, tmp_path, minimal_config):
    cfg = minimal_config()
    (tmp_path / ".kivax").mkdir()
    (tmp_path / ".kivax/state.yml").write_text(yaml.safe_dump({"active": {"number": "01"}}))
    assert klib.active_feature(tmp_path, cfg) is None


def test_require_active_feature_exits_when_none(klib, tmp_path, minimal_config):
    with pytest.raises(SystemExit, match="no active feature"):
        klib.require_active_feature(tmp_path, minimal_config())


def test_require_active_feature_returns_it(klib, tmp_path, minimal_config):
    cfg = minimal_config()
    (tmp_path / "specs/01-booking").mkdir(parents=True)
    (tmp_path / ".kivax").mkdir()
    (tmp_path / ".kivax/state.yml").write_text(yaml.safe_dump({"active": {"number": "01"}}))
    assert klib.require_active_feature(tmp_path, cfg).number == "01"


# --------------------------------------------------------------------------- load_spec
def test_load_spec_missing_file_exits(klib, tmp_path, minimal_config, spec_writer):
    cfg = minimal_config()
    (tmp_path / "specs/01-booking").mkdir(parents=True)
    f = klib.list_features(tmp_path, cfg)[0]
    with pytest.raises(SystemExit, match="does not exist"):
        klib.load_spec(tmp_path, cfg, f)


def test_load_spec_not_a_mapping_exits(klib, tmp_path, minimal_config):
    cfg = minimal_config()
    d = tmp_path / "specs/01-booking"
    d.mkdir(parents=True)
    (d / "spec.yml").write_text("- just\n- a\n- list\n")
    f = klib.list_features(tmp_path, cfg)[0]
    with pytest.raises(SystemExit, match="not a valid yml mapping"):
        klib.load_spec(tmp_path, cfg, f)


def test_load_spec_defaults_to_active_feature(klib, tmp_path, minimal_config, spec_writer):
    cfg = minimal_config()
    spec_writer(tmp_path, "01", "booking")
    (tmp_path / ".kivax").mkdir()
    (tmp_path / ".kivax/state.yml").write_text(yaml.safe_dump({"active": {"number": "01"}}))
    spec = klib.load_spec(tmp_path, cfg)
    assert spec["requirements"][0]["id"] == "REQ-01-001"


def test_load_spec_explicit_feature(klib, tmp_path, minimal_config, spec_writer):
    cfg = minimal_config()
    spec_writer(tmp_path, "02", "cancel")
    f = klib.feature_by_number(tmp_path, cfg, "02")
    spec = klib.load_spec(tmp_path, cfg, f)
    assert spec["meta"]["feature"] == "cancel"


# --------------------------------------------------------------------------- load_all_specs + the guard
def test_load_all_specs_uncompiled_feature_is_none_not_dropped(klib, tmp_path, minimal_config, spec_writer):
    cfg = minimal_config()
    spec_writer(tmp_path, "01", "booking")
    (tmp_path / "specs/02-cancel").mkdir(parents=True)  # no spec.yml yet
    pairs = klib.load_all_specs(tmp_path, cfg)
    by_number = {f.number: spec for f, spec in pairs}
    assert by_number["01"] is not None
    assert by_number["02"] is None


def test_guard_blocks_when_lock_holds_uncompiled_feature_ids(klib, tmp_path, minimal_config, spec_writer):
    cfg = minimal_config()
    spec_writer(tmp_path, "01", "booking")
    (tmp_path / "specs/02-cancel").mkdir(parents=True)
    klib.save_lock(tmp_path, cfg, {"requirements": {"REQ-02-001": {"hash": "sha256:x", "tests": []}},
                                   "integration_scenarios": {}})
    with pytest.raises(SystemExit, match="have no spec.yml"):
        klib.load_all_specs(tmp_path, cfg)


def test_guard_is_silent_when_lock_has_no_uncompiled_ids(klib, tmp_path, minimal_config, spec_writer):
    cfg = minimal_config()
    spec_writer(tmp_path, "01", "booking")
    (tmp_path / "specs/02-cancel").mkdir(parents=True)
    klib.save_lock(tmp_path, cfg, {"requirements": {"REQ-01-001": {"hash": "sha256:x", "tests": []}},
                                   "integration_scenarios": {}})
    pairs = klib.load_all_specs(tmp_path, cfg)  # must not raise
    assert len(pairs) == 2


# --------------------------------------------------------------------------- all_spec_hashes / owner_of
def test_all_spec_hashes_is_the_union(klib, tmp_path, minimal_config, spec_writer):
    cfg = minimal_config()
    spec_writer(tmp_path, "01", "booking")
    spec_writer(tmp_path, "02", "cancel")
    hashes = klib.all_spec_hashes(tmp_path, cfg)
    assert set(hashes["requirements"]) == {"REQ-01-001", "REQ-02-001"}
    assert set(hashes["integration_scenarios"]) == {"IT-01-001", "IT-02-001"}


def test_all_spec_hashes_duplicate_id_exits(klib, tmp_path, minimal_config, spec_writer):
    cfg = minimal_config()
    spec_writer(tmp_path, "01", "booking")
    # Hand-craft a second feature that (illegally) reuses REQ-01-001.
    doc = yaml.safe_load((tmp_path / "specs/01-booking/spec.yml").read_text())
    doc["meta"]["feature"] = "dup"
    d = tmp_path / "specs/02-dup"
    d.mkdir(parents=True)
    (d / "spec.yml").write_text(yaml.safe_dump(doc))
    with pytest.raises(SystemExit, match="duplicate id"):
        klib.all_spec_hashes(tmp_path, cfg)


def test_owner_of_maps_ids_to_features(klib, tmp_path, minimal_config, spec_writer):
    cfg = minimal_config()
    spec_writer(tmp_path, "01", "booking")
    owners = klib.owner_of(tmp_path, cfg)
    assert owners["REQ-01-001"].name == "01-booking"


# --------------------------------------------------------------------------- lock
def test_load_lock_missing_file_returns_empty_shape(klib, tmp_path, minimal_config):
    lock = klib.load_lock(tmp_path, minimal_config())
    assert lock == {"requirements": {}, "integration_scenarios": {}}


def test_save_and_load_lock_roundtrip(klib, tmp_path, minimal_config):
    cfg = minimal_config()
    p = klib.save_lock(tmp_path, cfg, {"requirements": {"REQ-01-001": {"hash": "sha256:x", "tests": []}},
                                       "integration_scenarios": {}})
    assert p.is_file()
    assert json.loads(p.read_text())["requirements"]["REQ-01-001"]["hash"] == "sha256:x"
    assert klib.load_lock(tmp_path, cfg)["requirements"]["REQ-01-001"]["hash"] == "sha256:x"


# --------------------------------------------------------------------------- hashing
def test_req_hash_excludes_notes(klib):
    a = klib.req_hash({"id": "REQ-01-001", "title": "T", "notes": "irrelevant"})
    b = klib.req_hash({"id": "REQ-01-001", "title": "T", "notes": "totally different"})
    assert a == b


def test_req_hash_changes_with_semantic_content(klib):
    a = klib.req_hash({"id": "REQ-01-001", "title": "T"})
    b = klib.req_hash({"id": "REQ-01-001", "title": "Different"})
    assert a != b


def test_req_hash_normalizes_whitespace(klib):
    a = klib.req_hash({"id": "REQ-01-001", "description": "a  b\nc"})
    b = klib.req_hash({"id": "REQ-01-001", "description": "a b c"})
    assert a == b


def test_req_hash_format(klib):
    h = klib.req_hash({"id": "REQ-01-001"})
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 16


def test_spec_hashes_shape(klib):
    spec = {
        "requirements": [{"id": "REQ-01-001", "title": "A"}],
        "integration_scenarios": [{"id": "IT-01-001", "title": "B"}],
    }
    out = klib.spec_hashes(spec)
    assert set(out) == {"requirements", "integration_scenarios"}
    assert "REQ-01-001" in out["requirements"]
    assert "IT-01-001" in out["integration_scenarios"]


def test_spec_hashes_handles_missing_lists(klib):
    assert klib.spec_hashes({}) == {"requirements": {}, "integration_scenarios": {}}


# --------------------------------------------------------------------------- pipeline_of
def test_pipeline_of_default(klib, minimal_config):
    cfg = minimal_config(pipeline=None)
    assert klib.pipeline_of(cfg) == klib.DEFAULT_PIPELINE


@pytest.mark.parametrize("pipeline", [
    ["spec", "compile", "plan"],
    ["principles", "spec", "compile"],
    ["architecture", "spec", "compile"],
    ["principles", "architecture", "spec", "compile", "deploy"],
])
def test_pipeline_of_valid_custom(klib, minimal_config, pipeline):
    cfg = minimal_config(pipeline=pipeline)
    assert klib.pipeline_of(cfg) == pipeline


def test_pipeline_of_not_a_list_exits(klib, minimal_config):
    with pytest.raises(SystemExit, match="must be a list"):
        klib.pipeline_of(minimal_config(pipeline="spec"))


def test_pipeline_of_missing_spec_compile_exits(klib, minimal_config):
    with pytest.raises(SystemExit, match="must continue with"):
        klib.pipeline_of(minimal_config(pipeline=["plan", "tdd"]))


def test_pipeline_of_reordered_mandatory_exits(klib, minimal_config):
    with pytest.raises(SystemExit, match="must continue with"):
        klib.pipeline_of(minimal_config(pipeline=["compile", "spec"]))


def test_pipeline_of_done_in_list_exits(klib, minimal_config):
    with pytest.raises(SystemExit, match="implicit terminal phase"):
        klib.pipeline_of(minimal_config(pipeline=["spec", "compile", "done"]))


def test_pipeline_of_duplicate_phase_exits(klib, minimal_config):
    with pytest.raises(SystemExit, match="duplicate phase names"):
        klib.pipeline_of(minimal_config(pipeline=["spec", "compile", "spec"]))
