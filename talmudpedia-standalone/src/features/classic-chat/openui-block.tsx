import { Component, type ReactNode, useMemo, useState } from "react";

import { Renderer, createParser, type ParseResult } from "@openuidev/react-lang";
import { openuiChatLibrary, openuiLibrary } from "@openuidev/react-ui";
import { Shimmer } from "@/components/ai-elements/shimmer";

import type { TemplateUiBlock } from "./types";

function sanitizeOpenUiSource(content: string) {
  const normalized = content.replace(/\r\n/g, "\n");
  const lines = normalized.split("\n");
  const firstAssignment = lines.findIndex((line) =>
    /^\s*[A-Za-z_][A-Za-z0-9_]*\s*=/.test(line),
  );
  const assigned = firstAssignment > 0 ? lines.slice(firstAssignment) : lines;
  const rootIndex = assigned.findIndex((line) => /^\s*root\s*=/.test(line));
  const reordered =
    rootIndex > 0
      ? [assigned[rootIndex], ...assigned.slice(0, rootIndex), ...assigned.slice(rootIndex + 1)]
      : assigned;
  if (reordered.length === 0) {
    return normalized.trim();
  }
  return reordered.join("\n").trim();
}

class OpenUiErrorBoundary extends Component<
  { children: ReactNode; fallback: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: unknown) {
    console.error("[standalone-openui] render failed", error);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

export function AssistantOpenUiBlock({
  block,
  isStreaming = false,
}: {
  block: TemplateUiBlock;
  isStreaming?: boolean;
}) {
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const source = sanitizeOpenUiSource(block.content);
  const library = block.surface === "chat_inline" ? openuiChatLibrary : openuiLibrary;
  const finalParseResult = useMemo(() => {
    if (isStreaming || !source.trim()) {
      return null;
    }
    try {
      return createParser(library.toJSONSchema()).parse(source);
    } catch (error) {
      console.warn("[standalone-openui] parser threw", { source, error });
      return null;
    }
  }, [isStreaming, library, source]);
  const shouldShowFallback = !isStreaming && source.trim() && !finalParseResult?.root;

  if (!isStreaming && source.trim() && !finalParseResult?.root) {
    console.warn("[standalone-openui] parse failed", {
      source,
      meta: finalParseResult?.meta ?? null,
    });
  }

  return (
    <div className="w-full overflow-hidden rounded-2xl border border-border/60 bg-card/95 p-3">
      {shouldShowFallback ? (
        <pre className="overflow-x-auto whitespace-pre-wrap break-words text-sm text-muted-foreground">
          {block.content}
        </pre>
      ) : isStreaming && !parseResult?.root ? (
        <div className="px-1 py-1 text-[0.95rem] text-muted-foreground">
          <Shimmer>Building UI...</Shimmer>
        </div>
      ) : (
        <OpenUiErrorBoundary
          fallback={
            <pre className="overflow-x-auto whitespace-pre-wrap break-words text-sm text-muted-foreground">
              {source}
            </pre>
          }
        >
          <Renderer
            key={isStreaming ? "streaming" : `final:${source}`}
            response={source}
            library={library}
            isStreaming={isStreaming}
            onParseResult={setParseResult}
          />
        </OpenUiErrorBoundary>
      )}
    </div>
  );
}
