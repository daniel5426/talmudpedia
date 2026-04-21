"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { ArtifactDependencyRow, ArtifactLanguage, ArtifactSourceFile, artifactsService } from "@/services/artifacts"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { cn } from "@/lib/utils"
import { Loader2, Plus, RotateCcw, Trash2 } from "lucide-react"

interface ArtifactDependencyTabProps {
  language: ArtifactLanguage
  sourceFiles: ArtifactSourceFile[]
  dependencies: string
  organizationId?: string
  onChangeDependencies: (nextValue: string) => void
}

function splitDeclaredDependencies(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
}

function joinDeclaredDependencies(items: string[]): string {
  return items.join(", ")
}

function sourceLabel(row: ArtifactDependencyRow): string {
  if (row.source === "builtin") return "Built-in"
  if (row.source === "runtime_registry") return "Runtime registry"
  if (row.source === "runtime_catalog") return "Pyodide catalog"
  return "Declared"
}

function statusClasses(status: string): string {
  if (status === "Built-in") return "bg-slate-100 text-slate-700 border-slate-200"
  if (status === "Runtime-provided") return "bg-emerald-50 text-emerald-700 border-emerald-200"
  if (status === "Runtime catalog") return "bg-teal-50 text-teal-700 border-teal-200"
  if (status === "Declaration required") return "bg-amber-50 text-amber-700 border-amber-200"
  if (status === "Declared") return "bg-blue-50 text-blue-700 border-blue-200"
  return "bg-muted text-muted-foreground border-border"
}

export function ArtifactDependencyTab({
  language,
  sourceFiles,
  dependencies,
  organizationId,
  onChangeDependencies,
}: ArtifactDependencyTabProps) {
  const [rows, setRows] = useState<ArtifactDependencyRow[]>([])
  const [loading, setLoading] = useState(false)
  const [query, setQuery] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const requestSeqRef = useRef(0)
  const declaredDependencies = useMemo(() => splitDeclaredDependencies(dependencies), [dependencies])

  const refreshRows = useCallback(async () => {
    const seq = ++requestSeqRef.current
    setLoading(true)
    try {
      const result = await artifactsService.analyzeDependencies(
        {
          language,
          source_files: sourceFiles,
          dependencies: declaredDependencies,
        },
        organizationId,
      )
      if (seq !== requestSeqRef.current) return
      setRows(result.rows || [])
    } catch (nextError) {
      if (seq !== requestSeqRef.current) return
      setError(nextError instanceof Error ? nextError.message : "Failed to analyze dependencies")
      setRows([])
    } finally {
      if (seq === requestSeqRef.current) {
        setLoading(false)
      }
    }
  }, [declaredDependencies, language, sourceFiles, organizationId])

  useEffect(() => {
    void refreshRows()
  }, [refreshRows])

  const upsertDeclaredDependency = useCallback((nextDependency: string) => {
    const trimmed = nextDependency.trim()
    if (!trimmed) return
    if (declaredDependencies.some((item) => item.toLowerCase() === trimmed.toLowerCase())) {
      setError(`Dependency \`${trimmed}\` is already declared.`)
      return
    }
    onChangeDependencies(joinDeclaredDependencies([...declaredDependencies, trimmed]))
    setError(null)
  }, [declaredDependencies, onChangeDependencies])

  const handleAdd = useCallback(async () => {
    const trimmed = query.trim()
    if (!trimmed) {
      setError("Enter a dependency name.")
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      if (language === "python") {
        const verification = await artifactsService.verifyPythonPackage({ package_name: trimmed }, organizationId)
        if (!verification.exists) {
          setError(verification.error_message || (verification.status === "not_found" ? "PyPI package not found." : "Dependency verification failed."))
          return
        }
        upsertDeclaredDependency(verification.normalized_name || trimmed)
      } else {
        upsertDeclaredDependency(trimmed)
      }
      setQuery("")
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Dependency verification failed.")
    } finally {
      setSubmitting(false)
    }
  }, [language, query, organizationId, upsertDeclaredDependency])

  const handleRemove = useCallback((row: ArtifactDependencyRow) => {
    const next = declaredDependencies.filter((item) => item.toLowerCase() !== String(row.declared_spec || row.normalized_name).toLowerCase())
    onChangeDependencies(joinDeclaredDependencies(next))
    setError(null)
  }, [declaredDependencies, onChangeDependencies])

  const handleAddFromRow = useCallback((row: ArtifactDependencyRow) => {
    upsertDeclaredDependency(row.normalized_name)
  }, [upsertDeclaredDependency])

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-border/50 bg-muted/10 p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center">
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={language === "python" ? "Add Python package from PyPI" : "Add package name"}
            className="font-mono"
          />
          <div className="flex items-center gap-2">
            <Button type="button" onClick={() => void handleAdd()} disabled={submitting} className="gap-2">
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Add dependency
            </Button>
            <Button type="button" variant="ghost" onClick={() => void refreshRows()} disabled={loading} className="gap-2">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
              Refresh
            </Button>
          </div>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          {language === "python"
            ? "Python additions are verified against PyPI before they are saved."
            : "JS dependencies are added directly in this slice."}
        </p>
        {error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}
      </div>

      <div className="rounded-lg border border-border/50">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Notes</TableHead>
              <TableHead className="w-[140px] text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                  {loading ? "Analyzing dependencies..." : "No dependencies detected yet."}
                </TableCell>
              </TableRow>
            ) : rows.map((row) => (
              <TableRow key={`${row.normalized_name}:${row.declared_spec || ""}`}>
                <TableCell className="font-mono text-xs">
                  <div className="space-y-1">
                    <div>{row.declared_spec || row.name}</div>
                    {row.declared_spec && row.declared_spec !== row.name ? (
                      <div className="text-[11px] text-muted-foreground">module: {row.name}</div>
                    ) : null}
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className={cn("font-medium", statusClasses(row.status))}>
                    {row.status}
                  </Badge>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">{sourceLabel(row)}</TableCell>
                <TableCell className="max-w-[360px] whitespace-normal text-sm text-muted-foreground">
                  {row.note || "—"}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    {row.can_add ? (
                      <Button type="button" variant="ghost" size="sm" onClick={() => handleAddFromRow(row)}>
                        Add
                      </Button>
                    ) : null}
                    {row.can_remove ? (
                      <Button type="button" variant="ghost" size="sm" className="gap-1 text-destructive hover:text-destructive" onClick={() => handleRemove(row)}>
                        <Trash2 className="h-3.5 w-3.5" />
                        Remove
                      </Button>
                    ) : null}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
