# Phase 3: Multi-Approach Editorial & Persistence - Research

**Researched:** 2026-09-24
**Domain:** LangGraph `Send` fan-out/fan-in with per-branch correction loops, structured-output editorial composition, S3 (Garage) artifact persistence
**Confidence:** HIGH (core LangGraph and Garage behaviours were verified by running probes against the pinned versions; see Sources)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Carried forward from Phase 2 (not re-discussed)
- Hybrid fixed graph (D-00a), Strategist + generic Solver (D-00b), and executors as tools (D-00c) all still hold.
- Targeted issue-routed correction (D-05) now applies **per approach**. Full history per iteration (D-06) also applies per approach.
- Critical vs minor severity (D-07): minor issues never block. They now surface in the article (see D-14).
- Stated assumption after clarification cap (D-04) must appear in the problem restatement (EDIT-06). A resolved clarification answer must appear there too.

#### Approach Count & Curation
- **D-01:** Max **3** approaches per task. The cap is configurable (`max_approaches` in `Settings`, default 3).
- **D-02:** **1 approach is valid.** When the Strategist judges no meaningful brute-force/alternative exists, it returns one approach. It must never invent a padding approach.
- **D-03:** Curation (STRAT-02) happens in the **same single Strategist call**: propose and select. Extend `ApproachList`/`Approach` so each approach carries a role label (e.g. `brute_force` / `optimized` / `alternative`) and a short "why included" rationale. The Strategist enforces the cap. The node must also guard it deterministically (truncate or reject if more than `max_approaches`).
- **D-04:** The **Editorial Writer decides the presentation order** in the article, not the Strategist. The Writer should follow the natural simple-to-better progression (EDIT-03). It writes the narrative bridge between consecutive approaches. The role label is input to the Writer, not a hard sort key.

#### Partial Failure
- **D-05:** An approach that exhausts its `max_iterations` without passing is **dropped from the verified set**. It is **mentioned briefly in the article** as attempted but not verified, and **no code is shown**. Its full attempt trail stays in Garage.
- **D-06:** The task is **COMPLETED if at least one approach passes**, whichever role it has. The task is FAILED only when zero approaches pass. The existing `CORRECTION_LOOP_EXHAUSTED` error shape still applies.

#### Time & Iteration Budget
- **D-07:** Raise global solve timeout from 10 min to **20 min** (`global_timeout_s` default 1200).
- **D-08:** Approaches run as a **parallel fan-out**. Use LangGraph `Send`, one branch per approach. Each branch runs its own Solver → Code Generator → Test Generator → Execute Python → Execute Go → Reviewer → correction loop. All branches join before the Editorial Writer. — **Reversibility:** costly — this restructures the graph from the Phase 2 linear shape into per-branch state. Going back to sequential means reworking the state schema and edges.
- **D-09:** `max_iterations` applies **per approach**. Each branch has its own correction budget. The global timeout still caps the total.
- **D-10:** When the global timeout hits while some approaches have passed, **ship the verified ones**. Cancel in-flight branches and treat them as "not verified" (same treatment as D-05). Still run the Editorial Writer. Reserve a time slice for the Writer inside the 20-min budget. The researcher/planner picks the concrete reserve. When zero approaches have passed at timeout, the task FAILS as today (INFRA-04).

#### Editorial Output Format
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

#### Garage Persistence
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

### Deferred Ideas (OUT OF SCOPE)
- Garage artifact retention/lifecycle policy and a task-delete endpoint. Future milestone.
- Markdown export of the editorial. Rejected for v1 (D-11); could return with Phase 4 UI or later.

(Also out of scope per the CONTEXT.md phase boundary: WebSocket streaming, React UI, docs set (Phase 4).)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STRAT-02 | Strategist decides which alternative approaches are worth including (not every possible approach) | Pattern 5: extend `Approach` with `role` + `rationale`, update the prompt to curate, deterministically truncate to `settings.max_approaches` in the node |
| EDIT-01 | Editorial in Russian regardless of input language | Pattern 7: Writer prompt plus a deterministic Cyrillic-ratio check (aggregate ≥ 0.6, per-field ≥ 0.3), with one retry |
| EDIT-02 | Each approach: Intuition → Algorithm → Code (Py + Go) → Complexity with one-line justification | Pattern 6: the `EditorialApproach` schema fixes the field order. Code is injected verbatim (D-12) |
| EDIT-03 | Sequential order with a narrative bridge | Pattern 6: the Writer returns approaches in its chosen order with `bridge_from_previous` (null only for the first). Assembly validates the ID set |
| EDIT-04 | Difficulty rating + topic/technique tags | Injected deterministically from `analysis.difficulty` and the verified approaches' `technique` (no LLM) |
| EDIT-05 | Edge cases the Reviewer identified as handled | New `ReviewResult.handled_edge_cases: list[str]` (Pitfall 6). The passing review's list is fed to the Writer |
| EDIT-06 | Resolved clarification reflected in the restatement | New `clarifications: list[dict]` state field appended by `clarification_gate_node` (Pitfall 7). `assumption_stated` is also passed to the Writer |
| ORCH-01 | Full pipeline as one deterministic StateGraph | Patterns 1–4: parent graph → `Send` → `run_approach` wrapper node invoking a compiled per-approach subgraph → join node → Writer → finalize |
| DATA-02 | All intermediate artifacts persisted to Garage | Pattern 8: `storage/artifacts.py` (boto3 in `asyncio.to_thread`), persist nodes, D-19 key layout, Garage `--default-bucket` provisioning (verified) |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Python 3.14, LangGraph, OpenAI API with model configurable via env/config and per-agent overrides. Fixed.
- `uv` package manager. Fixed. This is a single `uv` package, not a workspace (STATE.md decision).
- taskiq + Redis. PostgreSQL holds task state (source of truth) and LangGraph checkpoints.
- Garage (S3-compatible) holds intermediate agent artifacts.
- Docker Compose deployment for this milestone.
- Maximum feasible type safety in Python.
- Simple modular architecture (not DDD/clean architecture).
- Code execution: Python via subprocess, Go via compile+run, no sandbox in v1.
- Output (editorial) is always Russian.
- **What NOT to use:**
  - blocking `subprocess.run()` in async tasks
  - bare `psycopg.connect()` for the checkpointer
  - `RLIMIT_FSIZE=0`
  - `subprocess.run(timeout=)` as the only time bound
  - treating `chat.completions.parse()` as retry-safe
  - ARQ, Celery
- The same doc says to use `lifespan`, not `@app.on_event`.
- CLAUDE.md suggests `boto3` or `aioboto3` for Garage, and `aioboto3` "avoids blocking the event loop, plain boto3 is fine if artifact I/O happens in a thread". This research picks boto3 + `asyncio.to_thread`.
- GSD workflow enforcement: file edits happen through GSD commands (the planner/executor's concern).

## Summary

Phase 2 left a linear, single-approach graph. The shape is `GraphState` (a plain `TypedDict` with no reducers) → analyzer → strategist → solver (hardcoded `approaches[0]`) → code_generator → test_generator → execute_python → execute_go → reviewer → `decide_after_review` → `finalize_success`/`finalize_failed`. Phase 3 widens this in four ways:

1. The per-approach loop moves into a **compiled per-approach subgraph** (`ApproachState`). A thin `run_approach` wrapper node invokes it, and each `Send` targets that wrapper.
2. The parent gains a single idempotent fan-in reducer (a dict keyed by approach index) plus a **join node**.
3. A new Editorial Writer node makes one structured-output call. Deterministic assembly injects the verbatim code.
4. A new `storage/artifacts.py` Garage client is fed by small persist nodes.

Every load-bearing LangGraph behaviour was checked against the pinned `langgraph==1.2.12` in a scratch venv:

- Branches run truly independently. The fast branch finished 3 correction iterations while the slow one was still on iteration 1.
- A subgraph invoked inside a node inherits the parent checkpointer and gets its own namespace `run_approach:<task-uuid>`.
- An **unguarded exception in one branch cancels all sibling branches** and fails the graph. The try/except wrapper is therefore mandatory for D-05/D-06.
- `asyncio.wait_for` around the subgraph gives clean per-branch cancellation (D-10).
- `Overwrite({})` resets a reducer channel.
- `recursion_limit` is checked per graph (each subgraph invocation has its own step counter), not summed across branches.
- **A conditional edge attached directly to the fan-out node runs once per branch with a partial view of state. It caused both `writer` and `failed` to run in the probe.** Always join with a plain edge first.

For Garage, v2.4.1's built-in `--single-node --default-bucket` flags provision the bucket and key from `GARAGE_DEFAULT_*` env vars, idempotently across restarts. This was verified with a throwaway container. `boto3 1.43.101` (default checksum settings, path-style addressing, region `garage`) round-trips UTF-8 JSON correctly. **Garage does not enforce `If-None-Match: *`**, so an overwrite succeeds silently. Immutability (D-19) must come from the key scheme, not from the store.

**Primary recommendation:** Parent graph `analyzer ⇄ clarification_gate → persist_analysis → strategist ─Send×N→ run_approach (try/except + wait_for around the compiled approach subgraph) → collect_approaches (join) → editorial_writer | finalize_failed → finalize_success`. Run-scoped dependencies (deadline, artifact store, status sink) travel in a LangGraph `Runtime` context object, never in checkpointed state.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Approach proposal + curation + cap (STRAT-02) | Worker: LangGraph Strategist node | Settings (`max_approaches`) | One LLM call (D-03). The cap is enforced deterministically in node code |
| Per-approach solve/verify/correct loop | Worker: per-approach subgraph | Executors (tools) | D-08/D-09. Existing agent nodes are reused unchanged except the Solver/prompt input |
| Fan-in, partial-failure policy, timeout policy | Worker: parent graph (`run_approach` wrapper + join node) | Worker task (`_invoke_with_budget`) | D-05/D-06/D-10 are pure deterministic Python |
| Editorial prose (Russian) | Worker: Editorial Writer node (LLM) | — | D-15: one call |
| Editorial assembly (code injection, difficulty, tags) | Worker: deterministic assembly function | — | D-12: never LLM |
| Artifact persistence | Storage: Garage via `storage/artifacts.py` | Worker persist nodes | D-17..D-20 |
| Final result + status | Database: Postgres `tasks.result` / `status` | API reads only | D-13: `GET /tasks/{id}` never touches Garage |
| Bucket/key provisioning | Infra: docker-compose (Garage flags + env) | — | Verified `--default-bucket` |

## Standard Stack

### Core (already pinned, versions from `uv.lock`)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `langgraph` | 1.2.12 | `Send`, `Overwrite`, `Runtime` context, subgraphs | Already locked. All APIs below verified in this exact version [VERIFIED: scratch venv built from `uv export --frozen`] |
| `langgraph-checkpoint-postgres` | 3.1.2 | Parent + subgraph checkpoints | Already wired (`worker/broker.py`) |
| `openai` | 3.19.0 | `chat.completions.parse(..., timeout=...)` | `parse` accepts a per-request `timeout` [VERIFIED: `openai/resources/chat/completions/completions.py` signature]. The default client timeout is 600s [VERIFIED: `openai/_constants.py` `DEFAULT_TIMEOUT = httpx2.Timeout(timeout=600, connect=5.0)`] |
| `pydantic` | 2.13.5 | `Editorial`, `ApproachOutcome`, extended `Approach`/`ReviewResult` | Existing convention |
| `tenacity` | 9.1.4 | Existing `call_structured` retry | Reused as-is |

### New
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `boto3` | 1.43.101 (latest, 2026-09-23) | S3 client for Garage | `put_object` / `get_object` wrapped in `asyncio.to_thread`. Verified working against Garage v2.4.1 with default checksum config [VERIFIED: live probe] `boto3` [WARNING: flagged as suspicious — verify before using.] (the SUS verdict is "too-new/unknown-downloads" because AWS publishes daily. The repo is github.com/boto/boto3, requires-python `>=3.10`, and it has a 3.14 classifier) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `boto3` + `asyncio.to_thread` | `aioboto3` 15.5.0 | Last release 2025-10-30 (about 11 months stale). It pins `aiobotocore`, which pins an older `botocore`. It pulls in aiohttp. There are only about 5 small writes per iteration, so a thread hop costs nothing. Rejected |
| Garage `--default-bucket` flags | `garage layout/key/bucket` CLI init script or sidecar | More moving parts. The flags are built into v2.4.1 and idempotent [VERIFIED: probe restart] |
| Subgraph-per-branch | Flat `Send` chain (`Command(goto=Send(...))` per node) | A flat graph runs branches in **lock-step supersteps** (each superstep waits for the slowest branch node), and branch state rides inside Send packets. Rejected |
| Subgraph-per-branch | One plain async function running the whole loop | Breaks ORCH-01 ("deterministic StateGraph", nodes as graph nodes) and loses per-step checkpoints. Rejected |

**Installation:**
```bash
uv add boto3
# optional, dev-only typing stubs (also SUS "too-new" for the same daily-release reason):
# uv add --dev "types-boto3[s3]"
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| boto3 | PyPI | latest release 2026-09-23 (project ~10 yrs) | unknown to seam | github.com/boto/boto3 | [SUS] (too-new, unknown-downloads) | Flagged. The planner adds `checkpoint:human-verify` before `uv add boto3` |
| aioboto3 | PyPI | latest 2025-10-30 | unknown | none reported by seam | [SUS] (no-repository) | Not recommended (not installed) |
| types-boto3 | PyPI | latest 2026-09-23 | unknown | github.com/youtype/mypy_boto3_builder | [SUS] (too-new) | Optional dev dep. Checkpoint if adopted |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** boto3 (and types-boto3 if adopted). The planner inserts `checkpoint:human-verify` before each install.
No `postinstall` concept applies to PyPI wheels.

## Architecture Patterns

### System Architecture Diagram

```
worker.solve_problem(task_id)
  │  deadline = monotonic() + (global_timeout_s - active_execution_seconds)
  │  context = PipelineContext(deadline, artifacts=ArtifactStore, status_sink=pg_status_writer)
  ▼
graph.ainvoke(input, {"configurable":{"thread_id":task_id}, "recursion_limit":R}, context=..., durability="sync")
  │
  START → analyzer ──needs_clarification──► clarification_gate (interrupt; appends {question, answer}) ─┐
             ▲                                                                                        │
             └────────────────────────────────────────────────────────────────────────────────────────┘
          │ (no clarification)
          ▼
   persist_analysis ──► Garage tasks/{id}/analysis.json   (status: designing_solution)
          ▼
   strategist (LLM: curate ≤ max_approaches, role + rationale; resets approach_outcomes = Overwrite({}))
          │  fan_out_approaches(): [Send("run_approach", ApproachInput(idx, approach, ...)) for each]
          ▼
   ┌──────────── run_approach × N (same superstep, independent progress) ──────────────┐
   │ try: wait_for(approach_graph.ainvoke(branch_state), timeout = deadline - reserve - now)
   │   approach subgraph:  solver → code_generator → test_generator → execute_python
   │                        → execute_go → reviewer → persist_iteration ──► Garage approaches/{idx}/iter-{n}/*.json
   │                        persist_iteration ─decide_after_review─► solver | code_generator | END
   │ except TimeoutError → status "timed_out";  except GraphBubbleUp → re-raise;  except Exception → "errored"
   │ write approaches/{idx}/summary.json;  return {"approach_outcomes": {idx: ApproachOutcome}}
   └────────────────────────────────────────────────────────────────────────────────────┘
          │ plain edge (join: runs ONCE after all branches)
          ▼
   collect_approaches ──any verified?──► editorial_writer (LLM prose; Cyrillic check; 1 retry) (status: writing_editorial)
          │ none verified                       ▼
          ▼                              assemble_editorial (inject code/difficulty/tags) → finalize_success
   finalize_failed (error)                      └──► Garage tasks/{id}/editorial.json; result = {editorial, artifact_keys, artifacts_incomplete, approaches}
          ▼                                            ▼
         END ◄─────────────────────────────────────────┘
  ▼
worker._handle_result_or_pause → update_task_completed(result) | update_task_failed(error) | clarification pause
```

### Recommended Project Structure (new/changed files only)
```
src/algorunner/
├── agents/
│   ├── editorial_writer/        # NEW: __init__.py, node.py, prompts.py, language.py (Cyrillic check)
│   ├── solution_strategist/     # CHANGED: prompt curates + role/rationale; node caps to max_approaches, resets outcomes
│   └── solver/                  # CHANGED: reads state["approach"] (branch) instead of state["approaches"][0]
├── graph/
│   ├── state.py                 # CHANGED: GraphState (parent) + ApproachState (branch) + ApproachInput + reducer
│   ├── approach.py              # NEW: build_approach_graph(), run_approach wrapper, persist_iteration node
│   ├── build.py                 # CHANGED: parent graph, fan-out, join, writer, finalize nodes
│   ├── context.py               # NEW: PipelineContext dataclass (deadline, artifacts, status_sink)
│   └── routing.py               # CHANGED: annotations only; add decide_after_join
├── schemas/
│   ├── editorial.py             # NEW: EditorialDraft (LLM) + Editorial (assembled)
│   ├── outcome.py (or in solution.py)  # NEW: ApproachOutcome
│   ├── solution.py              # CHANGED: Approach gains role + rationale
│   └── review.py                # CHANGED: ReviewResult gains handled_edge_cases
├── storage/artifacts.py         # NEW: ArtifactStore (boto3 via to_thread), key builders
├── config.py                    # CHANGED: new settings (below)
└── worker/tasks.py              # CHANGED: deadline/context, recursion_limit, removes per-solution initial keys
docker-compose.yml               # CHANGED: garage flags/env/healthcheck; worker GARAGE_* env
.env.example                     # CHANGED: GARAGE_* vars
```

### Pattern 1: Parent/branch state split with an idempotent fan-in reducer
**What:** The parent `GraphState` keeps task-level fields only. Per-solution fields move to `ApproachState`. The **only** reducer is a dict merge keyed by approach index, which makes it idempotent: a re-delivered branch overwrites its own slot and never duplicates.
**Why a dict, not `operator.add`:** LangGraph applies graph *input* through reducers too. `solve_problem` re-invokes with `initial_state` on the same `thread_id` after a taskiq redelivery, so a list reducer would append old + new outcomes. The strategist resets the channel with `Overwrite({})` (verified: the re-invoke returned only the new outcome).
```python
# Source: verified in scratch probe against langgraph 1.2.12 (probe_send.py)
from typing import Annotated, TypedDict
from langgraph.types import Overwrite

def merge_outcomes(left: dict[int, "ApproachOutcome"] | None,
                   right: dict[int, "ApproachOutcome"] | None) -> dict[int, "ApproachOutcome"]:
    return {**(left or {}), **(right or {})}

class GraphState(TypedDict):
    task_id: str
    problem_text: str
    language: str
    examples: list[dict]
    analysis: ProblemAnalysis | None
    clarification_rounds: int
    clarification_answer: str | None
    clarifications: list[dict]          # NEW: [{"question":..., "answer":...}] plain append (EDIT-06)
    assumption_stated: str | None
    approaches: list[Approach]
    max_iterations: int
    analysis_artifact_key: str | None   # NEW: plain overwrite
    artifacts_incomplete: bool          # NEW: plain overwrite (only persist_analysis/finalize write it)
    approach_outcomes: Annotated[dict[int, ApproachOutcome], merge_outcomes]  # NEW: the one reducer
    result: dict | None
    error: dict | None

class ApproachState(TypedDict):          # branch-local, plain TypedDict, NO reducers
    task_id: str
    approach_idx: int
    approach: Approach
    problem_text: str
    examples: list[dict]
    analysis: ProblemAnalysis
    assumption_stated: str | None
    max_iterations: int
    solver_output: dict | None
    solution: Solution | None
    python_execution: ExecutionResult | None
    go_execution: ExecutionResult | None
    review: ReviewResult | None
    review_history: list[ReviewResult]
    iterations: int
    artifact_keys: list[str]
    artifacts_incomplete: bool

# strategist node return:  {"approaches": capped, "approach_outcomes": Overwrite({})}
```
Branch-level lists (`review_history`, `artifact_keys`) keep Phase 2's explicit `state[...] + [x]` style. They are sequential within a branch, so no reducer is needed.

### Pattern 2: `run_approach` wrapper = exception isolation + per-branch deadline
**What:** `Send` targets a plain async node that invokes the compiled approach subgraph inside `try/except` and `asyncio.wait_for`. It returns one `ApproachOutcome` whatever happens.
**Why mandatory:** In the probe, an unguarded `ValueError` in one branch **cancelled the sibling branch** mid-flight and raised out of `ainvoke` (the parent state showed both tasks errored). That contradicts D-05/D-06. The node functions keep raising `ValueError` per D-00f. The wrapper converts it to a non-verified outcome.
```python
# Source: pattern verified in probe_send.py (branches: verified/verified/errored/timed_out)
import asyncio, time
from langgraph.errors import GraphBubbleUp
from langgraph.runtime import Runtime

async def run_approach(state: ApproachInput, runtime: Runtime[PipelineContext]) -> dict:
    ctx = runtime.context  # None when the caller passed no context (tests) -> no deadline
    budget = None
    if ctx is not None and ctx.deadline_monotonic is not None:
        budget = ctx.deadline_monotonic - ctx.editorial_reserve_s - time.monotonic()
    branch_state = initial_branch_state(state)
    try:
        if budget is not None and budget <= 0:
            raise TimeoutError
        final = await asyncio.wait_for(approach_graph.ainvoke(branch_state), timeout=budget)
        outcome = outcome_from_final(state, final)       # "verified" | "exhausted"
    except GraphBubbleUp:
        raise                                           # never swallow interrupts/bubble-ups
    except TimeoutError:
        outcome = ApproachOutcome.not_verified(state, status="timed_out")
    except Exception as exc:                            # D-00f ValueErrors, executor errors, ...
        outcome = ApproachOutcome.not_verified(state, status="errored", error=str(exc)[:500])
    outcome = await write_summary(ctx, state, outcome)  # approaches/{idx}/summary.json (best effort)
    return {"approach_outcomes": {state["approach_idx"]: outcome}}
```
- `approach_graph.ainvoke(branch_state)` must be called **without** an explicit `configurable.thread_id`/`checkpoint_ns`. An explicit checkpoint coordinate drops the inherited ambient config, so the child writes to its own lineage and never finds it again [CITED: Context7 `/langchain-ai/langgraph` `_internal/_config.py` `ensure_config` comment]. Compile the subgraph with the default `checkpointer=None` ("stateless: inherits parent checkpointer, state resets each invocation") [CITED: Context7 `test_subgraph_persistence.py` docstring]. Verified: 4 branch namespaces `run_approach:<uuid>` appeared in the parent's saver.
- `CancelledError` is a `BaseException`, so `except Exception` does not catch it. The outer worker `wait_for` still cancels everything.
- In the verified status set, `"exhausted"` means the loop ended with `review.passed is False`.

### Pattern 3: Join with a plain edge, then route from the join node
**What:** `builder.add_edge("run_approach", "collect_approaches")`, then `add_conditional_edges("collect_approaches", decide_after_join, {...})`.
**Why:** In the probe, a conditional edge attached directly to the fan-out node ran **once per branch**, and each run saw only its own branch's write (`router sees outs= ['bad']` / `['ok']`). **Both** `failed` and `writer` executed. A plain edge from the Send target fires the next node exactly once after the whole superstep. The writer saw all 4 outcomes in probe 1.
```python
builder.add_conditional_edges("strategist", fan_out_approaches, ["run_approach"])
builder.add_edge("run_approach", "collect_approaches")
builder.add_conditional_edges("collect_approaches", decide_after_join,
                              {"editorial_writer": "editorial_writer", "finalize_failed": "finalize_failed"})
```
`collect_approaches` can be a zero-logic node (`return {}`) or can set the `WRITING_EDITORIAL` status.

### Pattern 4: Approach subgraph reusing Phase 2 nodes and the router unchanged
```python
def build_approach_graph() -> CompiledStateGraph:
    b = StateGraph(ApproachState, context_schema=PipelineContext)
    b.add_node("solver", solver_node)
    b.add_node("code_generator", code_generator_node)
    b.add_node("test_generator", test_generator_node)
    b.add_node("execute_python", execute_python_node)
    b.add_node("execute_go", execute_go_node)
    b.add_node("reviewer", reviewer_node)
    b.add_node("persist_iteration", persist_iteration_node)
    b.add_edge(START, "solver")
    ... linear edges as Phase 2 ... ; b.add_edge("reviewer", "persist_iteration")
    b.add_conditional_edges("persist_iteration", decide_after_review, {
        "finalize_success": END, "finalize_failed": END,
        "solver": "solver", "code_generator": "code_generator"})
    return b.compile()   # checkpointer=None -> inherits parent's
```
`decide_after_review` returns `"finalize_success"`/`"finalize_failed"`/`"solver"`/`"code_generator"` [VERIFIED: `src/algorunner/graph/routing.py:30-41`, which returns the verbatim strings `"finalize_failed"`, `"finalize_success"`, and `next((t for t in _TARGET_PRIORITY if t in targets), "solver")` with `_TARGET_PRIORITY = ["solver", "code_generator"]`]. Mapping the two terminal labels to `END` in the path map means `routing.py` needs only a type-annotation change (the parameter type becomes `ApproachState`). Existing nodes read these keys: `solver_output`, `review_history`, `analysis`, `assumption_stated`, `problem_text`, `solution`, `examples`, `python_execution`, `go_execution`, `iterations` (grep of `agents/`). `ApproachState` must carry all of them. Only `solver/node.py` and `solver/prompts.py` read `state["approaches"][0]`. They change to `state["approach"]`.

### Pattern 5: Strategist curation (STRAT-02, D-01..D-03)
- Extend `Approach` [current shape VERIFIED: `src/algorunner/schemas/solution.py:26-29`: `name: str = Field(..., min_length=1)`, `technique: str = Field(..., min_length=1)`, `summary: str = Field(..., min_length=1)`] with `role: Literal["brute_force", "optimized", "alternative"]` and `rationale: str = Field(..., min_length=1)`. Keep them required so OpenAI strict mode requires them anyway. Update every test fixture that constructs `Approach(...)` (9 call sites across `tests/` and `src/`).
- The prompt changes from "Do not merge or omit distinct approaches" (current text) to "propose, then **select** at most {max_approaches} worth teaching; return exactly one if no meaningful brute-force or alternative exists; never pad".
- Node guard: `approaches = result.approaches[: settings.max_approaches]` plus a `logger.warning` when truncated. Keep the existing `if not result.approaches: raise ValueError`.

### Pattern 6: Editorial = LLM draft + deterministic assembly (D-11, D-12, D-15)
Two schemas. The LLM only ever sees and returns prose. Code, difficulty and tags are injected after the call.
```python
# schemas/editorial.py  (field names are a recommendation — Claude's discretion)
ApproachRole = Literal["brute_force", "optimized", "alternative"]

class ApproachProse(BaseModel):              # LLM-authored (response_format part)
    approach_id: int                         # = Strategist index of a VERIFIED approach
    title: str = Field(..., min_length=1)
    bridge_from_previous: str | None         # null only for the first approach in writer order
    intuition: str = Field(..., min_length=1)
    algorithm: str = Field(..., min_length=1)
    complexity_time: str = Field(..., min_length=1)       # e.g. "O(n)"
    complexity_space: str = Field(..., min_length=1)
    complexity_justification: str = Field(..., min_length=1)  # one line (EDIT-02)
    notes: list[str]                          # short notes from minor issues (D-14), may be []

class UnverifiedMention(BaseModel):
    approach_id: int
    note: str = Field(..., min_length=1)      # "attempted but not verified", no code (D-05)

class EditorialDraft(BaseModel):             # response_format for the single Writer call
    problem_restatement: str = Field(..., min_length=1)   # reflects clarifications/assumption (EDIT-06)
    approaches: list[ApproachProse]          # WRITER ORDER = presentation order (D-04)
    edge_cases: list[str]                    # Russian rendering of reviewer-handled edge cases (EDIT-05)
    unverified: list[UnverifiedMention]

class EditorialApproach(BaseModel):          # assembled
    approach_id: int
    role: ApproachRole
    technique: str
    title: str
    bridge_from_previous: str | None
    intuition: str
    algorithm: str
    code_python: str                         # INJECTED verbatim from Solution.code_python
    code_go: str                             # INJECTED verbatim from Solution.code_go
    complexity_time: str
    complexity_space: str
    complexity_justification: str
    notes: list[str]

class Editorial(BaseModel):
    problem_restatement: str
    difficulty: Literal["easy", "medium", "hard"]     # INJECTED from analysis.difficulty
    tags: list[str]                                   # INJECTED: dedup verified techniques, writer order
    approaches: list[EditorialApproach]
    edge_cases: list[str]
    unverified_approaches: list[UnverifiedMention]
```
`difficulty` is `Literal["easy", "medium", "hard"]` [VERIFIED: `src/algorunner/schemas/problem.py:18`].

**Assembly validation (deterministic, raises `ValueError` so it counts toward the one D-16 retry):**
- The set of `approach_id` in `draft.approaches` must equal the set of verified IDs exactly, with no duplicates.
- `draft.unverified` IDs must be ⊆ the non-verified IDs.
- `bridge_from_previous` must be null for index 0 and non-empty for the rest. Alternatively, normalise index 0 to None.

Code comes **only** from `outcome.final_solution.code_python/code_go`. The Writer prompt receives algorithm and complexity text, **not** the code. That removes any temptation to rewrite code and keeps the prompt smaller.

### Pattern 7: Russian check (D-16)
```python
_CYR = re.compile(r"[Ѐ-ӿ]")
_CODE_SPAN = re.compile(r"`[^`]*`")
_BIG_O = re.compile(r"O\([^)]*\)")

def cyrillic_ratio(text: str) -> tuple[float, int]:
    text = _BIG_O.sub(" ", _CODE_SPAN.sub(" ", text))
    letters = [c for c in text if c.isalpha()]
    return (sum(1 for c in letters if _CYR.match(c)) / len(letters) if letters else 1.0, len(letters))
# pass iff aggregate ratio over all prose fields >= 0.6 AND every field with >= 20 letters has ratio >= 0.3
```
Measured on samples:

| Sample | Ratio |
|---|---|
| Typical Russian technical prose | 0.87 |
| Identifier-heavy Russian sentence | 0.48 |
| A short Russian bridge | 0.96 |
| Mostly-English text with one Russian sentence | 0.12 |
| English | 0.00 |

So aggregate ≥ 0.6 with per-field ≥ 0.3 separates them cleanly [VERIFIED: local computation]. The thresholds themselves are a tuning choice [ASSUMED]. Make them `Settings` fields. The prompt should also tell the Writer to wrap identifiers in backticks (backtick spans are excluded from the ratio).

### Pattern 8: Garage artifact store (D-17..D-20)
```python
# storage/artifacts.py — verified calls against Garage v2.4.1 + boto3 1.43.101 (probe_s3.py)
import asyncio, json, logging
from functools import lru_cache
import boto3
from botocore.config import Config

@lru_cache
def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.garage_endpoint,                # http://garage:3900 in compose
        region_name=settings.garage_region,                   # "garage" (docker/garage/garage.toml s3_region)
        aws_access_key_id=settings.garage_access_key_id,
        aws_secret_access_key=settings.garage_secret_access_key,
        config=Config(s3={"addressing_style": "path"},
                      retries={"max_attempts": 3, "mode": "standard"},
                      connect_timeout=2, read_timeout=5),
    )

class ArtifactStore:
    async def put_json(self, key: str, payload: BaseModel | dict) -> bool:
        body = (payload.model_dump_json() if isinstance(payload, BaseModel)
                else json.dumps(payload, ensure_ascii=False)).encode()
        try:
            await asyncio.wait_for(asyncio.to_thread(
                _client().put_object, Bucket=settings.garage_bucket, Key=key,
                Body=body, ContentType="application/json"), timeout=settings.artifact_write_timeout_s)
            return True
        except Exception:                      # D-18: warn and continue, never fail the task
            logger.warning("artifact write failed: %s", key, exc_info=True)
            return False

def iteration_key(task_id: str, idx: int, n: int, kind: str) -> str:
    return f"tasks/{task_id}/approaches/{idx}/iter-{n}/{kind}.json"   # kind in solution|python_exec|go_exec|review
```
- The region is `s3_region = "garage"` [VERIFIED: `docker/garage/garage.toml:12`].
- Retry count: botocore `standard` mode with `max_attempts=3` (initial + 2 retries) plus a 10s overall `wait_for` per write. A Garage outage then costs at most ~10s per write, not minutes [ASSUMED tuning].
- When `garage_endpoint == ""`, use a no-op store that returns `False`. The result then reports `artifacts_incomplete: true` and no keys. Tests inject an in-memory fake through the context.
- `n` in `iter-{n}` = `state["iterations"]` **after** the reviewer's increment. It is 1-based, and the reviewer increments exactly once per call [VERIFIED: `src/algorunner/agents/reviewer/node.py:66-70` returns `"iterations": state["iterations"] + 1`]. That makes keys unique per iteration, which is the only immutability guarantee available. Garage accepted an `IfNoneMatch="*"` overwrite in the probe.
- The analysis is written once by `persist_analysis` on the analyzer→strategist path. It always carries the *final* post-clarification analysis, so there is never an overwrite.

**Docker Compose provisioning (verified with a throwaway container, including restart idempotency):**
```yaml
garage:
  image: dxflrs/garage:v2.4.1
  command: ["/garage", "server", "--single-node", "--default-bucket"]
  environment:
    GARAGE_DEFAULT_ACCESS_KEY: ${GARAGE_ACCESS_KEY_ID:-GK0123456789abcdef01234567}
    GARAGE_DEFAULT_SECRET_KEY: ${GARAGE_SECRET_ACCESS_KEY:-<64 hex chars>}
    GARAGE_DEFAULT_BUCKET: ${GARAGE_BUCKET:-algorunner-artifacts}
  healthcheck:
    test: ["CMD", "/garage", "status"]
worker:
  environment:
    GARAGE_ENDPOINT: http://garage:3900
    GARAGE_ACCESS_KEY_ID / GARAGE_SECRET_ACCESS_KEY / GARAGE_BUCKET: same values
  depends_on: { garage: { condition: service_healthy } }
```
- `garage server --help` in v2.4.1 prints: `--default-access-key  Configure a default S3 API key using environment variables GARAGE_DEFAULT_ACCESS_KEY and GARAGE_DEFAULT_SECRET_KEY. Requires --single-node` and `--default-bucket  Configure a default bucket using environment variable GARAGE_DEFAULT_BUCKET. Implies --default-access-key. Requires --single-node` [VERIFIED: `docker exec algorunner-garage-1 /garage server --help`].
- The key format that worked was `GK` + 24 hex characters, with a 64-hex-character secret. Whether other formats are rejected is [ASSUMED]; keep this format.
- The existing dev Garage currently has **no buckets and no keys** [VERIFIED: `garage bucket list` / `garage key list` empty].

### Pattern 9: Deadline and run-scoped deps via `Runtime` context (not state, not configurable)
- `StateGraph(GraphState, context_schema=PipelineContext)` and `graph.ainvoke(..., context=PipelineContext(...))`. Nodes take `runtime: Runtime[PipelineContext]`.
- Context **propagates automatically to a subgraph invoked inside a node** [VERIFIED: probe3.py, where the inner node saw `deadline=123.0` without an explicit `context=`].
- When no context is passed, `runtime.context is None` [VERIFIED: probe4.py]. Every consumer must handle `None`, and existing tests pass no context.
- Do **not** put these in `config["configurable"]`. Primitive `configurable` values are copied into every checkpoint's metadata [VERIFIED: `langgraph/checkpoint/base/__init__.py` `get_checkpoint_metadata`, which copies `str`/`int`/`bool`/`float` values], and objects cannot go there.
```python
@dataclass(frozen=True)
class PipelineContext:
    deadline_monotonic: float | None = None     # worker: time.monotonic() + remaining budget
    editorial_reserve_s: float = 240.0
    artifacts: ArtifactStore | None = None
    status_sink: Callable[[str, TaskStatus], Awaitable[None]] | None = None  # (task_id, status)
```
The deadline is recomputed on every invocation (initial run and clarification resume) from `active_execution_seconds`. That matches the existing budget semantics [VERIFIED: `src/algorunner/worker/tasks.py:81-83`: `used = task.active_execution_seconds if task is not None else 0.0` / `remaining = settings.global_timeout_s - used`].

### Pattern 10: Time budget for D-07/D-10 (concrete numbers)
- `global_timeout_s = 1200` (D-07). `editorial_reserve_s = 240` [ASSUMED tuning].
- Branch deadline = invocation deadline − 240s. Branches that pass before it are kept. In-flight ones become `timed_out` (not verified, no code), and the Writer still runs.
- Writer: pass `timeout=editorial_attempt_timeout_s` (default 100s) to `parse` through `call_structured(**kwargs)`. Also wrap the whole writer node body in `asyncio.wait_for(..., timeout=max(1, deadline - now))`. `call_structured` retries `APITimeoutError` up to `retry_max_attempts=5`, which could otherwise exceed the reserve.
- The outer `_invoke_with_budget` `wait_for(remaining)` stays as the last-resort hard cap. If it fires (Writer overran), the task FAILS with `GLOBAL_TIMEOUT`, as today. The error code is quoted from `worker/tasks.py:84`: `TaskError(code="GLOBAL_TIMEOUT", message="Solve time budget exhausted")`.

### Pattern 11: Status transitions (Postgres only)
The single `status` column cannot represent N parallel branches. Use parent-level transitions only, through `ctx.status_sink`. The worker's sink calls `update_task_status`, and failures are logged, never raised. Phase 4 adds a Redis publish in the same sink.

| When | Status |
|------|--------|
| Worker start / analyzer | `analyzing_problem` (existing) |
| `persist_analysis` / strategist | `designing_solution` |
| Fan-out start (`strategist` return, or first `run_approach`) | `generating_code` |
| `collect_approaches` → writer | `writing_editorial` |
| Worker end | `completed` / `failed` (existing) |

These values come from the `TaskStatus` enum [VERIFIED: `src/algorunner/schemas/task.py:38-49`: `DESIGNING_SOLUTION = "designing_solution"`, `GENERATING_CODE = "generating_code"`, `WRITING_EDITORIAL = "writing_editorial"`, `COMPLETED = "completed"`, `FAILED = "failed"`]. `generating_tests`/`executing_tests`/`reviewing`/`correcting` stay unused at task level in Phase 3. Per-branch progress is a Phase 4 WebSocket concern.

### Pattern 12: Result and failure shapes (D-06, D-13, D-20)
```python
result = {
    "editorial": editorial.model_dump(),
    "approaches": [{"approach_id": i, "name": ..., "role": ..., "status": "verified|exhausted|timed_out|errored",
                    "iterations": n} for i, o in sorted(outcomes.items())],   # small index for the UI
    "artifact_keys": [...only keys whose put_json returned True...],
    "artifacts_incomplete": any_write_failed_or_store_disabled,
}
```
Zero verified routes to `finalize_failed`. Error-code precedence:
1. Any branch `exhausted` → `CORRECTION_LOOP_EXHAUSTED` (D-06, existing code [VERIFIED: `src/algorunner/graph/build.py:128` `"code": "CORRECTION_LOOP_EXHAUSTED"`]).
2. Otherwise, any `timed_out` → `GLOBAL_TIMEOUT` (INFRA-04).
3. Otherwise, all `errored` → `APPROACH_PIPELINE_ERROR` with the first branch's error message [ASSUMED new code name; needs user confirmation].

The message should summarise each approach's status.

### Anti-Patterns to Avoid
- **Conditional edge on the `Send` target node.** It runs once per branch with a partial view (Pattern 3).
- **`operator.add` list reducer for outcomes.** Graph input is reduced too, so re-invocation duplicates outcomes (Pattern 1).
- **Unguarded subgraph as a direct `Send` target.** One branch's `ValueError` cancels its siblings (Pattern 2).
- **Explicit `thread_id` in the subgraph `ainvoke` config.** It orphans the child's checkpoints (Pattern 2).
- **Writer emitting code or Big-O it invented from code.** Code is injected (D-12). The prompt gets no code.
- **Deadline/store in `configurable` or state.** Use the `Runtime` context (Pattern 9).
- **Relying on S3 `If-None-Match` for immutability.** Garage ignores it (Pattern 8).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Parallel branches + join | `asyncio.gather` inside one node | LangGraph `Send` + join edge | ORCH-01, per-step checkpoints, D-08 lock |
| Branch correction loop | Python `while` loop | Compiled approach subgraph reusing `decide_after_review` | Deterministic graph, checkpointed |
| Reducer reset | Sentinel values / custom "clear" logic | `langgraph.types.Overwrite` | Built-in, verified |
| S3 signing / retries | Raw HTTP to Garage | `boto3` with `Config(retries=...)` | SigV4, checksums, retries |
| Bucket/key bootstrap | Init scripts calling `garage layout/key/bucket` | `--single-node --default-bucket` + `GARAGE_DEFAULT_*` env | Built-in, idempotent (verified) |
| Language detection | `langdetect`/fastText dependency or an LLM judge | 10-line Cyrillic ratio (D-16) | D-16 says cheap deterministic check |

**Key insight:** The hard parts here are LangGraph's fan-out semantics (partial-view routers, sibling cancellation, reducer-on-input). They are subtle and were each confirmed empirically. Stick to the verified shapes rather than inventing orchestration.

## Runtime State Inventory

This phase refactors the graph state schema and node topology.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **Postgres `checkpoints` tables:** 29 distinct thread_ids with Phase-2-shaped `GraphState` (fields `solution`, `review`, … and the linear node names). **`tasks` table:** 10 `completed` rows whose `result` has the Phase 2 shape (`analysis/approaches/solution/python_execution/...`); 15 stuck `analyzing_problem`, 21 `queued`, 16 `failed`, 0 `awaiting_clarification` [VERIFIED: read-only `psql` query on dev DB] | No data migration. There are no paused tasks, so nothing needs to resume on the new graph. Document that pre-Phase-3 `completed` rows have the old `result` shape (Phase 4 UI should tolerate `result.editorial` missing). The stuck/queued rows are dev/test leftovers |
| Live service config | Garage dev instance has no bucket/key yet [VERIFIED] | Compose change (Pattern 8). Recreate the garage container with the new flags/env. The existing meta volume already has a single-node layout, which is compatible |
| OS-registered state | None. Services run under docker compose only [VERIFIED: `docker ps`] | None |
| Secrets/env vars | New: `GARAGE_ACCESS_KEY_ID`, `GARAGE_SECRET_ACCESS_KEY`, `GARAGE_BUCKET`, `GARAGE_REGION`. `GARAGE_ENDPOINT` already exists in `.env.example` (empty) | Add to `.env.example`, `docker-compose.yml` (garage + worker) and `Settings` |
| Build artifacts | **The repo `.venv` is broken.** It contains only `lib 2/` and `lib 3/` (Finder-duplicate-style dirs, no `bin/`), and `uv run` fails with "not a valid Python environment" [VERIFIED: `ls -la .venv`, `uv run python --version`]. Worker/API Docker images need a rebuild after `uv add boto3` | Wave 0: recreate the venv (`rm -rf .venv && uv sync`, with human confirmation), then rebuild images (`docker compose build worker api`) |

## Common Pitfalls

### Pitfall 1: Router on the fan-out node fires per branch
**What goes wrong:** `failed` and `writer` both run, or the writer runs with a partial outcome set.
**Why it happens:** Branch functions are evaluated per task with that task's writes over the pre-superstep state (probe5).
**How to avoid:** Pattern 3 (plain edge → join node → router).
**Warning signs:** The writer is invoked twice, or a FAILED task also has a result.

### Pitfall 2: One branch's exception kills the whole task
**What goes wrong:** A Code Generator `ValueError` (D-00f) in the brute-force branch cancels the optimized branch, and the task fails with `UNHANDLED_EXCEPTION`.
**How to avoid:** Pattern 2 wrapper. Re-raise `GraphBubbleUp`. Never catch `BaseException`.
**Warning signs:** A sibling branch's last log line shows it cancelled mid-node.

### Pitfall 3: Reducer applied to graph input on re-invocation
**What goes wrong:** `solve_problem` always passes `initial_state` (not `None`). On taskiq redelivery for an existing `thread_id`, the input is *reduced into* the checkpointed channels, so an `operator.add` outcome list would carry stale outcomes.
**How to avoid:** Use a dict-by-index reducer, plus `Overwrite({})` in the strategist (verified).

### Pitfall 4: `mock_pipeline_openai` side_effect ordering breaks under parallelism
**What goes wrong:** `tests/conftest.py` feeds a *positional* `side_effect` list (analysis, approaches, solver, codegen, tests, review). With 2+ parallel branches, calls interleave nondeterministically.
**How to avoid:** Use the dispatch-by-`response_format.__name__` pattern already used in `tests/graph/test_correction_loop.py`. For per-branch responses, key on the approach name found in `kwargs["messages"]`. Add an `EditorialDraft` canned response.
**Warning signs:** Flaky `AttributeError` on the wrong parsed type.

### Pitfall 5: Checkpoint and executor contention with N branches
**What goes wrong:**
- The executors use fresh temp dirs per run, including a fresh `GOCACHE` [VERIFIED: `tools/go_executor/subprocess_backend.py:118-137` uses `tempfile.TemporaryDirectory()` and `gocache = tmp / "gocache"`]. Parallel runs are therefore filesystem-isolated, but every Go build recompiles the runtime (about 3s CPU; see `_GO_TIMEOUT_S` note in `graph/build.py:38-42`). 3 branches × concurrent tasks can starve CPU and cause spurious Go build timeouts (false verification failures).
- The Postgres pool defaults to 4 connections [VERIFIED: `psycopg_pool/pool_async.py:55-56` `min_size: int = 4, max_size: int | None = None`, and `base.py:120` `max_size = min_size`].
**How to avoid:**
- Add a process-wide `asyncio.Semaphore(settings.executor_max_concurrency)` (default 4 [ASSUMED]) around both execute nodes.
- Optionally raise the pool `max_size` to ~10.
- Parallel runs of the same task share uid 65534 and can signal each other. That is already an accepted residual risk (`tools/process.py` TRUST MODEL item 4).
- No change is needed for OpenAI concurrency: 3 branches × 1 call at a time, and `call_structured` already backs off on 429.

### Pitfall 6: EDIT-05 has no data source today
**What goes wrong:** `ReviewResult` has no "handled edge cases" field [VERIFIED: `src/algorunner/schemas/review.py:29-33`: `passed: bool`, `issues: list[Issue]`, `required_changes: list[str]`, `complexity_reasoning: str = Field(..., min_length=1)`].
**How to avoid:** Add `handled_edge_cases: list[str] = Field(default_factory=list)` and prompt the Reviewer to list the edge cases it confirmed the solution handles, cross-referenced with the tests. The OpenAI strict schema still marks it required and emits no default [VERIFIED: `openai.lib._pydantic.to_strict_json_schema` output lists it in `required`]. Existing Python fixtures that omit it stay valid. The deterministic `_execution_failure_review` gets `[]`.

### Pitfall 7: EDIT-06 loses the clarification question
**What goes wrong:** `clarification_gate_node` stores only the latest `clarification_answer`, overwriting the previous round's answer [VERIFIED: `src/algorunner/graph/build.py:81-85`]. The re-run analyzer overwrites `analysis` (and its `clarification_question`). Postgres clears `clarification_question` on resume. So the Writer cannot restate "question → answer".
**How to avoid:** Add `clarifications: list[dict]`. The gate appends `{"question": state["analysis"].clarification_question, "answer": answer}` in plain-append style. Pass it plus `assumption_stated` to the Writer. Fence the user-supplied answer as DATA (T-02-07-01 pattern).

### Pitfall 8: Writer rewrites complexity inconsistently with the reviewed claim
**What goes wrong:** The Writer is given English `complexity_time` such as "O(n), one pass…" and may output a different Big-O in Russian.
**How to avoid:** The prompt says "copy the Big-O notation exactly as given". Optionally add a deterministic check that each `O(...)` token from `Solution.complexity_time/space` appears in the Writer's field, sharing the single retry [ASSUMED optional].

### Pitfall 9: `run_approach` deadline arithmetic when `context is None`
**What goes wrong:** Tests invoke without a context, so `runtime.context` is `None` (verified) and an `AttributeError` breaks every existing graph test.
**How to avoid:** Every context consumer handles `None`: no deadline, no-op artifacts, no-op status.

## Code Examples

### Fan-out edge function
```python
# Source: langgraph/types.py Send docstring (installed 1.2.12) + probe_send.py
from langgraph.types import Send

def fan_out_approaches(state: GraphState) -> list[Send]:
    return [
        Send("run_approach", {
            "task_id": state["task_id"], "approach_idx": i, "approach": a,
            "problem_text": state["problem_text"], "examples": state["examples"],
            "analysis": state["analysis"], "assumption_stated": state["assumption_stated"],
            "max_iterations": state["max_iterations"],
        })
        for i, a in enumerate(state["approaches"])
    ]
# builder.add_node("run_approach", run_approach, input_schema=ApproachInput)
```

### Worker invocation changes
```python
deadline = time.monotonic() + remaining
ctx = PipelineContext(deadline_monotonic=deadline, editorial_reserve_s=settings.editorial_reserve_s,
                      artifacts=get_artifact_store(), status_sink=_pg_status_sink)
config = {"configurable": {"thread_id": task_id},
          "recursion_limit": 8 * settings.max_iterations + 30}
await asyncio.wait_for(graph.ainvoke(payload, config, context=ctx, durability="sync"), timeout=remaining)
```
- The subgraph shares the same `recursion_limit` value but counts its own steps. The probe needed 7 for a 6-step subgraph under a 3-step parent, so the limit bounds the larger of the two, never the sum across branches [VERIFIED: probe2.py limits 4/6 → `GraphRecursionError`, 7 → OK].
- The branch uses 7 nodes per iteration × `max_iterations`, plus slack. The installed default is 10007 anyway [VERIFIED: `langgraph/_internal/_config.py:32`].
- A `GraphRecursionError` inside a branch is caught by the wrapper as `errored`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `config["configurable"]` for run-scoped deps | `context_schema` + `Runtime[Ctx]` (+ `get_runtime()`) | LangGraph 0.6/1.0 | Deps are not persisted into checkpoint metadata. They auto-propagate to subgraphs |
| Custom "reset" reducers | `langgraph.types.Overwrite` | Present in 1.2.12 | Clean reducer bypass |
| Only graph-level timeout | `add_node(..., timeout=TimeoutPolicy)` / `Send(..., timeout=...)` | Present in 1.2.12 [VERIFIED: `langgraph/types.py` `class TimeoutPolicy`, `Send.__init__(..., timeout=...)`] | Not used here. Its failure mode raises into the graph (not verified to isolate), so the explicit wrapper + `wait_for` is preferred |
| boto3 < 1.36 checksum behaviour | boto3 ≥ 1.36 default CRC checksums | 2025-01 | Works with Garage v2.4.1 for `put_object` with a bytes body [VERIFIED: probe, body round-trip equal] |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Cyrillic thresholds: aggregate 0.6, per-field 0.3 for fields ≥ 20 letters | Pattern 7 | False retries or English leakage; make them tunable |
| A2 | `editorial_reserve_s = 240`, Writer per-attempt timeout 100s | Patterns 9/10 | The Writer is cut off, so a verified task FAILS on GLOBAL_TIMEOUT |
| A3 | `executor_max_concurrency = 4` | Pitfall 5 | CPU starvation or needless queuing |
| A4 | New error code `APPROACH_PIPELINE_ERROR` when all branches errored | Pattern 12 | API contract naming; the user may prefer reusing `CORRECTION_LOOP_EXHAUSTED` |
| A5 | Garage key format must be `GK`+24 hex / 64-hex secret (the format that worked, others untested) | Pattern 8 | Garage refuses to start with other formats |
| A6 | Artifact write budget: botocore 3 attempts + 10s `wait_for` | Pattern 8 | Slow pipeline during a Garage outage |
| A7 | Tags stay the Strategist's `technique` strings, which may be English (e.g. "two pointers") | Pattern 6 | EDIT-01 purists may want Russian tags; the Writer could supply `tags_ru` instead |
| A8 | When the Writer fails validation twice (IDs mismatch / Cyrillic), the node raises and the task FAILS | Open Q1 | A verified task is lost, conflicting with the spirit of D-10 |
| A9 | Parent-level-only status transitions (no per-branch statuses) | Pattern 11 | Less granular progress until Phase 4 |

## Open Questions

1. **What happens after the second Writer failure (D-16 says "retry once" and stops there)?**
   - What we know: one retry is locked. Assembly validation (ID set) and the Cyrillic check can both fail.
   - What's unclear: whether to ship a non-Russian or partial article, or FAIL.
   - Recommendation: on a Cyrillic failure after the retry, ship anyway with a logged warning and an `editorial_language_check_failed: true` flag in `result`. On a structural (ID) failure, raise → FAILED with code `EDITORIAL_ASSEMBLY_FAILED`. Confirm with the user.
2. **Should FAILED tasks expose their Garage keys in Postgres?**
   - D-13/D-20 describe `result` for completed tasks. The trail is discoverable by the prefix `tasks/{task_id}/`.
   - Recommendation: leave `result` null on FAILED. The prefix is enough for v1.
3. **Crash-redelivery resume semantics.**
   - `solve_problem` re-invokes with input (a restart), not `None` (a resume). Pre-existing Phase 2 behaviour; out of scope.
   - Recommendation: keep as-is. The Overwrite reset + idempotent keys keep it safe.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | runtime | ✓ | 3.14.5 (`/opt/homebrew/bin/python3.14`) | — |
| uv | deps | ✓ | 0.8.3 | — |
| Repo `.venv` | pytest, `uv run` | ✗ (broken: `lib 2/`, `lib 3/`, no `bin/`) | — | `rm -rf .venv && uv sync` (Wave 0, human-confirm) |
| Docker + Compose | stack | ✓ | 27.4.0 / v2.31.0 | — |
| Postgres container | tests, checkpoints | ✓ running (healthy) | 18 | — |
| Redis container | broker | ✓ running | 8 | — |
| Garage container | DATA-02 | ✓ running, **no bucket/key** | v2.4.1 | Compose flags (Pattern 8) |
| Go toolchain (host) | Go executor tests | ✓ | go1.26.3 | Worker image has 1.27 |

**Missing dependencies with no fallback:** none.
**Missing with fallback:** repo venv (recreate); Garage bucket/key (compose provisioning).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth in v1 API (unchanged) |
| V3 Session Management | no | — |
| V4 Access Control | partial | Garage bucket is private (no website/anonymous access). Only the worker holds S3 credentials. The API does not need them (D-13) |
| V5 Input Validation | yes | Pydantic strict schemas for `ApproachList`/`EditorialDraft`, plus deterministic assembly validation (ID sets, cap). Artifact keys are built only from the UUID task_id and integer idx/iteration (no user text), so there is no key/path injection |
| V6 Cryptography | no (delegated) | SigV4 via boto3. Never hand-roll |
| V7 Error handling/logging | yes | D-18 warnings must not log credentials (log key + exception type, not client config). Truncate branch error strings (500 chars) before storing in Postgres |
| V8 Data protection | yes | Artifacts contain user problem text. Kept forever (D-21) in a private bucket. Garage credentials come from env/`.env`, with dev defaults only |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via problem_text / clarification answer reaching the Writer | Tampering | Same DATA-fencing framing as the existing prompts (T-02-03-01 / T-02-07-01). The Writer never controls code (D-12) |
| Writer smuggles code/HTML into prose fields | Tampering / XSS (Phase 4) | Phase 4 UI must render prose as text/sanitised Markdown. Code fields are only ever executed-and-verified strings |
| Checkpoint/Postgres bloat from N branches | DoS | Branch state is bounded by `max_iterations`. Heavy stdout/stderr lives in Garage. `result` holds only the editorial + keys |
| Garage outage stalls the pipeline | DoS | Bounded retries + `wait_for` per write, warn-and-continue (D-18) |
| Parallel generated code signalling sibling runs (shared uid 65534) | Tampering | Accepted v1 residual risk (`tools/process.py` TRUST MODEL #4). Per-run temp dirs verified |

## Sources

### Primary (HIGH confidence)
- Scratch venv built from `uv export --frozen` (langgraph 1.2.12, openai 3.19.0, psycopg-pool per lock). Probes:
  - `probe_send.py`: independence, checkpointer inheritance, isolation, `wait_for`, `Overwrite`, re-invoke.
  - `probe2.py`: recursion scope, unguarded sibling cancellation.
  - `probe3.py` / `probe4.py`: context propagation and `None` default.
  - `probe5.py`: per-branch router.
- Installed source: `langgraph/types.py` (`Send`, `TimeoutPolicy`, `Overwrite`), `langgraph/_internal/_config.py:32`, `langgraph/checkpoint/base/__init__.py` (`get_checkpoint_metadata`), `langgraph/checkpoint/serde/jsonplus.py` (msgpack allowlist is permissive by default), `openai/resources/chat/completions/completions.py`, `psycopg_pool/pool_async.py`.
- Throwaway `dxflrs/garage:v2.4.1` container + `boto3 1.43.101`: `--default-bucket` provisioning, restart idempotency, put/get UTF-8 round-trip, `IfNoneMatch` not enforced, 404/NoSuchBucket error codes.
- Repo files read this session: `graph/state.py`, `graph/build.py`, `graph/routing.py`, `worker/tasks.py`, `worker/broker.py`, `config.py`, `schemas/*.py`, `agents/*/node.py` + prompts, `storage/*.py`, `tools/process.py`, executors, `docker-compose.yml`, `docker/garage/garage.toml`, `docker/Dockerfile.worker`, `tests/conftest.py`, `tests/graph/*`.

### Secondary (MEDIUM confidence)
- Context7 `/langchain-ai/langgraph`: `ensure_config` explicit-coordinate behaviour, subgraph checkpointer modes (`test_subgraph_persistence.py`), `context_schema` example (`tests/test_runtime.py`).

### Tertiary (LOW confidence)
- WebSearch on boto3 1.36 checksum vs Garage (the results conflated trailer issues). Superseded by the live probe.
- The Garage S3 compatibility page (last updated 2022, no checksum info).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH. Versions come from `uv.lock`, and boto3 was verified live against Garage.
- Architecture (fan-out/join/isolation/context/reducers): HIGH. Every load-bearing claim was probed on the pinned version.
- Editorial schema / thresholds / time reserve: MEDIUM. These are design recommendations and tunables (see Assumptions).
- Pitfalls: HIGH. Pitfalls 1–3 and 9 were reproduced; 5–7 come from reading the repo source.

**Research date:** 2026-09-24
**Valid until:** 2026-10-24 (LangGraph is fast-moving. Re-run the probes if `langgraph` moves off 1.2.12)
