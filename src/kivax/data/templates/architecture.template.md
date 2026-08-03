# Project Architecture

> Reflects the CURRENT state of the system, not a snapshot of intent. Updated incrementally — via the plan phase of each feature — as the project evolves; never a full rewrite, only the sections a given feature actually affects.

## Overview
<One paragraph: what this system is, its primary architectural style (e.g. hexagonal, layered, event-driven), and the single most important thing a newcomer should understand about its shape.>

## Tech stack
<Languages, frameworks, key infrastructure — derived from `stack.profiles` in `.kivax/config.yml`, plus anything not captured there (databases, message brokers, deployment target).>

## Module map
<Top-level modules/packages and their responsibilities. One line each; link to a deeper doc if one exists instead of duplicating it here.>

## Key design decisions
<Decisions with lasting structural impact and why — the ones a newcomer would otherwise have to reconstruct by reading history or asking around.>

## Boundaries and conventions
<What must never cross a boundary (e.g. "domain layer never imports infrastructure"), naming/layering conventions, anything the tech-planner should treat as a hard constraint when planning a new feature.>

## Data flow
<How a request or event moves through the system, if that's non-obvious from the module map alone. Skip if not relevant.>

---
Last updated: <date> (<REQ-FF-NNN or "initial authoring">)
