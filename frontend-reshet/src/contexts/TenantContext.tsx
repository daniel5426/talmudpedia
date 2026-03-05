"use client"

import React, { createContext, useContext, useState, useEffect, useCallback } from "react"
import { httpClient } from "@/services/http"
import { useAuthStore } from "@/lib/store/useAuthStore"

export interface Tenant {
  id: string
  name: string
  slug: string
  status: string
  created_at: string
}

export interface OrgUnit {
  id: string
  tenant_id: string
  parent_id: string | null
  name: string
  slug: string
  type: "org" | "dept" | "team"
  created_at: string
}

export interface RoleScope {
  scope_id: string
  scope_type: string
  role_name: string
  permissions: string[]
}

export interface UserPermissions {
  permissions: string[]
  scopes: RoleScope[]
}

interface TenantContextType {
  currentTenant: Tenant | null
  currentOrgUnit: OrgUnit | null
  tenants: Tenant[]
  permissions: UserPermissions | null
  isLoading: boolean
  setCurrentTenant: (tenant: Tenant | null) => void
  setCurrentOrgUnit: (orgUnit: OrgUnit | null) => void
  refreshTenants: () => Promise<void>
  refreshPermissions: () => Promise<void>
  hasPermission: (resourceType: string, action: string) => boolean
}

const TenantContext = createContext<TenantContextType | undefined>(undefined)

export function TenantProvider({ children }: { children: React.ReactNode }) {
  const [currentTenant, setCurrentTenant] = useState<Tenant | null>(null)
  const [currentOrgUnit, setCurrentOrgUnit] = useState<OrgUnit | null>(null)
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [permissions, setPermissions] = useState<UserPermissions | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  
  const user = useAuthStore((state) => state.user)
  const token = useAuthStore((state) => state.token)

  const refreshTenants = useCallback(async () => {
    if (!token) {
      setTenants([])
      return
    }
    
    try {
      const data = await httpClient.get<Tenant[]>("/api/tenants")
      setTenants(data)
      
      if (data.length > 0 && !currentTenant) {
        const savedSlug = localStorage.getItem("currentTenantSlug")
        const savedTenant = data.find((t: Tenant) => t.slug === savedSlug) || data[0]
        setCurrentTenant(savedTenant)
      }
    } catch (error) {
      console.error("Failed to fetch tenants:", error)
    }
  }, [token, currentTenant])

  const refreshPermissions = useCallback(async () => {
    if (!currentTenant || !user || !token) {
      setPermissions(null)
      return
    }

    try {
      const data = await httpClient.get<UserPermissions>(
        `/api/tenants/${currentTenant.slug}/users/${user.id}/permissions`
      )
      setPermissions(data)
    } catch (error) {
      console.error("Failed to fetch permissions:", error)
    }
  }, [currentTenant, user, token])

  const hasPermission = useCallback(
    (resourceType: string, action: string): boolean => {
      if (user?.role === "admin" || user?.role === "system_admin" || user?.role === "system") return true
      if (!permissions) return false
      const wanted = resolveRequestedScope(resourceType, action)
      return permissions.permissions.includes(wanted)
    },
    [permissions, user]
  )

  useEffect(() => {
    const loadTenants = async () => {
      if (!token) {
        setTenants([])
        setCurrentTenant(null)
        setCurrentOrgUnit(null)
        setPermissions(null)
        setIsLoading(false)
        return
      }

      setIsLoading(true)
      try {
        const data = await httpClient.get<Tenant[]>("/api/tenants")
        setTenants(data)

        if (data.length > 0 && !currentTenant) {
          const savedSlug = localStorage.getItem("currentTenantSlug")
          const savedTenant = data.find((t: Tenant) => t.slug === savedSlug) || data[0]
          setCurrentTenant(savedTenant)
        }
      } catch (error) {
        console.error("Failed to fetch tenants:", error)
      } finally {
        setIsLoading(false)
      }
    }

    loadTenants()
  }, [token, currentTenant])

  const currentTenantRef = React.useRef<string | null>(null)

  useEffect(() => {
    const loadPermissions = async () => {
      if (!currentTenant || !user || !token || currentTenant.id === currentTenantRef.current) {
        return
      }

      localStorage.setItem("currentTenantSlug", currentTenant.slug)
      currentTenantRef.current = currentTenant.id

      try {
        const data = await httpClient.get<UserPermissions>(
          `/api/tenants/${currentTenant.slug}/users/${user.id}/permissions`
        )
        setPermissions(data)
      } catch (error) {
        console.error("Failed to fetch permissions:", error)
      }
    }

    loadPermissions()
  }, [currentTenant, user, token])

  return (
    <TenantContext.Provider
      value={{
        currentTenant,
        currentOrgUnit,
        tenants,
        permissions,
        isLoading,
        setCurrentTenant,
        setCurrentOrgUnit,
        refreshTenants,
        refreshPermissions,
        hasPermission,
      }}
    >
      {children}
    </TenantContext.Provider>
  )
}

export function useTenant() {
  const context = useContext(TenantContext)
  if (context === undefined) {
    throw new Error("useTenant must be used within a TenantProvider")
  }
  return context
}
const LEGACY_PERMISSION_TO_SCOPE: Record<string, string> = {
  "index.read": "pipelines.catalog.read",
  "index.write": "pipelines.write",
  "index.delete": "pipelines.delete",
  "pipeline.read": "pipelines.read",
  "pipeline.write": "pipelines.write",
  "pipeline.delete": "pipelines.delete",
  "job.read": "pipelines.read",
  "job.write": "pipelines.write",
  "job.delete": "pipelines.delete",
  "tenant.read": "tenants.read",
  "tenant.write": "tenants.write",
  "tenant.admin": "tenants.write",
  "org_unit.read": "membership.read",
  "org_unit.write": "membership.write",
  "org_unit.delete": "membership.delete",
  "role.read": "roles.read",
  "role.write": "roles.write",
  "role.delete": "roles.write",
  "role.admin": "roles.assign",
  "membership.read": "membership.read",
  "membership.write": "membership.write",
  "membership.delete": "membership.delete",
  "audit.read": "audit.read",
}

function resolveRequestedScope(resourceType: string, action: string): string {
  const key = `${resourceType}.${action}`.toLowerCase()
  return LEGACY_PERMISSION_TO_SCOPE[key] || key
}
