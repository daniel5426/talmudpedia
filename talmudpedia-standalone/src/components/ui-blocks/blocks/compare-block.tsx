import type { UICompareBlock } from "@agents24/ui-blocks-contract";

import { BlockShell } from "../lib/block-shell";
import { cx } from "../lib/layout";
import { useWidgetDensity } from "../lib/widget-density";
import { useWidgetTheme } from "../lib/widget-theme";

function CompareRow({
  color,
  label,
  pct,
  value,
  labelClass,
  valueClass,
  trackClass,
  trackHeightClass,
}: {
  color: string;
  label: string;
  pct: number;
  value: number;
  labelClass: string;
  valueClass: string;
  trackClass: string;
  trackHeightClass: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-3">
        <span className={labelClass}>{label}</span>
        <span className={valueClass}>{value.toLocaleString()}</span>
      </div>
      <div className={cx("w-full overflow-hidden rounded-full", trackHeightClass, trackClass)}>
        <div className="h-full rounded-full" style={{ backgroundColor: color, width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function CompareBlock({ block }: { block: UICompareBlock }) {
  const theme = useWidgetTheme();
  const density = useWidgetDensity();
  const max = Math.max(block.leftValue, block.rightValue, 1);

  return (
    <BlockShell block={block}>
      <div className={density.compareGap}>
        <CompareRow
          color={theme.chartColors[0]}
          label={block.leftLabel}
          pct={(block.leftValue / max) * 100}
          value={block.leftValue}
          labelClass={theme.compareLabel}
          valueClass={theme.compareValue}
          trackClass={theme.compareTrack}
          trackHeightClass={density.compareTrackHeight}
        />
        <CompareRow
          color={theme.chartColors[1]}
          label={block.rightLabel}
          pct={(block.rightValue / max) * 100}
          value={block.rightValue}
          labelClass={theme.compareLabel}
          valueClass={theme.compareValue}
          trackClass={theme.compareTrack}
          trackHeightClass={density.compareTrackHeight}
        />
        {block.delta ? <div className={theme.compareDelta}>{block.delta}</div> : null}
      </div>
    </BlockShell>
  );
}
