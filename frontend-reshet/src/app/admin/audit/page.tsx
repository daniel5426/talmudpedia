"use client"

import React, { useState, useEffect, useCallback } from "react"
import { useTenant } from "@/contexts/TenantContext"
import { useDirection } from "@/components/direction-provider"
import { cn } from "@/lib/utils"
import { auditService, AuditLog, AuditLogDetail, AuditFilters } from "@/services/audit"
import {
  Search,
  User,
  Activity,
  Eye,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  Calendar,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

/* ------------------------------------------------------------------ */
/*  Row skeleton – matches the list layout                            */
/* ------------------------------------------------------------------ */
function LogRowSkeleton() {
  return (
    <div className="flex items-center gap-4 px-4 py-3.5 border-b border-border/40">
      <div className="w-[88px] shrink-0 space-y-1.5">
        <Skeleton className="h-3.5 w-16" />
        <Skeleton className="h-3 w-12" />
      </div>
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <Skeleton className="h-7 w-7 rounded-full shrink-0" />
        <Skeleton className="h-3.5 w-32" />
      </div>
      <Skeleton className="h-3.5 w-14 hidden md:block" />
      <div className="hidden lg:block w-[120px] space-y-1.5">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-3.5 w-24" />
      </div>
      <Skeleton className="h-3.5 w-16" />
      <Skeleton className="h-7 w-7 rounded-md" />
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Result indicator – colored dot + label                            */
/* ------------------------------------------------------------------ */
function ResultBadge({ result }: { result: string }) {
  const config: Record<string, { dot: string; text: string; label: string }> = {
    success: { dot: "bg-emerald-500", text: "text-emerald-600 dark:text-emerald-400", label: "Success" },
    failure: { dot: "bg-red-500", text: "text-red-600 dark:text-red-400", label: "Failure" },
    denied:  { dot: "bg-amber-500", text: "text-amber-600 dark:text-amber-400", label: "Denied" },
  }
  const c = config[result] || { dot: "bg-zinc-400", text: "text-muted-foreground", label: result }

  return (
    <span className="flex items-center gap-1.5">
      <span className={cn("h-1.5 w-1.5 rounded-full", c.dot)} />
      <span className={cn("text-xs", c.text)}>{c.label}</span>
    </span>
  )
}

/* ------------------------------------------------------------------ */
/*  JSON viewer                                                       */
/* ------------------------------------------------------------------ */
function JsonView({ data, title }: { data: any; title: string }) {
  return (
    <div className="space-y-2">
      <Label className="text-[10px] uppercase text-muted-foreground/50">{title}</Label>
      <pre className="bg-muted/50 p-3 rounded-lg text-[10px] overflow-auto max-h-48 border border-border/40 font-mono">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  )
}

/* ================================================================== */
/*  Main page                                                         */
/* ================================================================== */
export default function AuditPage() {
  const { currentTenant } = useTenant()
  const { direction } = useDirection()
  const isRTL = direction === "rtl"

  const [logs, setLogs] = useState<AuditLog[]>([])
  const [total, setTotal] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [filters, setFilters] = useState<AuditFilters>({ skip: 0, limit: 20 })
  const [selectedLog, setSelectedLog] = useState<AuditLogDetail | null>(null)
  const [isDetailOpen, setIsDetailOpen] = useState(false)

  /* ---- data fetching ---- */
  const fetchData = useCallback(async () => {
    if (!currentTenant) return
    setIsLoading(true)
    try {
      const [logsData, countData] = await Promise.all([
        auditService.listAuditLogs(currentTenant.slug, filters),
        auditService.countAuditLogs(currentTenant.slug, filters),
      ])
      setLogs(logsData)
      setTotal(countData.count)
    } catch (error) {
      console.error("Failed to fetch audit logs", error)
    } finally {
      setIsLoading(false)
    }
  }, [currentTenant, filters])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  /* ---- detail ---- */
  const handleViewDetail = async (logId: string) => {
    if (!currentTenant) return
    try {
      const detail = await auditService.getAuditLog(currentTenant.slug, logId)
      setSelectedLog(detail)
      setIsDetailOpen(true)
    } catch (error) {
      console.error("Failed to fetch log detail", error)
    }
  }

  /* ---- pagination ---- */
  const pageSize = filters.limit || 20
  const currentSkip = filters.skip || 0

  const nextPage = () => {
    setFilters((prev) => ({ ...prev, skip: (prev.skip || 0) + (prev.limit || 20) }))
  }
  const prevPage = () => {
    setFilters((prev) => ({ ...prev, skip: Math.max(0, (prev.skip || 0) - (prev.limit || 20)) }))
  }

  /* ---- no tenant guard ---- */
  if (!currentTenant) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        Please select a tenant from the sidebar to view audit logs.
      </div>
    )
  }

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-background" dir={direction}>
      {/* ============================================================ */}
      {/*  Header                                                      */}
      {/* ============================================================ */}
      <header className="h-12 shrink-0 bg-background px-4 flex items-center justify-between border-b border-border/40">
        <CustomBreadcrumb
          items={[
            { label: "Security & Org", href: "/admin/organization" },
            { label: "Audit Logs", active: true },
          ]}
        />
        <span className="text-xs text-muted-foreground/60 tabular-nums">
          {total.toLocaleString()} entries
        </span>
      </header>

      {/* ============================================================ */}
      {/*  Filter bar                                                  */}
      {/* ============================================================ */}
      <div className="shrink-0 border-b border-border/40 px-4 py-3">
        <div className={cn("flex flex-wrap items-center gap-2", isRTL ? "flex-row-reverse" : "flex-row")}>
          {/* Actor search */}
          <div className="relative w-full max-w-[220px]">
            <Search className={cn(
              "absolute top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/60",
              isRTL ? "right-2.5" : "left-2.5"
            )} />
            <Input
              placeholder="Search actor..."
              className={cn(
                "h-9 bg-muted/30 border-border/50 text-sm placeholder:text-muted-foreground/50",
                isRTL ? "pr-8 text-right" : "pl-8 text-left"
              )}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, actor_id: e.target.value || undefined, skip: 0 }))
              }
            />
          </div>

          {/* Action */}
          <Select
            onValueChange={(value) =>
              setFilters((prev) => ({ ...prev, action: value === "__all__" ? undefined : value, skip: 0 }))
            }
            dir={direction}
          >
            <SelectTrigger className="h-9 w-[130px] bg-muted/30 border-border/50 text-sm">
              <SelectValue placeholder="Action" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All Actions</SelectItem>
              {["read", "write", "delete", "execute", "admin"].map((a) => (
                <SelectItem key={a} value={a}>
                  {a.charAt(0).toUpperCase() + a.slice(1)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Resource type */}
          <Select
            onValueChange={(value) =>
              setFilters((prev) => ({ ...prev, resource_type: value === "__all__" ? undefined : value, skip: 0 }))
            }
            dir={direction}
          >
            <SelectTrigger className="h-9 w-[130px] bg-muted/30 border-border/50 text-sm">
              <SelectValue placeholder="Resource" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All Resources</SelectItem>
              {["index", "pipeline", "job", "org_unit", "role", "membership", "audit"].map((r) => (
                <SelectItem key={r} value={r}>
                  {r.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Result */}
          <Select
            onValueChange={(value) =>
              setFilters((prev) => ({ ...prev, result: value === "__all__" ? undefined : value, skip: 0 }))
            }
            dir={direction}
          >
            <SelectTrigger className="h-9 w-[130px] bg-muted/30 border-border/50 text-sm">
              <SelectValue placeholder="Result" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All Results</SelectItem>
              {["success", "failure", "denied"].map((r) => (
                <SelectItem key={r} value={r}>
                  {r.charAt(0).toUpperCase() + r.slice(1)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Date range */}
          <div className="flex items-center gap-1.5">
            <Calendar className="h-3.5 w-3.5 text-muted-foreground/50 shrink-0" />
            <Input
              type="date"
              className={cn("h-9 w-[140px] bg-muted/30 border-border/50 text-sm", isRTL ? "text-right" : "text-left")}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, start_date: e.target.value || undefined, skip: 0 }))
              }
            />
            <span className="text-muted-foreground/40 text-xs">-</span>
            <Input
              type="date"
              className={cn("h-9 w-[140px] bg-muted/30 border-border/50 text-sm", isRTL ? "text-right" : "text-left")}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, end_date: e.target.value || undefined, skip: 0 }))
              }
            />
          </div>
        </div>
      </div>

      {/* ============================================================ */}
      {/*  Log list                                                    */}
      {/* ============================================================ */}
      <main className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div>
            {Array.from({ length: 8 }).map((_, i) => (
              <LogRowSkeleton key={i} />
            ))}
          </div>
        ) : logs.length === 0 ? (
          /* ---- empty state ---- */
          <div className="flex flex-col items-center justify-center py-24 px-4 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-xl border-2 border-dashed border-border/60 mb-4">
              <Activity className="h-6 w-6 text-muted-foreground/40" />
            </div>
            <h3 className="text-sm font-medium text-foreground mb-1">No audit logs found</h3>
            <p className="text-sm text-muted-foreground/70 max-w-[300px]">
              Adjust your filters or date range to see results.
            </p>
          </div>
        ) : (
          /* ---- log rows ---- */
          <div className="divide-y divide-border/40">
            {logs.map((log) => (
              <div
                key={log.id}
                className="group flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-muted/40 cursor-pointer"
                onClick={() => handleViewDetail(log.id)}
              >
                {/* Timestamp */}
                <div className={cn("w-[88px] shrink-0", isRTL ? "text-right" : "text-left")}>
                  <div className="text-xs text-muted-foreground/80 font-medium">
                    {new Date(log.timestamp).toLocaleDateString()}
                  </div>
                  <div className="text-[10px] text-muted-foreground/50">
                    {new Date(log.timestamp).toLocaleTimeString()}
                  </div>
                </div>

                {/* Actor */}
                <div className={cn("flex items-center gap-2 flex-1 min-w-0", isRTL ? "flex-row-reverse" : "flex-row")}>
                  <div className="h-7 w-7 rounded-full bg-muted/60 border border-border/50 flex items-center justify-center shrink-0">
                    <User className="h-3.5 w-3.5 text-muted-foreground/60" />
                  </div>
                  <span className="text-sm text-foreground truncate">{log.actor_email}</span>
                </div>

                {/* Action */}
                <span className="hidden md:block text-xs text-muted-foreground/60 uppercase tracking-wide w-[64px] shrink-0">
                  {log.action}
                </span>

                {/* Resource */}
                <div className={cn("hidden lg:block w-[120px] shrink-0", isRTL ? "text-right" : "text-left")}>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground/40 font-medium">
                    {log.resource_type}
                  </div>
                  <div className="text-xs text-foreground/80 font-mono truncate" title={log.resource_name || log.resource_id || ""}>
                    {log.resource_name || log.resource_id || "N/A"}
                  </div>
                </div>

                {/* Result */}
                <div className="w-[72px] shrink-0">
                  <ResultBadge result={log.result} />
                </div>

                {/* Detail button */}
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground"
                  onClick={(e) => {
                    e.stopPropagation()
                    handleViewDetail(log.id)
                  }}
                >
                  <Eye className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* ============================================================ */}
      {/*  Pagination footer                                           */}
      {/* ============================================================ */}
      {!isLoading && logs.length > 0 && (
        <footer className="h-11 shrink-0 border-t border-border/40 px-4 flex items-center justify-between bg-background">
          <span className="text-xs text-muted-foreground/60 tabular-nums">
            {currentSkip + 1}-{Math.min(currentSkip + pageSize, total)} of {total.toLocaleString()}
          </span>
          <div className={cn("flex items-center gap-1.5", isRTL ? "flex-row-reverse" : "flex-row")}>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={prevPage}
              disabled={currentSkip === 0}
            >
              {isRTL ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={nextPage}
              disabled={currentSkip + pageSize >= total}
            >
              {isRTL ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </Button>
          </div>
        </footer>
      )}

      {/* ============================================================ */}
      {/*  Detail dialog                                               */}
      {/* ============================================================ */}
      <Dialog open={isDetailOpen} onOpenChange={setIsDetailOpen}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-auto" dir={direction}>
          <DialogHeader>
            <DialogTitle className={cn("flex items-center gap-2", isRTL ? "flex-row-reverse" : "flex-row")}>
              Audit Entry Details
              {selectedLog && <ResultBadge result={selectedLog.result} />}
            </DialogTitle>
          </DialogHeader>

          {selectedLog && (
            <div className="space-y-6 py-4">
              {/* Metadata grid */}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm border border-border/40 p-4 rounded-xl bg-muted/10">
                <div className={cn("space-y-1 min-w-0", isRTL ? "text-right" : "text-left")}>
                  <Label className="text-[10px] uppercase text-muted-foreground/50 block">Timestamp</Label>
                  <p className="font-medium">{new Date(selectedLog.timestamp).toLocaleString()}</p>
                </div>
                <div className={cn("space-y-1 min-w-0", isRTL ? "text-right" : "text-left")}>
                  <Label className="text-[10px] uppercase text-muted-foreground/50 block">Action</Label>
                  <p className="font-medium">
                    {selectedLog.action.toUpperCase()} on {selectedLog.resource_type.toUpperCase()}
                  </p>
                </div>
                <div className={cn("space-y-1 min-w-0", isRTL ? "text-right" : "text-left")}>
                  <Label className="text-[10px] uppercase text-muted-foreground/50 block">Duration</Label>
                  <p className="font-medium">{selectedLog.duration_ms || 0}ms</p>
                </div>
                <div className={cn("space-y-1 min-w-0", isRTL ? "text-right" : "text-left")}>
                  <Label className="text-[10px] uppercase text-muted-foreground/50 block">Actor</Label>
                  <p className="font-medium truncate" title={selectedLog.actor_email}>
                    {selectedLog.actor_email}
                  </p>
                </div>
                <div className={cn("space-y-1 min-w-0", isRTL ? "text-right" : "text-left")}>
                  <Label className="text-[10px] uppercase text-muted-foreground/50 block">IP Address</Label>
                  <p className="font-medium">{selectedLog.ip_address || "Unknown"}</p>
                </div>
                <div className={cn("space-y-1 min-w-0", isRTL ? "text-right" : "text-left")}>
                  <Label className="text-[10px] uppercase text-muted-foreground/50 block">Resource ID</Label>
                  <p className="font-mono text-[10px] truncate" title={selectedLog.resource_id || ""}>
                    {selectedLog.resource_id}
                  </p>
                </div>
              </div>

              {/* Failure reason */}
              {selectedLog.failure_reason && (
                <div
                  className={cn(
                    "p-3 bg-destructive/10 border-destructive/20 border rounded-lg text-destructive text-sm flex gap-2",
                    isRTL ? "flex-row-reverse text-right" : "flex-row text-left"
                  )}
                >
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  <p>{selectedLog.failure_reason}</p>
                </div>
              )}

              {/* JSON views */}
              <div dir={direction}>
                {selectedLog.request_params && (
                  <JsonView title="Request Parameters" data={selectedLog.request_params} />
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
                  {selectedLog.before_state && (
                    <JsonView title="State Before" data={selectedLog.before_state} />
                  )}
                  {selectedLog.after_state && (
                    <JsonView title="State After" data={selectedLog.after_state} />
                  )}
                </div>
              </div>

              {/* User agent */}
              <div className={cn("space-y-1", isRTL ? "text-right" : "text-left")}>
                <Label className="text-[10px] uppercase text-muted-foreground/50 block">User Agent</Label>
                <p className="text-[10px] text-muted-foreground bg-muted/50 p-2 rounded-lg border border-border/40">
                  {selectedLog.user_agent}
                </p>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
