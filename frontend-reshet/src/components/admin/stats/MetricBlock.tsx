"use client"

import type { DailyDataPoint } from "@/services"
import { cn } from "@/lib/utils"
import { BarChart } from "@/components/admin/stats/BarChart"

export function MetricBlock({
  title,
  value,
  subValue,
  icon: Icon,
  sparkline,
  onClick,
}: {
  title: string;
  value: string | number;
  subValue?: string;
  icon?: React.ComponentType<{ className?: string }>;
  sparkline?: DailyDataPoint[];
  onClick?: () => void;
}) {
  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "text-left border rounded-lg p-4 transition-all",
          "hover:border-muted-foreground/40 hover:shadow-sm",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
        )}
      >
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-muted-foreground">{title}</span>
          {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
        </div>
        <div className="text-2xl font-semibold">{value}</div>
        {subValue && <div className="text-sm text-muted-foreground mt-1">{subValue}</div>}
        {sparkline && sparkline.length > 0 && (
          <div className="mt-3">
            <BarChart data={sparkline} height={50} color="#8b5cf6" showLabels={false} />
          </div>
        )}
      </button>
    )
  }

  return (
    <div className={cn("text-left border rounded-lg p-4 transition-all")}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-muted-foreground">{title}</span>
        {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
      </div>
      <div className="text-2xl font-semibold">{value}</div>
      {subValue && <div className="text-sm text-muted-foreground mt-1">{subValue}</div>}
      {sparkline && sparkline.length > 0 && (
        <div className="mt-3">
          <BarChart data={sparkline} height={50} color="#8b5cf6" showLabels={false} />
        </div>
      )}
    </div>
  )
}
