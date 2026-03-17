"use client"

import React, { useMemo } from "react"
import CodeMirror from "@uiw/react-codemirror"
import { json } from "@codemirror/lang-json"
import { oneDark } from "@codemirror/theme-one-dark"
import { useTheme } from "next-themes"
import { cn } from "@/lib/utils"

interface JsonViewerProps {
    value: unknown
    height?: string
    maxHeight?: string
    className?: string
    fontSize?: "xs" | "sm" | "base"
}

// Collapse large flat arrays so schema payloads stay readable in a compact viewer.
function truncateLargeArrays(obj: unknown, maxItems: number = 5): unknown {
    if (Array.isArray(obj)) {
        const isFlat = obj.every(item =>
            typeof item === "number" ||
            typeof item === "string" ||
            typeof item === "boolean" ||
            item === null
        )

        if (isFlat && obj.length > maxItems) {
            return [...obj.slice(0, maxItems), `...${obj.length - maxItems} more items`]
        }

        return obj.map(item => truncateLargeArrays(item, maxItems))
    }

    if (obj !== null && typeof obj === "object") {
        const result: Record<string, unknown> = {}
        for (const [key, val] of Object.entries(obj)) {
            result[key] = truncateLargeArrays(val, maxItems)
        }
        return result
    }

    return obj
}

export function JsonViewer({
    value,
    height,
    maxHeight = "400px",
    className,
    fontSize = "xs",
}: JsonViewerProps) {
    const { resolvedTheme } = useTheme()

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

    return (
        <div
            className={cn(
                "json-viewer rounded-md overflow-hidden w-full",
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
                extensions={[json()]}
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
