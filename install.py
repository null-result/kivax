#!/usr/bin/env python3
"""Kivax system-wide installer.

Usage:
  python3 install.py                  # installs into ~/.kivax
  KIVAX_HOME=/other/path python3 install.py

Does not depend on bash: it works the same on Linux, macOS, and Windows
(cmd.exe or PowerShell) with just python3 installed, which is already a
requirement of the rest of the system (the 'kivax' CLI itself is a Python
script).
"""
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIVAX_HOME = Path(os.environ.get("KIVAX_HOME", str(Path.home() / ".kivax")))


def ensure_pyyaml() -> None:
    try:
        import yaml  # noqa: F401
        return
    except ImportError:
        pass
    print("Installing PyYAML...")
    for cmd in (
        [sys.executable, "-m", "pip", "install", "--break-system-packages", "pyyaml"],
        [sys.executable, "-m", "pip", "install", "--user", "pyyaml"],
    ):
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    print("WARNING: could not install PyYAML automatically. Install it by hand:\n"
          "  pip install pyyaml")


SKIP_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def copy_tree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in SKIP_DIRS or item.suffix in SKIP_SUFFIXES:
            continue
        target = dst / item.name
        if item.is_dir():
            copy_tree(item, target)
        else:
            shutil.copy2(item, target)


def make_executable(p: Path) -> None:
    if os.name != "nt":
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def link_cli_posix(cli: Path) -> str | None:
    """Tries to link the CLI into a directory already on PATH (POSIX)."""
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    for cand in (Path.home() / ".local" / "bin", Path("/usr/local/bin")):
        if str(cand) in path_dirs and cand.is_dir():
            link = cand / "kivax"
            try:
                if link.is_symlink() or link.exists():
                    link.unlink()
                link.symlink_to(cli)
                return str(cand)
            except OSError:
                continue
    return None


def main() -> int:
    print(f"== Installing Kivax into {KIVAX_HOME} ==\n")
    ensure_pyyaml()

    copy_tree(HERE / "share", KIVAX_HOME)

    # The rendered-agent cache is derived, never hand-edited: wipe it so an
    # agent that was renamed or removed upstream doesn't linger as a stale
    # rendered file that 'kivax init'/'kivax upgrade' would copy into projects.
    # Everything else under KIVAX_HOME is left alone — agents/ and
    # runtime/skills/ can hold items put there by 'kivax promote'.
    shutil.rmtree(KIVAX_HOME / "_generated", ignore_errors=True)

    bin_dir = KIVAX_HOME / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    cli = bin_dir / "kivax"
    shutil.copy2(HERE / "bin" / "kivax", cli)
    make_executable(cli)
    bat = HERE / "bin" / "kivax.bat"
    if bat.is_file():
        shutil.copy2(bat, bin_dir / "kivax.bat")

    version_file = KIVAX_HOME / "VERSION"
    version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "unknown"
    print(f"Kivax {version} installed at {KIVAX_HOME}")

    if os.name == "nt":
        print("\nWindows detected: add this folder to your PATH (once):\n"
              f"  {bin_dir}\n"
              "For example, from PowerShell (as administrator):\n"
              f"  [Environment]::SetEnvironmentVariable('Path', $env:Path + ';{bin_dir}', 'User')\n"
              "Then open a new terminal and try: kivax version\n")
    else:
        linked = link_cli_posix(cli)
        if linked:
            print(f"CLI linked at {linked}/kivax")
        else:
            print("I couldn't find a directory on your PATH to link the CLI into.\n"
                 "Add this to your shell rc (~/.bashrc, ~/.zshrc...):\n\n"
                 f"  export PATH=\"{bin_dir}:$PATH\"\n")

    print("Next step: go to the root of your project and run 'kivax init'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
