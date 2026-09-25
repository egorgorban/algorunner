# Phase 4: API Coverage Matrix

**Detector:** `api-coverage.cjs` returned `detected:true` over the phase scope (the 04-01..04-08 PLAN bodies plus the ROADMAP Phase 4 section). Most signals point at AlgoRunner's own REST/WebSocket API, which is internal, not an external integration. Two external surfaces are integrated directly for the first time in this phase:

1. **Redis Pub/Sub through redis-py `redis.asyncio`** (Plans 04-01, 04-02). This is the live status fan-out channel `task:{task_id}:status`. Redis was previously used only indirectly, as the taskiq broker.
2. **Browser Web Platform APIs** (Plans 04-03, 04-05, 04-06): WebSocket, Fetch, Clipboard and History, called natively per D-12.

Coverage is full by default. Every capability starts as `INTEGRATE`, and each `OPT-OUT` carries a reason.

## Redis Pub/Sub (redis-py asyncio: `src/algorunner/realtime/publisher.py`, `src/algorunner/api/routes/events.py`)

| capability | decision | reason |
|---|---|---|
| PUBLISH | INTEGRATE | publish_status after every committed status write (04-01) |
| SUBSCRIBE | INTEGRATE | per-socket subscription to task:{task_id}:status, taken before the snapshot read (04-01) |
| UNSUBSCRIBE / connection release (`async with pubsub`, `aclose`) | INTEGRATE | released on every relay exit path; proven by PUBSUB NUMSUB returning 0 (04-01) |
| Blocking message read (`get_message(timeout=None)`) | INTEGRATE | relay forward loop, never busy-polling (04-01) |
| PUBSUB NUMSUB | INTEGRATE | used by the tests to prove subscriptions are released (04-01) |
| PSUBSCRIBE / PUNSUBSCRIBE (pattern subscriptions) | OPT-OUT | not needed yet: v1 uses one subscription per socket, capped by ws_max_connections; the shared psubscribe fan-out is recorded in DEFERRED.md (04-04) |
| SSUBSCRIBE / SPUBLISH (sharded pub/sub) | OPT-OUT | not needed: single Redis node in Docker Compose, no cluster |
| PUBSUB CHANNELS / NUMPAT | OPT-OUT | not needed: no runtime introspection use case |
| Redis Streams (XADD/XREAD) as a replayable status log | OPT-OUT | explicitly out of scope: D-01/D-02 make Postgres the authoritative state and the in-band snapshot the late-joiner path; pub/sub stays fire-and-forget |
| Keyspace notifications | OPT-OUT | not needed: status changes are published explicitly by the storage writers |
| Publish retries | OPT-OUT | explicitly out of scope: publishing is best-effort with 2 s timeouts; a missed event is corrected by the snapshot on the next (re)connect |
| Subscriber auto-reconnect / health_check_interval | OPT-OUT | not needed: on a Redis error the relay closes 1011, and the client reconnects with a fresh subscription and snapshot (04-01, 04-03) |

## Browser Web Platform APIs (`frontend/src`)

| capability | decision | reason |
|---|---|---|
| WebSocket (native) | INTEGRATE | live status stream with capped-backoff reconnect (04-03, D-12) |
| Fetch (native) | INTEGRATE | config, create task, get task, clarification (04-03, 04-05, D-12) |
| Clipboard `writeText` | INTEGRATE | copy button on every code block, with a selection + execCommand fallback outside secure contexts (04-06, D-10) |
| History `replaceState` + URLSearchParams | INTEGRATE | `?task=<id>` so reload and shared links resume through the snapshot (04-03) |
| Clipboard read | OPT-OUT | not needed: the app never reads the clipboard |
| EventSource (SSE) | OPT-OUT | explicitly out of scope: D-01..D-05 lock WebSocket as the realtime channel |
| Notifications API (alert on completion) | OPT-OUT | not needed yet: the status page is open while a task runs; revisit with user accounts |
| localStorage / IndexedDB (saved task history) | OPT-OUT | not needed yet: per-user history belongs with authentication and accounts (DEFERRED.md) |
| Service worker / offline support | OPT-OUT | not needed: the app requires the live backend |
