"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { adminService, User, Thread } from "@/services"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { ThreadsTable } from "@/components/admin/threads-table"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"

export default function AdminUserPage() {
  const params = useParams()
  const userId = params.userId as string
  const [user, setUser] = useState<User | null>(null)
  const [stats, setStats] = useState<any>(null)
  const [threads, setThreads] = useState<Thread[]>([])
  const [pageCount, setPageCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [pagination, setPagination] = useState({
    pageIndex: 0,
    pageSize: 20,
  })
  const [search, setSearch] = useState("")

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const data = await adminService.getUserDetails(userId)
        setUser(data.user)
        setStats(data.stats)
      } catch (error) {
        console.error("Failed to fetch user", error)
      }
    }
    fetchUser()
  }, [userId])

  useEffect(() => {
    const fetchThreads = async () => {
      try {
        const data = await adminService.getUserThreads(
          userId,
          pagination.pageIndex + 1,
          pagination.pageSize,
          search
        )
        setThreads(data.items)
        setPageCount(data.pages)
      } catch (error) {
        console.error("Failed to fetch user threads", error)
      } finally {
        setLoading(false)
      }
    }
    fetchThreads()
  }, [userId, pagination, search])

  if (loading && !user) return <div className="p-8">Loading...</div>
  if (!user) return <div className="p-8">User not found</div>

  return (
    <div className="flex flex-col h-full w-full">
      <AdminPageHeader>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <CustomBreadcrumb
              items={[
                { label: "Users", href: "/admin/users" },
                { label: user.full_name || user.email, active: true },
              ]}
            />
          </div>
        </div>
      </AdminPageHeader>

      <div className="flex-1 overflow-auto p-6 space-y-8" data-admin-page-scroll>
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-sm text-muted-foreground">Name</dt>
            <dd className="mt-1 text-sm font-medium">{user.full_name || "—"}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Email</dt>
            <dd className="mt-1 text-sm font-medium">{user.email}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Role</dt>
            <dd className="mt-1 text-sm font-medium capitalize">{user.role || "user"}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Token Usage</dt>
            <dd className="mt-1 text-sm font-medium">{stats?.tokens_used_this_month?.toLocaleString() || 0}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Created</dt>
            <dd className="mt-1 text-sm font-medium">
              {user.created_at ? new Date(user.created_at).toLocaleDateString() : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Threads</dt>
            <dd className="mt-1 text-sm font-medium">{stats?.threads_count || 0}</dd>
          </div>
        </dl>

        <div>
          <ThreadsTable
            data={threads}
            pageCount={pageCount}
            pagination={pagination}
            onPaginationChange={setPagination}
            onSearchChange={setSearch}
            basePath={`/admin/users/${userId}/threads`}
          />
        </div>
      </div>
    </div>
  )
}
