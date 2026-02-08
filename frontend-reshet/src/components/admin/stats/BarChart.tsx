"use client"

import { cn } from "@/lib/utils"
import type { DailyDataPoint } from "@/services"

export function BarChart({
  data,
  height = 180,
  color = "#8b5cf6",
  showLabels = true,
  className,
}: {
  data: DailyDataPoint[];
  height?: number;
  color?: string;
  showLabels?: boolean;
  className?: string;
}) {
  if (!data.length) return <div className="text-sm text-muted-foreground">No data</div>

  const maxValue = Math.max(...data.map((d) => d.value))
  const minLabel = data[0]?.date
  const maxLabel = data[data.length - 1]?.date

  return (
    <div className={cn("w-full min-w-0", className)}>
      <div className="flex items-end gap-[3px] w-full overflow-hidden" style={{ height }}>
        {data.map((d, i) => (
          <div
            key={i}
            className="flex-1 min-w-0 rounded-sm transition-all hover:opacity-80"
            style={{
              height: `${Math.max((d.value / (maxValue || 1)) * 100, 2)}%`,
              backgroundColor: color,
            }}
          />
        ))}
      </div>
      {showLabels && (
        <div className="flex justify-between mt-2 text-[11px] text-muted-foreground">
          <span>{minLabel}</span>
          <span>{maxLabel}</span>
        </div>
      )}
    </div>
  )
}
