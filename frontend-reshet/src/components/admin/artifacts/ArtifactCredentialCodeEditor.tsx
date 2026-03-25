"use client"

import { useCallback, useEffect, useRef } from "react"
import Editor, { type Monaco, OnMount } from "@monaco-editor/react"
import { useTheme } from "next-themes"
import ts from "typescript"
import { IntegrationCredential } from "@/services"
import { artifactsService, ArtifactSourceFile } from "@/services/artifacts"
import { buildCredentialMentionToken } from "@/lib/credential-mentions"
import { cn } from "@/lib/utils"

type ArtifactEditorLanguage = "python" | "javascript" | "typescript"

const ARTIFACT_DEP_MARKER_OWNER = "artifact-dependencies"
const ARTIFACT_SYNTAX_MARKER_OWNER = "artifact-syntax"

interface ArtifactCredentialCodeEditorProps {
  value: string
  onChange: (value: string) => void
  editorLanguage: ArtifactEditorLanguage
  sourceFiles?: ArtifactSourceFile[]
  activeFilePath?: string
  tenantSlug?: string
  dependencies?: string
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
  editorLanguage,
  sourceFiles = [],
  activeFilePath,
  tenantSlug,
  dependencies = "",
  credentials,
  height = "100%",
  className,
  onScroll,
}: ArtifactCredentialCodeEditorProps) {
  const { resolvedTheme } = useTheme()
  const credentialsRef = useRef(credentials)
  const completionDisposablesRef = useRef<Array<{ dispose: () => void }>>([])
  const monacoRef = useRef<Monaco | null>(null)
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null)
  const pythonValidationTimerRef = useRef<number | null>(null)
  const pythonValidationSeqRef = useRef(0)

  useEffect(() => {
    credentialsRef.current = credentials
  }, [credentials])

  useEffect(() => {
    return () => {
      completionDisposablesRef.current.forEach((item) => item.dispose())
      completionDisposablesRef.current = []
      if (pythonValidationTimerRef.current) {
        window.clearTimeout(pythonValidationTimerRef.current)
      }
    }
  }, [])

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

  const configureJsRuntime = useCallback((monaco: Monaco) => {
    monaco.languages.typescript.javascriptDefaults.setCompilerOptions({
      allowJs: true,
      checkJs: true,
      module: monaco.languages.typescript.ModuleKind.ESNext,
      moduleResolution: monaco.languages.typescript.ModuleResolutionKind.NodeJs,
      allowSyntheticDefaultImports: true,
      esModuleInterop: true,
      noEmit: true,
    })

    const declaredDependencies = dependencies
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)

    const extraLibs = declaredDependencies.map((dependency, index) => ({
      content: [
        `declare module "${dependency}" {`,
        "  const value: any;",
        "  export default value;",
        "}",
      ].join("\n"),
      filePath: `file:///artifact-node_modules/${dependency}/index.d.ts#artifact-${index}`,
    }))

    monaco.languages.typescript.javascriptDefaults.setExtraLibs(extraLibs)
    monaco.languages.typescript.typescriptDefaults.setExtraLibs(extraLibs)
  }, [dependencies])

  const applyBackendValidationMarkers = useCallback(async (nextValue?: string) => {
    const monaco = monacoRef.current
    const editor = editorRef.current
    const model = editor?.getModel()
    if (!monaco || !model) return
    const filePath = String(activeFilePath || model.uri.path.split("/").pop() || "main.py")
    const currentValue = nextValue ?? model.getValue()
    const nextSourceFiles = (sourceFiles.length ? sourceFiles : [{ path: filePath, content: currentValue }]).map((file) =>
      file.path === filePath ? { ...file, content: currentValue } : file,
    )
    const seq = ++pythonValidationSeqRef.current
    try {
      const result = await artifactsService.validateSource(
        {
          language: editorLanguage === "python" ? "python" : "javascript",
          source_files: nextSourceFiles,
          dependencies: dependencies
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
        },
        tenantSlug,
      )
      if (seq !== pythonValidationSeqRef.current) return
      const fileDiagnostics = (result.diagnostics || []).filter((item) => item.path === filePath)
      const dependencyMarkers = fileDiagnostics
        .filter((item) => String(item.code || "").endsWith("MISSING_DEPENDENCY"))
        .map((item) => ({
          startLineNumber: item.line,
          startColumn: item.column,
          endLineNumber: item.end_line,
          endColumn: item.end_column,
          message: item.message,
          severity: monaco.MarkerSeverity.Error,
        }))
      monaco.editor.setModelMarkers(model, ARTIFACT_DEP_MARKER_OWNER, dependencyMarkers)
      if (editorLanguage === "python") {
        const syntaxMarkers = fileDiagnostics
          .filter((item) => item.code === "PYTHON_SYNTAX_ERROR")
          .map((item) => ({
            startLineNumber: item.line,
            startColumn: item.column,
            endLineNumber: item.end_line,
            endColumn: item.end_column,
            message: item.message,
            severity: monaco.MarkerSeverity.Error,
          }))
        monaco.editor.setModelMarkers(model, ARTIFACT_SYNTAX_MARKER_OWNER, syntaxMarkers)
      }
    } catch {
      if (seq !== pythonValidationSeqRef.current) return
    }
  }, [activeFilePath, dependencies, editorLanguage, sourceFiles, tenantSlug])

  const applyJsSyntaxMarkers = useCallback(() => {
    const monaco = monacoRef.current
    const editor = editorRef.current
    const model = editor?.getModel()
    if (!monaco || !model || editorLanguage === "python") return

    const sourceFile = ts.createSourceFile(
      editorLanguage === "typescript" ? "artifact.ts" : "artifact.js",
      model.getValue(),
      ts.ScriptTarget.Latest,
      true,
      editorLanguage === "typescript" ? ts.ScriptKind.TS : ts.ScriptKind.JS,
    )

    const markers = (sourceFile.parseDiagnostics || []).map((diagnostic) => {
      const start = diagnostic.start ?? 0
      const length = diagnostic.length ?? 1
      const startPos = model.getPositionAt(start)
      const endPos = model.getPositionAt(start + Math.max(length, 1))
      return {
        startLineNumber: startPos.lineNumber,
        startColumn: startPos.column,
        endLineNumber: endPos.lineNumber,
        endColumn: endPos.column,
        message: ts.flattenDiagnosticMessageText(diagnostic.messageText, "\n"),
        severity: monaco.MarkerSeverity.Error,
      }
    })
    monaco.editor.setModelMarkers(model, ARTIFACT_SYNTAX_MARKER_OWNER, markers)
  }, [editorLanguage])

  const handleMount: OnMount = useCallback((editor, monaco) => {
    monacoRef.current = monaco
    editorRef.current = editor
    editor.focus()
    if (onScroll) {
      editor.onDidScrollChange((event) => onScroll(event.scrollTop > 0))
    }

    configureJsRuntime(monaco)
    void applyBackendValidationMarkers()
    if (editorLanguage !== "python") {
      applyJsSyntaxMarkers()
    }

    completionDisposablesRef.current.forEach((item) => item.dispose())
    completionDisposablesRef.current = [
      monaco.languages.registerCompletionItemProvider("python", buildCompletionProvider(monaco)),
      monaco.languages.registerCompletionItemProvider("javascript", buildCompletionProvider(monaco)),
      monaco.languages.registerCompletionItemProvider("typescript", buildCompletionProvider(monaco)),
    ]
  }, [applyBackendValidationMarkers, applyJsSyntaxMarkers, buildCompletionProvider, configureJsRuntime, editorLanguage, onScroll])

  useEffect(() => {
    if (!monacoRef.current) return
    configureJsRuntime(monacoRef.current)
    void applyBackendValidationMarkers()
    if (editorLanguage !== "python") {
      applyJsSyntaxMarkers()
    }
  }, [applyBackendValidationMarkers, applyJsSyntaxMarkers, configureJsRuntime, editorLanguage, sourceFiles, tenantSlug])

  return (
    <div className={cn("relative overflow-hidden rounded-md", className)}>
      <Editor
        height={height}
        language={editorLanguage}
        value={value}
        onChange={(nextValue) => {
          onChange(nextValue || "")
          queueMicrotask(() => {
            if (editorLanguage !== "python") {
              applyJsSyntaxMarkers()
            }
            if (pythonValidationTimerRef.current) {
              window.clearTimeout(pythonValidationTimerRef.current)
            }
            pythonValidationTimerRef.current = window.setTimeout(() => {
              void applyBackendValidationMarkers(nextValue || "")
            }, 250)
          })
        }}
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
