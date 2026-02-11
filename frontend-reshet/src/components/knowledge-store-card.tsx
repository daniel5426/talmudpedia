
import React from 'react'
import { KnowledgeStore } from "@/services"
import {
    Database,
    MoreHorizontal,
    Settings,
    Trash2,
    Layers,
    Box,
    FileText
} from "lucide-react"
import { Button } from "@/components/ui/button"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"

interface KnowledgeStoreCardProps {
    store: KnowledgeStore
    modelName?: string
    onDelete?: (store: KnowledgeStore) => void
    onSettings?: (store: KnowledgeStore) => void
    className?: string
}

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
    active: { color: "bg-emerald-500", label: "Active" },
    syncing: { color: "bg-blue-500", label: "Syncing" },
    initializing: { color: "bg-amber-500", label: "Init" },
    error: { color: "bg-red-500", label: "Error" },
    archived: { color: "bg-zinc-400", label: "Archived" },
}

// Metric Card matching the Stats Page "MetricBlock" design
export function KnowledgeStoreMetric({
    label,
    value,
    icon: Icon,
    subValue,
    className
}: {
    label: string,
    value: string | number,
    icon: any,
    subValue?: string,
    className?: string
}) {
    return (
        <div className={cn(
            "flex flex-col justify-between items-start p-4 bg-card border rounded-xl hover:shadow-md hover:border-muted-foreground/40 transition-all duration-200",
            className
        )}>
            <div className="flex items-center justify-between w-full mb-2">
                <span className="text-sm font-medium text-muted-foreground">{label}</span>
                <Icon className="h-4 w-4 text-muted-foreground/70" />
            </div>

            <div className="space-y-1">
                <h3 className={cn(
                    "font-bold tracking-tight text-foreground truncate",
                    typeof value === 'number' || !isNaN(Number(value)) ? "text-2xl" : "text-lg"
                )} title={String(value)}>
                    {value}
                </h3>
                {subValue && (
                    <p className="text-xs text-muted-foreground font-medium">{subValue}</p>
                )}
            </div>
        </div>
    )
}

export function KnowledgeStoreCard({ store, modelName, onDelete, onSettings, className }: KnowledgeStoreCardProps) {
    const status = STATUS_CONFIG[store.status] || { color: "bg-zinc-400", label: store.status }

    return (
        <div
            className={cn(
                "group relative flex items-center justify-between border border-muted text-card-foreground rounded-lg p-4 shadow-xs transition-all duration-200 hover:shadow-md hover:border-primary/20 bg-card",
                className
            )}
        >
            {/* Left: Icon & Info */}
            <div className="flex items-center gap-4 flex-1 min-w-0">
                <div className="h-12 w-12 rounded-xl bg-primary/10 flex items-center justify-center shrink-0 border border-primary/10">
                    <Database className="h-6 w-6 text-primary" />
                </div>
                <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-base font-bold tracking-tight truncate group-hover:text-primary transition-colors">
                            {store.name}
                        </h3>
                        <Badge
                            variant="secondary"
                            className={cn(
                                "text-[10px] h-5 px-1.5 font-medium border-0",
                                status.color.replace('bg-', 'bg-').replace('500', '500/15'),
                                status.color.replace('bg-', 'text-')
                            )}
                        >
                            {status.label}
                        </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground truncate max-w-lg">
                        {store.description || "No description provided."}
                    </p>
                </div>
            </div>

            {/* Middle: Stats */}
            <div className="hidden md:flex items-center gap-8 px-8 border-l border-r border-border/40 mx-6 h-10 shrink-0">
                <div className="flex items-center gap-3">
                    <div className="p-1.5 rounded-md bg-muted/50 text-muted-foreground">
                        <FileText className="h-4 w-4" />
                    </div>
                    <div className="flex flex-col">
                        <span className="text-sm font-bold">{store.document_count.toLocaleString()}</span>
                        <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wide">Docs</span>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <div className="p-1.5 rounded-md bg-muted/50 text-muted-foreground">
                        <Layers className="h-4 w-4" />
                    </div>
                    <div className="flex flex-col">
                        <span className="text-sm font-bold">{store.chunk_count.toLocaleString()}</span>
                        <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wide">Chunks</span>
                    </div>
                </div>
            </div>

            {/* Right: Meta & Actions */}
            <div className="flex items-center gap-6 shrink-0">
                <div className="hidden lg:flex flex-col items-end gap-1.5 text-xs text-muted-foreground text-right min-w-[200px]">
                    <div className="flex items-center gap-2">
                        <span className="truncate max-w-[180px] font-medium" title={modelName || store.embedding_model_id}>
                            {modelName || store.embedding_model_id.split('/').pop()}
                        </span>
                        <Badge variant="outline" className="text-[10px] h-5 px-1.5 font-normal bg-background">
                            {store.backend}
                        </Badge>
                    </div>
                    {store.retrieval_policy !== 'semantic_only' && (
                        <div className="flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                            <span className="text-emerald-600 font-medium">
                                {store.retrieval_policy === 'hybrid' ? 'Hybrid Search' : 'Boosted'}
                            </span>
                        </div>
                    )}
                </div>

                <div className="pl-2 border-l border-border/40 lg:border-0 lg:pl-0">
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground">
                                <MoreHorizontal className="h-4 w-4" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => onSettings?.(store)}>
                                <Settings className="mr-2 h-3.5 w-3.5" />
                                Settings
                            </DropdownMenuItem>
                            {onDelete && (
                                <>
                                    <DropdownMenuSeparator />
                                    <DropdownMenuItem className="text-destructive" onClick={() => onDelete(store)}>
                                        <Trash2 className="mr-2 h-3.5 w-3.5" />
                                        Delete
                                    </DropdownMenuItem>
                                </>
                            )}
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
            </div>
        </div>
    )
}
