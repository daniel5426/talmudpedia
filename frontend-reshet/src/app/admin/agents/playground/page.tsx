"use client"

import { useState, useEffect, Suspense } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import {
    Loader2,
    AlertCircle,
    Settings,
    Bot,
    Play,
    ChevronDown,
    Plus
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { agentService, Agent } from "@/services"
import { ChatWorkspace } from "@/components/layout/ChatPane"
import { useAgentRunController } from "@/hooks/useAgentRunController"
import { ExecutionSidebar } from "./ExecutionSidebar"
import { Conversation } from "@/components/ai-elements/conversation"
import { useDirection } from "@/components/direction-provider"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { ReactArtifactPane } from "@/components/ai-elements/ReactArtifactPane"
import { useReactArtifactPanel } from "@/lib/react-artifacts/useReactArtifactPanel"
import { parseReactArtifact } from "@/lib/react-artifacts/parseReactArtifact"
import { useTenant } from "@/contexts/TenantContext"
import { useAuthStore } from "@/lib/store/useAuthStore"

function PlaygroundContent() {
    const router = useRouter()
    const searchParams = useSearchParams()
    const agentId = searchParams.get("agentId")

    const [agent, setAgent] = useState<Agent | null>(null)
    const [agents, setAgents] = useState<Agent[]>([])
    const [isMetadataLoading, setIsMetadataLoading] = useState(true)
    const [isListingLoading, setIsListingLoading] = useState(false)

    const controller = useAgentRunController(agentId || undefined)
    const { executionSteps } = controller
    const { direction } = useDirection()
    const { currentTenant } = useTenant()
    const authUser = useAuthStore((state) => state.user)
    const tenantKey = currentTenant?.slug ?? authUser?.tenant_id ?? "unknown-tenant"
    const {
        artifact,
        openFromMessage,
        updateCode,
        persistCurrent,
        resetToSaved,
        closePanel,
    } = useReactArtifactPanel({
        messages: controller.messages,
        tenantKey,
        chatId: agentId ?? "agent-playground",
    })
    const isArtifactMessage = (content: string) => Boolean(parseReactArtifact(content))

    useEffect(() => {
        let isMounted = true;

        const init = async () => {
            // We want to load the agent data as fast as possible.
            // If we have an agentId, we fetch it and the list in parallel.
            // This avoids the sequential delay (flicker) where we wait for the whole list
            // before even starting to load the specific agent's metadata.

            setIsListingLoading(true);
            const listPromise = agentService.listAgents().catch(err => {
                console.error("Failed to load agents list:", err);
                return { agents: [] };
            });

            if (agentId) {
                try {
                    const [agentData, listData] = await Promise.all([
                        agentService.getAgent(agentId),
                        listPromise
                    ]);

                    if (isMounted) {
                        setAgent(agentData);
                        setAgents(listData.agents);
                        setIsMetadataLoading(false);
                    }
                } catch (err) {
                    console.error("Failed to load agent metadata:", err);
                    const listData = await listPromise;
                    if (isMounted) {
                        setAgents(listData.agents);
                        setAgent(null);
                        setIsMetadataLoading(false);
                    }
                }
            } else {
                // No agentId, must wait for list to decide which agent to load
                const listData = await listPromise;
                if (isMounted) {
                    setAgents(listData.agents);
                    if (listData.agents.length > 0) {
                        // Redirect to the first agent
                        router.replace(`/admin/agents/playground?agentId=${listData.agents[0].id}`, { scroll: false });
                    } else {
                        setAgent(null);
                        setIsMetadataLoading(false);
                    }
                }
            }

            if (isMounted) {
                setIsListingLoading(false);
            }
        };

        init();
        return () => { isMounted = false; };
    }, [agentId, router]);

    return (
        <div className="flex w-full flex-col h-screen bg-background overflow-hidden">
            {/* Header */}
            <header className="h-12 flex items-center justify-between px-4 bg-background z-30 shrink-0">
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                        <CustomBreadcrumb items={[
                            { label: "Agents Management", href: "/admin/agents" },
                            { label: "Playground", active: true }
                        ]} />
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    <Select
                        value={agent?.id || ""}
                        onValueChange={(id) => router.push(`/admin/agents/playground?agentId=${id}`)}
                        disabled={isMetadataLoading || isListingLoading}
                    >
                        <SelectTrigger className="h-9 w-[200px] bg-muted/50 border-none hover:bg-muted transition-colors gap-2">
                            <Bot className="size-3.5 text-primary" />
                            <SelectValue placeholder={isMetadataLoading ? "Loading..." : "Select Agent"} />
                        </SelectTrigger>
                        <SelectContent>
                            {agents.map((a) => (
                                <SelectItem key={a.id} value={a.id}>
                                    <div className="flex items-center gap-2">
                                        <span className="font-medium">{a.name}</span>
                                        {a.status === 'published' && (
                                            <Badge variant="secondary" className="text-[8px] h-3 px-1">PUB</Badge>
                                        )}
                                    </div>
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>

                    {agent && (
                        <Button
                            variant="outline"
                            size="sm"
                            className="h-8 gap-2 text-xs"
                            onClick={() => router.push(`/admin/agents/${agent.id}/builder`)}
                        >
                            <Settings className="size-3.5" />
                            Builder
                        </Button>
                    )}
                </div>
            </header>

            <main className="flex-1 overflow-hidden">
                {isMetadataLoading ? (
                    <div className="flex w-full h-full flex-col items-center justify-center space-y-4">
                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                        <p className="text-muted-foreground">Loading agent runner...</p>
                    </div>
                ) : !agentId || !agent ? (
                    <div className="p-6 h-full overflow-auto">
                        {!isListingLoading && agents.length === 0 && (
                            <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4 text-center border-2 border-dashed rounded-lg">
                                <div className="bg-muted p-4 rounded-full">
                                    <Plus className="h-8 w-8 text-muted-foreground" />
                                </div>
                                <div className="space-y-1">
                                    <h3 className="text-lg font-medium">No agents found</h3>
                                    <p className="text-muted-foreground max-w-sm">
                                        Get started by creating your first AI agent.
                                    </p>
                                </div>
                                <Button variant="secondary" onClick={() => router.push("/admin/agents/new")}>
                                    Create your first agent
                                </Button>
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="flex h-full overflow-hidden">
                        {/* Chat Area */}
                        <div className="flex min-w-0 flex-1">
                            <Conversation
                                dir={direction}
                                className="flex-1 relative border-none flex min-h-full flex-col overflow-hidden bg-(--chat-background)"
                                targetScrollTop={controller.isLoading ? (_target: number, { scrollElement }: any) => scrollElement?.scrollTop ?? 0 : undefined}
                            >
                                <ChatWorkspace
                                    noBackground={true}
                                    controller={controller}
                                    isVoiceModeActive={false}
                                    handleToggleVoiceMode={() => { }}
                                    onOpenArtifact={openFromMessage}
                                    isArtifactMessage={isArtifactMessage}
                                />
                            </Conversation>
                            {artifact && (
                                <ReactArtifactPane
                                    artifact={artifact}
                                    onClose={closePanel}
                                    onCodeChange={updateCode}
                                    onRun={persistCurrent}
                                    onReset={resetToSaved}
                                />
                            )}
                        </div>

                        {/* Execution Sidebar */}
                        <ExecutionSidebar
                            steps={executionSteps}
                            className="w-80 hidden lg:flex border-r"
                        />
                    </div>
                )}
            </main>
        </div>
    )
}

export default function PlaygroundPage() {
    return (
        <Suspense fallback={
            <div className="flex w-full flex-col items-center justify-center min-h-screen">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        }>
            <PlaygroundContent />
        </Suspense>
    )
}
