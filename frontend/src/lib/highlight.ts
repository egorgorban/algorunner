/**
 * Syntax highlighting wrapper: highlight.js core with Python and Go (UI-04, D-10).
 * Only python and go languages are registered; others will throw.
 */

import hljs from "highlight.js/lib/core";
import python from "highlight.js/lib/languages/python";
import go from "highlight.js/lib/languages/go";

// Register only python and go languages
hljs.registerLanguage("python", python);
hljs.registerLanguage("go", go);

/**
 * Highlight code with the registered language.
 * Returns HTML with properly escaped source text (< > & " ' are entities, not markup).
 * Only "python" and "go" are supported.
 */
export function highlight(code: string, language: "python" | "go"): string {
  try {
    const result = hljs.highlight(code, { language });
    return result.value;
  } catch (e) {
    // Fallback if something goes wrong; return escaped code as plain text
    console.warn("Highlight.js error:", e);
    return escapeHtml(code);
  }
}

/**
 * Escape HTML special characters.
 * Used as fallback when highlighting fails.
 */
function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#x27;",
  };
  return text.replace(/[&<>"']/g, (char: string) => map[char] || char);
}
