"use client"

import { useParams } from "next/navigation"
import { AdminChatView } from "@/components/admin/admin-chat-view"

export default function AdminChatPage() {
  const params = useParams()
  const chatId = params.chatId as string

  return (
    <AdminChatView
      chatId={chatId}
      breadcrumbs={[
        { label: "Chats", href: "/admin/chats" },
        { label: chatId, active: true },
      ]}
    />
  )
}
