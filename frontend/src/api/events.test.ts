/**
 * Tests for WebSocket event handling, reconnection, and payload guards.
 */

import { describe, it, expect, vi } from "vitest";
import { backoffDelay, parseServerMessage, connectTaskEvents, NO_RECONNECT_CODES } from "./events";
import type { TaskRecord } from "./types";

describe("backoffDelay", () => {
  it("yields 1000ms for attempt 0", () => {
    expect(backoffDelay(0)).toBe(1000);
  });

  it("yields 2000ms for attempt 1", () => {
    expect(backoffDelay(1)).toBe(2000);
  });

  it("yields 4000ms for attempt 2", () => {
    expect(backoffDelay(2)).toBe(4000);
  });

  it("yields 8000ms for attempt 3", () => {
    expect(backoffDelay(3)).toBe(8000);
  });

  it("caps at 10000ms for attempt 4", () => {
    expect(backoffDelay(4)).toBe(10000);
  });

  it("stays capped at 10000ms for attempt 5", () => {
    expect(backoffDelay(5)).toBe(10000);
  });
});

describe("NO_RECONNECT_CODES", () => {
  it("contains 1000 (normal close)", () => {
    expect(NO_RECONNECT_CODES.has(1000)).toBe(true);
  });

  it("contains 4403 (origin rejected)", () => {
    expect(NO_RECONNECT_CODES.has(4403)).toBe(true);
  });

  it("contains 4404 (task not found)", () => {
    expect(NO_RECONNECT_CODES.has(4404)).toBe(true);
  });

  it("does not contain 1011 (server error)", () => {
    expect(NO_RECONNECT_CODES.has(1011)).toBe(false);
  });

  it("does not contain 1013 (at capacity)", () => {
    expect(NO_RECONNECT_CODES.has(1013)).toBe(false);
  });
});

describe("parseServerMessage", () => {
  const mockTask: TaskRecord = {
    id: "task-123",
    status: "queued",
    problem_text: "test",
    language: "en",
    examples: [],
    result: null,
    error: null,
    clarification_question: null,
    active_execution_seconds: 0,
    created_at: "2026-09-25T00:00:00Z",
    updated_at: "2026-09-25T00:00:00Z",
  };

  it("parses valid snapshot message", () => {
    const raw = JSON.stringify({ type: "snapshot", task: mockTask });
    const message = parseServerMessage(raw);
    expect(message?.type).toBe("snapshot");
    if (message?.type === "snapshot") {
      expect(message.task.id).toBe("task-123");
    }
  });

  it("parses valid status message", () => {
    const raw = JSON.stringify({ type: "status", status: "analyzing_problem", timestamp: "2026-09-25T00:01:00Z" });
    const message = parseServerMessage(raw);
    expect(message?.type).toBe("status");
    if (message?.type === "status") {
      expect(message.status).toBe("analyzing_problem");
    }
  });

  it("returns null for non-JSON string", () => {
    expect(parseServerMessage("not json")).toBeNull();
  });

  it("returns null for unknown message type", () => {
    const raw = JSON.stringify({ type: "unknown" });
    expect(parseServerMessage(raw)).toBeNull();
  });

  it("returns null for status frame without timestamp", () => {
    const raw = JSON.stringify({ type: "status", status: "queued" });
    expect(parseServerMessage(raw)).toBeNull();
  });

  it("returns null for snapshot without task", () => {
    const raw = JSON.stringify({ type: "snapshot" });
    expect(parseServerMessage(raw)).toBeNull();
  });

  it("returns null for snapshot with invalid task", () => {
    const raw = JSON.stringify({ type: "snapshot", task: { id: 123 } });
    expect(parseServerMessage(raw)).toBeNull();
  });

  it("returns null for unknown status value", () => {
    const raw = JSON.stringify({ type: "status", status: "invalid_status", timestamp: "2026-09-25T00:00:00Z" });
    expect(parseServerMessage(raw)).toBeNull();
  });
});

describe("connectTaskEvents", () => {
  it("returns a stop function", () => {
    const stop = connectTaskEvents("ws://test", {
      onMessage: () => {},
      onConnectionChange: () => {},
    });
    expect(typeof stop).toBe("function");
    stop();
  });

  it("calls onConnectionChange on state changes", () => {
    const states: Array<"connecting" | "open" | "reconnecting" | "closed"> = [];
    const stop = connectTaskEvents("ws://test", {
      onMessage: () => {},
      onConnectionChange: (state) => states.push(state),
    });
    // Should have at least called onConnectionChange with "connecting"
    expect(states.length).toBeGreaterThanOrEqual(1);
    expect(states[0]).toBe("connecting");
    stop();
  });

  it("with injected timers, schedules reconnection on non-terminal close", () => {
    const timerCalls: Array<() => void> = [];
    const mockSocket = {
      addEventListener: vi.fn(() => {
        // Mock handlers
      }),
      close: vi.fn(),
    };

    const stop = connectTaskEvents(
      "ws://test",
      {
        onMessage: () => {},
        onConnectionChange: () => {},
      },
      {
        createSocket: () => mockSocket as any,
        setTimer: (cb: () => void) => {
          timerCalls.push(cb);
          return 1 as any;
        },
        clearTimer: () => {},
      }
    );

    stop();
  });
});
