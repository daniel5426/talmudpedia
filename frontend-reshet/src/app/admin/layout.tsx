"use client"

import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/navigation/app-sidebar"
import { useDirection } from "@/components/direction-provider"
import { useAuthStore } from "@/lib/store/useAuthStore"
import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { direction } = useDirection()
  const { user, isAuthenticated } = useAuthStore()
  const router = useRouter()
  const [isAuthorized, setIsAuthorized] = useState(false)

  const [isHydrated, setIsHydrated] = useState(false)

  useEffect(() => {
    // Handle hydration state safely
    const checkHydration = () => {
      if (useAuthStore.persist.hasHydrated()) {
        setIsHydrated(true)
      }
    }

    // Check immediately
    checkHydration()

    // Listen for hydration finish if available
    const unsub = useAuthStore.persist.onFinishHydration?.(() => {
      setIsHydrated(true)
    })

    return () => {
      if (typeof unsub === 'function') unsub()
    }
  }, [])

  useEffect(() => {
    // Don't check auth until hydration is complete
    if (!isHydrated) return;

    if (!isAuthenticated() || !user) {
      console.log("AdminLayout: Redirecting to login", { isAuthenticated: isAuthenticated(), hasUser: !!user })
      router.push("/auth/login")
      return
    }

    const hasAccess =
      user.role === "admin" ||
      user.org_role === "owner" ||
      user.org_role === "admin";

    if (!hasAccess) {
      console.log("AdminLayout: Redirecting to root (No Access)", { role: user.role, org_role: user.org_role })
      router.push("/")
      return
    }

    setIsAuthorized(true)
  }, [user, isAuthenticated, router, isHydrated])

  if (!isAuthorized) {
    return null // Or a loading spinner
  }

  return (
    <SidebarProvider className="h-full" dir={direction}>
      <AppSidebar />
      <SidebarInset className="h-full overflow-hidden">
        <div className="flex h-full w-full min-w-0 overflow-hidden bg-background">
          {children}
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
