/**
 * Non-dismissible clarification prompt modal (UI-03, D-09, RESEARCH Pattern 7).
 * Only closes when user answers the question or on conflict/error recovery.
 */

import * as React from "react";
import { useEffect, useState } from "react";
import { codePointLength } from "../lib/validation";
import { getClarificationQuestion, answerClarification } from "../api/client";

interface ClarificationModalProps {
  apiBase: string;
  taskId: string;
  pending: { question: string } | { loading: true } | null;
  maxAnswerChars: number;
  onAnswered(): void;
  onConflict(): void;
}

export function ClarificationModal({
  apiBase,
  taskId,
  pending,
  maxAnswerChars,
  onAnswered,
  onConflict,
}: ClarificationModalProps): React.ReactElement | null {
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState<string | null>(
    pending && "question" in pending ? pending.question : null
  );
  const [fetching, setFetching] = useState(false);

  const answerLength = codePointLength(answer);
  const isSubmitDisabled =
    !answer.trim() || answerLength > maxAnswerChars || submitting || fetching;

  // Fetch question when loading state is shown
  useEffect(() => {
    if (!pending || !("loading" in pending)) {
      return;
    }

    const fetchQuestion = async (): Promise<void> => {
      setFetching(true);
      try {
        const q = await getClarificationQuestion(apiBase, taskId);
        if (q) {
          setQuestion(q);
        }
      } finally {
        setFetching(false);
      }
    };

    fetchQuestion();
  }, [pending, apiBase, taskId, question]);

  // Update question when pending changes
  useEffect(() => {
    if (pending && "question" in pending) {
      setQuestion(pending.question);
      setError(null);
    }
  }, [pending]);

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      const result = await answerClarification(apiBase, taskId, answer);

      if (result.kind === "accepted") {
        onAnswered();
      } else if (result.kind === "conflict") {
        onConflict();
      } else {
        setError(result.message);
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (!pending) {
    return null;
  }

  // Show loading state while fetching
  if ("loading" in pending && !question) {
    return (
      <div
        className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
        onClick={(e) => {
          // Prevent dismiss on backdrop click
          e.preventDefault();
        }}
        onKeyDown={(e) => {
          // Prevent dismiss on Escape
          if (e.key === "Escape") {
            e.preventDefault();
          }
        }}
      >
        <div className="bg-white rounded-lg p-8 max-w-md w-full mx-4 shadow-lg">
          <h2 className="text-lg font-bold mb-4">Нужно уточнение</h2>
          <p className="text-gray-700">Загружаем вопрос…</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={(e) => {
        // Prevent dismiss on backdrop click
        e.preventDefault();
      }}
      onKeyDown={(e) => {
        // Prevent dismiss on Escape
        if (e.key === "Escape") {
          e.preventDefault();
        }
      }}
    >
      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-lg p-8 max-w-md w-full mx-4 shadow-lg space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-bold">Нужно уточнение</h2>

        {question && (
          <div className="bg-gray-50 p-4 rounded border border-gray-200 text-sm text-gray-800 whitespace-pre-line">
            {question}
          </div>
        )}

        <div>
          <label htmlFor="clarification-answer" className="block text-sm font-medium mb-2">
            Ответ ({answerLength} / {maxAnswerChars})
          </label>
          <textarea
            id="clarification-answer"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder="Введите ваш ответ..."
            className={`w-full h-24 px-3 py-2 border rounded-md font-mono text-sm ${
              answerLength > maxAnswerChars ? "border-red-500" : "border-gray-300"
            }`}
          />
          {answerLength > maxAnswerChars && (
            <div className="text-sm text-red-600 mt-1">
              Превышен лимит: {answerLength} из {maxAnswerChars} символов
            </div>
          )}
        </div>

        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded text-sm">
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
          {submitting || fetching ? "Отправка..." : "Ответить"}
        </button>
      </form>
    </div>
  );
}
