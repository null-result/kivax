# Specification: <feature name>

> One spec per feature. This file lives in its own directory
> (`<paths.features>/FF-<slug>/spec.md`) and `FF` is this feature's number —
> every id below carries it, which is what keeps ids unique across the project
> and lets one test tag resolve to exactly one requirement.

## Context and motivation
<Why this feature exists. Problem it solves. Affected users.>

## Assumptions
<Every assumption made while drafting, pending human validation.>

## Requirements

### REQ-FF-001 — <short behavior title>
**Priority:** must | should | could
**Depends on:** — <may reference a requirement of another feature, e.g. REQ-01-003>

<Description of the observable behavior. One requirement = one verifiable behavior.>

**Acceptance criteria:**
- **AC-FF-001-01** — Given <initial state>, when <action>, then <observable result>.
- **AC-FF-001-02** — Given ..., when ..., then ...

**Edge cases:**
- <edge case 1>

## Integration scenarios

### IT-FF-001 — <title> (covers: REQ-FF-001, REQ-FF-002)
Given <full system state>, when <end-to-end flow>, then <observable result>.

## Non-goals
- <What's explicitly out of scope.>
