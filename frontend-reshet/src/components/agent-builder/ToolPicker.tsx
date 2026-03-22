"use client"

import { useMemo, useState } from "react"
import { ToolDefinition, ToolImplementationType, ToolTypeBucket } from "@/services/agent"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetFooter } from "@/components/ui/sheet"
import { Search, X, ArrowLeft, Check, Wrench, Globe, Box, Code2, ChevronRight } from "lucide-react"
import { TOOL_BUCKETS, filterTools, getToolBucket, getSubtypeLabel } from "@/lib/tool-types"
import { cn } from "@/lib/utils"

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

export function ToolPicker({ tools, value, onChange, open, onOpenChange }: ToolPickerProps) {
    const [query, setQuery] = useState("")
    const [bucketFilter, setBucketFilter] = useState<ToolTypeBucket | "all">("all")
    const [selectedTool, setSelectedTool] = useState<ToolDefinition | null>(null)
    const [view, setView] = useState<"list" | "detail">("list")

    // Tools filtered by query only (for stable tab counts)
    const queryFilteredTools = useMemo(() => {
        return filterTools(tools || [], {
            query,
            bucket: "all",
            subtype: "all" as ToolImplementationType | "all",
            status: "all",
        })
    }, [tools, query])

    // Tools filtered by query + bucket (for the list)
    const filteredTools = useMemo(() => {
        if (bucketFilter === "all") return queryFilteredTools
        return queryFilteredTools.filter((tool) => getToolBucket(tool) === bucketFilter)
    }, [queryFilteredTools, bucketFilter])

    // Group query-filtered tools by bucket (stable counts for tabs)
    const allGroupedTools = useMemo(() => {
        const groups: Record<ToolTypeBucket, ToolDefinition[]> = {
            built_in: [],
            mcp: [],
            artifact: [],
            custom: [],
        }
        queryFilteredTools.forEach((tool) => {
            const bucket = getToolBucket(tool)
            groups[bucket].push(tool)
        })
        return groups
    }, [queryFilteredTools])

    // Group displayed tools by bucket (for the list rendering)
    const displayGroupedTools = useMemo(() => {
        const groups: Record<ToolTypeBucket, ToolDefinition[]> = {
            built_in: [],
            mcp: [],
            artifact: [],
            custom: [],
        }
        filteredTools.forEach((tool) => {
            const bucket = getToolBucket(tool)
            groups[bucket].push(tool)
        })
        return groups
    }, [filteredTools])

    // Show all buckets that have tools (based on query filter, not bucket filter)
    const activeBuckets = useMemo(() => {
        return TOOL_BUCKETS.filter((b) => allGroupedTools[b.id].length > 0)
    }, [allGroupedTools])

    const toggleTool = (toolId: string, checked: boolean) => {
        const next = new Set(value)
        if (checked) next.add(toolId)
        else next.delete(toolId)
        onChange(Array.from(next))
    }

    const handleOpenChange = (nextOpen: boolean) => {
        onOpenChange?.(nextOpen)
        if (!nextOpen) {
            setView("list")
            setSelectedTool(null)
            setQuery("")
            setBucketFilter("all")
        }
    }

    const openState = open ?? false

    return (
        <Sheet open={openState} onOpenChange={handleOpenChange}>
            <SheetContent side="right" className="w-full sm:max-w-md flex flex-col p-0 gap-0">
                {/* ── Header ── */}
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

                {/* ── Detail view ── */}
                {view === "detail" && selectedTool ? (
                    <ScrollArea className="flex-1">
                        <div className="px-5 py-4 space-y-5">
                            {/* Meta badges */}
                            <div className="flex flex-wrap gap-1.5">
                                <Badge variant="secondary" className="text-xs">
                                    {TOOL_BUCKETS.find((b) => b.id === getToolBucket(selectedTool))?.label ?? getToolBucket(selectedTool)}
                                </Badge>
                                <Badge variant="outline" className="text-xs">
                                    {getSubtypeLabel(selectedTool.implementation_type)}
                                </Badge>
                                <Badge variant="outline" className="text-xs">
                                    v{selectedTool.version}
                                </Badge>
                                <Badge
                                    variant={selectedTool.status === "published" ? "default" : "outline"}
                                    className="text-xs"
                                >
                                    {selectedTool.status}
                                </Badge>
                            </div>

                            {/* Slug */}
                            <div>
                                <div className="text-xs font-medium text-muted-foreground mb-1">Identifier</div>
                                <code className="text-xs bg-muted px-2 py-1 rounded font-mono block">
                                    {selectedTool.slug}
                                </code>
                            </div>

                            {/* Input Schema */}
                            {selectedTool.input_schema && Object.keys(selectedTool.input_schema).length > 0 && (
                                <div>
                                    <div className="text-xs font-medium text-muted-foreground mb-2">Input Schema</div>
                                    <pre className="text-xs bg-muted rounded-md p-3 overflow-x-auto max-h-[200px] overflow-y-auto font-mono leading-relaxed">
                                        {JSON.stringify(selectedTool.input_schema, null, 2)}
                                    </pre>
                                </div>
                            )}

                            {/* Output Schema */}
                            {selectedTool.output_schema && Object.keys(selectedTool.output_schema).length > 0 && (
                                <div>
                                    <div className="text-xs font-medium text-muted-foreground mb-2">Output Schema</div>
                                    <pre className="text-xs bg-muted rounded-md p-3 overflow-x-auto max-h-[200px] overflow-y-auto font-mono leading-relaxed">
                                        {JSON.stringify(selectedTool.output_schema, null, 2)}
                                    </pre>
                                </div>
                            )}
                        </div>
                    </ScrollArea>
                ) : (
                    /* ── List view ── */
                    <>
                        {/* Search + filter bar */}
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

                            {/* Bucket tabs */}
                            <div className="flex gap-1 overflow-x-auto">
                                <Button
                                    variant={bucketFilter === "all" ? "default" : "ghost"}
                                    size="sm"
                                    className="h-7 text-xs px-3 shrink-0"
                                    onClick={() => setBucketFilter("all")}
                                >
                                    All
                                    <span className="ml-1.5 text-[10px] opacity-70">{queryFilteredTools.length}</span>
                                </Button>
                                {activeBuckets.map((bucket) => {
                                    const count = allGroupedTools[bucket.id].length
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

                        {/* Tool list */}
                        <ScrollArea className="flex-1 min-h-0">
                            <div className="px-3 py-2">
                                {filteredTools.length === 0 ? (
                                    <div className="flex flex-col items-center justify-center py-12 text-center">
                                        <Search className="h-8 w-8 text-muted-foreground/40 mb-3" />
                                        <p className="text-sm font-medium text-muted-foreground">No tools found</p>
                                        <p className="text-xs text-muted-foreground/70 mt-1">
                                            Try a different search or filter
                                        </p>
                                    </div>
                                ) : (
                                    activeBuckets
                                        .filter((bucket) => displayGroupedTools[bucket.id].length > 0)
                                        .map((bucket) => (
                                        <div key={bucket.id} className="mb-2">
                                            {/* Only show group header when showing all buckets */}
                                            {bucketFilter === "all" && activeBuckets.length > 1 && (
                                                <div className="flex items-center gap-2 px-2 pt-3 pb-1.5">
                                                    <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                                                        {bucket.label}
                                                    </span>
                                                    <span className="text-[10px] text-muted-foreground/60">
                                                        {displayGroupedTools[bucket.id].length}
                                                    </span>
                                                </div>
                                            )}
                                            <div className="space-y-1.5">
                                            {displayGroupedTools[bucket.id].map((tool) => {
                                                const isSelected = value.includes(tool.id)
                                                return (
                                                    <div
                                                        key={tool.id}
                                                        className={cn(
                                                            "group flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors cursor-pointer",
                                                            isSelected
                                                                ? "bg-primary/5 border border-primary/20"
                                                                : "hover:bg-muted/50 border border-transparent"
                                                        )}
                                                        onClick={() => toggleTool(tool.id, !isSelected)}
                                                    >
                                                        <Checkbox
                                                            checked={isSelected}
                                                            onCheckedChange={(checked) => toggleTool(tool.id, Boolean(checked))}
                                                            onClick={(e) => e.stopPropagation()}
                                                            className="shrink-0"
                                                        />
                                                        <div className="flex-1 min-w-0">
                                                            <div className="flex items-center gap-2">
                                                                <span className="text-sm font-medium truncate">
                                                                    {tool.name}
                                                                </span>
                                                                <Badge variant="outline" className="text-[10px] shrink-0 h-4 px-1.5">
                                                                    {getSubtypeLabel(tool.implementation_type)}
                                                                </Badge>
                                                            </div>
                                                            {tool.description && (
                                                                <p className="text-xs text-muted-foreground line-clamp-1 mt-0.5">
                                                                    {tool.description}
                                                                </p>
                                                            )}
                                                        </div>
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            className="h-7 w-7 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                                                            onClick={(e) => {
                                                                e.stopPropagation()
                                                                setSelectedTool(tool)
                                                                setView("detail")
                                                            }}
                                                        >
                                                            <ChevronRight className="h-4 w-4" />
                                                        </Button>
                                                    </div>
                                                )
                                            })}
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>
                        </ScrollArea>

                        {/* Footer */}
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
