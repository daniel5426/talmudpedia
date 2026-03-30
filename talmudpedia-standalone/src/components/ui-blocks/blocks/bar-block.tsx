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
import { useWidgetDensity } from "../lib/widget-density";
import { useWidgetTheme } from "../lib/widget-theme";

export function BarBlock({ block }: { block: UIChartBlock }) {
  const theme = useWidgetTheme();
  const density = useWidgetDensity();
  const { isRtl } = useLocale();
  const rtlLabelWidth = Math.max(52, density.barLabelWidth - (density.id === "compact" ? 8 : 12));
  const yAxisWidth = isRtl ? rtlLabelWidth : density.barLabelWidth;

  return (
    <BlockShell block={block}>
      <div className={`${density.chartHeightClass} w-full`} dir={isRtl ? "rtl" : "ltr"}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={block.data}
            layout="vertical"
            margin={{
              left: isRtl ? density.barMarginTrailing : density.barMarginLeading,
              right: isRtl ? density.barMarginLeading : density.barMarginTrailing,
              top: density.barMarginTop,
              bottom: density.barMarginBottom,
            }}
          >
            <CartesianGrid horizontal={false} strokeDasharray="3 3" stroke={theme.gridColor} />
            <XAxis
              type="number"
              reversed={isRtl}
              tickLine={false}
              axisLine={false}
              tick={{ fill: theme.axisTickColor, fontSize: density.barAxisFontSize }}
            />
            <YAxis
              dataKey="label"
              type="category"
              orientation={isRtl ? "right" : "left"}
              mirror={false}
              interval={0}
              tickMargin={density.id === "compact" ? 6 : 8}
              width={yAxisWidth}
              tickLine={false}
              axisLine={false}
              tick={{
                fill: theme.axisTickColor,
                fontSize: density.barAxisFontSize,
                textAnchor: "end",
              }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: theme.tooltipBg,
                color: theme.tooltipText,
                border: `1px solid ${theme.tooltipBorder}`,
                borderRadius: 8,
                fontSize: density.barTooltipFontSize,
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
