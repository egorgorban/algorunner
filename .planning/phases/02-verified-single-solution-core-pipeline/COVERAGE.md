# Phase 2: OpenAI API Coverage Matrix

**Detector:** `api-coverage.cjs` returned `detected:true` against phase scope (ROADMAP goal/success-criteria + RESEARCH.md). This phase integrates the OpenAI Python SDK (`chat.completions.parse` structured outputs) across six LLM reasoning nodes (Problem Analyzer, Solution Strategist, Solver, Code Generator, Test Generator, Reviewer).

Full coverage by default — every capability below starts `INTEGRATE`; each `OPT-OUT` carries a reason.

| capability | decision | reason |
|---|---|---|
| Chat Completions structured outputs (`chat.completions.parse(response_format=PydanticModel)`) | INTEGRATE | Core mechanism for all 6 agent nodes (INTAKE-02/03, STRAT-01/03/04, CODE-01-04, REV-01-03) — `message.parsed`/`message.refusal` contract per RESEARCH.md Pattern 1 |
| Timeout/rate-limit retry with backoff (`tenacity` around `APITimeoutError`/`RateLimitError`) | INTEGRATE | INFRA-03, D-09 — Plan 02-01 |
| Per-agent model configuration via env/config | INTEGRATE | ORCH-03 — `llm/client_factory.py.model_for()`, Plan 02-01 |
| Streaming responses (`stream=True`) | OPT-OUT | not needed — no token-by-token UI surface exists this phase; live status streaming (API-04) is WebSocket-based and deferred to Phase 4, not OpenAI token streaming |
| Embeddings API | OPT-OUT | not needed — no semantic search/similarity use case in v1 scope (REQUIREMENTS.md "Similar problems" explicitly out of scope) |
| Native function/tool calling (model-invoked tools) | OPT-OUT | not needed — every inter-node contract is satisfied by `response_format` structured outputs alone; the project's own "tools" (PythonExecutorTool/GoExecutorTool) are deterministic graph nodes invoked by app code, never by the model itself, per D-00c |
| Vision / image inputs | OPT-OUT | not needed — problem statements are text-only per INTAKE-01; no diagram/image input path exists anywhere in REQUIREMENTS.md |
| Batch API | OPT-OUT | not needed — synchronous per-task processing model (one taskiq task per submission); no bulk/offline job workflow in scope |
| Fine-tuning | OPT-OUT | explicitly out of scope — no requirement calls for a custom-trained model |
| Moderation endpoint | OPT-OUT | not needed yet — no content-moderation requirement anywhere in REQUIREMENTS.md v1 scope |
| Assistants API / persistent threads | OPT-OUT | not needed — D-00a locks the hybrid LangGraph StateGraph architecture (bounded reasoning nodes, deterministic transitions), explicitly rejecting a stateful supervisor/assistant-thread model |
| Responses API (`client.responses.parse(text_format=...)`) | OPT-OUT | not needed yet — RESEARCH.md Alternatives Considered: OpenAI positions Responses as the forward path, but Chat Completions remains fully supported; migrating now touches every node for no functional gain this phase |
| Token usage / cost tracking per call | OPT-OUT | explicitly deferred to v2 — REQUIREMENTS.md `PLAT-02` ("per-request/agent/run OpenAI cost tracking") |

**No LangGraph capability opt-outs recorded here** — LangGraph is not the "external API" this checkpoint targets (no HTTP/SDK boundary to a third-party service); its `interrupt()`/`Command`/checkpointer surface is covered by the phase's Architecture Patterns instead.
