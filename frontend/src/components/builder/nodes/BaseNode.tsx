"use client"

import { memo } from "react"
import { Handle, Position, NodeProps } from "@xyflow/react"
import { cn } from "@/lib/utils"
import {
    Loader2,
    CheckCircle2,
    XCircle,
    Clock,
    AlertCircle,
    Hash
} from "lucide-react"

export interface SharedNodeHandle {
    id: string
    label?: string
    color?: string
    position?: Position
}

export interface SharedNodeData {
    displayName: string
    category: string
    inputType?: string | "none"
    outputType?: string | "none"
    isConfigured?: boolean
    hasErrors?: boolean
    executionStatus?: "pending" | "running" | "completed" | "failed" | "skipped"
    outputHandles?: SharedNodeHandle[]
    [key: string]: unknown
}

interface BaseNodeProps extends NodeProps {
    data: SharedNodeData
    icon?: React.ElementType
    categoryColor: string
    getHandleColor: (type: string) => string
    className?: string
}

function BaseNodeComponent({
    data,
    selected,
    icon: Icon = Hash,
    categoryColor,
    getHandleColor,
    className
}: BaseNodeProps) {
    const inputHandleColor = data.inputType ? getHandleColor(data.inputType) : "#6b7280"
    const outputHandleColor = data.outputType ? getHandleColor(data.outputType) : "#6b7280"

    const statusColors = {
        pending: "text-muted-foreground",
        running: "text-blue-500",
        completed: "text-green-500",
        failed: "text-destructive",
        skipped: "text-muted-foreground/50",
    }

    const statusIcons = {
        pending: <Clock className="w-3.5 h-3.5" />,
        running: <Loader2 className="w-3.5 h-3.5 animate-spin" />,
        completed: <CheckCircle2 className="w-3.5 h-3.5" />,
        failed: <XCircle className="w-3.5 h-3.5" />,
        skipped: <div className="w-1.5 h-1.5 rounded-full bg-muted-foreground/30" />,
    }

    const statusBorder = {
        running: "border-blue-500 ring-1 ring-blue-500/20",
        failed: "border-destructive ring-1 ring-destructive/20",
        completed: "border-green-500/50",
    }

    return (
        <div
            className={cn(
                "relative min-w-[200px] p-0 rounded-2xl bg-background/90 backdrop-blur-md transition-all duration-300 border",
                selected ? "border-primary ring-2 ring-primary/20 shadow-lg shadow-primary/5" : "border-border/50 shadow-sm",
                data.executionStatus && statusBorder[data.executionStatus as keyof typeof statusBorder],
                className
            )}
        >
            {/* Input Handle */}
            {data.inputType && data.inputType !== "none" && (
                <Handle
                    type="target"
                    position={Position.Left}
                    className={cn(
                        "!w-3 !h-3 !border-2 !border-background !-left-1.5",
                        "transition-all duration-200 hover:!w-4 hover:!h-4 hover:!-left-2"
                    )}
                    style={{ backgroundColor: inputHandleColor }}
                />
            )}

            <div className="flex items-center p-2.5 gap-2.5">
                <div
                    className="w-7 h-7 rounded-lg shrink-0 flex items-center justify-center relative shadow-sm"
                    style={{ backgroundColor: categoryColor }}
                >
                    {/* Status Overlay Icon */}
                    {data.executionStatus && data.executionStatus !== 'pending' && (
                        <div className={cn(
                            "absolute -top-1 -right-1 w-4 h-4 rounded-full bg-background flex items-center justify-center shadow-sm border border-border/50",
                            statusColors[data.executionStatus]
                        )}>
                            {statusIcons[data.executionStatus]}
                        </div>
                    )}
                    <Icon className="h-4 w-4 text-foreground/80" />
                </div>

                <div className="flex-1 min-w-0">
                    <div className="text-[9px] font-bold text-muted-foreground/50 uppercase tracking-widest leading-none mb-1">
                        {data.category}
                    </div>
                    <h4 className="text-[13px] font-semibold text-foreground/90 leading-tight truncate">
                        {data.displayName}
                    </h4>
                </div>

                {/* Status Indicators */}
                <div className="flex items-center gap-1.5 ml-1">
                    {data.hasErrors ? (
                        <AlertCircle className="h-3.5 w-3.5 text-destructive" />
                    ) : !data.isConfigured && !data.executionStatus ? (
                        <div className="w-1.5 h-1.5 rounded-full bg-amber-400/60 animate-pulse" />
                    ) : null}
                </div>
            </div>

            {/* Output Handles */}
            {!data.outputHandles && data.outputType && data.outputType !== "none" && (
                <Handle
                    type="source"
                    position={Position.Right}
                    className={cn(
                        "!w-3 !h-3 !border-2 !border-background !-right-1.5",
                        "transition-all duration-200 hover:!w-4 hover:!h-4 hover:!-right-2"
                    )}
                    style={{ backgroundColor: outputHandleColor }}
                />
            )}

            {/* Support for multiple handles (Conditional) */}
            {data.outputHandles && data.outputHandles.map((handle, idx) => (
                <div key={handle.id} className="relative group">
                    <Handle
                        type="source"
                        position={handle.position || Position.Right}
                        id={handle.id}
                        className={cn(
                            "!w-3 !h-3 !border-2 !border-background",
                            "transition-all duration-200 hover:!w-4 hover:!h-4"
                        )}
                        style={{
                            backgroundColor: handle.color || outputHandleColor,
                            top: `${((idx + 1) / (data.outputHandles!.length + 1)) * 100}%`
                        }}
                    />
                    {handle.label && (
                        <div
                            className="absolute right-[-24px] text-[9px] font-bold text-muted-foreground/60 uppercase"
                            style={{
                                top: `${((idx + 1) / (data.outputHandles!.length + 1)) * 100}%`,
                                transform: 'translateY(-50%)'
                            }}
                        >
                            {handle.label}
                        </div>
                    )}
                </div>
            ))}
        </div>
    )
}

export const BaseNode = memo(BaseNodeComponent)
