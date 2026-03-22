"use client"

import React, { useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"

interface FloatingPanelProps {
    children: React.ReactNode
    position: "left" | "right"
    visible: boolean
    className?: string
    fullHeight?: boolean
    autoHeight?: boolean
    offset?: number
    background?: string
    shadow?: string
    border?: string
}

/**
 * Reusable floating panel container for builder UIs.
 * Used for catalogs (left) and config panels (right).
 */
export function FloatingPanel({
    children,
    position,
    visible,
    background = "bg-background/95",
    fullHeight = false,
    autoHeight = false,
    offset = 0,
    shadow = "shadow-xs",
    border = "border-[0.5px]",
    className
}: FloatingPanelProps) {
    const sizerRef = useRef<HTMLDivElement>(null)
    const [animatedHeight, setAnimatedHeight] = useState<number | undefined>(undefined)

    useEffect(() => {
        if (!autoHeight || !sizerRef.current) return
        const ro = new ResizeObserver((entries) => {
            const entry = entries[0]
            if (entry) {
                const h = entry.borderBoxSize?.[0]?.blockSize ?? entry.contentRect.height
                setAnimatedHeight(h)
            }
        })
        ro.observe(sizerRef.current)
        return () => ro.disconnect()
    }, [autoHeight])

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
            <div
                className={cn(
                    "relative backdrop-blur-md flex flex-col overflow-hidden",
                    autoHeight && "transition-[height] duration-300 ease-in-out",
                    shadow,
                    background,
                    !fullHeight ? "rounded-2xl" : "",
                    !autoHeight && "h-full",
                    border
                )}
                style={autoHeight && animatedHeight != null ? { height: `${animatedHeight}px` } : undefined}
            >
                {autoHeight ? (
                    <div ref={sizerRef}>{children}</div>
                ) : (
                    children
                )}
            </div>
        </div>
    )
}
