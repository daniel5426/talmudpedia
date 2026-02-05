"use client"

import { memo } from "react"
import { NodeProps, Position, Handle } from "@xyflow/react"
import { Play, Square, Brain, Wrench, Search, GitBranch, GitFork, UserCheck, RefreshCw, Sparkles, Database, Bot, ListFilter } from "lucide-react"
import { cn } from "@/lib/utils"
import { BaseNode as SharedBaseNode, SharedNodeData, SharedNodeHandle } from "../../builder/nodes/BaseNode"
import { AgentNodeData, CATEGORY_COLORS, getClassifyHandleIds, getHandleColor, AgentNodeType } from "../types"

const NODE_ICONS: Record<AgentNodeType, React.ElementType> = {
    start: Play,
    end: Square,
    llm: Brain,
    agent: Bot,
    tool: Wrench,
    rag: Search,
    vector_search: Database,
    conditional: GitBranch,
    if_else: GitBranch,
    while: RefreshCw,
    parallel: GitFork,
    human_input: UserCheck,
    user_approval: UserCheck,
    transform: Sparkles,
    set_state: Database,
    classify: ListFilter,
}

function NodeBranchRow({
    label,
    handleId,
    handleColor,
    isLast = false,
}: {
    label: string
    handleId: string
    handleColor: string
    isLast?: boolean
}) {
    return (
        <div className={cn(
            "flex items-center justify-center px-4 py-3 bg-muted/5 relative min-h-[44px]",
            !isLast && "border-b border-border/40"
        )}>
            <span className="text-[12px] font-medium text-foreground/50 tracking-wide">{label}</span>
            <Handle
                type="source"
                position={Position.Right}
                id={handleId}
                className={cn(
                    "!w-3.5 !h-3.5 !border-2 !border-background !top-1/2 !-translate-y-1/2 !-right-1.75",
                    "transition-all duration-200 hover:!w-4.5 hover:!h-4.5 hover:!-right-2.25"
                )}
                style={{ backgroundColor: handleColor }}
            />
        </div>
    )
}

function BaseNodeComponent(props: NodeProps) {
    const fallbackData: AgentNodeData = {
        nodeType: "transform",
        category: "data",
        displayName: "Node",
        config: {},
        inputType: "any",
        outputType: "any",
        isConfigured: false,
        hasErrors: false,
    }
    const data = (props.data ?? fallbackData) as AgentNodeData
    const borderColor = CATEGORY_COLORS[data.category] ?? CATEGORY_COLORS.data
    const Icon = NODE_ICONS[data.nodeType] || Brain

    const isStartNode = data.nodeType === "start"
    const isEndNode = data.nodeType === "end"
    const isConditional = data.nodeType === "conditional"
    const isSpecialNode = ["if_else", "while", "user_approval", "classify"].includes(data.nodeType)

    // Prepare handles for shared node
    let outputHandles: SharedNodeHandle[] | undefined = undefined

    if (isConditional) {
        outputHandles = [
            { id: "true", label: "T", color: "#22c55e" },
            { id: "false", label: "F", color: "#ef4444" }
        ]
    }

    // Specialized content for if_else, while, user_approval
    let specializedContent: React.ReactNode = null

    if (data.nodeType === "if_else") {
        const conditions = (data.config?.conditions as any[]) || []
        specializedContent = (
            <div className="flex flex-col">
                {conditions.map((c: any) => (
                    <NodeBranchRow
                        key={c.name}
                        label={c.name}
                        handleId={c.name}
                        handleColor="#3b82f6"
                    />
                ))}
                <NodeBranchRow
                    label="Else"
                    handleId="else"
                    handleColor="#6b7280"
                    isLast={true}
                />
            </div>
        )
    } else if (data.nodeType === "while") {
        specializedContent = (
            <div className="flex flex-col">
                <NodeBranchRow
                    label="Loop"
                    handleId="loop"
                    handleColor="#3b82f6"
                />
                <NodeBranchRow
                    label="Exit"
                    handleId="exit"
                    handleColor="#6b7280"
                    isLast={true}
                />
            </div>
        )
    } else if (data.nodeType === "user_approval") {
        specializedContent = (
            <div className="flex flex-col">
                <NodeBranchRow
                    label="Approve"
                    handleId="approve"
                    handleColor="#22c55e"
                />
                <NodeBranchRow
                    label="Reject"
                    handleId="reject"
                    handleColor="#ef4444"
                    isLast={true}
                />
            </div>
        )
    } else if (data.nodeType === "classify") {
        const categories = (data.config?.categories as any[]) || []
        const handleIds = getClassifyHandleIds(categories)
        specializedContent = (
            <div className="flex flex-col">
                {categories.map((c: any, idx: number) => (
                    <NodeBranchRow
                        key={handleIds[idx]}
                        label={c.name}
                        handleId={handleIds[idx]}
                        handleColor="#8b5cf6"
                    />
                ))}
            </div>
        )
    }

    return (
        <SharedBaseNode
            {...props}
            data={{
                ...data,
                inputType: isStartNode ? "none" : data.inputType,
                outputType: (isEndNode || isConditional || isSpecialNode) ? "none" : data.outputType,
                outputHandles,
            } as SharedNodeData}
            icon={Icon}
            categoryColor={borderColor}
            getHandleColor={getHandleColor as (type: string) => string}
        >
            {specializedContent}
        </SharedBaseNode>
    )
}

export const BaseNode = memo(BaseNodeComponent)
