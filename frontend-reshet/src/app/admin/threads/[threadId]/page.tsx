"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { Loader2, Terminal } from "lucide-react"

import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import {
  type AdminHydratedThreadTreeNode,
  type AdminThreadTreePayloadNode,
  type AdminThreadTurn,
  hydrateThreadSubtree,
} from "@/components/admin/ThreadSubtreeBlock"
import { ExecutionSidebar } from "@/app/admin/agents/playground/ExecutionSidebar"
import { Conversation } from "@/components/ai-elements/conversation"
import { ChatWorkspace } from "@/components/layout/ChatPane"
import type { ChatController, ChatMessage } from "@/components/layout/useChatController"
import { FloatingPanel } from "@/components/builder"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { useDirection } from "@/components/direction-provider"
import { cn } from "@/lib/utils"
import { mapTurnsToMessages } from "@/hooks/useAgentThreadHistory"
import type { ExecutionStep } from "@/services/run-trace-steps"
import { loadRunTraceInspection } from "@/services/run-trace-steps"
import { adminService } from "@/services"
import type { ChatToolCallBlock } from "@/services/chat-presentation"

type UsageBucket = {
  input_tokens?: number | null
  output_tokens?: number | null
  total_tokens?: number | null
}

type ThreadDetails = {
  id: string
  title?: string | null
  status: string
  agent_id?: string | null
  agent_name?: string | null
  actor_id?: string | null
  actor_display?: string | null
  actor_email?: string | null
  token_usage?: {
    total_tokens?: number
    exact_total_tokens?: number
    estimated_total_tokens?: number
  } | null
  turns: AdminThreadTurn[]
  paging?: {
    has_more?: boolean
    next_before_turn_index?: number | null
  } | null
  subthread_tree?: AdminThreadTreePayloadNode | null
}

const THREAD_PAGE_SIZE = 20

const formatValue = (value?: string | null) => {
  const trimmed = String(value || "").trim()
  return trimmed || "—"
}

const formatTokenCount = (value?: number | null) => {
  if (value === null || value === undefined) return "—"
  return `${new Intl.NumberFormat("en-US").format(value)} tokens`
}

const formatUsageSummary = (actual?: number | null, estimated?: number | null) => {
  const actualLabel = `Exact ${formatTokenCount(actual)}`
  const estimatedLabel = `Estimate ${formatTokenCount(estimated)}`
  const hasActual = actual !== null && actual !== undefined
  const hasEstimated = estimated !== null && estimated !== undefined
  if (!hasActual && !hasEstimated) return actualLabel
  if (!hasActual) return estimatedLabel
  if (!hasEstimated) return actualLabel
  return `${actualLabel} / ${estimatedLabel}`
}

export default function AdminThreadPage() {
  const params = useParams()
  const threadId = params.threadId as string
  const { direction } = useDirection()

  const [thread, setThread] = useState<ThreadDetails | null>(null)
  const [subthreadTree, setSubthreadTree] = useState<AdminHydratedThreadTreeNode | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [isLoadingOlderHistory, setIsLoadingOlderHistory] = useState(false)
  const [paging, setPaging] = useState<ThreadDetails["paging"]>(null)
  const [traceLoadingByMessageId, setTraceLoadingByMessageId] = useState<Record<string, boolean>>({})
  const [executionSteps, setExecutionSteps] = useState<ExecutionStep[]>([])
  const [traceCopyText, setTraceCopyText] = useState<string | null>(null)
  const [isExecutionSidebarOpen, setIsExecutionSidebarOpen] = useState(false)
  const [liked, setLiked] = useState<Record<string, boolean>>({})
  const [disliked, setDisliked] = useState<Record<string, boolean>>({})
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    let isMounted = true

    const fetchThread = async () => {
      setLoading(true)
      try {
        const data = (await adminService.getThread(threadId, {
          limit: THREAD_PAGE_SIZE,
          includeSubthreads: true,
          subthreadDepth: 4,
          subthreadTurnLimit: THREAD_PAGE_SIZE,
          subthreadChildLimit: 20,
        })) as ThreadDetails
        const mappedMessages = await mapTurnsToMessages(
          threadId,
          Array.isArray(data.turns) ? data.turns : [],
        )
        const hydratedSubthreadTree = data.subthread_tree
          ? await hydrateThreadSubtree(data.subthread_tree)
          : null
        if (!isMounted) return
        setThread(data)
        setSubthreadTree(hydratedSubthreadTree)
        setMessages(mappedMessages)
        setPaging(data.paging ?? null)
      } catch (error) {
        console.error("Failed to fetch thread", error)
        if (!isMounted) return
        setThread(null)
        setSubthreadTree(null)
        setMessages([])
        setPaging(null)
      } finally {
        if (isMounted) {
          setLoading(false)
        }
      }
    }

    void fetchThread()
    return () => {
      isMounted = false
    }
  }, [threadId])

  const childThreadIdByChildRunId = useMemo(() => {
    const mapping = new Map<string, string>()

    const visit = (node: AdminHydratedThreadTreeNode | null) => {
      if (!node) return
      const children = Array.isArray(node.children) ? node.children : []
      children.forEach((child) => {
        const lastRunId = String(child.thread.last_run_id || "").trim()
        const childThreadId = String(child.thread.id || "").trim()
        if (lastRunId && childThreadId) {
          mapping.set(lastRunId, childThreadId)
        }
        visit(child)
      })
    }

    visit(subthreadTree)
    return mapping
  }, [subthreadTree])

  const handleCopy = useCallback(async (content: string, messageId: string) => {
    try {
      await navigator.clipboard.writeText(content)
      setCopiedMessageId(messageId)
      window.setTimeout(() => {
        setCopiedMessageId((current) => (current === messageId ? null : current))
      }, 1500)
    } catch (error) {
      console.error("Failed to copy thread response", error)
    }
  }, [])

  const getToolHref = useCallback((block: ChatToolCallBlock) => {
    const output = block.tool.output as Record<string, unknown> | null | undefined
    if (!output || typeof output !== "object") return null
    const childRunId =
      String((output as Record<string, unknown>).run_id || "").trim() ||
      String(
        (Array.isArray((output as Record<string, unknown>).spawned_run_ids)
          ? ((output as Record<string, unknown>).spawned_run_ids as string[])[0]
          : "") || "",
      ).trim()
    if (!childRunId) return null
    const childThreadId = childThreadIdByChildRunId.get(childRunId)
    if (!childThreadId || childThreadId === threadId) return null
    return `/admin/threads/${childThreadId}`
  }, [childThreadIdByChildRunId, threadId])

  const handleLoadTrace = useCallback(async (message: ChatMessage) => {
    if (!message.runId) return
    setTraceLoadingByMessageId((prev) => ({ ...prev, [message.id]: true }))
    try {
      const loaded = await loadRunTraceInspection(message.runId)
      setExecutionSteps(loaded?.steps ?? [])
      setTraceCopyText(loaded?.serialized ?? null)
      setIsExecutionSidebarOpen(true)
    } catch (error) {
      console.error("Failed to load execution trace", error)
    } finally {
      setTraceLoadingByMessageId((prev) => ({ ...prev, [message.id]: false }))
    }
  }, [])

  const loadOlderHistory = useCallback(async () => {
    const nextBeforeTurnIndex = paging?.next_before_turn_index
    if (nextBeforeTurnIndex === null || nextBeforeTurnIndex === undefined || isLoadingOlderHistory) {
      return null
    }
    setIsLoadingOlderHistory(true)
    try {
      const data = (await adminService.getThread(threadId, {
        beforeTurnIndex: nextBeforeTurnIndex,
        limit: THREAD_PAGE_SIZE,
      })) as ThreadDetails
      const olderMessages = await mapTurnsToMessages(
        threadId,
        Array.isArray(data.turns) ? data.turns : [],
      )
      setMessages((current) => [...olderMessages, ...current])
      setPaging(data.paging ?? null)
      return data
    } catch (error) {
      console.error("Failed to load older thread turns", error)
      return null
    } finally {
      setIsLoadingOlderHistory(false)
    }
  }, [isLoadingOlderHistory, paging?.next_before_turn_index, threadId])

  const controller = useMemo<
    ChatController & {
      currentResponseBlocks: []
      isPaused: false
      pendingApproval: false
      hasOlderHistory: boolean
      isLoadingOlderHistory: boolean
      loadOlderHistory: () => Promise<ThreadDetails | null>
    }
  >(
    () => ({
      messages,
      streamingContent: "",
      currentReasoning: [],
      currentResponseBlocks: [],
      isLoading: false,
      isLoadingHistory: false,
      liked,
      disliked,
      copiedMessageId,
      lastThinkingDurationMs: null,
      activeStreamingId: null,
      handleSubmit: async () => {},
      handleStop: () => {},
      handleCopy: (content, messageId) => {
        void handleCopy(content, messageId)
      },
      handleLike: async (msg) => {
        setLiked((prev) => ({ ...prev, [msg.id]: !prev[msg.id] }))
        setDisliked((prev) => ({ ...prev, [msg.id]: false }))
      },
      handleDislike: async (msg) => {
        setDisliked((prev) => ({ ...prev, [msg.id]: !prev[msg.id] }))
        setLiked((prev) => ({ ...prev, [msg.id]: false }))
      },
      handleRetry: async () => {},
      handleLoadTrace,
      handleSourceClick: () => {},
      traceLoadingByMessageId,
      upsertLiveVoiceMessage: () => {},
      refresh: async () => {},
      textareaRef,
      isPaused: false,
      pendingApproval: false,
      hasOlderHistory: Boolean(paging?.has_more),
      isLoadingOlderHistory,
      loadOlderHistory,
    }),
    [copiedMessageId, disliked, handleCopy, handleLoadTrace, isLoadingOlderHistory, liked, loadOlderHistory, messages, paging?.has_more, traceLoadingByMessageId],
  )

  if (loading) {
    return (
      <div className="flex h-screen w-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (!thread) {
    return <div className="p-6">Thread not found</div>
  }

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-background [&_button]:shadow-none">
      <AdminPageHeader>
        <CustomBreadcrumb
          items={[
            { label: "Threads", href: "/admin/threads" },
            { label: thread.title || thread.id, active: true },
          ]}
        />

        <div className="flex min-w-0 items-center gap-3">
          <div className="hidden min-w-0 items-center gap-3 text-sm lg:flex">
            {thread.agent_id ? (
              <Link
                href={`/admin/agents/${thread.agent_id}/builder`}
                className="min-w-0 truncate font-medium text-foreground/90 hover:underline"
                title={formatValue(thread.agent_name || thread.agent_id)}
              >
                {formatValue(thread.agent_name || thread.agent_id)}
              </Link>
            ) : (
              <div className="min-w-0 truncate font-medium text-foreground/90">{formatValue(thread.agent_name || thread.agent_id)}</div>
            )}
            <div className="text-muted-foreground/40">/</div>
            {thread.actor_id ? (
              <Link
                href={`/admin/users/${thread.actor_id}`}
                className="min-w-0 truncate font-medium text-foreground/90 hover:underline"
                title={formatValue(thread.actor_email || thread.actor_display || thread.actor_id)}
              >
                {formatValue(thread.actor_email || thread.actor_display || thread.actor_id)}
              </Link>
            ) : (
              <div className="min-w-0 truncate font-medium text-foreground/90">
                {formatValue(thread.actor_email || thread.actor_display || thread.actor_id)}
              </div>
            )}
            <div className="text-muted-foreground/40">/</div>
            <div className="min-w-0 truncate font-medium text-foreground/90">
              {formatUsageSummary(
                thread.token_usage?.exact_total_tokens ?? null,
                thread.token_usage?.estimated_total_tokens ?? null,
              )}
            </div>
          </div>
          <button
            type="button"
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border bg-background/90 text-xs font-medium text-foreground backdrop-blur hover:bg-muted transition-colors"
            onClick={() => setIsExecutionSidebarOpen((prev) => !prev)}
            aria-label={isExecutionSidebarOpen ? "Hide execution traces" : "Show execution traces"}
          >
            <Terminal className="h-3.5 w-3.5" />
          </button>
        </div>
      </AdminPageHeader>

      <main className="relative flex-1 overflow-hidden">
        <div
          className={cn(
            "relative flex h-full overflow-hidden transition-[padding] duration-300",
            isExecutionSidebarOpen && "lg:pr-[332px]",
          )}
        >
          <div className="flex min-w-0 flex-1">
            {messages.length === 0 ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6 py-6" data-admin-page-scroll>
                <div className="rounded-2xl border border-dashed px-6 py-8 text-sm text-muted-foreground">
                  No turns found in the main thread.
                </div>
              </div>
            ) : (
              <div className="flex min-h-full flex-1 flex-col overflow-y-auto" data-admin-page-scroll>
                <Conversation
                  dir={direction}
                  className="relative flex flex-1 flex-col overflow-hidden border-none bg-(--chat-background)"
                >
                  <ChatWorkspace
                    controller={controller}
                    noBackground={true}
                    hideInputArea={true}
                    hideRetryAction={true}
                    isVoiceModeActive={false}
                    handleToggleVoiceMode={() => {}}
                    showAssistantAvatar={false}
                    conversationScrollClassName="admin-page-scroll"
                    getToolHref={getToolHref}
                  />
                </Conversation>
              </div>
            )}
          </div>
        </div>

        <FloatingPanel
          position="right"
          visible={isExecutionSidebarOpen}
          className="z-30 hidden w-80 lg:block"
          fullHeight={false}
        >
          <ExecutionSidebar steps={executionSteps} copyText={traceCopyText} className="w-full" />
        </FloatingPanel>
      </main>
    </div>
  )
}
