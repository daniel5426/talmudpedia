"use client"

import { useState, useEffect, useMemo } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Bot, Plus } from "lucide-react"

import { Button } from "@/components/ui/button"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { SearchInput } from "@/components/ui/search-input"
import { Skeleton } from "@/components/ui/skeleton"
import { agentService, adminService, Agent } from "@/services"
import { AgentCard } from "@/components/agent-card"
import { CreateAgentDialog } from "@/components/agents/CreateAgentDialog"

function AgentCardSkeleton() {
    return (
        <div className="rounded-xl border border-border/50 bg-card p-5 space-y-4">
            <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                    <Skeleton className="h-10 w-10 rounded-lg" />
                    <div className="space-y-1.5">
                        <Skeleton className="h-4 w-32" />
                        <Skeleton className="h-3 w-20" />
                    </div>
                </div>
                <Skeleton className="h-7 w-7 rounded-md" />
            </div>
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-3/4" />
            <div className="flex items-center justify-between pt-2">
                <Skeleton className="h-3 w-16" />
                <Skeleton className="h-8 w-16 rounded-md" />
            </div>
        </div>
    )
}

export default function AgentsPage() {
    const router = useRouter()
    const searchParams = useSearchParams()
    const [agents, setAgents] = useState<Agent[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [searchQuery, setSearchQuery] = useState("")
    const [makingToolAgentId, setMakingToolAgentId] = useState<string | null>(null)
    const [agentMetrics, setAgentMetrics] = useState<Record<string, { threads: number; runs: number; failureRate: number; threadTrend: { date: string; value: number }[] }>>({})
    const isCreateDialogOpen = searchParams.get("create") === "1"

    useEffect(() => {
        loadAgents()
    }, [])

    const loadAgents = async () => {
        try {
            setIsLoading(true)
            const [data, stats] = await Promise.all([
                agentService.listAgents({ view: "summary", limit: 100 }),
                adminService.getStatsSummary("agents", 14),
            ])
            setAgents(data.items)
            const nextMetrics: Record<string, { threads: number; runs: number; failureRate: number; threadTrend: { date: string; value: number }[] }> = {}
            for (const item of stats.agents?.agents || []) {
                nextMetrics[item.id] = {
                    threads: item.thread_count,
                    runs: item.run_count,
                    failureRate: item.run_count > 0 ? (item.failed_count / item.run_count) * 100 : 0,
                    threadTrend: item.threads_by_day || [],
                }
            }
            setAgentMetrics(nextMetrics)
            setError(null)
        } catch (err) {
            console.error("Failed to load agents:", err)
            setError("Failed to load agents. Please try again later.")
        } finally {
            setIsLoading(false)
        }
    }

    const filteredAgents = useMemo(() => {
        const q = searchQuery.toLowerCase().trim()
        if (!q) return agents
        return agents.filter(agent =>
            agent.name.toLowerCase().includes(q) ||
            agent.slug?.toLowerCase().includes(q)
        )
    }, [agents, searchQuery])

    const handleDelete = async (agent: Agent) => {
        if (!window.confirm(`Delete agent "${agent.name}"? This cannot be undone.`)) return
        try {
            await agentService.deleteAgent(agent.id)
            await loadAgents()
        } catch (err) {
            console.error("Failed to delete agent:", err)
            setError("Failed to delete agent. Please try again.")
        }
    }

    const setCreateDialogOpen = (open: boolean) => {
        if (open) {
            router.push("/admin/agents?create=1")
            return
        }
        router.replace("/admin/agents")
    }

    const handleMakeTool = async (agent: Agent) => {
        try {
            setMakingToolAgentId(agent.id)
            await agentService.exportAgentTool(agent.id)
            await loadAgents()
        } catch (err) {
            console.error("Failed to make tool:", err)
            setError(`Failed to make "${agent.name}" a tool. Please try again.`)
        } finally {
            setMakingToolAgentId(null)
        }
    }

    return (
        <div className="flex w-full flex-col h-screen bg-background overflow-hidden">
            {/* Header */}
            <AdminPageHeader>
                <CustomBreadcrumb items={[
                    { label: "Agents", href: "/admin/agents", active: true },
                ]} />
                <div className="flex items-center gap-2">
                    <SearchInput
                        placeholder="Search agents..."
                        wrapperClassName="w-64"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        disabled={isLoading}
                    />
                    <Button
                        size="sm"
                        className="h-8 gap-1.5"
                        onClick={() => setCreateDialogOpen(true)}
                        disabled={isLoading}
                    >
                        <Plus className="h-3.5 w-3.5" />
                        New Agent
                    </Button>
                </div>
            </AdminPageHeader>

            {/* Content */}
            <main className="flex-1 overflow-y-auto p-4" data-admin-page-scroll>
                {error && (
                    <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive flex items-center justify-between">
                        <span>{error}</span>
                        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={loadAgents}>
                            Try Again
                        </Button>
                    </div>
                )}

                {isLoading ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                        {Array.from({ length: 6 }).map((_, i) => (
                            <AgentCardSkeleton key={i} />
                        ))}
                    </div>
                ) : filteredAgents.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-24 px-4 text-center">
                        <div className="flex h-14 w-14 items-center justify-center rounded-xl border-2 border-dashed border-border/60 mb-4">
                            <Bot className="h-6 w-6 text-muted-foreground/40" />
                        </div>
                        <h3 className="text-sm font-medium text-foreground mb-1">
                            {searchQuery ? "No agents match your search" : "No agents yet"}
                        </h3>
                        <p className="text-sm text-muted-foreground/70 max-w-[300px] mb-5">
                            {searchQuery
                                ? "Try a different search term."
                                : "Create your first AI agent to get started."}
                        </p>
                        {!searchQuery && (
                            <Button
                                size="sm"
                                variant="outline"
                                className="gap-1.5"
                                onClick={() => setCreateDialogOpen(true)}
                            >
                                <Plus className="h-3.5 w-3.5" />
                                Create Agent
                            </Button>
                        )}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 p-2">
                        {filteredAgents.map((agent) => (
                            <AgentCard
                                key={agent.id}
                                agent={agent}
                                metrics={agentMetrics[agent.id]}
                                onOpen={(a) => router.push(`/admin/agents/${a.id}/builder`)}
                                onPlayground={(a) => router.push(`/admin/agents/playground?agentId=${a.id}`)}
                                onMakeTool={handleMakeTool}
                                makeToolBusy={makingToolAgentId === agent.id}
                                onDelete={handleDelete}
                            />
                        ))}
                    </div>
                )}
            </main>

            <CreateAgentDialog open={isCreateDialogOpen} onOpenChange={setCreateDialogOpen} />
        </div>
    )
}
