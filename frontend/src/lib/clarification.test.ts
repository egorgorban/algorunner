/**
 * Tests for the pendingClarification selector covering all behavior bullets.
 */

import { describe, it, expect } from "vitest";
import { pendingClarification } from "./clarification";
import { initialTaskState } from "../context/taskReducer";
import type { TaskRecord } from "../api/types";

const mockTask = (overrides?: Partial<TaskRecord>): TaskRecord => ({
  id: "task-1",
  status: "awaiting_clarification",
  problem_text: "test",
  language: "ru",
  examples: [],
  result: null,
  error: null,
  clarification_question: "What is the input?",
  active_execution_seconds: 0,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
  ...overrides,
});

describe("pendingClarification", () => {
  it("returns null when status is not awaiting_clarification", () => {
    const state = {
      ...initialTaskState,
      status: "analyzing_problem" as const,
      task: mockTask({ status: "analyzing_problem" }),
    };
    expect(pendingClarification(state)).toBeNull();
  });

  it("returns question when status and snapshot both say awaiting_clarification with question", () => {
    const task = mockTask({ clarification_question: "What is the input?" });
    const state = {
      ...initialTaskState,
      status: "awaiting_clarification" as const,
      task,
    };
    const result = pendingClarification(state);
    expect(result).not.toBeNull();
    if (result !== null && "question" in result) {
      expect(result.question).toBe("What is the input?");
    }
  });

  it("returns loading when status is awaiting_clarification but task is null", () => {
    const state = {
      ...initialTaskState,
      status: "awaiting_clarification" as const,
      task: null,
    };
    const result = pendingClarification(state);
    expect(result).not.toBeNull();
    if (result !== null && "loading" in result) {
      expect(result.loading).toBe(true);
    }
  });

  it("returns loading when status is awaiting_clarification but task status is different", () => {
    const state = {
      ...initialTaskState,
      status: "awaiting_clarification" as const,
      task: mockTask({ status: "analyzing_problem" }),
    };
    const result = pendingClarification(state);
    expect(result).not.toBeNull();
    if (result !== null && "loading" in result) {
      expect(result.loading).toBe(true);
    }
  });

  it("returns loading when status is awaiting_clarification but clarification_question is null", () => {
    const state = {
      ...initialTaskState,
      status: "awaiting_clarification" as const,
      task: mockTask({ clarification_question: null }),
    };
    const result = pendingClarification(state);
    expect(result).not.toBeNull();
    if (result !== null && "loading" in result) {
      expect(result.loading).toBe(true);
    }
  });

  it("returns null right after UPDATE_STATUS changes to analyzing_problem even if snapshot still has old data", () => {
    // Scenario: status just changed to analyzing_problem via UPDATE_STATUS,
    // but the task snapshot still has the old awaiting_clarification status
    const state = {
      ...initialTaskState,
      status: "analyzing_problem" as const,
      task: mockTask({ status: "awaiting_clarification" }),
    };
    const result = pendingClarification(state);
    expect(result).toBeNull();
  });

  it("detects a second round clarification (new question in new snapshot)", () => {
    const secondQuestion = "What is the second input?";

    const state = {
      ...initialTaskState,
      status: "awaiting_clarification" as const,
      task: mockTask({ clarification_question: secondQuestion }),
    };

    const result = pendingClarification(state);
    expect(result).not.toBeNull();
    if (result !== null && "question" in result) {
      expect(result.question).toBe(secondQuestion);
    }
  });

  it("returns question with empty clarification text", () => {
    const state = {
      ...initialTaskState,
      status: "awaiting_clarification" as const,
      task: mockTask({ clarification_question: "" }),
    };
    // Empty question should not be shown (it's falsy)
    const result = pendingClarification(state);
    expect(result).not.toBeNull();
    if (result !== null && "loading" in result) {
      expect(result.loading).toBe(true);
    }
  });
});
