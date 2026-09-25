/**
 * Tests for validation logic covering all behavior bullets.
 */

import { describe, it, expect } from "vitest";
import { codePointLength, validateSubmission } from "./validation";

describe("codePointLength", () => {
  it("counts empty string as 0", () => {
    expect(codePointLength("")).toBe(0);
  });

  it("counts Cyrillic characters", () => {
    expect(codePointLength("абв")).toBe(3);
  });

  it("counts emoji as single code point", () => {
    // 😀 is a single code point, even though it's UTF-16 length 2
    expect(codePointLength("😀")).toBe(1);
  });

  it("counts mixed text correctly", () => {
    // "a" + "б" + "😀" = 3 code points
    expect(codePointLength("aб😀")).toBe(3);
  });
});

describe("validateSubmission", () => {
  const limits = {
    max_problem_chars: 5000,
    max_examples: 10,
  };

  describe("problem text validation", () => {
    it("rejects blank problem text", () => {
      const result = validateSubmission(
        {
          problemText: "",
          language: "ru",
          examples: [],
        },
        limits
      );
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.problemTextError).toBe("Введите условие задачи");
      }
    });

    it("rejects whitespace-only problem text", () => {
      const result = validateSubmission(
        {
          problemText: "   \n\t  ",
          language: "ru",
          examples: [],
        },
        limits
      );
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.problemTextError).toBe("Введите условие задачи");
      }
    });

    it("accepts text at exactly max_problem_chars code points", () => {
      const text = "a".repeat(5000);
      const result = validateSubmission(
        {
          problemText: text,
          language: "ru",
          examples: [],
        },
        limits
      );
      expect(result.ok).toBe(true);
    });

    it("rejects text exceeding max_problem_chars code points", () => {
      const text = "a".repeat(5001);
      const result = validateSubmission(
        {
          problemText: text,
          language: "ru",
          examples: [],
        },
        limits
      );
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.problemTextError).toContain("5001");
        expect(result.problemTextError).toContain("5000");
      }
    });

    it("accepts text with emoji when total code points within limit", () => {
      // Create 5000 code points using some emoji (1 CP each, but 2 UTF-16 units)
      const text = "a".repeat(4999) + "😀"; // 4999 + 1 = 5000 code points
      expect(codePointLength(text)).toBe(5000);
      const result = validateSubmission(
        {
          problemText: text,
          language: "ru",
          examples: [],
        },
        limits
      );
      expect(result.ok).toBe(true);
    });
  });

  describe("example validation", () => {
    it("accepts zero example rows", () => {
      const result = validateSubmission(
        {
          problemText: "test",
          language: "ru",
          examples: [],
        },
        limits
      );
      expect(result.ok).toBe(true);
    });

    it("drops rows with all three fields blank", () => {
      const result = validateSubmission(
        {
          problemText: "test",
          language: "ru",
          examples: [
            { input: "", output: "", explanation: "" },
            { input: "a", output: "b", explanation: "" },
            { input: "  ", output: "  ", explanation: "  " },
          ],
        },
        limits
      );
      expect(result.ok).toBe(true);
      if (result.ok) {
        expect(result.submission.examples).toHaveLength(1);
        expect(result.submission.examples[0]?.input || "").toBe("a");
      }
    });

    it("rejects row with input but no output", () => {
      const result = validateSubmission(
        {
          problemText: "test",
          language: "ru",
          examples: [{ input: "a", output: "", explanation: "" }],
        },
        limits
      );
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.rowErrors[0] || "").toBe("Заполните и вход, и выход");
      }
    });

    it("rejects row with output but no input", () => {
      const result = validateSubmission(
        {
          problemText: "test",
          language: "ru",
          examples: [{ input: "", output: "b", explanation: "" }],
        },
        limits
      );
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.rowErrors[0] || "").toBe("Заполните и вход, и выход");
      }
    });

    it("accepts row with input and output but blank explanation", () => {
      const result = validateSubmission(
        {
          problemText: "test",
          language: "ru",
          examples: [{ input: "a", output: "b", explanation: "" }],
        },
        limits
      );
      expect(result.ok).toBe(true);
      if (result.ok) {
        expect(result.submission.examples[0]?.explanation || null).toBe(null);
      }
    });

    it("preserves non-blank explanation exactly as typed", () => {
      const result = validateSubmission(
        {
          problemText: "test",
          language: "ru",
          examples: [{ input: "a", output: "b", explanation: "  explanation  " }],
        },
        limits
      );
      expect(result.ok).toBe(true);
      if (result.ok) {
        expect(result.submission.examples[0]?.explanation).toBe("  explanation  ");
      }
    });

    it("preserves input and output exactly as typed", () => {
      const result = validateSubmission(
        {
          problemText: "test",
          language: "ru",
          examples: [{ input: "  a  ", output: "  b  ", explanation: "x" }],
        },
        limits
      );
      expect(result.ok).toBe(true);
      if (result.ok) {
        expect(result.submission.examples[0]?.input).toBe("  a  ");
        expect(result.submission.examples[0]?.output).toBe("  b  ");
      }
    });

    it("rejects more rows than max_examples", () => {
      const examples = Array.from({ length: 11 }, (_, i) => ({
        input: `in${i}`,
        output: `out${i}`,
        explanation: "",
      }));
      const result = validateSubmission(
        {
          problemText: "test",
          language: "ru",
          examples,
        },
        limits
      );
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.examplesError).toBe("Не больше 10 примеров");
      }
    });
  });

  describe("combined validation", () => {
    it("fails on multiple errors", () => {
      const result = validateSubmission(
        {
          problemText: "",
          language: "ru",
          examples: [{ input: "a", output: "", explanation: "" }],
        },
        limits
      );
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.problemTextError).toBeDefined();
        expect(result.rowErrors[0]).toBeDefined();
      }
    });
  });
});
