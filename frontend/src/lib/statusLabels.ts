/**
 * Russian status labels and language labels (UI-02, D-08).
 * Record<TaskStatus, string> is exhaustive — missing labels are compile errors.
 */

import type { TaskStatus, Language } from "../api/types";

export const STATUS_LABELS: Record<TaskStatus, string> = {
  queued: "В очереди",
  analyzing_problem: "Анализ задачи",
  designing_solution: "Проектирование решений",
  generating_code: "Генерация кода",
  generating_tests: "Генерация тестов",
  executing_tests: "Запуск тестов",
  reviewing: "Ревью решения",
  correcting: "Исправление",
  awaiting_clarification: "Нужно уточнение",
  writing_editorial: "Написание разбора",
  completed: "Готово",
  failed: "Ошибка",
};

// Verify all statuses are covered
const _exhaustivenessCheck: Record<TaskStatus, string> = STATUS_LABELS;
void _exhaustivenessCheck;

export const LANGUAGE_LABELS: Record<Language, string> = {
  en: "English",
  ru: "Русский",
};
