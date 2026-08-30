"""Unit tests for share/lib/kivax_wiki.py."""
import json

import pytest

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- parse_frontmatter
def test_parse_frontmatter_none_without_marker(kwiki):
    assert kwiki.parse_frontmatter("# just a heading\n") is None


def test_parse_frontmatter_too_few_parts(kwiki):
    assert kwiki.parse_frontmatter("---\nonly one delimiter") is None


def test_parse_frontmatter_invalid_yaml(kwiki):
    assert kwiki.parse_frontmatter("---\nkey: [unclosed\n---\nbody") is None


def test_parse_frontmatter_not_a_mapping(kwiki):
    assert kwiki.parse_frontmatter("---\n- a\n- list\n---\nbody") is None


def test_parse_frontmatter_valid(kwiki):
    fm = kwiki.parse_frontmatter("---\nconcept: booking\nsources: []\n---\n\n# Booking\n")
    assert fm == {"concept": "booking", "sources": []}


def test_wiki_dir_default_fallback(kwiki, tmp_path):
    assert kwiki.wiki_dir(tmp_path, {}) == tmp_path / "specs/wiki"


def test_wiki_dir_derives_from_the_features_root(kwiki, tmp_path):
    assert kwiki.wiki_dir(tmp_path, {"paths": {"features": "docs/spec"}}) == tmp_path / "docs/spec/wiki"


def test_wiki_dir_ignores_a_stale_paths_wiki_key(kwiki, tmp_path):
    """Configs written before Kivax owned its own layout still carry one."""
    cfg = {"paths": {"features": "specs", "wiki": "somewhere/else"}}
    assert kwiki.wiki_dir(tmp_path, cfg) == tmp_path / "specs/wiki"


# --------------------------------------------------------------------------- main()
def test_no_mode_arg_prints_doc(kwiki, call, capsys):
    rc = call(kwiki.main)
    assert rc == 1
    assert "kivax wiki lint" in capsys.readouterr().out


def test_unknown_mode_prints_doc(kwiki, call, capsys):
    rc = call(kwiki.main, "bogus")
    assert rc == 1


def test_wiki_dir_missing_returns_0(kwiki, call, tmp_path, minimal_config, monkeypatch, capsys):
    monkeypatch.setattr(kwiki, "load_config", lambda: (tmp_path, minimal_config()))
    rc = call(kwiki.main, "lint")
    assert rc == 0
    assert "hasn't been" in capsys.readouterr().out


def _page(root, name, body):
    wiki = root / "specs/wiki"
    wiki.mkdir(parents=True, exist_ok=True)
    (wiki / name).write_text(body)


def test_lint_clean_wiki(kwiki, call, tmp_path, minimal_config, monkeypatch, spec_writer, capsys):
    spec_writer(tmp_path, "01", "booking")
    cfg = minimal_config()
    monkeypatch.setattr(kwiki, "load_config", lambda: (tmp_path, cfg))
    from kivax.lib import kivax_lib
    h = kivax_lib.all_spec_hashes(tmp_path, cfg)["requirements"]["REQ-01-001"]
    _page(tmp_path, "booking.md", f"---\nconcept: booking\nsources:\n  - REQ-01-001@{h}\n---\n\n# Booking\n")
    rc = call(kwiki.main, "lint")
    assert rc == 0
    out = capsys.readouterr().out
    assert "UP TO DATE" in out


def test_lint_stale_page(kwiki, call, tmp_path, minimal_config, monkeypatch, spec_writer, capsys):
    spec_writer(tmp_path, "01", "booking")
    cfg = minimal_config()
    monkeypatch.setattr(kwiki, "load_config", lambda: (tmp_path, cfg))
    _page(tmp_path, "booking.md",
         "---\nconcept: booking\nsources:\n  - REQ-01-001@sha256:0000000000000000\n---\n\n# Booking\n")
    rc = call(kwiki.main, "lint")
    assert rc == 0  # not --strict
    out = capsys.readouterr().out
    assert "booking.md" in out and "REQ-01-001" in out


def test_lint_strict_returns_1_on_problems(kwiki, call, tmp_path, minimal_config, monkeypatch,
                                           spec_writer, capsys):
    spec_writer(tmp_path, "01", "booking")
    cfg = minimal_config()
    monkeypatch.setattr(kwiki, "load_config", lambda: (tmp_path, cfg))
    _page(tmp_path, "booking.md",
         "---\nconcept: booking\nsources:\n  - REQ-01-001@sha256:0000000000000000\n---\n\nx\n")
    rc = call(kwiki.main, "lint", "--strict")
    assert rc == 1


def test_lint_broken_reference_nonexistent_id(kwiki, call, tmp_path, minimal_config, monkeypatch,
                                              spec_writer, capsys):
    spec_writer(tmp_path, "01", "booking")
    cfg = minimal_config()
    monkeypatch.setattr(kwiki, "load_config", lambda: (tmp_path, cfg))
    _page(tmp_path, "ghost.md",
         "---\nconcept: ghost\nsources:\n  - REQ-99-999@sha256:0000000000000000\n---\n\nx\n")
    rc = call(kwiki.main, "lint")
    out = capsys.readouterr().out
    assert "nonexistent" in out
    assert rc == 0  # not strict


def test_lint_broken_reference_deprecated_id(kwiki, call, tmp_path, minimal_config, monkeypatch, capsys):
    cfg = minimal_config()
    d = tmp_path / "specs/01-booking"
    d.mkdir(parents=True)
    import yaml
    (d / "spec.yml").write_text(yaml.safe_dump({
        "meta": {"feature": "booking", "version": 1},
        "requirements": [{"id": "REQ-01-001", "title": "T", "status": "deprecated",
                          "priority": "must", "description": "d"}],
        "integration_scenarios": [],
    }))
    monkeypatch.setattr(kwiki, "load_config", lambda: (tmp_path, cfg))
    from kivax.lib import kivax_lib
    h = kivax_lib.all_spec_hashes(tmp_path, cfg)["requirements"]["REQ-01-001"]
    _page(tmp_path, "booking.md", f"---\nconcept: booking\nsources:\n  - REQ-01-001@{h}\n---\n\nx\n")
    call(kwiki.main, "lint")
    assert "deprecated" in capsys.readouterr().out


def test_lint_no_provenance(kwiki, call, tmp_path, minimal_config, monkeypatch, spec_writer):
    spec_writer(tmp_path, "01", "booking")
    monkeypatch.setattr(kwiki, "load_config", lambda: (tmp_path, minimal_config()))
    _page(tmp_path, "orphan.md", "---\nconcept: orphan\nsources: []\n---\n\nx\n")
    rc = call(kwiki.main, "lint")
    assert rc == 0


def test_lint_plan_source_is_weak_provenance_not_audited(kwiki, call, tmp_path, minimal_config,
                                                          monkeypatch, spec_writer, capsys):
    spec_writer(tmp_path, "01", "booking")
    monkeypatch.setattr(kwiki, "load_config", lambda: (tmp_path, minimal_config()))
    _page(tmp_path, "p.md", "---\nconcept: p\nsources:\n  - 'plan:bookings'\n---\n\nx\n")
    call(kwiki.main, "lint")
    out = capsys.readouterr().out
    assert "no_provenance" not in out or "p.md" in out  # not treated as hashed source
    # a plan: source alone means no HASHED source -> no_provenance
    assert "No hashed provenance: specs/wiki/p.md" in out


def test_lint_malformed_source_string(kwiki, call, tmp_path, minimal_config, monkeypatch, spec_writer, capsys):
    spec_writer(tmp_path, "01", "booking")
    monkeypatch.setattr(kwiki, "load_config", lambda: (tmp_path, minimal_config()))
    _page(tmp_path, "bad.md", "---\nconcept: bad\nsources:\n  - 'not-a-valid-source-string'\n---\n\nx\n")
    call(kwiki.main, "lint")
    assert "Malformed" in capsys.readouterr().out


def test_lint_malformed_frontmatter_page(kwiki, call, tmp_path, minimal_config, monkeypatch, spec_writer, capsys):
    spec_writer(tmp_path, "01", "booking")
    monkeypatch.setattr(kwiki, "load_config", lambda: (tmp_path, minimal_config()))
    _page(tmp_path, "nofm.md", "# No frontmatter at all\n")
    call(kwiki.main, "lint")
    assert "Malformed" in capsys.readouterr().out


def test_lint_underscore_pages_are_skipped(kwiki, call, tmp_path, minimal_config, monkeypatch, spec_writer, capsys):
    spec_writer(tmp_path, "01", "booking")
    monkeypatch.setattr(kwiki, "load_config", lambda: (tmp_path, minimal_config()))
    _page(tmp_path, "_index.md", "not even frontmatter, but must be ignored\n")
    rc = call(kwiki.main, "lint")
    assert rc == 0
    assert "Wiki pages: 0" in capsys.readouterr().out


def test_lint_json_output(kwiki, call, tmp_path, minimal_config, monkeypatch, spec_writer, capsys):
    spec_writer(tmp_path, "01", "booking")
    monkeypatch.setattr(kwiki, "load_config", lambda: (tmp_path, minimal_config()))
    _page(tmp_path, "orphan.md", "---\nconcept: orphan\nsources: []\n---\n\nx\n")
    call(kwiki.main, "lint", "--json")
    payload = json.loads(capsys.readouterr().out)
    assert payload["passing"] is False
    assert "orphan.md" in " ".join(payload["no_provenance"])


def test_stale_mode_text_and_json(kwiki, call, tmp_path, minimal_config, monkeypatch, spec_writer, capsys):
    spec_writer(tmp_path, "01", "booking")
    monkeypatch.setattr(kwiki, "load_config", lambda: (tmp_path, minimal_config()))
    _page(tmp_path, "booking.md",
         "---\nconcept: booking\nsources:\n  - REQ-01-001@sha256:0000000000000000\n---\n\nx\n")
    rc = call(kwiki.main, "stale")
    assert rc == 0
    assert "booking.md" in capsys.readouterr().out

    call(kwiki.main, "stale", "--json")
    payload = json.loads(capsys.readouterr().out)
    assert "specs/wiki/booking.md" in payload


def test_stale_mode_none_message(kwiki, call, tmp_path, minimal_config, monkeypatch, spec_writer, capsys):
    spec_writer(tmp_path, "01", "booking")
    monkeypatch.setattr(kwiki, "load_config", lambda: (tmp_path, minimal_config()))
    (tmp_path / "specs/wiki").mkdir(parents=True)
    rc = call(kwiki.main, "stale")
    assert rc == 0
    assert "no stale pages" in capsys.readouterr().out
