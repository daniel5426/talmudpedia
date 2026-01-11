"use client"

import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/app-sidebar"
import { useDirection } from "@/components/direction-provider"

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { direction } = useDirection()
  
  return (
    <SidebarProvider className="h-full" dir={direction}>
      <AppSidebar />
      <SidebarInset className="h-full">
        <div className="flex h-full w-full overflow-hidden bg-background">
           {children}
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
