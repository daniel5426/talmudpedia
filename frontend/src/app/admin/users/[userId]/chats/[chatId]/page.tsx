"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { api, User, ChatHistory } from "@/lib/api"
import { AdminChatView } from "@/components/admin/admin-chat-view"

export default function AdminUserChatPage() {
  const params = useParams()
  const userId = params.userId as string
  const chatId = params.chatId as string
  const [user, setUser] = useState<User | null>(null)
  const [chat, setChat] = useState<ChatHistory | null>(null)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [userData, chatData] = await Promise.all([
          api.getAdminUserDetails(userId),
          api.getChatHistory(chatId)
        ])
        setUser(userData.user)
        setChat(chatData)
      } catch (error) {
        console.error("Failed to fetch data", error)
      }
    }
    fetchData()
  }, [userId, chatId])

  const chatDate = chat?.created_at ? new Date(chat.created_at).toLocaleDateString() : (chat?.title || chatId)
  
  return (
    <AdminChatView
      chatId={chatId}
      breadcrumbs={[
        { label: "Users", href: "/admin/users" },
        { label: user?.full_name || user?.email || "User", href: `/admin/users/${userId}` },
        { label: chatDate, active: true },
      ]}
    />
  )
}
