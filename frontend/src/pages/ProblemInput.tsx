/**
 * Problem input form with textarea, language select, and examples (D-08, UI-01).
 * Accepts problem text in English or Russian with multiple examples and submits to the API.
 */

// eslint-disable-next-line @typescript-eslint/no-unused-vars
import * as React from "react";
import { useState } from "react";
import { createTask } from "../api/client";
import { formatApiError } from "../api/client";
import { codePointLength, validateSubmission } from "../lib/validation";
import type { ClientConfig, Language } from "../api/types";
import { ExampleList } from "../components/ExampleList";
import { LANGUAGE_LABELS } from "../lib/statusLabels";

interface ExampleRow {
  input: string;
  output: string;
  explanation: string;
}

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
  const [examples, setExamples] = useState<ExampleRow[]>([{ input: "", output: "", explanation: "" }]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<Record<number, string>>({});

  const problemLength = codePointLength(text);

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setError(null);
    setValidationErrors({});

    // Validate before submitting
    const validationResult = validateSubmission(
      {
        problemText: text,
        language,
        examples,
      },
      {
        max_problem_chars: config.max_problem_chars,
        max_examples: config.max_examples,
      }
    );

    if (!validationResult.ok) {
      setValidationErrors(validationResult.rowErrors);
      if (validationResult.problemTextError) {
        setError(validationResult.problemTextError);
      } else if (validationResult.examplesError) {
        setError(validationResult.examplesError);
      }
      return;
    }

    setLoading(true);

    try {
      const response = await createTask(apiBase, validationResult.submission);
      onSubmitted(response.task_id);
    } catch (err: unknown) {
      const message = formatApiError(err);
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  const isSubmitDisabled =
    !text.trim() ||
    loading ||
    Object.keys(validationErrors).length > 0 ||
    (error !== null && error !== "");

  return (
    <form onSubmit={handleSubmit} className="space-y-6 p-6 max-w-4xl mx-auto">
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
          Описание задачи ({problemLength} / {config.max_problem_chars})
        </label>
        <textarea
          id="problem"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Введите описание задачи..."
          className={`w-full h-48 px-4 py-2 border rounded-md font-mono text-sm ${
            problemLength > config.max_problem_chars ? "border-red-500" : "border-gray-300"
          }`}
        />
        {problemLength > config.max_problem_chars && (
          <div className="text-sm text-red-600 mt-1">
            Превышен лимит: {problemLength} из {config.max_problem_chars} символов
          </div>
        )}
      </div>

      <ExampleList
        rows={examples}
        maxRows={config.max_examples}
        rowErrors={validationErrors}
        onChange={setExamples}
      />

      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={isSubmitDisabled}
        className={`w-full py-2 px-4 rounded-md font-medium ${
          isSubmitDisabled
            ? "bg-gray-300 text-gray-600 cursor-not-allowed"
            : "bg-blue-600 text-white hover:bg-blue-700"
        }`}
      >
        {loading ? "Отправка..." : "Отправить"}
      </button>
    </form>
  );
}
