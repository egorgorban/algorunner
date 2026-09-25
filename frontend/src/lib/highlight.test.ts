/**
 * Tests for syntax highlighting with highlight.js.
 */

import { describe, it, expect } from "vitest";
import { highlight } from "./highlight";

/**
 * Helper: strip HTML tags and decode entities to get plain text.
 * Used to verify round-trip: highlight output -> stripped text = original text.
 */
function stripAndDecode(html: string): string {
  // Strip HTML tags
  let text = html.replace(/<[^>]*>/g, "");
  // Decode HTML entities
  text = text.replace(/&lt;/g, "<");
  text = text.replace(/&gt;/g, ">");
  text = text.replace(/&amp;/g, "&");
  text = text.replace(/&quot;/g, '"');
  text = text.replace(/&#x27;/g, "'");
  text = text.replace(/&#39;/g, "'");
  return text;
}

describe("highlight", () => {
  it("highlights Python code", () => {
    const code = "def hello():\n    return 42";
    const result = highlight(code, "python");
    expect(result).toContain("def");
    expect(result).toContain("hello");
    // Strip and verify round-trip
    expect(stripAndDecode(result)).toBe(code);
  });

  it("highlights Go code", () => {
    const code = "func main() {\n    fmt.Println(42)\n}";
    const result = highlight(code, "go");
    expect(result).toContain("func");
    expect(result).toContain("main");
    // Strip and verify round-trip
    expect(stripAndDecode(result)).toBe(code);
  });

  it("escapes script tags in code (prevents XSS)", () => {
    const code = '<script>alert(1)</script>';
    const result = highlight(code, "python");
    // The HTML entities should be present, not the actual tags
    expect(result).toContain("&lt;script&gt;");
    expect(result).not.toContain("<script>");
    // Round-trip should recover original
    expect(stripAndDecode(result)).toBe(code);
  });

  it("preserves tabs in code", () => {
    const code = "def f():\n\tif True:\n\t\tpass";
    const result = highlight(code, "python");
    expect(stripAndDecode(result)).toBe(code);
  });

  it("preserves blank lines", () => {
    const code = "a := 1\n\nb := 2";
    const result = highlight(code, "go");
    expect(stripAndDecode(result)).toBe(code);
  });

  it("preserves trailing spaces", () => {
    const code = "print('hello')  \nprint('world')";
    const result = highlight(code, "python");
    expect(stripAndDecode(result)).toBe(code);
  });

  it("handles Cyrillic comments", () => {
    const code = "# Комментарий на русском\nx = 42";
    const result = highlight(code, "python");
    expect(stripAndDecode(result)).toBe(code);
  });

  it("handles Cyrillic string literals", () => {
    const code = 'msg := "Привет, мир!"\nfmt.Println(msg)';
    const result = highlight(code, "go");
    expect(stripAndDecode(result)).toBe(code);
  });

  it("escapes quotes and ampersands in code", () => {
    const code = 'x = "a&b" + \'c"d\'';
    const result = highlight(code, "python");
    // Should have entities, not raw characters (for & at least)
    expect(result).toContain("&amp;");
    // Round-trip should recover
    expect(stripAndDecode(result)).toBe(code);
  });

  it("handles real Python example", () => {
    const code = `def merge_sort(arr):
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    return merge(left, right)`;
    const result = highlight(code, "python");
    expect(stripAndDecode(result)).toBe(code);
  });

  it("handles real Go example", () => {
    const code = `func QuickSort(arr []int, low, high int) {
    if low < high {
        pi := Partition(arr, low, high)
        QuickSort(arr, low, pi-1)
        QuickSort(arr, pi+1, high)
    }
}`;
    const result = highlight(code, "go");
    expect(stripAndDecode(result)).toBe(code);
  });

  it("handles empty code", () => {
    const result = highlight("", "python");
    expect(result).toBeDefined();
    expect(stripAndDecode(result)).toBe("");
  });

  it("handles code with only whitespace", () => {
    const code = "   \n\t\n  ";
    const result = highlight(code, "python");
    expect(stripAndDecode(result)).toBe(code);
  });

  it("includes span/div wrapper elements", () => {
    const code = "x = 1";
    const result = highlight(code, "python");
    // highlight.js wraps tokens in span elements
    expect(result).toMatch(/<span[^>]*>/);
  });

  it("produces valid HTML", () => {
    const code = "print('hello')";
    const result = highlight(code, "python");
    // Basic HTML structure check: should have no unescaped < or >
    expect(result).not.toMatch(/<[^>]*[^>]?$/); // No unclosed tags
    // All < and > in code should be escaped
    const hasRawBrackets = /<(?!span|\/span)[^>]*>/.test(result);
    expect(hasRawBrackets).toBe(false);
  });

  it("round-trip works for complex code", () => {
    const code = ('def func(x, y):\n' +
      '    """Docstring with backticks and \'quotes\'"""\n' +
      '    # Comment with special chars: < > & " \'\n' +
      '    z = x + y\n' +
      '    return z');
    const result = highlight(code, "python");
    expect(stripAndDecode(result)).toBe(code);
  });
});
