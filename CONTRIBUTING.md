# Contributing to Kivax

Thanks for being here. This document covers how to run the project locally, how
it's laid out, and the few conventions that aren't obvious from reading the code.

## Getting set up

There is nothing to build and one dependency:

```bash
git clone https://github.com/null-result/kivax.git
cd kivax
python3 -m pip install pyyaml ruff pytest pytest-cov
```

Kivax is **not** a pip package. It's installed by cloning the repo and running
`install.py`, which copies `share/` into a global store (`~/.kivax`) and links
the CLI onto your PATH. The CLI runs directly from the checkout, so there's no
packaging step to worry about.

To try your changes end to end, install into a throwaway store instead of your
real one:

```bash
KIVAX_HOME=/tmp/kivax-dev python3 install.py
export KIVAX_HOME=/tmp/kivax-dev
cd /some/scratch/project && kivax init
```

## Running the checks

```bash
pytest tests                                                          # everything
pytest tests/unit                                                     # fast, no subprocess
pytest tests/integration                                              # one CLI subcommand at a time
pytest tests/e2e                                                      # full flows, some real subprocess
pytest tests --cov=. --cov-config=.coveragerc --cov-report=term-missing  # the coverage gate (>= 90%, see .coveragerc)
ruff check . bin/kivax                                                 # style and real-defect lint
```

The suite is organized by how much of the system a test touches:

- **`tests/unit/`** — one function at a time. Library modules (`share/lib/*.py`)
  are called directly with an in-memory `cfg` dict and a `tmp_path`; `bin/kivax`'s
  standalone helpers (`ask`, `find_source_files`, `_check_tag_regexes`, …) the
  same way.
- **`tests/integration/`** — one `kivax` subcommand at a time (`init`, `feature`,
  `doctor`, `upgrade`, `promote`, dispatch), against a project scaffolded by the
  `project`/`use_store` fixtures.
- **`tests/e2e/`** — full multi-feature flows (the kind of session an agent
  actually runs), plus a handful of true subprocess invocations of the real
  `bin/kivax` script as a sanity check independent of the in-process tests.

Everything in `tests/unit` and `tests/integration`, and most of `tests/e2e`,
calls `kivax_cli.main()` **in-process** — `sys.argv` and `builtins.input` are
monkeypatched, `SystemExit` is caught — rather than spawning a real
subprocess. `tests/conftest.py`'s module docstring explains why (speed,
identical behavior across Windows/macOS/Linux, and it's what lets
coverage.py see the lines execute at all). The one thing this requires
discipline about: `kivax validate|hash|trace|state|wiki|specfirst` dispatch
through `cmd_passthrough`, which calls `os.execv()` — fine in a real install
(separate processes), but calling it in-process would replace the *test
runner itself*. Never call `kivax_cli.main(..., "state", ...)` (etc.)
directly in a test; call the target module's own `main()` instead (there's a
fixture per module — `kstate`, `kvalidate`, `khash`, …), or use the
`set_phase` fixture for the common "advance the active feature's phase" case.

It builds a disposable global store and disposable git projects under
`tmp_path`, and never touches your real machine: `install.py` itself — which
symlinks into `~/.local/bin` — is exercised only by the separate `install`
job in CI, on a disposable runner, never by the test suite.

`bin/kivax` is passed to ruff explicitly because it has no `.py` extension — it's
meant to be executed directly.

## How the repository is laid out

```
install.py       system-wide installer (copies share/ into ~/.kivax)
bin/kivax        the CLI
share/           everything that gets copied into the global store:
  agents/          one canonical file per specialist, rendered per runtime
  runtime/skills/  the phase-driver and reference skills (SKILL.md)
  lib/             the kivax_*.py scripts the CLI dispatches to
  templates/       scaffolds copied into each project
  examples/        ready-to-copy pipeline extensions
  ci/              a SAMPLE CI gate for projects that USE Kivax
tests/
  conftest.py      shared fixtures — read its module docstring first
  unit/            one function at a time
  integration/     one CLI subcommand at a time
  e2e/             full flows, plus a few real-subprocess sanity checks
pytest.ini         test discovery + markers
.coveragerc        coverage scope and the 90% gate (`fail_under`)
```

> `share/ci/github-actions-kivax.yml` is **not** this repository's CI. It's a
> template that gets installed into your users' projects. This repo's own CI is
> `.github/workflows/ci.yml`.

## The three conventions that matter

**1. Agents and skills are documentation the assistant executes.** When you
change the CLI or the flow, the corresponding files under `share/agents/` and
`share/runtime/skills/` have to change with it. They tell the assistant which
commands exist and what the ids look like, and drift there is invisible until
someone hits it mid-session. The PR checklist has a line for this.

Note the deliberate duplication: each specialist exists both as an agent file
(for tools with real subagent support) and inlined as a "Specialist persona"
section inside the phase skill (for tools without one). Both copies must be
updated. If you change one and not the other, users on half the supported tools
get the old behavior.

**2. A test that can't fail isn't protecting anything.** When you fix a bug, add
a test for it, then *revert your fix and watch it go red*. Several invariants in
this codebase — the traceability lock keeping every feature's entries, above
all — fail silently rather than crashing, which is exactly why they need a test
that has been seen to fail, not just seen to pass.

**3. Coverage is a floor, not a target.** CI's `coverage` job fails the build
under 90% (`.coveragerc`'s `fail_under`), but a change that pads the number
without testing anything real (asserting on a mock instead of behavior, testing
a getter) isn't welcome. If a branch is genuinely impractical to exercise
honestly, say why in a comment next to a `# pragma: no cover`, don't just write
a hollow test to clear the gate.

## Style

Ruff enforces it, configured permissively in `ruff.toml`: real defects, unused
imports, and import order, not aesthetics. Run `ruff check . bin/kivax --fix`
before pushing and you'll rarely think about it again.

Beyond that, the codebase leans on comments that explain *why* rather than what,
especially where a choice looks arbitrary — why the lock stays a flat map, why
`sync-reqs` is the one command that must not span every feature. Keep that habit;
it's most of what makes this code approachable.

## Opening a pull request

Small and focused beats large and complete. If you're planning something
substantial — a change to the traceability model, a new phase, a change to the id
format — open an issue first so we can agree on the approach before you spend the
time.

## Code of conduct

By participating you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).
