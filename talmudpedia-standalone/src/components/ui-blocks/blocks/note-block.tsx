import type { UINoteBlock } from "@agents24/ui-blocks-contract";

import { BlockShell } from "../lib/block-shell";
import { useWidgetTheme } from "../lib/widget-theme";

export function NoteBlock({ block }: { block: UINoteBlock }) {
  const theme = useWidgetTheme();

  return (
    <BlockShell block={block}>
      <div className={theme.noteText}>{block.text}</div>
    </BlockShell>
  );
}
