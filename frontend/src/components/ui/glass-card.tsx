import * as React from "react"
import { cn } from "@/lib/utils"

export interface GlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "header" | "interactive" | "matte" | "matte_dark" | "no_glass" | "no_border"
  children?: React.ReactNode
}

const GlassCard = React.forwardRef<HTMLDivElement, GlassCardProps>(
  ({ className, variant = "default", children, ...props }, ref) => {
    const variants = {
      default: "border border-white/30 dark:border-white/10 backdrop-blur-md bg-white/50 dark:bg-gray-900/70 shadow-2xl",
      header: "border border-white/30 dark:border-white/10 backdrop-blur-md bg-white/50 dark:bg-gray-900/70 shadow-2xl rounded-2xl",
      interactive: "border border-white/20 dark:border-white/10 backdrop-blur-md bg-white/10 dark:bg-gray-900/50 hover:bg-white/20 dark:hover:bg-gray-900/70 transition-all duration-300 cursor-pointer shadow-lg hover:shadow-2xl",
      matte: "border border-gray-300/40 dark:border-gray-700/40 backdrop-blur-sm bg-white/40 dark:bg-gray-900/50 ",
      matte_dark: "border text-white border-gray-700/40 backdrop-blur-sm bg-gray-900/50 ",
      no_glass: "border bg-background dark:border-white/10 rounded-sm",
      no_border: " hover:bg-accent bg-primary-foreground dark:border-white/10 rounded-sm",
    }

    return (
      <div
        ref={ref}
        className={cn(variants[variant], className, "cursor-pointer")}
        {...props}
      >
        {children}
      </div>
    )
  }
)
GlassCard.displayName = "GlassCard"

export { GlassCard }
