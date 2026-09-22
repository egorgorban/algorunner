# Phase 2: Verified Single-Solution Core Pipeline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-23
**Phase:** 2-Verified Single-Solution Core Pipeline
**Areas discussed:** Clarification flow, Correction loop scope, Reliability budgets, Test generation depth

---

## Clarification flow

| Question | Options | Selected |
|----------|---------|----------|
| Clarification question format? | Free-text single question / Structured missing-fields list / You decide | **Free-text single question** |
| How many clarification rounds allowed? | One round only / Multiple rounds, capped | **Multiple rounds, capped** |
| Cap on clarification rounds (N)? | 2 rounds / 3 rounds | **2 rounds** |
| Where does user see/answer the clarification question? | Field on GET /tasks/{id} / Separate dedicated endpoint | **Separate dedicated endpoint** |
| If still ambiguous after clarification round(s) exhausted? | Proceed with stated assumption / Fail as terminal FAILED | **Proceed with stated assumption** |

**Notes:** Round cap (2) intentionally set lower than the correction loop's max_iterations (3-5) — clarification should resolve fast or fall back, not become an open-ended interrogation loop. The exposure endpoint is separate from the already-fixed `POST .../clarification` answer endpoint (API-03).

---

## Correction loop scope

| Question | Options | Selected |
|----------|---------|----------|
| On failed review, what gets redone? | Solver only, regen code+tests too / Targeted: only regenerate what issue implies | **Targeted: only regenerate what issue implies** |
| How much prior-attempt context carries into a correction iteration? | Full history (all prior attempts + all issues) / Last failure only | **Full history** |
| Does severity affect correction routing? | No — any failed review triggers full correction / Yes — critical vs minor treated differently | **Yes — critical vs minor treated differently** |
| When only minor issues are found (no critical), what happens? | Treated as PASS, issues noted / Still routes to correction once | **Treated as PASS, issues noted** |

**Notes:** User chose the more involved, issue-targeted routing over "always redo everything" — favors efficiency/production-readiness over simplicity. This decision was flagged in CONTEXT.md with a "costly" reversibility rating since it bakes issue-type routing into the graph's conditional edges.

---

## Reliability budgets

| Question | Options | Selected |
|----------|---------|----------|
| Global timeout on total task solve time? | 10 minutes / 20 minutes / You decide | **10 minutes** |
| OpenAI rate-limit/timeout retry backoff shape? | Exponential backoff, capped retries / You decide | **Exponential backoff, capped retries** |

**Notes:** Matches interview.md's "pause-and-cooldown" answer with a concrete bound now attached.

---

## Test generation depth

| Question | Options | Selected |
|----------|---------|----------|
| How should Test Generator treat user-provided examples? | Always include as-is, plus generated extras / You decide | **Always include as-is, plus generated extras** |
| Minimum additional generated tests when few/no examples are provided? | 3-5 generated tests minimum / You decide | **10 minimum with edge-cases** (free-text override) |
| Should generated tests explicitly target edge cases, or just typical-case coverage? | Yes — explicit edge-case tests required / No — typical-case coverage is enough | **Yes — explicit edge-case tests required** |

**Notes:** User explicitly raised the offered minimum (3-5) to 10, unprompted — a deliberate correctness-over-speed override consistent with the project's stated Core Value.

---

## Claude's Discretion

- Exact `tenacity` retry count and backoff delay curve for OpenAI timeout/rate-limit handling.
- `Command` vs `add_conditional_edges` idiom for the correction-loop graph structure.
- Reconciling LangGraph's `recursion_limit` against the app-level `max_iterations`.
- OpenAI Python SDK v1 vs v2 pinning.
- Internal Pydantic schema shapes beyond what's specified in CONTEXT.md.
- Exact wording/prompt design for the Analyzer's clarification question.

## Deferred Ideas

None — discussion stayed within Phase 2 scope.
