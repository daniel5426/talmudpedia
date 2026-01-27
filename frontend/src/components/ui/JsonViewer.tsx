"use client"

import React, { useMemo } from "react"
import CodeMirror from "@uiw/react-codemirror"
import { json } from "@codemirror/lang-json"
import { oneDark } from "@codemirror/theme-one-dark"
import { EditorView } from "@codemirror/view"
import { useTheme } from "next-themes"
import { cn } from "@/lib/utils"

interface JsonViewerProps {
    value: unknown
    height?: string
    maxHeight?: string
    className?: string
    fontSize?: "xs" | "sm" | "base"
}

export function JsonViewer({
    value,
    height,
    maxHeight = "400px",
    className,
    fontSize = "xs",
}: JsonViewerProps) {
    const { resolvedTheme } = useTheme()

    // Recursively process JSON to truncate large primitive arrays
    const truncateLargeArrays = (obj: unknown, maxItems: number = 5): unknown => {
        if (Array.isArray(obj)) {
            // Check if it's a "flat" array (only contains primitives)
            const isFlat = obj.every(item =>
                typeof item === 'number' ||
                typeof item === 'string' ||
                typeof item === 'boolean' ||
                item === null
            )

            if (isFlat && obj.length > maxItems) {
                // Return truncated array with a marker
                return [...obj.slice(0, maxItems), `...${obj.length - maxItems} more items`]
            }

            // Recurse into non-flat arrays
            return obj.map(item => truncateLargeArrays(item, maxItems))
        }

        if (obj !== null && typeof obj === 'object') {
            const result: Record<string, unknown> = {}
            for (const [key, val] of Object.entries(obj)) {
                result[key] = truncateLargeArrays(val, maxItems)
            }
            return result
        }

        return obj
    }

    const jsonString = useMemo(() => {
        try {
            const processed = truncateLargeArrays(value)
            return JSON.stringify(processed, null, 2)
        } catch {
            return String(value)
        }
    }, [value])

    const fontSizeClass = {
        xs: "text-xs",
        sm: "text-sm",
        base: "text-base",
    }[fontSize]

    // Custom theme extension to show scrollbars and constrain width
    const scrollbarTheme = EditorView.theme({
        "&": {
            height: "100%",
            width: "100%",
            maxWidth: "100%",
        },
        ".cm-scroller": {
            overflow: "auto !important",
            scrollbarWidth: "thin",
            scrollbarColor: "var(--border) transparent",
        },
        ".cm-content": {
            minWidth: "0",
        },
        ".cm-scroller::-webkit-scrollbar": {
            width: "8px",
            height: "8px",
        },
        ".cm-scroller::-webkit-scrollbar-track": {
            background: "transparent",
        },
        ".cm-scroller::-webkit-scrollbar-thumb": {
            background: "var(--border)",
            borderRadius: "4px",
        },
        ".cm-scroller::-webkit-scrollbar-thumb:hover": {
            background: "var(--muted-foreground)",
        },
    })

    return (
        <div
            className={cn(
                "rounded-md overflow-hidden w-full",
                fontSizeClass,
                className
            )}
            style={{ maxHeight }}
        >
            <CodeMirror
                value={jsonString}
                height={height}
                maxHeight={maxHeight}
                theme={resolvedTheme === "dark" ? oneDark : "light"}
                extensions={[
                    json(),
                    scrollbarTheme,
                ]}
                readOnly={true}
                editable={false}
                basicSetup={{
                    lineNumbers: true,
                    foldGutter: true,
                    highlightActiveLine: false,
                    highlightSelectionMatches: false,
                    dropCursor: false,
                    allowMultipleSelections: false,
                    indentOnInput: false,
                    bracketMatching: true,
                }}
            />
        </div>
    )
}
