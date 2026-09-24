# Phase 2: Verified Single-Solution Core Pipeline - Pattern Map

**Mapped:** 2026-09-23
**Files analyzed:** 34 (new + modified)
**Analogs found:** 28 in-repo / 34 (6 fall back to RESEARCH.md verified reference code — no in-repo precedent exists yet for LLM-call nodes, executor tools, or the routing/client-factory shapes)

## Repository State Note

Phase 1 shipped a real (non-greenfield) codebase this time: `src/algorunner/{schemas,graph,worker,storage,api,config.py}` all exist and are git-tracked. Phase 2 is the first phase where **in-repo analogs are the primary source**, not `RESEARCH.md` — every "Established Pattern" file (`schemas/task.py`, `graph/build.py`, `worker/tasks.py`, `storage/tasks.py`, `storage/postgres.py`, `api/routes/tasks.py`, `config.py`, `worker/broker.py`, `migrations/0001_create_tasks_table.sql`, `docker/Dockerfile.worker`, `docker-compose.yml`, `tests/conftest.py`, `tests/graph/test_build.py`, `tests/worker/test_tasks.py`, `tests/api/test_tasks.py`) was read directly this session and is quoted below with line numbers. Only genuinely new *roles* (LLM-call agent nodes, deterministic executor tools, the routing conditional-edge function, and the OpenAI client factory) have no in-repo precedent and fall back to `02-RESEARCH.md`'s verified Architecture Patterns/Code Examples — each such case is called out explicitly.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/algorunner/schemas/problem.py` | model | request-response | `src/algorunner/schemas/task.py` | exact (same file, same schema conventions) |
| `src/algorunner/schemas/solution.py` | model | request-response | `src/algorunner/schemas/task.py` | exact |
| `src/algorunner/schemas/review.py` | model | request-response | `src/algorunner/schemas/task.py` | exact |
| `src/algorunner/schemas/execution.py` | model | request-response | `src/algorunner/schemas/task.py` | exact |
| `src/algorunner/schemas/clarification.py` | model | request-response | `src/algorunner/schemas/task.py` (`TaskCreateResponse`) | exact |
| `src/algorunner/agents/problem_analyzer/node.py` | service (LLM reasoning node) | transform | `src/algorunner/graph/build.py` (`stub_node`) + RESEARCH.md Pattern 1 | role-match (node shape) + RESEARCH fallback (LLM call body) |
| `src/algorunner/agents/solution_strategist/node.py` | service | transform | same as above | role-match + RESEARCH fallback |
| `src/algorunner/agents/solver/node.py` | service | transform | same as above | role-match + RESEARCH fallback |
| `src/algorunner/agents/code_generator/node.py` | service | transform | same as above | role-match + RESEARCH fallback |
| `src/algorunner/agents/test_generator/node.py` | service | transform | same as above | role-match + RESEARCH fallback |
| `src/algorunner/agents/reviewer/node.py` | service | transform | same as above | role-match + RESEARCH fallback |
| `src/algorunner/agents/*/prompts.py` (x6) | utility | transform | none in-repo | no analog — RESEARCH.md Pattern 1 message-building convention |
| `src/algorunner/tools/base.py` | utility (Protocol) | — | none in-repo | no analog — RESEARCH.md Pattern 3 |
| `src/algorunner/tools/python_executor/subprocess_backend.py` | utility (file-I/O + subprocess) | file-I/O | none in-repo | no analog — RESEARCH.md Pattern 3 (verified stdlib facts) |
| `src/algorunner/tools/go_executor/subprocess_backend.py` | utility (file-I/O + subprocess) | file-I/O | none in-repo | no analog — RESEARCH.md Pattern 3 + Pitfall 3/11 |
| `src/algorunner/llm/client_factory.py` | provider | request-response | `src/algorunner/storage/postgres.py` (`get_pool`) + `src/algorunner/worker/broker.py` (module-level singleton) | role-match |
| `src/algorunner/llm/retry.py` | utility | request-response | none in-repo | no analog — RESEARCH.md Pattern 1 retry wrapper (`tenacity`) |
| `src/algorunner/graph/state.py` | model (TypedDict) | event-driven | itself (Phase 1 `StubGraphState`) | exact — same file, REPLACE |
| `src/algorunner/graph/build.py` | service | event-driven | itself (Phase 1 stub wiring) | exact — same file, REPLACE/EXTEND |
| `src/algorunner/graph/routing.py` | utility (conditional-edge fn) | transform | `src/algorunner/graph/build.py` (`stub_node`'s `if FAIL_TEST_MARKER...` branch) | role-match (only existing state-branching logic) |
| `src/algorunner/worker/tasks.py` | controller | event-driven | itself (`solve_problem_stub`) | exact — same file, EXTEND |
| `src/algorunner/storage/tasks.py` | service | CRUD | itself (`update_task_status`/`update_task_completed`/`update_task_failed`) | exact — same file, EXTEND |
| `src/algorunner/config.py` | config | — | itself | exact — same file, EXTEND |
| `src/algorunner/api/routes/tasks.py` | controller | request-response | itself (`create_task`/`get_task_status`) | exact — same file, EXTEND |
| `migrations/0002_add_clarification_columns.sql` | migration | batch | `migrations/0001_create_tasks_table.sql` | exact |
| `docker/Dockerfile.worker` | config | — | itself + `docker/Dockerfile.api` | exact — same file, EXTEND |
| `docker-compose.yml` | config | — | itself | exact — same file, EXTEND |
| `tests/conftest.py` | test | request-response | itself | exact — same file, EXTEND (new OpenAI-mock fixture) |
| `tests/agents/test_*.py` (x6) | test | transform | `tests/worker/test_tasks.py` (monkeypatch convention) | role-match |
| `tests/tools/test_executors.py` | test | file-I/O | `tests/graph/test_build.py` (real-infra integration test convention) | role-match |
| `tests/graph/test_clarification.py` | test | event-driven | `tests/graph/test_build.py` | exact |
| `tests/graph/test_correction_loop.py` | test | event-driven | `tests/graph/test_build.py` | exact |
| `tests/graph/test_global_timeout.py` | test | event-driven | `tests/graph/test_build.py` | exact |
| `tests/llm/test_client_factory.py`, `tests/llm/test_retry.py` | test | request-response | `tests/api/test_tasks.py` (plain assertion style) | role-match |
| `tests/api/test_clarification.py` | test | request-response | `tests/api/test_tasks.py` | exact |

## Pattern Assignments

### `src/algorunner/schemas/problem.py`, `solution.py`, `review.py`, `execution.py`, `clarification.py` (model, request-response)

**Analog:** `src/algorunner/schemas/task.py` (entire file, 73 lines)

**Imports pattern** (lines 8-12):
```python
from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field
```

**Enum + BaseModel core pattern** (lines 15-28, `Language`/`Example`/`TaskSubmission`):
```python
class Language(str, Enum):
    EN = "en"
    RU = "ru"

class Example(BaseModel):
    input: str
    output: str

class TaskSubmission(BaseModel):
    problem_text: str = Field(..., max_length=5000)
    language: Language
    examples: list[Example] = Field(default_factory=list, max_length=10)
```
Apply the same shape for `ProblemAnalysis`/`Approach`/`Solution`/`ReviewResult`/`Issue`/`ExecutionResult` — use `str, Enum` for closed vocabularies (or `Literal[...]` per RESEARCH.md's `IssueCategory`/`Severity` schema example, RESEARCH.md lines 559-560, which is the recommended shape for the new schemas since it needs no separate enum class), `Field(..., max_length=...)` for every free-text field that flows from/to an LLM or the client, matching the project's existing bound-everything discipline.

**Structured error shape reuse** (lines 51-55, `TaskError`):
```python
class TaskError(BaseModel):
    code: str
    message: str
```
Phase 2's pipeline failures (correction-loop exhaustion, global timeout) MUST reuse this exact `TaskError` class from `schemas/task.py` — do not create a second error shape (01-CONTEXT.md D-07, carried forward per 02-CONTEXT.md canonical refs).

**Response schema pattern** (lines 70-72, `TaskCreateResponse`):
```python
class TaskCreateResponse(BaseModel):
    task_id: UUID
    status: TaskStatus
```
`schemas/clarification.py`'s `ClarificationQuestion`/`ClarificationAnswer` should follow this exact minimal-response-model shape (RESEARCH.md's own sketch at RESEARCH.md lines 328-343 confirms `ClarificationQuestion(question=...)`/`ClarificationAnswer` as the expected pair).

---

### `src/algorunner/agents/{problem_analyzer,solution_strategist,solver,code_generator,test_generator,reviewer}/node.py` (service, transform)

**Analog (node-shape structural precedent):** `src/algorunner/graph/build.py` lines 17-28 (`stub_node`)
```python
async def stub_node(state: StubGraphState) -> dict:
    await asyncio.sleep(random.uniform(2, 5))
    if FAIL_TEST_MARKER in state["problem_text"]:
        return {"error": {"code": "SIMULATED_FAILURE", "message": "..."}}
    return {"result": {"message": "stub pipeline completed"}}
```
**What to copy:** every agent node is `async def name(state: GraphState) -> dict` returning a **plain partial-state dict update**, never mutating `state` in place — this is the one graph-node convention already established in-repo. Keep the file/module boundary the same as Phase 1's single-node file did (one node per file here, since there are 6 distinct nodes vs. Phase 1's 1).

**No in-repo analog for the LLM-call body itself** — fall back to `02-RESEARCH.md` Pattern 1 (RESEARCH.md lines 236-291), verified against Context7's official `/openai/openai-python` `helpers.md`:
```python
# llm/client_factory.py
from functools import lru_cache
from openai import AsyncOpenAI
from algorunner.config import settings

@lru_cache
def get_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)

def model_for(agent_name: str) -> str:
    return getattr(settings, f"{agent_name}_model", settings.default_model)

# agents/reviewer/node.py
async def reviewer_node(state: "GraphState") -> dict:
    completion = await get_client().chat.completions.parse(
        model=model_for("reviewer"),
        messages=build_review_messages(state),
        response_format=ReviewResult,
    )
    message = completion.choices[0].message
    if message.parsed is None:
        raise ValueError(f"Reviewer refused or failed to parse: {message.refusal}")
    result = message.parsed
    return {
        "review": result,
        "review_history": state["review_history"] + [result],  # plain append, no reducer
        "iterations": state["iterations"] + 1,
    }
```
Apply this exact `chat.completions.parse(response_format=PydanticModel)` + `message.parsed`/`message.refusal` check to all 6 nodes, swapping the schema/prompt-builder per node.

**History accumulation convention:** `state["review_history"] + [result]` — a **plain returned list**, not an `Annotated[list, add]` reducer (RESEARCH.md Pattern 4, lines 397-429 — deliberate, since `max_iterations` already bounds the list size and Phase 1 established no reducer precedent either — `graph/state.py`'s `StubGraphState` has zero `Annotated` fields).

---

### `src/algorunner/agents/*/prompts.py` (utility, transform)

**No in-repo analog.** Reference: RESEARCH.md Pattern 1's `build_review_messages(state)` call site (implied, RESEARCH.md line 264) and the Security Domain note (RESEARCH.md line 711/719): clearly delimit `problem_text`/user-provided `examples` as **data**, not instructions, in every prompt template — this is a new convention this phase establishes (prompt-injection mitigation), not something Phase 1 needed since it had no LLM calls at all.

---

### `src/algorunner/tools/base.py`, `tools/python_executor/subprocess_backend.py`, `tools/go_executor/subprocess_backend.py` (utility, file-I/O)

**No in-repo analog** — `src/algorunner/tools/` exists only as an empty `__init__.py` from Phase 1's INFRA-01 scaffold. Reference: `02-RESEARCH.md` Pattern 3 (RESEARCH.md lines 347-395), verified stdlib facts.

**Core pattern** (RESEARCH.md lines 353-393):
```python
import asyncio, os, resource, signal, tempfile
from pathlib import Path
from algorunner.schemas.execution import ExecutionResult

def _limit_resources():
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
    # deliberately NOT RLIMIT_FSIZE=0 — CLAUDE.md "What NOT to Use", SIGXFSZ footgun

class SubprocessPythonExecutor:
    async def run(self, code: str, tests: str, *, timeout_s: float = 10.0) -> ExecutionResult:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "solution.py"
            script.write_text(code + "\n\n" + tests)
            proc = await asyncio.create_subprocess_exec(
                "python3", str(script),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=tmp, start_new_session=True, preexec_fn=_limit_resources,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
            except asyncio.TimeoutError:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                await asyncio.sleep(0.5)
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await proc.wait()
                return ExecutionResult(passed=False, stdout="", stderr="timed out", exit_code=-1, duration_ms=int(timeout_s * 1000))
            return ExecutionResult(
                passed=proc.returncode == 0,
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                exit_code=proc.returncode,
                duration_ms=0,
            )
```
**Mandatory (CLAUDE.md "What NOT to Use", cross-checked this session):** `asyncio.create_subprocess_exec` not `subprocess.run()`; `start_new_session=True` + `os.killpg` on timeout, never a bare `communicate(timeout=N)`; never `RLIMIT_FSIZE=0`.

**Go executor delta** (RESEARCH.md Pitfall 3/11): needs a checked-in template `go.mod` scaffold copied into the temp dir, `GOCACHE`/`GOMODCACHE` set to a writable per-execution path, `go build` to a binary then execute that binary directly (not `go run`) so exactly one PID tree needs killing.

`tools/base.py`'s `CodeExecutor` Protocol has no in-repo precedent for a `Protocol` class in this codebase (Phase 1 used no `Protocol`s) — this is this phase's first occurrence of that pattern; follow RESEARCH.md's Standard Stack framing (EXEC-03 swappable-behind-an-interface) literally: an `async def run(self, code: str, tests: str, *, timeout_s: float) -> ExecutionResult` method signature, implemented identically by both `SubprocessPythonExecutor` and `SubprocessGoExecutor`.

---

### `src/algorunner/llm/client_factory.py` (provider, request-response)

**Analog:** `src/algorunner/storage/postgres.py` (module-level factory function) + `src/algorunner/worker/broker.py` (module-level singleton construction)

**Postgres pool factory pattern** (`storage/postgres.py` lines 17-26):
```python
def get_pool() -> AsyncConnectionPool:
    """Construct (but do not open) a shared AsyncConnectionPool.

    Callers must `await pool.open()` before use.
    """
    return AsyncConnectionPool(
        conninfo=settings.database_url,
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=False,
    )
```
**Broker module-level singleton pattern** (`worker/broker.py` lines 18-25):
```python
result_backend = RedisAsyncResultBackend(redis_url=settings.redis_url)
broker = RedisStreamBroker(
    url=settings.redis_url,
    queue_name="algorunner-tasks",
    consumer_group_name="algorunner-workers",
    unacknowledged_lock_timeout=30_000,
).with_result_backend(result_backend)
```
**Apply to `llm/client_factory.py`:** both existing patterns read `settings.*` (never hardcode config) at construction time — `get_client()` should do the same, reading `settings.openai_api_key`, matching `get_pool()`'s "construct from settings, one call site" shape. Use `functools.lru_cache` (RESEARCH.md Pattern 1) rather than a bare module-level singleton like `broker.py` uses, since the client is cheap to construct lazily and per-test monkeypatching is easier with a cached-function than a module-level object — this is a deliberate, minor deviation from `broker.py`'s style, not an inconsistency to "fix."

---

### `src/algorunner/llm/retry.py` (utility, request-response)

**No in-repo analog** — Phase 1 has zero retry logic anywhere (no external API calls existed). Reference RESEARCH.md Pattern 1 (RESEARCH.md lines 278-292), `tenacity` already resolved transitively (`9.1.4`):
```python
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from openai import APITimeoutError, RateLimitError

@retry(
    retry=retry_if_exception_type((APITimeoutError, RateLimitError)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
async def call_structured(client, **kwargs):
    return await client.chat.completions.parse(**kwargs)
```
**Critical scoping rule (D-00f):** only `APITimeoutError`/`RateLimitError` retry here — malformed structured output (`message.parsed is None`) is NOT a transient error and must NOT hit this same retry wrapper; it should raise/surface into the correction loop instead (RESEARCH.md Pattern 1, "Retry wrapper" paragraph).

---

### `src/algorunner/graph/state.py` (model/TypedDict, event-driven) — REPLACE

**Analog:** itself, Phase 1 version (`graph/state.py`, full 16 lines)
```python
from typing import TypedDict

class StubGraphState(TypedDict):
    task_id: str
    problem_text: str
    result: dict | None
    error: dict | None
```
**What to copy:** plain `TypedDict`, no `Annotated`/reducer fields, `| None` for not-yet-populated fields — carried forward exactly into the real `GraphState` (RESEARCH.md's full schema, RESEARCH.md lines 576-602) which is the target shape: `task_id`, `problem_text`, `language`, `examples`, `analysis`, `clarification_rounds`, `assumption_stated`, `approaches`, `solution`, `python_execution`, `go_execution`, `review`, `review_history`, `iterations`, `max_iterations`, `result`, `error`. Update the docstring to remove the "Phase 1 smoke test... Phase 2 replaces this" framing (lines 1-6) since this *is* now that replacement.

---

### `src/algorunner/graph/build.py` (service, event-driven) — REPLACE/EXTEND

**Analog:** itself, Phase 1 version (`graph/build.py`, full 37 lines)
```python
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

def build_stub_graph(checkpointer: object) -> CompiledStateGraph:
    builder = StateGraph(StubGraphState)
    builder.add_node("stub", stub_node)
    builder.add_edge(START, "stub")
    builder.add_edge("stub", END)
    return builder.compile(checkpointer=checkpointer)
```
**What to copy:** the `StateGraph(...).add_node(...).add_edge(...).compile(checkpointer=checkpointer)` builder shape and the `checkpointer: object` parameter-injection convention (never construct the checkpointer inside `build.py` itself — `worker/tasks.py` owns that, per the existing separation of concerns). Extend to `builder.add_conditional_edges("reviewer", decide_after_review, {...})` for the correction loop and clarification gate (RESEARCH.md Pattern 2/4) — this is the first `add_conditional_edges` call in the codebase, no in-repo precedent, follow RESEARCH.md's routing-function-returns-node-name convention exactly (Anti-Pattern: never let an LLM node decide the next node name).

**New non-negotiable kwarg this phase (RESEARCH.md State of the Art, verified against installed `langgraph==1.2.12` source):** every `ainvoke()` call site (in `worker/tasks.py`, not `build.py` itself) must pass `durability="sync"` explicitly — the default `"async"` mode risks losing a just-completed checkpoint write on worker crash, breaking the "resume from last completed node" guarantee this project's architecture depends on.

---

### `src/algorunner/graph/routing.py` (utility, transform) — NEW

**Analog:** `src/algorunner/graph/build.py` lines 20-24 (`stub_node`'s `if FAIL_TEST_MARKER in state["problem_text"]:` branch) — the only existing state-inspecting conditional logic in the codebase, structurally the same shape (pure function reading `state[...]`, returning a discriminator) as what a LangGraph conditional-edge function needs, just returning a node-name string instead of a dict.

**Core pattern (no in-repo precedent for the full routing function — RESEARCH.md Pattern 4, lines 401-427):**
```python
MAX_ITERATIONS = 5

_CATEGORY_TO_NODE = {
    "algorithm_soundness": "solver",
    "correctness": "solver",
    "edge_case": "solver",
    "complexity": "solver",
    "code_quality": "code_generator",
}

def decide_after_review(state: "GraphState") -> str:
    review = state["review"]
    if review.passed:
        return "finalize_success"
    if state["iterations"] >= state.get("max_iterations", MAX_ITERATIONS):
        return "finalize_failed"
    critical = [i for i in review.issues if i.severity == "critical"]
    target_priority = ["solver", "code_generator", "test_generator"]
    targets = {_CATEGORY_TO_NODE.get(i.category, "solver") for i in critical}
    return next((t for t in target_priority if t in targets), "solver")
```
**Non-negotiable:** this function must be pure Python, zero LLM calls, zero I/O — matches the one existing precedent (`stub_node`'s branch is also a pure `in` check with no I/O beyond the `asyncio.sleep` that precedes it).

---

### `src/algorunner/worker/tasks.py` (controller, event-driven) — EXTEND

**Analog:** itself (`solve_problem_stub`, full 68 lines, esp. lines 35-68)
```python
_pool = get_pool()

@broker.task
async def solve_problem_stub(task_id: str) -> None:
    from algorunner.graph.build import build_stub_graph  # deferred import, avoids circular import

    await _pool.open()  # safe to call again on an already-open pool

    await update_task_status(_pool, UUID(task_id), TaskStatus.ANALYZING_PROBLEM)  # D-09

    task = await get_task(_pool, UUID(task_id))
    problem_text = task.problem_text if task is not None else ""

    checkpointer = AsyncPostgresSaver(_pool)
    await checkpointer.setup()  # idempotent — safe every invocation
    graph = build_stub_graph(checkpointer)

    result_state = await graph.ainvoke(
        {"task_id": task_id, "problem_text": problem_text, "result": None, "error": None},
        config={"configurable": {"thread_id": task_id}},
    )

    error = result_state.get("error")
    if error is not None:
        await update_task_failed(_pool, UUID(task_id), TaskError(code=error["code"], message=error["message"]))
        return

    await update_task_completed(_pool, UUID(task_id), result=result_state.get("result"))
```
**What to copy exactly:** module-level `_pool = get_pool()` singleton, `await _pool.open()` idempotent re-open at task-entry, deferred `from algorunner.graph.build import ...` import inside the task function (avoids the circular import already documented at lines 37-40), `checkpointer.setup()` called every invocation (idempotent), `thread_id` = `task_id` string, `result_state.get("error")` / `result_state.get("result")` branching into `update_task_failed`/`update_task_completed`.

**New this phase — `resume_task_with_clarification` (RESEARCH.md Pattern 2, lines 306-325):**
```python
@broker.task
async def resume_task_with_clarification(task_id: str, answer: str) -> None:
    await _pool.open()
    checkpointer = AsyncPostgresSaver(_pool)
    graph = build_pipeline_graph(checkpointer)
    config = {"configurable": {"thread_id": task_id}}

    result_state = await graph.ainvoke(Command(resume=answer), config, durability="sync")
    await _handle_result_or_pause(task_id, result_state)

async def _handle_result_or_pause(task_id: str, result_state: dict) -> None:
    if "__interrupt__" in result_state:
        question = result_state["__interrupt__"][0].value
        await update_task_clarification(_pool, UUID(task_id), question)  # NEW storage helper
        return
    # existing completed/failed handling — reuse solve_problem_stub's exact branch above
```
**Constraint carried forward from CLAUDE.md, already honored in the Phase 1 file (docstring lines 5-7):** stay fully async — no blocking `subprocess.run()`/`time.sleep` in this file; the new executor-tool calls from Pattern 3 must be awaited via the async subprocess API, never invoked synchronously from here.

**Global timeout wrapper (RESEARCH.md Pattern 5, lines 436-452):** wrap every `ainvoke()`/resume call site in this file with `_invoke_with_budget` (new helper) rather than calling `graph.ainvoke` directly — accumulates `active_execution_seconds` on the task row so clarification-wait time doesn't count against D-08's 10-minute budget.

---

### `src/algorunner/storage/tasks.py` (service, CRUD) — EXTEND

**Analog:** itself, `update_task_status`/`update_task_completed`/`update_task_failed` (lines 43-78)
```python
async def update_task_status(pool: AsyncConnectionPool, task_id: UUID, status: TaskStatus) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE tasks SET status = %s, updated_at = now() WHERE id = %s",
            (status.value, task_id),
        )

async def update_task_failed(pool: AsyncConnectionPool, task_id: UUID, error: TaskError) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE tasks SET status = %s, error = %s, updated_at = now() WHERE id = %s",
            (TaskStatus.FAILED.value, Jsonb(error.model_dump()), task_id),
        )
```
**What to copy exactly:** `async with pool.connection() as conn: await conn.execute(...)` with `%s` placeholders only (never f-string/format user content into SQL — line 3-5 security note), `Jsonb(...)` wrapper for any dict/model-dump value written to a `JSONB` column, `updated_at = now()` on every mutating statement.

**New helpers needed this phase, following this exact shape:** `update_task_clarification(pool, task_id, question: str)` (writes `clarification_question` + sets status to `AWAITING_CLARIFICATION`), `add_active_execution_seconds(pool, task_id, delta: float)` (RESEARCH.md Pattern 5 — likely `UPDATE tasks SET active_execution_seconds = active_execution_seconds + %s WHERE id = %s`).

---

### `src/algorunner/config.py` (config) — EXTEND

**Analog:** itself, full 22 lines
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://algorunner:algorunner@localhost:5432/algorunner"
    redis_url: str = "redis://localhost:6379"
    garage_endpoint: str = ""

settings = Settings()
```
**What to copy exactly:** `pydantic_settings.BaseSettings` subclass, `env_file=".env"` config, typed fields with sane localhost defaults for host-dev parity with docker-compose. Add (per RESEARCH.md Pitfall 12 and ORCH-03): `openai_api_key: str` (no default — should fail loudly if unset, unlike the existing optional `garage_endpoint`), `default_model: str`, optional per-agent overrides (`reviewer_model: str | None = None`, etc. — read via `model_for()` in `llm/client_factory.py`), `max_iterations: int = 5` (D-00e/A3), `global_timeout_s: int = 600` (D-08).

---

### `src/algorunner/api/routes/tasks.py` (controller, request-response) — EXTEND

**Analog:** itself, `create_task`/`get_task_status` (full 35 lines)
```python
router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

@router.post("", status_code=202, response_model=TaskCreateResponse)
async def create_task(body: TaskSubmission, pool: AsyncConnectionPool = Depends(get_pg_pool)) -> TaskCreateResponse:
    task_id = uuid4()
    await insert_task(pool, task_id, body)
    await solve_problem_stub.kiq(str(task_id))
    return TaskCreateResponse(task_id=task_id, status=TaskStatus.QUEUED)

@router.get("/{task_id}", response_model=TaskRecord)
async def get_task_status(task_id: UUID, pool: AsyncConnectionPool = Depends(get_pg_pool)) -> TaskRecord:
    task = await get_task(pool, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
```
**What to copy exactly:** `Depends(get_pg_pool)` dependency injection (`api/dependencies.py`'s existing `get_pg_pool`, unchanged), `raise HTTPException(status_code=404, ...)` for missing-row 404s, `await <task>.kiq(str(task_id))` enqueue-after-commit ordering, `response_model=` on every route.

**New routes (D-03, RESEARCH.md lines 328-343), same router/file:**
```python
@router.get("/{task_id}/clarification")
async def get_clarification_question(task_id: UUID, pool=Depends(get_pg_pool)) -> ClarificationQuestion:
    task = await get_task(pool, task_id)
    if task is None or task.status != TaskStatus.AWAITING_CLARIFICATION:
        raise HTTPException(404, "No pending clarification for this task")
    return ClarificationQuestion(question=task.clarification_question)

@router.post("/{task_id}/clarification", status_code=202)
async def answer_clarification(task_id: UUID, body: ClarificationAnswer, pool=Depends(get_pg_pool)) -> TaskCreateResponse:
    task = await get_task(pool, task_id)
    if task is None or task.status != TaskStatus.AWAITING_CLARIFICATION:
        raise HTTPException(409, "Task is not awaiting clarification")
    await resume_task_with_clarification.kiq(str(task_id), body.answer)
    return TaskCreateResponse(task_id=task_id, status=TaskStatus.ANALYZING_PROBLEM)
```
Note the 409 (not 404) on the POST when status doesn't match — a real state-conflict, distinct from the GET's true-404 "no such task or nothing pending" case.

---

### `migrations/0002_add_clarification_columns.sql` (migration, batch)

**Analog:** `migrations/0001_create_tasks_table.sql` (full file, 11 lines)
```sql
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    problem_text TEXT NOT NULL,
    language VARCHAR(2) NOT NULL,
    examples JSONB NOT NULL DEFAULT '[]'::jsonb,
    result JSONB,
    error JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
**What to copy:** `CREATE TABLE IF NOT EXISTS`/`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` idempotency style (the runner in `storage/migrate.py` tracks applied filenames, but the SQL itself should still be defensively idempotent per this file's own style), `VARCHAR(32)` for status-like short strings, `JSONB` for structured optional data, `TIMESTAMPTZ ... DEFAULT now()`. New columns needed: `clarification_question TEXT`, `clarification_rounds INT NOT NULL DEFAULT 0`, `assumption_stated TEXT`, `active_execution_seconds DOUBLE PRECISION NOT NULL DEFAULT 0` (RESEARCH.md Pattern 5). File naming: `migrations/storage/migrate.py` globs `*.sql` in filename-sort order (`storage/migrate.py` line 43, `sorted(MIGRATIONS_DIR.glob("*.sql"))`) — `0002_` prefix is required for correct ordering after `0001_`.

**Scope boundary (carried forward, still applies):** never touch LangGraph's own `checkpoint_migrations`/`checkpoints`/`checkpoint_blobs`/`checkpoint_writes` tables — `AsyncPostgresSaver.setup()` owns those exclusively (01-PATTERNS.md, still correct).

---

### `docker/Dockerfile.worker` (config) — EXTEND

**Analog:** itself, full 13 lines
```dockerfile
FROM python:3.14-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY migrations ./migrations

RUN uv sync --frozen

CMD ["uv", "run", "taskiq", "worker", "algorunner.worker.tasks:broker", "--workers", "1"]
```
**Note a pre-existing drift to be aware of (not caused by this phase, flag for the planner):** the `CMD` here points at `algorunner.worker.tasks:broker`, but `worker/broker.py` line 20 is where `broker` is actually defined/imported by `worker/tasks.py` (`from algorunner.worker.broker import broker`, `worker/tasks.py` line 25) — `taskiq worker algorunner.worker.tasks:broker` works today only because `tasks.py` re-exports the imported `broker` name. Not a Phase 2 blocker, just worth the planner noting if this CMD needs touching for other reasons.

**Required extension (RESEARCH.md Pitfall 11, verified: current image has no Go at all):**
```dockerfile
FROM golang:1.27-bookworm AS go-toolchain

FROM python:3.14-slim
COPY --from=go-toolchain /usr/local/go /usr/local/go
ENV PATH="/usr/local/go/bin:${PATH}" GOCACHE=/tmp/gocache GOMODCACHE=/tmp/gomodcache
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY migrations ./migrations
COPY go-template ./go-template
RUN uv sync --frozen
CMD ["uv", "run", "taskiq", "worker", "algorunner.worker.broker:broker"]
```
Verify the exact `golang:1.27-bookworm` tag exists on Docker Hub at implementation time (Assumption A4, RESEARCH.md line 635) — low risk, fails loudly at build time if wrong.

---

### `docker-compose.yml` (config) — EXTEND

**Analog:** itself, `worker`/`api` service blocks (lines 36-62)
```yaml
worker:
  build:
    context: .
    dockerfile: docker/Dockerfile.worker
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
  environment:
    DATABASE_URL: postgresql://algorunner:algorunner@postgres:5432/algorunner
    REDIS_URL: redis://redis:6379
```
**What to copy exactly:** the `environment:` block shape, `depends_on: ... condition: service_healthy` gating. Add (RESEARCH.md lines 611-616): `OPENAI_API_KEY: ${OPENAI_API_KEY:?OPENAI_API_KEY must be set}` to both `api` and `worker` service blocks — fail-fast `:?` form, not a silent `:-` default, since this is a required secret with no fallback (RESEARCH.md Pitfall 12).

---

### `tests/conftest.py`, `tests/agents/test_*.py`, `tests/graph/test_clarification.py`, `test_correction_loop.py`, `test_global_timeout.py`, `tests/tools/test_executors.py`, `tests/api/test_clarification.py`, `tests/llm/test_*.py`

**Analog for infra-integration tests:** `tests/graph/test_build.py` (full 83 lines) + `tests/conftest.py` (full 30 lines)
```python
# conftest.py — session-scoped real-Postgres pool, migrated once
@pytest_asyncio.fixture(scope="session")
async def pg_pool() -> AsyncIterator:
    pool = get_pool()
    await pool.open()
    await apply_pending_migrations(pool)
    yield pool
    await pool.close()

# test_build.py — monkeypatch asyncio.sleep to skip the D-06 delay in tests
async def test_build_stub_graph_happy_path_sets_result(pg_pool, monkeypatch):
    async def _no_sleep(*args, **kwargs):
        return None
    monkeypatch.setattr(graph_build.asyncio, "sleep", _no_sleep)

    checkpointer = AsyncPostgresSaver(pg_pool)
    await checkpointer.setup()
    graph = build_stub_graph(checkpointer)

    thread_id = str(uuid4())
    result_state = await graph.ainvoke(
        {"task_id": thread_id, "problem_text": "two sum", "result": None, "error": None},
        config={"configurable": {"thread_id": thread_id}},
    )
    assert result_state["result"] is not None
```
**What to copy exactly:** real Postgres via the session-scoped `pg_pool` fixture (never `InMemorySaver` for these tests — 01-PATTERNS.md's own note that this is "the actual acceptance bar"), `monkeypatch.setattr(<module>.asyncio, "sleep", _no_sleep)` to skip artificial delays, direct `graph.ainvoke(..., config={"configurable": {"thread_id": thread_id}})` calls with a fresh `uuid4()` thread_id per test. `tests/graph/test_clarification.py` extends this exact pattern to also assert on `"__interrupt__" in result_state` and a subsequent `Command(resume=...)` call reusing the same `thread_id`.

**Analog for worker-task tests:** `tests/worker/test_tasks.py` (full 49 lines) — same monkeypatch-`asyncio.sleep` + `insert_task`/`get_task` round-trip convention; `tests/agents/test_*.py` should follow this file's assertion style (`record.status == "completed"`, `record.error.code == "..."`) but additionally need a new OpenAI-mock fixture (no existing precedent — RESEARCH.md Wave 0 Gaps flags this explicitly, RESEARCH.md line 700): add a `mock_openai_parse` fixture to `tests/conftest.py` that monkeypatches `get_client().chat.completions.parse` to return a canned `ParsedChatCompletion`-shaped object, following the same `monkeypatch.setattr` idiom already used for `asyncio.sleep`.

**Analog for API route tests:** `tests/api/test_tasks.py` (full 74 lines) — `app_client` fixture, `response.status_code == 202`/`422`/`404` assertions, direct `await app_client.post(...)`/`.get(...)` calls. `tests/api/test_clarification.py` follows this exactly: create a task, force it into `awaiting_clarification` (via a test-only DB write or a mocked Analyzer), then assert `GET .../clarification` returns 200 with the question and `POST .../clarification` returns 202 and enqueues resume.

**No analog for `tests/tools/test_executors.py`:** first occurrence of a subprocess-behavior test in this repo. Must explicitly assert timeout + process-group kill + zombie-reap (not just the happy path) per RESEARCH.md's Validation Architecture row for EXEC-01/02/03 (RESEARCH.md line 685) and PITFALLS.md's "Looks Done But Isn't" checklist.

## Shared Patterns

### Postgres connection kwargs (autocommit + dict_row)
**Source:** `src/algorunner/storage/postgres.py` lines 22-25 (in-repo, established Phase 1)
**Apply to:** any new module constructing a `psycopg` connection/pool this phase — none should; `llm/client_factory.py` and the new agent/tool modules all receive `pool`/`pg_pool` as a parameter rather than constructing their own, following `storage/tasks.py`'s existing convention of accepting `pool: AsyncConnectionPool` as the first argument to every function.
```python
kwargs={"autocommit": True, "row_factory": dict_row}
```

### Structured `{code, message}` error shape
**Source:** `src/algorunner/schemas/task.py` lines 51-55 (`TaskError`, in-repo)
**Apply to:** every Phase 2 pipeline failure path — correction-loop exhaustion (`finalize_failed` node), global timeout (`_invoke_with_budget`'s `except`/timeout branch), executor tool crashes surfaced up through `ExecutionResult`. Reuse the exact `TaskError` class; do not invent a second error shape for AI-pipeline-specific failures.

### Enqueue-after-commit / write-before-resume ordering
**Source:** `src/algorunner/api/routes/tasks.py` lines 19-23 (in-repo, comment explicitly documents this) + `storage/tasks.py`
**Apply to:** `answer_clarification` route (write nothing extra needed — the row is already `AWAITING_CLARIFICATION`; enqueue `resume_task_with_clarification.kiq()` only after confirming via `get_task` that the status is correct, mirroring the existing 404/409 guard-then-act shape).

### `durability="sync"` on every `ainvoke()`/resume call
**Source:** `02-RESEARCH.md` State of the Art (RESEARCH.md lines 622-623), verified against installed `langgraph==1.2.12` source this session — no in-repo precedent since Phase 1's single `ainvoke()` call (`worker/tasks.py` line 54) does NOT pass `durability=` at all (a gap this phase must fix, not copy forward).
**Apply to:** every `graph.ainvoke(...)` call site in `worker/tasks.py` (`solve_problem_stub`'s existing call site too, not just the new `resume_task_with_clarification`) — pass `durability="sync"` explicitly on all of them, since the crash-resume guarantee now matters for the first time (Phase 1's stub had no meaningful mid-pipeline state to lose).

### Tenacity-wrapped OpenAI retry, scoped narrowly
**Source:** `02-RESEARCH.md` Pattern 1 (RESEARCH.md lines 278-292) — no in-repo precedent
**Apply to:** every agent node's `chat.completions.parse()` call site, via `llm/retry.py`'s `call_structured` wrapper. Only `APITimeoutError`/`RateLimitError` retry; malformed output (`message.parsed is None`) must NOT be retried by this same mechanism.

### Deferred imports to avoid circular dependencies
**Source:** `src/algorunner/worker/tasks.py` lines 37-41 (in-repo, explicitly commented)
```python
async def solve_problem_stub(task_id: str) -> None:
    from algorunner.graph.build import build_stub_graph  # deferred import, avoids circular import
```
**Apply to:** `worker/tasks.py`'s new `resume_task_with_clarification` (same `graph.build` import), and any agent-node module that would otherwise need to import `graph.state.GraphState` at module load time purely for a type hint — prefer `from __future__ import annotations` + string-quoted type hints (already the convention: `state: "GraphState"` appears quoted in RESEARCH.md's own examples) over a real top-level import where a cycle risk exists.

## No Analog Found

Files where no in-repo precedent exists and RESEARCH.md's verified reference code is the pattern source instead:

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/algorunner/agents/*/node.py` (LLM-call body) | service | transform | Phase 1 made zero OpenAI calls; `RESEARCH.md` Pattern 1 (Context7-verified against official `openai-python` docs) is the only reference implementation |
| `src/algorunner/agents/*/prompts.py` | utility | transform | No prompt-template code exists anywhere in the repo yet |
| `src/algorunner/tools/base.py` + both executor backends | utility | file-I/O | `tools/` is an empty scaffold; no subprocess-execution code exists anywhere in the repo yet |
| `src/algorunner/llm/retry.py` | utility | request-response | No retry logic exists anywhere in the repo (no external API calls in Phase 1) |
| `src/algorunner/graph/routing.py` (full conditional-edge function) | utility | transform | No `add_conditional_edges` call exists in the repo yet; only a same-node `if` branch (`stub_node`) exists as a structural (not literal) precedent |
| `tests/tools/test_executors.py` | test | file-I/O | First subprocess-behavior test in the repo; must cover timeout/process-group-kill/zombie-reap explicitly, no existing test exercises OS process control |

## Metadata

**Analog search scope:** entire git-tracked repository (`git ls-files`), primarily `src/algorunner/**`, `tests/**`, `migrations/**`, `docker/**`, `docker-compose.yml`, cross-referenced against `02-RESEARCH.md`'s verified Architecture Patterns/Code Examples for the 6 files/patterns with no in-repo precedent
**Files scanned:** 20 tracked source/test/config files read in full this session (all ≤90 lines; no `Grep`-then-partial-`Read` was needed — every candidate analog fit comfortably in one `Read` call)
**Pattern extraction date:** 2026-09-23
