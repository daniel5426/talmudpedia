"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { adminService, User } from "@/services"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"

type ThreadTurn = {
  id: string;
  status: string;
  turn_index: number;
  user_input_text?: string | null;
  assistant_output_text?: string | null;
  run_usage?: {
    total_tokens?: number | null;
  } | null;
};

type ThreadDetails = {
  id: string;
  title?: string | null;
  turns: ThreadTurn[];
};

export default function AdminUserThreadPage() {
  const params = useParams()
  const userId = params.userId as string
  const threadId = params.threadId as string
  const [user, setUser] = useState<User | null>(null)
  const [thread, setThread] = useState<ThreadDetails | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const [userData, threadData] = await Promise.all([
          adminService.getUserDetails(userId),
          adminService.getThread(threadId),
        ])
        setUser(userData.user)
        setThread(threadData as ThreadDetails)
      } catch (error) {
        console.error("Failed to fetch data", error)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [userId, threadId])

  if (loading) return <div className="p-6">Loading thread...</div>
  if (!thread) return <div className="p-6">Thread not found</div>

  return (
    <div className="flex flex-col h-full w-full">
      <AdminPageHeader>
        <CustomBreadcrumb
          items={[
            { label: "Users", href: "/admin/users" },
            { label: user?.display_name || user?.full_name || user?.email || "User", href: `/admin/users/${userId}` },
            { label: thread.title || thread.id, active: true },
          ]}
        />
      </AdminPageHeader>
      <div className="flex-1 overflow-auto p-6 space-y-4" data-admin-page-scroll>
        {thread.turns.length === 0 ? (
          <div className="text-sm text-muted-foreground">No turns found.</div>
        ) : (
          thread.turns
            .slice()
            .sort((a, b) => a.turn_index - b.turn_index)
            .map((turn) => (
              <div key={turn.id} className="rounded-md border p-4 space-y-2">
                <div className="text-xs text-muted-foreground">
                  Turn #{turn.turn_index + 1} • {turn.status} • tokens: {turn.run_usage?.total_tokens || 0}
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
  );
}
