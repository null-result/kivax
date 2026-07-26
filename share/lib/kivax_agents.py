"""Generates per-runtime agent files from the canonical sources in agents/*.md
at install time ('kivax init' / 'kivax upgrade'), per the recipe in
agent_runtimes.yml. Also used by 'kivax promote' to write local edits back
into the canonical source instead of a per-runtime file.

Only two things are genuinely runtime-specific and can't be plain
substitution — both driven by the canonical 'tools:' CSV:
  - opencode's tools are a deny-list (only 'write'/'edit'/'bash' are ever
    listed, and only when ABSENT from the canonical allow-list); everything
    else is opencode's own default.
  - cursor's 'readonly' is true iff neither 'write' nor 'edit' is allowed.
"""
import json
from pathlib import Path

import yaml

OPENCODE_CONTROLLABLE_TOOLS = ["write", "edit", "bash"]  # fixed emission order


def split_frontmatter(text: str) -> tuple[dict, str]:
    """('---\\nkey: val\\n---\\nbody') -> ({'key': 'val'}, '\\nbody')."""
    if not text.startswith("---"):
        return {}, text
    _, fm_text, body = text.split("---", 2)
    return (yaml.safe_load(fm_text) or {}), body


def parse_canonical(path: Path) -> tuple[str, dict, str]:
    """Returns (name, frontmatter, body) for a canonical agents/<name>.md file.
    'name' is the filename stem, not a frontmatter field."""
    fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
    return path.stem, fm, body


def load_runtime_configs(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _tools_list(fm: dict) -> list[str]:
    return [t.strip() for t in str(fm.get("tools", "")).split(",") if t.strip()]


def _yaml_scalar(key: str, value) -> str:
    if key == "description":
        return f"description: {json.dumps(value, ensure_ascii=False)}"
    return f"{key}: {value}"


def _computed(spec: str, name: str, fm: dict) -> str | None:
    """spec is 'readonly', 'opencode_tools', or 'model:<default>'. Returns the
    frontmatter line to emit, or None to omit the field entirely."""
    tools_lower = {t.lower() for t in _tools_list(fm)}

    if spec == "readonly":
        readonly = not ({"write", "edit"} & tools_lower)
        return _yaml_scalar("readonly", "true" if readonly else "false")

    if spec == "opencode_tools":
        missing = [t for t in OPENCODE_CONTROLLABLE_TOOLS if t not in tools_lower]
        if not missing:
            return None
        return "tools:\n" + "\n".join(f"  {t}: false" for t in missing)

    if spec.startswith("model:"):
        default = spec.split(":", 1)[1]
        return _yaml_scalar("model", fm.get("model", default))

    raise ValueError(f"Unknown computed field spec: {spec}")


def render(name: str, fm: dict, body: str, runtime_cfg: dict) -> str:
    """Renders one runtime's agent file content from a canonical (name, fm, body)."""
    lines = ["---"]
    for key, source in runtime_cfg["fields"]:
        if source == "field:name":
            lines.append(_yaml_scalar(key, name))
        elif source.startswith("field:"):
            lines.append(_yaml_scalar(key, fm[source.split(":", 1)[1]]))
        elif source.startswith("value:"):
            lines.append(_yaml_scalar(key, source.split(":", 1)[1]))
        elif source.startswith("computed:"):
            line = _computed(source.split(":", 1)[1], name, fm)
            if line is not None:
                lines.append(line)
        else:
            raise ValueError(f"Unknown field source: {source}")
    lines.append("---")
    return "\n".join(lines) + body


def generate_all(agents_src: Path, runtimes_cfg: dict, cache_root: Path) -> None:
    """Renders every canonical agent into cache_root/<runtime>/<filename>,
    for every runtime declared in agent_runtimes.yml. Idempotent and cheap
    enough to call before every command that needs the generated files —
    it's the single place that keeps them fresh.

    Each runtime's directory is pruned of files this run didn't write, so an
    agent renamed or deleted upstream can't survive as a stale rendered file
    that sync_pairs would then copy into every project."""
    canonicals = [parse_canonical(p) for p in sorted(agents_src.glob("*.md"))]
    for runtime, cfg in runtimes_cfg.items():
        out_dir = cache_root / runtime
        out_dir.mkdir(parents=True, exist_ok=True)
        written: set[str] = set()
        for name, fm, body in canonicals:
            content = render(name, fm, body, cfg)
            filename = cfg["filename"].format(name=name)
            (out_dir / filename).write_text(content, encoding="utf-8")
            written.add(filename)
        for stale in out_dir.iterdir():
            if stale.is_file() and stale.name not in written:
                stale.unlink()


def update_canonical(path: Path, *, description: str | None = None,
                     tools: str | None = None, model: str | None = None,
                     body: str | None = None) -> str:
    """Applies a partial update to a canonical agents/<name>.md file's text
    (only the fields passed) and returns the new file content. Used by
    'kivax promote' to push a local edit back into the single shared source."""
    fm, old_body = split_frontmatter(path.read_text(encoding="utf-8")) if path.is_file() else ({}, "\n")
    if description is not None:
        fm["description"] = description
    if tools is not None:
        fm["tools"] = tools
    if model is not None:
        fm["model"] = model
    lines = ["---"]
    for key in ("description", "tools", "model"):
        if key in fm:
            lines.append(_yaml_scalar(key, fm[key]))
    lines.append("---")
    return "\n".join(lines) + (body if body is not None else old_body)
