"use client"

import { useTenant } from "@/contexts/TenantContext"

export function usePermission(resourceType: string, action: string): boolean {
  const { hasPermission } = useTenant()
  return hasPermission(resourceType, action)
}

export function usePermissions() {
  const { permissions, hasPermission } = useTenant()
  
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
