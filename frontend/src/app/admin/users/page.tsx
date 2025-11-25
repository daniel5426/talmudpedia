"use client"

import { UsersTable } from "@/components/admin/users-table"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"

export default function AdminUsersPage() {
  return (
    <div className="flex flex-col h-full w-full">
      <div className="p-4 border-b shrink-0">
        <CustomBreadcrumb
          items={[
            { label: "Users", href: "/admin/users", active: true },
          ]}
        />
      </div>
      <div className="flex-1 overflow-auto p-4">
        <UsersTable />
      </div>
    </div>
  )
}
