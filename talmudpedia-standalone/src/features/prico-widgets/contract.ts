import { z } from "zod";

export type PricoWidgetKind = "kpi" | "pie" | "bar" | "compare" | "table" | "note";

export type PricoWidgetDataPoint = {
  label: string;
  value: number;
};

export type PricoWidgetBase = {
  id: string;
  kind: PricoWidgetKind;
  span: number;
  title: string;
  subtitle?: string;
  footnote?: string;
};

export type PricoKpiWidget = PricoWidgetBase & {
  kind: "kpi";
  value: string;
};

export type PricoChartWidget = PricoWidgetBase & {
  kind: "pie" | "bar";
  data: PricoWidgetDataPoint[];
};

export type PricoCompareWidget = PricoWidgetBase & {
  kind: "compare";
  leftLabel: string;
  leftValue: number;
  rightLabel: string;
  rightValue: number;
  delta?: string;
};

export type PricoTableWidget = PricoWidgetBase & {
  kind: "table";
  columns: string[];
  rows: string[][];
};

export type PricoNoteWidget = PricoWidgetBase & {
  kind: "note";
  text: string;
};

export type PricoWidget =
  | PricoKpiWidget
  | PricoChartWidget
  | PricoCompareWidget
  | PricoTableWidget
  | PricoNoteWidget;

export type PricoWidgetRow = {
  widgets: PricoWidget[];
};

export type PricoWidgetBundle = {
  title?: string;
  subtitle?: string;
  rows: PricoWidgetRow[];
};

export type ValidatePricoWidgetBundleSuccess = {
  ok: true;
  bundle: PricoWidgetBundle;
};

export type ValidatePricoWidgetBundleFailure = {
  ok: false;
  error: string;
  details: {
    path: string;
    widget_id?: string | null;
    widget_kind?: string | null;
    hint?: string | null;
  };
};

export type ValidatePricoWidgetBundleResult =
  | ValidatePricoWidgetBundleSuccess
  | ValidatePricoWidgetBundleFailure;

const widgetBaseSchema = z.object({
  id: z.string().trim().min(1, "Widget id is required."),
  span: z
    .number({ error: "Widget span must be a number." })
    .int("Widget span must be an integer.")
    .min(1, "Widget span must be at least 1.")
    .max(12, "Widget span must be at most 12."),
  title: z.string().trim().min(1, "Widget title is required."),
  subtitle: z.string().trim().min(1).optional(),
  footnote: z.string().trim().min(1).optional(),
});

const dataPointSchema = z.object({
  label: z.string().trim().min(1, "Chart labels must be non-empty."),
  value: z.number({ error: "Chart values must be numeric." }).finite("Chart values must be finite."),
});

const kpiWidgetSchema = widgetBaseSchema.extend({
  kind: z.literal("kpi"),
  value: z.string().trim().min(1, "KPI value is required."),
});

const pieWidgetSchema = widgetBaseSchema.extend({
  kind: z.literal("pie"),
  data: z.array(dataPointSchema).min(1, "Chart widgets need at least one data point."),
});

const barWidgetSchema = widgetBaseSchema.extend({
  kind: z.literal("bar"),
  data: z.array(dataPointSchema).min(1, "Chart widgets need at least one data point."),
});

const compareWidgetSchema = widgetBaseSchema.extend({
  kind: z.literal("compare"),
  leftLabel: z.string().trim().min(1, "Compare widgets need leftLabel."),
  leftValue: z.number({ error: "Compare widgets need numeric leftValue." }).finite(),
  rightLabel: z.string().trim().min(1, "Compare widgets need rightLabel."),
  rightValue: z.number({ error: "Compare widgets need numeric rightValue." }).finite(),
  delta: z.string().trim().min(1).optional(),
});

const tableWidgetSchema = widgetBaseSchema
  .extend({
    kind: z.literal("table"),
    columns: z.array(z.string().trim().min(1, "Table columns must be non-empty.")).min(1, "Table widgets need at least one column."),
    rows: z.array(z.array(z.string())).default([]),
  })
  .superRefine((value, ctx) => {
    value.rows.forEach((row, rowIndex) => {
      if (row.length !== value.columns.length) {
        ctx.addIssue({
          code: "custom",
          path: ["rows", rowIndex],
          message: `Table row ${rowIndex + 1} has ${row.length} cells but expected ${value.columns.length}.`,
        });
      }
    });
  });

const noteWidgetSchema = widgetBaseSchema.extend({
  kind: z.literal("note"),
  text: z.string().trim().min(1, "Note widgets need text."),
});

const widgetSchema = z.discriminatedUnion("kind", [
  kpiWidgetSchema,
  pieWidgetSchema,
  barWidgetSchema,
  compareWidgetSchema,
  tableWidgetSchema,
  noteWidgetSchema,
]);

const rowSchema = z
  .object({
    widgets: z.array(widgetSchema).min(1, "Each row needs at least one widget."),
  })
  .superRefine((value, ctx) => {
    const span = value.widgets.reduce((sum, widget) => sum + widget.span, 0);
    if (span > 12) {
      ctx.addIssue({
        code: "custom",
        path: ["widgets"],
        message: `Row span exceeds 12 (got ${span}).`,
      });
    }
  });

const bundleSchema = z
  .object({
    title: z.string().trim().min(1).optional(),
    subtitle: z.string().trim().min(1).optional(),
    rows: z.array(rowSchema).min(1, "At least one row is required."),
  })
  .superRefine((value, ctx) => {
    const seen = new Map<string, { rowIndex: number; widgetIndex: number }>();
    value.rows.forEach((row, rowIndex) => {
      row.widgets.forEach((widget, widgetIndex) => {
        const existing = seen.get(widget.id);
        if (existing) {
          ctx.addIssue({
            code: "custom",
            path: ["rows", rowIndex, "widgets", widgetIndex, "id"],
            message: `Duplicate widget id '${widget.id}'.`,
          });
          return;
        }
        seen.set(widget.id, { rowIndex, widgetIndex });
      });
    });
  });

export function validatePricoWidgetBundle(input: unknown): ValidatePricoWidgetBundleResult {
  const parsed = bundleSchema.safeParse(input);
  if (parsed.success) {
    return {
      ok: true,
      bundle: parsed.data,
    };
  }

  const issue = parsed.error.issues[0];
  const path = issue?.path.filter((segment): segment is string | number => typeof segment === "string" || typeof segment === "number") || [];
  const details = extractIssueDetails(input, path);
  return {
    ok: false,
    error: issue?.message || "Invalid widget bundle.",
    details: {
      path: formatPath(path),
      widget_id: details.widgetId,
      widget_kind: details.widgetKind,
      hint: hintForIssue(issue?.message || "", details.widgetKind),
    },
  };
}

function formatPath(path: ReadonlyArray<string | number>): string {
  if (path.length === 0) {
    return "bundle";
  }
  return path
    .map((segment) => (typeof segment === "number" ? `[${segment}]` : segment))
    .join(".");
}

function extractIssueDetails(input: unknown, path: ReadonlyArray<string | number>) {
  let current: unknown = input;
  let widgetId: string | null = null;
  let widgetKind: string | null = null;

  for (const segment of path) {
    if (current == null || typeof current !== "object") {
      break;
    }
    const next = (current as Record<string, unknown>)[String(segment)];
    current = next;
    if (current && typeof current === "object") {
      const record = current as Record<string, unknown>;
      if (typeof record.id === "string") {
        widgetId = record.id;
      }
      if (typeof record.kind === "string") {
        widgetKind = record.kind;
      }
    }
  }

  return { widgetId, widgetKind };
}

function hintForIssue(message: string, widgetKind?: string | null): string | null {
  if (widgetKind === "compare") {
    return "Compare widgets require leftLabel, leftValue, rightLabel, and rightValue.";
  }
  if (widgetKind === "note") {
    return "Note widgets require a text field.";
  }
  if (widgetKind === "kpi") {
    return "KPI widgets require a non-empty value field.";
  }
  if (widgetKind === "table") {
    return "Table widgets require columns and rows with matching cell counts.";
  }
  if (widgetKind === "pie" || widgetKind === "bar") {
    return "Charts require a non-empty data array with { label, value } objects.";
  }
  if (/Row span exceeds 12/i.test(message)) {
    return "Keep each row's total span at 12 or less.";
  }
  if (/Duplicate widget id/i.test(message)) {
    return "Every widget in the bundle must have a unique id.";
  }
  if (/leftLabel|rightLabel|leftValue|rightValue|Compare widgets/i.test(message)) {
    return "Compare widgets require leftLabel, leftValue, rightLabel, and rightValue.";
  }
  if (/Table row/i.test(message)) {
    return "Each table row must have exactly the same number of cells as the columns array.";
  }
  if (/Chart widgets need at least one data point|Chart labels|Chart values/i.test(message)) {
    return "Charts require a non-empty data array with { label, value } objects.";
  }
  if (/KPI value is required/i.test(message)) {
    return "KPI widgets require a non-empty value field.";
  }
  if (/Note widgets need text/i.test(message)) {
    return "Note widgets require a text field.";
  }
  if (/Widget span/i.test(message)) {
    return "Widget spans must be integers from 1 to 12.";
  }
  if (/Widget title is required/i.test(message)) {
    return "Every widget requires a non-empty title.";
  }
  return "Use the strict JSON widget bundle schema with valid widget-specific fields.";
}
