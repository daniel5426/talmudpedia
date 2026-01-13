"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { useParams, useRouter } from "next/navigation"
import {
    Save,
    Play,
    Settings,
    ChevronLeft,
    Loader2,
    AlertCircle,
    CheckCircle2
} from "lucide-react"
import { Node, Edge } from "@xyflow/react"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { agentService } from "@/services/agent-resources"
import { AgentBuilder, AgentNodeData } from "@/components/agent-builder"

interface AgentWithGraph {
    id: string
    tenant_id: string
    name: string
    slug: string
    description?: string
    status: 'draft' | 'published' | 'deprecated' | 'archived'
    version: number
    graph_definition?: {
        nodes: Node<AgentNodeData>[]
        edges: Edge[]
    }
    created_at: string
    updated_at: string
    published_at?: string
}

export default function AgentBuilderPage() {
    const { id } = useParams()
    const router = useRouter()
    const [agent, setAgent] = useState<AgentWithGraph | null>(null)
    const [isLoading, setIsLoading] = useState(true)
    const [isSaving, setIsSaving] = useState(false)
    const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle")
    const [error, setError] = useState<string | null>(null)

    // Store current graph state for saving
    const graphRef = useRef<{ nodes: Node<AgentNodeData>[]; edges: Edge[] }>({ nodes: [], edges: [] })

    useEffect(() => {
        if (id) {
            loadAgent()
        }
    }, [id])

    const loadAgent = async () => {
        try {
            setIsLoading(true)
            const data = await agentService.getAgent(id as string) as AgentWithGraph
            setAgent(data)
            // Initialize graph ref with loaded data
            if (data.graph_definition) {
                graphRef.current = data.graph_definition
            }
        } catch (err) {
            console.error("Failed to load agent:", err)
            setError("Failed to load agent configuration.")
        } finally {
            setIsLoading(false)
        }
    }

    const handleGraphChange = useCallback((nodes: Node<AgentNodeData>[], edges: Edge[]) => {
        graphRef.current = { nodes, edges }
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
                // @ts-ignore - graph_definition exists on the backend
                graph_definition: graphRef.current
            })

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
                // @ts-ignore
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

    if (isLoading) {
        return (
            <div className="flex w-full flex-col items-center justify-center min-h-screen space-y-4">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <p className="text-muted-foreground">Loading agent builder...</p>
            </div>
        )
    }

    if (error || !agent) {
        return (
            <div className="flex w-full flex-col items-center justify-center min-h-screen space-y-4 text-center p-6">
                <AlertCircle className="h-12 w-12 text-destructive" />
                <div className="space-y-2">
                    <h3 className="text-lg font-medium">Error</h3>
                    <p className="text-muted-foreground max-w-sm">{error || "Agent not found"}</p>
                </div>
                <Button variant="outline" onClick={() => router.push("/admin/agents")}>
                    Back to Agents
                </Button>
            </div>
        )
    }

    return (
        <div className="flex w-full flex-col h-screen overflow-hidden">
            {/* Header */}
            <header className="border-b bg-background flex items-center justify-between px-6 py-3 shrink-0">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" size="icon" onClick={() => router.push("/admin/agents")}>
                        <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <div className="flex flex-col">
                        <div className="flex items-center gap-2">
                            <h1 className="font-semibold text-lg">{agent.name}</h1>
                            <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4">v{agent.version}</Badge>
                            <Badge
                                variant={agent.status === "published" ? "default" : "outline"}
                                className="text-[10px] px-1.5 py-0 h-4"
                            >
                                {agent.status}
                            </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground">{agent.slug}</p>
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    {saveStatus === "saved" && (
                        <span className="text-xs text-green-600 flex items-center gap-1">
                            <CheckCircle2 className="h-3 w-3" />
                            Saved
                        </span>
                    )}
                    {saveStatus === "error" && (
                        <span className="text-xs text-destructive flex items-center gap-1">
                            <AlertCircle className="h-3 w-3" />
                            Save failed
                        </span>
                    )}
                    <Button variant="outline" size="sm" onClick={handleSave} disabled={isSaving}>
                        {isSaving && saveStatus === "saving" ? (
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : (
                            <Save className="mr-2 h-4 w-4" />
                        )}
                        Save Draft
                    </Button>
                    <Button
                        size="sm"
                        variant="default"
                        className="bg-green-600 hover:bg-green-700 text-white"
                        onClick={handlePublish}
                        disabled={isSaving}
                    >
                        Publish
                    </Button>
                </div>
            </header>

            {/* Builder Canvas */}
            <main className="flex-1 overflow-hidden">
                <AgentBuilder
                    initialNodes={agent.graph_definition?.nodes || []}
                    initialEdges={agent.graph_definition?.edges || []}
                    onSave={handleGraphChange}
                />
            </main>
        </div>
    )
}
