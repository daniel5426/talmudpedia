"use client"

import { useEffect, useState } from "react"
import { adminService, User } from "@/services"
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
  const [internalUsers, setInternalUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [editName, setEditName] = useState("")
  const [editRole, setEditRole] = useState("")
  const [isEditOpen, setIsEditOpen] = useState(false)

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
    setEditRole(user.role || "user")
    setIsEditOpen(true)
  }

  const handleSaveEdit = async () => {
    if (!editingUser) return
    try {
      await adminService.updateUser(editingUser.id, { full_name: editName, role: editRole })
      setIsEditOpen(false)
      setEditingUser(null)
      if (!externalData) fetchUsers()
      else window.location.reload()
    } catch (error) {
      console.error("Failed to update user", error)
      alert("Failed to update user")
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
      header: "Role",
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
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="role" className="text-right">
                Role
              </Label>
              <Select value={editRole} onValueChange={setEditRole}>
                <SelectTrigger className="col-span-3">
                  <SelectValue placeholder="Select a role" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">User</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button onClick={handleSaveEdit}>Save changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
