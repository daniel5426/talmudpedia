"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react"

import { mapTurnsToMessages } from "@/hooks/useAgentThreadHistory"
import { adminService } from "@/services"
import type { ChatMessage } from "@/components/layout/useChatController"

export type AdminRuntimeAttachmentDto = {
  id: string
  filename: string
  mime_type: string
}

export type AdminThreadTurn = {
  id?: string
  run_id?: string
  status?: string
  turn_index?: number
  user_input_text?: string | null
  assistant_output_text?: string | null
  run_usage?: {
    source?: string | null
    input_tokens?: number | null
    output_tokens?: number | null
    total_tokens?: number | null
  } | null
  attachments?: AdminRuntimeAttachmentDto[]
  created_at?: string
  completed_at?: string
  metadata?: Record<string, unknown> | null
}

export type AdminThreadLineage = {
  root_thread_id?: string | null
  parent_thread_id?: string | null
  parent_thread_turn_id?: string | null
  spawned_by_run_id?: string | null
  depth?: number
  is_root?: boolean
}

export type AdminThreadTreePayloadNode = {
  thread: {
    id: string
    title?: string | null
    status?: string | null
    surface?: string | null
    agent_id?: string | null
    agent_name?: string | null
    last_run_id?: string | null
    created_at?: string
    updated_at?: string
    last_activity_at?: string
  }
  lineage?: AdminThreadLineage | null
  turns?: AdminThreadTurn[]
  paging?: {
    has_more?: boolean
    next_before_turn_index?: number | null
  } | null
  has_children?: boolean
  children?: AdminThreadTreePayloadNode[]
}

export type AdminHydratedThreadTreeNode = Omit<AdminThreadTreePayloadNode, "children"> & {
  messages: ChatMessage[]
  children: AdminHydratedThreadTreeNode[]
}

type ThreadDetailResponse = {
  subthread_tree?: AdminThreadTreePayloadNode | null
}

type ThreadSubtreeBlockProps = {
  initialNode: AdminHydratedThreadTreeNode
  onLoadTrace: (message: ChatMessage) => Promise<void> | void
  traceLoadingByMessageId: Record<string, boolean>
  depth?: number
  defaultExpanded?: boolean
}

const SUBTHREAD_PAGE_SIZE = 20

const formatTimestamp = (value?: string) => {
  if (!value) return null
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) return null
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(parsed))
}

const formatValue = (value?: string | null) => {
  const trimmed = String(value || "").trim()
  return trimmed || "Untitled thread"
}

export async function hydrateThreadSubtree(
  node: AdminThreadTreePayloadNode,
): Promise<AdminHydratedThreadTreeNode> {
  const turns = Array.isArray(node.turns) ? node.turns : []
  const children = Array.isArray(node.children) ? node.children : []
  return {
    ...node,
    messages: await mapTurnsToMessages(node.thread.id, turns),
    children: await Promise.all(children.map((child) => hydrateThreadSubtree(child))),
  }
}

export function ThreadSubtreeBlock({
  initialNode,
  onLoadTrace,
  traceLoadingByMessageId,
  depth = 0,
  defaultExpanded = false,
}: ThreadSubtreeBlockProps) {
  const [node, setNode] = useState(initialNode)
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)
  const [isLoadingChildren, setIsLoadingChildren] = useState(false)

  useEffect(() => {
    setNode(initialNode)
    setIsExpanded(defaultExpanded)
  }, [defaultExpanded, initialNode])

  const handleToggle = async () => {
    const nextExpanded = !isExpanded
    setIsExpanded(nextExpanded)
    if (!nextExpanded || isLoadingChildren) return
    if (!node.has_children || node.children.length > 0) return
    setIsLoadingChildren(true)
    try {
      const payload = (await adminService.getThread(node.thread.id, {
        limit: SUBTHREAD_PAGE_SIZE,
        includeSubthreads: true,
        subthreadDepth: 1,
        subthreadTurnLimit: SUBTHREAD_PAGE_SIZE,
        subthreadChildLimit: 20,
      })) as ThreadDetailResponse
      if (payload.subthread_tree) {
        setNode(await hydrateThreadSubtree(payload.subthread_tree))
      }
    } catch (error) {
      console.error("Failed to load subthread tree", { threadId: node.thread.id, error })
    } finally {
      setIsLoadingChildren(false)
    }
  }

  return (
    <div
      className="rounded-2xl border border-border/60 bg-background/70 p-4"
      style={{ marginLeft: depth > 0 ? `${Math.min(depth, 4) * 16}px` : undefined }}
    >
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void handleToggle()}
          className="inline-flex items-center gap-2 rounded-md text-left text-sm font-medium text-foreground hover:text-primary transition-colors"
        >
          {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          <span>{formatValue(node.thread.title)}</span>
        </button>
        <span className="text-xs text-muted-foreground">{formatValue(node.thread.agent_name || node.thread.agent_id)}</span>
        <span className="text-xs text-muted-foreground/70">{formatValue(node.thread.status)}</span>
        {formatTimestamp(node.thread.last_activity_at || node.thread.updated_at || node.thread.created_at) ? (
          <span className="text-xs text-muted-foreground/70">
            {formatTimestamp(node.thread.last_activity_at || node.thread.updated_at || node.thread.created_at)}
          </span>
        ) : null}
        <Link
          href={`/admin/threads/${node.thread.id}`}
          className="ml-auto text-xs font-medium text-primary hover:underline"
        >
          Open thread
        </Link>
      </div>

      {isExpanded ? (
        <div className="mt-4 space-y-4">
          {node.messages.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border/60 px-4 py-3 text-sm text-muted-foreground">
              No turns in this subthread.
            </div>
          ) : (
            <div className="space-y-3">
              {node.messages.map((message) => (
                <div key={message.id} className="rounded-xl border border-border/50 bg-muted/20 px-4 py-3">
                  <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
                    {message.role}
                  </div>
                  <div className="whitespace-pre-wrap text-sm text-foreground">{String(message.content || "")}</div>
                  {message.runId ? (
                    <button
                      type="button"
                      onClick={() => void onLoadTrace(message)}
                      className="mt-3 text-xs font-medium text-primary hover:underline"
                      disabled={Boolean(traceLoadingByMessageId[message.id])}
                    >
                      {traceLoadingByMessageId[message.id] ? "Loading trace..." : "Trace"}
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
          )}

          {isLoadingChildren ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading subthreads...
            </div>
          ) : null}

          {node.children.length > 0 ? (
            <div className="space-y-3">
              {node.children.map((child) => (
                <ThreadSubtreeBlock
                  key={child.thread.id}
                  initialNode={child}
                  onLoadTrace={onLoadTrace}
                  traceLoadingByMessageId={traceLoadingByMessageId}
                  depth={depth + 1}
                />
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

type LazyThreadSubtreeBlockProps = {
  threadId: string
  onLoadTrace: (message: ChatMessage) => Promise<void> | void
  traceLoadingByMessageId: Record<string, boolean>
}

export function LazyThreadSubtreeBlock({
  threadId,
  onLoadTrace,
  traceLoadingByMessageId,
}: LazyThreadSubtreeBlockProps) {
  const [node, setNode] = useState<AdminHydratedThreadTreeNode | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true

    const load = async () => {
      setIsLoading(true)
      setLoadError(null)
      try {
        const payload = (await adminService.getThread(threadId, {
          limit: SUBTHREAD_PAGE_SIZE,
          includeSubthreads: true,
          subthreadDepth: 1,
          subthreadTurnLimit: SUBTHREAD_PAGE_SIZE,
          subthreadChildLimit: 20,
        })) as ThreadDetailResponse
        if (!payload.subthread_tree) {
          throw new Error("Subthread tree not found")
        }
        const hydrated = await hydrateThreadSubtree(payload.subthread_tree)
        if (!isMounted) return
        setNode(hydrated)
      } catch (error) {
        console.error("Failed to load inline subthread", { threadId, error })
        if (!isMounted) return
        setLoadError("Failed to load subthread.")
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    }

    void load()
    return () => {
      isMounted = false
    }
  }, [threadId])

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-border/50 bg-muted/20 px-4 py-3 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading subthread...
      </div>
    )
  }

  if (loadError || !node) {
    return (
      <div className="rounded-xl border border-dashed border-border/60 px-4 py-3 text-sm text-muted-foreground">
        {loadError || "Subthread unavailable."}
      </div>
    )
  }

  return (
    <ThreadSubtreeBlock
      initialNode={node}
      onLoadTrace={onLoadTrace}
      traceLoadingByMessageId={traceLoadingByMessageId}
      depth={1}
      defaultExpanded
    />
  )
}
