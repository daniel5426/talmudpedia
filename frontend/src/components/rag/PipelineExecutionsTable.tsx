"use client"

import React from "react"
import { useDirection } from "@/components/direction-provider"
import { PipelineJob, VisualPipeline } from "@/services"
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
    CheckCircle2,
    XCircle,
    Loader2,
    Activity,
    History,
} from "lucide-react"
import { cn } from "@/lib/utils"
import Link from "next/link"

export function JobStatusBadge({ status }: { status: string }) {
    const { direction } = useDirection()
    const isRTL = direction === "rtl"
    const variants: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
        completed: "default",
        running: "secondary",
        pending: "outline",
        failed: "destructive",
        cancelled: "outline",
        queued: "outline"
    }

    const icons: Record<string, React.ReactNode> = {
        completed: <CheckCircle2 className={cn("h-3 w-3", isRTL ? "ml-1" : "mr-1")} />,
        running: <Loader2 className={cn("h-3 w-3 animate-spin", isRTL ? "ml-1" : "mr-1")} />,
        failed: <XCircle className={cn("h-3 w-3", isRTL ? "ml-1" : "mr-1")} />,
        queued: <Activity className={cn("h-3 w-3", isRTL ? "ml-1" : "mr-1")} />,
    }

    return (
        <Badge variant={variants[status] || "outline"} className="capitalize">
            {icons[status]}
            {status}
        </Badge>
    )
}

interface PipelineExecutionsTableProps {
    jobs: PipelineJob[]
    pipelines: VisualPipeline[]
    onRefresh?: () => void
    isLoading?: boolean
}

export function PipelineExecutionsTable({
    jobs,
    pipelines,
    onRefresh,
    isLoading
}: PipelineExecutionsTableProps) {
    const { direction } = useDirection()
    const isRTL = direction === "rtl"

    if (jobs.length === 0) {
        return (
            <div className="text-center text-muted-foreground py-8">
                No pipeline executions found.
            </div>
        )
    }

    return (
        <Table>
            <TableHeader>
                <TableRow>
                    <TableHead className={isRTL ? "text-right" : "text-left"}>Pipeline</TableHead>
                    <TableHead className={isRTL ? "text-right" : "text-left"}>Triggered By</TableHead>
                    <TableHead className={isRTL ? "text-right" : "text-left"}>Status</TableHead>
                    <TableHead className={isRTL ? "text-right" : "text-left"}>Started</TableHead>
                    <TableHead className={isRTL ? "text-right" : "text-left"}>Duration</TableHead>
                    <TableHead className={isRTL ? "text-left" : "text-right"}>Actions</TableHead>
                </TableRow>
            </TableHeader>
            <TableBody>
                {jobs.map((job) => (
                    <TableRow key={job.id}>
                        <TableCell className={cn("font-medium", isRTL ? "text-right" : "text-left")}>
                            <div className="flex flex-col">
                                <span className="text-xs font-mono opacity-50">{job.executable_pipeline_id.slice(-8)}</span>
                                <span>{pipelines.find(p => p.id === job.executable_pipeline_id)?.name || "Pipeline"}</span>
                            </div>
                        </TableCell>
                        <TableCell className={isRTL ? "text-right" : "text-left"}>{job.triggered_by}</TableCell>
                        <TableCell className={isRTL ? "text-right" : "text-left"}>
                            <JobStatusBadge status={job.status} />
                        </TableCell>
                        <TableCell className={isRTL ? "text-right" : "text-left"}>
                            {new Date(job.created_at).toLocaleString()}
                        </TableCell>
                        <TableCell className={isRTL ? "text-right" : "text-left"}>
                            {job.finished_at && job.started_at ?
                                `${Math.round((new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()) / 1000)}s`
                                : "-"}
                        </TableCell>
                        <TableCell className={isRTL ? "text-left" : "text-right"}>
                            <div className="flex justify-end">
                                <Button variant="ghost" size="icon" asChild title="View History">
                                    <Link href={`/admin/pipelines/${job.executable_pipeline_id}?jobId=${job.id}`}>
                                        <History className="h-4 w-4" />
                                    </Link>
                                </Button>
                            </div>
                        </TableCell>
                    </TableRow>
                ))}
            </TableBody>
        </Table>
    )
}
