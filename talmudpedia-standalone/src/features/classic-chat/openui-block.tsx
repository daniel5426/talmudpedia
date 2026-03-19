import { Component, type ReactNode, useState } from "react";

import { Renderer, type ParseResult } from "@openuidev/react-lang";
import { openuiChatLibrary, openuiLibrary } from "@openuidev/react-ui";
import { Shimmer } from "@/components/ai-elements/shimmer";

import type { TemplateUiBlock } from "./types";

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
  const shouldShowFallback = !isStreaming && block.content.trim() && !parseResult?.root;
  const library = block.surface === "chat_inline" ? openuiChatLibrary : openuiLibrary;

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
              {block.content}
            </pre>
          }
        >
          <Renderer
            key={isStreaming ? "streaming" : `final:${block.content}`}
            response={block.content}
            library={library}
            isStreaming={isStreaming}
            onParseResult={setParseResult}
          />
        </OpenUiErrorBoundary>
      )}
    </div>
  );
}
