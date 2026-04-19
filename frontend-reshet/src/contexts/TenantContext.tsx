"use client"

import React, { createContext, useContext, useMemo, useState } from "react"

import { applyAuthSession, clearAuthSession } from "@/lib/auth-session"
import { useAuthStore } from "@/lib/store/useAuthStore"
import { authService } from "@/services/auth"
import { HttpRequestError } from "@/services/http"

export interface Tenant {
  id: string
  name: string
  slug: string
  status: string
  created_at: string
}

export interface Project {
  id: string
  organization_id: string
  name: string
  slug: string
  description?: string | null
  status: string
  is_default: boolean
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
  currentProject: Project | null
  currentOrgUnit: OrgUnit | null
  tenants: Tenant[]
  projects: Project[]
  permissions: UserPermissions | null
  isLoading: boolean
  setCurrentTenant: (tenant: Tenant | null) => void
  setCurrentProject: (project: Project | null) => void
  setCurrentOrgUnit: (orgUnit: OrgUnit | null) => void
  refreshTenants: () => Promise<void>
  refreshPermissions: () => Promise<void>
  hasPermission: (resourceType: string, action: string) => boolean
}

const TenantContext = createContext<TenantContextType | undefined>(undefined)

function toTenant(input: {
  id: string
  name: string
  slug: string
  status: string
}): Tenant {
  return {
    ...input,
    created_at: "",
  }
}

function toProject(input: {
  id: string
  organization_id: string
  name: string
  slug: string
  description?: string | null
  status: string
  is_default: boolean
}): Project {
  return { ...input }
}

async function refreshSessionState(): Promise<void> {
  try {
    const session = await authService.getCurrentSession()
    applyAuthSession(session)
  } catch (error) {
    if (error instanceof HttpRequestError && error.status === 401) {
      clearAuthSession()
      return
    }
    throw error
  }
}

export function TenantProvider({ children }: { children: React.ReactNode }) {
  const [currentOrgUnit, setCurrentOrgUnit] = useState<OrgUnit | null>(null)

  const activeOrganization = useAuthStore((state) => state.activeOrganization)
  const activeProject = useAuthStore((state) => state.activeProject)
  const organizations = useAuthStore((state) => state.organizations)
  const projects = useAuthStore((state) => state.projects)
  const effectiveScopes = useAuthStore((state) => state.effectiveScopes)
  const hydrated = useAuthStore((state) => state.hydrated)
  const sessionChecked = useAuthStore((state) => state.sessionChecked)

  const currentTenant = activeOrganization ? toTenant(activeOrganization) : null
  const currentProject = activeProject ? toProject(activeProject) : null
  const tenants = organizations.map(toTenant)
  const projectList = projects.map(toProject)

  const permissions = useMemo<UserPermissions | null>(() => {
    if (!effectiveScopes.length) {
      return null
    }
    return {
      permissions: effectiveScopes,
      scopes: [],
    }
  }, [effectiveScopes])

  const setCurrentTenant = (tenant: Tenant | null) => {
    if (!tenant || tenant.slug === currentTenant?.slug) {
      return
    }
    void authService
      .switchOrganization(tenant.slug, window.location.href)
      .then((result) => {
        if ("redirect_url" in result) {
          window.location.assign(result.redirect_url)
          return
        }
        setCurrentOrgUnit(null)
        applyAuthSession(result)
      })
      .catch((error) => {
        console.error("Failed to switch organization", error)
      })
  }

  const setCurrentProject = (project: Project | null) => {
    if (!project || project.slug === currentProject?.slug) {
      return
    }
    void authService
      .switchProject(project.slug)
      .then((session) => {
        applyAuthSession(session)
      })
      .catch((error) => {
        console.error("Failed to switch project", error)
      })
  }

  const refreshTenants = async () => {
    await refreshSessionState()
  }

  const refreshPermissions = async () => {
    await refreshSessionState()
  }

  const hasPermission = (resourceType: string, action: string): boolean => {
    const granted = new Set(effectiveScopes)
    if (granted.has("*")) {
      return true
    }
    return granted.has(resolveRequestedScope(resourceType, action))
  }

  return (
    <TenantContext.Provider
      value={{
        currentTenant,
        currentProject,
        currentOrgUnit,
        tenants,
        projects: projectList,
        permissions,
        isLoading: !hydrated || !sessionChecked,
        setCurrentTenant,
        setCurrentProject,
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
  "tenant.read": "organizations.read",
  "tenant.write": "organizations.write",
  "tenant.admin": "organizations.write",
  "org_unit.read": "organization_units.read",
  "org_unit.write": "organization_units.write",
  "org_unit.delete": "organization_units.delete",
  "role.read": "roles.read",
  "role.write": "roles.write",
  "role.delete": "roles.write",
  "role.admin": "roles.assign",
  "membership.read": "organization_members.read",
  "membership.write": "organization_members.write",
  "membership.delete": "organization_members.delete",
  "audit.read": "audit.read",
}

function resolveRequestedScope(resourceType: string, action: string): string {
  const key = `${resourceType}.${action}`.toLowerCase()
  return LEGACY_PERMISSION_TO_SCOPE[key] || key
}
