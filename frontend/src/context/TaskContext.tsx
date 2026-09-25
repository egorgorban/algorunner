/**
 * React Context for task state management (D-07).
 * Provides TaskViewState and dispatch to the entire app.
 */

// eslint-disable-next-line @typescript-eslint/no-unused-vars
import * as React from "react";
import { createContext, useContext, useReducer } from "react";
import type { ReactNode } from "react";
import { taskReducer, initialTaskState, type TaskViewState, type TaskAction } from "./taskReducer";

interface TaskContextType {
  state: TaskViewState;
  dispatch: React.Dispatch<TaskAction>;
}

const TaskContext = createContext<TaskContextType | undefined>(undefined);

export function TaskProvider({ children }: { children: ReactNode }): React.ReactElement {
  const [state, dispatch] = useReducer(taskReducer, initialTaskState);

  return (
    <TaskContext.Provider value={{ state, dispatch }}>
      {children}
    </TaskContext.Provider>
  );
}

export function useTaskState(): TaskViewState {
  const context = useContext(TaskContext);
  if (!context) {
    throw new Error("useTaskState must be used within TaskProvider");
  }
  return context.state;
}

export function useTaskDispatch(): React.Dispatch<TaskAction> {
  const context = useContext(TaskContext);
  if (!context) {
    throw new Error("useTaskDispatch must be used within TaskProvider");
  }
  return context.dispatch;
}
