/**
 * Tests for the task state reducer.
 */

import { describe, it, expect } from "vitest";
import { taskReducer, initialTaskState } from "./taskReducer";
import type { TaskRecord } from "../api/types";

const mockTask: TaskRecord = {
  id: "task-123",
  status: "queued",
  problem_text: "test problem",
  language: "en",
  examples: [],
  result: null,
  error: null,
  clarification_question: null,
  active_execution_seconds: 0,
  created_at: "2026-09-25T00:00:00Z",
  updated_at: "2026-09-25T00:00:00Z",
};

describe("taskReducer", () => {
  it("initializes with empty state", () => {
    expect(initialTaskState.taskId).toBeNull();
    expect(initialTaskState.task).toBeNull();
    expect(initialTaskState.status).toBeNull();
    expect(initialTaskState.history).toEqual([]);
  });

  it("SUBMIT_TASK sets taskId and resets state", () => {
    const state = taskReducer(initialTaskState, { type: "SUBMIT_TASK", taskId: "task-123" });
    expect(state.taskId).toBe("task-123");
    expect(state.task).toBeNull();
    expect(state.status).toBeNull();
  });

  it("SNAPSHOT for different task id does not change state", () => {
    const state = taskReducer(initialTaskState, { type: "SUBMIT_TASK", taskId: "task-123" });
    const nextTask = { ...mockTask, id: "other-task" };
    const newState = taskReducer(state, { type: "SNAPSHOT", task: nextTask });
    expect(newState.task).toBeNull();
  });

  it("SNAPSHOT for same task id updates task and status", () => {
    const state = taskReducer(initialTaskState, { type: "SUBMIT_TASK", taskId: "task-123" });
    const newState = taskReducer(state, { type: "SNAPSHOT", task: mockTask });
    expect(newState.task).toEqual(mockTask);
    expect(newState.status).toBe("queued");
  });

  it("SNAPSHOT creates history entry on first snapshot", () => {
    const state = taskReducer(initialTaskState, { type: "SUBMIT_TASK", taskId: "task-123" });
    const newState = taskReducer(state, { type: "SNAPSHOT", task: mockTask });
    expect(newState.history).toHaveLength(1);
    expect(newState.history[0]?.status).toBe("queued");
  });

  it("SNAPSHOT does not duplicate history if same status", () => {
    let state = taskReducer(initialTaskState, { type: "SUBMIT_TASK", taskId: "task-123" });
    state = taskReducer(state, { type: "SNAPSHOT", task: mockTask });
    const sameTask = { ...mockTask, updated_at: "2026-09-25T00:01:00Z" };
    const newState = taskReducer(state, { type: "SNAPSHOT", task: sameTask });
    expect(newState.history).toHaveLength(1);
  });

  it("ADD_EVENT appends to history when status differs", () => {
    let state = taskReducer(initialTaskState, { type: "SUBMIT_TASK", taskId: "task-123" });
    state = taskReducer(state, { type: "SNAPSHOT", task: mockTask });
    const newState = taskReducer(state, {
      type: "ADD_EVENT",
      event: { status: "analyzing_problem", timestamp: "2026-09-25T00:01:00Z" },
    });
    expect(newState.history).toHaveLength(2);
    expect(newState.status).toBe("analyzing_problem");
  });

  it("ADD_EVENT does not duplicate if same status as last entry", () => {
    let state = taskReducer(initialTaskState, { type: "SUBMIT_TASK", taskId: "task-123" });
    state = taskReducer(state, { type: "SNAPSHOT", task: mockTask });
    state = taskReducer(state, {
      type: "ADD_EVENT",
      event: { status: "queued", timestamp: "2026-09-25T00:01:00Z" },
    });
    expect(state.history).toHaveLength(1);
  });

  it("UPDATE_STATUS changes status without modifying history", () => {
    let state = taskReducer(initialTaskState, { type: "SUBMIT_TASK", taskId: "task-123" });
    state = taskReducer(state, { type: "SNAPSHOT", task: mockTask });
    const newState = taskReducer(state, { type: "UPDATE_STATUS", status: "completed" });
    expect(newState.status).toBe("completed");
    expect(newState.history).toHaveLength(1);
  });

  it("SET_RESULT updates result and error", () => {
    const state = taskReducer(initialTaskState, { type: "SET_RESULT", result: { foo: "bar" }, error: null });
    expect(state.result).toEqual({ foo: "bar" });
    expect(state.error).toBeNull();
  });

  it("CONNECTION updates connection state", () => {
    const state = taskReducer(initialTaskState, { type: "CONNECTION", state: "reconnecting" });
    expect(state.connection).toBe("reconnecting");
  });

  it("CLEAR resets to initial state", () => {
    let state = taskReducer(initialTaskState, { type: "SUBMIT_TASK", taskId: "task-123" });
    state = taskReducer(state, { type: "SNAPSHOT", task: mockTask });
    const newState = taskReducer(state, { type: "CLEAR" });
    expect(newState).toEqual(initialTaskState);
  });

  it("SNAPSHOT handles both result and error", () => {
    const state = taskReducer(initialTaskState, { type: "SUBMIT_TASK", taskId: "task-123" });
    const completedTask = {
      ...mockTask,
      status: "completed" as const,
      result: { approaches: [] },
    };
    const newState = taskReducer(state, { type: "SNAPSHOT", task: completedTask });
    expect(newState.result).toEqual({ approaches: [] });
    expect(newState.error).toBeNull();
  });
});
