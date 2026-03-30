import type { UIKPIBlock } from "@agents24/ui-blocks-contract";

import { BlockShell } from "../lib/block-shell";
import { cx } from "../lib/layout";
import { useWidgetDensity } from "../lib/widget-density";
import { useWidgetTheme } from "../lib/widget-theme";

export function KPIBlock({ block }: { block: UIKPIBlock }) {
  const theme = useWidgetTheme();
  const density = useWidgetDensity();

  return (
    <BlockShell block={block}>
      <div className={cx(theme.kpiValue, density.kpiValue)}>{block.value}</div>
    </BlockShell>
  );
}
