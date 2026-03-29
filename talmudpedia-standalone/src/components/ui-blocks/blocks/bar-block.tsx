import type { UIChartBlock } from "@agents24/ui-blocks-contract";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useLocale } from "@/features/classic-chat/locale-context";

import { BlockShell } from "../lib/block-shell";
import { useWidgetTheme } from "../lib/widget-theme";

export function BarBlock({ block }: { block: UIChartBlock }) {
  const theme = useWidgetTheme();
  const { isRtl } = useLocale();

  return (
    <BlockShell block={block}>
      <div className="h-56 w-full" dir={isRtl ? "rtl" : "ltr"}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={block.data}
            layout="vertical"
            margin={{
              left: isRtl ? 12 : 24,
              right: isRtl ? 24 : 12,
              top: 4,
              bottom: 4,
            }}
          >
            <CartesianGrid horizontal={false} strokeDasharray="3 3" stroke={theme.gridColor} />
            <XAxis
              type="number"
              reversed={isRtl}
              tickLine={false}
              axisLine={false}
              tick={{ fill: theme.axisTickColor, fontSize: 12 }}
            />
            <YAxis
              dataKey="label"
              type="category"
              orientation={isRtl ? "right" : "left"}
              mirror={false}
              interval={0}
              tickMargin={12}
              width={136}
              tickLine={false}
              axisLine={false}
              tick={{
                fill: theme.axisTickColor,
                fontSize: 12,
                textAnchor: "end",
              }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: theme.tooltipBg,
                color: theme.tooltipText,
                border: `1px solid ${theme.tooltipBorder}`,
                borderRadius: 8,
                fontSize: 12,
              }}
            />
            <Bar dataKey="value" radius={4}>
              {block.data.map((entry, index) => (
                <Cell key={entry.label} fill={theme.chartColors[index % theme.chartColors.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </BlockShell>
  );
}
