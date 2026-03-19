import React, { useEffect, useRef, useState } from 'react'
import { Agent } from "@/services"
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

interface AgentCardProps {
    agent: Agent
    metrics?: {
        threads: number
        runs: number
        failureRate: number
    }
    onDelete?: (agent: Agent) => void
    onOpen?: (agent: Agent) => void // Should navigate to builder
    onRun?: (agent: Agent) => void  // Should navigate to playground
    onPlayground?: (agent: Agent) => void // Alternative to onRun
    className?: string
}

export function AgentCard({ agent, metrics, onOpen, onRun, onDelete, onPlayground, className }: AgentCardProps) {
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
                {metrics ? (
                    <div className="mt-5 grid grid-cols-3 gap-2 border-t border-border/60 pt-4">
                        <div className="rounded-lg border border-border/60 bg-background/60 px-3 py-2">
                            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                                Threads
                            </div>
                            <div className="mt-1 text-lg font-semibold tabular-nums text-foreground">
                                {metrics.threads.toLocaleString()}
                            </div>
                        </div>
                        <div className="rounded-lg border border-border/60 bg-background/60 px-3 py-2">
                            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                                Runs 7d
                            </div>
                            <div className="mt-1 text-lg font-semibold tabular-nums text-foreground">
                                {metrics.runs.toLocaleString()}
                            </div>
                        </div>
                        <div className="rounded-lg border border-border/60 bg-background/60 px-3 py-2">
                            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                                Fail Rate
                            </div>
                            <div className="mt-1 text-lg font-semibold tabular-nums text-foreground">
                                {metrics.failureRate.toFixed(1)}%
                            </div>
                        </div>
                    </div>
                ) : null}
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
