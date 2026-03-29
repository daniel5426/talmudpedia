"use client"

import { ThreadsTable } from "@/components/admin/threads-table"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"

export default function AdminThreadsPage() {
  return (
    <div className="flex flex-col h-full w-full">
      <AdminPageHeader>
        <CustomBreadcrumb
          items={[
            { label: "Threads", href: "/admin/threads", active: true },
          ]}
        />
      </AdminPageHeader>
      <div className="flex-1 overflow-auto px-4 pb-4 pt-3" data-admin-page-scroll>
        <ThreadsTable />
      </div>
    </div>
  )
}
