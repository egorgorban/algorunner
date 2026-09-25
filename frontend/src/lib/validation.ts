/**
 * Client-side validation mirroring API limits and constraints (UI-01, Pitfall 10).
 * Code-point counting, example validation, submission gate.
 */

import type { Example, TaskSubmission, Language } from "../api/types";

/**
 * Count code points in a string, matching Python's len() behavior.
 * Iterates the string to count each Unicode code point as 1.
 */
export function codePointLength(text: string): number {
  return [...text].length;
}

export interface ValidationLimits {
  max_problem_chars: number;
  max_examples: number;
}

export interface ValidationSuccess {
  ok: true;
  submission: TaskSubmission;
}

export interface ValidationFailure {
  ok: false;
  problemTextError?: string;
  rowErrors: Record<number, string>;
  examplesError?: string;
}

export type ValidationResult = ValidationSuccess | ValidationFailure;

export interface FormData {
  problemText: string;
  language: Language;
  examples: Array<{ input: string; output: string; explanation: string }>;
}

export function validateSubmission(form: FormData, limits: ValidationLimits): ValidationResult {
  const rowErrors: Record<number, string> = {};
  let problemTextError: string | undefined;
  let examplesError: string | undefined;

  // Validate problem text: not blank and within limits
  const trimmedText = form.problemText.trim();
  if (!trimmedText) {
    problemTextError = "Введите условие задачи";
  } else {
    const problemLength = codePointLength(form.problemText);
    if (problemLength > limits.max_problem_chars) {
      problemTextError = `Слишком длинное условие: ${problemLength} из ${limits.max_problem_chars} символов`;
    }
  }

  // Filter and validate examples
  const validRows: Example[] = [];

  for (let i = 0; i < form.examples.length; i++) {
    const row = form.examples[i];
    if (!row) continue;
    const inputTrimmed = row.input.trim();
    const outputTrimmed = row.output.trim();
    const explanationTrimmed = row.explanation.trim();

    // Skip rows that are completely empty
    if (!inputTrimmed && !outputTrimmed && !explanationTrimmed) {
      continue;
    }

    // Check for half-filled rows (only input or only output)
    if ((inputTrimmed && !outputTrimmed) || (!inputTrimmed && outputTrimmed)) {
      rowErrors[i] = "Заполните и вход, и выход";
      continue;
    }

    // Row is valid (has both input and output)
    if (inputTrimmed && outputTrimmed) {
      validRows.push({
        input: row.input,
        output: row.output,
        explanation: explanationTrimmed ? row.explanation : null,
      });
    }
  }

  // Check example count
  if (validRows.length > limits.max_examples) {
    examplesError = `Не больше ${limits.max_examples} примеров`;
  }

  // Return result
  if (problemTextError || Object.keys(rowErrors).length > 0 || examplesError) {
    return {
      ok: false,
      problemTextError,
      rowErrors,
      examplesError,
    };
  }

  return {
    ok: true,
    submission: {
      problem_text: form.problemText,
      language: form.language,
      examples: validRows,
    },
  };
}
