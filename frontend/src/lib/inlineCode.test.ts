/**
 * Tests for inline code splitting.
 */

import { describe, it, expect } from "vitest";
import { splitInlineCode } from "./inlineCode";

describe("splitInlineCode", () => {
  it("handles text with a single code span", () => {
    const result = splitInlineCode("Use `dp[i]` here");
    expect(result).toEqual([
      { kind: "text", value: "Use " },
      { kind: "code", value: "dp[i]" },
      { kind: "text", value: " here" },
    ]);
  });

  it("handles text without backticks", () => {
    const result = splitInlineCode("No code here");
    expect(result).toEqual([{ kind: "text", value: "No code here" }]);
  });

  it("keeps unmatched trailing backtick as literal text", () => {
    const result = splitInlineCode("Trailing `");
    expect(result).toEqual([{ kind: "text", value: "Trailing `" }]);
  });

  it("keeps empty backticks as literal text", () => {
    const result = splitInlineCode("`` empty");
    expect(result).toEqual([{ kind: "text", value: "`` empty" }]);
  });

  it("handles multiple code spans", () => {
    const result = splitInlineCode("Use `x` and `y`");
    expect(result).toEqual([
      { kind: "text", value: "Use " },
      { kind: "code", value: "x" },
      { kind: "text", value: " and " },
      { kind: "code", value: "y" },
    ]);
  });

  it("treats HTML tags as plain text", () => {
    const result = splitInlineCode("<b>x</b>");
    expect(result).toEqual([{ kind: "text", value: "<b>x</b>" }]);
  });

  it("handles code at the start", () => {
    const result = splitInlineCode("`code` at start");
    expect(result).toEqual([
      { kind: "code", value: "code" },
      { kind: "text", value: " at start" },
    ]);
  });

  it("handles code at the end", () => {
    const result = splitInlineCode("at the end `code`");
    expect(result).toEqual([
      { kind: "text", value: "at the end " },
      { kind: "code", value: "code" },
    ]);
  });

  it("handles consecutive code spans", () => {
    const result = splitInlineCode("`a``b`");
    // Empty backticks between code spans are treated as literal text
    expect(result).toEqual([
      { kind: "code", value: "a" },
      { kind: "code", value: "b" },
    ]);
  });

  it("handles only code", () => {
    const result = splitInlineCode("`code`");
    expect(result).toEqual([{ kind: "code", value: "code" }]);
  });

  it("handles newlines and special characters in code", () => {
    const result = splitInlineCode("Use `arr\\[0\\]` here");
    expect(result).toEqual([
      { kind: "text", value: "Use " },
      { kind: "code", value: "arr\\[0\\]" },
      { kind: "text", value: " here" },
    ]);
  });

  it("handles backticks within code (impossible by grammar, but edge case)", () => {
    // With our algorithm, a backtick inside code ends the span
    // so `a`b`c` becomes: code "a", text "b", code "c"
    const result = splitInlineCode("`a`b`c`");
    expect(result).toEqual([
      { kind: "code", value: "a" },
      { kind: "text", value: "b" },
      { kind: "code", value: "c" },
    ]);
  });

  it("handles empty string", () => {
    const result = splitInlineCode("");
    expect(result).toEqual([{ kind: "text", value: "" }]);
  });

  it("handles only backticks", () => {
    const result = splitInlineCode("`");
    expect(result).toEqual([{ kind: "text", value: "`" }]);
  });

  it("handles Russian characters", () => {
    const result = splitInlineCode("Используйте `переменную` здесь");
    expect(result).toEqual([
      { kind: "text", value: "Используйте " },
      { kind: "code", value: "переменную" },
      { kind: "text", value: " здесь" },
    ]);
  });

  it("handles complex scenario from PR description", () => {
    const result = splitInlineCode(
      "The Writer prompt wraps identifiers in backticks (agents/editorial_writer/prompts.py). Code fields are `byte-identical` to the executed Solutions."
    );
    expect(result).toEqual([
      { kind: "text", value: "The Writer prompt wraps identifiers in backticks (agents/editorial_writer/prompts.py). Code fields are " },
      { kind: "code", value: "byte-identical" },
      { kind: "text", value: " to the executed Solutions." },
    ]);
  });
});
