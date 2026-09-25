/**
 * Editorial result narrowing and validation (UI-04, D-09).
 * Typed guards, label maps, and code block extraction.
 */

import type {
  Editorial,
  EditorialApproach,
  UnverifiedApproach,
  ApproachIndexEntry,
  Difficulty,
  ApproachRole,
  UnverifiedStatus,
} from "../api/types";
import {
  DIFFICULTIES as DIFFICULTIES_ARRAY,
  APPROACH_ROLES as APPROACH_ROLES_ARRAY,
  UNVERIFIED_STATUSES as UNVERIFIED_STATUSES_ARRAY,
} from "../api/types";

/**
 * Type guard: check if value is a valid Editorial object.
 * Guards every field: strings, arrays, enums, nullability.
 */
export function isEditorial(value: unknown): value is Editorial {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;

  // Check required string fields
  if (
    typeof obj.problem_restatement !== "string" ||
    typeof obj.difficulty !== "string" ||
    !DIFFICULTIES_ARRAY.includes(obj.difficulty as Difficulty)
  ) {
    return false;
  }

  // Check tags array
  if (!Array.isArray(obj.tags) || !obj.tags.every((t) => typeof t === "string")) {
    return false;
  }

  // Check approaches array
  if (!Array.isArray(obj.approaches)) {
    return false;
  }
  for (const app of obj.approaches) {
    if (!isEditorialApproach(app)) {
      return false;
    }
  }

  // Check edge_cases array
  if (!Array.isArray(obj.edge_cases) || !obj.edge_cases.every((e) => typeof e === "string")) {
    return false;
  }

  // Check unverified_approaches array
  if (!Array.isArray(obj.unverified_approaches)) {
    return false;
  }
  for (const unv of obj.unverified_approaches) {
    if (!isUnverifiedApproach(unv)) {
      return false;
    }
  }

  return true;
}

function isEditorialApproach(value: unknown): value is EditorialApproach {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;

  return (
    typeof obj.approach_id === "number" &&
    typeof obj.role === "string" &&
    APPROACH_ROLES_ARRAY.includes(obj.role as ApproachRole) &&
    typeof obj.technique === "string" &&
    typeof obj.title === "string" &&
    (obj.bridge_from_previous === null || typeof obj.bridge_from_previous === "string") &&
    typeof obj.intuition === "string" &&
    typeof obj.algorithm === "string" &&
    typeof obj.code_python === "string" &&
    typeof obj.code_go === "string" &&
    typeof obj.complexity_time === "string" &&
    typeof obj.complexity_space === "string" &&
    typeof obj.complexity_justification === "string" &&
    Array.isArray(obj.notes) &&
    obj.notes.every((n) => typeof n === "string")
  );
}

function isUnverifiedApproach(value: unknown): value is UnverifiedApproach {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;

  return (
    typeof obj.approach_id === "number" &&
    typeof obj.name === "string" &&
    typeof obj.status === "string" &&
    UNVERIFIED_STATUSES_ARRAY.includes(obj.status as UnverifiedStatus) &&
    typeof obj.note === "string"
  );
}

/**
 * Read a CompletedResult from an untyped result.
 * Returns the narrowed Editorial (or null), the approaches index, and any warnings.
 * Never throws.
 */
export function readCompletedResult(result: unknown): {
  editorial: Editorial | null;
  approaches: ApproachIndexEntry[];
  warnings: string[];
} {
  if (typeof result !== "object" || result === null) {
    return { editorial: null, approaches: [], warnings: [] };
  }

  const obj = result as Record<string, unknown>;

  // Try to parse approaches (index)
  let approaches: ApproachIndexEntry[] = [];
  if (Array.isArray(obj.approaches)) {
    approaches = obj.approaches.filter((a) => {
      if (typeof a !== "object" || a === null) return false;
      const ap = a as Record<string, unknown>;
      return (
        typeof ap.approach_id === "number" &&
        typeof ap.name === "string" &&
        typeof ap.technique === "string" &&
        typeof ap.role === "string" &&
        typeof ap.status === "string" &&
        typeof ap.iterations === "number"
      );
    }) as ApproachIndexEntry[];
  }

  // Try to parse editorial
  let editorial: Editorial | null = null;
  if (typeof obj.editorial === "object" && obj.editorial !== null && isEditorial(obj.editorial)) {
    editorial = obj.editorial;
  }

  // Try to parse editorial_warnings
  let warnings: string[] = [];
  if (Array.isArray(obj.editorial_warnings)) {
    warnings = obj.editorial_warnings.filter((w) => typeof w === "string");
  }

  return { editorial, approaches, warnings };
}

/**
 * Extract code blocks from an editorial.
 * Returns exactly one python and one go block per approach, in order.
 */
export function approachCodeBlocks(
  editorial: Editorial
): Array<{ approachId: number; language: "python" | "go"; code: string }> {
  const blocks: Array<{ approachId: number; language: "python" | "go"; code: string }> = [];

  for (const approach of editorial.approaches) {
    blocks.push({
      approachId: approach.approach_id,
      language: "python",
      code: approach.code_python,
    });
    blocks.push({
      approachId: approach.approach_id,
      language: "go",
      code: approach.code_go,
    });
  }

  return blocks;
}

/**
 * Russian labels for roles.
 */
const roleLabels: Record<ApproachRole, string> = {
  brute_force: "Полный перебор",
  optimized: "Оптимальное решение",
  alternative: "Альтернативный подход",
};

export function getRoleLabel(role: ApproachRole): string {
  return roleLabels[role];
}

/**
 * Russian labels for difficulties.
 */
const difficultyLabels: Record<Difficulty, string> = {
  easy: "Лёгкая",
  medium: "Средняя",
  hard: "Сложная",
};

export function getDifficultyLabel(difficulty: Difficulty): string {
  return difficultyLabels[difficulty];
}

/**
 * Russian labels for unverified statuses.
 */
const unverifiedStatusLabels: Record<UnverifiedStatus, string> = {
  exhausted: "Не прошёл проверку",
  timed_out: "Не уложился во время",
  errored: "Ошибка при решении",
};

export function getUnverifiedStatusLabel(status: UnverifiedStatus): string {
  return unverifiedStatusLabels[status];
}
