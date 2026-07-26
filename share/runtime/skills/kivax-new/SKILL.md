---
name: kivax-new
description: "Starts a new feature within the Kivax spec-anchored flow. Use when the human asks to start/begin a new feature, says 'kivax-new <feature>', or wants to kick off work that should go through spec → plan → tdd → audit."
---

Starts a new feature within the Kivax flow. Feature request: **$ARGUMENTS**

Kivax keeps **one spec per feature**: each feature gets its own directory under `paths.features` (`specs/01-booking/`, `specs/02-cancel/`...) holding its own `spec.md`, `spec.yml`, and `plan.md`. The directory's number becomes the prefix of every id in that spec (`REQ-01-001`), which is what keeps ids unique project-wide.

Precondition: the project is already installed (`.kivax/config.yml` exists; if not, the project hasn't been initialized — tell the human to run `kivax init` in a terminal, at the repo root, BEFORE continuing. That step is the human's responsibility, not yours: it requires a real terminal, don't simulate it).

Steps (you run these directly, no delegation needed):
1. Infer a short kebab-case slug from the request (`cancel-booking`, `bulk-export`). If it isn't clear, ask the human for one — don't invent something vague.
2. Run `kivax feature new <slug>`. That single command allocates the next feature number, creates the directory, seeds `spec.md` from the template with the number already substituted, and makes it the active feature. Don't create directories or copy templates yourself.
3. If the command refuses because a feature is still in flight, relay its message: Kivax drives one feature at a time per branch. Ask the human whether to finish that one first, or to archive it as-is (`kivax feature new <slug> --force`). Don't pass `--force` on your own initiative.
4. Run `kivax feature show` and `kivax state show` to confirm, and tell the human the assigned feature number and the ids their requirements will carry (`REQ-<NN>-001`, ...).
5. Tell the human the next step: run the `kivax-spec` skill with the detailed feature request.

To work on a feature that already exists instead of starting a new one, `kivax feature switch <NN>` — see the `kivax-evolve` skill, which is the usual reason to go back to one.
