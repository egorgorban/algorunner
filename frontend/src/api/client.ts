/**
 * Fetch-based API client with type guards and error handling (D-12).
 */

import type {
  ClientConfig,
  TaskCreateResponse,
  TaskRecord,
  TaskSubmission,
} from "./types";
import { isTaskRecord } from "./types";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function isClientConfig(value: unknown): value is ClientConfig {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.api_base_url === "string" &&
    (obj.ws_base_url === undefined || typeof obj.ws_base_url === "string") &&
    typeof obj.max_problem_chars === "number" &&
    typeof obj.max_examples === "number" &&
    typeof obj.max_answer_chars === "number"
  );
}

function isTaskCreateResponse(value: unknown): value is TaskCreateResponse {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return typeof obj.task_id === "string" && typeof obj.status === "string";
}

export async function fetchConfig(origin: string): Promise<ClientConfig> {
  const url = origin ? `${origin}/api/config` : "/api/config";
  const response = await fetch(url);
  const data: unknown = await response.json();

  if (!response.ok) {
    throw new ApiError(`Failed to fetch config: ${response.statusText}`, response.status, data);
  }

  if (!isClientConfig(data)) {
    throw new ApiError("Invalid config response", 200, data);
  }

  return data;
}

export function resolveApiBase(config: ClientConfig, origin: string): string {
  if (config.api_base_url.startsWith("http://") || config.api_base_url.startsWith("https://")) {
    return config.api_base_url;
  }
  return origin + config.api_base_url;
}

export async function createTask(
  apiBase: string,
  submission: TaskSubmission
): Promise<TaskCreateResponse> {
  const response = await fetch(`${apiBase}/api/v1/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(submission),
  });

  const data: unknown = await response.json();

  if (!response.ok) {
    const detail = (data as Record<string, unknown>)?.detail ?? data;
    throw new ApiError(
      `Failed to create task: ${response.statusText}`,
      response.status,
      detail
    );
  }

  if (!isTaskCreateResponse(data)) {
    throw new ApiError("Invalid create response", 200, data);
  }

  return data;
}

export async function getTask(apiBase: string, taskId: string): Promise<TaskRecord> {
  const response = await fetch(`${apiBase}/api/v1/tasks/${encodeURIComponent(taskId)}`);
  const data: unknown = await response.json();

  if (response.status === 404) {
    throw new ApiError("Task not found", 404, data);
  }

  if (!response.ok) {
    throw new ApiError(`Failed to fetch task: ${response.statusText}`, response.status, data);
  }

  if (!isTaskRecord(data)) {
    throw new ApiError("Invalid task response", 200, data);
  }

  return data;
}
