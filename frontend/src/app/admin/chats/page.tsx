"use client"

import { ChatsTable } from "@/components/admin/chats-table"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"

export default function AdminChatsPage() {
  return (
    <div className="flex flex-col h-full w-full">
      <div className="p-4 border-b shrink-0">
        <CustomBreadcrumb
          items={[
            { label: "Chats", href: "/admin/chats", active: true },
          ]}
        />
      </div>
      <div className="flex-1 overflow-auto p-4">
        <ChatsTable />
      </div>
    </div>
  )
}
