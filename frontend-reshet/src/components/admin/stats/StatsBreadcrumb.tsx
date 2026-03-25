"use client"

import { cn } from "@/lib/utils"

export function StatsBreadcrumb({
  items,
}: {
  items: Array<{ label: string; onClick?: () => void; active?: boolean }>;
}) {
  if (!items.length) return null

  return (
    <nav className="max-w-full min-w-0 text-2xl font-semibold tracking-tight">
      <ol className="flex min-w-0 max-w-full items-center gap-2">
        {items.map((item, index) => (
          <li key={`${item.label}-${index}`} className="flex min-w-0 max-w-full items-center gap-2">
            {item.onClick ? (
              <button
                type="button"
                onClick={item.onClick}
                className={cn(
                  "max-w-[12rem] truncate transition-colors hover:text-foreground sm:max-w-[18rem] md:max-w-[24rem]",
                  item.active && "text-foreground font-medium"
                )}
                title={item.label}
              >
                {item.label}
              </button>
            ) : (
              <span
                className={cn(
                  "block max-w-[12rem] truncate sm:max-w-[18rem] md:max-w-[24rem]",
                  item.active && "text-foreground font-medium"
                )}
                title={item.label}
              >
                {item.label}
              </span>
            )}
            {index < items.length - 1 && <span className="text-muted-foreground">/</span>}
          </li>
        ))}
      </ol>
    </nav>
  )
}
