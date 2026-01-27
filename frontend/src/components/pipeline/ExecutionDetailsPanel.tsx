import { PipelineStepExecution } from "./types"
import { ScrollArea } from "@/components/ui/scroll-area"
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

            <div className="flex-1 min-h-0">
                <ScrollArea className="h-full w-full">
                    <div className="space-y-6 min-w-0 p-4 pb-10">

                        <div className="space-y-2">
                            <h4 className="text-sm font-medium">Details</h4>
                            <div className="grid grid-cols-2 gap-2 text-sm">
                                <div className="text-muted-foreground">Step ID</div>
                                <div className="font-mono text-xs">{step.step_id}</div>

                                <div className="text-muted-foreground">Operator</div>
                                <div className="font-mono text-xs">{step.operator_id}</div>

                                <div className="text-muted-foreground">Job ID</div>
                                <div className="font-mono text-xs" title={step.job_id}>{step.job_id.slice(0, 8)}...</div>

                                <div className="text-muted-foreground">Started</div>
                                <div>{step.started_at ? new Date(step.started_at).toLocaleTimeString() : "-"}</div>

                                <div className="text-muted-foreground">Duration</div>
                                <div>{duration !== null ? `${duration}s` : "-"}</div>
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

                        <div className="space-y-2">
                            <PaginatedJsonView
                                jobId={step.job_id}
                                stepId={step.step_id}
                                type="input"
                                initialData={step.input_data}
                            />
                        </div>

                        <div className="space-y-2">
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
                </ScrollArea>
            </div>
        </div>
    )
}
