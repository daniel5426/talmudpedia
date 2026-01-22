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
  CheckCircle2,
  XCircle,
  AlertCircle,
  Eye,
  ChevronLeft,
  ChevronRight
} from "lucide-react"

import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"

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

  const fetchData = useCallback(async () => {
    if (!currentTenant) return
    setIsLoading(true)
    try {
      const [logsData, countData] = await Promise.all([
        auditService.listAuditLogs(currentTenant.slug, filters),
        auditService.countAuditLogs(currentTenant.slug, filters)
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

  const nextPage = () => {
    setFilters(prev => ({ ...prev, skip: (prev.skip || 0) + (prev.limit || 20) }))
  }

  const prevPage = () => {
    setFilters(prev => ({ ...prev, skip: Math.max(0, (prev.skip || 0) - (prev.limit || 20)) }))
  }

  const ResultBadge = ({ result }: { result: string }) => {
    switch (result) {
      case "success": return <Badge variant="default" className="bg-green-500 hover:bg-green-600 gap-1"><CheckCircle2 className="size-3" /> Success</Badge>
      case "failure": return <Badge variant="destructive" className="gap-1"><XCircle className="size-3" /> Failure</Badge>
      case "denied": return <Badge variant="secondary" className="bg-orange-500 text-white hover:bg-orange-600 gap-1"><AlertCircle className="size-3" /> Denied</Badge>
      default: return <Badge variant="outline">{result}</Badge>
    }
  }

  const JsonView = ({ data, title }: { data: any, title: string }) => (
    <div className="space-y-2">
      <Label className="text-xs uppercase opacity-50">{title}</Label>
      <pre className="bg-muted p-3 rounded-lg text-[10px] overflow-auto max-h-48 border">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  )

  if (!currentTenant) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        Please select a tenant from the sidebar to view audit logs.
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-muted/20 w-full" dir={direction}>
      <header className="h-14 border-b flex items-center justify-between px-4 bg-background z-30 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <CustomBreadcrumb items={[
              { label: "Dashboard", href: "/admin/dashboard" },
              { label: "Audit Logs", active: true },
            ]} />
          </div>
        </div>
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground bg-muted/50 px-2 py-0.5 rounded-full border">
          <Activity className="size-3 text-primary" />
          <span className="font-medium whitespace-nowrap">Total: {total.toLocaleString()} entries</span>
        </div>
      </header>

      <div className="flex-1 p-6 min-h-0 overflow-hidden">
        <Card className="h-full flex flex-col border-none shadow-md ring-1 ring-border/50 overflow-hidden">
          <CardHeader className="py-4 border-b bg-muted/10">
            <div className="flex flex-wrap gap-4">
              <div className="flex-1 min-w-[200px] relative">
                <Search className={cn("absolute top-2.5 size-4 text-muted-foreground", isRTL ? "right-2.5" : "left-2.5")} />
                <Input
                  placeholder="Search by Actor ID..."
                  className={cn("bg-background shadow-sm", isRTL ? "pr-9 text-right" : "pl-9 text-left")}
                  onChange={e => setFilters(prev => ({ ...prev, actor_id: e.target.value, skip: 0 }))}
                />
              </div>
              <div className="w-48">
                <select
                  className={cn("w-full h-10 px-3 rounded-md border border-input bg-background text-sm shadow-sm", isRTL ? "text-right" : "text-left")}
                  onChange={e => setFilters(prev => ({ ...prev, action: e.target.value || undefined, skip: 0 }))}
                  dir={direction}
                >
                  <option value="">All Actions</option>
                  {["read", "write", "delete", "execute", "admin"].map(a => <option key={a} value={a}>{a.toUpperCase()}</option>)}
                </select>
              </div>
              <div className="w-48">
                <select
                  className={cn("w-full h-10 px-3 rounded-md border border-input bg-background text-sm shadow-sm", isRTL ? "text-right" : "text-left")}
                  onChange={e => setFilters(prev => ({ ...prev, resource_type: e.target.value || undefined, skip: 0 }))}
                  dir={direction}
                >
                  <option value="">All Resources</option>
                  {["index", "pipeline", "job", "org_unit", "role", "membership", "audit"].map(r => <option key={r} value={r}>{r.toUpperCase()}</option>)}
                </select>
              </div>
            </div>
          </CardHeader>
          <CardContent className="p-0 flex-1 overflow-auto custom-scrollbar">
            {isLoading ? (
              <div className="p-6 space-y-4">
                {[...Array(8)].map((_, i) => <Skeleton key={i} className="h-12 w-full rounded-xl" />)}
              </div>
            ) : logs.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
                <div className="p-4 rounded-full bg-muted">
                  <Activity className="size-8 text-muted-foreground/40" />
                </div>
                <div className="space-y-1">
                  <p className="text-sm font-semibold">No audit logs found</p>
                  <p className="text-xs text-muted-foreground">Adjust your filters to see more results.</p>
                </div>
              </div>
            ) : (
              <Table>
                <TableHeader className="bg-muted/30 sticky top-0 z-10">
                  <TableRow className="hover:bg-transparent">
                    <TableHead className={cn("text-[11px] font-bold uppercase tracking-wider py-3", isRTL ? "text-right" : "text-left")}>Timestamp</TableHead>
                    <TableHead className={cn("text-[11px] font-bold uppercase tracking-wider py-3", isRTL ? "text-right" : "text-left")}>Actor</TableHead>
                    <TableHead className={cn("text-[11px] font-bold uppercase tracking-wider py-3", isRTL ? "text-right" : "text-left")}>Action</TableHead>
                    <TableHead className={cn("text-[11px] font-bold uppercase tracking-wider py-3", isRTL ? "text-right" : "text-left")}>Resource</TableHead>
                    <TableHead className={cn("text-[11px] font-bold uppercase tracking-wider py-3", isRTL ? "text-right" : "text-left")}>Result</TableHead>
                    <TableHead className={cn("text-[11px] font-bold uppercase tracking-wider py-3", isRTL ? "text-left" : "text-right")}>View</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {logs.map(log => (
                    <TableRow key={log.id} className="cursor-pointer hover:bg-muted/10 transition-colors" onClick={() => handleViewDetail(log.id)}>
                      <TableCell className={cn("text-xs whitespace-nowrap py-4", isRTL ? "text-right" : "text-left")}>
                        <div className="font-medium text-muted-foreground/80">
                          {new Date(log.timestamp).toLocaleDateString()}
                        </div>
                        <div className="text-[10px] opacity-60">
                          {new Date(log.timestamp).toLocaleTimeString()}
                        </div>
                      </TableCell>
                      <TableCell className={isRTL ? "text-right" : "text-left"}>
                        <div className="flex items-center gap-2">
                          <div className="size-7 rounded-full bg-muted flex items-center justify-center">
                            <User className="size-3.5 text-muted-foreground" />
                          </div>
                          <div className="flex flex-col">
                            <span className="text-[13px] font-semibold">{log.actor_email}</span>
                            <Badge variant="outline" className="text-[8px] h-3.5 px-1 w-fit uppercase font-bold tracking-tighter">{log.actor_type}</Badge>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className={isRTL ? "text-right" : "text-left"}>
                        <Badge variant="secondary" className="bg-muted/50 text-[10px] font-bold uppercase px-2 py-0.5 border-none shadow-none">
                          {log.action}
                        </Badge>
                      </TableCell>
                      <TableCell className={isRTL ? "text-right" : "text-left"}>
                        <div className="flex flex-col gap-0.5">
                          <span className="opacity-50 uppercase text-[9px] font-black tracking-widest">{log.resource_type}</span>
                          <span className="text-xs font-mono truncate max-w-[150px]">{log.resource_name || log.resource_id || "N/A"}</span>
                        </div>
                      </TableCell>
                      <TableCell className={isRTL ? "text-right" : "text-left"}>
                        <ResultBadge result={log.result} />
                      </TableCell>
                      <TableCell className={isRTL ? "text-left" : "text-right"}>
                        <Button variant="ghost" size="icon" className="size-8 text-muted-foreground hover:bg-background hover:shadow-sm">
                          <Eye className="size-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
          <div className="p-4 border-t bg-muted/5 flex items-center justify-between">
            <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground opacity-70">
              Showing {filters.skip! + 1}-{Math.min(filters.skip! + (filters.limit || 20), total)} of {total}
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="icon" className="size-8 shadow-sm" onClick={prevPage} disabled={filters.skip === 0}>
                {isRTL ? <ChevronRight className="size-4" /> : <ChevronLeft className="size-4" />}
              </Button>
              <Button variant="outline" size="icon" className="size-8 shadow-sm" onClick={nextPage} disabled={filters.skip! + (filters.limit || 20) >= total}>
                {isRTL ? <ChevronLeft className="size-4" /> : <ChevronRight className="size-4" />}
              </Button>
            </div>
          </div>
        </Card>
      </div>
      {/* Log Detail Dialog */}
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
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm border p-4 rounded-xl bg-muted/10">
                <div className={cn("space-y-1", isRTL ? "text-right" : "text-left")}>
                  <Label className="text-[10px] uppercase opacity-50 block">Timestamp</Label>
                  <p className="font-medium">{new Date(selectedLog.timestamp).toLocaleString()}</p>
                </div>
                <div className={cn("space-y-1", isRTL ? "text-right" : "text-left")}>
                  <Label className="text-[10px] uppercase opacity-50 block">Action</Label>
                  <p className="font-medium">{selectedLog.action.toUpperCase()} on {selectedLog.resource_type.toUpperCase()}</p>
                </div>
                <div className={cn("space-y-1", isRTL ? "text-right" : "text-left")}>
                  <Label className="text-[10px] uppercase opacity-50 block">Duration</Label>
                  <p className="font-medium">{selectedLog.duration_ms || 0}ms</p>
                </div>
                <div className={cn("space-y-1", isRTL ? "text-right" : "text-left")}>
                  <Label className="text-[10px] uppercase opacity-50 block">Actor</Label>
                  <p className="font-medium">{selectedLog.actor_email}</p>
                </div>
                <div className={cn("space-y-1", isRTL ? "text-right" : "text-left")}>
                  <Label className="text-[10px] uppercase opacity-50 block">IP Address</Label>
                  <p className="font-medium">{selectedLog.ip_address || "Unknown"}</p>
                </div>
                <div className={cn("space-y-1 overflow-hidden", isRTL ? "text-right" : "text-left")}>
                  <Label className="text-[10px] uppercase opacity-50 block">Resource ID</Label>
                  <p className="font-mono text-[10px] truncate">{selectedLog.resource_id}</p>
                </div>
              </div>

              {selectedLog.failure_reason && (
                <div className={cn("p-3 bg-destructive/10 border-destructive/20 border rounded-lg text-destructive text-sm flex gap-2", isRTL ? "flex-row-reverse text-right" : "flex-row text-left")}>
                  <AlertCircle className="size-4 shrink-0" />
                  <p>{selectedLog.failure_reason}</p>
                </div>
              )}

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

              <div className={cn("space-y-1", isRTL ? "text-right" : "text-left")}>
                <Label className="text-[10px] uppercase opacity-50 block">User Agent</Label>
                <p className="text-[10px] text-muted-foreground bg-muted p-2 rounded-md">{selectedLog.user_agent}</p>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
