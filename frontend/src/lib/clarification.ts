/**
 * Clarification state selector for detecting when a modal should be shown (UI-03, RESEARCH Pattern 7).
 * Returns question, loading state, or null based on task state alignment.
 */

import type { TaskViewState } from "../context/taskReducer";

export type PendingClarification =
  | { question: string }
  | { loading: true }
  | null;

/**
 * Determine if and what clarification is pending.
 * - Returns {question} when status is awaiting_clarification and last snapshot matches
 * - Returns {loading: true} when status is awaiting_clarification but snapshot doesn't match yet
 * - Returns null otherwise, including right after UPDATE_STATUS
 */
export function pendingClarification(state: TaskViewState): PendingClarification {
  // Only show modal if current status is awaiting_clarification
  if (state.status !== "awaiting_clarification") {
    return null;
  }

  // If we have a task snapshot, check if it's in awaiting_clarification with a question
  if (state.task && state.task.status === "awaiting_clarification" && state.task.clarification_question) {
    return {
      question: state.task.clarification_question,
    };
  }

  // Status says awaiting_clarification but snapshot hasn't caught up yet (or has no question)
  // Show loading state so we can fetch the question
  return {
    loading: true,
  };
}
