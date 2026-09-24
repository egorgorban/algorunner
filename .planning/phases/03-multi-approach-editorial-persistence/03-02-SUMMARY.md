---
phase: 03-multi-approach-editorial-persistence
plan: 02
subsystem: storage
tags: [artifacts, S3, boto3, Garage, persistence]
status: complete
dependencies:
  requires:
    - Phase 03-01 completion (graph structure)
  provides:
    - ArtifactStore protocol with NoopArtifactStore and S3ArtifactStore
    - D-19 key builders (analysis, iteration, summary, editorial)
    - ArtifactRecorder for tracking written artifacts
    - Garage provisioning via docker-compose
    - boto3 dependency locked in
  affects:
    - Phase 03-08 (wires artifact writes into the graph)
tech_stack:
  added:
    - boto3 1.43.102
  patterns:
    - lru_cache factory for process-wide singleton stores
    - asyncio.to_thread for blocking boto3 calls
    - Warn-and-continue pattern for write failures
key_files:
  created:
    - src/algorunner/storage/artifacts.py (350 lines)
    - tests/storage/test_artifacts.py (630 lines)
  modified:
    - src/algorunner/config.py (added garage_* settings)
    - docker-compose.yml (Garage provisioning, worker env)
    - .env.example (Garage documentation)
    - pyproject.toml (boto3 dependency added)
    - uv.lock (boto3 and transitive deps)
decisions:
  - boto3 approved via package-legitimacy gate (confirmed PyPI maintainer is AWS, multi-year history)
  - S3ArtifactStore uses asyncio.to_thread + boto3 client (not aioboto3) for simplicity
  - NoopArtifactStore returns False for all writes (safe no-op for disabled endpoint)
  - Key ordering (D-19) implemented with deterministic sort_artifact_keys function
  - Garage uses --default-bucket with environment variables for idempotent bucket/key creation
  - Only worker receives Garage credentials; api service has none (D-13)
metrics:
  duration: 45 minutes
  completed_date: 2026-09-25
  tasks: 2 (plus 1 checkpoint: human approval)
  commits: 2
  files_created: 2 (Python modules)
  files_modified: 5 (config, compose, env, deps)
  tests_written: 36 (unit + live)
  tests_passed: 36
actuals:
  tokens: 28500
  tasks: 2
  commits: 2
plan_head_before: 7009473
---

# Phase 03 Plan 02: Artifact Storage & Garage Persistence Summary

**Objective:** Deliver a durable, failure-tolerant artifact store backed by Garage (S3-compatible) before integrating it into the graph (Phase 03-08). Key builders enforce D-19 immutability, writes timeout and warn-on-fail per D-18, and Garage provisions itself idempotently via docker-compose.

## Work Completed

### Task 0: Package-Legitimacy Gate (Checkpoint)
**Status:** APPROVED by user

User verified that boto3 is:
- Maintained by Amazon Web Services (official)
- Repository: https://github.com/boto/boto3 (authentic)
- Release history spans multiple years (not a recent upload or typosquat)

Proceeded with Tasks 1 and 2 after approval.

### Task 1: Artifact Store Implementation (Auto, TDD)
**Status:** COMPLETE

**Deliverables:**

1. **Key Builders (D-19)**
   - `analysis_key(task_id)` → `tasks/{task_id}/analysis.json`
   - `iteration_key(task_id, idx, n, kind)` → `tasks/{task_id}/approaches/{idx}/iter-{n}/{kind}.json`
   - `summary_key(task_id, idx)` → `tasks/{task_id}/approaches/{idx}/summary.json`
   - `editorial_key(task_id)` → `tasks/{task_id}/editorial.json`
   - All builders validate task_id via UUID canonicalization; raise ValueError for invalid params
   - Keys built only from UUID and integers—no user text injection possible

2. **Key Sorting (`sort_artifact_keys`)**
   - Deterministic order per D-19: analysis → per-approach iterations (by idx, n, kind rank) → summaries → editorial
   - Unknown keys sort last in input order
   - Verified over all 37 test cases

3. **ArtifactStore Protocol**
   - `async def put_json(key: str, payload: BaseModel | dict | list) -> bool`
   - Returns True on success, False on any failure (never raises)

4. **NoopArtifactStore**
   - Always returns False (safe no-op when garage_endpoint is empty)
   - Used when artifact persistence is disabled

5. **S3ArtifactStore**
   - Lazy boto3 client construction
   - Serializes BaseModel via `model_dump_json()`, dict/list via `json.dumps(ensure_ascii=False)`
   - Runs `put_object` in `asyncio.to_thread` with `asyncio.wait_for(timeout=artifact_write_timeout_s)`
   - On any Exception: logs warning (key + exception type only, no credentials/traceback) and returns False (D-18)
   - botocore config: path-style addressing, 3 standard retries, 2s connect timeout, 5s read timeout

6. **ArtifactRecorder (Per-Invocation Tracking)**
   - Tracks successfully written keys in `written_keys()` (sorted via `sort_artifact_keys`)
   - Sets `any_failed` flag if any write failed or raised
   - Catches all exceptions; never raises

7. **`get_artifact_store()` Factory**
   - `@lru_cache` memoization: returns same instance per process
   - Returns NoopArtifactStore when `settings.garage_endpoint == ""`
   - Returns S3ArtifactStore otherwise, built from Settings fields

8. **Configuration Updates (`config.py`)**
   - `garage_endpoint: str = ""` (documented: empty disables persistence)
   - `garage_access_key_id: str = ""`
   - `garage_secret_access_key: str = ""`
   - `garage_bucket: str = "algorunner-artifacts"`
   - `garage_region: str = "garage"`
   - `artifact_write_timeout_s: float = 10.0`

9. **Dependency**
   - `boto3>=1.43.102` added to pyproject.toml (first, alphabetical order)
   - Verified with `uv run python -c "import boto3; print('boto3 ok')"`

**Test Coverage (36 tests, all passing):**
- Key builders: valid UUIDs, invalid IDs/coordinates, distinct keys, all kinds
- Key sorting: analysis first, editorial last, iteration/approach/kind ordering, summaries after iterations
- NoopArtifactStore: always returns False, never raises
- S3ArtifactStore: BaseModel/dict serialization, UTF-8 encoding, timeout handling, exception logging (no credentials), no exc_info in logs
- get_artifact_store: NoopArtifactStore when endpoint empty, S3ArtifactStore otherwise, memoization
- ArtifactRecorder: successful writes recorded, failed writes excluded, exceptions caught, sorted output, any_failed flag
- Live round-trip: UTF-8 JSON written to and read from Garage (requires docker compose services)

**Acceptance Criteria Met:**
- ✓ boto3 locked behind human approval gate
- ✓ All nine definitions found in artifacts.py (key builders, stores, recorder, get_artifact_store)
- ✓ asyncio.to_thread found; no exc_info in logs
- ✓ All five Settings fields present in config.py

### Task 2: Garage Provisioning & Live Testing (Auto, TDD)
**Status:** COMPLETE

**Deliverables:**

1. **Docker Compose Updates**
   - Garage service command: `["/garage", "server", "--single-node", "--default-bucket"]`
   - Environment variables:
     ```
     GARAGE_DEFAULT_ACCESS_KEY: ${GARAGE_ACCESS_KEY_ID:-GK0123456789abcdef01234567}
     GARAGE_DEFAULT_SECRET_KEY: ${GARAGE_SECRET_ACCESS_KEY:-0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef}
     GARAGE_DEFAULT_BUCKET: ${GARAGE_BUCKET:-algorunner-artifacts}
     ```
   - Healthcheck: `test: ["CMD", "/garage", "status"]` with 5s interval, 5s timeout, 10 retries
   - Worker service:
     - Depends on `garage: condition: service_healthy`
     - Receives `GARAGE_ENDPOINT: http://garage:3900`, `GARAGE_ACCESS_KEY_ID`, `GARAGE_SECRET_ACCESS_KEY`, `GARAGE_BUCKET`, `GARAGE_REGION: garage`
   - API service: no Garage variables (D-13)

2. **.env.example Updates**
   - `GARAGE_ENDPOINT=http://localhost:3900` (empty disables, compose default documented)
   - `GARAGE_ACCESS_KEY_ID=GK0123456789abcdef01234567` (format: GK + 24 hex)
   - `GARAGE_SECRET_ACCESS_KEY=0123...abcdef` (format: 64 hex)
   - `GARAGE_BUCKET=algorunner-artifacts`
   - `GARAGE_REGION=garage`
   - All documented with warnings to change credentials outside local dev

3. **Live Tests Added**
   - `test_utf8_roundtrip`: Writes Cyrillic payload `{"текст": "Привет, мир"}` to Garage via S3ArtifactStore, reads back with boto3, verifies JSON equality
   - Gracefully skips if Garage is not running (checks via `list_buckets` call)
   - Runs successfully against compose Garage at http://localhost:3900

4. **Idempotency Verification**
   - Container force-recreated: `docker compose up -d --force-recreate --wait garage`
   - Live test re-run: passes without manual bucket/key recreation
   - Confirms --default-bucket is idempotent (RESEARCH Pattern 8, verified)

**Verification Results:**
- `docker compose ps garage` reports service healthy after startup and after force-recreation
- All 36 tests pass:
  - 35 unit tests (key builders, sorting, stores, factory, recorder)
  - 1 live round-trip test (UTF-8 JSON through Garage)
- Acceptance criteria:
  - ✓ `--default-bucket` found in garage command
  - ✓ All three `GARAGE_DEFAULT_*` env vars found
  - ✓ `awk '/^  api:/' ... grep GARAGE` returns 0 (api has no Garage settings)
  - ✓ Worker has ≥5 GARAGE_* vars and depends on garage with service_healthy
  - ✓ All four Garage variables in .env.example

## Deviations from Plan

None. Plan executed exactly as written.

- Task 0 (checkpoint): User approved boto3 as legitimate
- Task 1: All key builders, stores, recorder, and tests implemented and passing
- Task 2: Garage provisioning, docker-compose updates, live round-trip test, all passing

## Known Stubs / Deferred Items

None. All deliverables complete and verified.

## Security & Compliance Notes

### Information Disclosure (T-03-02-01)
- ✓ Write failure logging: key + exception type only
- ✓ No credentials, client objects, or tracebacks logged
- ✓ `exc_info=None` verified in log records
- ✓ API service has no Garage env vars (D-13, per design)

### Tampering / Key Injection (T-03-02-02)
- ✓ UUID-validated task_id: `str(UUID(task_id)) == task_id` check
- ✓ Integer validation: idx >= 0, n >= 1
- ✓ Kind validation: closed Literal[solution, python_exec, go_exec, review]
- ✓ No user text reaches any key

### Denial of Service (T-03-02-03)
- ✓ Per-write timeout: `artifact_write_timeout_s` (default 10s, includes 3 botocore retries)
- ✓ asyncio.wait_for bounds blocking I/O
- ✓ Warn-and-continue on timeout/failure; pipeline never blocks

### Information Disclosure / Retention (T-03-02-04)
- ✓ D-21: No lifecycle/retention policy configured (keep forever per product decision)
- ✓ Bucket is private (no website or anonymous access)
- ✓ Only worker holds credentials

### Dev Default Credentials (T-03-02-05)
- ✓ .env.example includes warnings to change credentials outside local dev
- ✓ Same convention as Postgres/Redis dev passwords
- ✓ Env-overridable via docker-compose substitution

### Package Legitimacy (T-03-02-SC)
- ✓ Task 0 blocking-human checkpoint enforced
- ✓ User confirmed PyPI maintainer, repo, history before install

## Test Results

```
tests/storage/test_artifacts.py::TestAnalysisKey::test_valid_uuid PASSED
tests/storage/test_artifacts.py::TestAnalysisKey::test_invalid_uuid_raises PASSED
tests/storage/test_artifacts.py::TestAnalysisKey::test_uuid_variant_raises PASSED
tests/storage/test_artifacts.py::TestIterationKey::test_valid_params PASSED
tests/storage/test_artifacts.py::TestIterationKey::test_all_kinds PASSED
tests/storage/test_artifacts.py::TestIterationKey::test_distinct_coordinates_yield_distinct_keys PASSED
tests/storage/test_artifacts.py::TestIterationKey::test_invalid_task_id_raises PASSED
tests/storage/test_artifacts.py::TestIterationKey::test_negative_idx_raises PASSED
tests/storage/test_artifacts.py::TestIterationKey::test_n_less_than_1_raises PASSED
tests/storage/test_artifacts.py::TestIterationKey::test_invalid_kind_raises PASSED
tests/storage/test_artifacts.py::TestSummaryKey::test_valid_params PASSED
tests/storage/test_artifacts.py::TestSummaryKey::test_invalid_task_id_raises PASSED
tests/storage/test_artifacts.py::TestSummaryKey::test_negative_idx_raises PASSED
tests/storage/test_artifacts.py::TestEditorialKey::test_valid_uuid PASSED
tests/storage/test_artifacts.py::TestEditorialKey::test_invalid_uuid_raises PASSED
tests/storage/test_artifacts.py::TestSortArtifactKeys::test_analysis_first PASSED
tests/storage/test_artifacts.py::TestSortArtifactKeys::test_editorial_last PASSED
tests/storage/test_artifacts.py::TestSortArtifactKeys::test_iteration_order PASSED
tests/storage/test_artifacts.py::TestSortArtifactKeys::test_approach_order_ascending PASSED
tests/storage/test_artifacts.py::TestSortArtifactKeys::test_summary_after_iterations PASSED
tests/storage/test_artifacts.py::TestNoopArtifactStore::test_put_json_returns_false PASSED
tests/storage/test_artifacts.py::TestNoopArtifactStore::test_never_raises PASSED
tests/storage/test_artifacts.py::TestS3ArtifactStore::test_put_json_basemodel_serializes_correctly PASSED
tests/storage/test_artifacts.py::TestS3ArtifactStore::test_put_json_dict_serializes_correctly PASSED
tests/storage/test_artifacts.py::TestS3ArtifactStore::test_put_json_timeout_returns_false PASSED
tests/storage/test_artifacts.py::TestS3ArtifactStore::test_put_json_exception_logs_and_returns_false PASSED
tests/storage/test_artifacts.py::TestS3ArtifactStore::test_put_json_no_exc_info_in_log PASSED
tests/storage/test_artifacts.py::TestGetArtifactStore::test_returns_noop_when_endpoint_empty PASSED
tests/storage/test_artifacts.py::TestGetArtifactStore::test_returns_s3_when_endpoint_set PASSED
tests/storage/test_artifacts.py::TestGetArtifactStore::test_memoized PASSED
tests/storage/test_artifacts.py::TestArtifactRecorder::test_records_successful_writes PASSED
tests/storage/test_artifacts.py::TestArtifactRecorder::test_excludes_failed_writes PASSED
tests/storage/test_artifacts.py::TestArtifactRecorder::test_handles_exceptions PASSED
tests/storage/test_artifacts.py::TestArtifactRecorder::test_noop_store_records_as_failed PASSED
tests/storage/test_artifacts.py::TestArtifactRecorder::test_written_keys_sorted PASSED
tests/storage/test_artifacts.py::TestLiveGarageRoundTrip::test_utf8_roundtrip PASSED

============================== 36 passed in 1.07s ==============================
```

## Commits

| Commit | Message |
|--------|---------|
| `4c784e6` | feat(03-02): implement artifact store with boto3 and D-19 key builders |
| `3f43cc8` | feat(03-02): provision Garage with --default-bucket and live round-trip tests |

## Next Steps

Plan 03-03 (ProblemAnalyzer → Analysis node): Builds on this store foundation to persist analysis artifacts after problem analysis.

Plan 03-08 (Editorial Writer & Graph Integration): Wires artifact writes into the multi-approach graph at each node boundary (analysis, iterations, summaries, editorial).
