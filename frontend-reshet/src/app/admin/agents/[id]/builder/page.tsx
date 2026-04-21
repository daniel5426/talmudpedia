"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { useParams, useRouter } from "next/navigation"
import {
    Save,
    Loader2,
    AlertCircle,
    CheckCircle2,
    PlugZap,
    RefreshCw,
    Unplug,
} from "lucide-react"

import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { agentService, Agent, AgentGraphDefinition, mcpService, McpAgentMount, McpServer } from "@/services"
import { formatHttpErrorMessage } from "@/services/http"
import { AgentBuilder } from "@/components/agent-builder"
import { normalizeGraphDefinition } from "@/components/agent-builder/graphspec"
import { HeaderConfigEditor } from "@/components/builder"
import { INTEGRATION_CATALOG, matchServerToCatalog, pickPreferredCatalogServer } from "@/services/integration-catalog"

export default function AgentBuilderPage() {
    const { id } = useParams()
    const router = useRouter()
    const [agent, setAgent] = useState<Agent | null>(null)
    const [agentName, setAgentName] = useState("")
    const [agentDescription, setAgentDescription] = useState("")
    const [isLoading, setIsLoading] = useState(true)
    const [isSaving, setIsSaving] = useState(false)
    const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle")
    const [error, setError] = useState<string | null>(null)
    const [actionError, setActionError] = useState<string | null>(null)
    const [builderMode, setBuilderMode] = useState<"build" | "execute">("build")
    const [mcpDialogOpen, setMcpDialogOpen] = useState(false)
    const [mcpServers, setMcpServers] = useState<McpServer[]>([])
    const [mcpMounts, setMcpMounts] = useState<McpAgentMount[]>([])
    const [mcpLoading, setMcpLoading] = useState(false)
    const [mcpError, setMcpError] = useState<string | null>(null)

    const visibleMcpServers = (() => {
        const grouped = new Map<string, McpServer[]>()
        const custom: McpServer[] = []

        for (const server of mcpServers) {
            const entry = matchServerToCatalog(server.server_url)
            if (!entry) {
                custom.push(server)
                continue
            }
            grouped.set(entry.slug, [...(grouped.get(entry.slug) ?? []), server])
        }

        const catalogServers = INTEGRATION_CATALOG
            .map((entry) => pickPreferredCatalogServer(entry, grouped.get(entry.slug) ?? []))
            .filter((server): server is McpServer => server !== null)

        return [...catalogServers, ...custom]
    })()

    // Store current graph state for saving
    const graphRef = useRef<AgentGraphDefinition>(normalizeGraphDefinition({ spec_version: "4.0", nodes: [], edges: [] }))

    const loadAgent = useCallback(async () => {
        try {
            setIsLoading(true)
            const data = await agentService.getAgent(id as string)
            setAgent(data)
            setAgentName(data.name)
            setAgentDescription(data.description || "")
            // Initialize graph ref with loaded data
            if (data.graph_definition) {
                graphRef.current = normalizeGraphDefinition(data.graph_definition)
            }
            setActionError(null)
        } catch (err) {
            console.error("Failed to load agent:", err)
            setError("Failed to load agent configuration.")
        } finally {
            setIsLoading(false)
        }
    }, [id])

    useEffect(() => {
        if (id) {
            loadAgent()
        }
    }, [id, loadAgent])

    const handleGraphChange = useCallback((graphDefinition: AgentGraphDefinition) => {
        graphRef.current = normalizeGraphDefinition(graphDefinition)
        setActionError(null)
        // Mark as unsaved when changes are made
        if (saveStatus === "saved" || saveStatus === "error") {
            setSaveStatus("idle")
        }
    }, [saveStatus])

    const handleSave = async () => {
        if (!agent) return

        try {
            setIsSaving(true)
            setSaveStatus("saving")
            setActionError(null)

            await agentService.updateAgent(agent.id, {
                name: agentName.trim(),
                description: agentDescription.trim() || undefined,
                graph_definition: graphRef.current
            })

            setAgent((current) => current ? {
                ...current,
                name: agentName.trim(),
                description: agentDescription.trim() || undefined,
            } : current)
            setSaveStatus("saved")
            setActionError(null)
            setTimeout(() => setSaveStatus("idle"), 2000)
        } catch (err) {
            console.error("Failed to save agent:", err)
            setSaveStatus("error")
            setActionError(formatHttpErrorMessage(err, "Failed to save draft."))
        } finally {
            setIsSaving(false)
        }
    }

    const handlePublish = async () => {
        if (!agent) return

        try {
            setIsSaving(true)
            setActionError(null)
            // Save first, then publish
            await agentService.updateAgent(agent.id, {
                name: agentName.trim(),
                description: agentDescription.trim() || undefined,
                graph_definition: graphRef.current
            })
            await agentService.publishAgent(agent.id)

            // Reload to get updated status
            await loadAgent()
        } catch (err) {
            console.error("Failed to publish agent:", err)
            setActionError(formatHttpErrorMessage(err, "Failed to publish agent."))
        } finally {
            setIsSaving(false)
        }
    }

    const loadMcpState = useCallback(async () => {
        if (!id) return
        try {
            setMcpLoading(true)
            setMcpError(null)
            const [servers, mounts] = await Promise.all([
                mcpService.listServers(),
                mcpService.listAgentMounts(id as string),
            ])
            setMcpServers(servers)
            setMcpMounts(mounts)
        } catch (err) {
            setMcpError(formatHttpErrorMessage(err, "Failed to load MCP mounts."))
        } finally {
            setMcpLoading(false)
        }
    }, [id])

    useEffect(() => {
        if (!mcpDialogOpen) return
        loadMcpState()
    }, [mcpDialogOpen, loadMcpState])

    async function handleAttach(serverId: string) {
        if (!id) return
        try {
            setMcpError(null)
            await mcpService.createAgentMount(id as string, { server_id: serverId, approval_policy: "always_allow" })
            await loadMcpState()
        } catch (err) {
            setMcpError(formatHttpErrorMessage(err, "Failed to attach MCP server."))
        }
    }

    async function handleApplyLatest(mountId: string) {
        if (!id) return
        try {
            setMcpError(null)
            await mcpService.updateAgentMount(id as string, mountId, { apply_latest_snapshot: true })
            await loadMcpState()
        } catch (err) {
            setMcpError(formatHttpErrorMessage(err, "Failed to apply latest MCP snapshot."))
        }
    }

    async function handleDetach(mountId: string) {
        if (!id) return
        try {
            setMcpError(null)
            await mcpService.deleteAgentMount(id as string, mountId)
            await loadMcpState()
        } catch (err) {
            setMcpError(formatHttpErrorMessage(err, "Failed to detach MCP server."))
        }
    }

    return (
        <div className="flex w-full flex-col h-screen overflow-hidden">
            {/* Header */}
            <header className="shrink-0 bg-background z-40">
                <div className="flex h-12 items-center justify-between gap-4 px-4">
                    <div className="flex items-center gap-3">
                        <div className="flex items-center gap-2">
                        <CustomBreadcrumb items={[
                            { label: "Agents", href: "/admin/agents" },
                            { label: agentName || agent?.name || "Loading...", active: true },
                        ]} />
                        {agent && (
                            <div className="flex items-center gap-2 ml-2">
                                <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4">v{agent.version}</Badge>
                                <Badge
                                    variant={agent.status === "published" ? "default" : "outline"}
                                    className="text-[10px] px-1.5 py-0 h-4"
                                >
                                    {agent.status}
                                </Badge>
                            </div>
                        )}
                    </div>
                    </div>

                    <div className="flex flex-1 justify-center">
                        {agent && (
                            <Tabs value={builderMode} onValueChange={(value) => setBuilderMode(value as "build" | "execute")} className="gap-0">
                                <TabsList className="h-8 p-1">
                                    <TabsTrigger value="build" className="px-4 text-[11px]">
                                        Build
                                    </TabsTrigger>
                                    <TabsTrigger value="execute" className="px-4 text-[11px]">
                                        Execute
                                    </TabsTrigger>
                                </TabsList>
                            </Tabs>
                        )}
                    </div>

                    <div className="flex items-center gap-2">
                        <HeaderConfigEditor
                            name={agentName}
                            description={agentDescription}
                            onNameChange={(value) => {
                                setAgentName(value)
                                setActionError(null)
                                if (saveStatus === "saved" || saveStatus === "error") {
                                    setSaveStatus("idle")
                                }
                            }}
                            onDescriptionChange={(value) => {
                                setAgentDescription(value)
                                setActionError(null)
                                if (saveStatus === "saved" || saveStatus === "error") {
                                    setSaveStatus("idle")
                                }
                            }}
                            nameLabel="Agent name"
                            descriptionLabel="Description"
                            namePlaceholder="Research Assistant"
                            descriptionPlaceholder="Describe what this agent is meant to handle."
                            triggerLabel="Edit details"
                            identifier={agent?.id}
                            identifierLabel="Agent ID"
                            disabled={isSaving || isLoading}
                        />
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setMcpDialogOpen(true)}
                            disabled={isLoading || isSaving}
                            className="h-8 rounded-md text-xs shadow-none"
                        >
                            <PlugZap className="mr-2 h-3 w-3" />
                            Manage MCP
                        </Button>
                        {saveStatus === "saved" && (
                            <span className="flex h-8 items-center gap-1 text-xs text-green-600">
                                <CheckCircle2 className="h-3 w-3" />
                                Saved
                            </span>
                        )}
                        {saveStatus === "error" && (
                            <span className="flex h-8 items-center gap-1 text-xs text-destructive">
                                <AlertCircle className="h-3 w-3" />
                                Save failed
                            </span>
                        )}
                        {actionError && (
                            <span className="max-w-[320px] truncate text-xs text-destructive" title={actionError}>
                                {actionError}
                            </span>
                        )}
                        <Button variant="outline" size="sm" onClick={handleSave} disabled={isSaving || isLoading} className="h-8 rounded-md text-xs shadow-none">
                            {isSaving && saveStatus === "saving" ? (
                                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                            ) : (
                                <Save className="mr-2 h-3 w-3" />
                            )}
                            Save Draft
                        </Button>
                        <Button
                            size="sm"
                            variant="default"
                            className="h-8 rounded-md bg-green-600 text-xs text-white shadow-none hover:bg-green-700"
                            onClick={handlePublish}
                            disabled={isSaving || isLoading}
                        >
                            Publish
                        </Button>
                    </div>
                </div>
            </header>

            {/* Main Content */}
            <main className="flex-1 mr-2 mb-2 ml-1 overflow-hidden relative">
                {isLoading ? (
                    <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-50">
                        <div className="flex flex-col items-center gap-2">
                            <Loader2 className="h-8 w-8 animate-spin text-primary" />
                            <p className="text-muted-foreground">Loading agent builder...</p>
                        </div>
                    </div>
                ) : error || !agent ? (
                    <div className="flex flex-col items-center justify-center h-full p-6 text-center">
                        <AlertCircle className="h-12 w-12 text-destructive mb-4" />
                        <h3 className="text-lg font-medium mb-2">Error</h3>
                        <p className="text-muted-foreground max-w-sm mb-4">{error || "Agent not found"}</p>
                        <Button variant="outline" onClick={() => router.push("/admin/agents")}>
                            Back to Agents
                        </Button>
                    </div>
                ) : (
                    <AgentBuilder
                        agentId={id as string}
                        agentSystemKey={agent.system_key}
                        initialGraphDefinition={graphRef.current}
                        onSave={handleGraphChange}
                        mode={builderMode}
                        onModeChange={setBuilderMode}
                    />
                )}
            </main>

            <Dialog open={mcpDialogOpen} onOpenChange={setMcpDialogOpen}>
                <DialogContent className="sm:max-w-2xl p-0 gap-0 overflow-hidden">
                    <div className="px-5 pt-5 pb-4">
                        <DialogHeader className="space-y-1">
                            <DialogTitle className="text-base font-semibold tracking-tight flex items-center gap-2">
                                <PlugZap className="h-4 w-4 text-primary" />
                                MCP Integrations
                            </DialogTitle>
                            <DialogDescription className="text-xs text-muted-foreground/70">
                                Attach MCP servers to give this agent access to external tools.
                            </DialogDescription>
                        </DialogHeader>
                    </div>

                    {mcpError && (
                        <div className="mx-5 mb-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
                            {mcpError}
                        </div>
                    )}

                    <div className="px-5 pb-5 max-h-[60vh] overflow-y-auto">
                        {mcpLoading ? (
                            <div className="flex flex-col items-center justify-center py-12 text-sm text-muted-foreground gap-2">
                                <Loader2 className="h-5 w-5 animate-spin text-primary/60" />
                                <span className="text-xs">Loading servers…</span>
                            </div>
                        ) : visibleMcpServers.length === 0 ? (
                            <div className="rounded-xl border-2 border-dashed border-border/50 px-6 py-10 text-center">
                                <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-muted/60">
                                    <PlugZap className="h-5 w-5 text-muted-foreground/50" />
                                </div>
                                <p className="text-sm font-medium text-foreground mb-1">No MCP servers</p>
                                <p className="text-xs text-muted-foreground/60 max-w-[280px] mx-auto">
                                    Configure MCP servers in Settings → MCP Servers first, then attach them here.
                                </p>
                            </div>
                        ) : (
                            <div className="space-y-2">
                                {visibleMcpServers.map((server) => {
                                    const catalogEntry = matchServerToCatalog(server.server_url)
                                    const mount = mcpMounts.find((item) => item.server_id === server.id) ?? null
                                    const pinned = mount?.applied_snapshot_version ?? null
                                    const latest = server.tool_snapshot_version
                                    const stale = mount !== null && pinned !== latest
                                    const isMounted = mount !== null
                                    const isReady = server.sync_status === "ready"

                                    return (
                                        <div
                                            key={server.id}
                                            className={`
                                                group rounded-xl border px-4 py-3 transition-all duration-150
                                                ${isMounted
                                                    ? "border-primary/20 bg-primary/[0.02] hover:border-primary/30"
                                                    : "border-border/50 hover:border-border/80 hover:bg-muted/20"
                                                }
                                            `}
                                        >
                                            <div className="flex items-center gap-3">
                                                {/* Icon */}
                                                <div className={`
                                                    flex h-9 w-9 shrink-0 items-center justify-center rounded-lg
                                                    ${isMounted ? "bg-primary/10 text-primary" : "bg-muted/60 text-muted-foreground/60"}
                                                `}>
                                                    <PlugZap className="h-4 w-4" />
                                                </div>

                                                {/* Info */}
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-sm font-medium truncate">{catalogEntry?.name ?? server.name}</span>
                                                        {/* Status dot */}
                                                        <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${
                                                            isMounted && isReady ? "bg-emerald-500" :
                                                            isMounted && !isReady ? "bg-amber-500" :
                                                            isReady ? "bg-zinc-400" : "bg-zinc-300"
                                                        }`} />
                                                        <span className="text-[10px] text-muted-foreground/60">
                                                            {isMounted ? (isReady ? "Active" : "Syncing") : (isReady ? "Available" : server.sync_status)}
                                                        </span>
                                                    </div>
                                                    <div className="flex items-center gap-1.5 mt-0.5">
                                                        <span className="text-[10px] text-muted-foreground/50 font-mono">{server.auth_mode.replace(/_/g, " ")}</span>
                                                        {isMounted && (
                                                            <>
                                                                <span className="text-muted-foreground/30">·</span>
                                                                <span className={`text-[10px] font-mono ${stale ? "text-amber-600" : "text-muted-foreground/50"}`}>
                                                                    v{pinned}{stale ? ` → v${latest}` : ""}
                                                                </span>
                                                            </>
                                                        )}
                                                    </div>
                                                </div>

                                                {/* Actions */}
                                                <div className="flex items-center gap-1.5 shrink-0">
                                                    {isMounted ? (
                                                        <>
                                                            {stale && (
                                                                <Button
                                                                    variant="outline"
                                                                    size="sm"
                                                                    className="h-7 text-[11px] px-2.5 gap-1.5 border-amber-500/30 text-amber-700 hover:bg-amber-500/5"
                                                                    onClick={() => handleApplyLatest(mount.id)}
                                                                >
                                                                    <RefreshCw className="h-3 w-3" />
                                                                    Update
                                                                </Button>
                                                            )}
                                                            <Button
                                                                variant="ghost"
                                                                size="sm"
                                                                className="h-7 text-[11px] px-2.5 gap-1.5 text-muted-foreground hover:text-destructive"
                                                                onClick={() => handleDetach(mount.id)}
                                                            >
                                                                <Unplug className="h-3 w-3" />
                                                                Detach
                                                            </Button>
                                                        </>
                                                    ) : (
                                                        <Button
                                                            size="sm"
                                                            className="h-7 text-[11px] px-3 gap-1.5"
                                                            onClick={() => handleAttach(server.id)}
                                                            disabled={server.tool_snapshot_version <= 0}
                                                        >
                                                            <PlugZap className="h-3 w-3" />
                                                            Attach
                                                        </Button>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>
                        )}

                        {/* Summary footer */}
                        {!mcpLoading && visibleMcpServers.length > 0 && (
                            <div className="mt-3 pt-3 border-t border-border/30 flex items-center justify-between">
                                <span className="text-[10px] text-muted-foreground/50">
                                    {mcpMounts.length} of {visibleMcpServers.length} server{visibleMcpServers.length !== 1 ? "s" : ""} attached
                                </span>
                                {mcpMounts.some((m) => {
                                    const s = visibleMcpServers.find((sv) => sv.id === m.server_id)
                                    return s && m.applied_snapshot_version !== s.tool_snapshot_version
                                }) && (
                                    <span className="text-[10px] text-amber-600 font-medium">
                                        Updates available
                                    </span>
                                )}
                            </div>
                        )}
                    </div>
                </DialogContent>
            </Dialog>
        </div>
    )
}
