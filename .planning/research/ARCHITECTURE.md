# Architecture Research

**Domain:** Multi-agent LLM pipeline (LangGraph) generating verified algorithmic editorials, with FastAPI + taskiq + Postgres + Garage(S3) around it
**Researched:** 2026-09-22
**Confidence:** MEDIUM (LangGraph/taskiq API shapes from official repo docs/source via Context7, MEDIUM confidence; general architecture/layout guidance from web search, LOW-MEDIUM confidence — verify exact API calls against the installed LangGraph version at implementation time)

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│  API layer (FastAPI)                                                     │
│  ┌─────────────┐   ┌────────────────────┐                                │
│  │ POST /tasks │   │ WS /tasks/{id}/events│  (reads Postgres + subscribes │
│  └──────┬──────┘   └──────────┬─────────┘   to a Redis pub/sub channel   │
│         │ enqueue             │ status stream    the worker publishes to)│
├─────────┴─────────────────────┴───────────────────────────────────────────┤
│  Queue (taskiq + Redis broker/result backend)                            │
│         │                                                                 │
│  ┌──────┴───────────────────────────────────────────────────────────┐    │
│  │  Worker process: runs ONE compiled LangGraph StateGraph per task  │    │
│  │                                                                   │    │
│  │  [Problem Analyzer] → [Solution Strategist] ─┬→ Send fan-out →    │    │
│  │        (LLM, cheap)      (LLM, cheap)        │  per-approach:     │    │
│  │                                               │  [Solver(LLM)] →  │    │
│  │                                               │  [Code Gen(LLM)]→ │    │
│  │                                               │  [Test Gen(LLM)]→ │    │
│  │                                               │  [PyExecutor tool]│    │
│  │                                               │  [GoExecutor tool]│    │
│  │                                               │  [Reviewer(LLM)]  │    │
│  │                                               │     │pass │fail   │    │
│  │                                               │     │     └─loop─┘    │
│  │                                               │     ▼ (max 3-5x)      │
│  │                                        (reduce: list[Solution])       │
│  │                                                     │                 │
│  │                                          [Editorial Writer (LLM)]     │
│  │                                                     │                 │
│  │                                          [Finalizer] → END            │
│  └───────────────────────────────────────────────────────────────────┘    │
├────────────────────────────────────────────────────────────────────────────┤
│  Persistence                                                              │
│  ┌───────────────────┐  ┌─────────────────────┐  ┌──────────────────┐    │
│  │ PostgreSQL         │  │ PostgreSQL           │  │ Garage (S3)       │    │
│  │ task table         │  │ LangGraph checkpoints│  │ artifacts:        │    │
│  │ (source of truth   │  │ (thread_id=task_id,  │  │ ProblemAnalysis,  │    │
│  │  for status/result)│  │  resumable state)     │  │ Solution[], │    │
│  │                     │  │                       │  │ Editorial          │    │
│  └───────────────────┘  └─────────────────────┘  └──────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| FastAPI app | HTTP/WS boundary only: validate input, enqueue task, read task row for status, stream events | Thin route handlers; no LangGraph invocation happens in the request/response cycle |
| taskiq worker | Owns the actual LangGraph `.ainvoke()`/`.astream()` call for a task; only place LangGraph runs | One taskiq task = one LangGraph run per problem-solve request |
| LangGraph StateGraph | Fixed pipeline: bounded LLM reasoning nodes + deterministic tool nodes + bounded correction loop | Compiled once at process startup, reused across invocations with different `thread_id`s |
| Agent nodes (Analyzer, Strategist, Solver, Code Gen, Test Gen, Reviewer, Editorial Writer) | Each is a plain async function `(state) -> dict`, calling an LLM with `with_structured_output(PydanticModel)` | One node = one bounded LLM call; no node itself decides graph topology except via its return value/conditional edge |
| Deterministic tools (PythonExecutorTool, GoExecutorTool) | Run/compile generated code against tests; return a structured pass/fail result; **not** LLM-backed, not agents | Plain classes/functions behind a `Protocol`, called directly from a node wrapper, not via LLM tool-calling |
| Checkpointer (`AsyncPostgresSaver`) | Persists graph state per superstep so an interrupted run resumes at the last completed node | Configured once, passed to `builder.compile(checkpointer=...)`; `thread_id` = task_id |
| Task table (Postgres) | Source of truth for API-visible status or terminal result — independent of LangGraph's internal checkpoint format | Simple row: id, status, timestamps, error, result_ref |
| Garage (S3) | Large/structured intermediate artifacts (full ProblemAnalysis, all Solutions with code+tests+review history, final Editorial) — keeps Postgres rows small | Written by the Finalizer node (and optionally by earlier nodes for audit), referenced by key from the task row |

## Recommended Project Structure

Single `uv` package (not a workspace of multiple packages) is the right scale call here — see rationale below.

```
algorunner/
├── pyproject.toml              # single project, uv-managed
├── uv.lock
├── src/
│   └── algorunner/
│       ├── __init__.py
│       ├── config.py            # pydantic-settings: per-agent model config, env
│       ├── schemas/              # shared Pydantic models — the contracts between everything
│       │   ├── __init__.py
│       │   ├── problem.py        # ProblemAnalysis
│       │   ├── solution.py       # Solution, Approach, ComplexityAnalysis
│       │   ├── review.py         # ReviewResult, Issue, Severity
│       │   ├── editorial.py      # Editorial
│       │   ├── execution.py      # ExecutionResult (shared contract for tools, see below)
│       │   └── task.py           # TaskStatus enum, TaskRecord
│       ├── graph/                # the LangGraph wiring itself — thin, no business logic
│       │   ├── __init__.py
│       │   ├── state.py          # GraphState TypedDict (+ reducers)
│       │   ├── build.py          # StateGraph(...); add_node/add_edge/add_conditional_edges; compile()
│       │   └── routing.py        # conditional-edge functions (decide_to_retry, decide_after_review, fan-out Send builder)
│       ├── agents/                # one subpackage per LLM-backed node, matches product owner's layout hint
│       │   ├── problem_analyzer/
│       │   │   ├── node.py        # async def run(state) -> dict
│       │   │   └── prompts.py
│       │   ├── solution_strategist/
│       │   │   ├── node.py
│       │   │   └── prompts.py
│       │   ├── solver/            # generic solver, algorithm-agnostic prompt + few-shot strategy
│       │   │   ├── node.py
│       │   │   └── prompts.py
│       │   ├── code_generator/
│       │   ├── test_generator/
│       │   ├── reviewer/
│       │   └── editorial_writer/
│       ├── tools/                 # deterministic, non-LLM — separate top-level concern
│       │   ├── __init__.py
│       │   ├── base.py            # ExecutorProtocol + ExecutionResult contract
│       │   ├── python_executor/
│       │   │   ├── subprocess_backend.py   # v1: subprocess.run
│       │   │   └── __init__.py             # exports the Protocol-conforming implementation in use
│       │   ├── go_executor/
│       │   │   ├── subprocess_backend.py   # v1: go build && run
│       │   │   └── __init__.py
│       │   └── test_runner/       # shared harness for assembling code+tests before execution
│       ├── llm/                   # model client factory, per-agent model selection from config
│       │   ├── __init__.py
│       │   └── client_factory.py  # get_chat_model(agent_name: str) -> BaseChatModel
│       ├── storage/
│       │   ├── postgres.py        # task table CRUD, checkpointer connection setup
│       │   └── artifacts.py       # Garage/S3 client, put/get for ProblemAnalysis/Solution[]/Editorial
│       ├── api/                   # FastAPI app — thin
│       │   ├── main.py
│       │   ├── routes/
│       │   │   ├── tasks.py       # POST /api/v1/tasks, GET /api/v1/tasks/{id}
│       │   │   └── events.py      # WS /api/v1/tasks/{id}/events
│       │   └── dependencies.py
│       └── worker/                 # taskiq broker + task definitions
│           ├── broker.py           # taskiq broker instance (Redis)
│           └── tasks.py            # @broker.task async def solve_problem(task_id): builds+runs the graph
├── tests/
│   ├── agents/
│   ├── tools/
│   ├── graph/
│   └── api/
├── frontend/                       # React + TS app, separate from the Python package
└── docker-compose.yml
```

### Structure Rationale

- **Single package, not a `uv` workspace:** uv workspaces (multiple `pyproject.toml`s sharing one `uv.lock`) earn their cost when independently-versioned, independently-deployable units exist with genuinely different dependency needs (e.g., a CLI vs a web service vs a shared SDK published separately). Here, the API, the worker, and the graph all deploy together (same Docker image family, same `algorunner` import root), and there's a single Python dependency set with no version-conflict pressure (nothing needs `pydantic<2` while something else needs `>=2`). A workspace would add editable-install indirection and multiple `pyproject.toml`s to maintain for zero practical benefit at this scale — this is squarely "not suitable yet" per current uv workspace guidance. Revisit only if a genuinely separate deployable (e.g. a standalone CLI or a public SDK) emerges later.
- **`schemas/` is the real contract layer:** because the architecture is explicitly "simple modular, not DDD," there's no separate domain/application/infrastructure layering — instead, the Pydantic models in `schemas/` are what everything (agents, tools, API, worker) imports and agrees on. This is where "maximum feasible type safety" actually lives.
- **`agents/<name>/` matches the product owner's explicit layout hint** and keeps each agent's prompt template colocated with its node function — a reviewer editing one agent's behavior touches one directory.
- **`tools/` is a hard boundary, not a convenience grouping:** each executor exposes only the `ExecutorProtocol` from `tools/base.py`; the subprocess implementation is an interchangeable detail. This is what makes the "swap subprocess for sandbox later without touching agent code" requirement actually hold — see Pattern 3 below.
- **`graph/` stays thin on purpose:** it should contain wiring only (`add_node`, `add_conditional_edges`, `compile`) and routing predicates, never business logic — so the graph shape (the architecturally-locked part) is reviewable in one file (`build.py`) independent of what each node does internally.
- **`api/` and `worker/` are separate top-level packages, not layers under a `services/` folder:** this matches "simple modular": each is a deployable entrypoint (`uvicorn algorunner.api.main:app` vs `taskiq worker algorunner.worker.broker:broker`) that both import the same `graph`, `agents`, `tools`, `schemas` — no circular dependency risk because `graph`/`agents`/`tools` never import from `api` or `worker`.

## Architectural Patterns

### Pattern 1: Bounded correction loop via in-state counter + conditional edge

**What:** A `max_iterations` cap enforced by graph *state*, not by prompt instruction. The retrying node increments a counter on every pass; the router reads both the Reviewer's `passed` flag and the counter to decide `END`/`FAILED` vs. loop back.

**When to use:** Any node sequence where an LLM step can produce output that a later step judges as unacceptable, and you need a deterministic, testable stopping guarantee — this is exactly the Reviewer → Solver correction loop.

**Trade-offs:** Requires the state schema to carry loop-control fields (`iterations: int`, `review_history: list[ReviewResult]`) that are otherwise pure plumbing. Upside: the stopping behavior is verifiable by unit-testing the router function directly with synthetic state, with no LLM call involved.

**Example (LangGraph 1.0 API shape — verify against installed version):**
```python
from langgraph.graph import StateGraph, START, END

class GraphState(TypedDict):
    iterations: int
    review: ReviewResult | None
    # ... other fields

MAX_ITERATIONS = 5

def decide_after_review(state: GraphState) -> str:
    if state["review"] and state["review"].passed:
        return "editorial_writer"
    if state["iterations"] >= MAX_ITERATIONS:
        return "failed"
    return "solver"  # loop back to the Solver, not restart from Analyzer

builder = StateGraph(GraphState)
builder.add_node("solver", solver_node)          # increments iterations in its return dict
builder.add_node("reviewer", reviewer_node)
builder.add_node("editorial_writer", editorial_writer_node)
builder.add_node("failed", failed_node)
builder.add_edge("solver", "reviewer")
builder.add_conditional_edges("reviewer", decide_after_review, {
    "editorial_writer": "editorial_writer",
    "solver": "solver",
    "failed": "failed",
})
```
This mirrors LangGraph's own reference "code assistant" example (`decide_to_finish` checking `error == "no" or iterations == max_iterations`) — the pattern is stable across LangGraph versions since it relies only on core `TypedDict` state + `add_conditional_edges`, not on newer APIs.

**Note on `Command` as an alternative:** a node can also return `Command(goto="solver", update={...})` instead of relying on a separate conditional-edge function — this fuses "update state" and "route" into one return value from inside the Reviewer node itself. Either shape is valid in LangGraph 1.0; `Command` is arguably cleaner when the routing decision needs to be very close to the state update logic (e.g., the Reviewer node itself decides where to go), while `add_conditional_edges` is cleaner when the routing predicate is independent from any single node's logic. **Verify current recommended idiom against the installed LangGraph version's docs before locking this in during phase planning** — this is an area LangGraph has actively evolved (Command was introduced specifically to unify the multi-agent handoff and conditional-edge mechanisms).

### Pattern 2: Structured LLM output at every agent-node boundary

**What:** Every LLM-backed node uses `llm.with_structured_output(PydanticModel)` (or the equivalent bound tool-calling schema) so the node's return value is already a validated Pydantic instance, never raw text to be parsed downstream.

**When to use:** Every node that must hand a well-typed object to the next node or to the graph state (ProblemAnalysis, list of proposed Approaches, ReviewResult, Editorial).

**Trade-offs:** Requires picking a strong-enough model for nodes with more complex schemas (the Strategist proposing several structured `Approach` objects is a heavier structured-output task than the Reviewer's simpler `ReviewResult`) — this is exactly why per-agent model configuration (cheap vs strong) matters, not just for cost but because structured-output reliability scales with model capability.

**Example:**
```python
class ReviewResult(BaseModel):
    passed: bool
    issues: list[Issue]
    severity: Severity
    required_changes: list[str]

reviewer_llm = get_chat_model("reviewer")  # cheap model, from per-agent config
structured_reviewer = reviewer_llm.with_structured_output(ReviewResult)

async def reviewer_node(state: GraphState) -> dict:
    result: ReviewResult = await structured_reviewer.ainvoke(build_review_prompt(state))
    return {
        "review": result,
        "review_history": state["review_history"] + [result],
        "iterations": state["iterations"] + 1,
    }
```

### Pattern 3: Protocol boundary for deterministic tools (subprocess → sandbox swap)

**What:** Deterministic execution tools are called through a `Protocol` (structural typing, no inheritance required) that defines exactly one method returning one structured result type. Agent/graph code never imports `subprocess`, `docker`, or any backend-specific type directly — only the Protocol and the result schema.

**When to use:** Any tool whose implementation is expected to change (subprocess now, sandboxed/Docker or an isolated microservice later) without agent-facing code changes — this is an explicit architectural requirement, not speculative.

**Trade-offs:** Slight indirection cost (one extra factory function to get "the configured executor"). Strong payoff: the swap from subprocess to sandbox becomes a config/DI change (`get_python_executor() -> PythonExecutorProtocol`), not a refactor touching the Code Generator, Test Generator, or Reviewer nodes.

**Example:**
```python
# tools/base.py
from typing import Protocol
from algorunner.schemas.execution import ExecutionResult

class CodeExecutor(Protocol):
    async def run(self, code: str, tests: str, *, timeout_s: float) -> ExecutionResult: ...

# schemas/execution.py
class ExecutionResult(BaseModel):
    passed: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    failed_test_names: list[str] = []

# tools/python_executor/subprocess_backend.py
class SubprocessPythonExecutor:  # structurally satisfies CodeExecutor, no explicit inheritance needed
    async def run(self, code: str, tests: str, *, timeout_s: float) -> ExecutionResult:
        ...  # subprocess.run(...) today; swap this file's internals for a Docker/sandbox
             # call later — CodeExecutor and ExecutionResult stay identical.

# tools/python_executor/__init__.py
def get_python_executor() -> CodeExecutor:
    return SubprocessPythonExecutor()  # later: return SandboxedPythonExecutor()
```
The node wrapper that calls this tool from inside the graph is a thin adapter (`async def python_executor_node(state) -> dict: result = await get_python_executor().run(...); return {"python_execution": result}`) — it is a **node in the graph but contains no LLM call**, matching the "deterministic tool, not an agent" requirement precisely.

## Data Flow

### Request Flow

```
[POST /api/v1/tasks] → validate input → write Task row (status=queued) → Postgres
    → enqueue via taskiq (.kiq()) → return 202 {task_id, status: queued}

[taskiq worker picks up task] → update Task row (status=analyzing_problem)
    → graph.ainvoke(initial_state, config={"configurable": {"thread_id": task_id}})
    → after each node completes, worker publishes a status event (Redis pub/sub or
      directly updates the Task row, which the WS handler polls/subscribes to)
    → on graph completion: write final Editorial to Garage, update Task row
      (status=completed, result_ref=<garage key>)
    → on failure/max_iterations exceeded: update Task row (status=failed, error=...)

[GET /api/v1/tasks/{id}] → read Task row → return current status/result
[WS /api/v1/tasks/{id}/events] → stream status transitions as they're written
```

### Key Data Flows

1. **Status propagation:** the Task row in Postgres is the single source of truth for API-visible status — it is deliberately decoupled from LangGraph's internal checkpoint state (which is an implementation detail for resumability, not a status API). Each node (or a lightweight wrapper around every node) writes a status transition after completing.
2. **Correction loop data accumulation:** `review_history: list[ReviewResult]` (or similar) accumulates across loop iterations in graph state so the Solver, when it re-runs, receives the *specific* prior issues rather than restarting from a blank slate — this is what "not starting over" requires structurally (see Pitfalls below).
3. **Artifact persistence:** the Finalizer node (or a small persistence step after each major node) writes structured objects (ProblemAnalysis, Solution[], Editorial) to Garage; the Task row stores only a reference key, keeping Postgres rows small and Garage as the artifact system of record — matches the requirement.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Solo/small user base (this milestone) | Single worker process, single Postgres instance, single Redis, single Garage node — Docker Compose as specified. This is entirely adequate. |
| Moderate concurrent tasks | Scale taskiq worker replicas horizontally (stateless workers reading from the same Redis broker); Postgres connection pooling matters before Postgres itself becomes a bottleneck. |
| High concurrency / many parallel fan-out branches per task | The Send-based fan-out (Pattern in Q3 below) means a single task can spawn N parallel LLM calls + N parallel subprocess executions; watch OpenAI rate limits and subprocess/CPU contention on the worker host before Postgres/Redis become the bottleneck — this is the more likely first constraint than raw request volume. |

### Scaling Priorities

1. **First bottleneck:** OpenAI API rate limits / cost when several solution approaches fan out in parallel per task, each with its own Solver + Code Generator + Reviewer LLM calls. Mitigate with per-agent model tiering (cheap model for Analyzer/Reviewer, strong only for Solver/Editorial Writer) — already an architectural decision — and with the existing "global timeout + retry with backoff" requirement.
2. **Second bottleneck:** subprocess execution contention on the worker host once Go compilation + Python execution run concurrently across fan-out branches and across multiple in-flight tasks. This is precisely the pressure that motivates the "must be swappable to sandboxed/isolated execution service" requirement — the Protocol boundary (Pattern 3) is what makes addressing this later cheap.

## Anti-Patterns

### Anti-Pattern 1: LLM-driven dynamic routing (supervisor pattern) for this pipeline

**What people do:** Give an LLM "supervisor" node the graph's edge list as tools and let it decide at runtime which node to call next.
**Why it's wrong:** Already explicitly rejected by the product owner for this project (non-deterministic control flow, harder to test, harder to bound cost/latency, harder to reason about correctness guarantees) — but worth naming because it's the default pattern most LangGraph tutorials reach for, and it would be easy to accidentally reintroduce inside a single node (e.g., letting the Solver decide via free-form reasoning whether to call the Reviewer again).
**Do this instead:** Keep all control flow in `add_conditional_edges`/`Command(goto=...)` functions that are plain Python, driven by structured state fields (counters, `passed` booleans) — never by an LLM inventing the next node name.

### Anti-Pattern 2: Prompt-only iteration limits ("please don't retry more than 3 times")

**What people do:** Tell the LLM in its prompt not to loop more than N times, or rely on the model to "know" it already tried a fix.
**Why it's wrong:** LLMs have no reliable memory of "how many times has this happened" unless it's explicitly in the input; this produces either premature termination or true infinite loops (LangGraph's default `recursion_limit=25` will eventually kill it, but that's a crash, not a graceful `FAILED` result) — a known, documented pitfall.
**Do this instead:** Enforce `max_iterations` as a plain integer comparison in the conditional-edge/router function, reading from graph state — exactly Pattern 1 above. Recursion-limit errors should never fire in normal operation; they're a safety net, not the mechanism.

### Anti-Pattern 3: Business logic living in `graph/build.py`

**What people do:** Put prompt construction, LLM calls, or tool invocation logic directly inside the functions passed to `add_node`, defined inline in the graph-building module.
**Why it's wrong:** Makes the graph topology (the architecturally-reviewed, locked part) hard to read at a glance, and makes individual agents hard to unit-test without spinning up the whole graph.
**Do this instead:** Keep `graph/build.py` to wiring only; each node is a one-line reference to a function imported from `agents/<name>/node.py` or `tools/<name>/`.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| OpenAI API | Per-agent `ChatOpenAI`-style client instances built by a small factory (`llm/client_factory.py`) reading model name from config per agent | Retry/backoff on timeout/rate-limit is a stated requirement — implement at the client-factory or LangChain-client level, not scattered per node |
| PostgreSQL | Two logical uses: (1) task-state table via a plain async driver/ORM, (2) LangGraph `AsyncPostgresSaver` for checkpoints | These can share one Postgres instance/database; checkpoint tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`) are created by the checkpointer's own `setup()` — don't hand-roll migrations for them |
| Redis | taskiq broker + result backend; optionally pub/sub channel for WS status fan-out | `taskiq-redis` is the maintained integration package; confirm exact broker class name against installed version at implementation time |
| Garage (S3-compatible) | Any S3-compatible client (e.g. `boto3`/`aioboto3`) pointed at Garage's endpoint | Treat as opaque object storage — write/read JSON-serialized Pydantic model dumps keyed by `task_id/artifact_type` |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `api/` ↔ `worker/` | Indirect, via taskiq broker (Redis) + shared Postgres task table | API never imports `graph/`; API and worker share only `schemas/`, `storage/`, `config.py` |
| `graph/` ↔ `agents/*` | Direct function import (`add_node("solver", solver_node)`) | One-directional: agents never import from `graph/` |
| `graph/` ↔ `tools/*` | Direct function import, tool call wrapped in a thin node adapter | Node adapter is where "tool as a graph node, not an agent" boundary is enforced |
| Any node ↔ `schemas/` | Every node's return dict and every tool's return type is a `schemas/` Pydantic model | This is the actual seam that keeps modules decoupled in the absence of DDD layering |

## Sources

- LangGraph official repo (`langchain-ai/langgraph`) code-assistant example, `add_conditional_edges`/`decide_to_finish`/`iterations` retry-loop pattern — via Context7, MEDIUM confidence: https://github.com/langchain-ai/langgraph/blob/main/examples/code_assistant/langgraph_code_assistant_mistral.ipynb
- LangGraph `Command` dataclass source (`langgraph/types.py`) — via Context7, MEDIUM confidence: https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/types.py
- LangGraph `Send` map-reduce fan-out docstring/example (`langgraph/types.py`) — via Context7, MEDIUM confidence
- LangGraph `AsyncPostgresSaver` README and migrations source — via Context7, MEDIUM confidence: https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-postgres/README.md
- `with_structured_output` usage examples (RAG/CRAG cookbooks) — via Context7, MEDIUM confidence
- `taskiq-fastapi` README/docs (FastAPI dependency reuse in tasks, broker startup guard against worker-process recursion) — via Context7, MEDIUM confidence: https://github.com/taskiq-python/taskiq-fastapi
- LangGraph 1.0 release (Oct 2025, no breaking changes to core graph primitives) — via WebSearch, LOW confidence, cross-referenced across multiple sources: https://blog.langchain.com/langchain-langgraph-1dot0/ , https://github.com/langchain-ai/langgraph/releases
- LangGraph infinite-loop / correction-loop pitfalls (state must change to break routing conditions, `recursion_limit` default 25, "logical rut" repeated failures) — via WebSearch, LOW confidence: https://theneuralbase.com/langgraph/qna/fix-langgraph-infinite-loop/ , https://theneuralbase.com/agents/errors/langgraph-graph-recursion-error/ , https://rajatpandit.com/ai-engineering/optimizing-langgraph-cycles/
- `uv` workspaces guidance and when they are/aren't appropriate — via WebSearch, LOW confidence: https://docs.astral.sh/uv/concepts/projects/workspaces/ , https://pydevtools.com/handbook/how-to/how-to-set-up-a-python-monorepo-with-uv-workspaces/
- Protocol-based swappable execution backend pattern (subprocess/local vs sandboxed/Docker) — via WebSearch, LOW confidence, general pattern confirmed across multiple independent sources, not project-specific: https://dev.to/leland_fy/stop-writing-docker-wrappers-for-your-ai-agents-code-execution-1c5b

**Version-sensitivity flag for implementation time:** confirm the exact `add_conditional_edges` signature, whether `Command` vs conditional-edge-function is the currently-recommended idiom for this specific correction-loop shape, and the exact `AsyncPostgresSaver`/`taskiq-redis` broker class names/import paths against whatever LangGraph, `langgraph-checkpoint-postgres`, and `taskiq-redis` versions get pinned in `pyproject.toml` — these were confirmed against LangGraph 1.0 (Oct 2025 GA) source/docs but should not be assumed frozen without a quick check against the installed version's changelog.

---
*Architecture research for: AlgoRunner (multi-agent LangGraph pipeline for algorithmic problem editorials)*
*Researched: 2026-09-22*
