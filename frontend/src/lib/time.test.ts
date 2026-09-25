/**
 * Tests for time formatting utilities.
 */

import { describe, it, expect } from "vitest";
import { formatElapsed } from "./time";

describe("formatElapsed", () => {
  it("formats zero as 00:00", () => {
    expect(formatElapsed(0)).toBe("00:00");
  });

  it("formats 65 seconds as 01:05", () => {
    expect(formatElapsed(65_000)).toBe("01:05");
  });

  it("formats 3725 seconds (1h 2m 5s) as 1:02:05", () => {
    expect(formatElapsed(3_725_000)).toBe("1:02:05");
  });

  it("formats 3660 seconds (1h 1m) as 1:01:00", () => {
    expect(formatElapsed(3_660_000)).toBe("1:01:00");
  });

  it("treats negative input as 0", () => {
    expect(formatElapsed(-1000)).toBe("00:00");
  });

  it("formats 59 seconds as 00:59", () => {
    expect(formatElapsed(59_000)).toBe("00:59");
  });

  it("formats 60 seconds as 01:00", () => {
    expect(formatElapsed(60_000)).toBe("01:00");
  });

  it("formats 3661 seconds (1h 1m 1s) as 1:01:01", () => {
    expect(formatElapsed(3_661_000)).toBe("1:01:01");
  });
});
