import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  XAxis,
  YAxis,
} from "recharts";

import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

import type {
  PricoCompareWidget,
  PricoNoteWidget,
  PricoTableWidget,
  PricoWidget,
  PricoWidgetRow,
  PricoWidgetBundle,
} from "./contract";

const WIDGET_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];

function spanClass(span: number): string {
  if (span === 12) return "md:col-span-12";
  if (span === 11) return "md:col-span-11";
  if (span === 10) return "md:col-span-10";
  if (span === 9) return "md:col-span-9";
  if (span === 8) return "md:col-span-8";
  if (span === 7) return "md:col-span-7";
  if (span === 6) return "md:col-span-6";
  if (span === 5) return "md:col-span-5";
  if (span === 4) return "md:col-span-4";
  if (span === 3) return "md:col-span-3";
  return "md:col-span-3";
}

function normalizeRow(row: PricoWidgetRow): PricoWidgetRow {
  const widgets = row.widgets;
  const totalSpan = widgets.reduce((sum, widget) => sum + widget.span, 0);

  if (widgets.length === 1 && widgets[0]?.span !== 12) {
    return {
      widgets: widgets.map((widget) => ({ ...widget, span: 12 })),
    };
  }

  if (totalSpan >= 12) {
    return row;
  }

  if (widgets.length === 2) {
    return {
      widgets: widgets.map((widget) => ({ ...widget, span: 6 })),
    };
  }

  if (widgets.length === 3) {
    return {
      widgets: widgets.map((widget) => ({ ...widget, span: 4 })),
    };
  }

  if (widgets.length === 4) {
    return {
      widgets: widgets.map((widget) => ({ ...widget, span: 3 })),
    };
  }

  return row;
}

function widgetShell(widget: PricoWidget, children: React.ReactNode) {
  return (
    <section
      key={widget.id}
      className={cn(
        "col-span-1 overflow-hidden rounded-sm bg-muted/40",
        spanClass(widget.span),
      )}
    >
      <div className="px-3 pt-3 pb-1">
        <div className="text-sm font-semibold text-card-foreground">{widget.title}</div>
        {widget.subtitle ? <div className="mt-0.5 text-xs text-muted-foreground">{widget.subtitle}</div> : null}
      </div>
      <div className="px-3 pb-3">{children}</div>
      {widget.footnote ? (
        <div className="border-t border-border/50 px-3 py-2 text-[0.7rem] text-muted-foreground">{widget.footnote}</div>
      ) : null}
    </section>
  );
}

function renderChart(widget: Extract<PricoWidget, { kind: "pie" | "bar" }>) {
  const config = Object.fromEntries(
    widget.data.map((item, index) => [
      item.label,
      {
        label: item.label,
        color: WIDGET_COLORS[index % WIDGET_COLORS.length],
      },
    ]),
  );

  if (widget.kind === "pie") {
    return widgetShell(
      widget,
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_160px]">
        <ChartContainer className="h-52 w-full" config={config}>
          <PieChart>
            <ChartTooltip content={<ChartTooltipContent hideLabel />} />
            <Pie data={widget.data} dataKey="value" nameKey="label" innerRadius={40} outerRadius={76}>
              {widget.data.map((entry, index) => (
                <Cell key={entry.label} fill={WIDGET_COLORS[index % WIDGET_COLORS.length]} />
              ))}
            </Pie>
          </PieChart>
        </ChartContainer>
        <div className="space-y-1.5 self-center">
          {widget.data.map((item, index) => (
            <div key={item.label} className="flex items-center justify-between gap-3 text-sm">
              <div className="flex items-center gap-2">
                <span
                  className="size-2 rounded-full"
                  style={{ backgroundColor: WIDGET_COLORS[index % WIDGET_COLORS.length] }}
                />
                <span className="text-muted-foreground">{item.label}</span>
              </div>
              <span className="font-medium tabular-nums text-card-foreground">{item.value.toLocaleString()}</span>
            </div>
          ))}
        </div>
      </div>,
    );
  }

  return widgetShell(
    widget,
    <ChartContainer className="h-52 w-full" config={config}>
      <BarChart data={widget.data} layout="vertical" margin={{ left: 8, right: 8 }}>
        <CartesianGrid horizontal={false} strokeDasharray="3 3" />
        <XAxis type="number" tickLine={false} axisLine={false} />
        <YAxis dataKey="label" type="category" width={90} tickLine={false} axisLine={false} />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Bar dataKey="value" radius={3}>
          {widget.data.map((entry, index) => (
            <Cell key={entry.label} fill={WIDGET_COLORS[index % WIDGET_COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ChartContainer>,
  );
}

function renderCompare(widget: PricoCompareWidget) {
  const max = Math.max(widget.leftValue, widget.rightValue, 1);
  const leftPct = (widget.leftValue / max) * 100;
  const rightPct = (widget.rightValue / max) * 100;

  return widgetShell(
    widget,
    <div className="space-y-4">
      <CompareRow label={widget.leftLabel} value={widget.leftValue} pct={leftPct} colorVar={WIDGET_COLORS[0]} />
      <CompareRow label={widget.rightLabel} value={widget.rightValue} pct={rightPct} colorVar={WIDGET_COLORS[1]} />
      {widget.delta ? (
        <div className="mt-1 text-xs text-muted-foreground">{widget.delta}</div>
      ) : null}
    </div>,
  );
}

function CompareRow({ label, value, pct, colorVar }: { label: string; value: number; pct: number; colorVar: string }) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className="text-lg font-semibold tabular-nums text-card-foreground">{value.toLocaleString()}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: colorVar }}
        />
      </div>
    </div>
  );
}

function renderTable(widget: PricoTableWidget) {
  return widgetShell(
    widget,
    <Table>
      <TableHeader>
        <TableRow>
          {widget.columns.map((column) => (
            <TableHead key={column}>{column}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {widget.rows.map((row, rowIndex) => (
          <TableRow key={`${widget.id}-${rowIndex}`}>
            {row.map((cell, cellIndex) => (
              <TableCell key={`${widget.id}-${rowIndex}-${cellIndex}`}>{cell}</TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>,
  );
}

function renderNote(widget: PricoNoteWidget) {
  return widgetShell(widget, <div className="text-sm leading-relaxed text-muted-foreground">{widget.text}</div>);
}

export function renderWidget(widget: PricoWidget) {
  if (widget.kind === "kpi") {
    return widgetShell(
      widget,
      <div className="text-2xl font-semibold tabular-nums text-card-foreground">{widget.value}</div>,
    );
  }
  if (widget.kind === "pie" || widget.kind === "bar") {
    return renderChart(widget);
  }
  if (widget.kind === "compare") {
    return renderCompare(widget);
  }
  if (widget.kind === "table") {
    return renderTable(widget);
  }
  if (widget.kind === "note") {
    return renderNote(widget);
  }
  return null;
}

type PricoWidgetBundleViewProps = {
  bundle: PricoWidgetBundle;
};

export function PricoWidgetBundleView({ bundle }: PricoWidgetBundleViewProps) {
  const normalizedRows = bundle.rows.map(normalizeRow);

  return (
    <div className="space-y-3">
      {bundle.title || bundle.subtitle ? (
        <div>
          {bundle.title ? <div className="text-sm font-semibold text-foreground">{bundle.title}</div> : null}
          {bundle.subtitle ? <div className="mt-0.5 text-xs text-muted-foreground">{bundle.subtitle}</div> : null}
        </div>
      ) : null}
      {normalizedRows.map((row, index) => (
        <div key={`row-${index}`} className="grid grid-cols-1 gap-3 md:grid-cols-12">
          {row.widgets.map((widget) => renderWidget(widget))}
        </div>
      ))}
    </div>
  );
}
