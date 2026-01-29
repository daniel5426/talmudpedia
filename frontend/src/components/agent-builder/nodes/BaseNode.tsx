"use client"

import { memo } from "react"
import { NodeProps, Position } from "@xyflow/react"
import { Play, Square, Brain, Wrench, Search, GitBranch, GitFork, UserCheck } from "lucide-react"
import { BaseNode as SharedBaseNode, SharedNodeData, SharedNodeHandle } from "../../builder/nodes/BaseNode"
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

function BaseNodeComponent(props: NodeProps) {
    const data = props.data as AgentNodeData
    const borderColor = CATEGORY_COLORS[data.category]
    const Icon = NODE_ICONS[data.nodeType] || Brain

    const isStartNode = data.nodeType === "start"
    const isEndNode = data.nodeType === "end"
    const isConditional = data.nodeType === "conditional"

    // Prepare handles for shared node
    let outputHandles: SharedNodeHandle[] | undefined = undefined
    if (isConditional) {
        outputHandles = [
            { id: "true", label: "T", color: "#22c55e" },
            { id: "false", label: "F", color: "#ef4444" }
        ]
    }

    return (
        <SharedBaseNode
            {...props}
            data={{
                ...data,
                inputType: isStartNode ? "none" : data.inputType,
                outputType: (isEndNode || isConditional) ? "none" : data.outputType,
                outputHandles,
            } as SharedNodeData}
            icon={Icon}
            categoryColor={borderColor}
            getHandleColor={getHandleColor as (type: string) => string}
        />
    )
}

export const BaseNode = memo(BaseNodeComponent)
