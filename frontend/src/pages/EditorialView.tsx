/**
 * Full-page editorial view (UI-04, D-09).
 * Renders problem, difficulty, tags, collapsible approaches, edge cases, unverified approaches.
 */

// eslint-disable-next-line @typescript-eslint/no-unused-vars
import * as React from "react";
import { useTaskState } from "../context/TaskContext";
import { InlineText } from "../components/InlineText";
import { CodeBlock } from "../components/CodeBlock";
import {
  readCompletedResult,
  getRoleLabel,
  getDifficultyLabel,
  getUnverifiedStatusLabel,
} from "../lib/editorial";

export interface EditorialViewProps {
  onNewProblem: () => void;
}

export function EditorialView({ onNewProblem }: EditorialViewProps): React.ReactElement {
  const state = useTaskState();
  const { editorial, approaches, warnings } = readCompletedResult(state.result);

  if (!editorial) {
    // Fallback for missing or malformed editorial
    return (
      <div className="p-6 space-y-6">
        <div className="bg-yellow-50 border border-yellow-200 rounded px-4 py-3">
          <p className="text-gray-700">Разбор недоступен для этой задачи</p>
        </div>

        {approaches.length > 0 && (
          <div className="space-y-3">
            <h2 className="text-lg font-semibold">Подходы</h2>
            <table className="w-full border-collapse border border-gray-300 text-sm">
              <thead className="bg-gray-100">
                <tr>
                  <th className="border border-gray-300 px-3 py-2 text-left">Подход</th>
                  <th className="border border-gray-300 px-3 py-2 text-left">Техника</th>
                  <th className="border border-gray-300 px-3 py-2 text-left">Статус</th>
                  <th className="border border-gray-300 px-3 py-2 text-center">Итерации</th>
                </tr>
              </thead>
              <tbody>
                {approaches.map((app) => (
                  <tr key={app.approach_id}>
                    <td className="border border-gray-300 px-3 py-2">{app.name}</td>
                    <td className="border border-gray-300 px-3 py-2">{app.technique}</td>
                    <td className="border border-gray-300 px-3 py-2">{app.status}</td>
                    <td className="border border-gray-300 px-3 py-2 text-center">{app.iterations}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <button
          onClick={onNewProblem}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors"
        >
          Новая задача
        </button>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-8 max-w-4xl mx-auto">
      {/* Problem restatement and metadata */}
      <section className="space-y-4">
        <h1 className="text-3xl font-bold">
          <InlineText text={editorial.problem_restatement} />
        </h1>

        <div className="flex items-center gap-4 flex-wrap">
          <span className="inline-block px-3 py-1 bg-blue-100 text-blue-800 rounded font-semibold">
            {getDifficultyLabel(editorial.difficulty)}
          </span>
          {editorial.tags.map((tag) => (
            <span key={tag} className="inline-block px-2 py-1 bg-gray-200 text-gray-700 text-sm rounded">
              {tag}
            </span>
          ))}
        </div>
      </section>

      {/* Approaches */}
      <section className="space-y-4">
        {editorial.approaches.map((approach, index) => (
          <details key={approach.approach_id} open={index === 0} className="group border border-gray-300 rounded">
            <summary className="cursor-pointer p-4 bg-gray-50 hover:bg-gray-100 font-semibold flex items-center gap-2">
              <span className="group-open:rotate-90 inline-block transition-transform">▶</span>
              <span>{approach.title}</span>
              <span className="text-sm text-gray-600">({getRoleLabel(approach.role)})</span>
              <span className="text-xs text-gray-500">{approach.technique}</span>
            </summary>

            <div className="p-4 space-y-4 border-t border-gray-300">
              {/* Bridge from previous */}
              {approach.bridge_from_previous && (
                <div className="bg-blue-50 border-l-4 border-blue-400 px-4 py-3 rounded">
                  <p className="text-sm text-gray-700">
                    <strong>Связь:</strong> <InlineText text={approach.bridge_from_previous} />
                  </p>
                </div>
              )}

              {/* Intuition */}
              <div className="space-y-2">
                <h3 className="font-semibold text-lg">Интуиция</h3>
                <p className="text-gray-700">
                  <InlineText text={approach.intuition} />
                </p>
              </div>

              {/* Algorithm */}
              <div className="space-y-2">
                <h3 className="font-semibold text-lg">Алгоритм</h3>
                <p className="text-gray-700">
                  <InlineText text={approach.algorithm} />
                </p>
              </div>

              {/* Python code */}
              <div className="space-y-2">
                <h3 className="font-semibold text-lg">Python</h3>
                <CodeBlock code={approach.code_python} language="python" />
              </div>

              {/* Go code */}
              <div className="space-y-2">
                <h3 className="font-semibold text-lg">Go</h3>
                <CodeBlock code={approach.code_go} language="go" />
              </div>

              {/* Complexity */}
              <div className="space-y-2">
                <h3 className="font-semibold text-lg">Сложность</h3>
                <div className="space-y-1 text-gray-700">
                  <p>
                    <strong>Время:</strong> <InlineText text={approach.complexity_time} />
                  </p>
                  <p>
                    <strong>Память:</strong> <InlineText text={approach.complexity_space} />
                  </p>
                  <p className="text-sm text-gray-600">
                    <InlineText text={approach.complexity_justification} />
                  </p>
                </div>
              </div>

              {/* Notes */}
              {approach.notes.length > 0 && (
                <div className="space-y-2">
                  <h3 className="font-semibold text-lg">Заметки</h3>
                  <ul className="space-y-1 list-disc list-inside text-gray-700">
                    {approach.notes.map((note, i) => (
                      <li key={i}>
                        <InlineText text={note} />
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </details>
        ))}
      </section>

      {/* Edge cases */}
      {editorial.edge_cases.length > 0 && (
        <section className="space-y-4">
          <h2 className="text-2xl font-semibold">Граничные случаи</h2>
          <ul className="space-y-2 list-disc list-inside text-gray-700">
            {editorial.edge_cases.map((edge, i) => (
              <li key={i}>
                <InlineText text={edge} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Unverified approaches */}
      {editorial.unverified_approaches.length > 0 && (
        <section className="space-y-4">
          <h2 className="text-2xl font-semibold">Непроверенные подходы</h2>
          <div className="space-y-3">
            {editorial.unverified_approaches.map((unv) => (
              <div key={unv.approach_id} className="border border-gray-300 rounded p-4">
                <p className="font-semibold">{unv.name}</p>
                <p className="text-sm text-gray-600">{getUnverifiedStatusLabel(unv.status)}</p>
                {unv.note && (
                  <p className="text-sm text-gray-700 mt-2">
                    <InlineText text={unv.note} />
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="bg-gray-100 border border-gray-300 rounded px-4 py-3 text-sm text-gray-600">
          {warnings.map((w, i) => (
            <p key={i}>{w}</p>
          ))}
        </div>
      )}

      {/* New problem button */}
      <div className="pt-4 border-t border-gray-300">
        <button
          onClick={onNewProblem}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors"
        >
          Новая задача
        </button>
      </div>
    </div>
  );
}
