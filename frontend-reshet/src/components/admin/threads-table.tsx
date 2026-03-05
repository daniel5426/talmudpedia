"use client"

import { useCallback, useEffect, useState } from "react"
import { adminService, Thread } from "@/services"
import { DataTable } from "@/components/ui/data-table"
import { ColumnDef } from "@tanstack/react-table"
import { Checkbox } from "@/components/ui/checkbox"
import { Button } from "@/components/ui/button"
import { MoreHorizontal, Trash2, ExternalLink } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { format } from "date-fns"
import Link from "next/link"

interface ThreadsTableProps {
  data?: Thread[]
  pageCount?: number
  pagination?: { pageIndex: number; pageSize: number }
  onPaginationChange?: (pagination: { pageIndex: number; pageSize: number }) => void
  onSearchChange?: (search: string) => void
  basePath?: string
}

export function ThreadsTable({
  data: externalData,
  basePath = "/admin/threads",
}: ThreadsTableProps) {
  const [internalThreads, setInternalThreads] = useState<Thread[]>([])
  const [loading, setLoading] = useState(true)

  const threads = externalData || internalThreads

  const fetchThreads = useCallback(async () => {
    if (externalData) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const data = await adminService.getThreads(1, 1000)
      setInternalThreads(data.items)
    } catch (error) {
      console.error("Failed to fetch threads", error)
    } finally {
      setLoading(false)
    }
  }, [externalData])

  useEffect(() => {
    fetchThreads()
  }, [fetchThreads])

  const handleBulkDelete = async (ids: string[]) => {
    try {
      await adminService.bulkDeleteThreads(ids)
      if (!externalData) {
          await fetchThreads()
      } else {
          // If external data, we can't easily refresh without a callback, 
          // but for now let's assume the parent handles it or we just reload the page if critical.
          window.location.reload() 
      }
    } catch (error) {
      console.error("Failed to delete threads", error)
      alert("Failed to delete threads")
    }
  }

  const columns: ColumnDef<Thread>[] = [
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
      accessorKey: "title",
      header: "Title",
      cell: ({ row }) => {
        const chat = row.original
        return (
            <Link href={`${basePath}/${chat.id}`} className="hover:underline font-medium">
                {chat.title || "Untitled Thread"}
            </Link>
        )
      }
    },
    {
      accessorKey: "updated_at",
      header: "Last Updated",
      cell: ({ row }) => {
        const date = row.getValue("updated_at") as string
        return date ? format(new Date(date), "MMM d, yyyy HH:mm") : "N/A"
      },
    },
    {
      id: "actions",
      cell: ({ row }) => {
        const chat = row.original
 
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
                onClick={() => navigator.clipboard.writeText(chat.id)}
              >
                Copy ID
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link href={`${basePath}/${chat.id}`}>
                    <ExternalLink className="mr-2 h-4 w-4" /> View Thread
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem 
                className="text-red-600"
                onClick={async () => {
                    if(confirm("Are you sure?")) {
                        await adminService.bulkDeleteThreads([chat.id])
                        if (!externalData) fetchThreads()
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
        <DataTable 
        columns={columns} 
        data={threads} 
        onBulkDelete={handleBulkDelete}
        filterColumn="title"
        filterPlaceholder="Filter threads..."
        isLoading={loading}
    />
  )
}
