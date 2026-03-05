"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { adminService } from "@/services"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"

type ThreadTurn = {
  id: string;
  status: string;
  turn_index: number;
  user_input_text?: string | null;
  assistant_output_text?: string | null;
  usage_tokens?: number;
  created_at?: string;
};

type ThreadDetails = {
  id: string;
  title?: string | null;
  status: string;
  turns: ThreadTurn[];
};

export default function AdminThreadPage() {
  const params = useParams()
  const threadId = params.threadId as string
  const [thread, setThread] = useState<ThreadDetails | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchThread = async () => {
      setLoading(true)
      try {
        const data = await adminService.getThread(threadId)
        setThread(data as ThreadDetails)
      } catch (error) {
        console.error("Failed to fetch thread", error)
      } finally {
        setLoading(false)
      }
    }
    fetchThread()
  }, [threadId])

  if (loading) {
    return <div className="p-6">Loading thread...</div>
  }
  if (!thread) {
    return <div className="p-6">Thread not found</div>
  }

  return (
    <div className="flex flex-col h-full w-full">
      <header className="h-12 flex items-center justify-between px-4 bg-background z-30 shrink-0 border-b">
        <CustomBreadcrumb
          items={[
            { label: "Threads", href: "/admin/threads" },
            { label: thread.title || thread.id, active: true },
          ]}
        />
      </header>
      <div className="flex-1 overflow-auto p-6 space-y-4">
        {thread.turns.length === 0 ? (
          <div className="text-sm text-muted-foreground">No turns found.</div>
        ) : (
          thread.turns
            .slice()
            .sort((a, b) => a.turn_index - b.turn_index)
            .map((turn) => (
              <div key={turn.id} className="rounded-md border p-4 space-y-2">
                <div className="text-xs text-muted-foreground">
                  Turn #{turn.turn_index + 1} • {turn.status} • tokens: {turn.usage_tokens || 0}
                </div>
                {turn.user_input_text ? (
                  <div>
                    <div className="text-xs font-medium text-muted-foreground">User</div>
                    <div className="whitespace-pre-wrap text-sm">{turn.user_input_text}</div>
                  </div>
                ) : null}
                {turn.assistant_output_text ? (
                  <div>
                    <div className="text-xs font-medium text-muted-foreground">Assistant</div>
                    <div className="whitespace-pre-wrap text-sm">{turn.assistant_output_text}</div>
                  </div>
                ) : null}
              </div>
            ))
        )}
      </div>
    </div>
  )
}
