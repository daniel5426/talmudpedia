import { Renderer } from "@openuidev/react-lang";
import { openuiLibrary } from "@openuidev/react-ui";

import type { TemplateUiBlock } from "./types";

export function AssistantOpenUiBlock({
  block,
  isStreaming = false,
}: {
  block: TemplateUiBlock;
  isStreaming?: boolean;
}) {
  return (
    <div className="w-full overflow-hidden rounded-2xl border border-border/60 bg-card/95 p-3">
      <Renderer
        response={block.content}
        library={openuiLibrary}
        isStreaming={isStreaming}
      />
    </div>
  );
}
