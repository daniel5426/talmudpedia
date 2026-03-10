"use client"

import { ThreadsTable } from "@/components/admin/threads-table"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"

export default function AdminThreadsPage() {
  return (
    <div className="flex flex-col h-full w-full">
      <AdminPageHeader>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <CustomBreadcrumb
              items={[
                { label: "Threads", href: "/admin/threads", active: true },
              ]}
            />
          </div>
        </div>
      </AdminPageHeader>
      <div className="flex-1 overflow-auto p-4" data-admin-page-scroll>
        <ThreadsTable />
      </div>
    </div>
  )
}
