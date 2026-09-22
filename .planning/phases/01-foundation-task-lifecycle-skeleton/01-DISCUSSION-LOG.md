# Phase 1: Foundation & Task Lifecycle Skeleton - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-22
**Phase:** 1-Foundation & Task Lifecycle Skeleton
**Areas discussed:** Task submission payload, Worker placeholder behavior, Status vocabulary, Scaffolding depth (LangGraph + Garage)

---

## Task submission payload

| Option | Description | Selected |
|--------|-------------|----------|
| problem_text only | Minimal now; language/examples added Phase 2 | |
| Full future shape now | problem_text + language + examples all present now, unused until later | ✓ |
| problem_text + examples | No language field, auto-detect later | |

**User's choice:** Full future shape now

| Option | Description | Selected |
|--------|-------------|----------|
| list of {input, output} pairs | Matches LeetCode-style test cases directly | ✓ |
| raw text block | Single free-text field, parsed later | |

**User's choice:** list of {input, output} pairs

| Option | Description | Selected |
|--------|-------------|----------|
| Basic only | Required non-empty + type checks, no limits | |
| Add limits now | Basic checks plus max length/count | ✓ |

**User's choice:** Add limits now

| Option | Description | Selected |
|--------|-------------|----------|
| Enum: "en" \| "ru" | Only two supported input languages, strict | ✓ |
| Optional, auto-detect if omitted | Field optional, Analyzer detects later | |

**User's choice:** Enum: "en" | "ru"

| Option | Description | Selected |
|--------|-------------|----------|
| 10,000 chars / 20 examples | Generous | |
| 5,000 chars / 10 examples | Tighter, still comfortable | ✓ |

**User's choice:** 5,000 chars / 10 examples

**Notes:** None additional.

---

## Worker placeholder behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Instant success | Immediate completed with stub result | |
| Fake delay then success | Sleeps a few seconds before completed | |
| Configurable success/fail | Also exercises the failure path | ✓ |

**User's choice:** Configurable success/fail

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit field in request | e.g. force_fail: bool | |
| Trigger by content | Magic string in problem_text | ✓ |

**User's choice:** Trigger by content

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, short sleep (2-5s) | Visibly sits in processing status | ✓ |
| No, resolve immediately | Faster, less realistic | |

**User's choice:** Yes, short sleep (2-5s)

| Option | Description | Selected |
|--------|-------------|----------|
| Simple error string | Fixed message | |
| Structured error object | {code, message} matching future pipeline errors | ✓ |

**User's choice:** Structured error object

**Notes:** None additional.

---

## Status vocabulary

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal skeleton set | queued/processing/completed/failed only, enum grows later | |
| Full future enum now | All pipeline statuses defined now, worker only uses a subset | ✓ |

**User's choice:** Full future enum now

| Option | Description | Selected |
|--------|-------------|----------|
| Generic "processing" | Placeholder status not in final enum | |
| First real stage: "analyzing_problem" | Worker jumps to real first-stage status | ✓ |

**User's choice:** First real stage: "analyzing_problem"

| Option | Description | Selected |
|--------|-------------|----------|
| Postgres native ENUM type | DB-enforced, migration needed to add values | |
| String/varchar + app-level enum | App-validated, no DB migration to add values | ✓ |

**User's choice:** String/varchar + app-level enum

**Notes:** None additional.

---

## Scaffolding depth (LangGraph + Garage)

| Option | Description | Selected |
|--------|-------------|----------|
| Container only, unused | Garage runs in compose, no client wiring | ✓ |
| Real client + bucket smoke test now | Garage client + test read/write at startup | |

**User's choice:** Container only, unused (Garage)

| Option | Description | Selected |
|--------|-------------|----------|
| Trivial stub graph now | Minimal LangGraph graph, checkpointed, early 3.14 compat smoke test | ✓ |
| Skip LangGraph, plain function | No graph until Phase 2 | |

**User's choice:** Trivial stub graph now (LangGraph)

| Option | Description | Selected |
|--------|-------------|----------|
| Pin interpreter to 3.13, continue | Matches documented STATE.md fallback | ✓ |
| Stop and escalate to user | Halt and ask before changing Python version | |

**User's choice:** Pin interpreter to 3.13, continue

**Notes:** Garage and LangGraph were deliberately treated asymmetrically — LangGraph carries a pre-flagged compatibility risk (STATE.md), Garage does not, so only LangGraph gets an early smoke test.

---

## Claude's Discretion

- Taskiq broker choice (`RedisStreamBroker` vs alternatives) — deferred to `.planning/research/STACK.md` recommendation
- Internal module layout within the single `uv` package
- Docker Compose healthchecks/ports/env wiring details

## Deferred Ideas

None — discussion stayed within phase scope.
