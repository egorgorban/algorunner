# Workflow & Execution

## Parent Graph

The top-level LangGraph StateGraph orchestrates the full pipeline with deterministic routing and three major phases:

```
START
  ↓
problem_analyzer_node
  ↓
decide_after_analysis (conditional)
  ├─ ambiguous → clarification_gate_node → interrupt(question) → [pause on awaiting_clarification]
  └─ clear → record_analysis_node
       ↓
       solution_strategist_node
         ↓
         fan_out_approaches (Send multiple branches in parallel)
           ↓
       [Each branch runs independently in the per-approach subgraph]
         ↓
       collect_approaches (fan-in join)
         ↓
       decide_after_join (conditional)
         ├─ no verified → finalize_failed
         └─ at least one verified → editorial_writer_node → finalize_success
           ↓
       END
```

## Per-Approach Subgraph

Each approach executes in isolation via the `approach_subgraph`:

```
solver_node
  ↓
code_generator_node
  ↓
test_generator_node
  ↓
python_executor_tool (concurrent with go_executor_tool)
↓ ↓
go_executor_tool
  ↓
reviewer_node
  ↓
decide_after_review (conditional)
  ├─ passed → outcome_from_final (wrap and return to parent)
  └─ failed & iterations < max_iterations → solver_node [correction loop]
       └─ iterations >= max_iterations → outcome_from_final with FAILED status
```

## Status Transitions

The pipeline emits 12 distinct statuses, each logged to Postgres and published to Redis pub/sub:

| Status | Emitted By | When | File/Function |
|--------|-----------|------|---------------|
| **queued** | API route | Task inserted into Postgres | `api/routes/tasks.py:create_task` |
| **analyzing_problem** | Worker startup | Graph invoked for first time | `worker/tasks.py:solve_problem_stub` |
| **designing_solution** | `record_analysis_node` | Analysis complete, before branching | `graph/build.py:record_analysis_node` |
| **generating_code** | `approach.py` status wrapper | Code Generator node starts | `graph/approach.py:run_approach` |
| **generating_tests** | `approach.py` status wrapper | Test Generator node starts | `graph/approach.py:run_approach` |
| **executing_tests** | `approach.py` status wrapper | Executor tools run | `graph/approach.py:run_approach` |
| **reviewing** | `approach.py` status wrapper | Reviewer node starts | `graph/approach.py:run_approach` |
| **correcting** | `approach.py` status wrapper | Correction loop iterates | `graph/approach.py:run_approach` |
| **awaiting_clarification** | `clarification_gate_node` | Problem ambiguous, needs user input | `graph/build.py:clarification_gate_node` |
| **writing_editorial** | Worker before Editorial Writer | At least one approach verified | `worker/tasks.py:solve_problem_stub` |
| **completed** | `finalize_success` | All artifacts written successfully | `graph/build.py:finalize_success` |
| **failed** | `finalize_failed` or correction max iteration reached | Unrecoverable error or max attempts exceeded | `graph/build.py:finalize_failed` |

## Clarification Pause & Resume

When the Problem Analyzer identifies an ambiguous problem:

1. **Pause:** `clarification_gate_node` calls `interrupt(question)`, moving the task to `awaiting_clarification` status.
2. **User Response:** Frontend displays the modal; user submits an answer via `POST /api/v1/tasks/{id}/clarification`.
3. **Resume:** Worker invokes the graph again with the same `thread_id`. LangGraph checkpoint logic resumes from `clarification_gate_node` with the user's answer in `state["clarification_answer"]`.
4. **Continuation:** The graph proceeds through `record_analysis_node` and continues the pipeline.
5. **Cap:** Up to `clarification_round_cap` (default 2) interactive rounds. After that, the system picks its best interpretation.

## Time Budget

The system enforces two time constraints:

- **Global timeout** (`global_timeout_s`, default 1200s = 20 min): Total elapsed time for the task. If exceeded, task terminates as FAILED.
- **Editorial reserve** (`editorial_reserve_s`, default 240s = 4 min): Time reserved for the Editorial Writer node. Once this reserve is reached, any pending approach branches are killed and the Writer proceeds with only verified approaches.

The budget is enforced via:
- Per-branch soft deadline (publish-before-deadline for fast feedback, catch-and-abandon at reserve time)
- LangGraph `recursion_limit` (counts supersteps; max 25) is reconciled separately with the app-level `max_iterations` (correction loop count)
- Worker sets `active_execution_seconds` in Postgres on every status update for monitoring

## Correction Loop

When the Reviewer fails an approach:

1. **Decision:** `decide_after_review` checks `review.passed`.
2. **If failed:**
   - If `iterations < max_iterations`: route back to `solver_node` with prior attempt context (review issues, previous code).
   - If `iterations >= max_iterations`: route to `outcome_from_final` with status="FAILED".
3. **Iteration counter:** Incremented on each loop; capped at `max_iterations` (default 5).

The loop carries the full `review_history` so each iteration knows why prior attempts failed.

## WebSocket Protocol

### Connection & Subscription

```
Client: WS CONNECT to /api/v1/tasks/{task_id}/events
  ↓
API: Accept connection
  ↓
API: Subscribe to Redis pub/sub channel task:{task_id}:status
  ↓
API: Fetch current task snapshot from Postgres
  ↓
API: Send SNAPSHOT frame to client (see frame format below)
  ↓
Client: Receive SNAPSHOT
  ↓
[Client is now subscribed; ready to receive future status transitions]
```

**Rule:** Client subscribes to Redis *before* querying Postgres to avoid a race where a status transition occurs between the query and the subscription.

### Frame Format

All frames are JSON, sent as text messages:

**Status transition frame:**
```json
{
  "type": "status_change",
  "status": "generating_code",
  "timestamp": "2026-09-25T11:05:23.456Z"
}
```

**Snapshot frame (sent once on connect):**
```json
{
  "type": "snapshot",
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "executing_tests",
  "created_at": "2026-09-25T11:00:00.000Z",
  "updated_at": "2026-09-25T11:05:20.000Z",
  "result": null,
  "error": null,
  "clarification_question": null
}
```

**Deduplication rule:** Client ignores any status frame with `timestamp <= last_received_timestamp` to handle out-of-order or duplicate Redis messages.

**Snapshot refresh:** When the task reaches `awaiting_clarification`, `completed`, or `failed`, the API sends a fresh SNAPSHOT frame (not just a status_change) so the client resyncs the full state (result data for completed; question text for clarification).

### Close Codes

The WebSocket connection closes with one of these codes:

| Code | Meaning | When |
|------|---------|------|
| 1000 | Normal closure | Task completed or failed; client closed gracefully |
| 1011 | Server error | Unexpected exception in handler (e.g., Redis failure) |
| 1013 | Server overloaded | `ws_max_connections` limit reached (too many concurrent WebSocket clients) |
| 4403 | Forbidden | Origin allowlist check failed (see WS guard below) |
| 4404 | Not Found | Task ID not found in Postgres |

**Client reconnection rule:** On 1000, do not reconnect (task is done). On 1011 or 1013, reconnect with exponential backoff. On 4403/4404, do not reconnect (auth/not-found errors).

### Ordering & Interleaving

- Multiple approaches execute in parallel, each emitting statuses (generating_code, generating_tests, executing_tests, reviewing).
- These statuses interleave in Redis pub/sub order, not in approach order.
- Example:
  ```
  [Approach 0] generating_code
  [Approach 1] generating_code
  [Approach 0] generating_tests
  [Approach 1] generating_tests
  [Approach 0] executing_tests
  [Approach 1] executing_tests
  ```
- The client receives this stream in Redis delivery order; UI can render it as a flat timeline or group by approach.

## WebSocket Guards

### Origin Allowlist (WS-02)

The API checks the `Origin` HTTP header on WebSocket handshake:
- If `ws_allowed_origins` is empty (default), all origins are allowed (dev-friendly).
- If non-empty, only origins in the list are accepted; others receive `4403 Forbidden`.

Example:
```
ws_allowed_origins: ["https://mysite.example.com", "http://localhost:3000"]
```

### Connection Cap (WS-03)

The API limits concurrent WebSocket connections per process:
- If current connections >= `ws_max_connections` (default 200), new connections receive `1013 Server Overloaded`.
- Prevents a single client from opening many connections and starving other clients.

## Bounded Corrections & Error Handling

| Scenario | Outcome |
|----------|---------|
| Correction loop reaches `max_iterations` | Status = FAILED; no more retries |
| Global timeout exceeded | Status = FAILED; task terminated immediately |
| Clarification cap reached (2 rounds) | System uses last best interpretation; proceeds without more questions |
| OpenAI API timeout/rate-limit | Retry with exponential backoff (up to `retry_max_attempts`, default 5) |
| Executor crash (Python/Go subprocess dies) | Execution status = FAILED; Reviewer sees no output |
| Garage artifact write fails | Warning logged; task continues; `result.artifacts_incomplete = true` |

All errors are caught and logged; tasks never silently fail or get stuck at non-terminal statuses.
