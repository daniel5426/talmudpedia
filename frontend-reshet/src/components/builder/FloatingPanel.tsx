"use client"

import React from "react"
import { cn } from "@/lib/utils"

interface FloatingPanelProps {
    children: React.ReactNode
    position: "left" | "right"
    visible: boolean
    className?: string
    fullHeight?: boolean
    autoHeight?: boolean
    offset?: number
}

/**
 * Reusable floating panel container for builder UIs.
 * Used for catalogs (left) and config panels (right).
 */
export function FloatingPanel({
    children,
    position,
    visible,
    fullHeight = false,
    autoHeight = false,
    offset = 0,
    className
}: FloatingPanelProps) {
    // Simplified translation logic for inline styles
    // We add an extra 100px to ensure it's fully off-screen even with shadows
    const translation = visible
        ? "translateX(0)"
        : position === "left"
            ? `translateX(calc(-100% - ${offset + 100}px))`
            : `translateX(calc(100% + ${offset + 100}px))`;

    const style: React.CSSProperties = {
        [position]: fullHeight ? `${offset}px` : `${12 + offset}px`,
        top: fullHeight ? "0" : "0.75rem",
        bottom: autoHeight ? "auto" : (fullHeight ? "0" : "0.75rem"),
        maxHeight: autoHeight ? "calc(100% - 24px)" : undefined,
        transform: translation,
        opacity: visible ? 1 : 0,
        pointerEvents: visible ? "auto" : "none",
    }

    return (
        <div
            className={cn(
                "absolute transition-all duration-500 ease-in-out",
                !fullHeight && !autoHeight && "h-[calc(100%-24px)]",
                fullHeight && "h-full",
                autoHeight && "h-auto",
                className
            )}
            style={style}
        >
            <div className={cn(
                "relative bg-background/95 backdrop-blur-md flex flex-col overflow-hidden h-full",
                !fullHeight ? "rounded-2xl border" : "border-l",
                autoHeight && "h-auto"
            )}>
                {children}
            </div>
        </div>
    )
}
