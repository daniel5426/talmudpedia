import type { UICompareBlock } from "@agents24/ui-blocks-contract";

import { BlockShell } from "../lib/block-shell";
import { useWidgetTheme } from "../lib/widget-theme";

function CompareRow({
  color,
  label,
  pct,
  value,
  labelClass,
  valueClass,
  trackClass,
}: {
  color: string;
  label: string;
  pct: number;
  value: number;
  labelClass: string;
  valueClass: string;
  trackClass: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-3">
        <span className={labelClass}>{label}</span>
        <span className={valueClass}>{value.toLocaleString()}</span>
      </div>
      <div className={`h-2 w-full overflow-hidden rounded-full ${trackClass}`}>
        <div className="h-full rounded-full" style={{ backgroundColor: color, width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function CompareBlock({ block }: { block: UICompareBlock }) {
  const theme = useWidgetTheme();
  const max = Math.max(block.leftValue, block.rightValue, 1);

  return (
    <BlockShell block={block}>
      <div className="space-y-4">
        <CompareRow
          color={theme.chartColors[0]}
          label={block.leftLabel}
          pct={(block.leftValue / max) * 100}
          value={block.leftValue}
          labelClass={theme.compareLabel}
          valueClass={theme.compareValue}
          trackClass={theme.compareTrack}
        />
        <CompareRow
          color={theme.chartColors[1]}
          label={block.rightLabel}
          pct={(block.rightValue / max) * 100}
          value={block.rightValue}
          labelClass={theme.compareLabel}
          valueClass={theme.compareValue}
          trackClass={theme.compareTrack}
        />
        {block.delta ? <div className={theme.compareDelta}>{block.delta}</div> : null}
      </div>
    </BlockShell>
  );
}
