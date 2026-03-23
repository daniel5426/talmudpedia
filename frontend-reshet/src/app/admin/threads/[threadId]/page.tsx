"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useParams } from "next/navigation"
import { Loader2, Terminal } from "lucide-react"

import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
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
import { buildExecutionStepsFromRunTrace } from "@/services/run-trace-steps"
import { adminService } from "@/services"

type RuntimeAttachmentDto = {
  id: string
  filename: string
  mime_type: string
}

type ThreadTurn = {
  id?: string
  run_id?: string
  status?: string
  turn_index?: number
  user_input_text?: string | null
  assistant_output_text?: string | null
  usage_tokens?: number
  attachments?: RuntimeAttachmentDto[]
  created_at?: string
  completed_at?: string
  metadata?: Record<string, unknown> | null
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
  turns: ThreadTurn[]
}

const formatValue = (value?: string | null) => {
  const trimmed = String(value || "").trim()
  return trimmed || "—"
}

export default function AdminThreadPage() {
  const params = useParams()
  const threadId = params.threadId as string
  const { direction } = useDirection()

  const [thread, setThread] = useState<ThreadDetails | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [traceLoadingByMessageId, setTraceLoadingByMessageId] = useState<Record<string, boolean>>({})
  const [executionSteps, setExecutionSteps] = useState<ExecutionStep[]>([])
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
        const data = (await adminService.getThread(threadId)) as ThreadDetails
        const mappedMessages = await mapTurnsToMessages(
          threadId,
          Array.isArray(data.turns) ? data.turns : [],
        )
        if (!isMounted) return
        setThread(data)
        setMessages(mappedMessages)
      } catch (error) {
        console.error("Failed to fetch thread", error)
        if (!isMounted) return
        setThread(null)
        setMessages([])
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

  const handleLoadTrace = useCallback(async (message: ChatMessage) => {
    if (!message.runId) return
    setTraceLoadingByMessageId((prev) => ({ ...prev, [message.id]: true }))
    try {
      const steps = await buildExecutionStepsFromRunTrace(message.runId)
      setExecutionSteps(steps ?? [])
      setIsExecutionSidebarOpen(true)
    } catch (error) {
      console.error("Failed to load execution trace", error)
    } finally {
      setTraceLoadingByMessageId((prev) => ({ ...prev, [message.id]: false }))
    }
  }, [])

  const controller = useMemo<ChatController & { currentResponseBlocks: []; isPaused: false; pendingApproval: false }>(
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
    }),
    [copiedMessageId, disliked, handleCopy, handleLoadTrace, liked, messages, traceLoadingByMessageId],
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
            <div className="min-w-0 text-right">
              <div className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground/80">Agent</div>
              <div className="truncate font-medium text-foreground/90">{formatValue(thread.agent_name || thread.agent_id)}</div>
            </div>
            <div className="text-muted-foreground/40">/</div>
            <div className="min-w-0 text-right">
              <div className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground/80">Actor</div>
              <div className="truncate font-medium text-foreground/90">{formatValue(thread.actor_email || thread.actor_display || thread.actor_id)}</div>
            </div>
            <div className="text-muted-foreground/40">/</div>
            <div className="min-w-0 text-right">
              <div className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground/80">Status</div>
              <div className="truncate font-medium text-foreground/90">{formatValue(thread.status)}</div>
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
              <div className="flex flex-1 items-center justify-center px-6" data-admin-page-scroll>
                <div className="rounded-2xl border border-dashed px-6 py-8 text-sm text-muted-foreground">
                  No turns found.
                </div>
              </div>
            ) : (
              <Conversation
                dir={direction}
                className="relative flex min-h-full flex-1 flex-col overflow-hidden border-none bg-(--chat-background)"
                data-admin-page-scroll
              >
                <ChatWorkspace
                  controller={controller}
                  noBackground={true}
                  hideInputArea={true}
                  hideRetryAction={true}
                  isVoiceModeActive={false}
                  handleToggleVoiceMode={() => {}}
                  conversationScrollClassName="admin-page-scroll"
                />
              </Conversation>
            )}
          </div>
        </div>

        <FloatingPanel
          position="right"
          visible={isExecutionSidebarOpen}
          className="z-30 hidden w-80 lg:block"
          fullHeight={false}
        >
          <ExecutionSidebar steps={executionSteps} className="w-full" />
        </FloatingPanel>
      </main>
    </div>
  )
}
