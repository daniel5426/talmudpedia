import type { UINoteBlock } from "@agents24/ui-blocks-contract";

import { BlockShell } from "../lib/block-shell";
import { cx } from "../lib/layout";
import { useWidgetDensity } from "../lib/widget-density";
import { useWidgetTheme } from "../lib/widget-theme";

export function NoteBlock({ block }: { block: UINoteBlock }) {
  const theme = useWidgetTheme();
  const density = useWidgetDensity();

  return (
    <BlockShell block={block}>
      <div className={cx(theme.noteText, density.noteText)}>{block.text}</div>
    </BlockShell>
  );
}
