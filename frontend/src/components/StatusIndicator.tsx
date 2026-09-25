/**
 * Status indicator badge with elapsed time clock (Task 2).
 * Shows current status with color coding: blue (running), amber (awaiting), green (completed), red (failed).
 * Displays elapsed time that ticks every second during execution, freezes when complete.
 */

import React, { useState, useEffect } from "react";
import { STATUS_LABELS } from "../lib/statusLabels";
import { formatElapsed } from "../lib/time";
import type { TaskStatus } from "../api/types";
import { TERMINAL_STATUSES } from "../api/types";

interface StatusIndicatorProps {
  status: TaskStatus;
  createdAt: string;
  updatedAt: string;
}

export function StatusIndicator({ status, createdAt, updatedAt }: StatusIndicatorProps): React.ReactElement {
  const [elapsedMs, setElapsedMs] = useState(0);

  const isTerminal = TERMINAL_STATUSES.has(status);
  const createdDate = new Date(createdAt);
  const updatedDate = new Date(updatedAt);

  useEffect(() => {
    if (isTerminal) {
      // For terminal statuses, calculate final elapsed time
      const elapsed = updatedDate.getTime() - createdDate.getTime();
      setElapsedMs(Math.max(0, elapsed));
      return;
    }

    // For non-terminal statuses, update elapsed time every second
    const interval = setInterval(() => {
      const now = new Date();
      const elapsed = now.getTime() - createdDate.getTime();
      setElapsedMs(Math.max(0, elapsed));
    }, 1000);

    return () => clearInterval(interval);
  }, [status, createdAt, updatedAt, isTerminal, createdDate, updatedDate]);

  // Color coding based on status category
  let badgeColor = "bg-blue-100 text-blue-800"; // default running
  if (status === "awaiting_clarification") {
    badgeColor = "bg-amber-100 text-amber-800";
  } else if (status === "completed") {
    badgeColor = "bg-green-100 text-green-800";
  } else if (status === "failed") {
    badgeColor = "bg-red-100 text-red-800";
  } else if (["analyzing_problem", "designing_solution", "generating_code", "generating_tests", "executing_tests", "reviewing", "correcting", "writing_editorial"].includes(status)) {
    badgeColor = "bg-blue-100 text-blue-800"; // running statuses
  }

  return (
    <div className="flex items-center gap-4">
      <div className={`px-4 py-2 rounded-lg font-semibold ${badgeColor}`}>
        {STATUS_LABELS[status]}
      </div>
      <div className="text-lg">
        <span className="text-gray-600">Прошло: </span>
        <span className="font-mono font-semibold">{formatElapsed(elapsedMs)}</span>
      </div>
    </div>
  );
}
