"use client"

import { useCallback } from "react"
import Editor, { OnMount } from "@monaco-editor/react"
import { useTheme } from "next-themes"
import { cn } from "@/lib/utils"

interface CodeEditorProps {
    value: string
    onChange: (value: string) => void
    language?: string
    height?: string | number
    className?: string
    readOnly?: boolean
    framed?: boolean
    suppressValidationDecorations?: boolean
}

export function CodeEditor({
    value,
    onChange,
    language = "python",
    height = "100%",
    className,
    readOnly = false,
    framed = true,
    suppressValidationDecorations = false,
}: CodeEditorProps) {
    const { resolvedTheme } = useTheme()

    const handleMount: OnMount = useCallback((editor) => {
        // Focus the editor when it mounts
        editor.focus()
    }, [])

    const monacoTheme = resolvedTheme === "dark" ? "vs-dark" : "vs"

    return (
        <div className={cn("relative overflow-hidden", framed && "rounded-md border", className)}>
            <Editor
                height={height}
                language={language}
                value={value}
                onChange={(val) => onChange(val || "")}
                onMount={handleMount}
                theme={monacoTheme}
                options={{
                    minimap: { enabled: false },
                    fontSize: 13,
                    fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
                    lineNumbers: "on",
                    scrollBeyondLastLine: false,
                    wordWrap: "on",
                    automaticLayout: true,
                    tabSize: 4,
                    insertSpaces: true,
                    readOnly,
                    padding: { top: 12, bottom: 12 },
                    renderLineHighlight: "line",
                    cursorBlinking: "smooth",
                    folding: true,
                    bracketPairColorization: { enabled: true },
                    renderValidationDecorations: suppressValidationDecorations ? "off" : "on",
                }}
            />
        </div>
    )
}
