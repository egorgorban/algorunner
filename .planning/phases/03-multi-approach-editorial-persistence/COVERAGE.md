# Phase 3: API Coverage Matrix

**Detector:** `api-coverage.cjs` returned `detected:true` over the phase scope (the 03-01..03-08 PLAN bodies plus the ROADMAP Phase 3 section). Two external APIs are in scope:

1. **Garage S3 API** (new this phase: store in Plan 03-02, graph writes and live proof in Plan 03-08). This is the S3-compatible object store for intermediate artifacts (DATA-02).
2. **OpenAI Chat Completions structured outputs** (delta over Phase 2). A new Editorial Writer node reuses the same integration (Plans 03-04..03-07).

Coverage is full by default. Every capability starts as `INTEGRATE`, and each `OPT-OUT` carries a reason.

## Garage S3 API (boto3 client, `src/algorunner/storage/artifacts.py`)

| capability | decision | reason |
|---|---|---|
| PutObject (JSON artifacts, UTF-8) | INTEGRATE | D-17/D-19 incremental writes: analysis, per-iteration solution/python_exec/go_exec/review, per-approach summary, editorial (store: Plan 03-02 T1-T2; graph writes: Plan 03-08 T1) |
| GetObject | INTEGRATE | Used by the live round-trip test and scripts/verify_phase3_live.py to prove stored code equals article code. No production reader, because the API serves results from Postgres (D-13) |
| HeadObject | INTEGRATE | Used by scripts/verify_phase3_live.py to prove every key in result.artifact_keys exists (D-20) |
| ListObjectsV2 | OPT-OUT | not needed: result.artifact_keys plus the deterministic D-19 key layout make listing unnecessary. A FAILED task's trail is found by the tasks/{task_id}/ prefix with Garage's own tooling |
| DeleteObject / DeleteObjects | OPT-OUT | explicitly out of scope: D-21 keeps artifacts forever in v1, and the task-delete endpoint is a CONTEXT.md deferred idea |
| CopyObject | OPT-OUT | not needed: artifacts are written once per key and never duplicated |
| Multipart upload (Create/UploadPart/Complete/Abort) | OPT-OUT | not needed: artifacts are small JSON documents (kilobytes), far below any multipart threshold |
| CreateBucket / access-key management via API | OPT-OUT | not needed: Garage provisions the bucket and key itself via the `--single-node --default-bucket` flags and GARAGE_DEFAULT_* env in docker-compose.yml |
| Bucket lifecycle / expiration configuration | OPT-OUT | explicitly out of scope: D-21 (keep forever) and the deferred retention policy |
| Bucket website / CORS / public access | OPT-OUT | explicitly out of scope: the bucket stays private, only the worker holds credentials, and clients read results from Postgres (D-13) |
| Presigned URLs | OPT-OUT | not needed yet: no client downloads artifacts in v1, and the Phase 4 UI renders result.editorial from Postgres |
| Conditional writes (If-None-Match) | OPT-OUT | not needed: Garage v2.4.1 ignores the header (research-verified), so immutability comes from the unique per-iteration key scheme instead |
| Object tagging / user metadata | OPT-OUT | not needed: the key path already encodes task, approach, iteration and kind |
| Bucket versioning | OPT-OUT | not needed: keys are unique per (task, approach, iteration, kind), so there are no overwrites to version within an invocation |

## OpenAI API (Phase 3 delta; the Phase 2 matrix in 02 COVERAGE.md still applies)

| capability | decision | reason |
|---|---|---|
| Structured outputs via chat.completions.parse (EditorialDraft) | INTEGRATE | New Editorial Writer node: one call per article (D-15), plus at most one retry (D-16) |
| Per-request `timeout` on parse | INTEGRATE | Writer per-attempt timeout (settings.editorial_attempt_timeout_s) inside the D-10 reserve (Plan 03-05) |
| Timeout/rate-limit retry with backoff (tenacity `call_structured`) | INTEGRATE | Reused unchanged for the Writer (INFRA-03) |
| Per-agent model configuration | INTEGRATE | New `editorial_writer_model` override resolved by `model_for("editorial_writer")` (ORCH-03 pattern) |
| Streaming responses | OPT-OUT | not needed: the Writer returns one structured object, and live status streaming is Phase 4 WebSocket work, not token streaming |
| LLM-as-judge / moderation call for language checking | OPT-OUT | explicitly out of scope: D-16 mandates a deterministic Cyrillic check with no extra LLM judge call |
| Embeddings, vision, batch, fine-tuning, Assistants, Responses, tools | OPT-OUT | not needed: the same reasons as the Phase 2 matrix still hold, and the Writer adds no use case for any of them |
| Token usage / cost tracking | OPT-OUT | explicitly deferred to v2 (REQUIREMENTS.md PLAT-02) |
