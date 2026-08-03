# Contributing to Kivax

Thanks for being here. This document covers how to run the project locally, how
it's laid out, and the few conventions that aren't obvious from reading the code.

## Getting set up

One runtime dependency, and nothing to build:

```bash
git clone https://github.com/null-result/kivax.git
cd kivax
python3 -m pip install -e ".[dev]"
```

Kivax is a pip package with a `src/` layout. The editable install puts a
`kivax` command on your PATH that runs the checkout directly, so your edits
take effect immediately with no build step.

The global store — the agents, skills, and templates that `kivax init` copies
into a project — ships as package data at `src/kivax/data/`, so an editable
install also picks up store edits immediately. That's the point of shipping it
inside the package: the CLI and the store are one artifact and cannot drift.

To try your changes end to end, work in a scratch repository:

```bash
mkdir /tmp/scratch && cd /tmp/scratch && git init
kivax init
```

The test suite needs no install at all — `pytest.ini` puts `src/` on the path,
so `pytest tests` works from a bare clone with just `pyyaml` and `pytest`.

`KIVAX_HOME` still overrides the store's location. You rarely need it now that
an editable install reads `src/kivax/data/` directly; it's there for anyone
running a vendored or forked store.

## Running the checks

```bash
pytest tests                                                          # everything
pytest tests/unit                                                     # fast, no subprocess
pytest tests/integration                                              # one CLI subcommand at a time
pytest tests/e2e                                                      # full flows, some real subprocess
pytest tests --cov --cov-config=.coveragerc --cov-report=term-missing  # the coverage gate (>= 90%, see .coveragerc)
ruff check .                                                           # style and real-defect lint
```

The suite is organized by how much of the system a test touches:

- **`tests/unit/`** — one function at a time. Library modules (`src/kivax/lib/*.py`)
  are called directly with an in-memory `cfg` dict and a `tmp_path`; `cli.py`'s
  standalone helpers (`ask`, `find_source_files`, `_check_tag_regexes`, …) the
  same way.
- **`tests/integration/`** — one `kivax` subcommand at a time (`init`, `feature`,
  `doctor`, `upgrade`, dispatch), against a project scaffolded by the
  `project`/`use_store` fixtures.
- **`tests/e2e/`** — full multi-feature flows (the kind of session an agent
  actually runs), plus a handful of true subprocess invocations of the real
  `python -m kivax` entry point as a sanity check independent of the in-process tests.

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
`tmp_path`, and never touches your real machine.

One thing the suite cannot check, by construction: that the **wheel** is
correct. Every test runs against `src/` on `sys.path`, where a wrong
`package-data` glob in `pyproject.toml` is invisible — the checkout works
perfectly while every `pip install` produces a CLI with no store. That's the
`package` job in CI: it builds the wheel, asserts its store file count matches
the tree, installs it into a clean virtualenv, and drives a real `kivax init`
from a temp directory. If you move anything under `src/kivax/data/`, that job
is the one to watch.

## How the repository is laid out

```
pyproject.toml     packaging: console script, dependencies, package data
src/kivax/
  cli.py           the CLI
  lib/             the kivax_*.py modules the CLI dispatches to
  data/            THE GLOBAL STORE — package data, shipped in the wheel:
    agents/          one canonical file per specialist, rendered per runtime
    runtime/skills/  the phase-driver and reference skills (SKILL.md)
    templates/       scaffolds copied into each project
    ci/              a SAMPLE CI gate for projects that USE Kivax
    stack_profiles.yml, agent_runtimes.yml, VERSION
tests/
  conftest.py      shared fixtures — read its module docstring first
  unit/            one function at a time
  integration/     one CLI subcommand at a time
  e2e/             full flows, plus a few real-subprocess sanity checks
pytest.ini         test discovery + markers + `pythonpath = src`
.coveragerc        coverage scope and the 90% gate (`fail_under`)
```

> `src/kivax/data/ci/github-actions-kivax.yml` is **not** this repository's CI.
> It's a template that gets installed into your users' projects. This repo's own
> CI is `.github/workflows/ci.yml`.

**Releasing.** Bump `src/kivax/data/VERSION` — it is the single source of truth
for both the distribution version and what `kivax version` reports. Then publish
a GitHub Release tagged `v<that version>`; `.github/workflows/release.yml` checks
the tag against the file, builds, and publishes to PyPI via Trusted Publishing
(no API token anywhere).

## The three conventions that matter

**1. Agents and skills are documentation the assistant executes.** When you
change the CLI or the flow, the corresponding files under `src/kivax/data/agents/`
and `src/kivax/data/runtime/skills/` have to change with it. They tell the assistant which
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
imports, and import order, not aesthetics. Run `ruff check . --fix`
before pushing and you'll rarely think about it again.

Beyond that, the codebase leans on comments that explain *why* rather than what,
especially where a choice looks arbitrary — why the lock stays a flat map, why
`sync-reqs` is the one command that must not span every feature. Keep that habit;
it's most of what makes this code approachable.

## Branching model and commit messages

`main` and `develop` are both protected by a GitHub ruleset: no direct pushes,
no force-pushes, no deletion — everything lands through a pull request.

- **`develop`** is the integration branch. Branch off it for day-to-day work:
  - `feature/<slug>` — new functionality, branches from and merges back into `develop`.
  - `release/<version>` — stabilizes `develop` before a release; merges into
    both `main` and `develop`.
  - `hotfix/<slug>` — urgent fix branched from `main`; merges into both `main`
    and `develop`.
- **`main`** only receives merges from `release/*` or `hotfix/*` branches and
  always reflects what's released. It also requires the `required checks` CI
  job (which aggregates test, coverage, lint, install, and commitlint) to pass
  before merging.

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
`<type>(<scope>): <description>`, e.g. `fix(trace): guard lock against dropped entries`
or `feat(cli): add kivax feature switch`. Common types: `feat`, `fix`, `docs`,
`refactor`, `test`, `chore`. `commitlint.config.js` (extending
`@commitlint/config-conventional`) is what the `commitlint` CI job checks PR
commits against — a non-conforming commit message fails the check.

## Opening a pull request

Small and focused beats large and complete. If you're planning something
substantial — a change to the traceability model, a new phase, a change to the id
format — open an issue first so we can agree on the approach before you spend the
time.

## Code of conduct

By participating you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).
