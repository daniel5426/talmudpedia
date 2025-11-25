"use client"

import { format } from "date-fns"
import { AdminStats as AdminStatsType } from "@/lib/api"
import Link from "next/link"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Users, MessageSquare, UserPlus, TrendingUp, Zap, Activity } from "lucide-react"
import { ChartBarInteractive } from "@/components/admin/charts/chart-bar-interactive"
import { ChartLineInteractive } from "@/components/admin/charts/chart-line-interactive"

interface DashboardContentProps {
  stats: AdminStatsType
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
      value: stats.total_active_users,
      icon: Activity,
      subtitle: `${stats.new_users_last_7_days} new this week`,
    },
    {
      title: "Total Chats",
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
      value: stats.new_users_last_7_days,
      icon: UserPlus,
    },
    {
      title: "Estimated Tokens",
      value: (stats.estimated_tokens / 1000000).toFixed(1) + "M",
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
        <ChartBarInteractive data={stats.daily_stats} />
        <ChartLineInteractive data={stats.daily_active_users} />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <Card className="border-border shadow-none rounded-none h-full">
          <CardHeader className="pb-3 border-b">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base font-semibold">Latest Chats</CardTitle>
              <Link href="/admin/chats" className="text-xs text-muted-foreground hover:text-primary transition-colors">
                View all →
              </Link>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {stats.latest_chats.map((chat) => (
                <Link
                  key={chat.id}
                  href={`/admin/chats/${chat.id}`}
                  className="flex items-center justify-between p-4 hover:bg-muted/50 transition-colors group"
                >
                  <div className="min-w-0 flex-1 mr-4">
                    <div className="text-sm font-medium truncate group-hover:text-primary transition-colors">
                      {chat.title || "Untitled Chat"}
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2">
                      <span>{chat.user_email || "Unknown User"}</span>
                      <span className="text-border">•</span>
                      <span>{format(new Date(chat.created_at), "MMM d, HH:mm")}</span>
                    </div>
                  </div>
                  <MessageSquare className="h-4 w-4 text-muted-foreground/50 group-hover:text-primary/50 transition-colors" />
                </Link>
              ))}
              {stats.latest_chats.length === 0 && (
                <div className="text-sm text-muted-foreground py-8 text-center">No chats found</div>
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
                  key={user.email}
                  className="flex items-center justify-between p-4 hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    <div className="flex items-center justify-center w-6 h-6 rounded-full bg-muted text-xs font-medium text-muted-foreground">
                      {index + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{user.email}</div>
                      <div className="text-xs text-muted-foreground mt-0.5">
                        {user.count} messages sent
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
