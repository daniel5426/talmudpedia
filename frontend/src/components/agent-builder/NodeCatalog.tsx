"use client"

import { useMemo } from "react"
import { Play, Square, Brain, Wrench, Search, GitBranch, GitFork, UserCheck } from "lucide-react"
import { cn } from "@/lib/utils"
import {
    AgentNodeCategory,
    AgentNodeType,
    AGENT_NODE_SPECS,
    CATEGORY_COLORS,
    CATEGORY_LABELS,
    AgentNodeSpec
} from "./types"

const CATEGORY_ICONS: Record<AgentNodeCategory, React.ElementType> = {
    control: Play,
    reasoning: Brain,
    action: Wrench,
    logic: GitBranch,
    interaction: UserCheck,
}

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

interface NodeCatalogProps {
    onDragStart: (event: React.DragEvent, nodeType: AgentNodeType, category: AgentNodeCategory) => void
}

function CatalogItem({
    spec,
    onDragStart
}: {
    spec: AgentNodeSpec
    onDragStart: (event: React.DragEvent) => void
}) {
    const Icon = NODE_ICONS[spec.nodeType]
    const color = CATEGORY_COLORS[spec.category]

    return (
        <div
            className={cn(
                "flex items-center gap-2 px-3 py-2 rounded-md cursor-grab",
                "border border-transparent hover:border-border",
                "bg-muted/50 hover:bg-muted transition-colors"
            )}
            draggable
            onDragStart={onDragStart}
            title={spec.description}
        >
            <div
                className="p-1 rounded"
                style={{ backgroundColor: `${color}20` }}
            >
                <Icon className="h-3.5 w-3.5" style={{ color }} />
            </div>
            <div className="flex-1 min-w-0">
                <span className="text-sm font-medium truncate">{spec.displayName}</span>
            </div>
        </div>
    )
}

function CategorySection({
    category,
    specs,
    onDragStart
}: {
    category: AgentNodeCategory
    specs: AgentNodeSpec[]
    onDragStart: (event: React.DragEvent, nodeType: AgentNodeType, category: AgentNodeCategory) => void
}) {
    const color = CATEGORY_COLORS[category]
    const label = CATEGORY_LABELS[category]

    if (specs.length === 0) return null

    return (
        <div className="space-y-2">
            <div className="flex items-center gap-2 px-1">
                <div
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: color }}
                />
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {label}
                </span>
            </div>
            <div className="space-y-1">
                {specs.map((spec) => (
                    <CatalogItem
                        key={spec.nodeType}
                        spec={spec}
                        onDragStart={(e) => onDragStart(e, spec.nodeType, spec.category)}
                    />
                ))}
            </div>
        </div>
    )
}

export function NodeCatalog({ onDragStart }: NodeCatalogProps) {
    const groupedSpecs = useMemo(() => {
        const groups: Record<AgentNodeCategory, AgentNodeSpec[]> = {
            control: [],
            reasoning: [],
            action: [],
            logic: [],
            interaction: [],
        }

        AGENT_NODE_SPECS.forEach(spec => {
            groups[spec.category].push(spec)
        })

        return groups
    }, [])

    const categories: AgentNodeCategory[] = ["control", "reasoning", "action", "logic", "interaction"]

    return (
        <div className="h-full flex flex-col">
            <div className="p-4 border-b">
                <h3 className="font-semibold text-sm">Agent Nodes</h3>
                <p className="text-xs text-muted-foreground mt-1">
                    Drag nodes onto the canvas
                </p>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-6">
                {categories.map((category) => (
                    <CategorySection
                        key={category}
                        category={category}
                        specs={groupedSpecs[category]}
                        onDragStart={onDragStart}
                    />
                ))}
            </div>
        </div>
    )
}
