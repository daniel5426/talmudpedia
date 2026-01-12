"use client"

import { useState, useEffect } from "react"
import { useParams, useRouter } from "next/navigation"
import {
    Save,
    Play,
    Settings,
    ChevronLeft,
    Loader2,
    AlertCircle
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { agentService, Agent } from "@/services/agent-resources"

export default function AgentBuilderPage() {
    const { id } = useParams()
    const router = useRouter()
    const [agent, setAgent] = useState<Agent | null>(null)
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        if (id) {
            loadAgent()
        }
    }, [id])

    const loadAgent = async () => {
        try {
            setIsLoading(true)
            const data = await agentService.getAgent(id as string)
            setAgent(data)
        } catch (err) {
            console.error("Failed to load agent:", err)
            setError("Failed to load agent configuration.")
        } finally {
            setIsLoading(false)
        }
    }

    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center min-h-screen space-y-4">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <p className="text-muted-foreground">Loading agent builder...</p>
            </div>
        )
    }

    if (error || !agent) {
        return (
            <div className="flex flex-col items-center justify-center min-h-screen space-y-4 text-center p-6">
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
        <div className="flex flex-col h-screen overflow-hidden">
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
                        </div>
                        <p className="text-xs text-muted-foreground">{agent.slug}</p>
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm">
                        <Settings className="mr-2 h-4 w-4" />
                        Config
                    </Button>
                    <Button variant="outline" size="sm">
                        <Play className="mr-2 h-4 w-4" />
                        Test
                    </Button>
                    <Button size="sm">
                        <Save className="mr-2 h-4 w-4" />
                        Save Draft
                    </Button>
                    <Button size="sm" variant="default" className="bg-green-600 hover:bg-green-700 text-white">
                        Publish
                    </Button>
                </div>
            </header>

            {/* Builder Canvas Placeholder */}
            <main className="flex-1 bg-muted/30 relative flex items-center justify-center">
                <div className="text-center space-y-4 max-w-md">
                    <div className="bg-background border rounded-lg p-8 shadow-sm">
                        <h2 className="text-xl font-semibold mb-2">Visual Graph Builder</h2>
                        <p className="text-muted-foreground mb-6">
                            This space will host the React Flow powered visual builder for defining agent nodes, tool calls, and LLM orchestration.
                        </p>
                        <div className="grid grid-cols-2 gap-3">
                            <div className="border border-dashed rounded p-4 text-xs">Node Palette</div>
                            <div className="border border-dashed rounded p-4 text-xs">Edge Logic</div>
                        </div>
                    </div>
                    <p className="text-xs text-muted-foreground italic">
                        React Flow integration pending implementation of specific node types.
                    </p>
                </div>
            </main>
        </div>
    )
}
