"use client"

import { useEffect, useState } from "react"
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Search,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { SearchInput } from "@/components/ui/search-input"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { formatHttpErrorMessage } from "@/services/http"
import {
  settingsAuditService,
  SettingsAuditLog,
  SettingsAuditLogDetail,
} from "@/services"

function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
      <AlertCircle className="h-3.5 w-3.5 shrink-0" />
      <span>{message}</span>
    </div>
  )
}

export function AuditLogsSection({
  initialResourceId,
}: {
  initialResourceId?: string | null
}) {
  const [logs, setLogs] = useState<SettingsAuditLog[]>([])
  const [count, setCount] = useState(0)
  const [filters, setFilters] = useState({
    actor_email: "",
    action: "",
    resource_type: "",
    resource_id: initialResourceId || "",
    result: "",
    skip: 0,
    limit: 20,
  })
  const [detail, setDetail] = useState<SettingsAuditLogDetail | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setError(null)
    try {
      const [rows, countData] = await Promise.all([
        settingsAuditService.listAuditLogs(filters),
        settingsAuditService.countAuditLogs(filters),
      ])
      setLogs(rows)
      setCount(countData.count)
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to load audit logs."))
    }
  }

  useEffect(() => {
    void load()
  }, [filters])

  useEffect(() => {
    if (initialResourceId) {
      setFilters((current) => ({ ...current, resource_id: initialResourceId, skip: 0 }))
    }
  }, [initialResourceId])

  const totalPages = Math.ceil(count / filters.limit)
  const currentPage = Math.floor(filters.skip / filters.limit) + 1

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div>
        <h2 className="text-sm font-medium text-foreground">Audit Logs</h2>
        <p className="text-xs text-muted-foreground/70 mt-0.5">
          {count.toLocaleString()} entries in the active organization.
        </p>
      </div>

      {/* ── Filter row ── */}
      <div className="flex items-center gap-2 flex-wrap">
        <SearchInput
          placeholder="Actor email"
          value={filters.actor_email}
          onChange={(event) => setFilters((c) => ({ ...c, actor_email: event.target.value, skip: 0 }))}
          wrapperClassName="w-52"
        />
        <Input
          value={filters.action}
          onChange={(event) => setFilters((c) => ({ ...c, action: event.target.value, skip: 0 }))}
          placeholder="Action"
          className="h-8 w-36"
        />
        <Input
          value={filters.resource_type}
          onChange={(event) => setFilters((c) => ({ ...c, resource_type: event.target.value, skip: 0 }))}
          placeholder="Resource type"
          className="h-8 w-36"
        />
        <Input
          value={filters.resource_id}
          onChange={(event) => setFilters((c) => ({ ...c, resource_id: event.target.value, skip: 0 }))}
          placeholder="Resource ID"
          className="h-8 w-44"
        />
      </div>

      <ErrorBanner message={error} />

      {/* ── Log list ── */}
      {logs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Search className="h-8 w-8 text-muted-foreground/30 mb-3" />
          <p className="text-sm font-medium text-muted-foreground">No audit logs found</p>
          <p className="text-xs text-muted-foreground/60 mt-1">Try adjusting your filters</p>
        </div>
      ) : (
        <>
          <div className="divide-y divide-border/30">
            {logs.map((log) => (
              <button
                key={log.id}
                type="button"
                className="flex w-full items-center justify-between px-1 py-2.5 text-left hover:bg-muted/20 transition-colors"
                onClick={() => {
                  void settingsAuditService.getAuditLog(log.id).then((row) => {
                    setDetail(row)
                    setDetailOpen(true)
                  })
                }}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate">{log.actor_email}</span>
                    <span className="text-muted-foreground/30">·</span>
                    <span className="text-xs text-muted-foreground/60">{log.action}</span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-2">
                    <span className="text-xs text-muted-foreground/50">{log.resource_type}</span>
                    <span className="text-muted-foreground/30">·</span>
                    <span className="text-xs text-muted-foreground/40">{log.result}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs text-muted-foreground/50">
                    {new Date(log.timestamp).toLocaleString()}
                  </span>
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/30" />
                </div>
              </button>
            ))}
          </div>

          {/* ── Pagination ── */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-2">
              <p className="text-xs text-muted-foreground/50">
                Page {currentPage} of {totalPages}
              </p>
              <div className="flex items-center gap-1">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 w-7 p-0"
                  disabled={filters.skip === 0}
                  onClick={() => setFilters((c) => ({ ...c, skip: Math.max(0, c.skip - c.limit) }))}
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 w-7 p-0"
                  disabled={filters.skip + filters.limit >= count}
                  onClick={() => setFilters((c) => ({ ...c, skip: c.skip + c.limit }))}
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Detail dialog ── */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="text-base">Audit Detail</DialogTitle>
          </DialogHeader>
          {detail ? (
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-lg border border-border/40 p-3">
                  <p className="text-xs text-muted-foreground/60 mb-0.5">Actor</p>
                  <p className="text-sm font-medium">{detail.actor_email}</p>
                </div>
                <div className="rounded-lg border border-border/40 p-3">
                  <p className="text-xs text-muted-foreground/60 mb-0.5">Action</p>
                  <p className="text-sm font-medium">{detail.action}</p>
                </div>
              </div>
              <pre className="max-h-[420px] overflow-auto rounded-lg border border-border/40 bg-muted/30 p-3 text-xs">
                {JSON.stringify(detail, null, 2)}
              </pre>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  )
}
