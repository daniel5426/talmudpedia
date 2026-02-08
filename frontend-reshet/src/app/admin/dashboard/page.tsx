"use client"

import { useEffect, useState } from "react"
import { adminService, AdminStats as AdminStatsType } from "@/services"
import { DashboardContent } from "@/components/admin/dashboard-content"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Skeleton } from "@/components/ui/skeleton"

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<AdminStatsType | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const endDate = new Date()
        const startDate = new Date()
        startDate.setDate(startDate.getDate() - 30)
        const data = await adminService.getStats(
          startDate.toISOString(),
          endDate.toISOString()
        )
        setStats(data)
      } catch (error) {
        console.error("Failed to fetch stats", error)
      } finally {
        setLoading(false)
      }
    }
    fetchStats()
  }, [])

  return (
    <div className="flex flex-col h-full w-full">
      <header className="h-12 flex items-center justify-between px-4 bg-background z-30 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <CustomBreadcrumb items={[
              { label: "Dashboard", href: "/admin/dashboard", active: true },
            ]} />
          </div>
        </div>
      </header>
      <div className="flex-1 overflow-auto p-3">
        {loading ? (
          <div className="space-y-3">
            <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-4">
              {[...Array(7)].map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <Skeleton className="h-[250px] w-full" />
              <Skeleton className="h-[250px] w-full" />
            </div>
          </div>
        ) : stats ? (
          <DashboardContent stats={stats} />
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <p className="text-sm text-muted-foreground">Failed to load stats</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
