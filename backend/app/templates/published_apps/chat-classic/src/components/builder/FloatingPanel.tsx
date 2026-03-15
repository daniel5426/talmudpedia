"use client";

import React from "react";

import { cn } from "@/lib/utils";

interface FloatingPanelProps {
  children: React.ReactNode;
  position: "left" | "right";
  visible: boolean;
  className?: string;
  fullHeight?: boolean;
  autoHeight?: boolean;
  offset?: number;
  background?: string;
  shadow?: string;
  border?: string;
}

export function FloatingPanel({
  children,
  position,
  visible,
  background = "bg-background/95",
  fullHeight = false,
  autoHeight = false,
  offset = 0,
  shadow = "shadow-xs",
  border = "border",
  className,
}: FloatingPanelProps) {
  const translation = visible
    ? "translateX(0)"
    : position === "left"
      ? `translateX(calc(-100% - ${offset + 100}px))`
      : `translateX(calc(100% + ${offset + 100}px))`;

  const style: React.CSSProperties = {
    [position]: fullHeight ? `${offset}px` : `${12 + offset}px`,
    top: fullHeight ? "0" : "0.75rem",
    bottom: autoHeight ? "auto" : fullHeight ? "0" : "0.75rem",
    maxHeight: autoHeight ? "calc(100% - 24px)" : undefined,
    transform: translation,
    opacity: visible ? 1 : 0,
    pointerEvents: visible ? "auto" : "none",
  };

  return (
    <div
      className={cn(
        "absolute transition-all duration-500 ease-in-out",
        !fullHeight && !autoHeight && "h-[calc(100%-24px)]",
        fullHeight && "h-full",
        autoHeight && "h-auto",
        className,
      )}
      style={style}
    >
      <div
        className={cn(
          "relative flex h-full flex-col overflow-hidden backdrop-blur-md",
          shadow,
          background,
          !fullHeight ? "rounded-2xl" : "",
          autoHeight && "h-auto",
          border,
        )}
      >
        {children}
      </div>
    </div>
  );
}
