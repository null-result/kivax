---
name: kivax-git
description: "Gitflow operations the SDD flow deliberately doesn't do on its own: merging a reviewed pull request, cutting a release, and running a hotfix. Use ONLY when the human explicitly asks for one of those — never as a continuation of a phase."
---

Gitflow operations outside the SDD flow. Requested operation: **$ARGUMENTS**

The SDD flow ends at a pull request marked ready for review. Everything past that point — merging it, cutting a release, patching production — is in here, and **only runs when the human asks for it by name**. Never invoke this skill because a phase finished, because the audit passed, or because it looks like the obvious next thing. A passing audit is what makes a PR reviewable; it is not a review, and it is not permission to merge.

## The rule that governs every operation below

**Summarize, then wait for an explicit yes.** Before any command that changes a shared branch, publishes a tag, or merges anything, tell the human exactly what is about to happen — source branch, target branch, how many commits, the tag name — and stop. A "yes" to one operation is not a yes to the next one: confirm each irreversible step on its own. If the human's request is ambiguous about which branch, which feature, or which version, ask rather than infer.

Read `git.base_branch` from `.kivax/config.yml` for the integration branch (gitflow's `develop`). The release branch is `main` unless the human says otherwise.

## Merging a reviewed feature

Preconditions you check and report before asking: the PR exists and is **not** draft, its checks are green, and it has an approving review. If any of those is false, say which and stop — the human may still choose to proceed, but they decide with the facts in front of them, not after the fact.

```bash
gh pr view --json number,isDraft,mergeStateStatus,reviewDecision
gh pr checks
```

Then, on confirmation:

```bash
gh pr merge <number> --squash --delete-branch   # or --merge / --rebase, as the human prefers
```

Ask which merge strategy if they haven't said. Don't default to squash on a repo whose history shows merge commits.

## Cutting a release (`develop` → `main`)

A release is a pull request too, not a direct push. Never push to `main` directly.

1. Confirm the version with the human — never derive it yourself from commit messages.
2. Open the release PR: `gh pr create --base main --head <base_branch> --title "release: v<X.Y.Z>"`, with a body summarizing the features included (`git log --oneline main..<base_branch>`).
3. Stop. The human reviews and merges it, or asks you to merge it — same confirmation as above.
4. After it merges, and only if asked: tag `main` (`git tag -a v<X.Y.Z> -m ...` and `git push origin v<X.Y.Z>`), then open the back-merge PR from `main` into the base branch so the tag and any release fixes return to integration.

## Hotfix (patching production)

A hotfix branches from `main`, not from the integration branch, and lands in both.

1. `git checkout -b hotfix/<slug> origin/main`
2. **The fix still needs a spec.** A hotfix is not an exemption from spec-first: if it changes behavior, it goes through the normal flow on that branch (`kivax feature new`, then the phases) — the only difference is where the branch is cut from and that it merges to `main` too. If it's a genuine non-behavioral fix (a bad config value, a broken build), say so explicitly and let the human agree before skipping the spec.
3. PR into `main`. On confirmation, merge, then tag.
4. **Open the second PR, from `main` back into the base branch.** A hotfix that never returns to integration is a fix that gets reverted by the next release — say this out loud if the human wants to stop after step 3.

## Hard rules

- **Never run any of this unprompted**, and never as a continuation of a phase.
- **Never force-push**, never rewrite published history, never delete a branch that isn't the merged feature's own.
- **Never push directly to `main` or to the integration branch.** Everything goes through a pull request, including releases and hotfixes.
- **Never invent a version number**, a tag, or a release scope — those are the human's.
- If a merge conflicts, stop and hand it back with the conflicting files named. Resolving a conflict on a shared branch is not something to improvise.
- If the human asks you to deploy, say that Kivax doesn't deploy: that's their pipeline, triggered by the tag or the merge they just made.
