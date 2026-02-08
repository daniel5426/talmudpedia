"use client"

import { ChatsTable } from "@/components/admin/chats-table"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"

export default function AdminChatsPage() {
  return (
    <div className="flex flex-col h-full w-full">
      <header className="h-12 flex items-center justify-between px-4 bg-background z-30 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <CustomBreadcrumb
              items={[
                { label: "Chats", href: "/admin/chats", active: true },
              ]}
            />
          </div>
        </div>
      </header>
      <div className="flex-1 overflow-auto p-4">
        <ChatsTable />
      </div>
    </div>
  )
}
