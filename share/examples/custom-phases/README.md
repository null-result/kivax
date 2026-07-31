# Example: extending the pipeline with custom phases

This example adds two user-defined phases after `audit`: `deploy` (ships the
build to an environment) and `regression` (runs regression tests against it).
Kivax doesn't model environments or deployments itself — your skill defines
what these phases mean; Kivax just runs them in order, with their gates,
like any built-in phase.

## Steps

1. Copy the extension files directly into your project's skills directory
   for whichever runtime(s) you use (plain files — copy them like you'd copy
   any template):
   ```
   cp -r ~/.kivax/examples/custom-phases/kivax-skills/*   your-project/.claude/skills/
   # if you also use opencode:
   cp -r ~/.kivax/examples/custom-phases/kivax-skills/*   your-project/.opencode/skills/
   # cursor / codex / GitHub Copilot follow the same pattern, into
   # .cursor/skills/, .codex/skills/, or .github/skills/ respectively.
   ```
2. Edit `.kivax/config.yml`:
   ```yaml
   pipeline: [spec, compile, plan, tdd, it, audit, deploy, regression, retro]
   gates:
     # ...existing gates...
     deploy: human        # recommended: shipping is destructive
     regression: auto
   ```
   `retro` stays last on purpose: it records what the whole iteration cost, and
   a deploy or a regression run is exactly where some of the most expensive
   lessons come from.
3. That's it — after `audit` passes, the orchestrator will continue into the
   `kivax-deploy` and `kivax-regression` skills per their gates, then into
   `kivax-retro`. Adapt the
   persona sections inside each SKILL.md to your real deploy/test commands
   (they ship with placeholders).

Custom phases are orthogonal to features: a phase runs against whichever
feature is active, and the same `kivax-deploy` skill serves every feature.

These files are now yours: edit them, commit them, and if you like the
result enough to want it as the default for future projects, `kivax promote
skill kivax-deploy` (and `kivax promote skill kivax-regression`) pushes them
to the global store.
