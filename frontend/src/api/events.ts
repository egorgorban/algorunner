/**
 * WebSocket client with reconnection, type guards, and backoff logic (D-02, D-05, UI-02).
 * Framework-free, injectable for testability.
 */

import type {
  ClientConfig,
  ServerMessage,
  SnapshotEvent,
  StatusEvent,
  TaskStatus,
} from "./types";
import { TASK_STATUSES, isTaskRecord } from "./types";

export function buildEventsUrl(
  config: ClientConfig,
  location: { protocol: string; host: string },
  taskId: string
): string {
  let wsUrl: string;

  if (config.ws_base_url) {
    wsUrl = config.ws_base_url;
  } else if (
    config.api_base_url.startsWith("http://") ||
    config.api_base_url.startsWith("https://")
  ) {
    const protocol = config.api_base_url.startsWith("https://") ? "wss:" : "ws:";
    const url = new URL(config.api_base_url);
    wsUrl = `${protocol}//${url.host}${url.pathname}`;
  } else {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    wsUrl = `${protocol}//${location.host}${config.api_base_url}`;
  }

  // Remove trailing slash if present
  if (wsUrl.endsWith("/")) {
    wsUrl = wsUrl.slice(0, -1);
  }

  return `${wsUrl}/tasks/${encodeURIComponent(taskId)}/events`;
}

export function isTaskStatus(value: unknown): value is TaskStatus {
  return typeof value === "string" && TASK_STATUSES.includes(value as TaskStatus);
}

export function parseServerMessage(raw: unknown): ServerMessage | null {
  if (typeof raw !== "string") return null;

  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }

  if (typeof data !== "object" || data === null) return null;

  const obj = data as Record<string, unknown>;
  const type = obj.type;

  if (type === "snapshot") {
    const task = obj.task;
    if (isTaskRecord(task)) {
      return { type: "snapshot", task } as SnapshotEvent;
    }
    return null;
  }

  if (type === "status") {
    const status = obj.status;
    const timestamp = obj.timestamp;
    if (isTaskStatus(status) && typeof timestamp === "string") {
      return { type: "status", status, timestamp } as StatusEvent;
    }
    return null;
  }

  return null;
}

export const NO_RECONNECT_CODES = new Set([1000, 4403, 4404]);

export function backoffDelay(attempt: number): number {
  const exponential = Math.min(1000 * Math.pow(2, attempt), 10000);
  return exponential;
}

export interface EventHandlers {
  onMessage(message: ServerMessage): void;
  onConnectionChange(state: "connecting" | "open" | "reconnecting" | "closed"): void;
}

export interface ConnectOptions {
  createSocket?: (url: string) => WebSocket;
  setTimer?: (callback: () => void, ms: number) => ReturnType<typeof setTimeout>;
  clearTimer?: (id: ReturnType<typeof setTimeout>) => void;
}

export function connectTaskEvents(
  url: string,
  handlers: EventHandlers,
  options: ConnectOptions = {}
): () => void {
  const createSocket = options.createSocket ?? ((url: string) => new WebSocket(url));
  const setTimer = options.setTimer ?? ((cb: () => void, ms: number) => setTimeout(cb, ms));
  const clearTimer = options.clearTimer ?? ((id) => clearTimeout(id));

  let socket: WebSocket | null = null;
  let stopped = false;
  let reconnectAttempt = 0;
  let pendingReconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function handleOpen(): void {
    reconnectAttempt = 0;
    handlers.onConnectionChange("open");
  }

  function handleClose(event: CloseEvent): void {
    if (stopped) {
      handlers.onConnectionChange("closed");
      return;
    }

    if (NO_RECONNECT_CODES.has(event.code)) {
      stopped = true;
      handlers.onConnectionChange("closed");
      return;
    }

    handlers.onConnectionChange("reconnecting");
    const delay = backoffDelay(reconnectAttempt);
    reconnectAttempt++;

    pendingReconnectTimer = setTimer(() => {
      if (!stopped) {
        connect();
      }
    }, delay);
  }

  function handleMessage(event: MessageEvent): void {
    const message = parseServerMessage(event.data);
    if (message) {
      handlers.onMessage(message);
    }
  }

  function connect(): void {
    if (stopped) return;

    handlers.onConnectionChange("connecting");
    socket = createSocket(url);
    socket.addEventListener("open", handleOpen);
    socket.addEventListener("close", handleClose);
    socket.addEventListener("message", handleMessage);
  }

  function stop(): void {
    stopped = true;

    if (pendingReconnectTimer !== null) {
      clearTimer(pendingReconnectTimer);
      pendingReconnectTimer = null;
    }

    if (socket) {
      socket.close(1000);
      socket = null;
    }

    handlers.onConnectionChange("closed");
  }

  connect();

  return stop;
}
