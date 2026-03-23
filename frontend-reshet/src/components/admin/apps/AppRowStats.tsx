"use client";

import { Skeleton } from "@/components/ui/skeleton";
import type { PublishedAppStatsSummary } from "@/services/published-apps";

function formatCompact(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}m`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}

function MiniSparkline({
  data,
  color = "#8b5cf6",
  width = 92,
  height = 48,
}: {
  data: { date: string; value: number }[];
  color?: string;
  width?: number;
  height?: number;
}) {
  if (!data.length) return null;
  const max = Math.max(...data.map((d) => d.value));
  const gap = 2;
  const barWidth = Math.max(1, (width - (data.length - 1) * gap) / data.length);

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="shrink-0"
      aria-hidden
    >
      {data.map((d, i) => {
        const barHeight = max > 0 ? Math.max(1, (d.value / max) * height) : 1;
        return (
          <rect
            key={i}
            x={i * (barWidth + gap)}
            y={height - barHeight}
            width={barWidth}
            height={barHeight}
            rx={0.5}
            fill={color}
            opacity={0.8}
          >
            <title>{`${d.date}: ${d.value.toLocaleString()}`}</title>
          </rect>
        );
      })}
    </svg>
  );
}

function StatUnit({
  label,
  value,
  dimmed,
}: {
  label: string;
  value: string | number;
  dimmed?: boolean;
}) {
  return (
    <span className="flex self-end items-end gap-1 whitespace-nowrap leading-none">
      <span className="text-[24px] leading-none tabular-nums text-foreground/80">
        {value}
      </span>
      <span
        className={`text-[12px] leading-none ${
          dimmed ? "text-muted-foreground/40" : "text-muted-foreground/50"
        }`}
      >
        {label}
      </span>
    </span>
  );
}

export function AppRowStatsSkeleton() {
  return (
    <div className="hidden items-end gap-3 xl:flex">
      <Skeleton className="h-3 w-10" />
      <Skeleton className="h-3 w-[52px]" />
      <Skeleton className="h-3 w-10" />
      <Skeleton className="h-3 w-[52px]" />
      <Skeleton className="h-3 w-10" />
      <Skeleton className="h-3 w-[52px]" />
      <Skeleton className="h-3 w-8" />
    </div>
  );
}

export function AppRowStatsEmpty() {
  return (
    <div className="hidden items-end xl:flex">
      <span className="text-[11px] text-muted-foreground/35"></span>
    </div>
  );
}

export function AppRowStats({
  stats,
  approximate,
}: {
  stats: PublishedAppStatsSummary;
  approximate?: boolean;
}) {
  const hasAnyActivity =
    stats.visits > 0 ||
    stats.agent_runs > 0 ||
    stats.tokens > 0;

  if (!hasAnyActivity) {
    return <AppRowStatsEmpty />;
  }

  return (
    <div
      className="hidden items-end gap-4 xl:flex"
      title={approximate ? "Stats are approximate" : undefined}
    >
      <StatUnit label="visits" value={formatCompact(stats.visits)} />
      <MiniSparkline data={stats.visits_by_day} color="#8b5cf6" />

      <span className="self-end leading-none text-muted-foreground/20">·</span>

      <StatUnit label="runs" value={formatCompact(stats.agent_runs)} />
      {stats.failed_runs > 0 && (
        <span className="self-end text-[11px] leading-none tabular-nums text-red-400/70">
          {stats.failed_runs}f
        </span>
      )}
      <MiniSparkline data={stats.runs_by_day} color="#3b82f6" />

      <span className="self-end leading-none text-muted-foreground/20">·</span>

      <StatUnit label="tok" value={formatCompact(stats.tokens)} />
      <MiniSparkline data={stats.tokens_by_day} color="#10b981" />

      <span className="self-end leading-none text-muted-foreground/20">·</span>

      <StatUnit label="acct" value={formatCompact(stats.app_accounts)} dimmed />

      {approximate && (
        <span className="self-end text-[10px] leading-none text-muted-foreground/30" title="Approximate values">
          ~
        </span>
      )}
    </div>
  );
}
