import type { ReactNode } from "react";
import * as RechartsPrimitive from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

import { useLocale } from "./locale-context";
import type {
  TemplateCartesianChartWidgetSpec,
  TemplatePieChartWidgetSpec,
  TemplateStatWidgetSpec,
  TemplateTableWidgetSpec,
  TemplateWidgetBlock,
  TemplateWidgetValueFormat,
} from "./types";

const CHART_COLORS = [
  "hsl(210 80% 56%)",
  "hsl(262 65% 58%)",
  "hsl(32 92% 54%)",
  "hsl(152 55% 45%)",
  "hsl(348 80% 60%)",
];

function formatValue(
  value: unknown,
  format: TemplateWidgetValueFormat | undefined,
  locale: string,
): string {
  if (typeof value !== "number") {
    return String(value ?? "");
  }
  if (format === "currency") {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    }).format(value);
  }
  if (format === "percent") {
    return new Intl.NumberFormat(locale, {
      style: "percent",
      maximumFractionDigits: 1,
    }).format(Math.abs(value) > 1 ? value / 100 : value);
  }
  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: 2,
  }).format(value);
}

function WidgetShell({
  title,
  subtitle,
  children,
}: {
  title?: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <Card className="w-full gap-3 rounded-2xl border border-border/70 bg-card/95 py-3 shadow-none ring-0">
      {title || subtitle ? (
        <CardHeader className="px-3">
          {title ? <CardTitle>{title}</CardTitle> : null}
          {subtitle ? <CardDescription>{subtitle}</CardDescription> : null}
        </CardHeader>
      ) : null}
      <CardContent className="px-3">{children}</CardContent>
    </Card>
  );
}

function StatWidget({
  spec,
  title,
  subtitle,
}: {
  spec: TemplateStatWidgetSpec;
  title?: string;
  subtitle?: string;
}) {
  const { locale } = useLocale();
  const trend = spec.trend;
  return (
    <WidgetShell subtitle={subtitle} title={title}>
      <div className="flex items-end justify-between gap-4">
        <div className="space-y-1">
          {spec.label ? <div className="text-sm text-muted-foreground">{spec.label}</div> : null}
          <div className="text-3xl font-semibold tracking-tight">
            {formatValue(spec.value, spec.format, locale)}
          </div>
        </div>
        {trend ? (
          <div
            className={cn(
              "rounded-full px-2.5 py-1 text-xs font-medium",
              trend.direction === "up" && "bg-emerald-500/12 text-emerald-600",
              trend.direction === "down" && "bg-rose-500/12 text-rose-600",
              trend.direction === "flat" && "bg-muted text-muted-foreground",
            )}
          >
            {trend.direction === "up" ? "+" : trend.direction === "down" ? "-" : ""}
            {formatValue(Math.abs(trend.value), spec.format, locale)}
          </div>
        ) : null}
      </div>
    </WidgetShell>
  );
}

function TableWidget({
  spec,
  title,
  subtitle,
}: {
  spec: TemplateTableWidgetSpec;
  title?: string;
  subtitle?: string;
}) {
  return (
    <WidgetShell subtitle={subtitle} title={title}>
      <Table>
        <TableHeader>
          <TableRow>
            {spec.columns.map((column) => (
              <TableHead key={column.key}>{column.label}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {spec.rows.map((row, index) => (
            <TableRow key={`row-${index}`}>
              {spec.columns.map((column) => (
                <TableCell key={column.key}>{String(row[column.key] ?? "")}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </WidgetShell>
  );
}

function chartConfig(dataKey: string, label?: string) {
  return {
    [dataKey]: {
      label: label || dataKey,
      color: CHART_COLORS[0],
    },
  };
}

function CartesianWidget({
  block,
  spec,
}: {
  block: TemplateWidgetBlock;
  spec: TemplateCartesianChartWidgetSpec;
}) {
  const { locale } = useLocale();
  const dataKey = spec.yKey;
  const colorVar = `var(--color-${dataKey})`;
  return (
    <WidgetShell subtitle={block.subtitle} title={block.title}>
      <ChartContainer className="h-64 w-full" config={chartConfig(dataKey, spec.seriesLabel)}>
        {block.widgetType === "line_chart" ? (
          <RechartsPrimitive.LineChart data={spec.data}>
            <RechartsPrimitive.CartesianGrid vertical={false} />
            <RechartsPrimitive.XAxis dataKey={spec.xKey} tickLine={false} axisLine={false} />
            <RechartsPrimitive.YAxis
              tickFormatter={(value: number) => formatValue(value, spec.format, locale)}
              tickLine={false}
              axisLine={false}
              width={72}
            />
            <ChartTooltip content={<ChartTooltipContent />} />
            <RechartsPrimitive.Line
              type="monotone"
              dataKey={dataKey}
              stroke={colorVar}
              strokeWidth={2.5}
              dot={{ r: 3 }}
            />
          </RechartsPrimitive.LineChart>
        ) : (
          <RechartsPrimitive.BarChart data={spec.data}>
            <RechartsPrimitive.CartesianGrid vertical={false} />
            <RechartsPrimitive.XAxis dataKey={spec.xKey} tickLine={false} axisLine={false} />
            <RechartsPrimitive.YAxis
              tickFormatter={(value: number) => formatValue(value, spec.format, locale)}
              tickLine={false}
              axisLine={false}
              width={72}
            />
            <ChartTooltip content={<ChartTooltipContent />} />
            <RechartsPrimitive.Bar dataKey={dataKey} fill={colorVar} radius={[8, 8, 0, 0]} />
          </RechartsPrimitive.BarChart>
        )}
      </ChartContainer>
    </WidgetShell>
  );
}

function PieWidget({
  block,
  spec,
}: {
  block: TemplateWidgetBlock;
  spec: TemplatePieChartWidgetSpec;
}) {
  const config = Object.fromEntries(
    spec.data.map((item, index) => [
      String(item[spec.labelKey] ?? `item-${index}`),
      {
        label: String(item[spec.labelKey] ?? `Item ${index + 1}`),
        color: CHART_COLORS[index % CHART_COLORS.length],
      },
    ]),
  );

  return (
    <WidgetShell subtitle={block.subtitle} title={block.title}>
      <ChartContainer className="h-64 w-full" config={config}>
        <RechartsPrimitive.PieChart>
          <ChartTooltip content={<ChartTooltipContent nameKey={spec.labelKey} />} />
          <RechartsPrimitive.Pie
            data={spec.data}
            dataKey={spec.valueKey}
            nameKey={spec.labelKey}
            innerRadius={52}
            outerRadius={84}
            paddingAngle={2}
          >
            {spec.data.map((item, index) => (
              <RechartsPrimitive.Cell
                key={`slice-${index}`}
                fill={CHART_COLORS[index % CHART_COLORS.length]}
                name={String(item[spec.labelKey] ?? `Item ${index + 1}`)}
              />
            ))}
          </RechartsPrimitive.Pie>
        </RechartsPrimitive.PieChart>
      </ChartContainer>
    </WidgetShell>
  );
}

function UnsupportedWidget({ block }: { block: TemplateWidgetBlock }) {
  return (
    <WidgetShell subtitle={block.subtitle} title={block.title || "Unsupported widget"}>
      <div className="text-sm text-muted-foreground">
        Widget type <span className="font-medium text-foreground">{block.widgetType}</span> is not supported yet.
      </div>
    </WidgetShell>
  );
}

export function AssistantWidgetBlock({ block }: { block: TemplateWidgetBlock }) {
  if (block.widgetType === "stat") {
    return <StatWidget spec={block.spec as TemplateStatWidgetSpec} title={block.title} subtitle={block.subtitle} />;
  }
  if (block.widgetType === "table") {
    return <TableWidget spec={block.spec as TemplateTableWidgetSpec} title={block.title} subtitle={block.subtitle} />;
  }
  if (block.widgetType === "bar_chart" || block.widgetType === "line_chart") {
    return <CartesianWidget block={block} spec={block.spec as TemplateCartesianChartWidgetSpec} />;
  }
  if (block.widgetType === "pie_chart") {
    return <PieWidget block={block} spec={block.spec as TemplatePieChartWidgetSpec} />;
  }
  return <UnsupportedWidget block={block} />;
}
