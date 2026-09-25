/**
 * Live integration test: full data path against the real API (UI-02, D-20).
 * Tests: fetchConfig -> createTask -> WebSocket -> reducer -> status.
 * Run with: npm run test:live
 */

import { describe, it, expect, beforeAll } from "vitest";
import { fetchConfig } from "./client";
import { createTask } from "./client";
import { buildEventsUrl } from "./events";
import { connectTaskEvents } from "./events";
import { taskReducer, initialTaskState, type TaskViewState } from "../context/taskReducer";
import type { ServerMessage } from "./types";

const ORIGIN = (import.meta.env.VITE_LIVE_API_ORIGIN as string) || "http://localhost:8000";

describe("Live Integration Test", () => {
  beforeAll(async () => {
    // Poll for config availability for up to 60 seconds
    const startTime = Date.now();
    const timeout = 60000;

    while (Date.now() - startTime < timeout) {
      try {
        await fetchConfig(ORIGIN);
        return; // Config is available
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
    }

    throw new Error("API not ready after 60 seconds");
  });

  it("should complete the full data path: config -> create task -> WebSocket -> reducer", async () => {
    // Step 1: Fetch config
    const config = await fetchConfig(ORIGIN);
    expect(config).toBeDefined();
    expect(config.api_base_url).toBeDefined();
    expect(config.max_problem_chars).toBeGreaterThan(0);

    // Step 2: Create a task
    const response = await createTask(ORIGIN + config.api_base_url, {
      problem_text:
        "Given an array of integers nums and an integer target, return indices of the two numbers that add up to target.",
      language: "en",
      examples: [],
    });

    expect(response.task_id).toBeDefined();
    expect(response.status).toBe("queued");
    const taskId = response.task_id;

    // Step 3: Connect WebSocket and collect messages
    const messages: ServerMessage[] = [];
    const stateUpdates: TaskViewState[] = [];

    let state = initialTaskState;
    state = taskReducer(state, { type: "SUBMIT_TASK", taskId });

    const wsUrl = buildEventsUrl(
      config,
      { protocol: ORIGIN.includes("https") ? "https:" : "http:", host: new URL(ORIGIN).host },
      taskId
    );

    const stopPromise = new Promise<void>((resolve, reject) => {
      const stop = connectTaskEvents(wsUrl, {
        onMessage(message: ServerMessage) {
          messages.push(message);

          if (message.type === "snapshot") {
            state = taskReducer(state, { type: "SNAPSHOT", task: message.task });
          } else if (message.type === "status") {
            state = taskReducer(state, { type: "ADD_EVENT", event: { status: message.status, timestamp: message.timestamp } });
          }

          stateUpdates.push({ ...state });

          // Stop after we have enough data
          if (messages.length >= 3 && state.history.length >= 2) {
            stop();
            resolve();
          }
        },
        onConnectionChange() {
          // Log connection changes but don't stop
        },
      });

      // Timeout after 60 seconds
      setTimeout(() => {
        stop();
        reject(new Error("WebSocket test timed out after 60 seconds"));
      }, 60000);
    });

    await stopPromise;

    // Verify the results
    expect(messages.length).toBeGreaterThanOrEqual(1);
    expect(messages[0]?.type).toBe("snapshot");

    if (messages[0]?.type === "snapshot") {
      expect(messages[0].task.id).toBe(taskId);
    }

    expect(state.taskId).toBe(taskId);
    expect(state.status).toBeDefined();
    expect(state.history.length).toBeGreaterThanOrEqual(1);
  });
});
