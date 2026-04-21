"use client"

import { useOrganization } from "@/contexts/OrganizationContext"

export function usePermission(resourceType: string, action: string): boolean {
  const { hasPermission } = useOrganization()
  return hasPermission(resourceType, action)
}

export function usePermissions() {
  const { permissions, hasPermission } = useOrganization()
  
  return {
    permissions,
    hasPermission,
    canRead: (resourceType: string) => hasPermission(resourceType, "read"),
    canWrite: (resourceType: string) => hasPermission(resourceType, "write"),
    canDelete: (resourceType: string) => hasPermission(resourceType, "delete"),
    canExecute: (resourceType: string) => hasPermission(resourceType, "execute"),
    canAdmin: (resourceType: string) => hasPermission(resourceType, "admin"),
  }
}
