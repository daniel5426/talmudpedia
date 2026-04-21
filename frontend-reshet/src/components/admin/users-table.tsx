"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { adminService, User } from "@/services"
import { DataTable } from "@/components/ui/data-table"
import { ColumnDef, type PaginationState } from "@tanstack/react-table"
import { Checkbox } from "@/components/ui/checkbox"
import { Button } from "@/components/ui/button"
import { MoreHorizontal, Edit, Trash2, Users, PencilLine } from "lucide-react"
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
import { Badge } from "@/components/ui/badge"

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
  const [internalUsers, setInternalUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [editName, setEditName] = useState("")
  const [isEditOpen, setIsEditOpen] = useState(false)
  const [actorType, setActorType] = useState("")
  const [selectionMode, setSelectionMode] = useState(false)
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

  const fetchUsers = useCallback(async () => {
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
  }, [actorType, externalData, pagination.pageIndex, pagination.pageSize, search])

  useEffect(() => {
    void fetchUsers()
  }, [fetchUsers])

  const handleEditClick = (user: User) => {
    setEditingUser(user)
    setEditName(user.display_name || user.full_name || "")
    setIsEditOpen(true)
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

  const handleBulkDelete = async (ids: string[]) => {
    try {
      const resolvedIds = ids.map((id) => {
        const user = users.find((entry) => entry.id === id)
        return user?.platform_user_id || user?.id || id
      })
      await adminService.bulkDeleteUsers(resolvedIds)
      await fetchUsers()
    } catch (error) {
      console.error("Failed to delete users", error)
      alert("Failed to delete users")
    }
  }

  const columns: ColumnDef<User>[] = useMemo(() => {
    const dataColumns: ColumnDef<User>[] = [
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
      cell: ({ row }) => <Badge variant="outline">{actorTypeLabel(row.original)}</Badge>,
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
      header: "Access",
      cell: ({ row }) => {
        const user = row.original
        if (!user.is_manageable) return <span className="text-muted-foreground">Read only</span>
        return <span className="text-sm text-muted-foreground">{user.org_role || user.role || "User"}</span>
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
    ]

    if (!selectionMode) return dataColumns

    return [
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
      ...dataColumns,
    ]
  }, [fetchUsers, selectionMode])

  return (
    <div className="space-y-4">
      <DataTable
        columns={columns}
        data={users}
        onBulkDelete={handleBulkDelete}
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
        selectionEnabled={selectionMode}
        toolbarActions={(
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 border-0 shadow-none data-[active=true]:bg-primary/5 data-[active=true]:text-primary"
            data-active={selectionMode}
            onClick={() => setSelectionMode((current) => !current)}
            aria-label={selectionMode ? "Hide selection controls" : "Show selection controls"}
          >
            <PencilLine className="h-4 w-4" />
          </Button>
        )}
        toolbarContent={(
          <Select
            value={actorType || ALL_TYPES_VALUE}
            onValueChange={(value) => {
              setActorType(value === ALL_TYPES_VALUE ? "" : value)
              setPagination({ pageIndex: 0, pageSize: pagination.pageSize })
            }}
          >
            <SelectTrigger size="sm" className="h-8 w-[220px] border-border/50 bg-muted/30 shadow-none">
              <SelectValue placeholder="All actor types" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_TYPES_VALUE}>All actor types</SelectItem>
              <SelectItem value="platform_user">Platform users</SelectItem>
              <SelectItem value="published_app_account">App accounts</SelectItem>
              <SelectItem value="embedded_external_user">Embedded users</SelectItem>
            </SelectContent>
          </Select>
        )}
        emptyStateTitle={search ? "No users match your search." : "No users found."}
        emptyStateDescription={search ? "Try a different name, email, or actor type." : "Users will appear here once accounts are created or synced."}
        emptyStateIcon={<Users className="h-6 w-6" />}
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
    </div>
  )
}
