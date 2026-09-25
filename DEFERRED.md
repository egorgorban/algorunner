# Deferred / Future Scope

This document captures all acknowledged features, requirements, and ideas that are deliberately deferred beyond v1. Nothing listed here is forgotten or deprioritized due to difficulty; rather, these items are *explicitly* out of scope to keep v1 focused on core correctness and user value.

See also: `.planning/PROJECT.md` (Out of Scope), `.planning/REQUIREMENTS.md` (v2 Requirements), and the phase-context files for specific deferred ideas.

---

## Security & Hardening

### SEC-01: Authentication & Multi-User Access

**Description:** User accounts, session management, API key authentication, and multi-user task isolation.

**Why Deferred:** v1 is stateless per-task. Any caller with a task UUID can read or stream that task. Multi-user and session-based workflows require persistent user state, which conflicts with the current stateless design. A later phase will introduce user accounts, saved history, and per-user isolation.

**Estimated Phase:** Phase 5 (user & persistence layer)
**Effort:** L (large)

### SEC-02: Sandboxed Code Execution

**Description:** Docker sandbox or isolated-service execution environment for generated Python and Go code (instead of plain subprocess execution).

**Why Deferred:** v1 executes code via subprocess with resource limits (RLIMIT_CPU, RLIMIT_AS, RLIMIT_NPROC, RLIMIT_NOFILE) and an import denylist. This guards against obvious misuse but is not a true sandbox. True isolation (Docker, seccomp, SELinux, or a dedicated execution service) is a known security hardening step, tracked but deferred to allow v1 to ship sooner.

**Estimated Phase:** Phase 6 (security hardening)
**Effort:** M (medium)

### SEC-03: Resource Limits on Execution

**Description:** Explicit CPU, RAM, execution time, network, and filesystem quotas for generated code (beyond current RLIMIT-only approach).

**Why Deferred:** v1 enforces basic limits via setrlimit. A comprehensive resource-limiting strategy (cgroups, seccomp profiles, network isolation) is deferred alongside sandboxing. These are complementary hardening measures that make sense to implement together.

**Estimated Phase:** Phase 6 (security hardening)
**Effort:** M (medium)

---

## Platform & Infrastructure

### PLAT-01: Kubernetes Deployment

**Description:** Kubernetes manifests, Helm charts, or deployment automation for production-scale deployment (beyond Docker Compose).

**Why Deferred:** v1 is designed for Docker Compose (single-machine or simple orchestration). Kubernetes is appropriate for multi-region, auto-scaling, high-availability deployments. These operational needs are out of scope for a first production release; Kubernetes becomes relevant in Phase 5-6.

**Estimated Phase:** Phase 6 (infrastructure scaling)
**Effort:** L (large)

### PLAT-02: Observability & Cost Tracking

**Description:** Structured logging, Prometheus metrics, OpenTelemetry tracing, LangSmith trace capture, per-request/agent/run OpenAI cost tracking.

**Why Deferred:** v1 logs to stdout/stderr (suitable for Docker Compose dev/test). Production observability (structured logs, metrics, traces) is valuable for cost optimization and debugging at scale, but not essential for the v1 use case (on-demand editorial generation). This is deferred to a later phase when multi-tenant or SaaS operations require detailed observability.

**Estimated Phase:** Phase 5-6 (operations & monitoring)
**Effort:** M (medium)

### PLAT-03: CI/CD & Linting

**Description:** GitHub Actions CI/CD pipeline, pre-commit hooks, ruff (Python linter), mypy/pyright (type checker) enforcement.

**Why Deferred:** v1 prioritizes type safety through Pydantic and careful coding, but does not gate on linting or static analysis tooling. These tools are deferred; code is reviewed by hand and via tests. A future phase will enforce linting and type checking.

**Estimated Phase:** Phase 5 (development hygiene)
**Effort:** S (small)

---

## Product Features

### PROD-01: Cross-Task Memory

**Description:** System remembers a user's previously solved problems, suggesting variations or related problems, and enabling follow-up questions on past editorials.

**Why Deferred:** This requires user accounts (SEC-01) and a curated problem corpus or embedding-based search. Deferred until SEC-01 is implemented.

**Estimated Phase:** Phase 7 (advanced features)
**Effort:** M (medium)

### PROD-02: Follow-Up Variation Prompt

**Description:** After viewing an editorial, user can ask "What if the input doesn't fit in memory?" or similar variation prompts, triggering a new pipeline run with modified constraints.

**Why Deferred:** Variation logic requires understanding the original problem intent and constraints deeply. This is a natural follow-on after multi-approach editorial is solid; deferred to Phase 5-6.

**Estimated Phase:** Phase 5-6 (follow-up capability)
**Effort:** M (medium)

### PROD-03: Review-History Transparency

**Description:** Web UI shows why each correction iteration failed, what changed, and how many iterations were attempted before a solution passed.

**Why Deferred:** The infrastructure for this exists (review_history in ApproachState, approach_outcomes.iterations). UI rendering is deferred until Phase 4 frontend is mature.

**Estimated Phase:** Phase 5 (UI enhancements)
**Effort:** S (small)

### PROD-04: True Interactive Clarifying-Question Chat

**Description:** Multi-turn clarifying-question chat (beyond the current single-round pause/resume) with the system asking follow-ups based on user answers.

**Why Deferred:** v1's clarification uses LangGraph interrupt()/Command, which is designed for single-round pause/resume. True multi-turn chat would require a different state machine. Deferred to Phase 5 when we rethink the clarification loop.

**Estimated Phase:** Phase 5 (interactive features)
**Effort:** M (medium)

---

## Evaluation & Quality

### EVAL-01: Automated Benchmark Suite

**Description:** Evaluation dataset of 1000+ problems with known solutions, automated benchmark measuring solution correctness, code correctness, complexity correctness, explanation quality, pass rate, latency, and token cost.

**Why Deferred:** v1 relies on the LLM's built-in capability and live testing of generated code. A formal evaluation framework requires a curated problem dataset (which does not yet exist) and comparison logic. This is a research-grade addition, deferred to Phase 7.

**Estimated Phase:** Phase 7 (evaluation & benchmarking)
**Effort:** L (large)

### EVAL-02: Automated Version Comparison

**Description:** Metrics comparison across system versions (accuracy/cost/latency per problem, per model, per approach selection heuristic).

**Why Deferred:** This requires EVAL-01's benchmark dataset and infrastructure. Deferred together.

**Estimated Phase:** Phase 7 (evaluation & benchmarking)
**Effort:** M (medium)

---

## User Experience & Operations

### Search & Filtering

**Description:** Full-text search over past editorials, filter by difficulty, technique tags, language, date range, etc.

**Why Deferred:** This requires user accounts and a persistent editorial corpus (SEC-01, PROD-01). Search is a Phase 5-7 feature.

**Estimated Phase:** Phase 5-6 (multi-user features)
**Effort:** M (medium)

### Retention & Lifecycle Policy

**Description:** Automatic cleanup of old tasks and artifacts; configurable retention periods; explicit task-delete endpoint.

**Why Deferred:** v1 keeps artifacts forever in Garage. A retention/lifecycle policy makes sense at scale (cost optimization, storage cleanup). Deferred to Phase 5-6.

**Estimated Phase:** Phase 5-6 (operations & cost)
**Effort:** S (small)

### Markdown Export

**Description:** Editorial can be exported as Markdown for offline reading, printing, or sharing.

**Why Deferred:** v1 editorial is JSON, which the UI renders. Markdown export adds a separate serialization format. Deferred to Phase 5 if user demand is high.

**Estimated Phase:** Phase 5 (output formats)
**Effort:** S (small)

### Mobile-Responsive Optimization

**Description:** Web UI optimized for mobile and tablet screens (touch-friendly input, responsive layout, readable code blocks on small screens).

**Why Deferred:** v1 UI targets desktop/tablet. Mobile optimization is a UX refinement, deferred to Phase 5.

**Estimated Phase:** Phase 5 (UX polish)
**Effort:** S (small)

### Accessibility (a11y)

**Description:** ARIA labels, keyboard navigation, screen-reader testing, color contrast compliance, semantic HTML.

**Why Deferred:** v1 UI is functional but not a11y-reviewed. Accessibility is important and deferred to a dedicated phase (Phase 5-6).

**Estimated Phase:** Phase 5-6 (accessibility)
**Effort:** M (medium)

---

## Alternative Execution Models

### Shared Redis Pub/Sub Fan-Out

**Description:** Instead of one Redis subscription per WebSocket client, use a shared pub/sub fan-out to reduce connection overhead (relevant if ws_max_connections limit is hit frequently).

**Why Deferred:** v1 opens one Redis subscription per WebSocket client (capped by ws_max_connections = 200). This is sufficient for v1. A shared fan-out pattern (pub/sub -> message queue -> broadcaster) is an optimization deferred to Phase 5 if needed.

**Estimated Phase:** Phase 5 (scalability optimization)
**Effort:** M (medium)

### TLS Termination & Certificates

**Description:** HTTPS/WSS support with TLS termination in nginx, certificate management (Let's Encrypt, AWS ACM, etc.).

**Why Deferred:** v1 nginx runs in HTTP-only mode. TLS is required for production but deferred to operational setup (Phase 5) after v1 ships.

**Estimated Phase:** Phase 5 (production hardening)
**Effort:** S (small)

### WebSocket Authentication Beyond Origin

**Description:** Token-based or header-based authentication for WebSocket connections (beyond the current Origin allowlist).

**Why Deferred:** This requires SEC-01 (user authentication). Deferred together.

**Estimated Phase:** Phase 5 (auth & security)
**Effort:** M (medium)

---

## Code Execution & Sandboxing

### Interactive Code Playground

**Description:** In-browser ability to edit the generated solution and re-run tests without re-invoking the full pipeline.

**Why Deferred:** This requires exposing the plain-subprocess executors to user input. This collides with deferred sandboxing (SEC-02); an interactive playground is unsafe until code is sandboxed. Deferred together with SEC-02.

**Estimated Phase:** Phase 6-7 (after sandboxing)
**Effort:** M (medium)

### Additional Programming Languages

**Description:** Support for languages beyond Python + Go (e.g., Java, C++, JavaScript, Rust).

**Why Deferred:** v1 is locked to Python + Go. Additional languages require separate executor tools, test harness renderers, and LLM prompt variations. Each new language is a ~1-week slice. Deferred to Phase 6-7; each language is a separate plan.

**Estimated Phase:** Phase 6-7 (multi-language support)
**Effort:** M per language (medium)

### Empirical Complexity Verification

**Description:** Automated benchmarking to verify that claimed Big-O complexity actually holds (measure runtime vs input size).

**Why Deferred:** v1 reviewers check complexity analytically (Reviewer node asks for justification). Empirical verification would require running the code at multiple scales and curve-fitting. This is a research-grade verification, deferred to Phase 7.

**Estimated Phase:** Phase 7 (evaluation)
**Effort:** L (large)

---

## Similar Problems & Recommendations

### "Similar Problems" Recommendations

**Description:** When viewing an editorial, suggest related problems based on technique tags, difficulty, or full-text similarity.

**Why Deferred:** This requires a curated problem corpus and embedding-based search or tag-based indexing. Deferred to Phase 5-6.

**Estimated Phase:** Phase 5-6 (recommendations)
**Effort:** M (medium)

---

## Documentation & Education

### Video or Animated Visual Explanations

**Description:** Animated diagrams or videos explaining each approach (e.g., visualizing pointer movement, DP table fills, graph traversal).

**Why Deferred:** This requires video/diagram generation capability absent from the current text-pipeline architecture. Deferred to a specialized phase if demand is high.

**Estimated Phase:** Phase 7 (media generation)
**Effort:** L (large)

---

## Literal BMAD Methodology

### Literal BMAD Agent Personas

**Description:** Implementing the full BMAD roles (Analyst, Product Manager, Architect, Scrum Master, Developer) as literal agent personas in the workflow.

**Why Deferred:** v1 uses BMAD as a methodology/documentation-structure influence only, not as literal role-play. This was an explicit product-owner decision to keep the agent graph simple and focused. Literal personas are deferred to Phase 5 if desired.

**Estimated Phase:** Phase 5-7 (advanced orchestration)
**Effort:** M (medium)

---

## Summary Table

| Item | ID (if applicable) | Reason | Phase | Effort |
|------|-----------|--------|-------|--------|
| Authentication & user accounts | SEC-01 | Deferred due to v1 stateless design | Phase 5 | L |
| Sandboxed execution | SEC-02 | Security hardening; known limitation documented | Phase 6 | M |
| Resource limits | SEC-03 | Complementary to SEC-02 | Phase 6 | M |
| Kubernetes | PLAT-01 | Infrastructure scaling; Docker Compose sufficient for v1 | Phase 6 | L |
| Observability & tracing | PLAT-02 | Operations & cost tracking; not essential for v1 | Phase 5-6 | M |
| CI/CD & linting | PLAT-03 | Development hygiene; hand-review sufficient for v1 | Phase 5 | S |
| Cross-task memory | PROD-01 | Requires user accounts (SEC-01) | Phase 7 | M |
| Follow-up variations | PROD-02 | Variation logic; Phase 5-6 | Phase 5-6 | M |
| Review history UI | PROD-03 | UI rendering; Phase 5 | Phase 5 | S |
| Multi-turn clarification | PROD-04 | State machine redesign; Phase 5 | Phase 5 | M |
| Evaluation benchmark | EVAL-01 | Curated dataset required; Phase 7 | Phase 7 | L |
| Version comparison | EVAL-02 | Requires EVAL-01 | Phase 7 | M |
| Search & filtering | — | Requires user accounts | Phase 5-6 | M |
| Retention policy | — | Storage cleanup; cost optimization | Phase 5-6 | S |
| Markdown export | — | Output format; Phase 5 | Phase 5 | S |
| Mobile optimization | — | UX polish; Phase 5 | Phase 5 | S |
| Accessibility (a11y) | — | Important for production; Phase 5-6 | Phase 5-6 | M |
| Shared Redis fan-out | — | Scalability optimization; Phase 5 | Phase 5 | M |
| TLS/HTTPS | — | Production hardening; Phase 5 | Phase 5 | S |
| WS authentication | — | Requires user auth (SEC-01) | Phase 5 | M |
| Interactive playground | — | Unsafe until sandboxing (SEC-02) | Phase 6-7 | M |
| Additional languages | — | One per language; Phase 6-7 | Phase 6-7 | M |
| Empirical complexity check | — | Research-grade verification; Phase 7 | Phase 7 | L |
| Similar problems | — | Corpus & search; Phase 5-6 | Phase 5-6 | M |
| Video/animated explanations | — | Media generation; Phase 7 | Phase 7 | L |
| Literal BMAD personas | — | Not a goal; v1 uses BMAD for structure only | Phase 5-7 | M |

---

**Last Updated:** 2026-09-25 (Phase 4 Plan 04-04)

Every item on this list is consciously acknowledged and valued. This document prevents deferred items from being scattered, lost, or rediscovered late in development. When any item becomes a priority, it is moved from this file to a plan and tracked explicitly.
