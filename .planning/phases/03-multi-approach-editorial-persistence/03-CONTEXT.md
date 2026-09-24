# Phase 3: Multi-Approach Editorial & Persistence - Context

**Gathered:** 2026-09-24
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase widens Phase 2's single verified solution into up to 3 curated, independently verified approaches. It composes them into one Russian-language editorial (structured JSON). It persists every intermediate artifact to Garage. The whole flow stays one deterministic LangGraph `StateGraph` (ORCH-01).

Requirements: STRAT-02, EDIT-01..EDIT-06, ORCH-01, DATA-02.

Not in this phase: WebSocket streaming, React UI, docs set (Phase 4). No task-delete endpoint. No Garage lifecycle/retention policy.

</domain>

<decisions>
## Implementation Decisions

### Carried forward from Phase 2 (not re-discussed)
- Hybrid fixed graph (D-00a), Strategist + generic Solver (D-00b), and executors as tools (D-00c) all still hold.
- Targeted issue-routed correction (D-05) now applies **per approach**. Full history per iteration (D-06) also applies per approach.
- Critical vs minor severity (D-07): minor issues never block. They now surface in the article (see D-14).
- Stated assumption after clarification cap (D-04) must appear in the problem restatement (EDIT-06). A resolved clarification answer must appear there too.

### Approach Count & Curation
- **D-01:** Max **3** approaches per task. The cap is configurable (`max_approaches` in `Settings`, default 3).
- **D-02:** **1 approach is valid.** When the Strategist judges no meaningful brute-force/alternative exists, it returns one approach. It must never invent a padding approach.
- **D-03:** Curation (STRAT-02) happens in the **same single Strategist call**: propose and select. Extend `ApproachList`/`Approach` so each approach carries a role label (e.g. `brute_force` / `optimized` / `alternative`) and a short "why included" rationale. The Strategist enforces the cap. The node must also guard it deterministically (truncate or reject if more than `max_approaches`).
- **D-04:** The **Editorial Writer decides the presentation order** in the article, not the Strategist. The Writer should follow the natural simple-to-better progression (EDIT-03). It writes the narrative bridge between consecutive approaches. The role label is input to the Writer, not a hard sort key.

### Partial Failure
- **D-05:** An approach that exhausts its `max_iterations` without passing is **dropped from the verified set**. It is **mentioned briefly in the article** as attempted but not verified, and **no code is shown**. Its full attempt trail stays in Garage.
- **D-06:** The task is **COMPLETED if at least one approach passes**, whichever role it has. The task is FAILED only when zero approaches pass. The existing `CORRECTION_LOOP_EXHAUSTED` error shape still applies.

### Time & Iteration Budget
- **D-07:** Raise global solve timeout from 10 min to **20 min** (`global_timeout_s` default 1200).
- **D-08:** Approaches run as a **parallel fan-out**. Use LangGraph `Send`, one branch per approach. Each branch runs its own Solver → Code Generator → Test Generator → Execute Python → Execute Go → Reviewer → correction loop. All branches join before the Editorial Writer. — **Reversibility:** costly — this restructures the graph from the Phase 2 linear shape into per-branch state. Going back to sequential means reworking the state schema and edges.
- **D-09:** `max_iterations` applies **per approach**. Each branch has its own correction budget. The global timeout still caps the total.
- **D-10:** When the global timeout hits while some approaches have passed, **ship the verified ones**. Cancel in-flight branches and treat them as "not verified" (same treatment as D-05). Still run the Editorial Writer. Reserve a time slice for the Writer inside the 20-min budget. The researcher/planner picks the concrete reserve. When zero approaches have passed at timeout, the task FAILS as today (INFRA-04).

### Editorial Output Format
- **D-11:** The Editorial Writer produces **structured JSON only**: a Pydantic `Editorial` model, with no Markdown artifact. Phase 4 UI renders it. Expected content:
  - Russian problem restatement, reflecting the clarification or stated assumption (EDIT-06)
  - Difficulty and tags (EDIT-04)
  - Ordered approaches, each with intuition → algorithm → code (Python + Go) → complexity with a one-line justification (EDIT-02), plus a bridge to the previous approach (EDIT-03)
  - Edge cases the Reviewer identified as handled (EDIT-05)
  - Per-approach notes
  - Unverified-approach mentions (D-05)
- **D-12:** **Code is injected verbatim** from the executed `Solution` (`code_python` / `code_go`). The Writer LLM never outputs or rewrites code. Assembly code copies the code fields into the `Editorial` after the LLM call. This guarantees article code equals tested code. — **Reversibility:** costly — the `Editorial` schema splits LLM-authored prose from injected code fields. Letting the Writer own code later changes the contract and weakens the Core Value guarantee.
- **D-13:** The **Postgres task `result` holds the editorial JSON plus Garage artifact keys**. `GET /tasks/{id}` serves the article without touching Garage. Heavy intermediate data (review history, execution stdout/stderr, all attempts) lives only in Garage. This replaces the Phase 2 "dump everything" `finalize_success` shape. — **Reversibility:** costly — `result` is an API-visible contract that Phase 4 UI builds on.
- **D-14:** The Reviewer's **minor issues appear in the article as short notes per approach**. This uses the D-07 (Phase 2) allowance.
- **D-15:** The Editorial Writer makes **one LLM call for the whole article**. It needs every verified approach at once for ordering and bridges.
- **D-16:** For the Russian output (EDIT-01), use a prompt instruction plus a **cheap deterministic Cyrillic check** on prose fields. When the check fails, retry the Writer once. No extra LLM judge call.

### Garage Persistence
- **D-17:** Artifacts are written **incrementally per node**, not once at the end:
  - the analysis after the Analyzer
  - each approach iteration's solution / python_exec / go_exec / review after that branch's Reviewer
  - the editorial at the end

  FAILED and timed-out tasks still leave a trail.
- **D-18:** A Garage write failure means **log a warning and continue**. The task does not fail because of storage. The editorial is still delivered via Postgres.
- **D-19:** Key layout is per task, per approach, per iteration, with immutable writes:
  - `tasks/{task_id}/analysis.json`
  - `tasks/{task_id}/approaches/{idx}/iter-{n}/{solution,python_exec,go_exec,review}.json`
  - `tasks/{task_id}/editorial.json`

  The researcher may add a per-approach summary/meta object, but must not overwrite iteration objects.
- **D-20:** `result` lists **only keys actually written**, plus an `artifacts_incomplete: bool` flag when any write failed. It never points at nonexistent objects.
- **D-21:** Retention: **keep forever for v1**. No lifecycle policy.

### Claude's Discretion
- `Send` fan-out mechanics:
  - per-branch state shape and reducers. Phase 2's "no reducers" rule in `graph/state.py` must bend for fan-in.
  - how interrupt/checkpoint resume interacts with parallel branches
  - how to reconcile `recursion_limit` with N branches × `max_iterations`
- Mechanism for cancelling in-flight branches at timeout while keeping passed ones (D-10). Also the concrete Writer time reserve.
- Concurrency limits on parallel OpenAI calls and executor subprocesses across branches. The executor runs as uid 65534 with process-group kill, so check that parallel runs stay isolated in separate temp dirs.
- S3 client choice (`aioboto3` vs `boto3` in thread). Garage bucket/key provisioning in Docker Compose. Retry count before giving up on a write (D-18).
- Exact `Editorial` Pydantic field names. Cyrillic-ratio threshold (D-16).
- Model config key for the new node (`editorial_writer_model`), following the existing per-agent override pattern.
- Status transitions for `writing_editorial` and `designing_solution`, etc., with parallel branches. Only the Postgres status write matters here. WebSocket streaming is Phase 4.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project scope & requirements
- `.planning/PROJECT.md`: core value (verified correctness), constraints, key decisions
- `.planning/REQUIREMENTS.md`: STRAT-02, EDIT-01..06, ORCH-01, DATA-02 text
- `.planning/ROADMAP.md` §Phase 3: goal and 4 success criteria

### Prior phase decisions
- `.planning/phases/02-verified-single-solution-core-pipeline/02-CONTEXT.md`: D-00a..g, D-04 (stated assumption), D-05..07 (correction routing and severity), D-08 (timeout, now superseded by D-07 here)
- `.planning/phases/02-verified-single-solution-core-pipeline/02-REVIEW.md`: executor hardening context (uid drop, process-group kill) relevant to parallel execution
- `.planning/phases/02-verified-single-solution-core-pipeline/02-VERIFICATION.md`: what Phase 2 proved live

### Architecture research
- `.planning/research/ARCHITECTURE.md`: planned `schemas/editorial.py` and `storage/artifacts.py` locations; Garage keyed by task_id; fan-out cost note
- `.planning/research/STACK.md`: `aioboto3`/`boto3` for Garage, tenacity retry pattern
- `.planning/research/PITFALLS.md`: LangGraph pitfalls (recursion_limit, reducers)

### Interview source
- `interview.md`: original product-owner answers (Strategist curation, editorial shape)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/algorunner/agents/solution_strategist/node.py`: extend for curation and cap (D-03). `ApproachList` container pattern already exists.
- `src/algorunner/agents/solver/node.py`: currently hardcodes `state["approaches"][0]`. It must take the branch's approach instead.
- `src/algorunner/graph/routing.py` `decide_after_review`: per-branch correction routing reuses the same category → node table.
- `src/algorunner/graph/build.py` `finalize_success`: its body must be replaced by the Editorial Writer + D-13 result shape. `execute_*_node` and `_require_pass_marker` are reusable per branch.
- `src/algorunner/llm/retry.py` `call_structured` and `llm/client_factory.py` `model_for(...)`: the Editorial Writer follows the same pattern.
- `src/algorunner/config.py`: `garage_endpoint` exists but is unused. `global_timeout_s=600` becomes 1200. Add `max_approaches` and `editorial_writer_model`.
- `docker-compose.yml` + `docker/garage/garage.toml`: Garage v2.4.1 single-node is already running. It needs bucket and access-key provisioning.

### Established Patterns
- One node = one bounded LLM call. Structured output via Pydantic. `message.parsed is None` raises `ValueError`, which `worker/tasks.py` CR-01 catches and turns into a structured `TaskError`.
- `graph/state.py` is a plain `TypedDict` with no reducers (Phase 2 Pattern 4). Fan-out/fan-in (D-08) forces a deliberate exception here.
- Checkpointer is injected, never constructed in `graph/build.py`.
- Every required free-text schema field uses `Field(..., min_length=1)`.
- psycopg3 needs explicit `Jsonb(...)` for JSONB writes (the `result` column).

### Integration Points
- `worker/tasks.py` `_handle_result_or_pause` / `update_task_completed`: completion now stores the editorial + keys.
- `worker/tasks.py` `_invoke_with_budget`: global timeout. D-10 needs partial-success behaviour instead of a blanket FAIL.
- New `storage/artifacts.py` (Garage client). New `schemas/editorial.py`. New `agents/editorial_writer/`.

</code_context>

<specifics>
## Specific Ideas

- LangGraph `Send` for per-approach fan-out, as the user explicitly picked in D-08.
- The article must never show code that was not executed. Unverified approaches are mentioned without code (D-05, D-12).
- The editorial is aimed at interview-prep learners. Minor notes should be short, not a code-review dump.

</specifics>

<deferred>
## Deferred Ideas

- Garage artifact retention/lifecycle policy and a task-delete endpoint. Future milestone.
- Markdown export of the editorial. Rejected for v1 (D-11); could return with Phase 4 UI or later.

</deferred>

---

*Phase: 03-multi-approach-editorial-persistence*
*Context gathered: 2026-09-24*
