# Phase 3: Multi-Approach Editorial & Persistence - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-24
**Phase:** 03-multi-approach-editorial-persistence
**Areas discussed:** Approach count & partial failure, Time & iteration budget, Editorial output format, Garage persistence policy

---

## Approach count & partial failure

| Question | Options | Selected |
|----------|---------|----------|
| Max approaches | Cap at 3 / Cap at 2 / No hard cap | Cap at 3 |
| Is 1 approach valid | Yes, 1 is valid / Require ≥2 | Yes, 1 is valid |
| One approach fails, others pass | Drop it, ship the rest / Drop it, mention in article / Fail whole task | Drop it, mention in article |
| Which must pass for COMPLETED | Any one / The optimized one | Any one |
| Curation mechanism | One call: propose + select / Propose many, then separate curate call | One call: propose + select |
| Who orders approaches | Strategist via role label / Editorial Writer | Editorial Writer |

**Notes:** User chose to mention unverified approaches in the article (no code) instead of silently dropping them. User chose Writer-decided ordering over the recommended deterministic role sort.

---

## Time & iteration budget

| Question | Options | Selected |
|----------|---------|----------|
| Global timeout | Raise to 20 min / Keep 10 min / Scale per approach | Raise to 20 min |
| Sequential vs parallel | Parallel fan-out / Sequential / You decide | Parallel fan-out |
| max_iterations scope | Per approach / Shared pool | Per approach |
| Timeout with partial success | Ship verified ones / Task FAILED | Ship verified ones |

---

## Editorial output format

| Question | Options | Selected |
|----------|---------|----------|
| Editorial shape | Structured JSON + rendered Markdown / Structured JSON only / Markdown only | Structured JSON only |
| Code source | Verified code injected verbatim / Writer may reformat code | Verified code injected verbatim |
| Minor issues in article | No, artifacts only / Yes, as short notes per approach | Yes, as short notes per approach |
| Postgres result content | Editorial JSON + Garage keys / Everything, as today / Keys only | Editorial JSON + Garage keys |
| Writer call structure | One call, whole article / Per approach + stitch call | One call, whole article |
| Russian check | Prompt + cheap Cyrillic check / Prompt only | Prompt + cheap Cyrillic check |

**Notes:** User rejected the recommended Markdown render (JSON only). User chose to show minor issues in the article, against the recommended artifacts-only option.

---

## Garage persistence policy

| Question | Options | Selected |
|----------|---------|----------|
| Write timing | Incrementally per node / Once at the end | Incrementally per node |
| On write failure | Retry, then FAIL task / Log warning, continue | Log warning, continue |
| Key layout | Per task/approach/iteration / Per task latest-only / You decide | Per task/approach/iteration |
| Retention | Keep forever for v1 / Delete on task deletion | Keep forever for v1 |
| Result key honesty | Only written keys + flag / List all expected keys | Only written keys + flag |

**Notes:** User chose best-effort storage over the recommended fail-on-storage-error option.

---

## Claude's Discretion

- `Send` fan-out mechanics: state reducers, recursion_limit, interrupt interaction
- Branch cancellation at timeout and Writer time reserve
- Parallel concurrency limits (OpenAI, executors)
- S3 client choice, Garage provisioning, write retry count
- `Editorial` field names, Cyrillic threshold, `editorial_writer_model` config
- Status transitions under parallel branches

## Deferred Ideas

- Garage retention/lifecycle policy and task-delete endpoint
- Markdown export of editorial
