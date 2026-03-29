import type { UIKPIBlock } from "@agents24/ui-blocks-contract";

import { BlockShell } from "../lib/block-shell";
import { useWidgetTheme } from "../lib/widget-theme";

export function KPIBlock({ block }: { block: UIKPIBlock }) {
  const theme = useWidgetTheme();

  return (
    <BlockShell block={block}>
      <div className={theme.kpiValue}>{block.value}</div>
    </BlockShell>
  );
}
