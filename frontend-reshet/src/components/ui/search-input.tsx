"use client"

import * as React from "react"
import { Search } from "lucide-react"

import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

type SearchInputProps = Omit<React.ComponentProps<typeof Input>, "type" | "size"> & {
  wrapperClassName?: string
  iconClassName?: string
  iconPosition?: "left" | "right"
  size?: "sm" | "md"
}

const sizeClasses = {
  sm: {
    input: "h-8 text-sm",
    icon: "h-3.5 w-3.5",
    leftPadding: "pl-8",
    rightPadding: "pr-8",
  },
  md: {
    input: "h-9 text-sm",
    icon: "h-4 w-4",
    leftPadding: "pl-9",
    rightPadding: "pr-9",
  },
} as const

export const SearchInput = React.forwardRef<HTMLInputElement, SearchInputProps>(
  (
    {
      className,
      wrapperClassName,
      iconClassName,
      iconPosition = "left",
      size = "sm",
      ...props
    },
    ref
  ) => {
    const config = sizeClasses[size]

    return (
      <div className={cn("relative", wrapperClassName)}>
        <Search
          className={cn(
            "pointer-events-none absolute top-1/2 -translate-y-1/2 text-muted-foreground/60",
            config.icon,
            iconPosition === "left" ? "left-2.5" : "right-2.5",
            iconClassName
          )}
        />
        <Input
          ref={ref}
          type="search"
          className={cn(
            "border-border/50 bg-muted/30 shadow-none placeholder:text-muted-foreground/50",
            config.input,
            iconPosition === "left" ? config.leftPadding : config.rightPadding,
            className
          )}
          {...props}
        />
      </div>
    )
  }
)

SearchInput.displayName = "SearchInput"
