import React, { useEffect, useRef, useState } from 'react'
import { Agent } from "@/services"
import { BarChart } from "@/components/admin/stats/BarChart"
import { ArrowUpRight, Check, Copy, MoreHorizontal } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"
import type { DailyDataPoint } from "@/services"

export const AGENT_METRIC_VARIANTS = [
    { id: "quiet-grid", label: "Quiet Grid" },
    { id: "editorial-columns", label: "Editorial Columns" },
    { id: "soft-inline", label: "Soft Inline" },
    { id: "mono-strip", label: "Mono Strip" },
    { id: "centered-triad", label: "Centered Triad" },
    { id: "caption-stack", label: "Caption Stack" },
    { id: "signal-row", label: "Signal Row" },
    { id: "micro-caps", label: "Micro Caps" },
    { id: "numeric-band", label: "Numeric Band" },
    { id: "soft-ledger", label: "Soft Ledger" },
] as const

export type AgentMetricVariant = typeof AGENT_METRIC_VARIANTS[number]["id"]

interface AgentCardProps {
    agent: Agent
    metrics?: {
        threads: number
        runs: number
        failureRate: number
        threadTrend?: DailyDataPoint[]
    }
    metricVariant?: AgentMetricVariant
    onDelete?: (agent: Agent) => void
    onOpen?: (agent: Agent) => void // Should navigate to builder
    onRun?: (agent: Agent) => void  // Should navigate to playground
    onPlayground?: (agent: Agent) => void // Alternative to onRun
    className?: string
}

function formatMetricNumber(value: number) {
    return value.toLocaleString()
}

function renderMetrics(metrics: NonNullable<AgentCardProps["metrics"]>, variant: AgentMetricVariant) {
    const items = [
        { label: "Threads", value: formatMetricNumber(metrics.threads) },
        { label: "Runs 7d", value: formatMetricNumber(metrics.runs) },
        { label: "Fail Rate", value: `${metrics.failureRate.toFixed(1)}%` },
    ]

    switch (variant) {
        case "editorial-columns":
            return (
                <div className="mt-5 grid grid-cols-3 gap-4">
                    {items.map((item) => (
                        <div key={item.label} className="space-y-1">
                            <div className="text-xl font-semibold tracking-tight tabular-nums">{item.value}</div>
                            <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{item.label}</div>
                        </div>
                    ))}
                </div>
            )
        case "soft-inline":
            return (
                <div className="mt-5 flex flex-wrap items-baseline gap-x-5 gap-y-2">
                    {items.map((item) => (
                        <div key={item.label} className="flex items-baseline gap-2">
                            <span className="text-lg font-semibold tabular-nums">{item.value}</span>
                            <span className="text-sm text-muted-foreground">{item.label}</span>
                        </div>
                    ))}
                </div>
            )
        case "mono-strip":
            return (
                <div className="mt-5 flex flex-wrap items-center gap-3 font-mono text-sm">
                    {items.map((item, index) => (
                        <React.Fragment key={item.label}>
                            <div className="flex items-center gap-2">
                                <span className="text-foreground tabular-nums">{item.value}</span>
                                <span className="text-muted-foreground">{item.label}</span>
                            </div>
                            {index < items.length - 1 ? <span className="text-border">/</span> : null}
                        </React.Fragment>
                    ))}
                </div>
            )
        case "centered-triad":
            return (
                <div className="mt-5 grid grid-cols-3 gap-3 text-center">
                    {items.map((item) => (
                        <div key={item.label} className="space-y-1">
                            <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{item.label}</div>
                            <div className="text-2xl font-medium tabular-nums">{item.value}</div>
                        </div>
                    ))}
                </div>
            )
        case "caption-stack":
            return (
                <div className="mt-5 space-y-2">
                    {items.map((item) => (
                        <div key={item.label} className="flex items-baseline justify-between gap-4">
                            <span className="text-sm text-muted-foreground">{item.label}</span>
                            <span className="text-lg font-semibold tabular-nums">{item.value}</span>
                        </div>
                    ))}
                </div>
            )
        case "signal-row":
            return (
                <div className="mt-5 flex flex-wrap items-center gap-4">
                    {items.map((item) => (
                        <div key={item.label} className="flex items-center gap-2">
                            <span className="h-1.5 w-1.5 rounded-full bg-foreground/40" />
                            <div className="flex items-baseline gap-2">
                                <span className="text-base font-semibold tabular-nums">{item.value}</span>
                                <span className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{item.label}</span>
                            </div>
                        </div>
                    ))}
                </div>
            )
        case "micro-caps":
            return (
                <div className="mt-5 grid grid-cols-3 gap-3">
                    {items.map((item) => (
                        <div key={item.label} className="space-y-2">
                            <div className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground">{item.label}</div>
                            <div className="text-base font-semibold tabular-nums">{item.value}</div>
                            <div className="h-px w-6 bg-foreground/15" />
                        </div>
                    ))}
                </div>
            )
        case "numeric-band":
            return (
                <div className="mt-5">
                    <div className="flex items-end gap-4">
                        {items.map((item, index) => (
                            <React.Fragment key={item.label}>
                                <div className="min-w-0 flex-1">
                                    <div className="text-[11px] text-muted-foreground">{item.label}</div>
                                    <div className="mt-1 text-2xl font-light tabular-nums tracking-tight">{item.value}</div>
                                </div>
                                {index < items.length - 1 ? <div className="h-8 w-px bg-border/60" /> : null}
                            </React.Fragment>
                        ))}
                    </div>
                </div>
            )
        case "soft-ledger":
            return (
                <div className="mt-5 space-y-3">
                    <div className="grid grid-cols-[1fr_auto] items-baseline gap-3">
                        <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Threads</span>
                        <span className="text-base font-medium tabular-nums">{formatMetricNumber(metrics.threads)}</span>
                    </div>
                    <div className="space-y-2">
                        <div className="grid grid-cols-[1fr_auto] items-center gap-3">
                            <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Last 7d Thread Trend</span>
                            <span className="text-[11px] text-muted-foreground">{metrics.threadTrend?.length || 0} pts</span>
                        </div>
                        <BarChart
                            data={metrics.threadTrend || []}
                            height={82}
                            color="#8b5cf6"
                            showLabels={false}
                            className="rounded-md"
                        />
                    </div>
                </div>
            )
        case "quiet-grid":
        default:
            return (
                <div className="mt-5 grid grid-cols-3 gap-3">
                    {items.map((item) => (
                        <div key={item.label} className="space-y-1">
                            <div className="text-[11px] text-muted-foreground">{item.label}</div>
                            <div className="text-xl font-semibold tabular-nums tracking-tight">{item.value}</div>
                        </div>
                    ))}
                </div>
            )
    }
}

export function AgentCard({ agent, metrics, metricVariant = "quiet-grid", onOpen, onRun, onDelete, onPlayground, className }: AgentCardProps) {
    const [idCopied, setIdCopied] = useState(false)
    const copyResetTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    useEffect(() => {
        return () => {
            if (copyResetTimeoutRef.current) {
                clearTimeout(copyResetTimeoutRef.current)
            }
        }
    }, [])

    const handleOpen = (e: React.MouseEvent) => {
        e.preventDefault();
        onOpen?.(agent);
    }

    const handleCopyId = async () => {
        if (typeof window === "undefined" || !navigator?.clipboard?.writeText) {
            return
        }
        await navigator.clipboard.writeText(agent.id)
        setIdCopied(true)
        if (copyResetTimeoutRef.current) {
            clearTimeout(copyResetTimeoutRef.current)
        }
        copyResetTimeoutRef.current = setTimeout(() => {
            setIdCopied(false)
        }, 2000)
    }

    return (
        <div
            onClick={handleOpen}
            className={cn(
                "group relative flex min-h-[250px] flex-col justify-between bg-card text-card-foreground border rounded-xl p-5 shadow-sm transition-all duration-200 hover:shadow-md hover:border-primary/20 cursor-pointer overflow-hidden",
                className
            )}
        >
            {/* Background Decoration */}
            <div className="absolute top-0 right-0 p-20 bg-gradient-to-br from-transparent to-muted/20 rounded-bl-full pointer-events-none" />

            {/* Header */}
            <div className="flex items-center justify-between relative z-10">
                <div className="flex items-center gap-2">
                    <div className={cn(
                        "h-2 w-2 rounded-full",
                        agent.status === 'published' ? "bg-emerald-500" :
                            agent.status === 'draft' ? "bg-zinc-300" : "bg-amber-500"
                    )} />
                    <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        {agent.status}
                    </span>
                </div>

                <div className="opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-6 w-6 -mr-1">
                                <MoreHorizontal className="h-3.5 w-3.5 lg:h-4 lg:w-4" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => onOpen?.(agent)}>Edit Agent</DropdownMenuItem>
                            <DropdownMenuItem onClick={() => (onPlayground || onRun)?.(agent)}>Run Playground</DropdownMenuItem>
                            <DropdownMenuItem onClick={handleCopyId}>
                                {idCopied ? (
                                    <>
                                        <Check className="mr-2 h-3.5 w-3.5" />
                                        Copied ID
                                    </>
                                ) : (
                                    <>
                                        <Copy className="mr-2 h-3.5 w-3.5" />
                                        Copy ID
                                    </>
                                )}
                            </DropdownMenuItem>
                            {onDelete && (
                                <>
                                    <DropdownMenuSeparator />
                                    <DropdownMenuItem className="text-destructive" onClick={() => onDelete(agent)}>Delete</DropdownMenuItem>
                                </>
                            )}
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
            </div>

            {/* Main Content */}
            <div className="relative z-10 my-2">
                <h3 className="text-xl font-bold tracking-tight text-foreground truncate group-hover:text-primary transition-colors">
                    {agent.name}
                </h3>
                <p className="text-xs text-muted-foreground font-mono mt-0.5 truncate bg-muted/50 inline-block px-1.5 py-0.5 rounded">
                    {agent.slug}
                </p>
                <p className="text-sm text-muted-foreground mt-3 line-clamp-2 leading-relaxed">
                    {agent.description || "No description provided."}
                </p>
                {metrics ? renderMetrics(metrics, metricVariant) : null}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between relative z-10 pt-2 border-t border-border/50">
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span>v{agent.version}</span>
                    <span>•</span>
                    <span>{new Date(agent.updated_at).toLocaleDateString()}</span>
                </div>
                <Button variant="ghost" size="icon" className="h-6 w-6 rounded-full bg-muted/50 hover:bg-primary hover:text-primary-foreground transition-colors group-hover:scale-105">
                    <ArrowUpRight className="h-3 w-3" />
                </Button>
            </div>
        </div>
    )
}
