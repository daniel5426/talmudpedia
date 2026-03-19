"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { adminService, agentService, Thread, type Agent } from "@/services"
import { DataTable } from "@/components/ui/data-table"
import { ColumnDef, type PaginationState } from "@tanstack/react-table"
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

interface ThreadsTableProps {
  data?: Thread[]
  pageCount?: number
  pagination?: PaginationState
  onPaginationChange?: (pagination: PaginationState) => void
  search?: string
  onSearchChange?: (search: string) => void
  agentId?: string
  onAgentIdChange?: (agentId: string) => void
  basePath?: string
}

const ALL_AGENTS_VALUE = "__all_agents__"

export function ThreadsTable({
  data: externalData,
  pageCount: externalPageCount,
  pagination: externalPagination,
  onPaginationChange,
  search: externalSearch,
  onSearchChange,
  agentId: externalAgentId,
  onAgentIdChange,
  basePath = "/admin/threads",
}: ThreadsTableProps) {
  const [internalThreads, setInternalThreads] = useState<Thread[]>([])
  const [loading, setLoading] = useState(true)
  const [agents, setAgents] = useState<Agent[]>([])
  const [internalSearch, setInternalSearch] = useState("")
  const [internalAgentId, setInternalAgentId] = useState("")
  const [internalPagination, setInternalPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 20,
  })
  const [internalPageCount, setInternalPageCount] = useState(0)

  const pagination = externalPagination ?? internalPagination
  const search = externalSearch ?? internalSearch
  const selectedAgentId = externalAgentId ?? internalAgentId
  const pageCount = externalPageCount ?? internalPageCount
  const setPagination = onPaginationChange ?? setInternalPagination
  const setSearch = onSearchChange ?? setInternalSearch
  const setAgentId = onAgentIdChange ?? setInternalAgentId
  const threads = externalData || internalThreads

  useEffect(() => {
    const loadAgents = async () => {
      try {
        const data = await agentService.listAgents({ compact: true })
        setAgents(data.agents)
      } catch (error) {
        console.error("Failed to load agents for filter", error)
      }
    }
    loadAgents()
  }, [])

  const fetchThreads = useCallback(async () => {
    if (externalData) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const data = await adminService.getThreads(
        pagination.pageIndex + 1,
        pagination.pageSize,
        search,
        { agentId: selectedAgentId || undefined },
      )
      setInternalThreads(data.items)
      setInternalPageCount(data.pages)
    } catch (error) {
      console.error("Failed to fetch threads", error)
    } finally {
      setLoading(false)
    }
  }, [externalData, pagination.pageIndex, pagination.pageSize, search, selectedAgentId])

  useEffect(() => {
    fetchThreads()
  }, [fetchThreads])

  const handleBulkDelete = async (ids: string[]) => {
    try {
      await adminService.bulkDeleteThreads(ids)
      if (!externalData) {
        await fetchThreads()
      } else {
        window.location.reload()
      }
    } catch (error) {
      console.error("Failed to delete threads", error)
      alert("Failed to delete threads")
    }
  }

  const columns: ColumnDef<Thread>[] = useMemo(() => [
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
        const thread = row.original
        return (
          <Link href={`${basePath}/${thread.id}`} className="hover:underline font-medium">
            {thread.title || "Untitled Thread"}
          </Link>
        )
      },
    },
    {
      accessorKey: "agent_name",
      header: "Agent",
      cell: ({ row }) => {
        const thread = row.original
        if (!thread.agent_id) return <span className="text-muted-foreground">—</span>
        return (
          <Link href={`/admin/agents/${thread.agent_id}/builder`} className="hover:underline">
            {thread.agent_name || thread.agent_slug || thread.agent_id}
          </Link>
        )
      },
    },
    {
      accessorKey: "surface",
      header: "Surface",
      cell: ({ row }) => row.original.surface || "—",
    },
    {
      accessorKey: "actor_display",
      header: "Actor",
      cell: ({ row }) => {
        const thread = row.original
        if (!thread.actor_id) return <span className="text-muted-foreground">—</span>
        return (
          <Link href={`/admin/users/${thread.actor_id}`} className="hover:underline">
            {thread.actor_display || thread.actor_email || thread.actor_id}
          </Link>
        )
      },
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
        const thread = row.original
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
              <DropdownMenuItem onClick={() => navigator.clipboard.writeText(thread.id)}>
                Copy ID
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link href={`${basePath}/${thread.id}`}>
                  <ExternalLink className="mr-2 h-4 w-4" /> View Thread
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem
                className="text-red-600"
                onClick={async () => {
                  if (confirm("Are you sure?")) {
                    await adminService.bulkDeleteThreads([thread.id])
                    if (!externalData) await fetchThreads()
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
  ], [basePath, externalData, fetchThreads])

  return (
    <div className="space-y-4">
      <DataTable
        columns={columns}
        data={threads}
        onBulkDelete={handleBulkDelete}
        filterColumn="title"
        filterPlaceholder="Search threads..."
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
        toolbarContent={(
          <Select
            value={selectedAgentId || ALL_AGENTS_VALUE}
            onValueChange={(value) => {
              setAgentId(value === ALL_AGENTS_VALUE ? "" : value)
              setPagination({ pageIndex: 0, pageSize: pagination.pageSize })
            }}
          >
            <SelectTrigger className="w-[220px]">
              <SelectValue placeholder="All agents" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_AGENTS_VALUE}>All agents</SelectItem>
              {agents.map((agent) => (
                <SelectItem key={agent.id} value={agent.id}>
                  {agent.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      />
    </div>
  )
}
