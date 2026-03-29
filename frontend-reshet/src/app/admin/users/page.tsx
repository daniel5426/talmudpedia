"use client"

import { UsersTable } from "@/components/admin/users-table"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"

export default function AdminUsersPage() {
  return (
    <div className="flex flex-col h-full w-full">
      <AdminPageHeader>
        <CustomBreadcrumb
          items={[
            { label: "Users", href: "/admin/users", active: true },
          ]}
        />
      </AdminPageHeader>
      <div className="flex-1 overflow-auto px-4 pb-4 pt-3" data-admin-page-scroll>
        <UsersTable />
      </div>
    </div>
  )
}
