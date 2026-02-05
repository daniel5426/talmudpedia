"use client"

import * as React from "react"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useEffect, useState } from "react"
import { CompileResult, ragAdminService } from "@/services"
import { useTenant } from "@/contexts/TenantContext"
import { DynamicOperatorForm } from "@/components/rag/DynamicOperatorForm"
import { ExecutablePipelineInputSchema } from "@/components/pipeline/types"

interface RunPipelineDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    onRun: (inputParams: Record<string, Record<string, unknown>>) => Promise<void>
    compileResult?: CompileResult | null
}

export function RunPipelineDialog({ open, onOpenChange, onRun, compileResult }: RunPipelineDialogProps) {
    const { currentTenant } = useTenant()
    const [inputData, setInputData] = useState<Record<string, Record<string, unknown>>>({})
    const [schema, setSchema] = useState<ExecutablePipelineInputSchema | null>(null)
    const [schemaError, setSchemaError] = useState<string | null>(null)
    const [loading, setLoading] = useState(false)
    const [loadingSchema, setLoadingSchema] = useState(false)

    useEffect(() => {
        const execId = compileResult?.executable_pipeline_id
        if (!open || !execId) {
            setSchema(null)
            setSchemaError(null)
            return
        }
        const loadSchema = async () => {
            try {
                setLoadingSchema(true)
                setSchemaError(null)
                const response = await ragAdminService.getExecutablePipelineInputSchema(execId, currentTenant?.slug)
                setSchema(response)
            } catch (error) {
                console.error("Failed to load input schema", error)
                setSchemaError("Failed to load input schema")
            } finally {
                setLoadingSchema(false)
            }
        }
        loadSchema()
    }, [open, compileResult?.executable_pipeline_id, currentTenant?.slug])

    const handleRun = async () => {
        try {
            setLoading(true)
            await onRun(inputData)
            onOpenChange(false)
        } catch (error) {
            console.error("Failed to run pipeline", error)
        } finally {
            setLoading(false)
        }
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[500px]">
                <DialogHeader>
                    <DialogTitle>Run Pipeline</DialogTitle>
                    <DialogDescription>
                        Execute the compiled pipeline with custom input.
                        {compileResult?.version && ` Using v${compileResult.version}.`}
                    </DialogDescription>
                </DialogHeader>

                <div className="grid gap-4 py-4">
                    {loadingSchema && (
                        <div className="space-y-2">
                            <Skeleton className="h-4 w-1/2" />
                            <Skeleton className="h-4 w-full" />
                            <Skeleton className="h-4 w-3/4" />
                        </div>
                    )}
                    {schemaError && (
                        <div className="text-sm text-destructive">{schemaError}</div>
                    )}
                    {!loadingSchema && !schemaError && (
                        <DynamicOperatorForm
                            schema={schema}
                            values={inputData}
                            onChange={setInputData}
                            onUploadFile={(file) => ragAdminService.uploadPipelineInput(file, currentTenant?.slug).then(res => res.path)}
                            disabled={loading}
                        />
                    )}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
                    <Button onClick={handleRun} disabled={loading}>
                        {loading ? "Running..." : "Run Pipeline"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
