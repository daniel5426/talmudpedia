import type { UIChartBlock } from "@agents24/ui-blocks-contract";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { BlockShell } from "../lib/block-shell";
import { cx } from "../lib/layout";
import { useWidgetDensity } from "../lib/widget-density";
import { useWidgetTheme } from "../lib/widget-theme";

export function PieBlock({ block }: { block: UIChartBlock }) {
  const theme = useWidgetTheme();
  const density = useWidgetDensity();

  return (
    <BlockShell block={block}>
      <div className={density.pieLegendLayout}>
        <div className={cx(density.pieChartHeightClass, "w-full")}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={block.data}
                dataKey="value"
                nameKey="label"
                innerRadius={density.pieInnerRadius}
                outerRadius={density.pieOuterRadius}
              >
                {block.data.map((entry, index) => (
                  <Cell key={entry.label} fill={theme.chartColors[index % theme.chartColors.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: theme.tooltipBg,
                  color: theme.tooltipText,
                  border: `1px solid ${theme.tooltipBorder}`,
                  borderRadius: 8,
                  fontSize: density.barTooltipFontSize,
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="space-y-1.5 self-center">
          {block.data.map((item, index) => (
            <div key={item.label} className={density.pieLegendRow}>
              <div className="flex min-w-0 items-center gap-2">
                <span
                  className={cx(density.pieLegendDot, "rounded-full")}
                  style={{ backgroundColor: theme.chartColors[index % theme.chartColors.length] }}
                />
                <span className={theme.legendLabel}>{item.label}</span>
              </div>
              <span className={cx(theme.legendValue, density.pieLegendValue)}>{item.value.toLocaleString()}</span>
            </div>
          ))}
        </div>
      </div>
    </BlockShell>
  );
}
