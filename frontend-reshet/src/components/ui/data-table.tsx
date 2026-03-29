"use client"

import * as React from "react"
import {
  ColumnDef,
  ColumnFiltersState,
  PaginationState,
  SortingState,
  type Updater,
  VisibilityState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table"
import { ChevronDown, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { SearchInput } from "@/components/ui/search-input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[]
  data: TData[]
  onBulkDelete?: (selectedIds: string[]) => Promise<void>
  filterColumn?: string
  filterPlaceholder?: string
  isLoading?: boolean
  filterValue?: string
  onFilterChange?: (value: string) => void
  manualPagination?: boolean
  pageCount?: number
  pagination?: PaginationState
  onPaginationChange?: (pagination: PaginationState) => void
  toolbarContent?: React.ReactNode
  toolbarActions?: React.ReactNode
  selectionEnabled?: boolean
  emptyStateTitle?: string
  emptyStateDescription?: string
  emptyStateIcon?: React.ReactNode
}

export function DataTable<TData, TValue>({
  columns,
  data,
  onBulkDelete,
  filterColumn = "email",
  filterPlaceholder = "Filter...",
  isLoading = false,
  filterValue,
  onFilterChange,
  manualPagination = false,
  pageCount,
  pagination,
  onPaginationChange,
  toolbarContent,
  toolbarActions,
  selectionEnabled = true,
  emptyStateTitle = "No results found.",
  emptyStateDescription,
  emptyStateIcon,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = React.useState<SortingState>([])
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([])
  const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>({})
  const [rowSelection, setRowSelection] = React.useState({})
  const [internalPagination, setInternalPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 10,
  })

  const resolvedPagination = pagination ?? internalPagination

  const table = useReactTable({
    data,
    columns,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onPaginationChange: (updater: Updater<PaginationState>) => {
      const nextValue = typeof updater === "function" ? updater(resolvedPagination) : updater
      const applyPagination = onPaginationChange ?? setInternalPagination
      applyPagination(nextValue)
    },
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: manualPagination ? undefined : getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: manualPagination ? undefined : getFilteredRowModel(),
    onColumnVisibilityChange: setColumnVisibility,
    onRowSelectionChange: setRowSelection,
    manualPagination,
    manualFiltering: Boolean(onFilterChange),
    pageCount,
    state: {
      sorting,
      columnFilters,
      columnVisibility,
      rowSelection,
      pagination: resolvedPagination,
    },
  })

  const filteredSelectedRows = table.getFilteredSelectedRowModel().rows
  const selectedIds = React.useMemo(() => {
    return filteredSelectedRows.map((row) => (row.original as any).id)
  }, [filteredSelectedRows])
  const resolvedSelectedIds = selectionEnabled ? selectedIds : []

  React.useEffect(() => {
    if (!selectionEnabled) {
      setRowSelection({})
    }
  }, [selectionEnabled])

  const handleBulkDelete = async () => {
    if (onBulkDelete && resolvedSelectedIds.length > 0) {
      if (confirm(`Are you sure you want to delete ${resolvedSelectedIds.length} items?`)) {
        await onBulkDelete(resolvedSelectedIds)
        setRowSelection({})
      }
    }
  }

  return (
    <div className="w-full space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <SearchInput
            placeholder={filterPlaceholder}
            value={filterValue ?? ((table.getColumn(filterColumn)?.getFilterValue() as string) ?? "")}
            onChange={(event) => {
              if (onFilterChange) {
                onFilterChange(event.target.value)
                return
              }
              table.getColumn(filterColumn)?.setFilterValue(event.target.value)
            }}
            wrapperClassName="max-w-md flex-1 min-w-[220px]"
          />

          {toolbarContent}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {resolvedSelectedIds.length > 0 && (
            <Button variant="destructive" size="sm" onClick={handleBulkDelete}>
              <Trash2 className="mr-2 h-4 w-4" />
              Delete ({resolvedSelectedIds.length})
            </Button>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                Columns <ChevronDown className="ml-2 h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {table
                .getAllColumns()
                .filter((column) => column.getCanHide())
                .map((column) => {
                  return (
                    <DropdownMenuCheckboxItem
                      key={column.id}
                      className="capitalize"
                      checked={column.getIsVisible()}
                      onCheckedChange={(value) => column.toggleVisibility(!!value)}
                    >
                      {column.id}
                    </DropdownMenuCheckboxItem>
                  )
              })}
            </DropdownMenuContent>
          </DropdownMenu>
          {toolbarActions}
        </div>
      </div>
      <div className="overflow-hidden rounded-xl border bg-background">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  return (
                    <TableHead key={header.id}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(
                            header.column.columnDef.header,
                            header.getContext()
                          )}
                    </TableHead>
                  )
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 4 }).map((_, index) => (
                <TableRow key={`loading-${index}`}>
                  {Array.from({ length: columns.length }).map((__, cellIndex) => (
                    <TableCell key={`loading-${index}-${cellIndex}`}>
                      <Skeleton className="h-4 w-full max-w-[140px]" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  data-state={row.getIsSelected() && "selected"}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext()
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="py-12 text-center"
                >
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    {emptyStateIcon ? (
                      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
                        {emptyStateIcon}
                      </div>
                    ) : null}
                    <span>{emptyStateTitle}</span>
                    {emptyStateDescription ? (
                      <span className="max-w-sm text-sm text-muted-foreground/80">{emptyStateDescription}</span>
                    ) : null}
                  </div>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex-1 text-sm text-muted-foreground">
          {selectionEnabled
            ? `${table.getFilteredSelectedRowModel().rows.length} of ${table.getFilteredRowModel().rows.length} row(s) selected.`
            : `${table.getFilteredRowModel().rows.length} row(s)`}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  )
}
