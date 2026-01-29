"use client"

import { useMemo, useEffect, useState } from "react"
import {
    Play, Square, Brain, Wrench, Search, GitBranch, GitFork, UserCheck, Circle,
    GripVertical, PanelLeftClose
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import {
    AgentNodeCategory,
    AgentNodeType,
    CATEGORY_COLORS,
    CATEGORY_LABELS,
    AgentNodeSpec,
    AGENT_NODE_SPECS,
} from "./types"
import { agentService, AgentOperatorSpec } from "@/services/agent"

const CATEGORY_ICONS: Record<AgentNodeCategory, React.ElementType> = {
    control: Play,
    reasoning: Brain,
    action: Wrench,
    logic: GitBranch,
    interaction: UserCheck,
}

const NODE_ICONS: Record<string, React.ElementType> = {
    start: Play,
    end: Square,
    llm: Brain,
    tool: Wrench,
    rag: Search,
    conditional: GitBranch,
    parallel: GitFork,
    human_input: UserCheck,
}

// Helper to get icon component safely
const getIcon = (iconName: string) => {
    const mapped = Object.entries(NODE_ICONS).find(([k]) => k.toLowerCase() === iconName.toLowerCase())
    if (mapped) return mapped[1]
    return Circle
}

interface NodeCatalogProps {
    onDragStart: (event: React.DragEvent, nodeType: AgentNodeType, category: AgentNodeCategory) => void
    onClose?: () => void
}

function CatalogItem({
    spec,
    onDragStart
}: {
    spec: AgentNodeSpec
    onDragStart: (event: React.DragEvent) => void
}) {
    const Icon = getIcon(spec.icon) || Circle
    const color = CATEGORY_COLORS[spec.category]

    return (
        <div
            className={cn(
                "group flex items-center gap-2.5 px-2 py-1.5 rounded-lg cursor-grab active:cursor-grabbing",
                "border border-transparent bg-muted/30 hover:bg-background hover:border-border",
                "transition-all duration-200"
            )}
            draggable
            onDragStart={onDragStart}
            title={spec.description}
        >
            <div
                className="shrink-0 p-1.5 rounded-md transition-transform group-hover:scale-105"
                style={{ backgroundColor: color }}
            >
                <Icon className="h-3.5 w-3.5 text-foreground" />
            </div>
            <div className="flex-1 min-w-0">
                <span className="text-[13px] font-medium text-foreground/80 truncate block">
                    {spec.displayName}
                </span>
            </div>
            <GripVertical className="h-3.5 w-3.5 text-muted-foreground/10 group-hover:text-muted-foreground/30 transition-colors" />
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
    const label = CATEGORY_LABELS[category]

    if (specs.length === 0) return null

    return (
        <div className="space-y-2">
            <div className="flex items-center gap-2 px-1">
                <span className="text-[9px] font-bold uppercase tracking-[0.1em] text-muted-foreground/50">
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

export function NodeCatalog({ onDragStart, onClose }: NodeCatalogProps) {
    const [operators, setOperators] = useState<AgentOperatorSpec[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [search, setSearch] = useState("")

    useEffect(() => {
        agentService.listOperators()
            .then(setOperators)
            .catch(err => {
                console.error("Failed to fetch operators:", err)
                // Fallback to static specs if API fails
                setOperators([])
            })
            .finally(() => setIsLoading(false))
    }, [])

    // Convert API operators to specs, falling back to static specs if API fails
    const nodeSpecs: AgentNodeSpec[] = useMemo(() => {
        if (operators.length === 0) {
            // Fallback to static specs
            return AGENT_NODE_SPECS
        }
        return operators.map(op => ({
            nodeType: op.type as AgentNodeType,
            displayName: op.display_name,
            description: op.description,
            category: op.category as AgentNodeCategory,
            inputType: op.ui.inputType || "any",
            outputType: op.ui.outputType || "any",
            icon: op.ui.icon || "Circle",
            configFields: op.ui.configFields || []
        }))
    }, [operators])

    // Filter specs by search
    const filteredSpecs = useMemo(() => {
        if (!search) return nodeSpecs
        const lowerSearch = search.toLowerCase()
        return nodeSpecs.filter(spec =>
            spec.displayName.toLowerCase().includes(lowerSearch) ||
            spec.description.toLowerCase().includes(lowerSearch)
        )
    }, [nodeSpecs, search])

    const groupedSpecs = useMemo(() => {
        const groups: Record<AgentNodeCategory, AgentNodeSpec[]> = {
            control: [],
            reasoning: [],
            action: [],
            logic: [],
            interaction: [],
        }

        filteredSpecs.forEach(spec => {
            if (groups[spec.category]) {
                groups[spec.category].push(spec)
            }
        })

        return groups
    }, [filteredSpecs])

    const categories: AgentNodeCategory[] = ["control", "reasoning", "action", "logic", "interaction"]

    return (
        <div className="flex flex-col">
            <div className="p-3.5 space-y-3 flex-shrink-0">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        {onClose && (
                            <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 rounded-md -ml-1 text-muted-foreground hover:text-foreground"
                                onClick={onClose}
                                title="Close Catalog"
                            >
                                <PanelLeftClose className="h-4 w-4" />
                            </Button>
                        )}
                        <h3 className="text-xs font-bold text-foreground/70 uppercase tracking-tight">
                            Agent Nodes
                        </h3>
                    </div>
                </div>
                <div className="relative">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
                    <Input
                        placeholder="Search..."
                        className="pl-8 h-8 bg-muted/40 border-none rounded-lg text-[11px] focus-visible:ring-1 focus-visible:ring-offset-0"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                    />
                </div>
            </div>

            {isLoading ? (
                <div className="flex-1 flex items-center justify-center">
                    <p className="text-xs text-muted-foreground">Loading catalog...</p>
                </div>
            ) : (
                <div className="flex-1 overflow-y-auto px-3.5 pb-6 space-y-6 scrollbar-none max-h-[70vh]">
                    {categories.map((category) => (
                        <CategorySection
                            key={category}
                            category={category}
                            specs={groupedSpecs[category]}
                            onDragStart={onDragStart}
                        />
                    ))}
                    {filteredSpecs.length === 0 && (
                        <div className="flex flex-col items-center justify-center py-8 text-center">
                            <p className="text-[11px] text-muted-foreground">No matches</p>
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
