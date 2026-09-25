/**
 * Inline text renderer: renders backtick spans as code (UI-04).
 * Produces React text nodes and <code> elements; no raw HTML injection.
 */

// eslint-disable-next-line @typescript-eslint/no-unused-vars
import * as React from "react";
import { useMemo } from "react";
import { splitInlineCode } from "../lib/inlineCode";

export interface InlineTextProps {
  text: string;
}

export function InlineText({ text }: InlineTextProps): React.ReactElement {
  const segments = useMemo(() => splitInlineCode(text), [text]);

  return (
    <span className="whitespace-pre-line">
      {segments.map((segment, i) => {
        if (segment.kind === "code") {
          return (
            <code key={i} className="bg-gray-100 px-1 py-0.5 rounded font-mono text-sm">
              {segment.value}
            </code>
          );
        }
        return <span key={i}>{segment.value}</span>;
      })}
    </span>
  );
}
