## What this changes

<!-- One or two sentences. Link the issue if there is one. -->

## Why

<!-- The problem being solved. For a behavior change, say what was wrong before. -->

## Checklist

- [ ] `pytest tests` passes
- [ ] `pytest tests --cov=. --cov-config=.coveragerc --cov-report=term-missing` stays at
      or above the 90% gate (`.coveragerc`'s `fail_under`)
- [ ] `ruff check . bin/kivax` passes
- [ ] If behavior changed, a test under `tests/unit`, `tests/integration`, or `tests/e2e`
      covers it — and **fails without the fix** (revert your change and watch it go red;
      a test that can't fail isn't protecting anything, and coverage that isn't testing
      real behavior isn't welcome just to clear the gate)
- [ ] If the CLI or the flow changed, the affected agents and skills under
      `share/` were updated too — they describe the CLI to the assistant, and
      drift there is invisible until someone hits it in a real session
- [ ] README updated if the user-facing behavior changed
