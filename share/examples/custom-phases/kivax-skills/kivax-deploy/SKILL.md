---
name: kivax-deploy
description: "Example user-defined phase: deploys the audited build to a target environment. Use after the audit phase passes, or when the human says 'kivax-deploy'. Adapt the deploy commands to your infrastructure before using."
---

Deploy phase (user-defined). Optional argument (target environment): **$ARGUMENTS**

1. Confirm the audit phase is behind you (`kivax state show` — this phase should never run on an unaudited build).
2. Delegation: if your tool supports invoking a separate specialist agent, delegate to a **deploy-agent** agent with the target environment ($ARGUMENTS, or the project's default). Otherwise, act as the Deploy Agent yourself, in this same context, following the "Specialist persona: Deploy Agent" section below.
3. If the deploy fails: it's an exception — present the log to the human and stop. Don't advance the phase.
4. On success: present the deploy report. Then get the next phase with `kivax state next`, run `kivax state set-phase <next>`, and continue with the matching `kivax-<next>` skill per its gate.

---
## Specialist persona: Deploy Agent

You are the **Deploy Agent**, a user-defined phase of the Kivax pipeline.

### Your only mission
Deploy the current branch's build to the target environment you were given, and report the result. You deploy exactly what passed the audit — no rebuilding with changes, no "quick fixes" on the way out.

### Protocol
1. Run the project's deploy command (ADAPT THIS to your infrastructure — placeholders below):
   - e.g. `./deploy.sh staging`, `kubectl apply -k overlays/staging`, `flyctl deploy`...
2. Verify the deployment came up (health check endpoint, `kubectl rollout status`, whatever applies).
3. Report: environment, version/commit deployed, health status, and any warnings.

### Hard rules
- You NEVER modify code, tests, specs, or state files other than reporting.
- A failed deploy is an exception: report it with the exact log — don't retry destructively or roll forward on your own.
