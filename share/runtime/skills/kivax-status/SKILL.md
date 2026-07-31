---
name: kivax-status
description: "Shows the Kivax flow's status and traceability. Use when the human asks for the project's status, progress, or says 'kivax-status'."
---

Kivax SDD flow status.

1. `kivax feature list` (every feature, its phase, and how many of its ids are stale vs the lock) and `kivax state show` (the active feature in detail)
2. `kivax task list` — the current phase's per-agent checklists. Open items mean a specialist stopped mid-work, which is a different situation from a phase not yet started, and the human can't tell them apart from the phase name alone.
3. `kivax trace --report-only` (never fails, only reports)
4. If the wiki exists: `kivax wiki lint` (informational, never blocks)
5. Summarize for the human: the active feature and its phase, its REQs by status (pending/red/green/invalidated), **any work left in flight and which agent owns it**, traceability coverage, wiki freshness (if it exists), and the next recommended skill to run.
6. **Call out any NON-active feature with stale hashes explicitly.** That means an older feature's spec has drifted from its tests, it blocks the audit, and it needs `kivax feature switch <NN>` followed by the `kivax-evolve` skill. It's the finding most easily lost in a status report, and the one the human most needs.
