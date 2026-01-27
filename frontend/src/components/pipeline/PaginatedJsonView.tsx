"use client"

import { useEffect, useState, useCallback } from "react"
import { useTenant } from "@/contexts/TenantContext"
import { ragAdminService, PipelineStepData } from "@/services"
import { ChevronLeft, ChevronRight, Loader2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ExpandableBlock } from "@/components/ui/ExpandableBlock"
import { JsonViewer } from "@/components/ui/JsonViewer"

interface PaginatedJsonViewProps {
    jobId: string
    stepId: string
    type: "input" | "output"
    className?: string
    initialData?: unknown
}

export function PaginatedJsonView({
    jobId,
    stepId,
    type,
    className,
}: PaginatedJsonViewProps) {
    const { currentTenant } = useTenant()

    // State for normal view (small)
    const [data, setData] = useState<PipelineStepData | null>(null)
    const [loading, setLoading] = useState(false)
    const [page, setPage] = useState(1)
    const [limit] = useState(20)

    // State for expanded view (large)
    const [expandedPage, setExpandedPage] = useState(1)
    const [expandedLimit] = useState(100)
    const [expandedData, setExpandedData] = useState<PipelineStepData | null>(null)
    const [expandedLoading, setExpandedLoading] = useState(false)

    // State for viewing a specific large string field
    const [viewingField, setViewingField] = useState<{
        path: string
        content: string
        offset: number
        total: number
        isLoading: boolean
    } | null>(null)

    const fetchData = useCallback(async (p: number, l: number, isExpanded: boolean) => {
        if (!currentTenant) return
        const setter = isExpanded ? setExpandedLoading : setLoading
        const dataSetter = isExpanded ? setExpandedData : setData

        setter(true)
        try {
            const res = await ragAdminService.getStepData(
                jobId,
                stepId,
                type,
                p,
                l,
                currentTenant.slug
            )
            dataSetter(res)
        } catch (error) {
            console.error("Failed to fetch step data", error)
        } finally {
            setter(false)
        }
    }, [jobId, stepId, type, currentTenant])

    // Reset state when job or step changes
    useEffect(() => {
        setData(null)
        setExpandedData(null)
        setPage(1)
        setExpandedPage(1)
        setViewingField(null)
    }, [jobId, stepId])

    // Initial fetch for small view
    useEffect(() => {
        if (!data) {
            fetchData(page, limit, false)
        }
    }, [fetchData, page, limit, data])

    // Fetch for expanded view
    useEffect(() => {
        if (expandedData === null) {
            fetchData(expandedPage, expandedLimit, true)
        }
    }, [expandedPage, expandedLimit, expandedData, fetchData])

    // Effect for pagination in expanded view
    useEffect(() => {
        if (expandedData && expandedData.page !== expandedPage) {
            fetchData(expandedPage, expandedLimit, true)
        }
    }, [expandedPage, expandedLimit, expandedData, fetchData])

    const loadFieldContent = async (path: string, offset: number = 0, append: boolean = false) => {
        if (!currentTenant) return

        setViewingField(prev => ({
            path,
            content: append ? (prev?.content || "") : "",
            offset,
            total: prev?.total || 0,
            isLoading: true
        }))

        try {
            const res = await ragAdminService.getStepFieldContent(
                jobId,
                stepId,
                type,
                path,
                offset,
                50000,
                currentTenant.slug
            )

            setViewingField(prev => ({
                path,
                content: append ? (prev?.content || "") + res.content : res.content,
                offset: res.offset,
                total: res.total_size,
                isLoading: false
            }))
        } catch (error) {
            console.error("Failed to load field content", error)
            setViewingField(null)
        }
    }

    const renderFieldViewer = () => {
        if (!viewingField) return null

        const { path, content, total, isLoading } = viewingField
        const hasMore = content.length < total

        return (
            <div className="flex flex-col h-full w-full bg-background border rounded-lg overflow-hidden">
                <div className="flex items-center justify-between p-2 px-4 border-b bg-muted/50 flex-shrink-0">
                    <div className="flex flex-col overflow-hidden min-w-0">
                        <span className="text-[10px] font-bold text-primary uppercase tracking-wider">Field Inspector</span>
                        <span className="text-xs font-mono truncate">{path}</span>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                        <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                            {(content.length / 1024).toFixed(1)} / {(total / 1024).toFixed(1)} KB
                        </span>
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6"
                            onClick={() => setViewingField(null)}
                        >
                            <X className="h-3.5 w-3.5" />
                        </Button>
                    </div>
                </div>

                <div className="flex-1 overflow-auto p-2 bg-muted/20">
                    <pre className="text-xs font-mono whitespace-pre-wrap break-all">
                        {content}
                    </pre>
                    {isLoading && (
                        <div className="flex items-center justify-center py-4 text-muted-foreground">
                            <Loader2 className="h-4 w-4 animate-spin mr-2" />
                            <span className="text-xs italic">Loading...</span>
                        </div>
                    )}
                    {hasMore && !isLoading && (
                        <div className="flex justify-center py-4">
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => loadFieldContent(path, content.length, true)}
                                className="text-xs h-7"
                            >
                                Load more (+50 KB)
                            </Button>
                        </div>
                    )}
                </div>
            </div>
        )
    }

    const renderContent = (
        currentData: PipelineStepData | null,
        isLoading: boolean,
        currentPage: number,
        onPageChange: (p: number) => void,
        isExpanded: boolean
    ) => {
        if (isLoading && !currentData) {
            return (
                <div className="flex items-center justify-center p-8 text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    Loading data...
                </div>
            )
        }

        if (!currentData || currentData.data === null) {
            return <div className="p-4 text-xs text-muted-foreground italic">No data available</div>
        }

        const { data: content, total, pages, is_list } = currentData

        // If viewing a specific field, show the field viewer
        if (viewingField) {
            return (
                <div className="flex flex-col h-full w-full overflow-hidden">
                    {renderFieldViewer()}
                </div>
            )
        }

        return (
            <div className="flex flex-col h-full w-full overflow-hidden">
                <div className="flex-1 overflow-hidden">
                    <JsonViewer
                        value={content}
                        maxHeight={isExpanded ? "calc(90vh - 80px)" : "150px"}
                        fontSize={isExpanded ? "sm" : "xs"}
                    />
                </div>

                {/* Truncated fields alert */}
                {currentData.truncated_fields && Object.keys(currentData.truncated_fields).length > 0 && (
                    <div className="p-2 bg-primary/5 border-t border-primary/10">
                        <p className="text-[10px] font-bold text-primary uppercase tracking-wide mb-1">
                            Large Fields Detected
                        </p>
                        <div className="flex flex-wrap gap-1">
                            {Object.entries(currentData.truncated_fields).map(([path, info]) => (
                                <Button
                                    key={path}
                                    variant="outline"
                                    size="sm"
                                    className="h-6 px-2 text-[10px] gap-1"
                                    onClick={() => loadFieldContent(path)}
                                >
                                    <span className="font-mono truncate max-w-[100px]">{path}</span>
                                    <span className="text-muted-foreground">({(info.full_size / 1024).toFixed(1)} KB)</span>
                                </Button>
                            ))}
                        </div>
                    </div>
                )}

                {/* Pagination controls */}
                {is_list && pages > 1 && (
                    <div className="flex items-center justify-between p-2 border-t bg-background text-xs flex-shrink-0">
                        <span className="text-muted-foreground">
                            Page {currentPage} of {pages} ({total} items)
                        </span>
                        <div className="flex gap-1">
                            <Button
                                variant="outline"
                                size="icon"
                                className="h-6 w-6"
                                onClick={() => onPageChange(Math.max(1, currentPage - 1))}
                                disabled={currentPage <= 1 || isLoading}
                            >
                                <ChevronLeft className="h-3 w-3" />
                            </Button>
                            <Button
                                variant="outline"
                                size="icon"
                                className="h-6 w-6"
                                onClick={() => onPageChange(Math.min(pages, currentPage + 1))}
                                disabled={currentPage >= pages || isLoading}
                            >
                                <ChevronRight className="h-3 w-3" />
                            </Button>
                        </div>
                    </div>
                )}
            </div>
        )
    }

    return (
        <ExpandableBlock
            title={`${type === 'input' ? 'Input' : 'Output'} Data`}
            className={className}
            contentClassName="max-h-[350px] flex flex-col overflow-hidden"
            renderExpanded={() => renderContent(expandedData, expandedLoading, expandedPage, setExpandedPage, true)}
        >
            {renderContent(data, loading, page, setPage, false)}
        </ExpandableBlock>
    )
}
