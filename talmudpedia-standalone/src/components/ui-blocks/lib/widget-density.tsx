import { createContext, useContext } from "react";

export type WidgetDensityMode = "auto" | "comfortable" | "compact";

export type WidgetDensity = {
  id: Exclude<WidgetDensityMode, "auto">;
  bundleGap: string;
  rowGap: string;
  rowGrid: string;
  bundleTitle: string;
  bundleSubtitle: string;
  blockTitle: string;
  blockSubtitle: string;
  footnote: string;
  shellHeaderPadding: string;
  shellBodyPadding: string;
  shellFootnotePadding: string;
  chartHeightClass: string;
  pieChartHeightClass: string;
  pieInnerRadius: number;
  pieOuterRadius: number;
  pieLegendLayout: string;
  pieLegendRow: string;
  pieLegendDot: string;
  pieLegendValue: string;
  barLabelWidth: number;
  barAxisFontSize: number;
  barTooltipFontSize: number;
  barMarginTop: number;
  barMarginBottom: number;
  barMarginLeading: number;
  barMarginTrailing: number;
  compareGap: string;
  compareTrackHeight: string;
  tableText: string;
  tableCellPadding: string;
  noteText: string;
  kpiValue: string;
};

export const COMFORTABLE_WIDGET_DENSITY: WidgetDensity = {
  id: "comfortable",
  bundleGap: "space-y-4",
  rowGap: "gap-4",
  rowGrid: "grid-cols-1 md:grid-cols-12",
  bundleTitle: "",
  bundleSubtitle: "",
  blockTitle: "",
  blockSubtitle: "",
  footnote: "",
  shellHeaderPadding: "px-4 pt-4 pb-2",
  shellBodyPadding: "px-4 pb-4",
  shellFootnotePadding: "px-4 py-2",
  chartHeightClass: "h-56",
  pieChartHeightClass: "h-44",
  pieInnerRadius: 42,
  pieOuterRadius: 78,
  pieLegendLayout: "grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(170px,0.85fr)]",
  pieLegendRow: "flex items-center gap-3 text-sm",
  pieLegendDot: "size-2",
  pieLegendValue: "text-sm",
  barLabelWidth: 112,
  barAxisFontSize: 12,
  barTooltipFontSize: 12,
  barMarginTop: 4,
  barMarginBottom: 4,
  barMarginLeading: 12,
  barMarginTrailing: 8,
  compareGap: "space-y-4",
  compareTrackHeight: "h-2",
  tableText: "text-sm",
  tableCellPadding: "px-2 py-2",
  noteText: "text-sm",
  kpiValue: "text-3xl",
};

export const COMPACT_WIDGET_DENSITY: WidgetDensity = {
  id: "compact",
  bundleGap: "space-y-2.5",
  rowGap: "gap-2.5",
  rowGrid: "grid-cols-2 md:grid-cols-12",
  bundleTitle: "text-xs",
  bundleSubtitle: "text-[11px]",
  blockTitle: "text-xs",
  blockSubtitle: "text-[11px] mt-0.5",
  footnote: "text-[0.65rem]",
  shellHeaderPadding: "px-3 pt-3 pb-1.5",
  shellBodyPadding: "px-3 pb-3",
  shellFootnotePadding: "px-3 py-1.5",
  chartHeightClass: "h-40",
  pieChartHeightClass: "h-32",
  pieInnerRadius: 28,
  pieOuterRadius: 52,
  pieLegendLayout: "grid gap-2",
  pieLegendRow: "flex items-center gap-2 text-xs",
  pieLegendDot: "size-1.5",
  pieLegendValue: "text-xs",
  barLabelWidth: 68,
  barAxisFontSize: 10,
  barTooltipFontSize: 11,
  barMarginTop: 2,
  barMarginBottom: 2,
  barMarginLeading: 6,
  barMarginTrailing: 4,
  compareGap: "space-y-2.5",
  compareTrackHeight: "h-1.5",
  tableText: "text-xs",
  tableCellPadding: "px-1.5 py-1.5",
  noteText: "text-xs",
  kpiValue: "text-2xl",
};

const DensityContext = createContext<WidgetDensity>(COMFORTABLE_WIDGET_DENSITY);

export const WidgetDensityProvider = DensityContext.Provider;

export function useWidgetDensity(): WidgetDensity {
  return useContext(DensityContext);
}
