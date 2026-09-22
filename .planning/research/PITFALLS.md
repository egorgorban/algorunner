# Pitfalls Research

**Domain:** Multi-agent LLM pipeline producing verified algorithmic editorials (subprocess code execution, LangGraph orchestration, taskiq/Redis/FastAPI/WebSocket infra, bilingual EN/RU input->RU output)
**Researched:** 2026-09-22
**Confidence:** MEDIUM (web sources are mostly LOW-confidence/unverified individually, but findings were cross-checked against multiple independent sources and, for LangGraph, against official docs via Context7 at MEDIUM confidence — see Sources)

## Critical Pitfalls

### Pitfall 1: "No sandbox yet" quietly becomes "no safety net at all"

**What goes wrong:**
Teams read "sandboxing deferred to a later milestone" as license to run `subprocess.run(python_code)` / `go run generated.go` with no limits at all. The first LLM-generated solution with an accidental infinite loop (very common — off-by-one in a `while` condition, wrong loop-invariant on a binary search) hangs a worker forever, or a solution that allocates an unbounded list explodes host memory, or a runaway process becomes a zombie that nobody reaps and slowly exhausts the process table.

**Why it happens:**
"No sandbox" (Docker/gVisor/firecracker-level isolation) and "no minimum-viable safety net" (timeouts, resource limits, process-group kill, non-root, temp-dir isolation) get conflated. The PROJECT.md correctly defers the former but the latter is not optional even for v1 — it's the difference between "worker occasionally slow" and "worker permanently wedged, task queue backs up, whole system down."

**How to avoid:**
Build the safety net as a fixed checklist baked into `PythonExecutorTool`/`GoExecutorTool` from phase 1, not as an afterthought:
- Wall-clock timeout on every subprocess call (`subprocess.run(..., timeout=N)` for Python; `context.WithTimeout` + `exec.CommandContext` for the Go tool invocation) as a backstop even if you also set CPU limits.
- `resource.setrlimit` in a `preexec_fn` (Python) before exec: `RLIMIT_CPU` (wall/CPU seconds), `RLIMIT_AS` (address space / memory), `RLIMIT_NOFILE` (fd count), `RLIMIT_NPROC=0` (blocks `fork()` — kills fork-bomb risk outright). Avoid `RLIMIT_FSIZE=0` — it SIGKILLs on any write including stderr, which looks like a mysterious silent kill.
- Spawn the child in its own process group (`start_new_session=True` in Python `Popen`; `SysProcAttr{Setpgid: true}` in Go) so a timeout/kill can `os.killpg`/`syscall.Kill(-pgid, ...)` the entire group — killing only the top-level PID leaves runaway grandchildren (and, for `go run`, the actual compiled binary) alive as orphans.
- Always reap: call `.wait()`/`.join()` after kill, in a `finally`. Otherwise killed processes become zombies that accumulate and eventually hit the OS per-user PID limit, which then fails unrelated tasks with a confusing "cannot fork" error days after the real cause.
- Run the executor as a dedicated non-root, low-privilege OS user/container user. Root inside a container can still escape unexpected boundaries (e.g. remounting or writing files outside the intended temp dir), so "runs as root" quietly cancels out most of the other mitigations.
- One `tempfile.mkdtemp()` per execution, delete unconditionally in a `finally`/`defer`, and never write executed code adjacent to real repo/app files.

**Warning signs:** worker CPU pinned at 100% with no corresponding task progressing; `ps` shows growing `<defunct>` (zombie) entries; disk usage in `/tmp` creeping up over days; "cannot fork" or "resource temporarily unavailable" errors appearing in unrelated code paths.

**Phase to address:** The phase that builds PythonExecutorTool/GoExecutorTool (early — this is core-value-critical since correctness verification depends on execution actually completing and returning, not hanging the worker).

---

### Pitfall 2: `go run` timeout kills the wrong process, binary keeps running

**What goes wrong:**
`go run` is itself a wrapper: it compiles to a temp binary under the go tool's control and then execs it as a child. If the Go executor tool kills only the top-level "go run"/`go build && ./binary` parent process on timeout (the natural first implementation), the actual compiled binary — the one that might contain the infinite loop or goroutine leak from the generated code — can be left running as an orphan, continuing to consume CPU/memory indefinitely and never being reported back as "timed out."

**Why it happens:** `exec.CommandContext`/`cmd.Process.Kill()` in Go, or Python's `subprocess.run(["go", "run", ...], timeout=N)`, only signal the direct child PID by default. Process groups aren't automatic.

**How to avoid:** Set `SysProcAttr{Setpgid: true}` when invoking the Go toolchain (whether the caller is Python's subprocess module targeting `go run`, or the executor is itself written in Go) and kill the whole process group (`-pgid`) on timeout, not just the parent PID. Prefer `go build` to a known binary path followed by executing that binary directly under your own process-group control (rather than `go run`), so you know exactly which PID tree needs to die and can separately time-box compile vs. execute.

**Warning signs:** host process count grows over time even though task throughput looks bounded; `go run` processes reported as "killed" in logs but `ps aux | grep <binary-name>` still shows the compiled binary running.

**Phase to address:** GoExecutorTool implementation phase.

---

### Pitfall 3: Go module resolution breaks because generated code has no `go.mod`

**What goes wrong:** LLM-generated Go code is a single file/snippet with no module context. Running `go build`/`go run` directly against it in an arbitrary temp directory fails with module-resolution errors (`go.mod file not found`, or it picks up an unrelated `go.mod` from a parent directory if the temp dir happens to be nested inside one), or — worse — silently resolves against whatever module happens to be nearest on disk, pulling in unintended dependencies or Go version constraints.

**Why it happens:** Go's module-aware build requires a `go.mod` scoping every build; generated code produced by an LLM as raw text has none, and this is easy to miss until the first Go executor run in an integration environment (as opposed to a quick manual `go run file.go` on the developer's machine, which can behave differently depending on `GO111MODULE`/ambient module state).

**How to avoid:** Pre-seed a minimal template module (fixed `go.mod` with a pinned Go version and zero/minimal dependencies) per execution's temp directory, write the generated code into that scaffold, and run `go build`/`go run` from inside it — don't rely on ambient GOPATH/module discovery. Point `GOCACHE` (and `GOMODCACHE` if any deps are ever allowed) at a writable, per-container path explicitly — the stock `golang` Docker image's default cache location is not always writable by a non-root user, producing `permission denied`/`failed to initialize build cache` errors that look unrelated to the actual generated code.

**Warning signs:** intermittent "go.mod not found" or "ambiguous import" errors that don't reproduce locally; build failures concentrated on a specific host/container that has a different ambient Go environment.

**Phase to address:** GoExecutorTool implementation phase; template scaffold should be a fixed asset checked into the repo, not generated at runtime.

---

### Pitfall 4: LLM-generated tests validate the model's own blind spots, not correctness

**What goes wrong:** The Test Generator (same family of model as the Code Generator/Solver) produces tests that the generated solution passes — but those tests systematically under-exercise exactly the edge cases the model itself is prone to getting wrong (off-by-one boundaries, empty/singleton inputs, duplicate values, negative numbers, integer overflow-adjacent sizes). The Reviewer then sees "all tests pass" and treats that as strong correctness evidence when it is weak evidence, because the tests and the code share the same generative blind spots.

**Why it happens:** This is a documented phenomenon, not a hypothetical: research on LLM-generated tests shows meaningfully weaker fault-detection than human-written tests under mutation testing, and models solving competitive-programming problems score noticeably better against their own self-generated tests than against independent test suites — the test generation and code generation share failure correlation because they come from the same source distribution.

**How to avoid:**
- Always require the Test Generator to include the problem's given/provided examples verbatim as tests (they are the one source not subject to model bias) and treat them as non-negotiable pass criteria.
- Have the Test Generator work from an explicit edge-case checklist derived from the problem's stated constraints (empty input, min/max size, duplicate/negative/zero values, boundary of any stated numeric range) rather than "generate N more tests" — a checklist-driven prompt is measurably harder for the model to satisfice than an open-ended one.
- Consider generating tests from the Problem Analyzer's structured constraints (independent of the Code Generator's specific implementation) rather than from the same context window that produced the solution, to reduce shared-blind-spot correlation.
- Treat "all generated tests pass" as necessary but not sufficient in the Reviewer's correctness judgment — the Reviewer prompt should explicitly ask "do these tests actually exercise the constraints stated in the problem?" as a distinct check, not just "did tests pass?".

**Warning signs:** review pass rate suspiciously high across many problems; user-reported bugs concentrated on inputs "everyone knows" are edge cases (empty array, single element, all-equal elements) that supposedly-passing solutions get wrong.

**Phase to address:** Test Generator phase and Reviewer phase — the mitigation is a Reviewer prompt-design responsibility working in concert with the Test Generator's prompt, so both should be scoped/reviewed together.

---

### Pitfall 5: Complexity claims are asserted, not verified — Reviewer must check reasoning, not the string

**What goes wrong:** The project explicitly defers empirical complexity verification. Without a specific Reviewer mitigation, this collapses to "trust the model's stated Big-O" — and models are known to state a plausible-looking but infeasible complexity for a given problem (asserting an achievable-sounding bound even when no algorithm meeting it can exist for that problem shape), especially under pressure to look "optimized." A confidently wrong complexity claim published in the final Russian editorial is a direct hit to the product's core value proposition (correctness matters most).

**Why it happens:** Without execution-based verification, complexity is a claim about behavior on inputs the system never actually runs at scale, and LLMs are prone to pattern-matching "this shape of problem usually gets O(n log n)" without re-deriving it from the actual code's loop/recursion structure.

**How to avoid:** Make the Reviewer's `ReviewResult` complexity check structural, not just a claim-echo: require the review reasoning to explicitly walk the generated code's loop nesting depth, recursion branching factor/depth, and any data-structure operation costs (e.g. "is this a set/dict membership check or a list scan?") and match that walk to the stated complexity — i.e. force a chain-of-reasoning complexity re-derivation as part of the ReviewResult schema (a required `complexity_reasoning` field, not just `complexity_claim: str` + `passed: bool`). This doesn't replace empirical verification but makes a wrong claim require the Reviewer to make an internally inconsistent argument to pass it, which is more likely to be caught (by the Reviewer model itself or in later manual QA) than an unexamined assertion.

**Warning signs:** complexity claims that don't obviously match the code's visible loop structure (e.g. claims O(n) with a nested loop over the input); the Reviewer's structured output has a `complexity` pass/fail but no reasoning trace to audit.

**Phase to address:** Reviewer / ReviewResult schema design phase — this is a schema-shaping decision (what fields ReviewResult requires), so it must be decided before the correction loop is wired up, not retrofitted.

---

### Pitfall 6: LangGraph's `recursion_limit` counts super-steps, not "correction attempts"

**What goes wrong:** The correction loop (Solver → CodeGen → TestGen → Execute → Review → back to Solver) is designed with an app-level `max_iterations` of 3-5. But LangGraph enforces its own `recursion_limit` (default 25) counted in graph super-steps — not in units of "one full correction cycle." If a single correction cycle spans 4-5 graph nodes, the graph-level limit is reached after only ~5-6 cycles, independent of and potentially in conflict with the intended app-level bound. If the app-level counter is set higher than what the graph-level limit actually allows, the pipeline fails with an opaque `GraphRecursionError` instead of the intended clean `FAILED` result — a materially different (and worse) failure UX and a bug that only appears once someone actually exercises multiple correction rounds.

**Why it happens:** The two counters are conceptually similar ("don't loop forever") but live at different granularities and neither framework surfaces the mismatch by default.

**How to avoid:** Explicitly compute and set `recursion_limit` in the graph invocation config as a function of `(nodes per correction cycle) * max_iterations + fixed overhead`, don't leave it at the LangGraph default. Enforce the actual `max_iterations` bound as application state (an explicit iteration counter field checked in a conditional edge) that produces the clean `FAILED` result *before* the graph-level limit could ever be hit — the graph-level limit should only ever be a last-resort safety net that should never actually trigger in normal operation, and if it does trigger, that's a bug to fix, not the intended failure path.

**Warning signs:** `GraphRecursionError` appearing in logs/task failures instead of a structured `FAILED` result with `required_changes`/`issues`; correction loop tests that pass at `max_iterations=3` but break when experimenting with `max_iterations=6-8`.

**Phase to address:** LangGraph orchestration/state-graph phase, specifically when wiring the correction loop's conditional edges.

---

### Pitfall 7: State reducers turn the correction loop into unbounded checkpoint growth

**What goes wrong:** LangGraph state fields declared with accumulating reducers (e.g. `Annotated[list, add]`, or `add_messages`-style channels) append rather than overwrite on every node write. If review history, per-attempt generated code, or per-attempt test results are modeled this way (a natural first design, since "keep prior attempts for context" sounds reasonable), every correction iteration grows that field, and the *entire accumulated state* is persisted at *every* super-step checkpoint (PostgreSQL-backed). For a task with several solution approaches, each retried 3-5 times, checkpoint storage and the resulting DB size/row payload grow multiplicatively — and there's no automatic pruning: LangGraph's own docs explicitly recommend a manual cron job to delete old checkpoints, because none is provided by default.

**Why it happens:** Reducer-based accumulation is the idiomatic LangGraph pattern for "remember conversation history," and it's easy to reach for the same pattern for "remember correction attempts" without realizing the persistence cost compounds per checkpoint, not just in final state.

**How to avoid:** Be deliberate about which state fields actually need cross-iteration accumulation (e.g. the Reviewer plausibly needs the *previous* review's issues to inform the next correction, but does it need *every* prior attempt's full code, or just the most recent one plus a short structured issues list?). Default to overwrite-semantics for large fields (generated code, generated tests) and reserve accumulation only for small structured summaries (e.g. `list[ReviewIssue]` capped/truncated, not full code snapshots). Set up the checkpoint-pruning cron job (delete checkpoints for completed/failed tasks older than N days) as part of the initial PostgreSQL/LangGraph persistence setup, not as a later hardening task — this is explicitly called out as required operator work by LangGraph's own documentation, not an edge case.
Also: keep `thread_id` short and fixed-format (e.g. UUID) — PostgresSaver enforces a 255-character limit and raises DB errors above it, which is an easy trap if thread_id is ever derived from a natural key.

**Warning signs:** PostgreSQL checkpoints table growing faster than task volume would suggest; task resume/replay operations getting slower over the life of a long-running task; DB errors referencing `thread_id` length on tasks with unusually long identifiers.

**Phase to address:** LangGraph state-schema design phase (Pydantic state models) — reducer choice per field is a schema decision that's expensive to change once the correction loop and checkpointing are both live.

---

### Pitfall 8: taskiq + Redis result backend has a "worker died, did the task finish?" blind spot

**What goes wrong:** A worker crashes (OOM-killed by the host, container restarted, process killed) while executing a task. Depending on the broker/result-backend combination: (a) if using a non-acknowledging Redis broker, the task message itself can simply be lost — nobody re-enqueues it and it silently disappears from the queued/running view; (b) even with a durable broker, a client polling for the task result during/around the crash window gets an ambiguous "no result yet" that looks identical to "still running normally," so naive status logic can either wrongly report the task as still in-progress forever, or wrongly mark it failed for a task that (rarely) actually did finish and write its result microseconds before or after the check.

**Why it happens:** taskiq's own documentation and issue tracker note that some Redis-backed brokers provide no acknowledgement semantics (message is considered delivered once handed to a worker, regardless of whether it completes), unlike stream-based or AMQP-based brokers which support acks/redelivery.

**How to avoid:** Use `taskiq-redis`'s stream-based broker (Redis Streams with consumer groups/acks) rather than a plain pub/sub-style broker if task durability across worker crashes matters — for AlgoRunner it does, since a "lost" task means the user's request silently vanishes with no error surfaced. Independently of broker choice, the source of truth for task status must be the PostgreSQL task-state row (already planned per PROJECT.md), updated by the worker at each pipeline stage transition — not solely inferred from Redis result-backend presence/absence. On worker startup/recovery, reconcile: any task left in a non-terminal PostgreSQL status with no active worker heartbeat past a timeout should be explicitly re-queued or marked FAILED by a watchdog, rather than left in limbo indefinitely.

**Warning signs:** tasks stuck in "processing"/intermediate status in the UI indefinitely with no further WebSocket events; task counts in Redis and PostgreSQL diverging over time.

**Phase to address:** Task queue/taskiq integration phase — broker choice and the worker-crash reconciliation watchdog should be designed together, since retrofitting durability semantics after choosing a lossy broker means a broker migration later.

---

### Pitfall 9: WebSocket clients that connect late miss earlier status transitions

**What goes wrong:** The pipeline status stream (`queued → analyzing_problem → ... → completed/failed`) is naturally implemented as "worker publishes each transition, API relays to connected WebSocket clients." If the publish mechanism is plain Redis pub/sub (the default, simplest choice), any transition published before a given client connects (or during a brief client reconnect gap) is gone forever for that client — pub/sub has no history/replay. A user who opens the task's status page a few seconds after submission (very likely, since the API returns immediately with `202 Accepted` and the user then navigates to a status view) can miss `queued → analyzing_problem` entirely and see a confusing jump straight to a later state, or nothing at all until the next transition fires.

**Why it happens:** Redis pub/sub is fire-and-forget by design; it was not built for "catch a new subscriber up on history."

**How to avoid:** On WebSocket connection, before subscribing to live pub/sub events, always fetch and send the task's *current* full status from PostgreSQL (the source of truth) as an initial synthetic event — this guarantees a newly-connected or reconnecting client always sees at least the current state, even if all intermediate transitions were missed. If a full transition history/timeline in the UI matters (not just "current state"), persist each transition as a row (task_id, status, timestamp) rather than relying on pub/sub as the only record, and serve history via a REST endpoint the client calls on connect. This also naturally solves the "worker crashed, WebSocket shows stale state forever" case from Pitfall 8, since the client can re-fetch current state on any reconnect.

**Warning signs:** UI status view shows a status that doesn't match `GET /api/v1/tasks/{id}`'s current value; users reporting "it looked stuck" for tasks that actually completed.

**Phase to address:** WebSocket API phase — the "send current state on connect, then stream deltas" pattern must be the initial design, not a bugfix bolted on after users report confusing state.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Run generated Python/Go with only a wall-clock timeout, no `setrlimit`/process-group kill | Faster to build, "works in the demo" | Memory-hungry or forking generated code can take down the whole worker host, not just the one task | Never — this is the minimum viable net, not an extra |
| Model review history/generated-code attempts with accumulating LangGraph reducers | Simple mental model ("just keep everything") | Checkpoint size and DB storage scale with iteration count x approaches; slows resume/replay over a task's life | Only for small, capped structured fields (e.g. last N issues), never for full code/test payloads |
| Treat "generated tests pass" as sufic correctness evidence in the Reviewer | Simpler Reviewer prompt, fewer review failures to handle | False sense of correctness on exactly the edge cases users hit in practice | Never as the sole signal — must be combined with provided-example tests + constraint-derived edge-case checks |
| Accept the LLM's stated Big-O without requiring a reasoning trace in ReviewResult | Faster Reviewer implementation, simpler schema | Wrong complexity claims ship in the final Russian editorial — a direct hit to stated core value ("correctness matters more than explanation quality") | Never for v1 given the product's own stated priority; acceptable only if complexity review is explicitly marked "best-effort" in user-facing copy |
| Use Redis plain pub/sub for WebSocket status fanout without a "send current state on connect" fallback | Less code, matches most FastAPI+Redis tutorials | Clients that connect a few seconds late (the common case, since task creation returns immediately) silently miss early transitions | Acceptable only if paired with the fetch-current-state-on-connect pattern from day one — not acceptable standalone |
| Use taskiq-redis's simplest/default broker without checking ack semantics | Fewer moving pieces to configure initially | Worker crash mid-task can silently lose the task with no user-facing error | Acceptable only for a personal/dev environment, not for anything resembling "production-ready" per the project's own framing |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|-------------------|
| Go toolchain (`go build`/`go run`) invoked from Python via subprocess | Assuming a bare temp directory with a `.go` file is buildable | Pre-seed a template `go.mod` per execution temp dir; point `GOCACHE`/`GOMODCACHE` at an explicitly writable path |
| taskiq + Redis | Treating "no result found in backend" as equivalent to "task failed" | Source of truth is PostgreSQL task-state row updated at each stage; Redis result backend is a cache/transport, not the record of truth |
| FastAPI WebSocket + Redis pub/sub | Streaming only live deltas from the moment of `subscribe()` | Always emit current full state from PostgreSQL as the first message on every connect/reconnect |
| LangGraph + PostgreSQL checkpointer | Assuming checkpoints self-clean | Explicit cron/scheduled job to prune checkpoints for completed/failed tasks past a retention window; this is called out as required by LangGraph's own docs |
| OpenAI API per-agent model config | Assuming rate-limit/timeout handling is uniform across "cheap" and "strong" model tiers | Backoff/retry and per-model timeout tuning should be configured per model tier — cheaper/faster models and stronger/slower reasoning models have different realistic latency envelopes |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Unbounded correction-loop state accumulation (Pitfall 7) | Checkpoint reads/writes slow down over a task's lifetime; DB row/JSON payload size grows | Overwrite-semantics for large fields, cap/truncate accumulating fields, prune checkpoints | Noticeable once a task has gone through several approaches x several correction rounds each — could already be visible in normal v1 usage, not just at scale |
| Fast worker event publishing vs. slow WebSocket client | Per-connection outbound buffer grows, memory pressure on the API process | Monitor/bound outbound buffer size; coalesce rapid status events if needed | At higher concurrent task volume with many simultaneously-connected status viewers |
| Sequential per-approach code-execution (Python then Go, per solution approach, per correction iteration) with no concurrency limit | Total task wall-clock time balloons as more approaches/iterations are attempted | Bound total task time via the already-planned global timeout; consider running independent approaches' executor calls concurrently if resource limits allow | Once task volume is high enough that worker throughput (not per-task correctness) becomes the bottleneck — likely post-v1 |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Running generated code as the same OS user as the API/worker process | A container/process escape or resource exhaustion from generated code can affect the host application, not just the sandboxed task | Dedicated low-privilege non-root user for the executor subprocess, separate from the app's own runtime user |
| Trusting the Reviewer's `passed: true` as a security signal, not just correctness | Generated code could (accidentally or via prompt injection embedded in a "problem description") attempt filesystem/network access; a correctness-only Reviewer won't catch this | Even pre-sandbox, apply basic static checks (disallowed imports like `os`, `subprocess`, `socket`, `shutil` for the Python side; restrict Go generated code to stdlib-only, no `net`/`os/exec`) before executing, as a cheap complement to real sandboxing later |
| Letting problem-description free text flow unfiltered into prompts across all agents | A malicious/crafted problem description could attempt prompt injection to alter Reviewer behavior or leak system prompts across the pipeline | Treat problem-description input as untrusted content in every agent's prompt (clearly delimited, instructed to be treated as data not instructions), consistent with the existing project practice of protecting agent instructions in this system |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|------------------|
| WebSocket-only status with no state-on-connect fallback | User sees a stuck-looking or inconsistent status if they open/reopen the status view mid-run (Pitfall 9) | Always sync current state from `GET /api/v1/tasks/{id}` semantics on WebSocket connect, then stream deltas |
| Presenting complexity analysis with the same visual confidence regardless of review depth | Users trust an unverifiable complexity claim as if it were benchmarked | Consider a lightweight "analytically reviewed, not empirically benchmarked" note in the editorial output, consistent with the project's own explicit scope decision |
| Silent correction-loop failures surfaced only as a generic FAILED status | User has no idea why their problem couldn't be solved after several minutes of waiting | Surface the Reviewer's final `issues`/`required_changes` (or a user-friendly summary of them) in the FAILED result, not just a bare failure flag |

## "Looks Done But Isn't" Checklist

- [ ] **PythonExecutorTool/GoExecutorTool:** Often missing process-group kill and reaping on timeout — verify killing a deliberately-infinite-looped generated solution actually frees all resources and leaves no zombie/orphan processes (test this explicitly, don't assume the happy-path timeout test covers it).
- [ ] **Go execution:** Often missing a per-execution `go.mod` scaffold and writable `GOCACHE` — verify by running the executor from a clean container with no ambient Go module state.
- [ ] **Correction loop:** Often missing an explicit reconciliation between app-level `max_iterations` and LangGraph's `recursion_limit` — verify by deliberately forcing max_iterations rounds of failure and confirming a clean `FAILED` result, not a `GraphRecursionError`.
- [ ] **Task status stream:** Often missing "send current state first" on WebSocket connect — verify by connecting a client several seconds after task submission and confirming it doesn't show a stale/blank state.
- [ ] **Worker crash handling:** Often missing any reconciliation for a task whose worker died mid-run — verify by killing a worker process mid-task and confirming the task eventually transitions to FAILED (not stuck forever) via a watchdog or timeout.
- [ ] **Bilingual output:** Often missing a check that code comments actually ended up in the intended language — verify by testing with a Russian-language problem input, an English-language problem input, and confirming both produce Russian comments/explanation with English-only identifiers consistently.
- [ ] **Complexity claims:** Often missing a required reasoning trace behind the Reviewer's complexity pass/fail — verify the `ReviewResult` schema has a structured field forcing the walk-through, not just a boolean.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|-----------------|
| Zombie/orphan processes from ungrouped kills | LOW | Add process-group spawn + killpg/kill(-pgid) to the executor tools; can be patched in isolation without touching agent logic (this is exactly why executors are tools, not agents, per the project's own architecture decision) |
| LangGraph checkpoint bloat from reducer accumulation | MEDIUM | Requires a state-schema migration (changing which fields use reducers) plus a one-time cleanup of existing bloated checkpoints; easier the earlier it's caught |
| Broker message loss on worker crash (lossy Redis broker) | MEDIUM | Swap to `taskiq-redis`'s stream-based broker; requires a broker migration and re-testing durability, but doesn't require pipeline/agent changes |
| Missing "current state on connect" WebSocket pattern | LOW | Additive fix — add an initial state-fetch-and-send on connection handler; doesn't require protocol changes if the message format already supports a full-state message type |
| Reviewer accepting complexity claims without a reasoning trace | MEDIUM | Requires a `ReviewResult` schema change (new required field) and a Reviewer prompt change; any already-stored review history is now "of the old, weaker shape" — acceptable to leave as-is for historical tasks if this is caught early |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|--------------|
| Missing subprocess safety net (timeouts/ulimits/process-group kill/non-root/temp-dir isolation) | PythonExecutorTool/GoExecutorTool implementation phase | Deliberately execute a generated infinite loop and a generated fork-bomb-style snippet in tests; confirm bounded resource use and clean process reaping |
| `go run`/`go build` orphaned binary on timeout kill | GoExecutorTool implementation phase | Kill test with a generated Go program spawning goroutines that never terminate; confirm no orphan process survives |
| Missing `go.mod` scaffold for generated Go code | GoExecutorTool implementation phase | Run the executor in a clean container with no ambient Go state |
| LLM-generated tests biased toward passing the LLM's own code | Test Generator + Reviewer phases (designed together) | Reviewer prompt explicitly checks test coverage against stated problem constraints, not just pass/fail |
| Complexity claims accepted without verification | Reviewer/ReviewResult schema design phase | ReviewResult requires a structured complexity-reasoning field; spot-check against known-tricky problems (e.g. one where naive analysis over-claims optimality) |
| `recursion_limit` vs. app-level `max_iterations` mismatch | LangGraph orchestration/correction-loop wiring phase | Force max_iterations failures in an integration test; confirm clean FAILED result, not GraphRecursionError |
| Checkpoint bloat from accumulating reducers | LangGraph state-schema design phase | Inspect checkpoint row size growth across a multi-iteration correction loop in a test task |
| taskiq/Redis task loss on worker crash | Task queue integration phase | Kill a worker process mid-task in an integration test; confirm the task is not silently lost (reconciled to FAILED or retried, not stuck) |
| WebSocket clients missing early state transitions | WebSocket API phase | Connect a client several seconds after task creation; confirm it receives current state immediately, not just future deltas |
| Bilingual language leakage (English creeping into Russian output/comments) | Editorial Writer + Code Generator prompt design phase | Test with both English and Russian problem inputs; validate comment/explanation language consistency programmatically (e.g. a lightweight language-detection check) as part of the Reviewer or a post-generation check |

## Sources

- [Running Untrusted Python Code — Andrew Healey](https://healeycodes.com/running-untrusted-python-code)
- [Six layers to sandbox untrusted Python — chs.us](https://chs.us/2026/07/sandboxing-untrusted-python/)
- [Python bug tracker: subprocess.kill process group support](https://bugs.python.org/issue5115)
- [os.killpg() — Educative](https://www.educative.io/answers/what-is-oskillpg-method-in-python)
- [Zombie process discussion — comp.lang.python](https://groups.google.com/g/comp.lang.python/c/ueR_ToKHVN0)
- [check_correctness leaves zombie process after timeout kill — rllm-org/rllm#915](https://github.com/rllm-org/rllm/issues/915)
- [GOCACHE workspace scope / temp dir issue — dennisonbertram/go-code#1399](https://github.com/dennisonbertram/go-code/issues/1399)
- [golang:1.10 GOCACHE permission denied — docker-library/golang#225](https://github.com/docker-library/golang/issues/225)
- [Permission Denied for go build — golang/go#29063](https://github.com/golang/go/issues/29063)
- [exec.CommandContext orphaned descendant processes — Go Forum](https://forum.golangbridge.org/t/windows-c-exec-commandcontext-ctx-c-output-dont-return-when-process-is-killed-upon-context-expiration-until-child-termination/26358)
- [Killing child process on timeout in Go — Go Forum](https://forum.golangbridge.org/t/killing-child-process-on-timeout-in-go-code/995)
- [Terminating Processes in Go — Cerebrations](https://bigkevmcd.github.io/go/pgrp/context/2019/02/19/terminating-processes-in-go.html)
- [Large Language Models for Unit Test Generation: Achievements, Challenges, and Opportunities (arXiv)](https://arxiv.org/pdf/2511.21382)
- [Rethinking Verification for LLM Code Generation: From Generation to Testing (arXiv)](https://arxiv.org/html/2507.06920)
- [CodeContests-O: Powering LLMs via Feedback-Driven Iterative Test Case Generation (arXiv)](https://arxiv.org/html/2601.13682)
- [Complexity-Constraint Code Evaluation: A Benchmark for Time Complexity Compliance in LLM-Generated Code — Springer JCST](https://link.springer.com/article/10.1007/s11390-025-5518-5)
- [taskiq getting started docs](https://taskiq-python.github.io/guide/getting-started.html)
- [taskiq wait_result aborts on transient result-backend error — taskiq-python/taskiq#655](https://github.com/taskiq-python/taskiq/issues/655)
- [Worker child not restarted after --max-tasks-per-child — taskiq-python/taskiq#646](https://github.com/taskiq-python/taskiq/issues/646)
- [taskiq-redis README](https://github.com/taskiq-python/taskiq-redis/blob/main/README.md)
- [Scaling Pub/Sub with WebSockets and Redis — Ably](https://ably.com/blog/scaling-pub-sub-with-websockets-and-redis)
- [Replaying Missed Events with Redis Streams — server-sent-events.com](https://www.server-sent-events.com/backend-stream-generation-connection-management/redis-pubsub-fanout-for-sse/replaying-missed-events-with-redis-streams/)
- [FastAPI WebSockets: Production-Ready Setup and Scaling — DEV Community](https://dev.to/ayush_kumar_085a0f2c54e3f/fastapi-websockets-production-ready-setup-and-scaling-45pp)
- [Large Language Models for Code Generation from Multilingual Prompts (arXiv)](https://arxiv.org/html/2607.14816)
- [LangGraph persistence/checkpointers documentation (via Context7, docs.langchain.com/oss/python/langgraph/persistence and /checkpointers)](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph Pregel/reducers documentation (via Context7, docs.langchain.com/oss/python/langgraph/pregel)](https://docs.langchain.com/oss/python/langgraph/pregel)

---
*Pitfalls research for: AlgoRunner (multi-agent algorithmic-editorial generation system)*
*Researched: 2026-09-22*
