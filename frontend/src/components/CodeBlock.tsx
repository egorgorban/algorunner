/**
 * Code block renderer with syntax highlighting and copy button (UI-04, D-10).
 * The only raw-HTML sink in the app; receives output from highlight.js only.
 */

// eslint-disable-next-line @typescript-eslint/no-unused-vars
import * as React from "react";
import { useState, useMemo } from "react";
import { highlight } from "../lib/highlight";

export interface CodeBlockProps {
  code: string;
  language: "python" | "go";
}

export function CodeBlock({ code, language }: CodeBlockProps): React.ReactElement {
  const [copied, setCopied] = useState(false);

  // Compute highlighted HTML once per code/language change
  const highlightedHtml = useMemo(() => highlight(code, language), [code, language]);

  const languageLabel = language === "python" ? "Python" : "Go";

  async function handleCopy(): Promise<void> {
    try {
      // Try Clipboard API first (requires secure context)
      if (navigator.clipboard && navigator.clipboard.writeText) {
        try {
          await navigator.clipboard.writeText(code);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
          return;
        } catch (e) {
          // Clipboard API failed; fall through to fallback
          console.debug("Clipboard API failed:", e);
        }
      }
    } catch (e) {
      console.debug("Clipboard not available:", e);
    }

    // Fallback: select text and execCommand
    const codeEl = document.querySelector(`[data-code-block="${language}"]`) as HTMLElement | null;
    if (codeEl) {
      const selection = window.getSelection();
      if (selection) {
        const range = document.createRange();
        range.selectNodeContents(codeEl);
        selection.removeAllRanges();
        selection.addRange(range);

        try {
          const success = document.execCommand("copy");
          if (success) {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
            selection.removeAllRanges();
            return;
          }
        } catch (e) {
          console.debug("execCommand copy failed:", e);
        }
      }
    }

    // Last resort: tell user to copy manually
    alert("Выделите код вручную");
  }

  return (
    <div className="bg-gray-900 rounded border border-gray-700 overflow-hidden my-4">
      {/* Language label and copy button */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
        <span className="text-gray-400 text-sm font-mono">{languageLabel}</span>
        <button
          onClick={handleCopy}
          className="px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-100 text-xs rounded transition-colors"
          title="Copy code"
        >
          {copied ? "Скопировано" : "Копировать"}
        </button>
      </div>

      {/* Code block with syntax highlighting from highlight.js */}
      <pre className="overflow-x-auto p-4 text-sm text-gray-100">
        <code
          className={`hljs language-${language}`}
          data-code-block={language}
          dangerouslySetInnerHTML={{ __html: highlightedHtml }}
        />
      </pre>
    </div>
  );
}
