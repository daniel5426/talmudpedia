"use client"

import { useEffect, useState } from "react"
import { Check, Search, X, GitFork } from "lucide-react"
import { cn } from "@/lib/utils"
import { Input } from "@/components/ui/input"
import { ragAdminService, VisualPipeline } from "@/services/rag-admin"
import { useTenant } from "@/contexts/TenantContext"

interface RetrievalPipelineSelectProps {
    value: string
    onChange: (value: string) => void
    placeholder?: string
    className?: string
}

export function RetrievalPipelineSelect({
    value,
    onChange,
    placeholder = "Select a retrieval pipeline...",
    className
}: RetrievalPipelineSelectProps) {
    const [pipelines, setPipelines] = useState<VisualPipeline[]>([])
    const [loading, setLoading] = useState(true)
    const [showSuggestions, setShowSuggestions] = useState(false)
    const [query, setQuery] = useState("")
    const [selectedIndex, setSelectedIndex] = useState(0)
    const [isFocused, setIsFocused] = useState(false)

    const { currentTenant } = useTenant()

    useEffect(() => {
        async function loadPipelines() {
            try {
                setLoading(true)
                const data = await ragAdminService.listVisualPipelines(currentTenant?.slug)
                // Filter for retrieval pipelines only
                const retrievalPipelines = data.pipelines.filter(p => p.pipeline_type === "retrieval")
                setPipelines(retrievalPipelines)
            } catch (error) {
                console.error("Failed to load pipelines:", error)
            } finally {
                setLoading(false)
            }
        }
        loadPipelines()
    }, [currentTenant?.slug])

    // Get the label for the current value
    const selectedPipeline = pipelines.find(p => p.id === value)

    // Sync query when value changes and we are not typing
    useEffect(() => {
        if (!isFocused) {
            setQuery(selectedPipeline?.name || value || "")
        }
    }, [value, selectedPipeline, isFocused])

    const isValid = !value || !!selectedPipeline || (pipelines.length === 0 && loading)

    const filteredPipelines = pipelines.filter(p =>
        p.name.toLowerCase().includes(query.toLowerCase()) ||
        p.id.toLowerCase().includes(query.toLowerCase())
    )

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (!showSuggestions || filteredPipelines.length === 0) return

        if (e.key === "ArrowDown") {
            e.preventDefault()
            setSelectedIndex(i => (i + 1) % filteredPipelines.length)
        } else if (e.key === "ArrowUp") {
            e.preventDefault()
            setSelectedIndex(i => (i - 1 + filteredPipelines.length) % filteredPipelines.length)
        } else if (e.key === "Enter" || e.key === "Tab") {
            e.preventDefault()
            const selected = filteredPipelines[selectedIndex]
            if (selected) {
                onChange(selected.id)
                setQuery(selected.name)
                setShowSuggestions(false)
            }
        } else if (e.key === "Escape") {
            setShowSuggestions(false)
        }
    }

    const handleBlur = () => {
        setIsFocused(false)

        // Check if what was typed matches a pipeline exactly (by name or ID)
        const exactMatch = pipelines.find(p =>
            p.name.toLowerCase() === query.trim().toLowerCase() ||
            p.id.toLowerCase() === query.trim().toLowerCase()
        )

        if (exactMatch) {
            onChange(exactMatch.id)
            setQuery(exactMatch.name)
        } else if (query.trim() === "") {
            onChange("")
            setQuery("")
        } else {
            // It's invalid, but we set it anyway to show the error
            onChange(query.trim())
        }

        // Close suggestions immediately
        setShowSuggestions(false)
    }

    return (
        <div className="relative">
            <div className="relative">
                <Input
                    value={query}
                    onChange={(e) => {
                        setQuery(e.target.value)
                        setShowSuggestions(true)
                    }}
                    onFocus={() => {
                        setIsFocused(true)
                        setShowSuggestions(true)
                    }}
                    onKeyDown={handleKeyDown}
                    placeholder={loading ? "Loading pipelines..." : placeholder}
                    className={cn(
                        "h-9 px-3 bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0 placeholder:text-muted-foreground/40 font-mono pr-8 transition-all",
                        !isValid && "ring-1 ring-destructive bg-destructive/5",
                        className
                    )}
                    onBlur={handleBlur}
                />
                <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
                    {query && (
                        <button
                            className="text-muted-foreground/40 hover:text-muted-foreground"
                            onClick={() => {
                                setQuery("")
                                onChange("")
                            }}
                        >
                            <X className="h-3 w-3" />
                        </button>
                    )}
                    <GitFork className="h-3.5 w-3.5 text-muted-foreground/30" />
                </div>
            </div>

            {showSuggestions && filteredPipelines.length > 0 && (
                <div className="absolute z-50 w-full mt-1 bg-popover text-popover-foreground shadow-md rounded-md border border-border p-1 max-h-[200px] overflow-auto">
                    {filteredPipelines.map((pipeline, idx) => (
                        <div
                            key={pipeline.id}
                            className={cn(
                                "flex flex-col px-2 py-1.5 text-xs rounded-sm cursor-pointer",
                                idx === selectedIndex ? "bg-accent text-accent-foreground" : "hover:bg-muted"
                            )}
                            onMouseDown={(e) => {
                                e.preventDefault() // Prevent blurring the input
                                onChange(pipeline.id)
                                setQuery(pipeline.name)
                                setShowSuggestions(false)
                            }}
                        >
                            <div className="flex items-center justify-between">
                                <span className="font-medium">{pipeline.name}</span>
                                {pipeline.id === value && <Check className="h-3 w-3 text-primary" />}
                            </div>
                            <div className="flex items-center gap-2 text-[10px] opacity-50 font-mono truncate">
                                <span>{pipeline.id.substring(0, 8)}...</span>
                                <span>•</span>
                                <span className="capitalize">v{pipeline.version || 1}</span>
                                <span>•</span>
                                <span>{pipeline.nodes.length} nodes</span>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}
