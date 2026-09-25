# Code Conventions

Coding style and structure rules for AlgoRunner. For quick summary, see the "Repository Rules" section in [`.claude/CLAUDE.md`](../../.claude/CLAUDE.md); read here for details.

## Backend

### Async-Only I/O

All I/O (database, Redis, HTTP, subprocess) is async:
- Database: `AsyncConnectionPool` from `psycopg-pool[asyncio]`.
- Redis: `redis.asyncio.Redis` (never sync `redis.Redis`).
- HTTP: `httpx.AsyncClient` in tests; FastAPI is natively async.
- Subprocess: `asyncio.create_subprocess_exec()` + `await asyncio.wait_for(proc.communicate(), timeout=...)` for task execution; never blocking `subprocess.run()`.

Blocking I/O inside an `async def` task stalls the entire worker process. Use async I/O exclusively.

### SQL: `%s` Placeholders

All SQL queries use `%s` parameter placeholders (psycopg style), never f-strings or string concatenation:

```python
async with pool.connection() as conn:
    result = await conn.execute(
        "UPDATE tasks SET status = %s, updated_at = now() WHERE id = %s",
        ["completed", task_id],
    )
```

This prevents SQL injection and ensures parameter escaping is handled by the driver.

### Pydantic Everywhere

Every boundary (API request/response, LangGraph state, OpenAI Structured Outputs, storage contracts) uses Pydantic v2:

```python
from pydantic import BaseModel

class TaskResponse(BaseModel):
    id: str
    status: str
    result: Optional[dict] = None
```

Never use plain dicts for contracts; Pydantic provides validation and IDE autocompletion. Schemas live in `src/algorunner/schemas/` and are imported into all modules that need them.

### Status Transitions: Storage Writers & Emission

Status changes only flow through designated storage writers (`storage/tasks.py`):

1. **Worker writes the new status to Postgres** (task record column).
2. **After the transaction commits**, the storage writer publishes a status event to Redis Pub/Sub.

Example from `storage/tasks.py`:

```python
async def update_task_status(pool, task_id, status):
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE tasks SET status = %s, updated_at = now() WHERE id = %s",
            [status, task_id],
        )
    # After commit, publish to Redis (no await; fire-and-forget is safe)
    await redis.publish(f"task:{task_id}:status", json.dumps({...}))
```

**In-graph status emission** is done via `emit_status(ctx, status)` (defined in `graph/context.py`), which writes to `ctx.status_sink` (a reference to the storage writer). Never call `redis.publish()` or `postgres.execute()` directly from graph nodes; always go through the context sink.

**Rule:** Status is the single source of truth only after it is written to Postgres AND published to Redis. The write must happen first, always.

### Never-Raise Side Channels

Side channels (WebSocket, subscriptions) never raise `Exception` and never swallow `CancelledError`. Log errors but don't raise; propagate `CancelledError` for proper shutdown.

### Structured TaskError Codes

Errors in task execution are represented as `TaskError` with a code (enum) and message:

```python
class TaskError(BaseModel):
    code: ErrorCode  # enum: ANALYSIS_FAILED, CODE_EXECUTION_FAILED, ...
    message: str

class ErrorCode(str, Enum):
    ANALYSIS_FAILED = "analysis_failed"
    CODE_EXECUTION_FAILED = "code_execution_failed"
    ...
```

This allows the UI to render human-readable errors without localization of error strings.

### One Logger Per Module

Each module: `logger = logging.getLogger(__name__)`. Settings from `.env` and `config.py`, never hardcoded.

### Per-Agent Model Overrides

Each agent can override its model via `{AGENT_NAME}_MODEL` env var, enabling cost optimization (cheap model for analysis, stronger for solving).

### Module Docstrings

Every module has a docstring citing the design decisions (D-01, D-02, etc.) that shaped it. This traces code back to design intent.

---

## Frontend

### File Layout & Naming

```
frontend/src/
├── App.tsx                 # Entry point, layout shell
├── context/
│   └── TaskContext.tsx     # useReducer + dispatch for global task state
├── pages/
│   ├── ProblemInputPage.tsx
│   ├── StatusPage.tsx
│   ├── EditorialPage.tsx
│   └── ClarificationModal.tsx
├── components/
│   ├── CodeBlock.tsx
│   ├── StatusBadge.tsx
│   └── ApproachCard.tsx
├── lib/
│   └── parseEditorial.ts    # Pure utility functions
├── api/
│   ├── types.ts             # TypeScript mirrors of Python Pydantic schemas
│   ├── client.ts            # fetch() wrappers for API endpoints
│   └── events.ts            # WebSocket client
├── api/
│   └── *.test.ts            # Vitest tests colocated with modules
├── index.css
└── main.tsx
```

**File Naming:**
- Components (React): `PascalCase.tsx` (e.g., `CodeBlock.tsx`, `StatusBadge.tsx`)
- Utilities, APIs, hooks: `camelCase.ts` (e.g., `parseEditorial.ts`, `useTaskEvents.ts`)

### TypeScript Strictness

- `strict: true` in `tsconfig.json`
- No `any` type in the API/event contract types
- Narrow `unknown` types with type guards before use

Example:
```typescript
function isTaskResponse(obj: unknown): obj is TaskResponse {
  return typeof obj === "object" && obj !== null && "id" in obj;
}
```

### Type Mirrors: `api/types.ts`

Backend Pydantic schemas (e.g., `TaskResponse`, `EditorialDraft`, `StatusEvent`) are mirrored in TypeScript in `api/types.ts`:

```typescript
export interface TaskResponse {
  id: string;
  status: TaskStatus;
  result?: EditorialDraft;
}
```

**Rule:** Changes to Python schemas require corresponding updates to TypeScript types. They are not auto-generated; keep them in sync manually.

### As-Const Unions Instead of Enum

Use `as const` unions instead of TS `enum`: lighter, better with overloads and literal types.

### State: Context + useReducer

Global task state in React Context with useReducer. No Redux or Zustand; built-in APIs sufficient.

### HTTP & WebSocket: Native APIs

No axios, no React Query, no socket.io. Use native `fetch` for REST and native `WebSocket` for streaming:

```typescript
async function submitTask(problem: string): Promise<TaskResponse> {
  const response = await fetch("/api/v1/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ problem_text: problem }),
  });
  return response.json() as Promise<TaskResponse>;
}
```

Wrap native calls in small utility functions for error handling. Keep the boundary simple.

### Tailwind Only; No Custom CSS

All styling uses Tailwind utility classes. No custom `.css` files except `index.css` (which imports Tailwind's directives):

```css
@import "tailwindcss/base";
@import "tailwindcss/components";
@import "tailwindcss/utilities";
```

Tailwind v4 (CSS-first) means no `tailwind.config.js` needed for this project.

### Russian UI Text

All user-facing text in the UI is in Russian:

```tsx
<button className="...">Отправить</button> {/* "Submit" */}
<h2 className="...">Статус задачи</h2> {/* "Task Status" */}
```

Comments and code are in English; UI text is always in Russian.

### CodeBlock: The Single Raw-HTML Sink

The only place raw HTML is rendered in the frontend is `components/CodeBlock.tsx`, which renders syntax-highlighted code from `highlight.js`:

```tsx
import hljs from "highlight.js/lib/core";
import python from "highlight.js/lib/languages/python";
import go from "highlight.js/lib/languages/go";

hljs.registerLanguage("python", python);
hljs.registerLanguage("go", go);

export const CodeBlock: React.FC<{ code: string; language: "python" | "go" }> = ({
  code,
  language,
}) => {
  const html = hljs.highlight(code, { language }).value;
  return <pre><code dangerouslySetInnerHTML={{ __html: html }} /></pre>;
};
```

No other component uses `dangerouslySetInnerHTML`.

---

## Workflow

Changes go through GSD commands (`/gsd-quick`, `/gsd-debug`, `/gsd-execute-phase`). Each commit is atomic per task. Commit messages follow the form:

```
<type>(<scope>): <description>

<optional detailed explanation if needed>

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

Types: `feat` (new feature), `fix` (bug fix), `docs` (documentation), `refactor` (code reorganization), `test` (test additions/changes).
