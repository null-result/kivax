---
id: LSN-XXXX
title: <title>
status: active                # active | retired
# Which phases must be shown this lesson before they start. Be narrow: a
# lesson surfaced in every phase is a lesson skimmed in every phase.
phases: [plan, tdd]
# Optional scope. Empty = project-wide (always applicable). With globs, the
# lesson only has to be answered for when the feature touches a matching path.
paths: []
tags: []
origin:
  feature: <feature>
  phase: tdd
  # What actually happened, in evidence a human can go look at: commit hashes,
  # a REQ that cycled red->green->red, an audit finding, a reviewer comment.
  evidence: []
# Every feature that hit this again. A lesson seen three times is not three
# lessons — reinforce the entry, never duplicate it.
seen_in: [<feature>]
updated_at: <date>
---

# <title>

## What happened
<2-4 sentences. The concrete failure, not a generality. Name the file, the
symptom, and how long it took to find — that's what makes it recognizable
next time.>

## Rule
<One imperative sentence somebody can follow before the mistake happens.
"Run migrations in a @BeforeAll, not a @BeforeEach" — not "be careful with
migrations".>

## How to catch it early
<The cheapest signal that this is happening again: a specific error message,
a test that goes red, a command to run.>

## Why it isn't a REQ
<Optional. If the lesson is really unspecified BEHAVIOR, it belongs in the
spec instead: say so here and open kivax-evolve. This section is the check
against using the lessons store as a place to stash requirements.>
