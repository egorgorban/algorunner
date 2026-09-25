# AlgoRunner

AlgoRunner is a production-ready multi-agent system that transforms a free-text algorithmic problem description (English or Russian) into a comprehensive LeetCode-editorial-style article in Russian. The system analyzes the problem, generates 1+ solution approaches with Python and Go implementations, executes them against tests for correctness, refines them through a review loop, and presents everything in a well-structured editorial. **Correctness of the generated solution—verified by executing Python and Go code against actual tests—matters more than explanation quality or speed.**

---

## Quickstart

### Prerequisites

- Docker and Docker Compose
- Python 3.14 with `uv` package manager
- Node.js 18+ (for frontend)
- OpenAI API key

### Start the Stack

1. **Copy the environment file and set your OpenAI API key:**
   ```bash
   cp .env.example .env
   # Edit .env and add your OPENAI_API_KEY
   export OPENAI_API_KEY=sk-...
   ```

2. **Start all services:**
   ```bash
   docker compose up -d --build
   ```

3. **Open the web interface:**
   ```
   http://localhost
   ```

That's it! The system is ready to solve problems. Enter a LeetCode-style problem description, and AlgoRunner will generate a full editorial with multiple approaches, Python and Go code, and test results.

---

## Local Development

### Setup

```bash
# Install Python dependencies
uv sync

# Install frontend dependencies
npm --prefix frontend ci
```

### Running Services

In separate terminals:

```bash
# Start the backend API (auto-reloads on file changes)
uv run uvicorn src.algorunner.api.main:app --reload

# Start the taskiq worker
uv run taskiq worker algorunner.worker.broker:broker

# Start the frontend dev server (port 5173, proxied to api on 8000)
npm --prefix frontend run dev
```

Or use Docker Compose:

```bash
docker compose up --build
```

Then navigate to `http://localhost` (via nginx gateway) or directly to:
- Frontend: `http://localhost:5173` (dev server)
- API: `http://localhost:8000`

---

## Tests

### Backend Tests

Requires Postgres and Redis (started with Docker Compose):

```bash
docker compose up -d postgres redis

pytest                                    # Full suite
pytest tests/api/test_events_ws.py        # Single file
```

See [docs/development/testing.md](docs/development/testing.md) for detailed testing guide, fixtures, and patterns.

### Frontend Tests

```bash
npm --prefix frontend test                # Unit tests (vitest, node environment)
npm --prefix frontend run test:live       # Integration tests (requires api/worker running)
```

### Live Probes

End-to-end verification scripts:

```bash
docker compose up -d --build

# Core workflow: submit → status polling → editorial
uv run python scripts/verify_phase3_live.py

# WebSocket streaming and gateway reverse proxy
uv run python scripts/verify_phase4_live.py

# Process isolation and timeout handling
uv run python scripts/verify_executor_isolation.py
```

See [docs/development/testing.md](docs/development/testing.md#live-probes) for details.

---

## Documentation

Complete documentation lives in `docs/` and is indexed in [`.claude/CLAUDE.md`](https://github.com/egorgorban/algorunner/blob/main/.claude/CLAUDE.md#documentation-index) (Repository Rules section):

| Document | Purpose |
|----------|---------|
| [docs/product/prd.md](docs/product/prd.md) | Product requirements: user stories, scope, success criteria |
| [docs/architecture/architecture.md](docs/architecture/architecture.md) | Service topology (7 containers), data paths, module organization |
| [docs/architecture/agents.md](docs/architecture/agents.md) | LLM agent nodes: input, process, output per agent |
| [docs/architecture/workflow.md](docs/architecture/workflow.md) | LangGraph state machine: node execution order, edges, fan-out |
| [docs/architecture/data-model.md](docs/architecture/data-model.md) | Pydantic schemas: task, problem, approach, solution, execution, editorial |
| [docs/development/testing.md](docs/development/testing.md) | How to run and write tests: backend fixtures, WebSocket testing, live probes |
| [docs/development/conventions.md](docs/development/conventions.md) | Code style: backend (async, SQL, Pydantic, status), frontend (React, TypeScript, Tailwind) |
| [docs/plans/implementation-plan.md](docs/plans/implementation-plan.md) | Phase-by-phase roadmap and success criteria |
| [DEFERRED.md](DEFERRED.md) | Out-of-scope features (auth, sandboxing, Kubernetes, search, etc.) with rationale |

---

## Important: No Sandboxing in v1

**⚠️ Security Notice**

Generated Python and Go code executes **without sandboxing** in v1. The code runs via subprocess with resource limits (CPU, memory, file descriptors) and an import denylist, but is not isolated. 

**This stack is for local use and trusted environments only.** For production use with untrusted code, implement sandboxing (Docker, seccomp, SELinux) as described in [DEFERRED.md](DEFERRED.md) (SEC-02, SEC-03).

---

## Configuration

All configuration comes from environment variables or `.env`:

```bash
# Required
OPENAI_API_KEY=sk-...                                 # OpenAI API key

# Optional (defaults shown)
DATABASE_URL=postgresql://algorunner:algorunner@localhost:5432/algorunner
REDIS_URL=redis://localhost:6379
GARAGE_ENDPOINT=http://localhost:3900
GARAGE_ACCESS_KEY_ID=GK0123456789abcdef01234567
GARAGE_SECRET_ACCESS_KEY=0123456789abcdef...
GARAGE_BUCKET=algorunner-artifacts
```

See `.env.example` for the full reference.

---

## Architecture Overview

- **API** (FastAPI): REST endpoints + WebSocket streaming
- **Worker** (taskiq): Background task execution (LangGraph + OpenAI)
- **Postgres**: Task state (authoritative), LangGraph checkpoints
- **Redis**: Task queue (taskiq broker) + Pub/Sub (real-time events)
- **Garage**: S3-compatible artifact storage
- **Frontend** (React + TypeScript + Vite): Web UI
- **nginx**: Reverse proxy (port 80 → api:8000 + frontend:3000)

For detailed architecture, data paths, and module map, see [docs/architecture/architecture.md](docs/architecture/architecture.md).

---

## License & Attribution

Built for LeetCode-style algorithmic problem preparation. See `.claude/CLAUDE.md` for working rules, conventions, and decision log.
