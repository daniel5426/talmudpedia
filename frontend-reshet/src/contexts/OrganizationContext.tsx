"use client"

import React, { createContext, useContext, useMemo, useState } from "react"

import { applyAuthSession, clearAuthSession } from "@/lib/auth-session"
import { useAuthStore } from "@/lib/store/useAuthStore"
import { authService } from "@/services/auth"
import { HttpRequestError } from "@/services/http"

export interface Organization {
  id: string
  name: string
  status: string
  created_at: string
}

export interface Project {
  id: string
  organization_id: string
  name: string
  description?: string | null
  status: string
  is_default: boolean
}

export interface OrgUnit {
  id: string
  organization_id: string
  parent_id: string | null
  name: string
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

interface OrganizationContextType {
  currentOrganization: Organization | null
  currentProject: Project | null
  currentOrgUnit: OrgUnit | null
  organizations: Organization[]
  projects: Project[]
  permissions: UserPermissions | null
  isLoading: boolean
  setCurrentOrganization: (organization: Organization | null) => void
  setCurrentProject: (project: Project | null) => void
  setCurrentOrgUnit: (orgUnit: OrgUnit | null) => void
  refreshOrganizations: () => Promise<void>
  refreshPermissions: () => Promise<void>
  hasPermission: (resourceType: string, action: string) => boolean
}

const OrganizationContext = createContext<OrganizationContextType | undefined>(undefined)

function toOrganization(input: {
  id: string
  name: string
  status: string
}): Organization {
  return {
    ...input,
    created_at: "",
  }
}

function toProject(input: {
  id: string
  organization_id: string
  name: string
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

export function OrganizationProvider({ children }: { children: React.ReactNode }) {
  const [currentOrgUnit, setCurrentOrgUnit] = useState<OrgUnit | null>(null)

  const activeOrganization = useAuthStore((state) => state.activeOrganization)
  const activeProject = useAuthStore((state) => state.activeProject)
  const organizations = useAuthStore((state) => state.organizations)
  const projects = useAuthStore((state) => state.projects)
  const effectiveScopes = useAuthStore((state) => state.effectiveScopes)
  const hydrated = useAuthStore((state) => state.hydrated)
  const sessionChecked = useAuthStore((state) => state.sessionChecked)

  const currentOrganization = activeOrganization ? toOrganization(activeOrganization) : null
  const currentProject = activeProject ? toProject(activeProject) : null
  const organizationsList = organizations.map(toOrganization)
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

  const setCurrentOrganization = (organization: Organization | null) => {
    if (!organization || organization.id === currentOrganization?.id) {
      return
    }
    void authService
      .switchOrganization(organization.id, window.location.href)
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
    if (!project || project.id === currentProject?.id) {
      return
    }
    void authService
      .switchProject(project.id)
      .then((session) => {
        applyAuthSession(session)
      })
      .catch((error) => {
        console.error("Failed to switch project", error)
      })
  }

  const refreshOrganizations = async () => {
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
    <OrganizationContext.Provider
      value={{
        currentOrganization,
        currentProject,
        currentOrgUnit,
        organizations: organizationsList,
        projects: projectList,
        permissions,
        isLoading: !hydrated || !sessionChecked,
        setCurrentOrganization,
        setCurrentProject,
        setCurrentOrgUnit,
        refreshOrganizations,
        refreshPermissions,
        hasPermission,
      }}
    >
      {children}
    </OrganizationContext.Provider>
  )
}

export function useOrganization() {
  const context = useContext(OrganizationContext)
  if (context === undefined) {
    throw new Error("useOrganization must be used within an OrganizationProvider")
  }
  return context
}

function resolveRequestedScope(resourceType: string, action: string): string {
  return `${resourceType}.${action}`.toLowerCase()
}
