"use client"

import { memo } from "react"
import { Handle, Position, NodeProps } from "@xyflow/react"
import { cn } from "@/lib/utils"
import { AlertCircle, CheckCircle2, Play, Square, Brain, Wrench, Search, GitBranch, GitFork, UserCheck } from "lucide-react"
import { AgentNodeData, CATEGORY_COLORS, getHandleColor, AgentNodeType } from "../types"

const NODE_ICONS: Record<AgentNodeType, React.ElementType> = {
    start: Play,
    end: Square,
    llm: Brain,
    tool: Wrench,
    rag: Search,
    conditional: GitBranch,
    parallel: GitFork,
    human_input: UserCheck,
}

interface BaseNodeProps extends NodeProps {
    data: AgentNodeData
}

function BaseNodeComponent({ data, selected }: BaseNodeProps) {
    const borderColor = CATEGORY_COLORS[data.category]
    const inputHandleColor = getHandleColor(data.inputType)
    const outputHandleColor = getHandleColor(data.outputType)
    const Icon = NODE_ICONS[data.nodeType] || Brain

    const isStartNode = data.nodeType === "start"
    const isEndNode = data.nodeType === "end"
    const isConditional = data.nodeType === "conditional"

    return (
        <div
            className={cn(
                "relative px-4 py-3 rounded-lg border-2 bg-background shadow-sm min-w-[160px]",
                "transition-all duration-200",
                selected && "ring-2 ring-primary ring-offset-2"
            )}
            style={{ borderColor }}
        >
            {/* Input Handle - not for start nodes */}
            {!isStartNode && (
                <Handle
                    type="target"
                    position={Position.Left}
                    className="!w-3 !h-3 !border-2 !border-background"
                    style={{ backgroundColor: inputHandleColor }}
                />
            )}

            <div className="flex items-center gap-2">
                <div
                    className="p-1.5 rounded-md"
                    style={{ backgroundColor: `${borderColor}20` }}
                >
                    <Icon className="h-4 w-4" style={{ color: borderColor }} />
                </div>
                <div className="flex-1 min-w-0">
                    <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                        {data.category}
                    </div>
                    <div className="text-sm font-semibold truncate">
                        {data.displayName}
                    </div>
                </div>
                <div className="flex-shrink-0">
                    {data.hasErrors ? (
                        <AlertCircle className="h-4 w-4 text-destructive" />
                    ) : data.isConfigured ? (
                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                    ) : (
                        <div className="h-4 w-4 rounded-full border-2 border-muted-foreground/30" />
                    )}
                </div>
            </div>

            {/* Output Handle - not for end nodes */}
            {!isEndNode && !isConditional && (
                <Handle
                    type="source"
                    position={Position.Right}
                    className="!w-3 !h-3 !border-2 !border-background"
                    style={{ backgroundColor: outputHandleColor }}
                />
            )}

            {/* Conditional nodes get two output handles */}
            {isConditional && (
                <>
                    <Handle
                        type="source"
                        position={Position.Right}
                        id="true"
                        className="!w-3 !h-3 !border-2 !border-background !top-[35%]"
                        style={{ backgroundColor: "#22c55e" }}
                    />
                    <Handle
                        type="source"
                        position={Position.Right}
                        id="false"
                        className="!w-3 !h-3 !border-2 !border-background !top-[65%]"
                        style={{ backgroundColor: "#ef4444" }}
                    />
                    <div className="absolute right-[-20px] top-[32%] text-[8px] text-green-500 font-medium">T</div>
                    <div className="absolute right-[-20px] top-[62%] text-[8px] text-red-500 font-medium">F</div>
                </>
            )}
        </div>
    )
}

export const BaseNode = memo(BaseNodeComponent)
