"use client";

import { cn } from "@/lib/utils";
import { type ElementType, memo } from "react";

export type TextShimmerProps = {
  children: string;
  as?: ElementType;
  className?: string;
  duration?: number;
  spread?: number;
};

const ShimmerComponent = ({
  children,
  as: Component = "p",
  className,
  duration = 2,
}: TextShimmerProps) => {
  return (
    <Component
      className={cn(
        "relative inline-block bg-clip-text text-transparent",
        "bg-[length:200%_100%,auto] [background-repeat:no-repeat,padding-box] animate-pulse",
        className
      )}
      style={{
        animationDuration: `${duration}s`,
        backgroundImage:
          "linear-gradient(90deg, transparent, var(--panel, #fff), transparent), linear-gradient(var(--muted, #5a6b85), var(--muted, #5a6b85))",
      }}
    >
      {children}
    </Component>
  );
};

export const Shimmer = memo(ShimmerComponent);
