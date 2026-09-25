/**
 * Inline code parsing: split text on backticks (UI-04).
 * Backticks delimit code spans; escaped HTML in prose stays as text.
 */

export interface InlineSegment {
  kind: "text" | "code";
  value: string;
}

/**
 * Split text into alternating text and code segments.
 * Backticks (`text`) delimit code; unmatched or empty backticks stay literal.
 * HTML tags in the text stay as plain text (not rendered as HTML).
 *
 * Examples:
 *   "Use `dp[i]` here" -> [text "Use ", code "dp[i]", text " here"]
 *   "No code here" -> [text "No code here"]
 *   "Trailing `" -> [text "Trailing `"] (unmatched backtick stays literal)
 *   "`` empty" -> [text "`` empty"] (empty backticks stay literal)
 *   "`a``b`" -> [code "a", text "`", code "b"] (`` is literal, not an escape)
 */
export function splitInlineCode(text: string): InlineSegment[] {
  const segments: InlineSegment[] = [];
  let current = "";
  let i = 0;

  while (i < text.length) {
    if (text[i] === "`") {
      // Found opening backtick. Look for closing backtick.
      const openIdx = i;
      i += 1;

      // Scan for closing backtick
      let found = false;
      while (i < text.length) {
        if (text[i] === "`") {
          found = true;
          break;
        }
        i += 1;
      }

      if (found) {
        // We have a matching pair. Check if code is empty.
        const code = text.substring(openIdx + 1, i);
        if (code.length === 0) {
          // Empty backticks stay literal: add both backticks to current text
          current += "``";
        } else {
          // We have content. Flush current text, add code segment.
          if (current.length > 0) {
            segments.push({ kind: "text", value: current });
            current = "";
          }
          segments.push({ kind: "code", value: code });
        }
        i += 1; // Move past closing backtick
      } else {
        // No closing backtick found. This opening backtick stays literal.
        current += text.substring(openIdx);
        i = text.length;
      }
    } else {
      // Regular character
      current += text[i];
      i += 1;
    }
  }

  // Flush remaining text
  if (current.length > 0) {
    segments.push({ kind: "text", value: current });
  }

  // If we have no segments at all, return one text segment with the original text
  if (segments.length === 0) {
    segments.push({ kind: "text", value: text });
  }

  return segments;
}
