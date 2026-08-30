"""Kivax — a runtime for spec-anchored Spec-Driven Development.

The package ships its own global store as package data under `data/`: the
agents, skills, templates, and stack catalog that `kivax init`/`kivax upgrade`
materialize into a project. That's why `pip install --upgrade kivax` is the
whole upgrade path — the CLI and the store it reads are the same artifact and
cannot drift apart.
"""
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"


def _read_version() -> str:
    v = DATA_DIR / "VERSION"
    return v.read_text(encoding="utf-8").strip() if v.is_file() else "unknown"


__version__ = _read_version()
__all__ = ["DATA_DIR", "__version__"]
