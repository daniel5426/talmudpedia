"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { useParams, useRouter } from "next/navigation"
import {
    Save,
    Loader2,
    AlertCircle,
    CheckCircle2,
} from "lucide-react"
import { Node, Edge } from "@xyflow/react"

import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { agentService, Agent, AgentGraphDefinition } from "@/services"
import { AgentBuilder, AgentNodeData } from "@/components/agent-builder"
import { normalizeGraphSpecForSave } from "@/components/agent-builder/graphspec"
import { HeaderConfigEditor } from "@/components/builder"

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
    const [builderMode, setBuilderMode] = useState<"build" | "execute">("build")

    // Store current graph state for saving
    const graphRef = useRef<AgentGraphDefinition>({ spec_version: "3.0", nodes: [], edges: [] })

    const loadAgent = useCallback(async () => {
        try {
            setIsLoading(true)
            const data = await agentService.getAgent(id as string)
            setAgent(data)
            setAgentName(data.name)
            setAgentDescription(data.description || "")
            // Initialize graph ref with loaded data
            if (data.graph_definition) {
                graphRef.current = {
                    spec_version: data.graph_definition.spec_version || "3.0",
                    nodes: data.graph_definition.nodes || [],
                    edges: data.graph_definition.edges || [],
                }
            }
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

    const handleGraphChange = useCallback((nodes: Node<AgentNodeData>[], edges: Edge[]) => {
        graphRef.current = normalizeGraphSpecForSave(nodes, edges, { specVersion: graphRef.current.spec_version })
        // Mark as unsaved when changes are made
        if (saveStatus === "saved") {
            setSaveStatus("idle")
        }
    }, [saveStatus])

    const handleSave = async () => {
        if (!agent) return

        try {
            setIsSaving(true)
            setSaveStatus("saving")

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
            setTimeout(() => setSaveStatus("idle"), 2000)
        } catch (err) {
            console.error("Failed to save agent:", err)
            setSaveStatus("error")
        } finally {
            setIsSaving(false)
        }
    }

    const handlePublish = async () => {
        if (!agent) return

        try {
            setIsSaving(true)
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
            setError("Failed to publish agent.")
        } finally {
            setIsSaving(false)
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
                                if (saveStatus === "saved") {
                                    setSaveStatus("idle")
                                }
                            }}
                            onDescriptionChange={(value) => {
                                setAgentDescription(value)
                                if (saveStatus === "saved") {
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
                        initialNodes={agent.graph_definition?.nodes || []}
                        initialEdges={agent.graph_definition?.edges || []}
                        onSave={handleGraphChange}
                        mode={builderMode}
                        onModeChange={setBuilderMode}
                    />
                )}
            </main>
        </div>
    )
}
