"use client"

import React from "react"
import CodeMirror from "@uiw/react-codemirror"
import { json } from "@codemirror/lang-json"
import { oneDark } from "@codemirror/theme-one-dark"
import { useTheme } from "next-themes"
import { cn } from "@/lib/utils"

interface JsonEditorProps {
    value: string
    onChange: (value: string) => void
    height?: string
    className?: string
    readOnly?: boolean
}

export function JsonEditor({
    value,
    onChange,
    height = "200px",
    className,
    readOnly = false,
}: JsonEditorProps) {
    const { resolvedTheme } = useTheme()

    return (
        <div className={cn("rounded-md border border-input overflow-hidden", className)}>
            <CodeMirror
                value={value}
                height={height}
                theme={resolvedTheme === "dark" ? oneDark : "light"}
                extensions={[json()]}
                onChange={(val) => onChange(val)}
                readOnly={readOnly}
                basicSetup={{
                    lineNumbers: true,
                    foldGutter: true,
                    dropCursor: true,
                    allowMultipleSelections: false,
                    indentOnInput: true,
                }}
                className="text-xs"
            />
        </div>
    )
}
