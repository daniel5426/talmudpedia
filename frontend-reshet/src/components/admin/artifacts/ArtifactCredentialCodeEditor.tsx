"use client"

import { useCallback, useEffect, useRef } from "react"
import Editor, { type Monaco, OnMount } from "@monaco-editor/react"
import { useTheme } from "next-themes"
import { IntegrationCredential } from "@/services"
import type { ArtifactLanguage } from "@/services/artifacts"
import { buildCredentialMentionToken } from "@/lib/credential-mentions"
import { cn } from "@/lib/utils"

interface ArtifactCredentialCodeEditorProps {
  value: string
  onChange: (value: string) => void
  language: ArtifactLanguage
  credentials: IntegrationCredential[]
  height?: string | number
  className?: string
  onScroll?: (isScrolled: boolean) => void
}

function getMentionQuery(line: string, column: number): { query: string; fromColumn: number; toColumn: number } | null {
  const prefix = line.slice(0, Math.max(0, column - 1))
  const atIndex = prefix.lastIndexOf("@")
  if (atIndex < 0) return null
  const previousChar = atIndex > 0 ? prefix[atIndex - 1] : ""
  if (/[A-Za-z0-9_]/.test(previousChar)) return null
  const query = prefix.slice(atIndex + 1)
  if (/[\s"'`)\]}]/.test(query)) return null
  return { query: query.trim().toLowerCase(), fromColumn: atIndex + 1, toColumn: column }
}

export function ArtifactCredentialCodeEditor({
  value,
  onChange,
  language,
  credentials,
  height = "100%",
  className,
  onScroll,
}: ArtifactCredentialCodeEditorProps) {
  const { resolvedTheme } = useTheme()
  const credentialsRef = useRef(credentials)
  const completionDisposablesRef = useRef<Array<{ dispose: () => void }>>([])

  useEffect(() => {
    credentialsRef.current = credentials
  }, [credentials])

  useEffect(() => {
    return () => {
      completionDisposablesRef.current.forEach((item) => item.dispose())
      completionDisposablesRef.current = []
    }
  }, [])

  const editorLanguage = language === "javascript" ? "typescript" : "python"

  const buildCompletionProvider = useCallback((monaco: Monaco) => ({
    triggerCharacters: ["@"],
    provideCompletionItems(
      model: Parameters<Monaco["languages"]["registerCompletionItemProvider"]>[1]["provideCompletionItems"] extends (model: infer TModel, position: infer TPosition, ...args: never[]) => unknown ? TModel : never,
      position: Parameters<Monaco["languages"]["registerCompletionItemProvider"]>[1]["provideCompletionItems"] extends (model: never, position: infer TPosition, ...args: never[]) => unknown ? TPosition : never,
    ) {
      const query = getMentionQuery(model.getLineContent(position.lineNumber), position.column)
      if (!query) {
        return { suggestions: [] }
      }
      const normalizedQuery = query.query
      const matches = credentialsRef.current
        .filter((credential) => credential.is_enabled)
        .filter((credential) => {
          if (!normalizedQuery) return true
          const haystack = `${credential.display_name} ${credential.provider_key} ${credential.category}`.toLowerCase()
          return haystack.includes(normalizedQuery)
        })
        .slice(0, 12)

      return {
        suggestions: matches.map((credential) => ({
          label: `@${credential.display_name}`,
          kind: monaco.languages.CompletionItemKind.Reference,
          insertText: buildCredentialMentionToken(credential),
          range: new monaco.Range(position.lineNumber, query.fromColumn, position.lineNumber, query.toColumn),
          detail: `${credential.category} • ${credential.provider_key}`,
          documentation: "Use only as an exact string literal value. The runtime rewrites it to a context.credentials lookup.",
        })),
      }
    },
  }), [])

  const handleMount: OnMount = useCallback((editor, monaco) => {
    editor.focus()
    if (onScroll) {
      editor.onDidScrollChange((event) => onScroll(event.scrollTop > 0))
    }

    completionDisposablesRef.current.forEach((item) => item.dispose())
    completionDisposablesRef.current = [
      monaco.languages.registerCompletionItemProvider("python", buildCompletionProvider(monaco)),
      monaco.languages.registerCompletionItemProvider("javascript", buildCompletionProvider(monaco)),
      monaco.languages.registerCompletionItemProvider("typescript", buildCompletionProvider(monaco)),
    ]
  }, [buildCompletionProvider, onScroll])

  return (
    <div className={cn("relative overflow-hidden rounded-md", className)}>
      <Editor
        height={height}
        language={editorLanguage}
        value={value}
        onChange={(nextValue) => onChange(nextValue || "")}
        onMount={handleMount}
        theme={resolvedTheme === "dark" ? "vs-dark" : "vs"}
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
          padding: { top: 12, bottom: 12 },
          renderLineHighlight: "line",
          cursorBlinking: "smooth",
          folding: true,
          bracketPairColorization: { enabled: true },
          overviewRulerBorder: false,
        }}
      />
    </div>
  )
}
