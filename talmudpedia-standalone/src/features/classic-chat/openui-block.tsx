import { Component, type ReactNode } from "react";

import { Renderer } from "@openuidev/react-lang";
import { openuiLibrary } from "@openuidev/react-ui";

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
  return (
    <div className="w-full overflow-hidden rounded-2xl border border-border/60 bg-card/95 p-3">
      <OpenUiErrorBoundary
        fallback={
          <pre className="overflow-x-auto whitespace-pre-wrap break-words text-sm text-muted-foreground">
            {block.content}
          </pre>
        }
      >
        <Renderer
          response={block.content}
          library={openuiLibrary}
          isStreaming={isStreaming}
        />
      </OpenUiErrorBoundary>
    </div>
  );
}
