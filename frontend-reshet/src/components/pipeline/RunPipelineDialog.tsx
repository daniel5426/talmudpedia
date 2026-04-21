"use client"

import * as React from "react"
import { useEffect, useState } from "react"
import {
    Sheet,
    SheetContent,
    SheetHeader,
    SheetTitle,
    SheetDescription,
} from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { CompileResult, ragAdminService } from "@/services"
import { useOrganization } from "@/contexts/OrganizationContext"
import { DynamicOperatorForm } from "@/components/rag/DynamicOperatorForm"
import { ExecutablePipelineInputSchema } from "@/components/pipeline/types"
import { formatHttpErrorMessage } from "@/services/http"
import {
    Play,
    Loader2,
    AlertCircle,
    Zap,
    ChevronRight,
    Sparkles,
} from "lucide-react"
import { cn } from "@/lib/utils"

interface RunPipelineDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    onRun: (inputParams: Record<string, Record<string, unknown>>) => Promise<void>
    compileResult?: CompileResult | null
}

export function RunPipelineDialog({ open, onOpenChange, onRun, compileResult }: RunPipelineDialogProps) {
    const { currentOrganization } = useOrganization()
    const [inputData, setInputData] = useState<Record<string, Record<string, unknown>>>({})
    const [schema, setSchema] = useState<ExecutablePipelineInputSchema | null>(null)
    const [showAdvanced, setShowAdvanced] = useState(false)
    const [schemaError, setSchemaError] = useState<string | null>(null)
    const [runError, setRunError] = useState<string | null>(null)
    const [loading, setLoading] = useState(false)
    const [loadingSchema, setLoadingSchema] = useState(false)

    useEffect(() => {
        const execId = compileResult?.executable_pipeline_id
        if (!open || !execId) {
            setInputData({})
            setSchema(null)
            setSchemaError(null)
            setRunError(null)
            setShowAdvanced(false)
            return
        }
        const loadSchema = async () => {
            try {
                setLoadingSchema(true)
                setSchemaError(null)
                const response = await ragAdminService.getExecutablePipelineInputSchema(execId, currentOrganization?.id)
                setSchema(response)
            } catch (error) {
                console.error("Failed to load input schema", error)
                setSchemaError("Failed to load input schema")
            } finally {
                setLoadingSchema(false)
            }
        }
        loadSchema()
    }, [open, compileResult?.executable_pipeline_id, currentOrganization?.id])

    const hasAdvancedFields = (schema?.steps || []).some((step) =>
        (step.fields || []).some((field) =>
            field.operator_id === "query_input" && (field.name === "schema" || field.name === "filters")
        )
    )

    const totalInputCount = (schema?.steps || []).reduce(
        (count, step) => count + (step.fields || []).length,
        0
    )

    const handleRun = async () => {
        try {
            setLoading(true)
            setRunError(null)
            await onRun(inputData)
            onOpenChange(false)
        } catch (error) {
            console.error("Failed to run pipeline", error)
            setRunError(formatHttpErrorMessage(error, "Failed to run pipeline."))
        } finally {
            setLoading(false)
        }
    }

    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetContent
                side="right"
                className="w-full sm:max-w-lg flex flex-col p-0 gap-0"
            >
                {/* ── Header ── */}
                <SheetHeader className="px-5 pt-5 pb-5 border-b border-border/50 shrink-0 bg-muted/5">
                    <div className="flex items-center justify-between gap-4">
                        <div className="flex items-center gap-3 min-w-0">
                            <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 shrink-0">
                                <Play className="h-4 w-4 text-primary fill-primary/10" />
                            </div>
                            <div className="min-w-0 flex flex-col gap-0.5">
                                <SheetTitle className="text-[15px] font-bold tracking-tight text-foreground">
                                    Run Pipeline
                                </SheetTitle>
                                <SheetDescription className="text-xs text-muted-foreground/60 flex items-center gap-2">
                                    Execute compiled workflow
                                    {compileResult?.version && (
                                        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-primary/60 bg-primary/5 px-1.5 py-0.5 rounded-md border border-primary/10 uppercase tracking-wider">
                                            v{compileResult.version}
                                        </span>
                                    )}
                                </SheetDescription>
                            </div>
                        </div>
                        
                        {!loadingSchema && schema && totalInputCount > 0 && (
                            <div className="flex items-center gap-2 rounded-lg bg-background border border-border/40 px-2.5 py-1.5 shadow-[0_1px_2px_rgba(0,0,0,0.02)] shrink-0">
                                <div className="h-1.5 w-1.5 rounded-full bg-primary/60 animate-pulse" />
                                <span className="text-[10px] font-bold text-foreground/70 uppercase tracking-[0.05em]">
                                    {totalInputCount} {totalInputCount === 1 ? "input" : "inputs"} required
                                </span>
                            </div>
                        )}
                    </div>
                </SheetHeader>

                {/* ── Scrollable content ── */}
                <div className="flex-1 overflow-y-auto min-h-0">
                    <div className="px-5 py-6">
                        {/* Schema loading state */}
                        {loadingSchema && (
                            <div className="space-y-4">
                                <Skeleton className="h-[100px] w-full rounded-xl" />
                                <Skeleton className="h-[80px] w-full rounded-xl" />
                            </div>
                        )}

                        {/* Schema error */}
                        {schemaError && (
                            <div className="flex items-start gap-3 rounded-xl border border-destructive/20 bg-destructive/5 px-4 py-4">
                                <AlertCircle className="h-5 w-5 text-destructive shrink-0" />
                                <div className="space-y-1">
                                    <p className="text-sm font-bold text-destructive">
                                        Configuration Error
                                    </p>
                                    <p className="text-xs text-destructive/70 leading-relaxed">
                                        {schemaError}
                                    </p>
                                </div>
                            </div>
                        )}

                        {/* Run error */}
                        {runError && (
                            <div className="flex items-start gap-3 rounded-xl border border-destructive/20 bg-destructive/5 px-4 py-4 mb-6">
                                <AlertCircle className="h-5 w-5 text-destructive shrink-0" />
                                <div className="space-y-1">
                                    <p className="text-sm font-bold text-destructive">
                                        Execution Failed
                                    </p>
                                    <p className="text-xs text-destructive/70 leading-relaxed">
                                        {runError}
                                    </p>
                                </div>
                            </div>
                        )}

                        {/* Dynamic form */}
                        {!loadingSchema && !schemaError && (
                            <DynamicOperatorForm
                                schema={schema}
                                values={inputData}
                                onChange={setInputData}
                                onUploadFile={(file) => ragAdminService.uploadPipelineInput(file, currentOrganization?.id).then(res => res.path)}
                                showAdvanced={showAdvanced}
                                disabled={loading}
                            />
                        )}
                    </div>
                </div>

                {/* ── Sticky footer ── */}
                <div className="shrink-0 border-t border-border/50 bg-background px-5 py-4">
                    {/* Advanced toggle */}
                    {hasAdvancedFields && (
                        <button
                            type="button"
                            className={cn(
                                "flex items-center gap-1.5 text-[11px] font-medium transition-colors mb-3 px-0",
                                showAdvanced
                                    ? "text-primary"
                                    : "text-muted-foreground/60 hover:text-muted-foreground"
                            )}
                            onClick={() => setShowAdvanced((prev) => !prev)}
                            disabled={loading}
                        >
                            <ChevronRight
                                className={cn(
                                    "h-3 w-3 transition-transform duration-200",
                                    showAdvanced && "rotate-90"
                                )}
                            />
                            {showAdvanced ? "Hide advanced fields" : "Show advanced fields"}
                        </button>
                    )}

                    <div className="flex items-center gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            className="h-9 flex-1 text-xs"
                            onClick={() => onOpenChange(false)}
                            disabled={loading}
                        >
                            Cancel
                        </Button>
                        <Button
                            size="sm"
                            className="h-9 flex-[2] text-xs gap-1.5"
                            onClick={handleRun}
                            disabled={loading || loadingSchema || !!schemaError}
                        >
                            {loading ? (
                                <>
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                    Running…
                                </>
                            ) : (
                                <>
                                    <Sparkles className="h-3.5 w-3.5" />
                                    Run Pipeline
                                </>
                            )}
                        </Button>
                    </div>
                </div>
            </SheetContent>
        </Sheet>
    )
}
