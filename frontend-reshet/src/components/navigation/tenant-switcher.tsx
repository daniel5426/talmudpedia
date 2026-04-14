"use client"

import * as React from "react"
import { ChevronsUpDown, Building2, FolderKanban, Landmark } from "lucide-react"
import { useTenant } from "@/contexts/TenantContext"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import { Skeleton } from "@/components/ui/skeleton"

export function TenantSwitcher() {
  const { isMobile } = useSidebar()
  const {
    currentTenant,
    currentProject,
    tenants,
    projects,
    isLoading,
    setCurrentTenant,
    setCurrentProject,
  } = useTenant()

  if (isLoading) {
    return (
      <div className="p-2">
        <Skeleton className="h-10 w-full" />
      </div>
    )
  }

  if (tenants.length === 0) return null

  const currentProjectLabel = currentProject?.name || "No project selected"

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size="lg"
              className="data-[state=open]:bg-sidebar-accent focus-visible:ring-0 data-[state=open]:text-sidebar-accent-foreground"
            >
              <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                <Landmark className="size-4" />
              </div>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-semibold">
                  {currentTenant?.name || "Select Organization"}
                </span>
                <span className="truncate text-xs text-muted-foreground">
                  {currentProjectLabel}
                </span>
              </div>
              <ChevronsUpDown className="ml-auto size-4 opacity-50" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg"
            align="start"
            side={isMobile ? "bottom" : "right"}
            sideOffset={4}
          >
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              Organizations
            </DropdownMenuLabel>
            {tenants.map((tenant) => (
              <DropdownMenuItem
                key={tenant.id}
                onClick={() => setCurrentTenant(tenant)}
                className="gap-2 p-2 cursor-pointer"
              >
                <div className="flex size-6 items-center justify-center rounded-sm border">
                  <Building2 className="size-4 shrink-0" />
                </div>
                <span className="flex-1">{tenant.name}</span>
                {tenant.slug === currentTenant?.slug ? (
                  <span className="text-[10px] uppercase opacity-60">Active</span>
                ) : null}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              Projects
            </DropdownMenuLabel>
            {projects.length === 0 ? (
              <div className="p-2 text-xs text-muted-foreground">No projects found</div>
            ) : (
              projects.map((project) => (
                <DropdownMenuItem
                  key={project.id}
                  onClick={() => setCurrentProject(project)}
                  className="gap-2 p-2 cursor-pointer"
                >
                  <div className="flex size-6 items-center justify-center rounded-sm border">
                    {project.is_default ? <Landmark className="size-4 shrink-0" /> : <FolderKanban className="size-4 shrink-0" />}
                  </div>
                  <span className="flex-1">{project.name}</span>
                  {project.slug === currentProject?.slug ? (
                    <span className="text-[10px] uppercase opacity-60">Active</span>
                  ) : null}
                </DropdownMenuItem>
              ))
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
