"use client"

import { format } from "date-fns"
import { type AdminStatsOverview } from "@/services"
import Link from "next/link"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Users, MessageSquare, UserPlus, TrendingUp, Zap, Activity } from "lucide-react"
import { ChartBarInteractive } from "@/components/admin/charts/chart-bar-interactive"
import { ChartLineInteractive } from "@/components/admin/charts/chart-line-interactive"

interface DashboardContentProps {
  stats: AdminStatsOverview
}

const StatCard = ({ 
  title, 
  value, 
  icon: Icon, 
  subtitle
}: { 
  title: string
  value: string | number
  icon: typeof Users
  subtitle?: string
}) => {
  return (
    <Card className="py-2 border-border shadow-none rounded-none">
      <div className="px-4 flex items-center justify-between">
        <div className="flex-1 min-w-0">
          <div className="text-xs text-muted-foreground mb-0.5">{title}</div>
          <div className="text-xl font-semibold">{value}</div>
          {subtitle && (
            <div className="text-xs text-muted-foreground mt-0.5">{subtitle}</div>
          )}
        </div>
        <Icon className="h-4 w-4 text-muted-foreground shrink-0 ml-2" />
      </div>
    </Card>
  )
}



export function DashboardContent({ stats }: DashboardContentProps) {
  const statCards = [
    {
      title: "Total Users",
      value: stats.total_users,
      icon: Users,
    },
    {
      title: "Active Users (7d)",
      value: stats.active_users,
      icon: Activity,
      subtitle: `${stats.new_users} new in range`,
    },
    {
      title: "Total Threads",
      value: stats.total_chats,
      icon: MessageSquare,
    },
    {
      title: "Total Messages",
      value: stats.total_messages.toLocaleString(),
      icon: Zap,
    },
    {
      title: "Avg per Chat",
      value: stats.avg_messages_per_chat.toFixed(1),
      icon: TrendingUp,
    },
    {
      title: "New Users (7d)",
      value: stats.new_users,
      icon: UserPlus,
    },
    {
      title: "Estimated Tokens",
      value: (stats.total_tokens / 1000000).toFixed(1) + "M",
      icon: Zap,
    },
  ]

  return (
    <div className="space-y-3">
      <div className="grid gap-2 grid-cols-2 md:grid-cols-3 lg:grid-cols-5 xl:grid-cols-7">
        {statCards.map((stat, index) => (
          <StatCard key={index} {...stat} />
        ))}
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <ChartBarInteractive data={stats.tokens_by_day.map((item) => ({ date: item.date, chats: item.value }))} />
        <ChartLineInteractive data={stats.daily_active_users.map((item) => ({ date: item.date, count: item.value }))} />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <Card className="border-border shadow-none rounded-none h-full">
          <CardHeader className="pb-3 border-b">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base font-semibold">Latest Threads</CardTitle>
              <Link href="/admin/threads" className="text-xs text-muted-foreground hover:text-primary transition-colors">
                View all →
              </Link>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {stats.recent_threads.map((thread) => (
                <Link
                  key={thread.id}
                  href={`/admin/threads/${thread.id}`}
                  className="flex items-center justify-between p-4 hover:bg-muted/50 transition-colors group"
                >
                  <div className="min-w-0 flex-1 mr-4">
                    <div className="text-sm font-medium truncate group-hover:text-primary transition-colors">
                      {thread.title || "Untitled Thread"}
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2">
                      <span>{thread.actor_email || thread.actor_display || "Unknown User"}</span>
                      <span className="text-border">•</span>
                      <span>{thread.created_at ? format(new Date(thread.created_at), "MMM d, HH:mm") : "—"}</span>
                    </div>
                  </div>
                  <MessageSquare className="h-4 w-4 text-muted-foreground/50 group-hover:text-primary/50 transition-colors" />
                </Link>
              ))}
              {stats.recent_threads.length === 0 && (
                <div className="text-sm text-muted-foreground py-8 text-center">No threads found</div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="border-border shadow-none rounded-none h-full">
          <CardHeader className="pb-3 border-b">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base font-semibold">Top Active Users</CardTitle>
              <Link href="/admin/users" className="text-xs text-muted-foreground hover:text-primary transition-colors">
                View all →
              </Link>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {stats.top_users.map((user, index) => (
                <div
                  key={user.user_id}
                  className="flex items-center justify-between p-4 hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    <div className="flex items-center justify-center w-6 h-6 rounded-full bg-muted text-xs font-medium text-muted-foreground">
                      {index + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{user.display_name || user.email || "Unknown actor"}</div>
                      <div className="text-xs text-muted-foreground mt-0.5">
                        {user.count} runs
                      </div>
                    </div>
                  </div>
                  <div className="text-xs font-medium bg-primary/10 text-primary px-2 py-1 rounded-full">
                    Top {index + 1}
                  </div>
                </div>
              ))}
              {stats.top_users.length === 0 && (
                <div className="text-sm text-muted-foreground py-8 text-center">No active users found</div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
