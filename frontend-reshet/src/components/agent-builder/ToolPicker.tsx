"use client"

import { useMemo, useState } from "react"
import { ToolDefinition, ToolImplementationType, ToolStatus, ToolTypeBucket } from "@/services/agent"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet"
import { Search, Layers, Filter, X, Info, ArrowLeft } from "lucide-react"
import { TOOL_BUCKETS, TOOL_SUBTYPES, filterTools, getToolBucket, getSubtypeLabel } from "@/lib/tool-types"
import { cn } from "@/lib/utils"

interface ToolPickerProps {
    tools: ToolDefinition[]
    value: string[]
    onChange: (next: string[]) => void
    open?: boolean
    onOpenChange?: (open: boolean) => void
}

export function ToolPicker({ tools, value, onChange, open, onOpenChange }: ToolPickerProps) {
    const [query, setQuery] = useState("")
    const [bucketFilter, setBucketFilter] = useState<ToolTypeBucket | "all">("all")
    const [subtypeFilter, setSubtypeFilter] = useState<ToolImplementationType | "all">("all")
    const [selectedTool, setSelectedTool] = useState<ToolDefinition | null>(null)
    const [view, setView] = useState<"list" | "detail">("list")

    const filteredTools = useMemo(() => filterTools(tools, {
        query,
        bucket: bucketFilter,
        subtype: subtypeFilter,
        status: "all" as ToolStatus | "all",
    }), [tools, query, bucketFilter, subtypeFilter])

    const groupedTools = useMemo(() => {
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
        }
    }

    const openState = open ?? false

    return (
        <Sheet open={openState} onOpenChange={handleOpenChange}>
        <SheetContent side="right" className="w-full sm:max-w-lg flex flex-col">
                <SheetHeader className="flex-row items-center justify-between">
                    {view === "detail" ? (
                        <div className="flex items-center gap-2">
                            <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                onClick={() => setView("list")}
                            >
                                <ArrowLeft className="h-4 w-4" />
                            </Button>
                            <div>
                                <SheetTitle>{selectedTool?.name}</SheetTitle>
                                <SheetDescription>{selectedTool?.description}</SheetDescription>
                            </div>
                        </div>
                    ) : (
                        <div>
                            <SheetTitle>Select Tools</SheetTitle>
                            <SheetDescription>Attach tools to this agent node.</SheetDescription>
                        </div>
                    )}
                </SheetHeader>

                {view === "detail" && selectedTool ? (
                    <div className="px-4 pb-6 space-y-3 overflow-y-auto">
                        <div className="text-xs text-muted-foreground font-mono">{selectedTool.slug}</div>
                        <div className="flex flex-wrap gap-2">
                            <Badge variant="secondary">{getToolBucket(selectedTool)}</Badge>
                            <Badge variant="outline">{getSubtypeLabel(selectedTool.implementation_type)}</Badge>
                            <Badge variant="outline">v{selectedTool.version}</Badge>
                        </div>
                        <div className="text-[11px] text-muted-foreground">Status: {selectedTool.status}</div>
                        <div className="space-y-1">
                            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Input Schema</div>
                            <pre className="text-[10px] bg-muted/50 rounded-md p-2 overflow-auto max-h-[160px]">
                                {JSON.stringify(selectedTool.input_schema, null, 2)}
                            </pre>
                        </div>
                        <div className="space-y-1">
                            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Output Schema</div>
                            <pre className="text-[10px] bg-muted/50 rounded-md p-2 overflow-auto max-h-[160px]">
                                {JSON.stringify(selectedTool.output_schema, null, 2)}
                            </pre>
                        </div>
                    </div>
                ) : (
                    <div className="px-4 pb-6 space-y-3 flex-1 min-h-0 flex flex-col">
                        <div className="flex items-center gap-2">
                            <div className="relative flex-1">
                                <Input
                                    placeholder="Search tools..."
                                    value={query}
                                    onChange={(e) => setQuery(e.target.value)}
                                    className="h-9 pr-8 focus-visible:ring-0 focus-visible:ring-offset-0"
                                />
                                <Search className="h-4 w-4 text-muted-foreground absolute right-2 top-1/2 -translate-y-1/2" />
                            </div>
                            {query && (
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-9 w-9"
                                    onClick={() => setQuery("")}
                                >
                                    <X className="h-4 w-4" />
                                </Button>
                            )}
                        </div>

                        <div className="space-y-2">
                            <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                                <Filter className="h-3 w-3" />
                                Bucket
                            </div>
                            <div className="flex flex-wrap gap-1">
                                <Button
                                    variant={bucketFilter === "all" ? "default" : "outline"}
                                    size="sm"
                                    className="h-7 text-[11px]"
                                    onClick={() => setBucketFilter("all")}
                                >
                                    All
                                </Button>
                                {TOOL_BUCKETS.map((bucket) => (
                                    <Button
                                        key={bucket.id}
                                        variant={bucketFilter === bucket.id ? "default" : "outline"}
                                        size="sm"
                                        className="h-7 text-[11px]"
                                        onClick={() => setBucketFilter(bucket.id)}
                                    >
                                        {bucket.label}
                                    </Button>
                                ))}
                            </div>
                        </div>

                        <div className="space-y-2">
                            <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                                <Filter className="h-3 w-3" />
                                Subtype
                            </div>
                            <div className="flex flex-wrap gap-1">
                                <Button
                                    variant={subtypeFilter === "all" ? "default" : "outline"}
                                    size="sm"
                                    className="h-7 text-[11px]"
                                    onClick={() => setSubtypeFilter("all")}
                                >
                                    All
                                </Button>
                                {TOOL_SUBTYPES.map((subtype) => (
                                    <Button
                                        key={subtype.id}
                                        variant={subtypeFilter === subtype.id ? "default" : "outline"}
                                        size="sm"
                                        className="h-7 text-[11px]"
                                        onClick={() => setSubtypeFilter(subtype.id)}
                                    >
                                        {subtype.label}
                                    </Button>
                                ))}
                            </div>
                        </div>

                        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                            <span>{value.length} selected</span>
                            {value.length > 0 && (
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 text-[11px]"
                                    onClick={() => onChange([])}
                                >
                                    Clear all
                                </Button>
                            )}
                        </div>

                        <div className="space-y-3 flex-1 min-h-0 overflow-y-auto p-2">
                            {TOOL_BUCKETS.map((bucket) => (
                                <div key={bucket.id} className="space-y-2">
                                    <div className="flex items-center gap-2 text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
                                        <Layers className="h-3 w-3" />
                                        {bucket.label}
                                    </div>
                                    {groupedTools[bucket.id].length === 0 ? (
                                        <div className="text-[11px] text-muted-foreground">No tools</div>
                                    ) : (
                                        groupedTools[bucket.id].map((tool) => (
                                            <div
                                                key={tool.id}
                                                className={cn(
                                                    "flex items-start gap-2 rounded-md p-2 hover:bg-muted/40",
                                                    value.includes(tool.id) && "bg-muted/30"
                                                )}
                                            >
                                                <Checkbox
                                                    id={`tool-${tool.id}`}
                                                    aria-label={tool.name}
                                                    checked={value.includes(tool.id)}
                                                    onCheckedChange={(checked) => toggleTool(tool.id, Boolean(checked))}
                                                />
                                                <label htmlFor={`tool-${tool.id}`} className="flex-1 cursor-pointer">
                                                    <div className="flex items-center justify-between">
                                                        <span className="text-xs font-medium">{tool.name}</span>
                                                        <Badge variant="outline" className="text-[10px]">
                                                            {getSubtypeLabel(tool.implementation_type)}
                                                        </Badge>
                                                    </div>
                                                    <div className="text-[10px] text-muted-foreground font-mono">{tool.slug}</div>
                                                    {tool.description && (
                                                        <div className="text-[10px] text-muted-foreground line-clamp-1">{tool.description}</div>
                                                    )}
                                                </label>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-7 w-7"
                                                    onClick={() => {
                                                        setSelectedTool(tool)
                                                        setView("detail")
                                                    }}
                                                >
                                                    <Info className="h-3.5 w-3.5" />
                                                </Button>
                                            </div>
                                        ))
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </SheetContent>
        </Sheet>
    )
}
