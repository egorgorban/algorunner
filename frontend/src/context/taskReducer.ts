/**
 * Task state reducer for managing the submitted task's lifecycle (D-07, UI-02).
 * Actions: SUBMIT_TASK, SNAPSHOT, ADD_EVENT, UPDATE_STATUS, SET_RESULT, CONNECTION, CLEAR.
 */

import type { TaskRecord, TaskStatus, TaskError } from "../api/types";

export interface HistoryEntry {
  status: TaskStatus;
  at: string; // ISO8601 timestamp
}

export interface TaskViewState {
  taskId: string | null;
  task: TaskRecord | null;
  status: TaskStatus | null;
  history: HistoryEntry[];
  result: Record<string, unknown> | null;
  error: TaskError | null;
  connection: "connecting" | "open" | "reconnecting" | "closed";
}

export const initialTaskState: TaskViewState = {
  taskId: null,
  task: null,
  status: null,
  history: [],
  result: null,
  error: null,
  connection: "closed",
};

export type TaskAction =
  | { type: "SUBMIT_TASK"; taskId: string }
  | { type: "SNAPSHOT"; task: TaskRecord }
  | { type: "ADD_EVENT"; event: { status: TaskStatus; timestamp: string } }
  | { type: "UPDATE_STATUS"; status: TaskStatus }
  | { type: "SET_RESULT"; result: Record<string, unknown> | null; error: TaskError | null }
  | { type: "CONNECTION"; state: "connecting" | "open" | "reconnecting" | "closed" }
  | { type: "CLEAR" };

export function taskReducer(state: TaskViewState, action: TaskAction): TaskViewState {
  switch (action.type) {
    case "SUBMIT_TASK": {
      return {
        ...initialTaskState,
        taskId: action.taskId,
      };
    }

    case "SNAPSHOT": {
      // Ignore snapshots for different tasks
      if (state.taskId !== action.task.id) {
        return state;
      }

      // Seed history if empty
      const history = state.history.length === 0 ? [{ status: action.task.status, at: action.task.updated_at }] : state.history;

      // Append to history if status is different from the last entry
      const lastEntry = history[history.length - 1];
      const newHistory =
        lastEntry && lastEntry.status === action.task.status
          ? history
          : [...history, { status: action.task.status, at: action.task.updated_at }];

      return {
        ...state,
        task: action.task,
        status: action.task.status,
        history: newHistory,
        result: action.task.result ?? null,
        error: action.task.error ?? null,
      };
    }

    case "ADD_EVENT": {
      const { status: newStatus, timestamp } = action.event;
      const lastEntry = state.history[state.history.length - 1];
      const newHistory =
        lastEntry && lastEntry.status === newStatus
          ? state.history
          : [...state.history, { status: newStatus, at: timestamp }];

      return {
        ...state,
        status: newStatus,
        history: newHistory,
      };
    }

    case "UPDATE_STATUS": {
      return {
        ...state,
        status: action.status,
      };
    }

    case "SET_RESULT": {
      return {
        ...state,
        result: action.result,
        error: action.error,
      };
    }

    case "CONNECTION": {
      return {
        ...state,
        connection: action.state,
      };
    }

    case "CLEAR": {
      return initialTaskState;
    }
  }
}
