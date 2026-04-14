"use client"

import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/navigation/app-sidebar"
import { useDirection } from "@/components/direction-provider"
import { useAuthStore } from "@/lib/store/useAuthStore"
import { usePathname, useRouter } from "next/navigation"
import { useEffect, useState } from "react"

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { direction } = useDirection()
  const user = useAuthStore((state) => state.user)
  const hydrated = useAuthStore((state) => state.hydrated)
  const sessionChecked = useAuthStore((state) => state.sessionChecked)
  const effectiveScopes = useAuthStore((state) => state.effectiveScopes)
  const router = useRouter()
  const pathname = usePathname()
  const [isAuthorized, setIsAuthorized] = useState(false)

  useEffect(() => {
    if (!hydrated || !sessionChecked) {
      return
    }

    if (!user) {
      router.replace("/auth/login")
      return
    }

    const hasAccess =
      effectiveScopes.length > 0 ||
      user.role === "admin" ||
      user.role === "system_admin" ||
      user.role === "system"

    if (!hasAccess) {
      router.replace("/")
      return
    }

    setIsAuthorized(true)
  }, [effectiveScopes.length, hydrated, router, sessionChecked, user])

  if (!isAuthorized) {
    return null
  }

  const isAppsBuilderRoute =
    !!pathname &&
    pathname.startsWith("/admin/apps/") &&
    pathname !== "/admin/apps";

  if (isAppsBuilderRoute) {
    return (
      <SidebarProvider className="h-dvh min-h-0" dir={direction}>
        <div className="flex h-full min-h-0 w-full min-w-0 overflow-hidden bg-background">
          {children}
        </div>
      </SidebarProvider>
    )
  }

  return (
    <SidebarProvider className="h-full" dir={direction}>
      <AppSidebar  />
      <SidebarInset className="h-full overflow-hidden">
        <div className="flex h-full w-full min-w-0 overflow-hidden bg-background">
          {children}
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
