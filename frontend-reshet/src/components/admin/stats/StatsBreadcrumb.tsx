"use client"

import { cn } from "@/lib/utils"

export function StatsBreadcrumb({
  items,
}: {
  items: Array<{ label: string; onClick?: () => void; active?: boolean }>;
}) {
  if (!items.length) return null

  return (
    <nav className="text-2xl font-semibold tracking-tight">
      <ol className="flex items-center gap-2">
        {items.map((item, index) => (
          <li key={`${item.label}-${index}`} className="flex items-center gap-2">
            {item.onClick ? (
              <button
                type="button"
                onClick={item.onClick}
                className={cn(
                  "transition-colors hover:text-foreground",
                  item.active && "text-foreground font-medium"
                )}
              >
                {item.label}
              </button>
            ) : (
              <span className={cn(item.active && "text-foreground font-medium")}>{item.label}</span>
            )}
            {index < items.length - 1 && <span className="text-muted-foreground">/</span>}
          </li>
        ))}
      </ol>
    </nav>
  )
}
