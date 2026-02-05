import { PipelineStepExecution } from "./types"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { X, CheckCircle2, XCircle, Clock, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { PaginatedJsonView } from "./PaginatedJsonView"

interface ExecutionDetailsPanelProps {
    step: PipelineStepExecution
    onClose: () => void
}

function JsonView({ data }: { data: unknown }) {
    if (data === undefined || data === null) return <span className="text-muted-foreground italic">None</span>
    return (
        <pre className="bg-muted p-2 rounded-md text-xs font-mono overflow-auto max-h-[200px]">
            {JSON.stringify(data, null, 2)}
        </pre>
    )
}

export function ExecutionDetailsPanel({ step, onClose }: ExecutionDetailsPanelProps) {
    const duration = step.completed_at && step.started_at
        ? Math.round((new Date(step.completed_at).getTime() - new Date(step.started_at).getTime()) / 1000 * 100) / 100
        : null

    return (
        <div className="flex flex-col h-full bg-background w-full min-w-0">
            <div className="flex items-center justify-between p-2 border-b">
                <div className="flex items-center gap-2 pl-2">
                    <h3 className="font-semibold">Step Execution</h3>
                    <Badge variant={
                        step.status === 'completed' ? 'default' :
                            step.status === 'failed' ? 'destructive' :
                                step.status === 'running' ? 'secondary' : 'outline'
                    }>
                        {step.status}
                    </Badge>
                </div>
                <Button variant="ghost" size="icon" onClick={onClose}>
                    <X className="h-4 w-4" />
                </Button>
            </div>

            <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden">
                <div className="space-y-4 p-3 pb-10 w-full max-w-full">

                    <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                            <h4 className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground">Details</h4>
                        </div>
                        <div className="grid grid-cols-[max-content_2fr_max-content_1fr] gap-x-4 gap-y-1 text-xs items-baseline">
                            <span className="text-muted-foreground">Operator</span>
                            <span className="font-mono text-[11px] truncate">{step.operator_id}</span>
                            <span className="text-muted-foreground">Duration</span>
                            <span className="text-right font-medium">{duration !== null ? `${duration}s` : "-"}</span>

                            <span className="text-muted-foreground">Step ID</span>
                            <span className="font-mono text-[11px] text-muted-foreground/70 truncate" title={step.step_id}>{step.step_id}</span>
                            <span className="text-muted-foreground">Started</span>
                            <span className="text-right">{step.started_at ? new Date(step.started_at).toLocaleTimeString() : "-"}</span>

                            <span className="text-muted-foreground">Job ID</span>
                            <span className="font-mono text-[11px] text-muted-foreground/70 truncate col-span-3" title={step.job_id}>{step.job_id}</span>
                        </div>
                    </div>

                    <Separator />

                    {step.error_message && (
                        <div className="space-y-2">
                            <h4 className="text-sm font-medium text-destructive flex items-center gap-2">
                                <XCircle className="h-4 w-4" />
                                Error
                            </h4>
                            <div className="bg-destructive/10 text-destructive text-sm p-3 rounded-md whitespace-pre-wrap">
                                {step.error_message}
                            </div>
                        </div>
                    )}

                    <div className="space-y-2 overflow-hidden">
                        <PaginatedJsonView
                            jobId={step.job_id}
                            stepId={step.step_id}
                            type="input"
                            initialData={step.input_data}
                        />
                    </div>

                    <div className="space-y-2 overflow-hidden">
                        <PaginatedJsonView
                            jobId={step.job_id}
                            stepId={step.step_id}
                            type="output"
                            initialData={step.output_data}
                        />
                    </div>

                    <div className="space-y-2">
                        <h4 className="text-sm font-medium">Metadata</h4>
                        <JsonView data={step.metadata} />
                    </div>

                </div>
            </div>
        </div>
    )
}
