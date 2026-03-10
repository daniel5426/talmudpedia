"use client"

import { useEffect, useRef, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { CodeEditor } from "@/components/ui/code-editor"
import { cn } from "@/lib/utils"
import {
  ArtifactRun,
  ArtifactRunEvent,
  artifactsService,
  ArtifactTestResponse,
} from "@/services/artifacts"
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Loader2,
  Play,
  Terminal,
  XCircle,
} from "lucide-react"

interface ArtifactTestPanelProps {
  tenantSlug?: string
  artifactId?: string
  pythonCode: string
  inputType: string
  outputType: string
}

const INITIAL_INPUT = '[\n  {\n    "text": "Hello world",\n    "metadata": {}\n  }\n]'
const INITIAL_CONFIG = "{\n  \n}"
const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"])

function formatPhase(event: ArtifactRunEvent | null): string {
  if (!event) return "Synthesizing execution environment..."
  const label = String(event.payload?.name || event.event_type || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase())
  return label || "Running artifact..."
}

function summarizeFailure(run: ArtifactRun | null): string {
  if (!run) return "Artifact test run failed"
  return (
    run.error_payload?.message ||
    run.stderr_excerpt ||
    run.stdout_excerpt ||
    "Artifact test run failed"
  )
}

export function ArtifactTestPanel({
  tenantSlug,
  artifactId,
  pythonCode,
  inputType,
  outputType,
}: ArtifactTestPanelProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [isTesting, setIsTesting] = useState(false)
  const [testTab, setTestTab] = useState("input")
  const [testInput, setTestInput] = useState(INITIAL_INPUT)
  const [testConfig, setTestConfig] = useState(INITIAL_CONFIG)
  const [runId, setRunId] = useState<string | null>(null)
  const [events, setEvents] = useState<ArtifactRunEvent[]>([])
  const [legacyResult, setLegacyResult] = useState<ArtifactTestResponse | null>(null)
  const pollTimerRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (pollTimerRef.current) {
        window.clearTimeout(pollTimerRef.current)
      }
    }
  }, [])

  useEffect(() => {
    if (!runId || !isTesting) return
    let cancelled = false

    const poll = async () => {
      try {
        const [nextRun, nextEvents] = await Promise.all([
          artifactsService.getRun(runId, tenantSlug),
          artifactsService.getRunEvents(runId, tenantSlug),
        ])
        if (cancelled) return
        setEvents(nextEvents.events)

        if (TERMINAL_STATUSES.has(nextRun.status)) {
          setIsTesting(false)
          setLegacyResult({
            success: nextRun.status === "completed",
            data: nextRun.result_payload,
            error_message: summarizeFailure(nextRun),
            execution_time_ms: nextRun.duration_ms || 0,
            run_id: nextRun.id,
            error_payload: nextRun.error_payload,
            stdout_excerpt: nextRun.stdout_excerpt,
            stderr_excerpt: nextRun.stderr_excerpt,
          })
          return
        }
        pollTimerRef.current = window.setTimeout(poll, 900)
      } catch (error) {
        if (cancelled) return
        setIsTesting(false)
        setLegacyResult({
          success: false,
          data: null,
          error_message: error instanceof Error ? error.message : "Failed to poll artifact run",
          execution_time_ms: 0,
          run_id: runId,
        })
      }
    }

    poll()

    return () => {
      cancelled = true
      if (pollTimerRef.current) {
        window.clearTimeout(pollTimerRef.current)
      }
    }
  }, [isTesting, runId, tenantSlug])

  const handleTestRun = async () => {
    setIsOpen(true)
    setIsTesting(true)
    setTestTab("output")
    setEvents([])
    setLegacyResult(null)

    try {
      let inputData: unknown
      let config: Record<string, unknown>
      try {
        inputData = JSON.parse(testInput)
      } catch {
        setIsTesting(false)
        setTestTab("input")
        setLegacyResult({ success: false, data: null, error_message: "Invalid Input JSON", execution_time_ms: 0 })
        return
      }
      try {
        config = JSON.parse(testConfig)
      } catch {
        setIsTesting(false)
        setTestTab("config")
        setLegacyResult({ success: false, data: null, error_message: "Invalid Config JSON", execution_time_ms: 0 })
        return
      }

      const created = await artifactsService.createTestRun(
        {
          artifact_id: artifactId,
          python_code: pythonCode,
          input_data: inputData,
          config,
          input_type: inputType,
          output_type: outputType,
        },
        tenantSlug
      )
      setRunId(created.run_id)
    } catch (error) {
      setIsTesting(false)
      setLegacyResult({
        success: false,
        data: null,
        error_message: error instanceof Error ? error.message : "Unknown error",
        execution_time_ms: 0,
      })
    }
  }

  const latestPhase = events.length > 0 ? events[events.length - 1] : null

  return (
    <div className={cn("border-t bg-background flex flex-col transition-all duration-300", isOpen ? "h-[420px]" : "h-11")}>
      <Tabs value={testTab} onValueChange={setTestTab} className="flex-1 flex flex-col min-h-0">
        <div className="h-11 px-3 border-b bg-muted/15 flex items-center gap-3">
          <button
            type="button"
            className="flex items-center gap-3 min-w-0 flex-1 text-left"
            onClick={() => setIsOpen(!isOpen)}
          >
            <div className="h-7 w-7 rounded-md bg-primary/10 text-primary flex items-center justify-center shrink-0">
              <Terminal className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex items-center gap-3">
              <span className="text-xs font-bold uppercase tracking-[0.18em] text-muted-foreground">Test Runtime</span>
              {legacyResult && (
                <Badge variant={legacyResult.success ? "secondary" : "destructive"} className="h-5 text-[10px] gap-1 px-2 border-none">
                  {legacyResult.success ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                  {legacyResult.success ? `Ready (${legacyResult.execution_time_ms.toFixed(1)}ms)` : "Error"}
                </Badge>
              )}
              {isTesting && (
                <span className="text-[11px] text-primary truncate">{formatPhase(latestPhase)}</span>
              )}
              {runId && (
                <span className="text-[10px] text-muted-foreground font-mono shrink-0">run {runId.slice(0, 8)}</span>
              )}
            </div>
          </button>

          <TabsList className="h-8 bg-transparent gap-1 px-0">
            <TabsTrigger value="input" className="text-[11px] h-7 px-3">Input Data (JSON)</TabsTrigger>
            <TabsTrigger value="config" className="text-[11px] h-7 px-3">Runtime Config</TabsTrigger>
            <TabsTrigger value="output" className="text-[11px] h-7 px-3">Trace Output</TabsTrigger>
            <TabsTrigger value="timeline" className="text-[11px] h-7 px-3">Execution Timeline</TabsTrigger>
          </TabsList>

          <Button
            id="artifact-test-panel-execute"
            size="icon"
            variant="default"
            onClick={(e) => {
              e.stopPropagation()
              handleTestRun()
            }}
            disabled={isTesting}
            className="h-7 w-7 shrink-0 border-none"
            aria-label="Execute artifact test run"
            title="Execute"
          >
            {isTesting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5 fill-current" />}
          </Button>

          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            onClick={() => setIsOpen(!isOpen)}
            aria-label={isOpen ? "Collapse test runtime" : "Expand test runtime"}
          >
            {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
          </Button>
        </div>

        {isOpen && (
          <div className="flex-1 min-h-0 relative">
              <TabsContent value="input" className="absolute inset-0 m-0">
                <CodeEditor value={testInput} onChange={setTestInput} language="json" className="h-full" />
              </TabsContent>
              <TabsContent value="config" className="absolute inset-0 m-0">
                <CodeEditor value={testConfig} onChange={setTestConfig} language="json" className="h-full" />
              </TabsContent>
              <TabsContent value="output" className="absolute inset-0 m-0 p-5 font-mono text-sm overflow-auto bg-background">
                {legacyResult ? (
                  <div className="space-y-4">
                    {legacyResult.success ? (
                      <pre className="text-emerald-400 whitespace-pre-wrap">{JSON.stringify(legacyResult.data, null, 2)}</pre>
                    ) : (
                      <div className="space-y-3 text-rose-400">
                        <div>
                          <p className="font-bold underline mb-2">Execution Failed:</p>
                          <pre className="whitespace-pre-wrap">{legacyResult.error_message}</pre>
                        </div>
                        {(legacyResult.stderr_excerpt || legacyResult.stdout_excerpt) && (
                          <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 p-3 space-y-2">
                            {legacyResult.stderr_excerpt && (
                              <div>
                                <p className="text-[10px] uppercase tracking-[0.2em] text-rose-300/80">stderr</p>
                                <pre className="mt-1 whitespace-pre-wrap text-[12px] text-rose-200">{legacyResult.stderr_excerpt}</pre>
                              </div>
                            )}
                            {legacyResult.stdout_excerpt && (
                              <div>
                                <p className="text-[10px] uppercase tracking-[0.2em] text-rose-300/80">stdout</p>
                                <pre className="mt-1 whitespace-pre-wrap text-[12px] text-rose-100">{legacyResult.stdout_excerpt}</pre>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex items-center justify-center h-full text-muted-foreground">
                    <span>No result yet. Run the artifact to see output here.</span>
                  </div>
                )}
              </TabsContent>
              <TabsContent value="timeline" className="absolute inset-0 m-0 font-mono text-sm overflow-auto bg-background">
                {isTesting ? (
                  <div className="h-full flex flex-col">
                    <div className="border-b px-5 py-4 flex items-center gap-3 text-muted-foreground">
                      <Loader2 className="h-6 w-6 animate-spin text-primary" />
                      <div>
                        <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Current Phase</p>
                        <p className="mt-1 text-sm text-foreground animate-pulse">{formatPhase(latestPhase)}</p>
                      </div>
                    </div>
                    <div className="flex-1 overflow-auto px-5 py-4">
                      {events.length > 0 ? (
                        <>
                          {events.map((event) => (
                            <div key={event.id} className="grid grid-cols-[20px_1fr] gap-3 py-3 border-b border-border/40 last:border-b-0 text-xs">
                              <div className="pt-1 flex justify-center">
                                <span className="h-2 w-2 rounded-full bg-primary/70 shrink-0" />
                              </div>
                              <div className="min-w-0">
                                <div className="flex items-center gap-3">
                                  <span className="text-foreground">{formatPhase(event)}</span>
                                  <span className="text-[10px] text-muted-foreground">#{event.sequence}</span>
                                </div>
                                {event.payload?.data && (
                                  <pre className="mt-2 whitespace-pre-wrap text-[11px] text-muted-foreground">
                                    {JSON.stringify(event.payload.data, null, 2)}
                                  </pre>
                                )}
                              </div>
                            </div>
                          ))}
                        </>
                      ) : (
                        <div className="flex items-center justify-center h-full text-muted-foreground">
                          <span>Waiting for execution events...</span>
                        </div>
                      )}
                    </div>
                  </div>
                ) : events.length > 0 ? (
                  <div className="h-full overflow-auto px-5 py-4">
                    {events.map((event) => (
                      <div key={event.id} className="grid grid-cols-[20px_1fr] gap-3 py-3 border-b border-border/40 last:border-b-0 text-xs">
                        <div className="pt-1 flex justify-center">
                          <span className={cn("h-2 w-2 rounded-full shrink-0", event.event_type.includes("failed") ? "bg-rose-500" : "bg-primary/70")} />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-3">
                            <span className="text-foreground">{formatPhase(event)}</span>
                            <span className="text-[10px] text-muted-foreground">#{event.sequence}</span>
                          </div>
                          {event.payload?.data && (
                            <pre className="mt-2 whitespace-pre-wrap text-[11px] text-muted-foreground">
                              {JSON.stringify(event.payload.data, null, 2)}
                            </pre>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex items-center justify-center h-full text-muted-foreground px-5">
                    <span>No execution timeline yet. Click &quot;Execute&quot; to start session.</span>
                  </div>
                )}
              </TabsContent>
          </div>
        )}
      </Tabs>
    </div>
  )
}
