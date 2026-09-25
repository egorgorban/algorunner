/**
 * Status view showing task progress and history (UI-02, D-02).
 * Displays current status, elapsed time, and history of status changes.
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import * as React from "react";
import { useTaskState } from "../context/TaskContext";
import type { ClientConfig } from "../api/types";
import { STATUS_LABELS } from "../lib/statusLabels";

interface StatusViewProps {
  apiBase?: string;
  config?: ClientConfig;
  onNewProblem(): void;
}

export function StatusView({
  onNewProblem,
}: StatusViewProps): React.ReactElement {
  const state = useTaskState();

  return (
    <div className="space-y-6 p-6">
      <div>
        <h2 className="text-2xl font-bold mb-4">Статус задачи</h2>

        {state.status && (
          <div className="text-lg mb-4">
            <span className="font-semibold">Текущий статус: </span>
            <span className="text-blue-600">{STATUS_LABELS[state.status]}</span>
          </div>
        )}

        {state.connection === "reconnecting" && (
          <div className="bg-yellow-100 border border-yellow-400 text-yellow-700 px-4 py-3 rounded mb-4">
            Соединение потеряно, переподключаемся…
          </div>
        )}

        {state.error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
            <div className="font-semibold">{state.error.code}</div>
            <div>{state.error.message}</div>
          </div>
        )}

        {state.task?.problem_text && (
          <div className="mb-4">
            <div className="text-sm text-gray-600 mb-2">Задача:</div>
            <div className="bg-gray-50 p-4 rounded border border-gray-200 max-h-32 overflow-auto">
              <p className="whitespace-pre-wrap text-sm">{state.task.problem_text.slice(0, 300)}</p>
              {state.task.problem_text.length > 300 && (
                <p className="text-xs text-gray-500 mt-2">...</p>
              )}
            </div>
          </div>
        )}

        {state.history.length > 0 && (
          <div className="mb-4">
            <div className="text-sm font-semibold mb-2">История статусов:</div>
            <ol className="list-decimal list-inside space-y-1">
              {state.history.map((entry, idx) => (
                <li key={idx} className="text-sm text-gray-700">
                  {STATUS_LABELS[entry.status]} — {new Date(entry.at).toLocaleTimeString("ru-RU")}
                </li>
              ))}
            </ol>
            <p className="text-xs text-gray-500 mt-2 italic">
              Подходы решаются параллельно, поэтому статусы могут чередоваться.
            </p>
          </div>
        )}
      </div>

      <button
        onClick={onNewProblem}
        className="w-full py-2 px-4 rounded-md font-medium bg-gray-200 text-gray-800 hover:bg-gray-300"
      >
        Новая задача
      </button>
    </div>
  );
}
