"use client"

import React from "react"
import { X, Activity } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ExecutionTrace } from "./ExecutionTrace"
import { ExecutionStep } from "@/hooks/useAgentRunController"

interface NodeTracePanelProps {
    nodeId: string
    nodeName: string
    steps: ExecutionStep[]
    nodeStatus?: "pending" | "running" | "completed" | "failed" | "skipped"
    onClose: () => void
}

export function NodeTracePanel({ nodeId, nodeName, steps, nodeStatus, onClose }: NodeTracePanelProps) {
    const traceStatus = nodeStatus
        ? nodeStatus.toUpperCase()
        : (steps.length > 0 ? steps[steps.length - 1].status.toUpperCase() : "IDLE")

    return (
        <div className="flex flex-col max-w-[320px]">
            <div className="p-3.5 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2.5">
                    <div className="w-7 h-7 rounded-lg shrink-0 flex items-center justify-center bg-primary/10">
                        <Activity className="h-4 w-4 text-primary" />
                    </div>
                    <div>
                        <h3 className="text-xs font-bold text-foreground/80 uppercase tracking-tight">Node Trace</h3>
                        <p className="text-[10px] text-muted-foreground leading-none mt-0.5 uppercase tracking-wider font-medium opacity-50">
                            {nodeName}
                        </p>
                    </div>
                </div>
                <Button
                    variant="ghost"
                    size="icon"
                    onClick={onClose}
                    className="h-8 w-8 rounded-lg text-muted-foreground hover:bg-muted"
                >
                    <X className="h-4 w-4" />
                </Button>
            </div>

            <div className="overflow-y-auto px-1 pb-4 max-h-[60vh] scrollbar-none">
                <ExecutionTrace
                    steps={steps}
                    className="bg-transparent h-auto"
                    showHeader={false}
                />

                {steps.length === 0 && (
                    <div className="p-8 text-center text-muted-foreground">
                        <p className="text-[11px] font-medium opacity-50">No execution trace found for this node yet.</p>
                    </div>
                )}
            </div>

            <div className="px-3.5 py-4 flex items-center justify-between border-t border-border/10 bg-muted/5">
                <div className="flex flex-col">
                    <span className="text-[9px] font-bold text-foreground/40 uppercase tracking-widest">
                        Node ID
                    </span>
                    <span className="text-[10px] font-mono text-muted-foreground tabular-nums">
                        {nodeId.split("-").pop()}
                    </span>
                </div>
                <div className="flex flex-col items-end">
                    <span className="text-[9px] font-bold text-foreground/40 uppercase tracking-widest">
                        Status
                    </span>
                    <span className="text-[10px] font-mono text-primary font-bold">
                        {traceStatus}
                    </span>
                </div>
            </div>
        </div>
    )
}
