import type { UIChartBlock } from "@agents24/ui-blocks-contract";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { BlockShell } from "../lib/block-shell";
import { useWidgetTheme } from "../lib/widget-theme";

export function PieBlock({ block }: { block: UIChartBlock }) {
  const theme = useWidgetTheme();

    return (
    <BlockShell block={block}>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(170px,0.85fr)]">
        <div className="h-44 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={block.data} dataKey="value" nameKey="label" innerRadius={42} outerRadius={78}>
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
                  fontSize: 12,
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="space-y-2 self-center">
          {block.data.map((item, index) => (
            <div key={item.label} className="flex items-center gap-3 text-sm">
              <div className="flex min-w-0 items-center gap-2">
                <span
                  className="size-2 rounded-full"
                  style={{ backgroundColor: theme.chartColors[index % theme.chartColors.length] }}
                />
                <span className={theme.legendLabel}>{item.label}</span>
              </div>
              <span className={theme.legendValue}>{item.value.toLocaleString()}</span>
            </div>
          ))}
        </div>
      </div>
    </BlockShell>
  );
}
