"use client"

import * as React from "react"
import { ChevronsUpDown, Building2, Landmark, Users } from "lucide-react"
import { useTenant, Tenant, OrgUnit } from "@/contexts/TenantContext"
import { orgUnitsService } from "@/services/org-units"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
  DropdownMenuPortal,
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
    currentOrgUnit, 
    tenants, 
    isLoading,
    setCurrentTenant, 
    setCurrentOrgUnit 
  } = useTenant()
  
  const [orgUnits, setOrgUnits] = React.useState<OrgUnit[]>([])
  const [isUnitsLoading, setIsUnitsLoading] = React.useState(false)

  React.useEffect(() => {
    if (currentTenant) {
      setIsUnitsLoading(true)
      orgUnitsService.listOrgUnits(currentTenant.slug)
        .then(setOrgUnits)
        .catch(console.error)
        .finally(() => setIsUnitsLoading(false))
    }
  }, [currentTenant])

  if (isLoading) {
    return (
      <div className="p-2">
        <Skeleton className="h-10 w-full" />
      </div>
    )
  }

  if (tenants.length === 0) return null

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size="lg"
              className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
            >
              <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                <Landmark className="size-4" />
              </div>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-semibold">
                  {currentTenant?.name || "Select Tenant"}
                </span>
                <span className="truncate text-xs text-muted-foreground">
                  {currentOrgUnit?.name || "No Org Unit selected"}
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
              Available Tenants
            </DropdownMenuLabel>
            {tenants.map((tenant) => (
              <DropdownMenuSub key={tenant.id}>
                <DropdownMenuSubTrigger
                  onClick={() => setCurrentTenant(tenant)}
                  className="gap-2 p-2 cursor-pointer"
                >
                  <div className="flex size-6 items-center justify-center rounded-sm border">
                    <Building2 className="size-4 shrink-0" />
                  </div>
                  <span className="flex-1">{tenant.name}</span>
                </DropdownMenuSubTrigger>
                <DropdownMenuPortal>
                  <DropdownMenuSubContent className="min-w-48">
                    <DropdownMenuLabel className="text-xs">Org Units</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    {isUnitsLoading ? (
                      <div className="p-2 space-y-1">
                        <Skeleton className="h-8 w-full" />
                        <Skeleton className="h-8 w-full" />
                      </div>
                    ) : orgUnits.length === 0 ? (
                      <div className="p-2 text-xs text-muted-foreground">No units found</div>
                    ) : (
                      orgUnits.map((unit) => (
                        <DropdownMenuItem
                          key={unit.id}
                          onClick={() => {
                            setCurrentTenant(tenant)
                            setCurrentOrgUnit(unit)
                          }}
                          className="gap-2 p-2 cursor-pointer"
                        >
                          <div className="flex size-4 items-center justify-center">
                            {unit.type === "org" && <Landmark className="size-3" />}
                            {unit.type === "dept" && <Building2 className="size-3" />}
                            {unit.type === "team" && <Users className="size-3" />}
                          </div>
                          <span>{unit.name}</span>
                          <span className="ml-auto text-[10px] uppercase opacity-50">
                            {unit.type}
                          </span>
                        </DropdownMenuItem>
                      ))
                    )}
                  </DropdownMenuSubContent>
                </DropdownMenuPortal>
              </DropdownMenuSub>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
