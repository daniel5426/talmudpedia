"use client"

import { useEffect, useState } from "react"
import { adminService, User } from "@/services"
import { useTenant } from "@/contexts/TenantContext"
import { rbacService, Role, RoleAssignment } from "@/services/rbac"
import { DataTable } from "@/components/ui/data-table"
import { ColumnDef } from "@tanstack/react-table"
import { Checkbox } from "@/components/ui/checkbox"
import { Button } from "@/components/ui/button"
import { MoreHorizontal, Edit, Trash2 } from "lucide-react"
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
import { Label } from "@/components/ui/label"
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
  pagination?: { pageIndex: number; pageSize: number }
  onPaginationChange?: (pagination: { pageIndex: number; pageSize: number }) => void
  onSearchChange?: (search: string) => void
}

export function UsersTable({
  data: externalData,
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

  const users = externalData || internalUsers

  const fetchUsers = async () => {
    if (externalData) {
        setLoading(false)
        return
    }
    setLoading(true)
    try {
      const data = await adminService.getUsers(1, 1000)
      setInternalUsers(data.items)
    } catch (error) {
      console.error("Failed to fetch users", error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchUsers()
  }, [externalData])

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

  const handleBulkDelete = async (ids: string[]) => {
    try {
      await adminService.bulkDeleteUsers(ids)
      if (!externalData) {
          await fetchUsers()
      } else {
          window.location.reload()
      }
    } catch (error) {
      console.error("Failed to delete users", error)
      alert("Failed to delete users")
    }
  }

  const handleEditClick = (user: User) => {
    setEditingUser(user)
    setEditName(user.full_name || "")
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
      await adminService.updateUser(editingUser.id, { full_name: editName })
      setIsEditOpen(false)
      setEditingUser(null)
      if (!externalData) fetchUsers()
      else window.location.reload()
    } catch (error) {
      console.error("Failed to update user", error)
      alert("Failed to update user")
    }
  }

  const userAssignments = (userId: string) =>
    assignments.filter((assignment) => assignment.user_id === userId)

  const handleAssignRole = async () => {
    if (!currentTenant || !managingUser || !selectedRoleId) return
    try {
      await rbacService.createRoleAssignment(currentTenant.slug, {
        user_id: managingUser.id,
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

  const columns: ColumnDef<User>[] = [
    {
      id: "select",
      header: ({ table }) => (
        <Checkbox
          checked={table.getIsAllPageRowsSelected() || (table.getIsSomePageRowsSelected() && "indeterminate")}
          onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
          aria-label="Select all"
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(value) => row.toggleSelected(!!value)}
          aria-label="Select row"
        />
      ),
      enableSorting: false,
      enableHiding: false,
    },
    {
      accessorKey: "email",
      header: "Email",
      cell: ({ row }) => {
        const user = row.original
        return (
            <Link href={`/admin/users/${user.id}`} className="hover:underline font-medium">
                {user.email}
            </Link>
        )
      }
    },
    {
      accessorKey: "full_name",
      header: "Full Name",
      cell: ({ row }) => {
        const user = row.original
        return (
            <Link href={`/admin/users/${user.id}`} className="hover:underline">
                {user.full_name || "-"}
            </Link>
        )
      }
    },
    {
      accessorKey: "role",
      header: "Roles",
      cell: ({ row }) => {
        const user = row.original
        const names = userAssignments(user.id).map((a) => a.role_name)
        return names.length > 0 ? names.join(", ") : user.role
      },
    },
    {
      accessorKey: "created_at",
      header: "Joined",
      cell: ({ row }) => {
        const date = row.getValue("created_at") as string
        return date ? format(new Date(date), "MMM d, yyyy") : "N/A"
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
              <DropdownMenuItem
                onClick={() => navigator.clipboard.writeText(user.id)}
              >
                Copy ID
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => handleEditClick(user)}>
                <Edit className="mr-2 h-4 w-4" /> Edit
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleManageRolesClick(user)}>
                <Edit className="mr-2 h-4 w-4" /> Manage Roles
              </DropdownMenuItem>
              <DropdownMenuItem 
                className="text-red-600"
                onClick={async () => {
                    if(confirm("Are you sure?")) {
                        await adminService.bulkDeleteUsers([user.id])
                        if (!externalData) fetchUsers()
                        else window.location.reload()
                    }
                }}
              >
                <Trash2 className="mr-2 h-4 w-4" /> Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )
      },
    },
  ]

  return (
    <>
      <DataTable 
          columns={columns} 
          data={users} 
          onBulkDelete={handleBulkDelete}
          filterColumn="email"
          filterPlaceholder="Filter emails..."
          isLoading={loading}
      />
      <Dialog open={isEditOpen} onOpenChange={setIsEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit User</DialogTitle>
            <DialogDescription>
              Make changes to the user&apos;s profile here. Click save when you&apos;re done.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="name" className="text-right">
                Name
              </Label>
              <Input
                id="name"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="col-span-3"
              />
            </div>
          </div>
          <DialogFooter>
            <Button onClick={handleSaveEdit}>Save changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={isRolesOpen} onOpenChange={setIsRolesOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Manage User Roles</DialogTitle>
            <DialogDescription>
              Assign or revoke tenant RBAC roles for this user.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label className="text-right">Assign</Label>
              <div className="col-span-3 flex gap-2">
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
                <Button onClick={handleAssignRole} disabled={!selectedRoleId}>
                  Assign
                </Button>
              </div>
            </div>
            <div className="space-y-2">
              {managingUser && userAssignments(managingUser.id).length > 0 ? (
                userAssignments(managingUser.id).map((assignment) => (
                  <div key={assignment.id} className="flex items-center justify-between rounded border px-3 py-2">
                    <span className="text-sm">{assignment.role_name}</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-red-600 hover:text-red-700"
                      onClick={() => handleRevokeRole(assignment.id)}
                    >
                      Revoke
                    </Button>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">No RBAC role assignments for this user.</p>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
