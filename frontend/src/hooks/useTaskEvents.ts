/**
 * React hook for WebSocket task event streaming with cleanup (D-02, Pitfall 6).
 * StrictMode-safe: effect cleanup prevents duplicate connections.
 */

import { useEffect } from "react";
import { buildEventsUrl, connectTaskEvents } from "../api/events";
import type { ClientConfig, ServerMessage } from "../api/types";
import type { TaskAction } from "../context/taskReducer";
import type React from "react";

export function useTaskEvents(
  taskId: string | null,
  config: ClientConfig | null,
  dispatch: React.Dispatch<TaskAction>
): void {
  useEffect(() => {
    if (!taskId || !config) {
      return;
    }

    const url = buildEventsUrl(config, window.location, taskId);

    const stop = connectTaskEvents(url, {
      onMessage(message: ServerMessage) {
        if (message.type === "snapshot") {
          dispatch({ type: "SNAPSHOT", task: message.task });
        } else if (message.type === "status") {
          dispatch({ type: "ADD_EVENT", event: { status: message.status, timestamp: message.timestamp } });
        }
      },
      onConnectionChange(state) {
        dispatch({ type: "CONNECTION", state });
      },
    });

    return stop;
  }, [taskId, config, dispatch]);
}
