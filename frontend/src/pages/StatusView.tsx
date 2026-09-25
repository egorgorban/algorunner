/**
 * Status view showing task progress and history (UI-02, D-02).
 * Displays current status with elapsed time, history of status changes, and error details.
 * Includes clarification modal for paused tasks (UI-03).
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import * as React from "react";
import { useTaskState, useTaskDispatch } from "../context/TaskContext";
import type { ClientConfig } from "../api/types";
import { STATUS_LABELS } from "../lib/statusLabels";
import { StatusIndicator } from "../components/StatusIndicator";
import { ClarificationModal } from "../components/ClarificationModal";
import { pendingClarification } from "../lib/clarification";
import { getTask } from "../api/client";

interface StatusViewProps {
  apiBase?: string;
  config?: ClientConfig;
  onNewProblem(): void;
}

export function StatusView({
  apiBase = "",
  config,
  onNewProblem,
}: StatusViewProps): React.ReactElement {
  const state = useTaskState();
  const dispatch = useTaskDispatch();

  if (!state.task || !state.status) {
    return <div className="p-6 text-center text-gray-500">Загрузка задачи...</div>;
  }

  return (
    <div className="space-y-6 p-6">
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-2xl font-bold mb-6">Статус задачи</h2>

        {/* Status indicator with elapsed time */}
        <div className="mb-6">
          <StatusIndicator
            status={state.status}
            createdAt={state.task.created_at}
            updatedAt={state.task.updated_at}
          />
        </div>

        {/* Reconnection notice */}
        {state.connection === "reconnecting" && (
          <div className="bg-yellow-100 border border-yellow-400 text-yellow-700 px-4 py-3 rounded mb-6">
            Соединение потеряно, переподключаемся…
          </div>
        )}

        {/* Error display */}
        {state.error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-6">
            <div className="font-semibold text-lg mb-2">{state.error.code}</div>
            <div className="text-base">{state.error.message}</div>
          </div>
        )}

        {/* Problem statement */}
        {state.task.problem_text && (
          <div className="mb-6">
            <div className="text-sm font-semibold text-gray-700 mb-2">Задача:</div>
            <div className="bg-gray-50 p-4 rounded border border-gray-200 max-h-40 overflow-auto">
              <p className="whitespace-pre-wrap text-sm text-gray-800">
                {state.task.problem_text.slice(0, 500)}
              </p>
              {state.task.problem_text.length > 500 && (
                <p className="text-xs text-gray-500 mt-2">...</p>
              )}
            </div>
          </div>
        )}

        {/* Status history */}
        {state.history.length > 0 && (
          <div className="mb-6">
            <div className="text-sm font-semibold text-gray-700 mb-3">История статусов:</div>
            <ol className="list-decimal list-inside space-y-2 border-l-4 border-blue-300 pl-4">
              {state.history.map((entry, idx) => (
                <li key={idx} className="text-sm text-gray-700">
                  <span className="font-medium">{STATUS_LABELS[entry.status]}</span>
                  <span className="text-gray-500 text-xs ml-2">
                    {new Date(entry.at).toLocaleTimeString("ru-RU")}
                  </span>
                </li>
              ))}
            </ol>
            <p className="text-xs text-gray-500 mt-3 italic">
              ℹ️ Подходы решаются параллельно, поэтому статусы могут чередоваться.
            </p>
          </div>
        )}

        {/* Completion message */}
        {state.status === "completed" && (
          <div className="bg-green-50 border border-green-200 rounded p-4 mb-6">
            <p className="text-green-800 font-semibold">✓ Готово</p>
          </div>
        )}
      </div>

      <button
        onClick={onNewProblem}
        className="w-full py-3 px-4 rounded-md font-medium bg-gray-100 text-gray-800 hover:bg-gray-200 transition"
      >
        ← Новая задача
      </button>

      {/* Clarification modal */}
      {config && state.taskId && (
        <ClarificationModal
          apiBase={apiBase}
          taskId={state.taskId ?? ""}
          pending={pendingClarification(state)}
          maxAnswerChars={config.max_answer_chars}
          onAnswered={() => {
            dispatch({ type: "UPDATE_STATUS", status: "analyzing_problem" });
          }}
          onConflict={async () => {
            try {
              if (state.taskId) {
                const updatedTask = await getTask(apiBase, state.taskId);
                dispatch({ type: "SNAPSHOT", task: updatedTask });
              }
            } catch {
              // Leave state as-is; the stream will correct it
            }
          }}
        />
      )}
    </div>
  );
}
