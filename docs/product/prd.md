# Product Requirements Document: AlgoRunner

## Problem Statement

Developers and students preparing for technical interviews often struggle with algorithmic problems: understanding what's being asked, identifying the right approach, implementing correctly in multiple languages, and evaluating edge cases. They rely on solutions from platforms like LeetCode, but must manually synthesize approach variations, code, and complexity analysis. This is time-consuming and error-prone.

## Target Users

- **Primary:** Students and professionals preparing for technical interviews (on-site, remote, coding bootcamp assessments).
- **Secondary:** Educators creating problem sets and model solutions.
- **Use case:** Submit a problem description → receive a comprehensive editorial with multiple solution approaches, tested code in Python and Go, and clear explanations in Russian (for Russian-speaking learners).

## Core Value

**Correctness of the generated solution—verified by executing Python and Go code against actual test cases—matters more than explanation quality or speed.** The editorial is only useful if users can trust that the provided code actually works.

## Goals

1. **Automate solution generation:** Users submit a problem once; the system produces a complete multi-approach editorial without manual effort.
2. **Ensure correctness:** Generated code is executed against test cases; incorrect solutions are corrected or marked as failed, not published.
3. **Provide multiple approaches:** Offer at least one brute-force and one optimized approach, with clear trade-off explanations.
4. **Support Russian learners:** Final editorial is always in Russian, regardless of input language.
5. **Interactive ambiguity handling:** When a problem statement is unclear, ask the user for clarification rather than making assumptions.

## Non-Goals

- Authentication / multi-user accounts (deferred to Phase 2 of future work)
- Sandboxed execution environment (security hardening deferred)
- Kubernetes deployment (v1 uses Docker Compose)
- Observability/tracing tools
- Evaluation/benchmarking framework
- Search/filtering across past editorials

## Requirements & User Stories

### Intake

**INTAKE-01: Submit a Problem**
- *As a* student, *I want to* submit a problem description (text + optional examples), *so that* the system can analyze it and generate solutions.
- **Acceptance Criteria:**
  - API accepts POST /api/v1/tasks with problem_text, language ("en" or "ru"), examples array.
  - API responds with 202 Accepted, task_id, and initial status (queued).
  - Problem text is stored durably in Postgres.

**INTAKE-02: Problem Analysis**
- *As a* student, *I want the* system to extract constraints and intent from my free-text problem, *so that* the solution is actually relevant to what I meant.
- **Acceptance Criteria:**
  - Problem Analyzer node parses problem_text and outputs a structured ProblemAnalysis (problem statement, constraints, input/output format).
  - Analysis is persisted to Garage.

**INTAKE-03: Difficulty Rating**
- *As a* student, *I want* the editorial to include a difficulty rating (Easy/Medium/Hard), *so that* I know the problem's scope.
- **Acceptance Criteria:**
  - Problem Analyzer assigns a difficulty value; Editorial includes it.

**INTAKE-04: Clarification on Ambiguity**
- *As a* student, *I want the* system to ask me for clarification when the problem is ambiguous, *instead of* guessing and publishing a wrong solution.
- **Acceptance Criteria:**
  - If Analyzer detects ambiguity, task transitions to awaiting_clarification.
  - A clarification_question field is set in the task record.
  - User can see the question via GET /api/v1/tasks/{id}.

**INTAKE-05: Resume from Clarification**
- *As a* student, *I want to* submit my clarification answer and have the task resume from its checkpoint, *so that* I do not lose progress.
- **Acceptance Criteria:**
  - API provides POST /api/v1/tasks/{id}/clarification with the answer text.
  - Task resumes from the LangGraph checkpoint, continuing the pipeline with the clarified context.

### Strategy & Solving

**STRAT-01: Multiple Solution Approaches**
- *As a* student, *I want to* see multiple solution approaches (brute-force, optimized, alternative), *so that* I understand the trade-offs.
- **Acceptance Criteria:**
  - Solution Strategist node proposes 1+ distinct approaches, each tagged with a technique.
  - Each approach is solved, coded, tested, and reviewed independently.

**STRAT-03: Technique Tags**
- *As a* student, *I want each* approach tagged with its technique (e.g., two pointers, dynamic programming), *so that* I can learn the underlying concept.
- **Acceptance Criteria:**
  - Strategist assigns a technique tag per approach.
  - Editorial includes all technique tags.

**STRAT-04: Single Generic Solver**
- *As a* system designer, *I want* one generic Solver agent (not one per algorithm type), *so that* the system is maintainable and extensible.
- **Acceptance Criteria:**
  - Solver node accepts an Approach from Strategist and elaborates it into a detailed algorithm (not specialized per problem class).

### Code Generation & Execution

**CODE-01/CODE-02: Python & Go Implementations**
- *As a* student, *I want* working Python and Go implementations for each approach, *so that* I can adapt the solution to my language of choice.
- **Acceptance Criteria:**
  - Code Generator produces syntactically valid Python and Go code per approach.
  - Code runs without syntax errors (grammar validated by compilation/import).

**CODE-03/CODE-04: Test Cases**
- *As a* student, *I want* the system to test the code against examples and edge cases, *so that* I trust the solution works.
- **Acceptance Criteria:**
  - Test Generator incorporates provided examples and generates additional edge-case tests (min 10 total).
  - All tests are persisted and executable.

**EXEC-01/EXEC-02: Python & Go Execution**
- *As a* system, *I want to* actually run the generated code and verify it passes tests (not just hope), *so that* incorrect solutions are caught.
- **Acceptance Criteria:**
  - Python Executor tool runs Python code against tests via subprocess; returns pass/fail per test.
  - Go Executor tool compiles Go code and runs it; returns pass/fail per test.
  - Execution results are structured (ExecutionResult with per-test breakdown).

**EXEC-03: Swappable Execution**
- *As a* system maintainer, *I want* executor tools to be swappable (subprocess today, sandbox later), *so that* security hardening does not break agent logic.
- **Acceptance Criteria:**
  - Executors implement a common interface (take code + tests, return ExecutionResult).
  - Agent nodes use executors via tools, not direct subprocess calls.

### Review & Correction

**REV-01/REV-02: Correctness Review**
- *As a* system, *I want* a Reviewer agent to evaluate correctness, edge cases, and complexity, *so that* flawed solutions are caught and fixed.
- **Acceptance Criteria:**
  - Reviewer node assesses correctness (execution results), algorithm soundness, edge-case coverage, and complexity claim.
  - Returns a structured ReviewResult (passed: bool, issues: list, required_changes: str).

**REV-03: Complexity Justification**
- *As a* reviewer, *I want* complexity claims to have reasoning, not just Big-O notation, *so that* I can verify the claim is sound.
- **Acceptance Criteria:**
  - Solver outputs Big-O with a one-sentence justification.
  - Reviewer asks Solver to justify the claim if suspicious.

**REV-04/REV-05: Bounded Correction Loop**
- *As a* student, *I want* failing solutions to be automatically corrected, but not indefinitely, *so that* stuck tasks time out instead of running forever.
- **Acceptance Criteria:**
  - Failed review routes back to Solver with prior context (up to max_iterations = 5 times).
  - After max_iterations, task status = FAILED and no more retries occur.
  - Error message states why the task failed.

### Editorial & Output

**EDIT-01: Russian Editorial**
- *As a* Russian-speaking student, *I want* the final editorial in Russian regardless of my input language, *so that* I can learn in my native language.
- **Acceptance Criteria:**
  - Editorial Writer node outputs Russian-language text.
  - All explanations, algorithm descriptions, and notes are in Russian.

**EDIT-02: Editorial Structure**
- *As a* student, *I want each* approach in a clear structure (Intuition → Algorithm → Code → Complexity), *so that* I can follow the logic.
- **Acceptance Criteria:**
  - Editorial object contains editorial_approaches array.
  - Each approach has intuition, algorithm, python_code, go_code, complexity, edge_cases fields.

**EDIT-03: Approach Progression**
- *As a* student, *I want* approaches ordered logically (brute-force → optimized) with explanations of why each is better, *so that* I understand the evolution of the solution.
- **Acceptance Criteria:**
  - Approaches are presented in sequential order.
  - Editorial notes explain the trade-off between approaches (bridging text).

**EDIT-04/EDIT-05: Metadata & Edge Cases**
- *As a* student, *I want* the editorial to include difficulty, technique tags, and explicitly handled edge cases, *so that* I do not miss important considerations.
- **Acceptance Criteria:**
  - Editorial includes difficulty, techniques array, and per-approach edge_cases list (from Reviewer).

**EDIT-06: Clarification Reflection**
- *As a* student, *I want* any clarification I provided to be reflected in the problem restatement, *so that* the editorial is unambiguous.
- **Acceptance Criteria:**
  - If a clarification round occurred, the final problem_statement includes the resolved interpretation.

### Orchestration & Infrastructure

**ORCH-01: LangGraph Pipeline**
- *As a* system, *I want* the full pipeline (Analyzer → Strategist → Solver → Code Gen → Test Gen → Executors → Reviewer → correction loop → Editorial Writer) as a single deterministic LangGraph StateGraph, *so that* execution is reproducible and checkpointed.
- **Acceptance Criteria:**
  - StateGraph with deterministic edges (no free LLM-driven routing).
  - Parent graph fans out per-approach branches; all branches execute in parallel.
  - LangGraph checkpoints execution state to Postgres; interrupted tasks resume from checkpoint.

**ORCH-02/ORCH-03/ORCH-04: Validation & Config**
- *As a* developer, *I want* all inter-node data validated by Pydantic, per-agent model configuration, and persistent checkpoints, *so that* the system is robust and observable.
- **Acceptance Criteria:**
  - Every node input/output validated by Pydantic schema.
  - Each agent reads its {agent}_model env var; falls back to default_model.
  - LangGraph checkpoints persisted to Postgres; resumption via thread_id = task_id.

**API-01/API-02/API-03: REST API**
- *As a* client, *I want* REST endpoints to create tasks, query status, and submit clarification, *so that* I can interact with the system.
- **Acceptance Criteria:**
  - POST /api/v1/tasks accepts problem submission, returns 202 + task_id.
  - GET /api/v1/tasks/{id} returns current task state.
  - POST /api/v1/tasks/{id}/clarification accepts clarification answer.

**API-04/API-05: WebSocket Live Stream**
- *As a* client, *I want* live status updates via WebSocket, including a current-state snapshot on connect, *so that* I can watch progress in real-time.
- **Acceptance Criteria:**
  - WS /api/v1/tasks/{id}/events opens a connection and streams status transitions.
  - On connect, client immediately receives a snapshot (current status, result if completed).
  - Subsequent transitions are streamed as events.

**QUEUE-01/DATA-01: Postgres + Redis Queue**
- *As a* system, *I want* taskiq + Redis as the task queue and Postgres as the source of truth, *so that* tasks are durable and progress is authoritative.
- **Acceptance Criteria:**
  - Task submission enqueues via RedisStreamBroker.
  - Worker dequeues and executes; status written to Postgres is the single source of truth.
  - If worker crashes, unacknowledged tasks are reclaimed and reprocessed.

**DATA-02: Garage Artifact Storage**
- *As a* system, *I want* intermediate artifacts (analysis, code, tests, reviews, editorial) persisted to Garage S3-compatible storage, *so that* artifacts survive task completion and can be audited.
- **Acceptance Criteria:**
  - All intermediate artifacts written to Garage with task_id-based keys.
  - Final result includes artifact_keys array listing all written keys.
  - Task result links to editorial.json in Garage.

### Frontend & User Experience

**UI-01: Problem Input Form**
- *As a* student, *I want* a simple form to enter a problem description and optional examples, *so that* I can submit without complex setup.
- **Acceptance Criteria:**
  - Web UI provides a textarea for problem_text, dropdown for language (en/ru), and dynamic list for examples (input/output pairs).
  - Submit button sends the problem to the API.

**UI-02: Live Status View**
- *As a* student, *I want* to see the task progress updating live (status badge, elapsed time), *so that* I can monitor the run without polling.
- **Acceptance Criteria:**
  - Web UI connects to WS /api/v1/tasks/{id}/events and renders status transitions.
  - Status badge updates as events arrive (queued → analyzing → ... → completed).

**UI-03: Clarification Prompt**
- *As a* student, *I want* a modal to appear when the system asks a clarification question, *so that* I can answer without losing context.
- **Acceptance Criteria:**
  - UI detects awaiting_clarification status and displays a non-dismissible modal with the question.
  - Submit button sends the answer via POST /api/v1/tasks/{id}/clarification.

**UI-04: Editorial Display**
- *As a* student, *I want* to view the final editorial with all approaches, code blocks (syntax-highlighted, copyable), and explanations, *so that* I can study the solution offline.
- **Acceptance Criteria:**
  - Web UI displays Editorial object with all approaches in sequence.
  - Python and Go code blocks are syntax-highlighted and have copy-to-clipboard buttons.
  - Each approach shows intuition, algorithm, complexity, and edge cases.

### Infrastructure

**INFRA-01/INFRA-02: Tooling & Deployment**
- *As a* developer, *I want* Python 3.14 + uv, single package structure, and Docker Compose for local dev, *so that* development and deployment are friction-free.
- **Acceptance Criteria:**
  - Single uv-managed Python package with modular structure (agents/, api/, worker/, schemas/, tools/).
  - docker-compose.yml brings up API, worker, Postgres, Redis, Garage, frontend, nginx in one command.

**INFRA-03/INFRA-04: Resilience**
- *As a* system, *I want* timeouts and rate-limit retries for OpenAI, a global timeout on task execution, and correction loop bounds, *so that* tasks terminate cleanly instead of hanging.
- **Acceptance Criteria:**
  - OpenAI timeout/rate-limit errors trigger exponential backoff retry (up to 5 attempts).
  - Global timeout of 20 minutes prevents infinite task execution.
  - Correction loop capped at 5 iterations.

**INFRA-05: Documentation**
- *As a* contributor, *I want* comprehensive docs (PRD, architecture, development guides, implementation plan, deferred items), *so that* the project is maintainable and decisions are justified.
- **Acceptance Criteria:**
  - docs/product/prd.md (this file) explains the product intent and user stories.
  - docs/architecture/{architecture,agents,workflow,data-model}.md describe the system design.
  - docs/plans/implementation-plan.md lists phases and plans.
  - DEFERRED.md lists future-scope items.

---

## Out of Scope

See [DEFERRED.md](../../DEFERRED.md) for the full list of acknowledged but deferred features (authentication, sandboxing, Kubernetes, observability, evaluation framework, etc.). These are not deprioritized due to feasibility, but explicitly deferred to a later milestone to keep v1 focused on core correctness.
