/**
 * TypeScript mirrors of backend schema contracts (UI-01, UI-02, D-12).
 * All values, enum names, and array bounds are verbatim from Python schemas.
 */

export const TASK_STATUSES = [
  "queued",
  "analyzing_problem",
  "designing_solution",
  "generating_code",
  "generating_tests",
  "executing_tests",
  "reviewing",
  "correcting",
  "awaiting_clarification",
  "writing_editorial",
  "completed",
  "failed",
] as const;

export type TaskStatus = (typeof TASK_STATUSES)[number];

export const TERMINAL_STATUSES = new Set<TaskStatus>([
  "completed",
  "failed",
  "awaiting_clarification",
] as const);

export const LANGUAGES = ["en", "ru"] as const;
export type Language = (typeof LANGUAGES)[number];

export const DIFFICULTIES = ["easy", "medium", "hard"] as const;
export type Difficulty = (typeof DIFFICULTIES)[number];

export const APPROACH_ROLES = ["brute_force", "optimized", "alternative"] as const;
export type ApproachRole = (typeof APPROACH_ROLES)[number];

export const APPROACH_STATUSES = ["verified", "exhausted", "timed_out", "errored"] as const;
export type ApproachStatus = (typeof APPROACH_STATUSES)[number];

export const UNVERIFIED_STATUSES = ["exhausted", "timed_out", "errored"] as const;
export type UnverifiedStatus = (typeof UNVERIFIED_STATUSES)[number];

export interface Example {
  input: string;
  output: string;
  explanation: string | null;
}

export interface TaskSubmission {
  problem_text: string; // max 5000
  language: Language;
  examples: Example[]; // max 10
}

export interface TaskError {
  code: string;
  message: string;
}

export interface TaskRecord {
  id: string; // UUID
  status: TaskStatus;
  problem_text: string;
  language: Language;
  examples: Example[];
  result: Record<string, unknown> | null;
  error: TaskError | null;
  clarification_question: string | null;
  active_execution_seconds: number;
  created_at: string; // ISO8601
  updated_at: string; // ISO8601
}

export interface TaskCreateResponse {
  task_id: string; // UUID
  status: TaskStatus;
}

export interface ClarificationQuestion {
  question: string;
}

export interface ClarificationAnswer {
  answer: string; // max 5000
}

export interface ClientConfig {
  api_base_url: string;
  ws_base_url?: string;
  max_problem_chars: number;
  max_examples: number;
  max_answer_chars: number;
}

export interface EditorialApproach {
  approach_id: number;
  role: ApproachRole;
  technique: string;
  title: string;
  bridge_from_previous: string | null;
  intuition: string;
  algorithm: string;
  code_python: string;
  code_go: string;
  complexity_time: string;
  complexity_space: string;
  complexity_justification: string;
  notes: string[];
}

export interface UnverifiedApproach {
  approach_id: number;
  name: string;
  status: UnverifiedStatus;
  note: string;
}

export interface Editorial {
  problem_restatement: string;
  difficulty: Difficulty;
  tags: string[];
  approaches: EditorialApproach[];
  edge_cases: string[];
  unverified_approaches: UnverifiedApproach[];
}

export interface ApproachIndexEntry {
  approach_id: number;
  name: string;
  technique: string;
  role: ApproachRole;
  status: ApproachStatus;
  iterations: number;
}

export interface CompletedResult {
  approaches: ApproachIndexEntry[];
  editorial?: Editorial;
  editorial_warnings: string[];
  artifact_keys: string[];
  artifacts_incomplete: boolean;
}

export interface StatusEvent {
  type: "status";
  status: TaskStatus;
  timestamp: string; // ISO8601
}

export interface SnapshotEvent {
  type: "snapshot";
  task: TaskRecord;
}

export type ServerMessage = StatusEvent | SnapshotEvent;

// Type guard for TaskRecord
export function isTaskRecord(value: unknown): value is TaskRecord {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.id === "string" &&
    typeof obj.status === "string" &&
    typeof obj.problem_text === "string" &&
    typeof obj.language === "string" &&
    Array.isArray(obj.examples) &&
    (obj.result === null || typeof obj.result === "object") &&
    (obj.error === null || (typeof obj.error === "object" && obj.error !== null)) &&
    (obj.clarification_question === null || typeof obj.clarification_question === "string") &&
    typeof obj.active_execution_seconds === "number" &&
    typeof obj.created_at === "string" &&
    typeof obj.updated_at === "string"
  );
}
