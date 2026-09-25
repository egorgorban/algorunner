/**
 * Main app: config fetch, task submission, live status view (UI-01, UI-02, D-20).
 * @jsx React.createElement
 */

// eslint-disable-next-line @typescript-eslint/no-unused-vars
import * as React from "react";
import { useState, useEffect } from "react";
import { fetchConfig, resolveApiBase } from "./api/client";
import type { ClientConfig } from "./api/types";
import { useTaskState, useTaskDispatch } from "./context/TaskContext";
import { useTaskEvents } from "./hooks/useTaskEvents";
import { ProblemInput } from "./pages/ProblemInput";
import { StatusView } from "./pages/StatusView";
import { EditorialView } from "./pages/EditorialView";

function App(): React.ReactElement {
  const [config, setConfig] = useState<ClientConfig | null>(null);
  const [configLoading, setConfigLoading] = useState(true);
  const [configError, setConfigError] = useState<string | null>(null);
  const [apiBase, setApiBase] = useState("");

  const state = useTaskState();
  const dispatch = useTaskDispatch();

  // Fetch config on mount
  useEffect(() => {
    async function initConfig(): Promise<void> {
      try {
        const cfg = await fetchConfig("");
        setConfig(cfg);
        setApiBase(resolveApiBase(cfg, ""));
      } catch (err) {
        setConfigError(err instanceof Error ? err.message : String(err));
      } finally {
        setConfigLoading(false);
      }
    }

    initConfig();
  }, []);

  // Check URL for ?task=<uuid>
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const taskId = params.get("task");
    if (taskId && !state.taskId) {
      dispatch({ type: "SUBMIT_TASK", taskId });
    }
  }, [state.taskId, dispatch]);

  // Connect WebSocket when task is tracked
  useTaskEvents(state.taskId, config, dispatch);

  if (configLoading) {
    return <div className="p-6 text-center">Загрузка...</div>;
  }

  if (configError || !config) {
    return (
      <div className="p-6">
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          <strong>Ошибка загрузки конфигурации:</strong> {configError}
        </div>
      </div>
    );
  }

  function handleTaskSubmitted(taskId: string): void {
    dispatch({ type: "SUBMIT_TASK", taskId });
    window.history.replaceState({}, "", `?task=${encodeURIComponent(taskId)}`);
  }

  function handleNewProblem(): void {
    dispatch({ type: "CLEAR" });
    window.history.replaceState({}, "", window.location.pathname);
  }

  return (
    <div className="min-h-screen bg-white">
      <header className="bg-gray-50 border-b border-gray-200 p-6">
        <h1 className="text-3xl font-bold">AlgoRunner</h1>
        <p className="text-gray-600">Решения для задач собеседований</p>
      </header>

      <main>
        {!state.taskId ? (
          <div className="max-w-2xl mx-auto">
            <ProblemInput
              apiBase={apiBase}
              config={config}
              onSubmitted={handleTaskSubmitted}
            />
          </div>
        ) : state.status === "completed" ? (
          <EditorialView onNewProblem={handleNewProblem} />
        ) : (
          <div className="max-w-2xl mx-auto">
            <StatusView onNewProblem={handleNewProblem} />
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
