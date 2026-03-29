import { createContext, useContext } from "react";

export type WidgetTheme = {
  id: string;
  name: string;
  // Card shell
  card: string;
  // Header text
  title: string;
  subtitle: string;
  // Bundle-level title
  bundleTitle: string;
  bundleSubtitle: string;
  // Footnote
  footnote: string;
  footnoteBorder: string;
  // Chart
  chartColors: string[];
  // KPI
  kpiValue: string;
  // Compare
  compareLabel: string;
  compareValue: string;
  compareTrack: string;
  compareDelta: string;
  // Table
  tableHeader: string;
  tableHeaderBorder: string;
  tableCell: string;
  tableCellBorder: string;
  // Note
  noteText: string;
  // Pie legend
  legendLabel: string;
  legendValue: string;
  legendDot: string;
  // Bar/axis
  gridColor: string;
  axisTickColor: string;
  tooltipBg: string;
  tooltipText: string;
  tooltipBorder: string;
};

/* ── Theme 1: Clean ── */
export const THEME_CLEAN: WidgetTheme = {
  id: "clean",
  name: "Clean",
  card: "rounded-xl border border-slate-200 bg-white shadow-sm",
  title: "text-sm font-semibold text-slate-900",
  subtitle: "mt-0.5 text-xs text-slate-500",
  bundleTitle: "text-sm font-semibold text-slate-900",
  bundleSubtitle: "mt-0.5 text-xs text-slate-500",
  footnote: "text-[0.7rem] text-slate-400",
  footnoteBorder: "border-t border-slate-100",
  chartColors: ["#0f766e", "#1d4ed8", "#b45309", "#7c3aed", "#be123c"],
  kpiValue: "text-3xl font-semibold tabular-nums text-slate-900",
  compareLabel: "text-sm text-slate-500",
  compareValue: "text-lg font-semibold tabular-nums text-slate-900",
  compareTrack: "bg-slate-100",
  compareDelta: "text-xs text-slate-500",
  tableHeader: "text-right font-medium text-slate-500",
  tableHeaderBorder: "border-b border-slate-200",
  tableCell: "text-slate-700",
  tableCellBorder: "border-b border-slate-100",
  noteText: "text-sm leading-relaxed text-slate-600",
  legendLabel: "text-slate-500",
  legendValue: "font-medium tabular-nums text-slate-900",
  legendDot: "",
  gridColor: "#e2e8f0",
  axisTickColor: "#94a3b8",
  tooltipBg: "#ffffff",
  tooltipText: "#1e293b",
  tooltipBorder: "#e2e8f0",
};

/* ── Theme 2: Warm ── */
export const THEME_WARM: WidgetTheme = {
  id: "warm",
  name: "Warm",
  card: "rounded-2xl border border-orange-200/50 bg-orange-50/40 shadow-[0_1px_8px_rgba(180,130,60,0.06)]",
  title: "text-sm font-semibold text-amber-950",
  subtitle: "mt-0.5 text-xs text-amber-700/60",
  bundleTitle: "text-sm font-semibold text-amber-950",
  bundleSubtitle: "mt-0.5 text-xs text-amber-700/60",
  footnote: "text-[0.7rem] text-amber-700/50",
  footnoteBorder: "border-t border-orange-200/40",
  chartColors: ["#c2410c", "#65a30d", "#b45309", "#9f1239", "#78716c"],
  kpiValue: "text-3xl font-semibold tabular-nums text-amber-950",
  compareLabel: "text-sm text-amber-800/60",
  compareValue: "text-lg font-semibold tabular-nums text-amber-950",
  compareTrack: "bg-orange-100/60",
  compareDelta: "text-xs text-amber-700/60",
  tableHeader: "text-right font-medium text-amber-800/60",
  tableHeaderBorder: "border-b border-orange-200/50",
  tableCell: "text-amber-950/80",
  tableCellBorder: "border-b border-orange-100/50",
  noteText: "text-sm leading-relaxed text-amber-900/70",
  legendLabel: "text-amber-800/60",
  legendValue: "font-medium tabular-nums text-amber-950",
  legendDot: "",
  gridColor: "#fed7aa50",
  axisTickColor: "#92400e80",
  tooltipBg: "#fffbeb",
  tooltipText: "#78350f",
  tooltipBorder: "#fde68a",
};

/* ── Theme 3: Midnight ── */
export const THEME_MIDNIGHT: WidgetTheme = {
  id: "midnight",
  name: "Midnight",
  card: "rounded-xl border border-slate-700/60 bg-slate-800 shadow-lg shadow-black/20",
  title: "text-sm font-semibold text-slate-100",
  subtitle: "mt-0.5 text-xs text-slate-400",
  bundleTitle: "text-sm font-semibold text-slate-100",
  bundleSubtitle: "mt-0.5 text-xs text-slate-400",
  footnote: "text-[0.7rem] text-slate-500",
  footnoteBorder: "border-t border-slate-700/50",
  chartColors: ["#22d3ee", "#34d399", "#fbbf24", "#f472b6", "#a78bfa"],
  kpiValue: "text-3xl font-semibold tabular-nums text-white",
  compareLabel: "text-sm text-slate-400",
  compareValue: "text-lg font-semibold tabular-nums text-white",
  compareTrack: "bg-slate-700",
  compareDelta: "text-xs text-slate-500",
  tableHeader: "text-right font-medium text-slate-400",
  tableHeaderBorder: "border-b border-slate-700",
  tableCell: "text-slate-300",
  tableCellBorder: "border-b border-slate-700/50",
  noteText: "text-sm leading-relaxed text-slate-300",
  legendLabel: "text-slate-400",
  legendValue: "font-medium tabular-nums text-slate-100",
  legendDot: "",
  gridColor: "#334155",
  axisTickColor: "#64748b",
  tooltipBg: "#1e293b",
  tooltipText: "#f1f5f9",
  tooltipBorder: "#334155",
};

/* ── Theme 4: Ink ── */
export const THEME_INK: WidgetTheme = {
  id: "ink",
  name: "Ink",
  card: "rounded-none border border-slate-200 bg-transparent",
  title: "text-[11px] font-bold uppercase tracking-[0.08em] text-slate-900",
  subtitle: "mt-1 text-xs text-slate-400",
  bundleTitle: "text-[11px] font-bold uppercase tracking-[0.08em] text-slate-900",
  bundleSubtitle: "mt-1 text-xs text-slate-400",
  footnote: "text-[0.65rem] text-slate-400",
  footnoteBorder: "border-t border-slate-200",
  chartColors: ["#1e3a5f", "#2d5f8a", "#4b8bbe", "#7ab8e0", "#b0d4f1"],
  kpiValue: "text-4xl font-light tabular-nums text-slate-900",
  compareLabel: "text-xs uppercase tracking-wider text-slate-400",
  compareValue: "text-lg font-light tabular-nums text-slate-900",
  compareTrack: "bg-slate-100",
  compareDelta: "text-xs text-slate-400",
  tableHeader: "text-right text-[10px] font-bold uppercase tracking-wider text-slate-400",
  tableHeaderBorder: "border-b-2 border-slate-900",
  tableCell: "text-slate-700",
  tableCellBorder: "border-b border-slate-100",
  noteText: "text-sm leading-relaxed text-slate-500 italic",
  legendLabel: "text-slate-400",
  legendValue: "font-light tabular-nums text-slate-900",
  legendDot: "",
  gridColor: "#f1f5f9",
  axisTickColor: "#94a3b8",
  tooltipBg: "#ffffff",
  tooltipText: "#0f172a",
  tooltipBorder: "#e2e8f0",
};

/* ── Theme 5: Soft ── */
export const THEME_SOFT: WidgetTheme = {
  id: "soft",
  name: "Soft",
  card: "rounded-2xl border border-violet-100 bg-gradient-to-b from-white to-violet-50/30 shadow-[0_2px_16px_rgba(139,92,246,0.06)]",
  title: "text-sm font-semibold text-violet-950",
  subtitle: "mt-0.5 text-xs text-violet-400",
  bundleTitle: "text-sm font-semibold text-violet-950",
  bundleSubtitle: "mt-0.5 text-xs text-violet-400",
  footnote: "text-[0.7rem] text-violet-400",
  footnoteBorder: "border-t border-violet-100",
  chartColors: ["#7c3aed", "#0ea5e9", "#10b981", "#f472b6", "#f59e0b"],
  kpiValue: "text-3xl font-semibold tabular-nums text-violet-950",
  compareLabel: "text-sm text-violet-400",
  compareValue: "text-lg font-semibold tabular-nums text-violet-950",
  compareTrack: "bg-violet-100/60",
  compareDelta: "text-xs text-violet-400",
  tableHeader: "text-right font-medium text-violet-400",
  tableHeaderBorder: "border-b border-violet-200/60",
  tableCell: "text-violet-900/80",
  tableCellBorder: "border-b border-violet-100/50",
  noteText: "text-sm leading-relaxed text-violet-700/70",
  legendLabel: "text-violet-400",
  legendValue: "font-medium tabular-nums text-violet-950",
  legendDot: "",
  gridColor: "#ede9fe50",
  axisTickColor: "#8b5cf680",
  tooltipBg: "#faf5ff",
  tooltipText: "#4c1d95",
  tooltipBorder: "#ddd6fe",
};

export const ALL_THEMES: WidgetTheme[] = [
  THEME_CLEAN,
  THEME_WARM,
  THEME_MIDNIGHT,
  THEME_INK,
  THEME_SOFT,
];

/* ── Context ── */
export const DEFAULT_WIDGET_THEME = THEME_INK;

const ThemeContext = createContext<WidgetTheme>(DEFAULT_WIDGET_THEME);

export const WidgetThemeProvider = ThemeContext.Provider;

export function useWidgetTheme(): WidgetTheme {
  return useContext(ThemeContext);
}
