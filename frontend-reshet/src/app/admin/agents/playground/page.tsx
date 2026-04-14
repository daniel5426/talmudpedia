"use client"

import { useState, useEffect, useRef, useCallback, useMemo, Suspense } from "react"
import dynamic from "next/dynamic"
import { useRouter, useSearchParams } from "next/navigation"
import {
    Loader2,
    Pencil,
    Bot,
    Terminal,
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
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { useReactArtifactPanel } from "@/lib/react-artifacts/useReactArtifactPanel"
import { parseReactArtifact } from "@/lib/react-artifacts/parseReactArtifact"
import { useTenant } from "@/contexts/TenantContext"
import { useAuthStore } from "@/lib/store/useAuthStore"
import { ExecutionHistoryDropdown } from "@/components/agent-builder/ExecutionHistoryDropdown"
import { FloatingPanel } from "@/components/builder"
import { cn } from "@/lib/utils"
import type { AgentChatHistoryItem } from "@/hooks/useAgentThreadHistory"

const ReactArtifactPane = dynamic(
    () => import("@/components/ai-elements/ReactArtifactPane").then((mod) => mod.ReactArtifactPane),
    { ssr: false }
)

const logPlaygroundDebug = (event: string, details?: Record<string, unknown>) => {
    if (process.env.NODE_ENV === "production") return
    console.debug("[playground-thread-debug]", event, details || {})
}

function PlaygroundContent() {
    const router = useRouter()
    const searchParams = useSearchParams()
    const agentId = searchParams.get("agentId")
    const threadId = searchParams.get("threadId")

    const [agent, setAgent] = useState<Agent | null>(null)
    const [agents, setAgents] = useState<Agent[]>([])
    const [isMetadataLoading, setIsMetadataLoading] = useState(true)
    const [isListingLoading, setIsListingLoading] = useState(false)
    const [isExecutionSidebarOpen, setIsExecutionSidebarOpen] = useState(false)
    const hydratedThreadRef = useRef<string | null>(null)
    const suppressedThreadIdRef = useRef<string | null>(null)
    const pendingUrlThreadIdRef = useRef<string | null>(null)
    const clearingThreadRef = useRef(false)

    const controller = useAgentRunController(agentId || undefined, agent?.graph_definition, agent?.slug)
    const { executionSteps, currentThreadId, inspectedTraceCopyText } = controller
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
    const visibleAgents = useMemo(
        () => agents.filter((item) => item.show_in_playground !== false),
        [agents],
    )

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
                        setAgents(listData.agents);
                        const visibleList = listData.agents.filter((item) => item.show_in_playground !== false);
                        setAgent(agentData.show_in_playground === false ? null : agentData);
                        setIsMetadataLoading(false);
                        if (agentData.show_in_playground === false && visibleList.length > 0) {
                            router.replace(`/admin/agents/playground?agentId=${visibleList[0].id}`, { scroll: false });
                        }
                    }
                } catch (err) {
                    console.error("Failed to load agent metadata:", err);
                    const listData = await listPromise;
                    if (isMounted) {
                        setAgents(listData.agents);
                        setAgent(null);
                        setIsMetadataLoading(false);
                        const visibleList = listData.agents.filter((item) => item.show_in_playground !== false);
                        if (visibleList.length > 0) {
                            router.replace(`/admin/agents/playground?agentId=${visibleList[0].id}`, { scroll: false });
                        }
                    }
                }
            } else {
                // No agentId, must wait for list to decide which agent to load
                const listData = await listPromise;
                if (isMounted) {
                    setAgents(listData.agents);
                    const visibleList = listData.agents.filter((item) => item.show_in_playground !== false);
                    if (visibleList.length > 0) {
                        // Redirect to the first agent
                        router.replace(`/admin/agents/playground?agentId=${visibleList[0].id}`, { scroll: false });
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

    const handleSelectHistory = useCallback((item: AgentChatHistoryItem) => {
        logPlaygroundDebug("history.select.start", {
            itemThreadId: item.threadId,
            itemAgentId: item.agentId,
            currentAgentId: agentId,
            currentThreadId,
            urlThreadId: threadId,
        })
        if (!item?.threadId) {
            return
        }
        if (item.threadId === threadId && (item.agentId || agentId) === agentId) {
            logPlaygroundDebug("history.select.skip.already-active", {
                itemThreadId: item.threadId,
                currentAgentId: agentId,
                urlThreadId: threadId,
            })
            return
        }
        const resolvedAgentId = item.agentId || agentId
        if (!resolvedAgentId) {
            return
        }
        pendingUrlThreadIdRef.current = item.threadId
        if (resolvedAgentId === agentId) {
            hydratedThreadRef.current = null
            logPlaygroundDebug("history.select.replace.same-agent", {
                targetThreadId: item.threadId,
                pendingUrlThreadId: pendingUrlThreadIdRef.current,
                hydratedThreadKey: hydratedThreadRef.current,
            })
            router.replace(`/admin/agents/playground?agentId=${resolvedAgentId}&threadId=${item.threadId}`, { scroll: false })
            return
        }
        hydratedThreadRef.current = null
        logPlaygroundDebug("history.select.push.cross-agent", {
            targetAgentId: resolvedAgentId,
            targetThreadId: item.threadId,
        })
        router.push(`/admin/agents/playground?agentId=${resolvedAgentId}&threadId=${item.threadId}`, { scroll: false })
    }, [agentId, currentThreadId, router, threadId])

    useEffect(() => {
        if (clearingThreadRef.current) {
            logPlaygroundDebug("history.hydration.skip.clearing-thread", {
                agentId,
                urlThreadId: threadId,
                currentThreadId,
                suppressedThreadId: suppressedThreadIdRef.current,
            })
            return
        }
        if (!threadId || !agentId || isMetadataLoading || isListingLoading) return
        const hydrationKey = `${agentId}:${threadId}`
        if (hydratedThreadRef.current === hydrationKey) {
            logPlaygroundDebug("history.hydration.skip.already-hydrated", {
                hydrationKey,
                currentHydratedKey: hydratedThreadRef.current,
            })
            return
        }
        const target = controller.history.find((item) => item.threadId === threadId)
        hydratedThreadRef.current = hydrationKey
        logPlaygroundDebug(target ? "history.hydration.load" : "history.hydration.load.direct", {
            hydrationKey,
            currentThreadId,
            urlThreadId: threadId,
            knownThreadIds: controller.history.map((item) => item.threadId),
        })
        void (async () => {
            if (target) {
                await controller.loadHistoryChat(target)
                return
            }
            await controller.loadHistoryChatById(threadId)
        })()
    }, [agentId, controller, currentThreadId, isListingLoading, isMetadataLoading, threadId])

    useEffect(() => {
        if (clearingThreadRef.current) {
            if (!threadId && !currentThreadId) {
                logPlaygroundDebug("url-sync.clear.thread-clear-complete", {
                    agentId,
                })
                clearingThreadRef.current = false
                suppressedThreadIdRef.current = null
                pendingUrlThreadIdRef.current = null
                return
            }
            logPlaygroundDebug("url-sync.skip.clearing-thread", {
                agentId,
                urlThreadId: threadId,
                currentThreadId,
                suppressedThreadId: suppressedThreadIdRef.current,
            })
            return
        }
        if (pendingUrlThreadIdRef.current) {
            if (currentThreadId !== pendingUrlThreadIdRef.current) {
                logPlaygroundDebug("url-sync.skip.pending-thread-navigation", {
                    pendingUrlThreadId: pendingUrlThreadIdRef.current,
                    currentThreadId,
                    urlThreadId: threadId,
                })
                return
            }
            if (threadId === pendingUrlThreadIdRef.current) {
                logPlaygroundDebug("url-sync.clear.pending-url-thread", {
                    pendingUrlThreadId: pendingUrlThreadIdRef.current,
                    urlThreadId: threadId,
                })
                pendingUrlThreadIdRef.current = null
            }
        }
        if (suppressedThreadIdRef.current) {
            if (!currentThreadId) {
                logPlaygroundDebug("url-sync.clear.suppressed-thread.after-reset", {
                    suppressedThreadId: suppressedThreadIdRef.current,
                })
                suppressedThreadIdRef.current = null
                return
            }
            if (currentThreadId === suppressedThreadIdRef.current) {
                logPlaygroundDebug("url-sync.skip.suppressed-current-thread", {
                    suppressedThreadId: suppressedThreadIdRef.current,
                    currentThreadId,
                    urlThreadId: threadId,
                })
                return
            }
            logPlaygroundDebug("url-sync.clear.suppressed-thread.changed", {
                suppressedThreadId: suppressedThreadIdRef.current,
                currentThreadId,
            })
            suppressedThreadIdRef.current = null
        }
        if (!agentId || !currentThreadId) {
            logPlaygroundDebug("url-sync.skip.missing-agent-or-thread", {
                agentId,
                currentThreadId,
                urlThreadId: threadId,
            })
            return
        }
        if (threadId === currentThreadId) {
            logPlaygroundDebug("url-sync.skip.already-synced", {
                agentId,
                currentThreadId,
            })
            return
        }
        hydratedThreadRef.current = `${agentId}:${currentThreadId}`
        logPlaygroundDebug("url-sync.replace.thread", {
            agentId,
            currentThreadId,
            urlThreadId: threadId,
            hydratedThreadKey: hydratedThreadRef.current,
        })
        router.replace(`/admin/agents/playground?agentId=${agentId}&threadId=${currentThreadId}`, { scroll: false })
    }, [agentId, currentThreadId, router, threadId])

    const handleStartNewThread = useCallback(() => {
        clearingThreadRef.current = true
        suppressedThreadIdRef.current = currentThreadId
        pendingUrlThreadIdRef.current = null
        hydratedThreadRef.current = null
        logPlaygroundDebug("new-thread.start", {
            agentId,
            currentThreadId,
            urlThreadId: threadId,
            suppressedThreadId: suppressedThreadIdRef.current,
        })
        controller.startNewChat()
        if (agentId) {
            logPlaygroundDebug("new-thread.replace.base-url", {
                agentId,
            })
            router.replace(`/admin/agents/playground?agentId=${agentId}`, { scroll: false })
        }
    }, [agentId, controller, currentThreadId, router, threadId])

    const chatController = useMemo(() => ({
        ...controller,
        handleLoadTrace: async (message: AgentChatHistoryItem["messages"][number]) => {
            setIsExecutionSidebarOpen(true)
            await controller.handleLoadTrace(message)
        },
    }), [controller])

    return (
        <div className="flex w-full flex-col h-screen bg-background overflow-hidden [&_button]:shadow-none">
            {/* Header */}
            <AdminPageHeader>
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                        <CustomBreadcrumb items={[
                            { label: "Agents Management", href: "/admin/agents" },
                            { label: "Playground", active: true }
                        ]} />
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    <button
                        type="button"
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md border bg-background/90 text-xs font-medium text-foreground backdrop-blur hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        onClick={() => setIsExecutionSidebarOpen((prev) => !prev)}
                        disabled={!agent || isMetadataLoading}
                        aria-label={isExecutionSidebarOpen ? "Hide execution traces" : "Show execution traces"}
                    >
                        <Terminal className="h-3.5 w-3.5" />
                    </button>

                    <ExecutionHistoryDropdown
                        historyItems={controller.history}
                        loading={controller.historyLoading}
                        label={null}
                        ariaLabel="Show history"
                        align="end"
                        showChevron={false}
                        onSelectHistory={handleSelectHistory}
                        onStartNewChat={handleStartNewThread}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md border bg-background/90 text-xs font-medium text-foreground backdrop-blur hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        contentClassName="w-[320px] max-w-[min(90vw,320px)] max-h-[360px] overflow-y-auto"
                    />

                    {agent && (
                        <Button
                            variant="outline"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => router.push(`/admin/agents/${agent.id}/builder`)}
                            aria-label="Edit agent"
                            title="Edit agent"
                        >
                            <Pencil className="size-3.5" />
                        </Button>
                    )}

                    <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-8 gap-1.5"
                        onClick={handleStartNewThread}
                        disabled={!agent || isMetadataLoading}
                    >
                        <Plus className="size-3.5" />
                        <span>New Thread</span>
                    </Button>

                    <Select
                        value={agent?.id || ""}
                        onValueChange={(id) => router.push(`/admin/agents/playground?agentId=${id}`)}
                        disabled={isMetadataLoading || isListingLoading}
                    >
                        <SelectTrigger className="h-9 w-[200px] bg-muted/50 border-none hover:bg-muted transition-colors gap-2">
                            <Bot className="size-3.5 text-primary" />
                            <SelectValue placeholder={isMetadataLoading ? "Loading..." : "Select Agent"} />
                        </SelectTrigger>
                        <SelectContent className="w-[280px] max-w-[min(90vw,280px)] max-h-[320px]">
                            {visibleAgents.map((a) => (
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
                </div>
            </AdminPageHeader>

            <main className="relative flex-1 overflow-hidden">
                {isMetadataLoading ? (
                    <div className="flex w-full h-full flex-col items-center justify-center space-y-4">
                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                        <p className="text-muted-foreground">Loading agent runner...</p>
                    </div>
                ) : !agentId || !agent ? (
                    <div className="p-6 h-full overflow-auto" data-admin-page-scroll>
                        {!isListingLoading && visibleAgents.length === 0 && (
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
                    <div
                        className={cn(
                            "flex h-full overflow-hidden transition-[padding] duration-300",
                            isExecutionSidebarOpen && "lg:pr-[332px]"
                        )}
                    >
                        {/* Chat Area */}
                        <div className="flex min-w-0 flex-1">
                            <Conversation
                                dir={direction}
                                className="flex-1 relative border-none flex min-h-full flex-col overflow-hidden bg-(--chat-background)"
                                data-admin-page-scroll
                                targetScrollTop={controller.isLoading ? (_target: number, { scrollElement }: any) => scrollElement?.scrollTop ?? 0 : undefined}
                            >
                                <ChatWorkspace
                                    noBackground={true}
                                    controller={chatController}
                                    isVoiceModeActive={false}
                                    handleToggleVoiceMode={() => { }}
                                    showAssistantAvatar={false}
                                    conversationScrollClassName="admin-page-scroll"
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

                    </div>
                )}

                <FloatingPanel
                    position="right"
                    visible={Boolean(isExecutionSidebarOpen && agent && !isMetadataLoading)}
                    className="w-80 z-30 hidden lg:block"
                    fullHeight={false}
                >
                    <ExecutionSidebar
                        steps={executionSteps}
                        copyText={inspectedTraceCopyText}
                        className="w-full"
                    />
                </FloatingPanel>
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
