"use client"

import { useEffect, useMemo, useState } from "react"
import { adminService, User } from "@/services"
import { useTenant } from "@/contexts/TenantContext"
import { rbacService, Role, RoleAssignment } from "@/services/rbac"
import { DataTable } from "@/components/ui/data-table"
import { ColumnDef, type PaginationState } from "@tanstack/react-table"
import { Button } from "@/components/ui/button"
import { MoreHorizontal, Edit, Shield, Trash2 } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { format } from "date-fns"
import Link from "next/link"

interface UsersTableProps {
  data?: User[]
  pageCount?: number
  pagination?: PaginationState
  onPaginationChange?: (pagination: PaginationState) => void
  search?: string
  onSearchChange?: (search: string) => void
}

const ALL_TYPES_VALUE = "__all_actor_types__"

function actorTypeLabel(user: User) {
  switch (user.actor_type) {
    case "platform_user":
      return "Platform"
    case "published_app_account":
      return "App Account"
    case "embedded_external_user":
      return "Embed"
    default:
      return "Unknown"
  }
}

export function UsersTable({
  data: externalData,
  pageCount: externalPageCount,
  pagination: externalPagination,
  onPaginationChange,
  search: externalSearch,
  onSearchChange,
}: UsersTableProps) {
  const { currentTenant } = useTenant()
  const [internalUsers, setInternalUsers] = useState<User[]>([])
  const [roles, setRoles] = useState<Role[]>([])
  const [assignments, setAssignments] = useState<RoleAssignment[]>([])
  const [loading, setLoading] = useState(true)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [editName, setEditName] = useState("")
  const [managingUser, setManagingUser] = useState<User | null>(null)
  const [selectedRoleId, setSelectedRoleId] = useState("")
  const [isEditOpen, setIsEditOpen] = useState(false)
  const [isRolesOpen, setIsRolesOpen] = useState(false)
  const [actorType, setActorType] = useState("")
  const [internalSearch, setInternalSearch] = useState("")
  const [internalPagination, setInternalPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 20,
  })
  const [internalPageCount, setInternalPageCount] = useState(0)

  const users = externalData || internalUsers
  const search = externalSearch ?? internalSearch
  const pagination = externalPagination ?? internalPagination
  const pageCount = externalPageCount ?? internalPageCount
  const setPagination = onPaginationChange ?? setInternalPagination
  const setSearch = onSearchChange ?? setInternalSearch

  const fetchUsers = async () => {
    if (externalData) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const data = await adminService.getUsers(
        pagination.pageIndex + 1,
        pagination.pageSize,
        search,
        { actorType: actorType || undefined },
      )
      setInternalUsers(data.items)
      setInternalPageCount(data.pages)
    } catch (error) {
      console.error("Failed to fetch users", error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchUsers()
  }, [externalData, pagination.pageIndex, pagination.pageSize, search, actorType])

  const fetchSecurityData = async () => {
    if (!currentTenant) return
    try {
      const [rolesData, assignmentsData] = await Promise.all([
        rbacService.listRoles(currentTenant.slug),
        rbacService.listRoleAssignments(currentTenant.slug),
      ])
      setRoles(rolesData)
      setAssignments(assignmentsData)
    } catch (error) {
      console.error("Failed to fetch RBAC data", error)
    }
  }

  useEffect(() => {
    fetchSecurityData()
  }, [currentTenant])

  const handleEditClick = (user: User) => {
    setEditingUser(user)
    setEditName(user.display_name || user.full_name || "")
    setIsEditOpen(true)
  }

  const handleManageRolesClick = (user: User) => {
    setManagingUser(user)
    setSelectedRoleId("")
    setIsRolesOpen(true)
  }

  const handleSaveEdit = async () => {
    if (!editingUser) return
    try {
      await adminService.updateUser(editingUser.platform_user_id || editingUser.id, { full_name: editName })
      setIsEditOpen(false)
      setEditingUser(null)
      await fetchUsers()
    } catch (error) {
      console.error("Failed to update user", error)
      alert("Failed to update user")
    }
  }

  const userAssignments = (user: User) => {
    const targetId = user.platform_user_id || user.id
    return assignments.filter((assignment) => assignment.user_id === targetId)
  }

  const handleAssignRole = async () => {
    if (!currentTenant || !managingUser || !selectedRoleId) return
    try {
      await rbacService.createRoleAssignment(currentTenant.slug, {
        user_id: managingUser.platform_user_id || managingUser.id,
        role_id: selectedRoleId,
        scope_id: currentTenant.id,
        scope_type: "tenant",
        actor_type: "user",
      })
      setSelectedRoleId("")
      await fetchSecurityData()
    } catch (error) {
      console.error("Failed to assign role", error)
      alert("Failed to assign role")
    }
  }

  const handleRevokeRole = async (assignmentId: string) => {
    if (!currentTenant) return
    try {
      await rbacService.deleteRoleAssignment(currentTenant.slug, assignmentId)
      await fetchSecurityData()
    } catch (error) {
      console.error("Failed to revoke role", error)
      alert("Failed to revoke role")
    }
  }

  const columns: ColumnDef<User>[] = useMemo(() => [
    {
      accessorKey: "display_name",
      header: "User",
      cell: ({ row }) => {
        const user = row.original
        return (
          <div className="min-w-0">
            <Link href={`/admin/users/${user.actor_id || user.id}`} className="hover:underline font-medium">
              {user.display_name || user.full_name || user.email || user.id}
            </Link>
            <div className="text-xs text-muted-foreground truncate">{user.email || "No email"}</div>
          </div>
        )
      },
    },
    {
      accessorKey: "actor_type",
      header: "Type",
      cell: ({ row }) => actorTypeLabel(row.original),
    },
    {
      accessorKey: "source_app_count",
      header: "Sources",
      cell: ({ row }) => row.original.source_app_count ?? 0,
    },
    {
      accessorKey: "threads_count",
      header: "Threads",
      cell: ({ row }) => row.original.threads_count ?? 0,
    },
    {
      accessorKey: "role",
      header: "Roles",
      cell: ({ row }) => {
        const user = row.original
        if (!user.is_manageable) return <span className="text-muted-foreground">Read only</span>
        const names = userAssignments(user).map((assignment) => assignment.role_name)
        return names.length > 0 ? names.join(", ") : user.role || "user"
      },
    },
    {
      accessorKey: "last_activity_at",
      header: "Last Activity",
      cell: ({ row }) => {
        const value = row.original.last_activity_at
        return value ? format(new Date(value), "MMM d, yyyy HH:mm") : "—"
      },
    },
    {
      id: "actions",
      cell: ({ row }) => {
        const user = row.original
        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="h-8 w-8 p-0">
                <span className="sr-only">Open menu</span>
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Actions</DropdownMenuLabel>
              <DropdownMenuItem onClick={() => navigator.clipboard.writeText(user.actor_id || user.id)}>
                Copy ID
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link href={`/admin/users/${user.actor_id || user.id}`}>
                  View Details
                </Link>
              </DropdownMenuItem>
              {user.is_manageable ? (
                <>
                  <DropdownMenuItem onClick={() => handleEditClick(user)}>
                    <Edit className="mr-2 h-4 w-4" /> Edit
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleManageRolesClick(user)}>
                    <Shield className="mr-2 h-4 w-4" /> Manage Roles
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    className="text-red-600"
                    onClick={async () => {
                      if (confirm("Are you sure?")) {
                        await adminService.bulkDeleteUsers([user.platform_user_id || user.id])
                        await fetchUsers()
                      }
                    }}
                  >
                    <Trash2 className="mr-2 h-4 w-4" /> Delete
                  </DropdownMenuItem>
                </>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        )
      },
    },
  ], [assignments, roles])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={actorType || ALL_TYPES_VALUE}
          onValueChange={(value) => {
            setActorType(value === ALL_TYPES_VALUE ? "" : value)
            setPagination({ pageIndex: 0, pageSize: pagination.pageSize })
          }}
        >
          <SelectTrigger className="w-[220px]">
            <SelectValue placeholder="All actor types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_TYPES_VALUE}>All actor types</SelectItem>
            <SelectItem value="platform_user">Platform users</SelectItem>
            <SelectItem value="published_app_account">App accounts</SelectItem>
            <SelectItem value="embedded_external_user">Embedded users</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <DataTable
        columns={columns}
        data={users}
        filterColumn="display_name"
        filterPlaceholder="Search users..."
        isLoading={loading}
        manualPagination
        pageCount={pageCount}
        pagination={pagination}
        onPaginationChange={setPagination}
        filterValue={search}
        onFilterChange={(value) => {
          setSearch(value)
          setPagination({ pageIndex: 0, pageSize: pagination.pageSize })
        }}
      />

      <Dialog open={isEditOpen} onOpenChange={setIsEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit User</DialogTitle>
            <DialogDescription>Update the profile name for this platform user.</DialogDescription>
          </DialogHeader>
          <Input value={editName} onChange={(event) => setEditName(event.target.value)} placeholder="Display name" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditOpen(false)}>Cancel</Button>
            <Button onClick={handleSaveEdit}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={isRolesOpen} onOpenChange={setIsRolesOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Manage Roles</DialogTitle>
            <DialogDescription>Assign tenant-scoped roles for this platform user.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Select value={selectedRoleId} onValueChange={setSelectedRoleId}>
              <SelectTrigger>
                <SelectValue placeholder="Select role" />
              </SelectTrigger>
              <SelectContent>
                {roles.map((role) => (
                  <SelectItem key={role.id} value={role.id}>
                    {role.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="space-y-2">
              {managingUser ? userAssignments(managingUser).map((assignment) => (
                <div key={assignment.id} className="flex items-center justify-between rounded border px-3 py-2">
                  <span>{assignment.role_name}</span>
                  <Button variant="ghost" size="sm" onClick={() => handleRevokeRole(assignment.id)}>
                    Remove
                  </Button>
                </div>
              )) : null}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsRolesOpen(false)}>Close</Button>
            <Button onClick={handleAssignRole}>Assign Role</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
