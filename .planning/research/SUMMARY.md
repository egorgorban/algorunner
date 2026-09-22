# Project Research Summary

**Project:** AlgoRunner
**Domain:** Multi-agent LLM pipeline (LangGraph) that generates verified, bilingual-input/Russian-output algorithmic editorials with dual-language (Python + Go) executed-and-tested code, served via FastAPI/WebSocket + taskiq/Redis + PostgreSQL + Garage(S3)
**Researched:** 2026-09-22
**Confidence:** MEDIUM

## Executive Summary

AlgoRunner is a verification-first, multi-agent code-editorial generator: a fixed (non-LLM-routed) LangGraph pipeline takes a problem statement, analyzes it, proposes brute-force/optimized/alternative approaches, solves and codes each one, generates tests, actually compiles and executes the code in Python and Go, reviews the result (including a structural complexity re-derivation, not just a claim echo), loops back through a bounded correction cycle on failure, and finally writes a Russian-language editorial. The product sits between two reference classes researched separately: human-curated editorial sites (LeetCode/NeetCode/AlgoExpert), which set the bar for output *structure and pedagogy*, and AI code-generation/judge research systems (CodeContests+, AutoCode), which establish that a Generator→Validator→Checker verification loop is *table stakes, not a differentiator*, for LLM-generated code. AlgoRunner's own Core Value statement ("correctness matters more than explanation quality or speed") aligns exactly with the second reference class — this is the validated, non-negotiable spine of the system and should never be cut under schedule pressure.

The recommended approach is: a single `uv`-managed Python package (not a multi-package workspace — API, worker, and graph share one deployable image and dependency set, so a workspace would add indirection for no benefit at this scale), with `schemas/` (Pydantic v2 models) as the real contract layer across agents/tools/API/worker in the absence of DDD-style layering. All control flow is deterministic Python (`add_conditional_edges` / `Command`, driven by state counters), never LLM-decided routing — this was already locked by the product owner and research confirms it as the correct call (non-deterministic supervisor routing is explicitly named as the most common anti-pattern to avoid reintroducing). LangGraph's `AsyncPostgresSaver` checkpoints every superstep keyed by `thread_id = task_id`, giving free crash-resume for both the correction loop and (later, cheaply) a true interactive-clarification feature. taskiq (Redis Streams broker, not plain pub/sub or list-queue, for durability) runs one LangGraph invocation per task; Postgres — not Redis, not LangGraph's checkpoint state — is the single source of truth for API-visible task status, with Redis pub/sub as a pure low-latency fan-out layer for the WebSocket bridge.

The key risks cluster in three places, all addressable with known, cheap mitigations if built in from day one rather than retrofitted: (1) the code-execution tools are a genuine safety-critical surface even without a "real" sandbox — missing timeouts/rlimits/process-group kills/temp-dir isolation on Python and (especially) Go execution can wedge or crash a whole worker host, and Go's `go run` process-tree and missing-`go.mod` issues are sharp, well-documented edges; (2) LangGraph's own internal `recursion_limit` (default 25, counted in supersteps) is a different counter than the app's intended `max_iterations` correction bound and will silently produce an ugly `GraphRecursionError` instead of a clean `FAILED` result if not explicitly reconciled, and unbounded state reducers on correction-loop history will bloat Postgres checkpoint storage; (3) the async task-queue delivery model (submit → poll/stream, no live chat) means the pipeline's "ask a clarifying question" requirement and "LLM-generated tests validate the model's own blind spots" risk both need explicit architectural/prompt decisions now (stated-assumptions-in-output for v1; problem-example tests + constraint-derived edge-case checklists for test generation) rather than assuming the naive version is sufficient.

## Key Findings

### Recommended Stack

The stack is mostly pre-locked by PROJECT.md; the research fills in *how the pieces integrate*. `langgraph` + `langgraph-checkpoint-postgres` (psycopg3-only, never asyncpg for this piece) gives crash-resumable graph state. `taskiq` + `taskiq-redis`'s `RedisStreamBroker` (acked, durable — not the list-queue or pub/sub broker variants) is the task queue. `openai`'s `chat.completions.parse()` gives Pydantic-schema-constrained structured outputs at every agent boundary, but is **not** automatically retried by the SDK on refusal/truncation — wrap in `tenacity`. FastAPI uses `lifespan` (not `@app.on_event`) to manage broker/pool startup. A `uv` workspace is the right shape *if* api/worker/shared code ever become separately deployable, but the Architecture research recommends starting as a **single package** since nothing currently forces independent deploys or conflicting dependency versions.

**Core technologies:**
- `langgraph` (1.0.x) + `langgraph-checkpoint-postgres` (3.1.2, needs `langgraph-checkpoint>=4.1.0,<5.0.0` and `psycopg[binary,pool]>=3.2.0`) — orchestration + crash-resumable state, official first-party checkpointer
- `taskiq` + `taskiq-redis` (`RedisStreamBroker`) — async-native task queue with durable ack semantics, matched to the node-graph-in-a-task execution model
- `openai` Python SDK (pin explicitly, v1 vs v2 line) — `chat.completions.parse()` for schema-constrained inter-node contracts
- `pydantic` v2 — one schema library end-to-end (LangGraph state, OpenAI structured outputs, FastAPI models)
- `psycopg[binary,pool]` (Psycopg 3) — required by the checkpointer; use `AsyncPostgresSaver.from_conn_string(...)` or explicitly set `autocommit=True, row_factory=dict_row` (a documented, easy-to-hit footgun otherwise)
- `redis.asyncio` — direct pub/sub client for bridging worker progress to WebSocket clients, alongside `taskiq-redis`'s broker use of Redis
- `aioboto3`/`boto3` — Garage (S3-compatible) artifact storage client

Flagged for verification at implementation time (not blocking, but genuinely uncertain): LangGraph's explicit Python 3.14 support is unconfirmed (3.13 is confirmed; run a real `uv sync` smoke test in Phase 1 with a documented fallback to pin the interpreter at 3.13 if it fails), and the OpenAI SDK v1/v2 major-version boundary should be pinned deliberately rather than left to float.

### Expected Features

No direct competitor matches AlgoRunner's exact shape; the comparison set splits into human-curated editorial products (structure/pedagogy bar) and AI code-generation/judge research systems (verification-trust bar), and AlgoRunner must clear both simultaneously.

**Must have (table stakes):**
- Per-approach structure (Intuition → Algorithm → Code → Complexity), with complexity claims *justified* with a one-line "why," not just Big-O notation
- Sequential brute-force → optimized → alternative approach ordering (already implied by the confirmed Solution Strategist design)
- Test-generation + dual-language execution + Reviewer + bounded correction loop — validated here as **non-negotiable table stakes**, not a differentiator, given the LLM-code reference class and the product's own stated core value
- Explicit ambiguity handling before solving (minimum viable version for v1: Problem Analyzer states its assumptions in the output, since the async task-queue delivery model doesn't yet support true interactive clarification)
- Difficulty rating and topic/technique tags — cheap, near-free additions to already-produced agent output, absent from current confirmed requirements
- Edge-case callouts surfaced in the article itself (Reviewer already computes this internally — the gap is plumbing it to the Editorial Writer)

**Should have (competitive):**
- Narrative bridge sentence between approaches ("Approach 1 is correct but too slow because X; Approach 2 fixes this by Y") — NeetCode's specific, cheap, prompt-level differentiator over terser official editorials
- Dual verified-language output (Python + Go) and Russian-language output — both already committed, and both are genuine structural advantages with no precedent in the comparison set; worth stating explicitly in product framing
- Review-history transparency in a future web UI (data already exists in `ReviewResult`/correction history)

**Defer (v2+):**
- True interactive (synchronous) clarifying-question chat — requires new task-pause/await-input/resume state machinery; shares infrastructure with the correction loop's checkpointing, so design the checkpoint/resume mechanism generically now even though it stays non-interactive in v1
- Interactive code playground — conflicts directly with the deferred sandboxing/resource-limits milestone; do not schedule until that lands
- Similar-problems recommendations — requires a curated problem corpus that doesn't exist
- Additional languages beyond Python/Go, video/animated explanations, empirical (as opposed to analytical) complexity verification — all explicitly out of scope

### Architecture Approach

A thin FastAPI boundary (validate → enqueue → read status/stream events, never invokes LangGraph directly) sits in front of a taskiq worker that owns the one place LangGraph actually runs — a single compiled `StateGraph` reused across `thread_id`s. The graph fans out per solution approach (`Send`), runs LLM-backed agent nodes (each a plain `async def (state) -> dict` using `with_structured_output`) alongside deterministic, non-LLM tool nodes (Python/Go executors behind a `Protocol` boundary, so subprocess execution can later be swapped for a sandbox without touching any agent code), and loops a bounded number of times between Solver and Reviewer before reducing to a Editorial Writer → Finalizer. PostgreSQL holds two independent things sharing one instance: the task-status table (source of truth for the API) and LangGraph's own checkpoint tables (resumability, keyed by `thread_id = task_id`). Garage (S3) stores large structured artifacts (ProblemAnalysis, Solution list, Editorial), keeping Postgres rows small.

**Major components:**
1. `schemas/` — the real contract layer (Pydantic models every agent, tool, API route, and worker task agrees on)
2. `graph/` — wiring only (`add_node`/`add_conditional_edges`/`compile` + routing predicates); no business logic, so the architecturally-locked control flow stays reviewable in one file
3. `agents/<name>/` — one subpackage per LLM-backed node (Problem Analyzer, Solution Strategist, Solver, Code Generator, Test Generator, Reviewer, Editorial Writer), each colocated with its own prompts
4. `tools/` — deterministic, non-LLM executors (`PythonExecutorTool`, `GoExecutorTool`) behind an `ExecutorProtocol`, the seam that makes "subprocess now, sandbox later" a config change, not a refactor
5. `api/` and `worker/` — separate deployable entrypoints sharing only `schemas/`, `storage/`, `config.py`; API never imports `graph/`

### Critical Pitfalls

1. **"No sandbox yet" quietly becomes "no safety net at all"** — build the full minimum-viable checklist (wall-clock timeout, `RLIMIT_CPU`/`RLIMIT_AS`/`RLIMIT_NOFILE`/`RLIMIT_NPROC=0`, process-group spawn + `killpg`, always reap, non-root user, per-execution temp dir) into the executor tools from Phase 1 of that work, not as a later hardening pass — a single hung generated infinite loop can wedge an entire worker host.
2. **`go run` timeout kills the wrapper, not the compiled binary** — invoke the Go toolchain with `Setpgid: true` and kill the whole process group on timeout; prefer `go build` to a known path + execute that binary under your own process-group control over `go run`.
3. **Missing `go.mod` scaffold breaks or silently misresolves Go builds** — pre-seed a fixed template module (pinned Go version, zero/minimal deps) per execution temp dir, and point `GOCACHE`/`GOMODCACHE` at an explicitly writable path.
4. **LLM-generated tests share the code generator's own blind spots** — require the problem's given examples verbatim as non-negotiable tests, drive additional test generation from an explicit constraint-derived edge-case checklist (not open-ended "generate more tests"), and have the Reviewer explicitly judge test *coverage against stated constraints*, not just pass/fail.
5. **`recursion_limit` (LangGraph, default 25, counts supersteps) vs. app-level `max_iterations` (correction cycles) are different counters** — compute and set `recursion_limit` explicitly as a function of `(nodes per cycle) × max_iterations + overhead`; the app-level counter must produce a clean `FAILED` result before the graph-level limit could ever fire, which should only ever be a safety net that never actually triggers.

## Implications for Roadmap

Based on combined research, suggested phase structure:

### Phase 1: Foundation & Infrastructure Skeleton
**Rationale:** Everything downstream (agents, tools, graph) depends on the schema contract layer, the task-status source of truth, and the deploy shape being settled first; this phase carries no LLM/graph risk and can be validated end-to-end cheaply (submit → queued → stub-complete) before any agent logic exists.
**Delivers:** Single `uv` package structure (`schemas/`, `config.py`, `storage/`), Docker Compose (Postgres, Redis, Garage), Postgres task table, FastAPI skeleton (`POST /tasks`, `GET /tasks/{id}`), taskiq broker wired to a stub no-op task.
**Addresses:** No FEATURES.md item directly — this is the "product feels incomplete without it" plumbing every feature depends on.
**Avoids:** Establishes the Postgres-as-source-of-truth pattern from day one (Pitfall 8), before anything else can grow the bad habit of trusting Redis/result-backend presence as status.

### Phase 2: Code Execution Tools (Python + Go Executors)
**Rationale:** This is the single highest-density pitfall cluster (3 of 9 critical pitfalls) and is fully testable in isolation from any LLM/graph work — build and harden it before it's wired into the correction loop, where failures would be much harder to isolate.
**Delivers:** `ExecutorProtocol`, `SubprocessPythonExecutor`, `SubprocessGoExecutor` with full safety net (timeouts, rlimits, process-group kill+reap, non-root execution, per-run temp dir, Go `go.mod` scaffold + writable `GOCACHE`).
**Addresses:** Test-driven correctness verification (table stakes, FEATURES.md).
**Avoids:** Pitfalls 1, 2, 3 (safety net gaps, orphaned Go binaries, missing `go.mod`) — verified via explicit "deliberately execute an infinite loop / fork-bomb-style snippet / never-terminating goroutine" tests, not just happy-path timeout tests.

### Phase 3: LangGraph Core — Analysis & Strategy
**Rationale:** Establishes the graph wiring pattern (structured-output nodes, `Send` fan-out, `AsyncPostgresSaver` checkpointing keyed by `thread_id=task_id`) with the lowest-complexity agents first, before adding the correction loop's extra state-machine complexity.
**Delivers:** `graph/build.py` skeleton, `agents/problem_analyzer/`, `agents/solution_strategist/`, checkpointer wired and verified resumable (kill worker mid-run, confirm resume from last checkpoint).
**Uses:** `langgraph`, `langgraph-checkpoint-postgres`, `psycopg[binary,pool]`, `pydantic` structured outputs (STACK.md).
**Implements:** `graph/`, `agents/` boundary per ARCHITECTURE.md; Pattern 2 (structured LLM output at every node boundary).

### Phase 4: Solve–Verify–Correct Loop
**Rationale:** The verification loop is the product's core value and its highest-risk state-machine logic (recursion-limit mismatch, reducer bloat, complexity-claim trust); build it once the executor tools (Phase 2) and graph skeleton (Phase 3) both already exist and are independently trustworthy.
**Delivers:** `agents/solver/`, `agents/code_generator/`, `agents/test_generator/`, `agents/reviewer/` (with a required structured `complexity_reasoning` field, not just a pass/fail), wired to Phase 2's executor tools via thin node adapters, plus the bounded correction loop (in-state `max_iterations` counter + conditional edge, explicit `recursion_limit` calculation).
**Addresses:** Test-driven correctness verification, justified complexity claims (table stakes, FEATURES.md).
**Avoids:** Pitfalls 4, 5, 6, 7 (test blind spots, unverified complexity claims, recursion-limit mismatch, checkpoint bloat from over-eager reducers) — verified via forced `max_iterations` failure tests confirming a clean `FAILED` result rather than `GraphRecursionError`, and checkpoint-size inspection across a multi-iteration test task.

### Phase 5: Editorial Writer & Finalization
**Rationale:** Only makes sense once verified `Solution` objects exist per approach (Phase 4); this phase is pure prompt-engineering and artifact-persistence work with no new infrastructure risk.
**Delivers:** `agents/editorial_writer/` (bilingual EN/RU input → RU output, narrative bridge between approaches, difficulty rating, topic/technique tags, edge-case callouts threaded from Reviewer output, stated-assumptions surfacing), Finalizer node writing artifacts to Garage and marking the task row complete.
**Addresses:** Per-approach structure, narrative bridge, difficulty/tags, edge-case callouts, stated-assumptions handling — the bulk of the P1 feature list (FEATURES.md).
**Avoids:** Bilingual language leakage (Pitfall checklist item) — verify with both English- and Russian-language problem inputs that output/comments are consistently Russian with English-only identifiers.

### Phase 6: Real-Time Status & WebSocket Streaming
**Rationale:** Best built last among backend phases because it's a thin layer over status transitions that only exist once the graph (Phases 3-5) actually produces them; also benefits from Phase 1's Postgres-source-of-truth pattern already being solid.
**Delivers:** `WS /api/v1/tasks/{id}/events` with "send current full state from Postgres on connect, then stream deltas via Redis pub/sub" (never live-deltas-only), plus a worker-crash reconciliation watchdog (any non-terminal task with no active worker heartbeat past a timeout gets re-queued or marked FAILED).
**Addresses:** No new FEATURES.md item — this is UX-critical plumbing for the async delivery model already locked by PROJECT.md.
**Avoids:** Pitfalls 8, 9 (silent task loss on worker crash; WebSocket clients missing early transitions) — verified by killing a worker mid-task and by connecting a client several seconds after task submission.

### Phase Ordering Rationale

- Infrastructure and the contract schema layer must exist before anything else can be tested in isolation (Phase 1).
- The highest pitfall-density, most independently-testable component (code execution) is pulled forward to Phase 2, ahead of any LLM/graph complexity, so failures there are never confused with agent/prompt bugs later.
- Graph wiring is split into "low-risk agents + checkpointing" (Phase 3) before "correction loop + verification" (Phase 4), because the correction loop's state-machine pitfalls (recursion limit, reducer bloat) are much easier to design correctly against an already-proven checkpoint/resume mechanism than to retrofit.
- Editorial generation (Phase 5) and real-time status streaming (Phase 6) are pushed to the end because both are additive layers over data/state that only exists once the core pipeline is trustworthy — this also matches FEATURES.md's own MVP-vs-v1.x prioritization (P1 pipeline features before P2 UI/transparency features).

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Code Execution Tools):** sandboxing/resource-limit specifics are almost entirely community-practice/LOW-confidence web sources, not official docs — verify exact `resource.setrlimit`/process-group syntax and the `RLIMIT_FSIZE` footgun against the target OS/container base image before implementation.
- **Phase 4 (Solve–Verify–Correct Loop):** LangGraph's `Command` vs. `add_conditional_edges` idiom for this exact correction-loop shape is an actively-evolving area of the API — confirm current recommended idiom, exact `recursion_limit` interaction, and reducer semantics against the actually-installed LangGraph version before locking in the state schema.
- **Phase 6 (WebSocket Streaming):** the taskiq/FastAPI/Redis-pub-sub bridging pattern is corroborated across multiple independent blog/community sources but has no single canonical official doc — verify the exact `redis.asyncio` pub/sub API shape and confirm `RedisStreamBroker`'s ack semantics against the installed `taskiq-redis` version.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** FastAPI `lifespan`, Docker Compose, Postgres task tables, and `uv` project setup are extremely well-documented, stable patterns.
- **Phase 3 (Analysis & Strategy agents):** `with_structured_output`/`chat.completions.parse()` structured-output usage is confirmed against official LangGraph and OpenAI SDK docs via Context7 at MEDIUM-HIGH confidence.
- **Phase 5 (Editorial Writer):** pure prompt-engineering work with no new integration surface once Phase 4's `Solution` objects exist.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Core integration facts (LangGraph checkpointer, taskiq/taskiq-redis, OpenAI structured outputs) verified against official docs via Context7; monorepo/sandboxing/websocket-bridging specifics are community-practice, explicitly flagged as verify-at-implementation-time |
| Features | MEDIUM | No direct competitor exists for this exact product shape; findings are grounded in websearch (MEDIUM) plus long-standing, stable product conventions (LeetCode/AlgoExpert page structure) treated as high-certainty despite the websearch sourcing tier |
| Architecture | MEDIUM | LangGraph/taskiq API shapes confirmed from official repo docs/source via Context7 (MEDIUM); general project-layout and Protocol-boundary guidance is LOW-MEDIUM, sourced from web search rather than an authoritative single reference |
| Pitfalls | MEDIUM | Individually LOW-confidence web sources, but cross-checked across multiple independent sources per pitfall, and LangGraph-specific claims corroborated against official docs via Context7 |

**Overall confidence:** MEDIUM

### Gaps to Address

- **Python 3.14 + LangGraph compatibility is unconfirmed** (3.13 is explicitly confirmed by LangGraph's changelog; 3.14 is not) — run a real `uv sync`/smoke-test in a 3.14 environment as the very first Phase 1 task, with a documented fallback (pin interpreter to 3.13) if it fails.
- **OpenAI Python SDK v1 vs v2 major version** — both are current per the package registry; pin explicitly during Phase 1 setup and confirm `chat.completions.parse()` exists unchanged in whichever major is chosen, rather than letting `uv add openai` float.
- **Interactive clarifying-question UX is an explicit scoping decision, not resolved by this research** — v1 should default to "Problem Analyzer states assumptions in output" (fits the async architecture with zero new components); true interactive pause/resume is a natural v1.x extension once the correction loop's checkpoint/resume plumbing is proven, but this decision should be made explicitly during requirements definition, not discovered as a gap during Phase 4/5 implementation.
- **`Command` vs. `add_conditional_edges` idiom** for the correction loop is an actively-evolving part of the LangGraph API — verify against the pinned LangGraph version before finalizing the Phase 4 state schema, since this affects how routing logic and state updates are structured.
- **Exact `taskiq-redis` broker class names/import paths and `RedisStreamBroker` ack guarantees** should be re-confirmed against whatever version is actually pinned in `pyproject.toml`, since taskiq is a fast-moving, less mature ecosystem than LangGraph/FastAPI.

## Sources

### Primary (HIGH/MEDIUM confidence, official sources via Context7)
- `/langchain-ai/langgraph` (Context7) — checkpointer setup, `thread_id`/`checkpoint_id` resume, `Command`/`Send` types, `AsyncPostgresSaver`
- `/openai/openai-python` and `/websites/developers_openai_api` (Context7) — `chat.completions.parse()`, structured-outputs schema constraints, refusal/parsed handling
- `/taskiq-python/taskiq` and `/taskiq-python/taskiq-redis` (Context7) — broker/result-backend choices, FastAPI lifespan integration, worker CLI concurrency flags
- `docs.astral.sh/uv/concepts/projects/workspaces/` — official `uv` workspace documentation

### Secondary (MEDIUM confidence, cross-corroborated web sources)
- LeetCode/NeetCode/AlgoExpert editorial structure and feature-set comparisons (multiple independent sources per claim)
- CodeContests+, AutoCode, CodeHacker (arXiv, 2025-2026) — LLM code-generation verification-loop research, used to establish test/execute/review as table stakes
- LangGraph infinite-loop/recursion-limit and checkpoint-pruning community writeups, cross-referenced against official LangGraph persistence/Pregel docs

### Tertiary (LOW confidence individually, needs validation at implementation time)
- Python subprocess resource-limiting and Go process-group/`go.mod`-scaffold community posts and GitHub issues (`healeycodes.com`, `chs.us`, `docker-library/golang#225`, `golang/go#29063`, Go forum threads)
- FastAPI + Celery/taskiq + WebSocket + Redis pub/sub bridging pattern (multiple blog/Medium/GitHub examples, no single canonical official doc)
- Python 3.14 compatibility claims for `psycopg`/`taskiq-postgres` (PyPI package pages, release notes)

---
*Research completed: 2026-09-22*
*Ready for roadmap: yes*
