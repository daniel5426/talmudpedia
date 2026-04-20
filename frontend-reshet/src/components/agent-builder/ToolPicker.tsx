"use client"

import { useMemo, useState } from "react"
import { ToolDefinition, ToolTypeBucket } from "@/services/agent"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetFooter } from "@/components/ui/sheet"
import { Search, X, ArrowLeft, Check, Wrench, Globe, Box, Code2, ChevronRight } from "lucide-react"
import { TOOL_BUCKETS, buildToolsets, getToolBucket, getSubtypeLabel, getToolsetSelectionState, ToolsetGroup } from "@/lib/tool-types"
import { cn } from "@/lib/utils"
import { ToolDefinitionDetailBody } from "./tool-definition-detail-body"

interface ToolPickerProps {
    tools: ToolDefinition[]
    value: string[]
    onChange: (next: string[]) => void
    open?: boolean
    onOpenChange?: (open: boolean) => void
}

const BUCKET_ICONS: Record<ToolTypeBucket, React.ElementType> = {
    built_in: Wrench,
    mcp: Globe,
    artifact: Box,
    custom: Code2,
}

type ToolPickerItem =
    | { kind: "tool"; tool: ToolDefinition; bucket: ToolTypeBucket }
    | { kind: "toolset"; toolset: ToolsetGroup; bucket: ToolTypeBucket }

export function ToolPicker({ tools, value, onChange, open, onOpenChange }: ToolPickerProps) {
    const [query, setQuery] = useState("")
    const [bucketFilter, setBucketFilter] = useState<ToolTypeBucket | "all">("all")
    const [selectedTool, setSelectedTool] = useState<ToolDefinition | null>(null)
    const [view, setView] = useState<"list" | "detail">("list")
    const [expandedToolsets, setExpandedToolsets] = useState<Record<string, boolean>>({})

    const normalizedQuery = query.trim().toLowerCase()
    const toolsets = useMemo(() => buildToolsets(tools || []), [tools])
    const toolsetMemberIds = useMemo(() => {
        const next = new Set<string>()
        toolsets.forEach((toolset) => {
            toolset.member_ids.forEach((memberId) => next.add(memberId))
        })
        return next
    }, [toolsets])

    const topLevelItems = useMemo<ToolPickerItem[]>(() => {
        const standaloneItems = (tools || [])
            .filter((tool) => !toolsetMemberIds.has(tool.id))
            .map<ToolPickerItem>((tool) => ({
                kind: "tool",
                tool,
                bucket: getToolBucket(tool),
            }))
        const toolsetItems = toolsets.map<ToolPickerItem>((toolset) => ({
            kind: "toolset",
            toolset,
            bucket: toolset.bucket,
        }))
        return [...toolsetItems, ...standaloneItems]
    }, [tools, toolsetMemberIds, toolsets])

    const matchesQuery = (text: string | null | undefined) => {
        if (!normalizedQuery) return true
        return (text || "").toLowerCase().includes(normalizedQuery)
    }

    const matchesTool = (tool: ToolDefinition) => {
        if (!normalizedQuery) return true
        return (
            matchesQuery(tool.name) ||
            matchesQuery(tool.slug) ||
            matchesQuery(tool.description)
        )
    }

    const matchesToolset = (toolset: ToolsetGroup) => {
        if (!normalizedQuery) return true
        return (
            matchesQuery(toolset.name) ||
            matchesQuery(toolset.description) ||
            toolset.members.some((member) => matchesTool(member))
        )
    }

    const queryFilteredItems = useMemo(() => {
        return topLevelItems.filter((item) => {
            if (item.kind === "tool") return matchesTool(item.tool)
            return matchesToolset(item.toolset)
        })
    }, [topLevelItems, normalizedQuery])

    const filteredItems = useMemo(() => {
        if (bucketFilter === "all") return queryFilteredItems
        return queryFilteredItems.filter((item) => item.bucket === bucketFilter)
    }, [bucketFilter, queryFilteredItems])

    const allGroupedItems = useMemo(() => {
        const groups: Record<ToolTypeBucket, ToolPickerItem[]> = {
            built_in: [],
            mcp: [],
            artifact: [],
            custom: [],
        }
        queryFilteredItems.forEach((item) => {
            groups[item.bucket].push(item)
        })
        return groups
    }, [queryFilteredItems])

    const displayGroupedItems = useMemo(() => {
        const groups: Record<ToolTypeBucket, ToolPickerItem[]> = {
            built_in: [],
            mcp: [],
            artifact: [],
            custom: [],
        }
        filteredItems.forEach((item) => {
            groups[item.bucket].push(item)
        })
        return groups
    }, [filteredItems])

    const activeBuckets = useMemo(() => {
        return TOOL_BUCKETS.filter((bucket) => allGroupedItems[bucket.id].length > 0)
    }, [allGroupedItems])

    const toggleTool = (toolId: string, checked: boolean) => {
        const next = new Set(value)
        if (checked) next.add(toolId)
        else next.delete(toolId)
        onChange(Array.from(next))
    }

    const toggleToolset = (toolset: ToolsetGroup, checked: boolean) => {
        const next = new Set(value)
        toolset.member_ids.forEach((memberId) => {
            if (checked) next.add(memberId)
            else next.delete(memberId)
        })
        onChange(Array.from(next))
    }

    const toggleToolsetExpanded = (toolsetId: string) => {
        setExpandedToolsets((current) => ({
            ...current,
            [toolsetId]: !current[toolsetId],
        }))
    }

    const handleOpenChange = (nextOpen: boolean) => {
        onOpenChange?.(nextOpen)
        if (!nextOpen) {
            setView("list")
            setSelectedTool(null)
            setQuery("")
            setBucketFilter("all")
            setExpandedToolsets({})
        }
    }

    const openState = open ?? false

    return (
        <Sheet open={openState} onOpenChange={handleOpenChange}>
            <SheetContent side="right" className="w-full sm:max-w-md flex flex-col p-0 gap-0 overflow-hidden">
                {view === "detail" && selectedTool ? (
                    <div className="flex items-start gap-3 px-5 pt-5 pb-4 border-b">
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 shrink-0 mt-0.5"
                            onClick={() => setView("list")}
                        >
                            <ArrowLeft className="h-4 w-4" />
                        </Button>
                        <div className="min-w-0 flex-1">
                            <SheetTitle className="text-base truncate">{selectedTool.name}</SheetTitle>
                            <SheetDescription className="text-xs mt-0.5 line-clamp-2">
                                {selectedTool.description || "No description"}
                            </SheetDescription>
                        </div>
                        <Checkbox
                            checked={value.includes(selectedTool.id)}
                            onCheckedChange={(checked) => toggleTool(selectedTool.id, Boolean(checked))}
                            className="mt-1.5"
                        />
                    </div>
                ) : (
                    <SheetHeader className="px-5 pt-5 pb-4 border-b space-y-0">
                        <div className="flex items-center justify-between">
                            <div>
                                <SheetTitle className="text-base">Add Tools</SheetTitle>
                                <SheetDescription className="text-xs mt-0.5">
                                    Choose tools for this agent node
                                </SheetDescription>
                            </div>
                            {value.length > 0 && (
                                <Badge variant="secondary" className="text-xs tabular-nums">
                                    {value.length} selected
                                </Badge>
                            )}
                        </div>
                    </SheetHeader>
                )}

                {view === "detail" && selectedTool ? (
                    <ScrollArea className="flex-1">
                        <div className="px-5 py-4">
                            <ToolDefinitionDetailBody tool={selectedTool} />
                        </div>
                    </ScrollArea>
                ) : (
                    <>
                        <div className="px-5 pt-4 pb-2 space-y-3">
                            <div className="relative">
                                <Search className="h-4 w-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                                <Input
                                    placeholder="Search tools..."
                                    value={query}
                                    onChange={(e) => setQuery(e.target.value)}
                                    className="h-9 pl-9 pr-8"
                                />
                                {query && (
                                    <button
                                        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                                        onClick={() => setQuery("")}
                                    >
                                        <X className="h-3.5 w-3.5" />
                                    </button>
                                )}
                            </div>

                            <div className="flex gap-1 overflow-x-auto no-scrollbar">
                                <Button
                                    variant={bucketFilter === "all" ? "default" : "ghost"}
                                    size="sm"
                                    className="h-7 text-xs px-3 shrink-0"
                                    onClick={() => setBucketFilter("all")}
                                >
                                    All
                                    <span className="ml-1.5 text-[10px] opacity-70">{queryFilteredItems.length}</span>
                                </Button>
                                {activeBuckets.map((bucket) => {
                                    const count = allGroupedItems[bucket.id].length
                                    const BucketIcon = BUCKET_ICONS[bucket.id]
                                    return (
                                        <Button
                                            key={bucket.id}
                                            variant={bucketFilter === bucket.id ? "default" : "ghost"}
                                            size="sm"
                                            className="h-7 text-xs px-3 shrink-0"
                                            onClick={() => setBucketFilter(bucket.id)}
                                        >
                                            <BucketIcon className="h-3 w-3 mr-1" />
                                            {bucket.label}
                                            <span className="ml-1.5 text-[10px] opacity-70">{count}</span>
                                        </Button>
                                    )
                                })}
                            </div>
                        </div>

                        <Separator />

                        <ScrollArea className="flex-1 min-h-0 w-full">
                            <div className="px-3 py-2 w-full overflow-hidden">
                                {filteredItems.length === 0 ? (
                                    <div className="flex flex-col items-center justify-center py-12 text-center">
                                        <Search className="h-8 w-8 text-muted-foreground/40 mb-3" />
                                        <p className="text-sm font-medium text-muted-foreground">No tools found</p>
                                        <p className="text-xs text-muted-foreground/70 mt-1">
                                            Try a different search or filter
                                        </p>
                                    </div>
                                ) : (
                                    activeBuckets
                                        .filter((bucket) => displayGroupedItems[bucket.id].length > 0)
                                        .map((bucket) => (
                                            <div key={bucket.id} className="mb-2 w-full">
                                                {bucketFilter === "all" && activeBuckets.length > 1 && (
                                                    <div className="flex items-center gap-2 px-2 pt-3 pb-1.5">
                                                        <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                                                            {bucket.label}
                                                        </span>
                                                        <span className="text-[10px] text-muted-foreground/60">
                                                            {displayGroupedItems[bucket.id].length}
                                                        </span>
                                                    </div>
                                                )}
                                                <div className="space-y-1.5 w-full">
                                                    {displayGroupedItems[bucket.id].map((item) => {
                                                        if (item.kind === "toolset") {
                                                            const toolset = item.toolset
                                                            const selectionState = getToolsetSelectionState(toolset, value)
                                                            const isExpanded = Boolean(expandedToolsets[toolset.id])
                                                            const groupMatches = matchesQuery(toolset.name) || matchesQuery(toolset.description)
                                                            const visibleMembers = normalizedQuery
                                                                ? (groupMatches ? toolset.members : toolset.members.filter((member) => matchesTool(member)))
                                                                : toolset.members

                                                            return (
                                                                <div key={toolset.id} className="rounded-lg border border-transparent">
                                                                    <div
                                                                        className={cn(
                                                                            "group flex w-full min-w-0 items-center gap-3 rounded-lg px-3 py-2.5 transition-colors cursor-pointer",
                                                                            selectionState === "full"
                                                                                ? "bg-primary/5 border border-primary/20"
                                                                                : selectionState === "partial"
                                                                                    ? "bg-primary/5 border border-dashed border-primary/20"
                                                                                    : "hover:bg-muted/50 border border-transparent"
                                                                        )}
                                                                        onClick={() => toggleToolset(toolset, selectionState !== "full")}
                                                                    >
                                                                        <Button
                                                                            variant="ghost"
                                                                            size="icon"
                                                                            className="h-7 w-7 shrink-0"
                                                                            onClick={(e) => {
                                                                                e.stopPropagation()
                                                                                toggleToolsetExpanded(toolset.id)
                                                                            }}
                                                                        >
                                                                            <ChevronRight className={cn("h-4 w-4 transition-transform", isExpanded && "rotate-90")} />
                                                                        </Button>
                                                                        <div className="flex items-center shrink-0">
                                                                            <Checkbox
                                                                                checked={selectionState === "partial" ? "indeterminate" : selectionState === "full"}
                                                                                onCheckedChange={(checked) => toggleToolset(toolset, Boolean(checked))}
                                                                                onClick={(e) => e.stopPropagation()}
                                                                            />
                                                                        </div>
                                                                        <div className="flex-1 min-w-0">
                                                                            <div className="flex items-center gap-2 min-w-0">
                                                                                <span className="text-sm font-medium truncate shrink">
                                                                                    {toolset.name}
                                                                                </span>
                                                                                <Badge variant="outline" className="text-[10px] shrink-0 h-4 px-1.5 whitespace-nowrap">
                                                                                    Toolset
                                                                                </Badge>
                                                                                <Badge variant="outline" className="text-[10px] shrink-0 h-4 px-1.5 whitespace-nowrap">
                                                                                    {toolset.member_ids.length} tools
                                                                                </Badge>
                                                                            </div>
                                                                            <p className="text-xs text-muted-foreground line-clamp-1 mt-0.5 break-all">
                                                                                {toolset.description || "Grouped tool surface"}
                                                                            </p>
                                                                        </div>
                                                                    </div>
                                                                    {isExpanded && visibleMembers.length > 0 && (
                                                                        <div className="mt-1 space-y-1 pl-10">
                                                                            {visibleMembers.map((tool) => {
                                                                                const isSelected = value.includes(tool.id)
                                                                                return (
                                                                                    <div
                                                                                        key={tool.id}
                                                                                        className={cn(
                                                                                            "group flex w-full min-w-0 items-center gap-3 rounded-lg px-3 py-2 transition-colors cursor-pointer",
                                                                                            isSelected
                                                                                                ? "bg-primary/5 border border-primary/20"
                                                                                                : "hover:bg-muted/50 border border-transparent"
                                                                                        )}
                                                                                        onClick={() => toggleTool(tool.id, !isSelected)}
                                                                                    >
                                                                                        <div className="flex items-center shrink-0">
                                                                                            <Checkbox
                                                                                                checked={isSelected}
                                                                                                onCheckedChange={(checked) => toggleTool(tool.id, Boolean(checked))}
                                                                                                onClick={(e) => e.stopPropagation()}
                                                                                            />
                                                                                        </div>
                                                                                        <div className="flex-1 min-w-0">
                                                                                            <div className="flex items-center gap-2 min-w-0">
                                                                                                <span className="text-sm font-medium truncate shrink">
                                                                                                    {tool.name}
                                                                                                </span>
                                                                                                <Badge variant="outline" className="text-[10px] shrink-0 h-4 px-1.5 whitespace-nowrap">
                                                                                                    {getSubtypeLabel(tool.implementation_type)}
                                                                                                </Badge>
                                                                                            </div>
                                                                                            {tool.description && (
                                                                                                <p className="text-xs text-muted-foreground line-clamp-1 mt-0.5 break-all">
                                                                                                    {tool.description}
                                                                                                </p>
                                                                                            )}
                                                                                        </div>
                                                                                        <div className="flex items-center shrink-0">
                                                                                            <Button
                                                                                                variant="ghost"
                                                                                                size="icon"
                                                                                                className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity"
                                                                                                onClick={(e) => {
                                                                                                    e.stopPropagation()
                                                                                                    setSelectedTool(tool)
                                                                                                    setView("detail")
                                                                                                }}
                                                                                            >
                                                                                                <ChevronRight className="h-4 w-4" />
                                                                                            </Button>
                                                                                        </div>
                                                                                    </div>
                                                                                )
                                                                            })}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            )
                                                        }

                                                        const tool = item.tool
                                                        const isSelected = value.includes(tool.id)
                                                        return (
                                                            <div
                                                                key={tool.id}
                                                                className={cn(
                                                                    "group flex w-full min-w-0 items-center gap-3 rounded-lg px-3 py-2.5 transition-colors cursor-pointer",
                                                                    isSelected
                                                                        ? "bg-primary/5 border border-primary/20"
                                                                        : "hover:bg-muted/50 border border-transparent"
                                                                )}
                                                                onClick={() => toggleTool(tool.id, !isSelected)}
                                                            >
                                                                <div className="flex items-center shrink-0">
                                                                    <Checkbox
                                                                        checked={isSelected}
                                                                        onCheckedChange={(checked) => toggleTool(tool.id, Boolean(checked))}
                                                                        onClick={(e) => e.stopPropagation()}
                                                                    />
                                                                </div>
                                                                <div className="flex-1 min-w-0">
                                                                    <div className="flex items-center gap-2 min-w-0">
                                                                        <span className="text-sm font-medium truncate shrink">
                                                                            {tool.name}
                                                                        </span>
                                                                        <Badge variant="outline" className="text-[10px] shrink-0 h-4 px-1.5 whitespace-nowrap">
                                                                            {getSubtypeLabel(tool.implementation_type)}
                                                                        </Badge>
                                                                    </div>
                                                                    {tool.description && (
                                                                        <p className="text-xs text-muted-foreground line-clamp-1 mt-0.5 break-all">
                                                                            {tool.description}
                                                                        </p>
                                                                    )}
                                                                </div>
                                                                <div className="flex items-center shrink-0">
                                                                    <Button
                                                                        variant="ghost"
                                                                        size="icon"
                                                                        className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity"
                                                                        onClick={(e) => {
                                                                            e.stopPropagation()
                                                                            setSelectedTool(tool)
                                                                            setView("detail")
                                                                        }}
                                                                    >
                                                                        <ChevronRight className="h-4 w-4" />
                                                                    </Button>
                                                                </div>
                                                            </div>
                                                        )
                                                    })}
                                                </div>
                                            </div>
                                        ))
                                )}
                            </div>
                        </ScrollArea>

                        <SheetFooter className="border-t px-5 py-3 flex-row items-center justify-between">
                            {value.length > 0 ? (
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="text-xs text-muted-foreground"
                                    onClick={() => onChange([])}
                                >
                                    Clear all
                                </Button>
                            ) : (
                                <div />
                            )}
                            <Button
                                size="sm"
                                onClick={() => handleOpenChange(false)}
                            >
                                <Check className="h-3.5 w-3.5 mr-1.5" />
                                Done
                                {value.length > 0 && (
                                    <span className="ml-1.5 bg-primary-foreground/20 px-1.5 py-0.5 rounded text-[10px]">
                                        {value.length}
                                    </span>
                                )}
                            </Button>
                        </SheetFooter>
                    </>
                )}
            </SheetContent>
        </Sheet>
    )
}
