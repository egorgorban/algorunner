# Requirements: AlgoRunner

**Defined:** 2026-09-22
**Core Value:** Correctness of the generated solution — verified by actually executing the generated Python and Go code against generated (or provided) tests — matters more than explanation quality or speed.

## v1 Requirements

### Intake

- [x] **INTAKE-01**: User submits a problem description (English or Russian text, optional examples/tests) via the API
- [x] **INTAKE-02**: Problem Analyzer extracts the task's constraints, input/output shape, and intent from free-text input
- [x] **INTAKE-03**: Problem Analyzer assigns a difficulty rating (Easy/Medium/Hard)
- [ ] **INTAKE-04**: When the problem description is ambiguous or underspecified, the task transitions to `awaiting_clarification` status instead of guessing
- [ ] **INTAKE-05**: User can submit a clarification answer against an `awaiting_clarification` task via a dedicated API endpoint, resuming the same task from its checkpointed state

### Strategy

- [ ] **STRAT-01**: Solution Strategist proposes 1+ distinct solution approaches (e.g. brute-force, optimized, alternative) for the analyzed problem
- [ ] **STRAT-02**: Solution Strategist decides which alternative approaches are worth including in the final editorial (not every possible approach is surfaced)
- [ ] **STRAT-03**: Each proposed approach is tagged with its topic/technique (e.g. "two pointers", "dynamic programming", "graph — BFS")
- [ ] **STRAT-04**: A single generic Solver agent (not one agent per algorithm type) elaborates each proposed approach into a concrete algorithm

### Code Generation

- [ ] **CODE-01**: Code Generator produces a Python implementation for each approach
- [ ] **CODE-02**: Code Generator produces a Go implementation for each approach
- [ ] **CODE-03**: Test Generator produces test cases per approach, incorporating any examples/tests provided in the original problem input
- [ ] **CODE-04**: Test Generator generates additional test cases (including edge cases) when the input doesn't provide enough

### Execution

- [ ] **EXEC-01**: Deterministic PythonExecutorTool runs generated Python code against generated/provided tests via subprocess and returns a structured pass/fail result (not an LLM agent)
- [ ] **EXEC-02**: Deterministic GoExecutorTool compiles and runs generated Go code against generated/provided tests via subprocess and returns a structured pass/fail result (not an LLM agent)
- [ ] **EXEC-03**: Both executor tools are built behind a swappable interface so the underlying execution strategy (subprocess today) can later be replaced with a sandboxed/isolated implementation without changing agent logic

### Review

- [ ] **REV-01**: Reviewer agent evaluates each approach's correctness, algorithm soundness, edge-case coverage, complexity claim, and code quality
- [ ] **REV-02**: Reviewer returns a structured ReviewResult (passed, issues, severity, required_changes) including edge cases considered
- [ ] **REV-03**: Reviewer's complexity check requires a reasoning justification for the claimed Big-O, not just acceptance of the asserted notation
- [ ] **REV-04**: A failed review routes the task back into a correction loop (Solution Designer/Solver) carrying prior attempt context, not starting over
- [ ] **REV-05**: The correction loop is bounded by a configurable max_iterations (3-5); exceeding it produces a terminal FAILED result instead of looping indefinitely

### Editorial

- [ ] **EDIT-01**: Editorial Writer composes the final article in Russian regardless of input language
- [ ] **EDIT-02**: Each approach in the article follows a fixed structure: Intuition → Algorithm → Code (Python + Go) → Complexity (with a one-line justification, not just Big-O notation)
- [ ] **EDIT-03**: Approaches are presented in sequential order (brute-force → optimized → alternative) with a narrative bridge sentence explaining why each subsequent approach improves on the previous one
- [ ] **EDIT-04**: The article surfaces the difficulty rating and topic/technique tags
- [ ] **EDIT-05**: The article surfaces edge cases the Reviewer identified as handled
- [ ] **EDIT-06**: When the Problem Analyzer required clarification, the resolved clarification is reflected in the final article's problem restatement

### Orchestration

- [ ] **ORCH-01**: The full pipeline (Analyzer → Strategist → Solver → Code Generator → Test Generator → Executors → Reviewer → correction loop → Editorial Writer) runs as a LangGraph StateGraph with deterministic transitions and LLM reasoning bounded to specific nodes
- [x] **ORCH-02**: Inter-node data (analysis, approaches, code, review results) is validated via Pydantic structured-output schemas
- [x] **ORCH-03**: Each OpenAI-backed node's model is configurable independently via env/config (e.g. cheap model for analysis/review, strong model for solving/finalization)
- [x] **ORCH-04**: LangGraph execution state is checkpointed to PostgreSQL so an interrupted run (including one paused on `awaiting_clarification`) can resume from where it left off

### API & Realtime

- [x] **API-01**: `POST /api/v1/tasks` accepts a problem submission and returns `202 Accepted` with `task_id` and `status: queued`
- [x] **API-02**: `GET /api/v1/tasks/{task_id}` returns the task's current status and, when completed, its result
- [ ] **API-03**: `POST /api/v1/tasks/{task_id}/clarification` accepts a clarification answer for a task in `awaiting_clarification` status
- [ ] **API-04**: `WS /api/v1/tasks/{task_id}/events` streams status transitions in realtime (queued → analyzing_problem → designing_solution → generating_code → generating_tests → executing_tests → reviewing → correcting → awaiting_clarification → writing_editorial → completed/failed)
- [ ] **API-05**: A WebSocket client connecting after a task has already progressed immediately receives the task's current state, not only future deltas

### Queue & Persistence

- [x] **QUEUE-01**: API requests enqueue tasks via taskiq + Redis and return immediately; if all workers are busy, the task remains in `queued` status until a worker is free
- [x] **DATA-01**: PostgreSQL is the source of truth for task state (id, status, timestamps, error, result)
- [ ] **DATA-02**: Intermediate artifacts per task (ProblemAnalysis, each Solution's algorithm/Python code/Go code/tests/complexity/review history, final Editorial) are persisted to Garage (S3-compatible storage)

### Frontend

- [ ] **UI-01**: React + TypeScript web UI provides a problem input form (text + optional examples)
- [ ] **UI-02**: Web UI shows live pipeline status via the WebSocket events endpoint
- [ ] **UI-03**: Web UI prompts the user for a clarification answer when the task is `awaiting_clarification`
- [ ] **UI-04**: Web UI displays the final editorial per approach (explanation, Python code, Go code, complexity, difficulty, tags, edge cases)

### Infrastructure

- [x] **INFRA-01**: Project uses Python 3.14 managed via `uv`, a single package with clear modular structure (agents/, tools/, api/, worker/, schemas/) — not DDD/clean-architecture layering
- [x] **INFRA-02**: Docker Compose brings up API, worker, PostgreSQL, Redis, and Garage together
- [x] **INFRA-03**: OpenAI timeout and rate-limit errors trigger a pause-and-cooldown retry with backoff rather than an immediate failure
- [ ] **INFRA-04**: A global timeout bounds total task solve time; a task exceeding it terminates as FAILED rather than running indefinitely
- [ ] **INFRA-05**: Full documentation set is produced alongside implementation: `CLAUDE.md` (minimal repo rules) + `docs/product/prd.md` + `docs/architecture/{architecture,agents,workflow,data-model}.md` + `docs/development/{testing,conventions}.md` + `docs/plans/implementation-plan.md`, with deferred/future-scope assumptions captured in their own dedicated section

## v2 Requirements

Deferred to a future milestone. Tracked but not in the current roadmap.

### Security & Hardening

- **SEC-01**: Authentication for API/UI access
- **SEC-02**: Sandboxed (Docker/isolated-service) execution for generated Python and Go code
- **SEC-03**: Resource limits (CPU/RAM/execution time/network/filesystem) on code execution

### Platform

- **PLAT-01**: Kubernetes deployment
- **PLAT-02**: Structured logging, Prometheus metrics, OpenTelemetry tracing, LangSmith trace capture, per-request/agent/run OpenAI cost tracking
- **PLAT-03**: CI/CD (GitHub Actions), pre-commit, ruff, mypy/pyright enforcement

### Product

- **PROD-01**: Cross-task memory (system remembers a user's previously solved problems)
- **PROD-02**: Follow-up variation prompt per problem (e.g. "what if input doesn't fit in memory?")
- **PROD-03**: Review-history transparency surfaced in the web UI (why a correction iteration failed and what changed)
- **PROD-04**: True interactive clarifying-question chat beyond the single-round pause/resume already in v1 (shares infrastructure with the correction loop's checkpoint/resume mechanism)

### Evaluation

- **EVAL-01**: Evaluation dataset and automated benchmark suite (solution correctness, code correctness, complexity correctness, explanation quality, pass rate, latency, token cost)
- **EVAL-02**: Automated comparison across system versions (accuracy/cost/latency)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Empirical verification that claimed asymptotic complexity actually holds | Product owner decided complexity is reviewed analytically (Reviewer's reasoning check) only, not benchmarked |
| Interactive code playground (edit-and-rerun in-browser) | Requires exposing today's plain-subprocess executors to arbitrary user input — collides with deferred sandboxing; revisit only after SEC-02/SEC-03 land |
| Additional programming languages beyond Python + Go | Fixed dual-language scope per product owner; a distinct future milestone would need its own executor tools |
| "Similar problems" recommendations | Requires a curated, tagged problem corpus that doesn't exist; different product surface entirely |
| Video or animated visual explanations | Requires video/diagram generation capability absent from this text-pipeline architecture |
| Literal BMAD agent personas (Analyst/PM/Architect/Scrum Master/Developer role-play) | Using BMAD as a methodology/doc-structure influence only, per product owner |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INTAKE-01 | Phase 1 | Complete |
| ORCH-02 | Phase 1 | Complete |
| API-01 | Phase 1 | Complete |
| API-02 | Phase 1 | Complete |
| QUEUE-01 | Phase 1 | Complete |
| DATA-01 | Phase 1 | Complete |
| INFRA-01 | Phase 1 | Complete |
| INFRA-02 | Phase 1 | Complete |
| INTAKE-02 | Phase 2 | Complete |
| INTAKE-03 | Phase 2 | Complete |
| INTAKE-04 | Phase 2 | Pending |
| INTAKE-05 | Phase 2 | Pending |
| STRAT-01 | Phase 2 | Pending |
| STRAT-03 | Phase 2 | Pending |
| STRAT-04 | Phase 2 | Pending |
| CODE-01 | Phase 2 | Pending |
| CODE-02 | Phase 2 | Pending |
| CODE-03 | Phase 2 | Pending |
| CODE-04 | Phase 2 | Pending |
| EXEC-01 | Phase 2 | Pending |
| EXEC-02 | Phase 2 | Pending |
| EXEC-03 | Phase 2 | Pending |
| REV-01 | Phase 2 | Pending |
| REV-02 | Phase 2 | Pending |
| REV-03 | Phase 2 | Pending |
| REV-04 | Phase 2 | Pending |
| REV-05 | Phase 2 | Pending |
| ORCH-03 | Phase 2 | Complete |
| ORCH-04 | Phase 2 | Complete |
| API-03 | Phase 2 | Pending |
| INFRA-03 | Phase 2 | Complete |
| INFRA-04 | Phase 2 | Pending |
| STRAT-02 | Phase 3 | Pending |
| EDIT-01 | Phase 3 | Pending |
| EDIT-02 | Phase 3 | Pending |
| EDIT-03 | Phase 3 | Pending |
| EDIT-04 | Phase 3 | Pending |
| EDIT-05 | Phase 3 | Pending |
| EDIT-06 | Phase 3 | Pending |
| ORCH-01 | Phase 3 | Pending |
| DATA-02 | Phase 3 | Pending |
| API-04 | Phase 4 | Pending |
| API-05 | Phase 4 | Pending |
| UI-01 | Phase 4 | Pending |
| UI-02 | Phase 4 | Pending |
| UI-03 | Phase 4 | Pending |
| UI-04 | Phase 4 | Pending |
| INFRA-05 | Phase 4 | Pending |

**Coverage:**

- v1 requirements: 48 total (corrected from a stale "42" count in the original definition — recount against the actual `### Intake` through `### Infrastructure` sections above)
- Mapped to phases: 48
- Unmapped: 0 ✓

---
*Requirements defined: 2026-09-22*
*Last updated: 2026-09-22 after roadmap creation (traceability populated, stale total-count corrected)*
