"""Kivax common library (spec-anchored SDD flow).

Config loading, feature discovery, canonical spec loading, traceability lock,
and deterministic per-requirement hashing. Requires: pyyaml.

One spec per feature
--------------------
A project keeps ONE directory per feature under `paths.features`, each holding
its own `spec.md`, `spec.yml`, and `plan.md`:

    specs/
      01-booking/   spec.md  spec.yml  plan.md
      02-cancel/    spec.md  spec.yml  plan.md
      wiki/         (project-wide, not a feature)

Feature directories are recognized by FEATURE_DIR_RE (`NN-slug`), so anything
else living under that root — the wiki, a README — is simply not a feature.

REQ/IT ids carry their feature's number (`REQ-01-001`), which makes them
globally unique and lets a single test tag resolve to exactly one requirement
in exactly one feature. That is what allows the traceability lock to stay a
flat `{id: {...}}` map: the owning feature is derivable from the id itself.

The phase-driven workflow acts on the ACTIVE feature only (one per git branch,
tracked in `.kivax/state.yml`), but validation, hashing, and tracing act on the
UNION of every feature's spec — that union is what keeps the anchor alive:
editing the spec of a feature that shipped months ago still changes its hashes
and still marks its tests as potentially stale.
"""
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_REL = Path(".kivax") / "config.yml"

# A feature directory is `<number>-<slug>`, e.g. `01-cancel-booking`. Matching
# by pattern rather than by an exclusion list is what lets the wiki (and any
# other sibling) live under paths.features without special-casing, and makes a
# mistyped directory a diagnosable condition instead of a silently ignored one.
FEATURE_DIR_RE = re.compile(r"^(?P<num>\d{2,})-(?P<slug>[a-z0-9][a-z0-9-]*)$")

# REQ-01-001 / IT-01-001 — the feature number is the id's first numeric group.
ID_WITH_FF_RE = re.compile(r"^(?:REQ|IT)-(?P<ff>\d{2,})-\d{3}$")


def feature_number_of_id(rid: str) -> str | None:
    """'REQ-02-001' -> '02'. None for anything not in the canonical form."""
    m = ID_WITH_FF_RE.match(rid or "")
    return m.group("ff") if m else None


def find_root(start: Path | None = None) -> Path:
    """Walks up parent directories looking for .kivax/config.yml."""
    d = (start or Path.cwd()).resolve()
    for cand in [d, *d.parents]:
        if (cand / CONFIG_REL).is_file():
            return cand
    sys.exit(f"ERROR: .kivax/config.yml not found in {d} or any parent directory.\n"
             f"Did you run 'kivax init' at the project root?")


def load_config(root: Path | None = None) -> tuple[Path, dict]:
    root = root or find_root()
    cfg = yaml.safe_load((root / CONFIG_REL).read_text(encoding="utf-8"))
    return root, cfg


def path_of(root: Path, cfg: dict, key: str) -> Path:
    try:
        return root / cfg["paths"][key]
    except KeyError:
        sys.exit(f"ERROR: missing paths.{key} in .kivax/config.yml")


def active_profiles(cfg: dict) -> list[dict]:
    """Returns the list of active stack profiles (supports monorepos with
    several stacks at once).

    stack.active can be a string (one profile) or a list (several, e.g.
    backend + frontend). Each profile can define 'root' (the monorepo
    subdirectory its test_globs and commands are anchored to); if absent,
    the project root is assumed.
    """
    stack = cfg.get("stack", {})
    active = stack.get("active")
    names = [active] if isinstance(active, str) else list(active or [])
    profiles = stack.get("profiles", {})
    if not names:
        sys.exit("ERROR: stack.active is empty in .kivax/config.yml")
    out = []
    for name in names:
        if name not in profiles:
            sys.exit(f"ERROR: active profile '{name}' does not exist in stack.profiles")
        out.append({"name": name, "root": "", **profiles[name]})
    return out


# --------------------------------------------------------------------------- features
@dataclass(frozen=True)
class Feature:
    """One feature's directory and the three artifacts inside it. Filenames are
    fixed, not configurable: a directory whose filenames varied per feature
    couldn't be discovered by globbing, which is what list_features() does."""
    number: str          # "01"
    slug: str            # "cancel-booking"
    dir: Path
    spec_md: Path
    spec_yml: Path
    plan: Path

    @property
    def name(self) -> str:
        return f"{self.number}-{self.slug}"


def features_root(root: Path, cfg: dict) -> Path:
    paths = cfg.get("paths", {}) or {}
    if "features" not in paths:
        sys.exit("ERROR: missing paths.features in .kivax/config.yml.\n"
                 "Kivax keeps one spec per feature, in one directory each under that\n"
                 "root (e.g. specs/01-booking/spec.yml). Add to .kivax/config.yml:\n"
                 "  paths:\n    features: specs")
    return root / paths["features"]


def list_features(root: Path, cfg: dict) -> list[Feature]:
    """Every feature directory under paths.features, ordered by number."""
    base = features_root(root, cfg)
    if not base.is_dir():
        return []
    out: list[Feature] = []
    for d in base.iterdir():
        if not d.is_dir():
            continue
        m = FEATURE_DIR_RE.match(d.name)
        if not m:
            continue  # the wiki, or anything else that isn't a feature
        out.append(Feature(number=m.group("num"), slug=m.group("slug"), dir=d,
                           spec_md=d / "spec.md", spec_yml=d / "spec.yml",
                           plan=d / "plan.md"))
    return sorted(out, key=lambda f: (int(f.number), f.slug))


def feature_by_number(root: Path, cfg: dict, number: str) -> Feature:
    number = str(number).strip()
    for f in list_features(root, cfg):
        if f.number == number or f.number == number.zfill(2):
            return f
    known = ", ".join(f.name for f in list_features(root, cfg)) or "(none yet)"
    sys.exit(f"ERROR: no feature numbered '{number}'. Existing features: {known}")


def read_state(root: Path, cfg: dict) -> dict:
    """Raw state file. Kept here (rather than importing kivax_state) so the
    feature helpers stay free of a circular import."""
    p = path_of(root, cfg, "state")
    if not p.is_file():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def active_feature(root: Path, cfg: dict) -> Feature | None:
    """The feature the phase workflow is currently driving, or None."""
    number = ((read_state(root, cfg).get("active") or {}) or {}).get("number")
    if not number:
        return None
    for f in list_features(root, cfg):
        if f.number == str(number):
            return f
    return None


def require_active_feature(root: Path, cfg: dict) -> Feature:
    f = active_feature(root, cfg)
    if f is None:
        sys.exit("ERROR: no active feature. Start one with 'kivax feature new <slug>', "
                 "or resume an existing one with 'kivax feature switch <NN>'.")
    return f


def load_spec(root: Path, cfg: dict, feature: Feature | None = None) -> dict:
    """One feature's canonical spec. Defaults to the active feature."""
    feature = feature or require_active_feature(root, cfg)
    if not feature.spec_yml.is_file():
        sys.exit(f"ERROR: canonical spec {feature.spec_yml} does not exist. "
                 f"Run the kivax-compile skill.")
    spec = yaml.safe_load(feature.spec_yml.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        sys.exit(f"ERROR: {feature.spec_yml} is not a valid yml mapping.")
    return spec


def load_all_specs(root: Path, cfg: dict) -> list[tuple[Feature, dict | None]]:
    """Every feature paired with its compiled spec, or None when it has no
    spec.yml yet — the normal state during the `spec` phase, NOT a deletion."""
    out: list[tuple[Feature, dict | None]] = []
    for f in list_features(root, cfg):
        if not f.spec_yml.is_file():
            out.append((f, None))
            continue
        spec = yaml.safe_load(f.spec_yml.read_text(encoding="utf-8"))
        if not isinstance(spec, dict):
            sys.exit(f"ERROR: {f.spec_yml} is not a valid yml mapping.")
        out.append((f, spec))
    _guard_lock_against_uncompiled(root, cfg, out)
    return out


def _guard_lock_against_uncompiled(root: Path, cfg: dict,
                                   pairs: list[tuple[Feature, dict | None]]) -> None:
    """A feature that lost its spec.yml while the lock still holds its ids is a
    hard error. Without this, 'kivax hash --diff' would report every one of
    those requirements as `removed` and 'kivax trace --update-lock' would drop
    them from the lock — silent loss of the traceability baseline."""
    uncompiled = {f.number for f, spec in pairs if spec is None}
    if not uncompiled:
        return
    lock = load_lock(root, cfg)
    stranded: list[str] = []
    for kind in ("requirements", "integration_scenarios"):
        for rid in (lock.get(kind) or {}):
            ff = feature_number_of_id(rid)
            if ff and ff in uncompiled:
                stranded.append(rid)
    if stranded:
        nums = ", ".join(sorted(uncompiled))
        sys.exit(f"ERROR: feature(s) {nums} have no spec.yml, but the traceability "
                 f"lock still holds their ids: {', '.join(sorted(stranded))}.\n"
                 f"Recompile them (the kivax-compile skill) rather than leaving the "
                 f"lock pointing at requirements no spec declares.")


def all_spec_hashes(root: Path, cfg: dict) -> dict:
    """Union of every feature's hashes: {'requirements': {id: hash}, ...}.

    Ids are globally unique by construction; a collision means two features
    declare the same id (a copy-pasted directory, or a hand-edited number), and
    nothing else in the system would notice, so it fails hard here."""
    out: dict[str, dict[str, str]] = {"requirements": {}, "integration_scenarios": {}}
    seen: dict[str, Feature] = {}
    for feature, spec in load_all_specs(root, cfg):
        if spec is None:
            continue
        for kind, table in spec_hashes(spec).items():
            for rid, h in table.items():
                if rid in seen:
                    sys.exit(f"ERROR: duplicate id '{rid}' declared by both "
                             f"{seen[rid].name} and {feature.name}. Ids must be unique "
                             f"across the whole project — a test tagged '{rid}' would "
                             f"otherwise be ambiguous.")
                seen[rid] = feature
                out[kind][rid] = h
    return out


def owner_of(root: Path, cfg: dict) -> dict[str, Feature]:
    """id -> the Feature that declares it. For reporting which feature a stale
    hash or an uncovered requirement belongs to."""
    owners: dict[str, Feature] = {}
    for feature, spec in load_all_specs(root, cfg):
        if spec is None:
            continue
        for table in spec_hashes(spec).values():
            for rid in table:
                owners[rid] = feature
    return owners


def load_lock(root: Path, cfg: dict) -> dict:
    p = path_of(root, cfg, "lock")
    if not p.is_file():
        return {"requirements": {}, "integration_scenarios": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def save_lock(root: Path, cfg: dict, lock: dict) -> Path:
    p = path_of(root, cfg, "lock")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(lock, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                 encoding="utf-8")
    return p


def _canonical(obj) -> str:
    """Canonical serialization: JSON with sorted keys and normalized strings."""
    if isinstance(obj, dict):
        return json.dumps({k: _canonical(v) for k, v in sorted(obj.items())},
                          ensure_ascii=False, sort_keys=True)
    if isinstance(obj, list):
        return json.dumps([_canonical(x) for x in obj], ensure_ascii=False)
    if isinstance(obj, str):
        return " ".join(obj.split())  # normalizes whitespace/newlines
    return json.dumps(obj)


def req_hash(req: dict) -> str:
    """Stable hash of a requirement. Excludes non-semantic volatile fields."""
    core = {k: v for k, v in req.items() if k not in ("notes",)}
    return "sha256:" + hashlib.sha256(_canonical(core).encode("utf-8")).hexdigest()[:16]


def spec_hashes(spec: dict) -> dict:
    """Returns {'requirements': {id: hash}, 'integration_scenarios': {id: hash}}."""
    out = {"requirements": {}, "integration_scenarios": {}}
    for req in spec.get("requirements", []) or []:
        out["requirements"][req["id"]] = req_hash(req)
    for sc in spec.get("integration_scenarios", []) or []:
        out["integration_scenarios"][sc["id"]] = req_hash(sc)
    return out


DEFAULT_PIPELINE = ["constitution", "architecture", "spec", "compile", "plan", "tdd", "it",
                    "audit", "retro"]
MANDATORY_PREFIX = ["spec", "compile"]
OPTIONAL_PRE_PHASES = {"constitution", "architecture"}
TERMINAL_PHASE = "done"


def pipeline_of(cfg: dict) -> list[str]:
    """Returns the project's phase pipeline, validated.

    The pipeline is data in .kivax/config.yml (`pipeline:` key); users can
    append, remove, or reorder phases — including fully custom ones backed by
    their own kivax-<phase> skill (and, for runtimes that support one, an
    agent file too).

    Invariants enforced and NOT configurable:
      - Only 'constitution' and/or 'architecture' may precede ['spec',
        'compile'] — both are optional, self-skipping setup phases (their
        skill checks whether CONSTITUTION.md/ARCHITECTURE.md already exists
        and, if so, advances immediately without doing anything). Whatever
        comes after that optional leading run must start with
        ['spec', 'compile']: they're what makes the flow spec-anchored.
        Removing them isn't customizing the pipeline, it's removing the
        system's guarantees.
      - 'done' is the implicit terminal phase and can't appear in the list.
    """
    pl = cfg.get("pipeline") or list(DEFAULT_PIPELINE)
    if not isinstance(pl, list) or not all(isinstance(x, str) and x for x in pl):
        sys.exit("ERROR: 'pipeline' in .kivax/config.yml must be a list of phase names")
    i = 0
    while i < len(pl) and pl[i].strip() in OPTIONAL_PRE_PHASES:
        i += 1
    if [p.strip() for p in pl[i:i + 2]] != MANDATORY_PREFIX:
        sys.exit("ERROR: after any leading 'constitution'/'architecture' phases, the "
                 "pipeline must continue with ['spec', 'compile'] — these phases "
                 "are mandatory (they're what makes the flow spec-anchored). "
                 "Current pipeline: " + str(pl))
    if TERMINAL_PHASE in pl:
        sys.exit(f"ERROR: '{TERMINAL_PHASE}' is the implicit terminal phase; "
                 f"don't list it in 'pipeline'")
    if len(pl) != len(set(pl)):
        sys.exit("ERROR: duplicate phase names in 'pipeline': " + str(pl))
    return pl
