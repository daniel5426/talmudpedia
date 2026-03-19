"use client"

import { useState, useEffect, useMemo } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import {
    Bot,
    Loader2,
    Plus,
    Search,
    Wrench,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Skeleton } from "@/components/ui/skeleton"
import { agentService, adminService, Agent } from "@/services"
import { AgentCard } from "@/components/agent-card"
import { CreateAgentDialog } from "@/components/agents/CreateAgentDialog"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"


const DEFAULT_AGENT_TOOL_INPUT_SCHEMA = {
    type: "object",
    properties: {
        input: {
            anyOf: [
                { type: "string" },
                { type: "object", additionalProperties: true },
            ],
        },
        text: { type: "string" },
        input_text: { type: "string" },
        messages: { type: "array", items: { type: "object" } },
        context: { type: "object", additionalProperties: true },
    },
    additionalProperties: false,
}

function ExportAgentToolDialog({
    open,
    agents,
    onOpenChange,
}: {
    open: boolean
    agents: Agent[]
    onOpenChange: (open: boolean) => void
}) {
    const router = useRouter()
    const [selectedAgentId, setSelectedAgentId] = useState("")
    const [name, setName] = useState("")
    const [description, setDescription] = useState("")
    const [inputSchemaText, setInputSchemaText] = useState(JSON.stringify(DEFAULT_AGENT_TOOL_INPUT_SCHEMA, null, 2))
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const selectedAgent = useMemo(
        () => agents.find((agent) => agent.id === selectedAgentId) ?? null,
        [agents, selectedAgentId]
    )

    useEffect(() => {
        if (!open) {
            return
        }
        if (!selectedAgentId && agents.length > 0) {
            setSelectedAgentId(agents[0].id)
        }
    }, [agents, open, selectedAgentId])

    useEffect(() => {
        if (!open || !selectedAgent) {
            return
        }
        setName(`${selectedAgent.name} Tool`)
        setDescription(selectedAgent.description || `Delegates to agent ${selectedAgent.name}.`)
        setInputSchemaText(JSON.stringify(DEFAULT_AGENT_TOOL_INPUT_SCHEMA, null, 2))
        setError(null)
    }, [open, selectedAgent])

    const handleSubmit = async () => {
        if (!selectedAgentId) {
            setError("Select an agent to export.")
            return
        }

        let parsedInputSchema: Record<string, unknown>
        try {
            parsedInputSchema = JSON.parse(inputSchemaText)
        } catch {
            setError("Input schema must be valid JSON.")
            return
        }

        setLoading(true)
        setError(null)
        try {
            await agentService.exportAgentTool(selectedAgentId, {
                name: name.trim() || undefined,
                description: description.trim() || undefined,
                input_schema: parsedInputSchema,
            })
            onOpenChange(false)
            router.push("/admin/tools")
        } catch (err) {
            console.error("Failed to export agent tool", err)
            setError("Failed to export agent as a tool.")
        } finally {
            setLoading(false)
        }
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[720px]">
                <DialogHeader>
                    <DialogTitle>Export Agent As Tool</DialogTitle>
                    <DialogDescription>
                        Create or refresh an owner-managed `agent_call` tool for an agent. Ongoing edits stay in the agents surface.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-2">
                    <div className="space-y-2">
                        <Label htmlFor="export-agent-select">Agent</Label>
                        <select
                            id="export-agent-select"
                            value={selectedAgentId}
                            onChange={(event) => setSelectedAgentId(event.target.value)}
                            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        >
                            {agents.length === 0 ? (
                                <option value="">No agents available</option>
                            ) : (
                                agents.map((agent) => (
                                    <option key={agent.id} value={agent.id}>
                                        {agent.name}
                                    </option>
                                ))
                            )}
                        </select>
                    </div>

                    <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                            <Label htmlFor="export-tool-name">Tool Name</Label>
                            <Input id="export-tool-name" value={name} onChange={(event) => setName(event.target.value)} />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="export-tool-description">Description</Label>
                            <Input id="export-tool-description" value={description} onChange={(event) => setDescription(event.target.value)} />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="export-tool-input-schema">Input Schema</Label>
                        <Textarea
                            id="export-tool-input-schema"
                            className="min-h-[220px] font-mono text-xs"
                            value={inputSchemaText}
                            onChange={(event) => setInputSchemaText(event.target.value)}
                        />
                    </div>

                    {error ? (
                        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                            {error}
                        </div>
                    ) : null}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
                        Cancel
                    </Button>
                    <Button onClick={handleSubmit} disabled={loading || agents.length === 0} className="gap-2">
                        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wrench className="h-4 w-4" />}
                        Export Tool
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

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
    const [agentMetrics, setAgentMetrics] = useState<Record<string, { threads: number; runs: number; failureRate: number }>>({})
    const isCreateDialogOpen = searchParams.get("create") === "1"
    const isExportDialogOpen = searchParams.get("mode") === "export-tool"

    useEffect(() => {
        loadAgents()
    }, [])

    const loadAgents = async () => {
        try {
            setIsLoading(true)
            const [data, stats] = await Promise.all([
                agentService.listAgents(),
                adminService.getStatsSummary("agents", 7),
            ])
            setAgents(data.agents)
            const nextMetrics: Record<string, { threads: number; runs: number; failureRate: number }> = {}
            for (const item of stats.agents?.agents || []) {
                nextMetrics[item.id] = {
                    threads: item.thread_count,
                    runs: item.run_count,
                    failureRate: item.run_count > 0 ? (item.failed_count / item.run_count) * 100 : 0,
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

    const setExportDialogOpen = (open: boolean) => {
        if (open) {
            router.push("/admin/agents?mode=export-tool")
            return
        }
        router.replace("/admin/agents")
    }

    return (
        <div className="flex w-full flex-col h-screen bg-background overflow-hidden">
            {/* Header */}
            <AdminPageHeader>
                <CustomBreadcrumb items={[
                    { label: "Agents", href: "/admin/agents", active: true },
                ]} />
                <div className="flex items-center gap-2">
                    <div className="relative w-64">
                        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/60" />
                        <Input
                            placeholder="Search agents..."
                            className="h-8 pl-8 bg-muted/30 border-border/50 text-sm placeholder:text-muted-foreground/50"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            disabled={isLoading}
                        />
                    </div>
                    <Button
                        size="sm"
                        className="h-8 gap-1.5"
                        onClick={() => setCreateDialogOpen(true)}
                        disabled={isLoading}
                    >
                        <Plus className="h-3.5 w-3.5" />
                        New Agent
                    </Button>
                    <Button
                        size="sm"
                        variant="outline"
                        className="h-8 gap-1.5"
                        onClick={() => setExportDialogOpen(true)}
                        disabled={isLoading}
                    >
                        <Wrench className="h-3.5 w-3.5" />
                        Export As Tool
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
                                onDelete={handleDelete}
                            />
                        ))}
                    </div>
                )}
            </main>

            <CreateAgentDialog open={isCreateDialogOpen} onOpenChange={setCreateDialogOpen} />
            <ExportAgentToolDialog open={isExportDialogOpen} onOpenChange={setExportDialogOpen} agents={agents} />
        </div>
    )
}
