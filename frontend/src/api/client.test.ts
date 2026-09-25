/**
 * Tests for API client functions covering error formatting and clarification endpoints.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { formatApiError, ApiError, answerClarification, getClarificationQuestion } from "./client";

// Type helpers for fetch stubbing
type FetchMock = typeof fetch;
const global = globalThis;

describe("formatApiError", () => {
  it("formats 422 validation error with field names", () => {
    const error = new ApiError("Validation failed", 422, [
      { loc: ["body", "problem_text"], msg: "Field required" },
      { loc: ["body", "examples", 0, "input"], msg: "Value cannot be empty" },
    ]);
    const message = formatApiError(error);
    expect(message).toContain("Поле problem_text");
    expect(message).toContain("Поле examples.0.input");
  });

  it("formats 413 body too large error", () => {
    const error = new ApiError("Payload too large", 413, null);
    const message = formatApiError(error);
    expect(message).toBe("Запрос слишком большой");
  });

  it("formats status 0 network error", () => {
    const error = new ApiError("Network error", 0, null);
    const message = formatApiError(error);
    expect(message).toBe("Нет соединения с сервером");
  });

  it("formats generic server error with code", () => {
    const error = new ApiError("Server error", 500, null);
    const message = formatApiError(error);
    expect(message).toBe("Ошибка сервера (код 500)");
  });

  it("formats non-ApiError gracefully", () => {
    const message = formatApiError(new Error("Some error"));
    expect(message).toBe("Неизвестная ошибка");
  });

  it("formats null with generic message", () => {
    const message = formatApiError(null);
    expect(message).toBe("Неизвестная ошибка");
  });
});

describe("answerClarification", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns accepted on 202", async () => {
    const mockFetch = vi.mocked(global.fetch);
    mockFetch.mockResolvedValueOnce({
      status: 202,
      ok: true,
      json: async () => ({ task_id: "123", status: "analyzing_problem" }),
    } as Response);

    const result = await answerClarification("http://api", "task-123", "answer text");
    expect(result.kind).toBe("accepted");
  });

  it("returns conflict on 409", async () => {
    const mockFetch = vi.mocked(global.fetch);
    mockFetch.mockResolvedValueOnce({
      status: 409,
      ok: false,
      json: async () => ({}),
    } as Response);

    const result = await answerClarification("http://api", "task-123", "answer text");
    expect(result.kind).toBe("conflict");
  });

  it("returns error with message on 404", async () => {
    const mockFetch = vi.mocked(global.fetch);
    mockFetch.mockResolvedValueOnce({
      status: 404,
      ok: false,
      json: async () => ({ detail: "Not found" }),
    } as Response);

    const result = await answerClarification("http://api", "task-123", "answer text");
    expect(result.kind).toBe("error");
  });

  it("returns error with message on 422", async () => {
    const mockFetch = vi.mocked(global.fetch as FetchMock);
    mockFetch.mockResolvedValueOnce({
      status: 422,
      ok: false,
      json: async () => ({
        detail: [{ loc: ["body", "answer"], msg: "Too short" }],
      }),
    } as Response);

    const result = await answerClarification("http://api", "task-123", "a");
    expect(result.kind).toBe("error");
  });
});

describe("getClarificationQuestion", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns question on 200", async () => {
    const mockFetch = vi.mocked(global.fetch);
    mockFetch.mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => ({ question: "What is the input type?" }),
    } as Response);

    const result = await getClarificationQuestion("http://api", "task-123");
    expect(result).toBe("What is the input type?");
  });

  it("returns null on 404", async () => {
    const mockFetch = vi.mocked(global.fetch);
    mockFetch.mockResolvedValueOnce({
      status: 404,
      ok: false,
      json: async () => ({}),
    } as Response);

    const result = await getClarificationQuestion("http://api", "task-123");
    expect(result).toBeNull();
  });

  it("returns null on error", async () => {
    const mockFetch = vi.mocked(global.fetch);
    mockFetch.mockResolvedValueOnce({
      status: 500,
      ok: false,
      json: async () => ({}),
    } as Response);

    const result = await getClarificationQuestion("http://api", "task-123");
    expect(result).toBeNull();
  });
});
