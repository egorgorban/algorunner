/**
 * Tests for editorial narrowing, validation, and label functions.
 */

import { describe, it, expect } from "vitest";
import {
  isEditorial,
  readCompletedResult,
  approachCodeBlocks,
  getRoleLabel,
  getDifficultyLabel,
  getUnverifiedStatusLabel,
} from "./editorial";
import type { Editorial } from "../api/types";

describe("isEditorial", () => {
  it("accepts a valid Editorial object", () => {
    const valid: Editorial = {
      problem_restatement: "Find the maximum element",
      difficulty: "easy",
      tags: ["array", "search"],
      approaches: [
        {
          approach_id: 1,
          role: "brute_force",
          technique: "Linear scan",
          title: "Brute Force",
          bridge_from_previous: null,
          intuition: "Compare all elements",
          algorithm: "Iterate through array",
          code_python: "max(arr)",
          code_go: "slices.Max(arr)",
          complexity_time: "O(n)",
          complexity_space: "O(1)",
          complexity_justification: "One pass",
          notes: ["Simple", "No extra space"],
        },
      ],
      edge_cases: ["Empty array", "Single element"],
      unverified_approaches: [],
    };

    expect(isEditorial(valid)).toBe(true);
  });

  it("rejects null", () => {
    expect(isEditorial(null)).toBe(false);
  });

  it("rejects non-object", () => {
    expect(isEditorial("not an object")).toBe(false);
    expect(isEditorial(123)).toBe(false);
  });

  it("rejects invalid difficulty", () => {
    const invalid = {
      problem_restatement: "test",
      difficulty: "impossible",
      tags: [],
      approaches: [],
      edge_cases: [],
      unverified_approaches: [],
    };
    expect(isEditorial(invalid)).toBe(false);
  });

  it("rejects invalid role in approach", () => {
    const invalid = {
      problem_restatement: "test",
      difficulty: "easy",
      tags: [],
      approaches: [
        {
          approach_id: 1,
          role: "unknown_role",
          technique: "test",
          title: "test",
          bridge_from_previous: null,
          intuition: "test",
          algorithm: "test",
          code_python: "test",
          code_go: "test",
          complexity_time: "O(n)",
          complexity_space: "O(1)",
          complexity_justification: "test",
          notes: [],
        },
      ],
      edge_cases: [],
      unverified_approaches: [],
    };
    expect(isEditorial(invalid)).toBe(false);
  });

  it("rejects invalid unverified status", () => {
    const invalid = {
      problem_restatement: "test",
      difficulty: "easy",
      tags: [],
      approaches: [],
      edge_cases: [],
      unverified_approaches: [
        {
          approach_id: 1,
          name: "test",
          status: "unknown_status",
          note: "test",
        },
      ],
    };
    expect(isEditorial(invalid)).toBe(false);
  });

  it("accepts null bridge_from_previous", () => {
    const valid: Editorial = {
      problem_restatement: "test",
      difficulty: "easy",
      tags: [],
      approaches: [
        {
          approach_id: 1,
          role: "brute_force",
          technique: "test",
          title: "test",
          bridge_from_previous: null,
          intuition: "test",
          algorithm: "test",
          code_python: "test",
          code_go: "test",
          complexity_time: "O(n)",
          complexity_space: "O(1)",
          complexity_justification: "test",
          notes: [],
        },
      ],
      edge_cases: [],
      unverified_approaches: [],
    };
    expect(isEditorial(valid)).toBe(true);
  });

  it("rejects missing code_go", () => {
    const invalid = {
      problem_restatement: "test",
      difficulty: "easy",
      tags: [],
      approaches: [
        {
          approach_id: 1,
          role: "brute_force",
          technique: "test",
          title: "test",
          bridge_from_previous: null,
          intuition: "test",
          algorithm: "test",
          code_python: "test",
          // code_go is missing
          complexity_time: "O(n)",
          complexity_space: "O(1)",
          complexity_justification: "test",
          notes: [],
        },
      ],
      edge_cases: [],
      unverified_approaches: [],
    };
    expect(isEditorial(invalid)).toBe(false);
  });
});

describe("readCompletedResult", () => {
  it("reads a valid completed result with editorial", () => {
    const result = {
      approaches: [{ approach_id: 1, name: "BF", technique: "scan", role: "brute_force", status: "verified", iterations: 1 }],
      editorial: {
        problem_restatement: "Find max",
        difficulty: "easy",
        tags: [],
        approaches: [
          {
            approach_id: 1,
            role: "brute_force",
            technique: "test",
            title: "test",
            bridge_from_previous: null,
            intuition: "test",
            algorithm: "test",
            code_python: "test",
            code_go: "test",
            complexity_time: "O(n)",
            complexity_space: "O(1)",
            complexity_justification: "test",
            notes: [],
          },
        ],
        edge_cases: [],
        unverified_approaches: [],
      },
      editorial_warnings: [],
      artifact_keys: [],
      artifacts_incomplete: false,
    };

    const { editorial, approaches, warnings } = readCompletedResult(result);
    expect(editorial).not.toBeNull();
    expect(editorial?.problem_restatement).toBe("Find max");
    expect(approaches).toHaveLength(1);
    expect(warnings).toHaveLength(0);
  });

  it("returns null editorial when result has no editorial", () => {
    const result = {
      approaches: [{ approach_id: 1, name: "BF", technique: "scan", role: "brute_force", status: "verified", iterations: 1 }],
      editorial_warnings: [],
      artifact_keys: [],
      artifacts_incomplete: false,
    };

    const { editorial, approaches } = readCompletedResult(result);
    expect(editorial).toBeNull();
    expect(approaches).toHaveLength(1);
  });

  it("returns null on null result", () => {
    const { editorial, approaches, warnings } = readCompletedResult(null);
    expect(editorial).toBeNull();
    expect(approaches).toHaveLength(0);
    expect(warnings).toHaveLength(0);
  });

  it("returns null on non-object result", () => {
    const { editorial } = readCompletedResult("not an object");
    expect(editorial).toBeNull();
  });

  it("returns null editorial when editorial is malformed", () => {
    const result = {
      approaches: [],
      editorial: { problem_restatement: "test" }, // incomplete
      editorial_warnings: [],
      artifact_keys: [],
      artifacts_incomplete: false,
    };

    const { editorial } = readCompletedResult(result);
    expect(editorial).toBeNull();
  });

  it("parses editorial_warnings even when editorial is missing", () => {
    const result = {
      approaches: [],
      editorial_warnings: ["Warning 1", "Warning 2"],
      artifact_keys: [],
      artifacts_incomplete: false,
    };

    const { warnings } = readCompletedResult(result);
    expect(warnings).toEqual(["Warning 1", "Warning 2"]);
  });
});

describe("approachCodeBlocks", () => {
  it("extracts python and go code in order", () => {
    const editorial: Editorial = {
      problem_restatement: "test",
      difficulty: "easy",
      tags: [],
      approaches: [
        {
          approach_id: 1,
          role: "brute_force",
          technique: "test",
          title: "test",
          bridge_from_previous: null,
          intuition: "test",
          algorithm: "test",
          code_python: "def brute(arr): pass",
          code_go: "func brute(arr) {}",
          complexity_time: "O(n)",
          complexity_space: "O(1)",
          complexity_justification: "test",
          notes: [],
        },
        {
          approach_id: 2,
          role: "optimized",
          technique: "test",
          title: "test",
          bridge_from_previous: "from brute",
          intuition: "test",
          algorithm: "test",
          code_python: "def opt(arr): return max(arr)",
          code_go: "func opt(arr) int { return slices.Max(arr) }",
          complexity_time: "O(n)",
          complexity_space: "O(1)",
          complexity_justification: "test",
          notes: [],
        },
      ],
      edge_cases: [],
      unverified_approaches: [],
    };

    const blocks = approachCodeBlocks(editorial);
    expect(blocks).toHaveLength(4);
    expect(blocks[0]).toEqual({
      approachId: 1,
      language: "python",
      code: "def brute(arr): pass",
    });
    expect(blocks[1]).toEqual({
      approachId: 1,
      language: "go",
      code: "func brute(arr) {}",
    });
    expect(blocks[2]).toEqual({
      approachId: 2,
      language: "python",
      code: "def opt(arr): return max(arr)",
    });
    expect(blocks[3]).toEqual({
      approachId: 2,
      language: "go",
      code: "func opt(arr) int { return slices.Max(arr) }",
    });
  });

  it("returns empty array for editorial with no approaches", () => {
    const editorial: Editorial = {
      problem_restatement: "test",
      difficulty: "easy",
      tags: [],
      approaches: [],
      edge_cases: [],
      unverified_approaches: [],
    };

    const blocks = approachCodeBlocks(editorial);
    expect(blocks).toHaveLength(0);
  });
});

describe("label functions", () => {
  it("returns correct role labels", () => {
    expect(getRoleLabel("brute_force")).toBe("Полный перебор");
    expect(getRoleLabel("optimized")).toBe("Оптимальное решение");
    expect(getRoleLabel("alternative")).toBe("Альтернативный подход");
  });

  it("returns correct difficulty labels", () => {
    expect(getDifficultyLabel("easy")).toBe("Лёгкая");
    expect(getDifficultyLabel("medium")).toBe("Средняя");
    expect(getDifficultyLabel("hard")).toBe("Сложная");
  });

  it("returns correct unverified status labels", () => {
    expect(getUnverifiedStatusLabel("exhausted")).toBe("Не прошёл проверку");
    expect(getUnverifiedStatusLabel("timed_out")).toBe("Не уложился во время");
    expect(getUnverifiedStatusLabel("errored")).toBe("Ошибка при решении");
  });
});
