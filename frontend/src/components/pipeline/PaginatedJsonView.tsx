
"use client"

import { useEffect, useState, useCallback } from "react"
import { useTenant } from "@/contexts/TenantContext"
import { ragAdminService, PipelineStepData } from "@/services"
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ExpandableBlock } from "@/components/ui/ExpandableBlock"
import { cn } from "@/lib/utils"

interface PaginatedJsonViewProps {
    jobId: string
    stepId: string
    type: "input" | "output"
    className?: string
    initialData?: any // Fallback or initial data (e.g. from lite response if any)
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
    const [limit] = useState(20) // Limit for small view

    // State for expanded view (large)
    const [expandedPage, setExpandedPage] = useState(1)
    const [expandedLimit] = useState(100) // Larger limit for expanded view
    const [expandedData, setExpandedData] = useState<PipelineStepData | null>(null)
    const [expandedLoading, setExpandedLoading] = useState(false)

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
    }, [jobId, stepId])

    // Initial fetch for small view
    useEffect(() => {
        if (!data) {
            fetchData(page, limit, false)
        }
    }, [fetchData, page, limit, data])

    // Fetch for expanded view when page changes (triggered by custom render)
    useEffect(() => {
        // We don't fetch automatically here because we only want to fetch when expanded is actually visible
        // But since `renderExpanded` is called only when modal opens, we can trigger it there or use an effect
        // For simplicity, we'll let the view logic call it or trigger it via a side effect when `expandedPage` changes
        if (expandedData === null) {
            // Initial load for expanded
            fetchData(expandedPage, expandedLimit, true)
        }
    }, [expandedPage, expandedLimit, expandedData, fetchData])

    // Effect for pagination in expanded view
    useEffect(() => {
        if (expandedData && expandedData.page !== expandedPage) {
            fetchData(expandedPage, expandedLimit, true)
        }
    }, [expandedPage, expandedLimit, expandedData, fetchData])


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

        return (
            <div className="flex flex-col h-full w-full min-w-0">
                <div className="flex-1 w-full relative min-h-[200px] bg-muted/30">
                    <div className="absolute inset-0 overflow-auto p-2">
                        <pre className={cn("text-xs font-mono", isExpanded ? "text-sm" : "text-xs")}>
                            {JSON.stringify(content, null, 2)}
                        </pre>
                    </div>
                </div>

                {is_list && pages > 1 && (
                    <div className="flex items-center justify-between p-2 border-t bg-background text-xs">
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
            contentClassName="max-h-[300px] flex flex-col overflow-hidden"
            renderExpanded={() => renderContent(expandedData, expandedLoading, expandedPage, setExpandedPage, true)}
        >
            {renderContent(data, loading, page, setPage, false)}
        </ExpandableBlock>
    )
}
