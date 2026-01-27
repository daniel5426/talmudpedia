"use client"

import * as React from "react"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useState } from "react"
import { CompileResult } from "@/services"

interface RunPipelineDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    onRun: (inputParams: Record<string, unknown>) => Promise<void>
    compileResult?: CompileResult | null
}

export function RunPipelineDialog({ open, onOpenChange, onRun, compileResult }: RunPipelineDialogProps) {
    const [inputData, setInputData] = useState("{}")
    const [loading, setLoading] = useState(false)

    const handleRun = async () => {
        try {
            setLoading(true)
            let parsedInput = {}
            try {
                parsedInput = JSON.parse(inputData)
            } catch (e) {
                alert("Invalid JSON input")
                setLoading(false)
                return
            }
            await onRun(parsedInput)
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
                    <div className="space-y-2">
                        <Label>Input Parameters (JSON)</Label>
                        <Textarea
                            className="font-mono min-h-[150px]"
                            value={inputData}
                            onChange={e => setInputData(e.target.value)}
                            placeholder='{ "query": "test" }'
                        />
                    </div>
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
