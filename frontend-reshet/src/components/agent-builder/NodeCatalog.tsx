"use client"

import { useMemo, useEffect, useState } from "react"
import {
    Play, Square, Brain, Wrench, Search, GitBranch, GitFork, UserCheck, Circle,
    GripVertical, PanelLeftClose, Database, Bot, Sparkles, RefreshCw, ListFilter, GitMerge, Link, Route, Scale, Ban, Mic,
    PanelLeft
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import {
    AgentNodeCategory,
    CATEGORY_COLORS,
    CATEGORY_LABELS,
} from "./types"
import type { NodeCatalogItem } from "@/services/graph-authoring"
import { agentService } from "@/services/agent"

const ICON_MAP: Record<string, React.ElementType> = {
    Play, Square, Brain, Wrench, Search, GitBranch, GitFork, UserCheck, Circle,
    Database, Bot, Sparkles, RefreshCw, ListFilter, GitMerge, Link, Route, Scale, Ban, Mic,
    // Lowercase mappings for types
    start: Play,
    end: Square,
    agent: Bot,
    tool: Wrench,
    rag: Search,
    conditional: GitBranch,
    if_else: GitBranch,
    while: RefreshCw,
    parallel: GitFork,
    spawn_run: GitBranch,
    spawn_group: GitMerge,
    join: Link,
    router: Route,
    judge: Scale,
    replan: RefreshCw,
    cancel_subtree: Ban,
    human_input: UserCheck,
    user_approval: UserCheck,
    speech_to_text: Mic,
    transform: Sparkles,
    set_state: Database,
    classify: ListFilter,
}

// Helper to get icon component safely
const getIcon = (iconName: string) => {
    // Try exact match (e.g. Brain)
    if (ICON_MAP[iconName]) return ICON_MAP[iconName]
    // Try lowercase match (e.g. brain or agent)
    const lower = iconName.toLowerCase()
    if (ICON_MAP[lower]) return ICON_MAP[lower]
    return Circle
}

const renderCatalogIcon = (iconName: string) => {
    const IconComponent = getIcon(iconName) || Circle
    return <IconComponent className="h-3.5 w-3.5 text-foreground" />
}

interface NodeCatalogProps {
    onDragStart: (event: React.DragEvent, item: NodeCatalogItem) => void
    onClose?: () => void
}

function CatalogItem({
    spec,
    onDragStart
}: {
    spec: NodeCatalogItem
    onDragStart: (event: React.DragEvent) => void
}) {
    const color = CATEGORY_COLORS[spec.category as AgentNodeCategory] || spec.color || CATEGORY_COLORS.data

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
                className="shrink-0 h-7 w-7 rounded-lg flex items-center justify-center shadow-sm transition-transform group-hover:scale-105"
                style={{ backgroundColor: color }}
            >
                {renderCatalogIcon(spec.icon || "Circle")}
            </div>
            <div className="flex-1 min-w-0">
                <span className="text-[13px] font-medium text-foreground/80 truncate block">
                    {spec.title}
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
    specs: NodeCatalogItem[]
    onDragStart: (event: React.DragEvent, spec: NodeCatalogItem) => void
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
                        key={spec.type}
                        spec={spec}
                        onDragStart={(e) => onDragStart(e, spec)}
                    />
                ))}
            </div>
        </div>
    )
}

export function NodeCatalog({ onDragStart, onClose }: NodeCatalogProps) {
    const [operators, setOperators] = useState<NodeCatalogItem[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [search, setSearch] = useState("")

    useEffect(() => {
        agentService.listNodeCatalog()
            .then((response) => setOperators(response.nodes || []))
            .catch(err => {
                console.error("Failed to fetch node catalog:", err)
                setOperators([])
            })
            .finally(() => setIsLoading(false))
    }, [])

    // Filter specs by search
    const filteredSpecs = useMemo(() => {
        if (!search) return operators
        const lowerSearch = search.toLowerCase()
        return operators.filter(spec =>
            spec.title.toLowerCase().includes(lowerSearch) ||
            (spec.description || "").toLowerCase().includes(lowerSearch)
        )
    }, [operators, search])

    const groupedSpecs = useMemo(() => {
        const groups: Record<AgentNodeCategory, NodeCatalogItem[]> = {
            control: [],
            reasoning: [],
            action: [],
            logic: [],
            interaction: [],
            data: [],
            orchestration: [],
        }

        filteredSpecs.forEach(spec => {
            const category = spec.category as AgentNodeCategory
            if (groups[category]) {
                groups[category].push(spec)
            }
        })

        return groups
    }, [filteredSpecs])

    const categories: AgentNodeCategory[] = ["control", "reasoning", "action", "logic", "interaction", "data"]

    return (
        <div className="flex flex-col h-full">
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
                                <PanelLeft className="h-4 w-4" />
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
                <div className="flex-1 pb-2 overflow-y-auto px-3.5 pb-6 space-y-6 scrollbar-none">
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
