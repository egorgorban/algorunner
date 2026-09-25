/**
 * Problem input form with textarea and language select (D-08, UI-01).
 * Accepts problem text in English or Russian and submits to the API.
 */

// eslint-disable-next-line @typescript-eslint/no-unused-vars
import * as React from "react";
import { useState } from "react";
import { createTask, ApiError } from "../api/client";
import type { ClientConfig, Language, TaskSubmission } from "../api/types";
import { LANGUAGE_LABELS } from "../lib/statusLabels";

interface ProblemInputProps {
  apiBase: string;
  config: ClientConfig;
  onSubmitted(taskId: string): void;
}

export function ProblemInput({
  apiBase,
  config,
  onSubmitted,
}: ProblemInputProps): React.ReactElement {
  const [text, setText] = useState("");
  const [language, setLanguage] = useState<Language>("ru");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const submission: TaskSubmission = {
        problem_text: text,
        language,
        examples: [],
      };
      const response = await createTask(apiBase, submission);
      onSubmitted(response.task_id);
    } catch (err) {
      if (err instanceof Error) {
        const apiErr = err as ApiError;
        let message = apiErr.message;
        if (apiErr.detail) {
          if (Array.isArray(apiErr.detail)) {
            message = apiErr.detail
              .map((d: Record<string, unknown>) => (d as Record<string, unknown>).msg || String(d))
              .join("; ");
          } else if (typeof apiErr.detail === "string") {
            message = apiErr.detail;
          }
        }
        setError(message);
      } else {
        setError(String(err));
      }
    } finally {
      setLoading(false);
    }
  }

  const isDisabled = !text.trim() || loading;

  return (
    <form onSubmit={handleSubmit} className="space-y-4 p-6">
      <div>
        <label htmlFor="language" className="block text-sm font-medium mb-2">
          Язык задачи
        </label>
        <select
          id="language"
          value={language}
          onChange={(e) => setLanguage(e.target.value as Language)}
          className="w-full px-4 py-2 border border-gray-300 rounded-md"
        >
          {(["en", "ru"] as const).map((lang) => (
            <option key={lang} value={lang}>
              {LANGUAGE_LABELS[lang]}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="problem" className="block text-sm font-medium mb-2">
          Описание задачи ({text.length} / {config.max_problem_chars})
        </label>
        <textarea
          id="problem"
          value={text}
          onChange={(e) => setText(e.target.value.slice(0, config.max_problem_chars))}
          placeholder="Введите описание задачи..."
          maxLength={config.max_problem_chars}
          className="w-full h-48 px-4 py-2 border border-gray-300 rounded-md font-mono text-sm"
        />
      </div>

      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={isDisabled}
        className={`w-full py-2 px-4 rounded-md font-medium ${
          isDisabled
            ? "bg-gray-300 text-gray-600 cursor-not-allowed"
            : "bg-blue-600 text-white hover:bg-blue-700"
        }`}
      >
        {loading ? "Отправка..." : "Отправить"}
      </button>
    </form>
  );
}
