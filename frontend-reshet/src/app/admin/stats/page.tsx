"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Calendar,
  ChevronRight,
  Download,
  Users,
  MessageSquare,
  Cpu,
  Database,
  Wrench,
  Activity,
  AlertCircle,
  Timer,
  Server,
  Loader2,
} from "lucide-react"
import { cn } from "@/lib/utils"
import {
  adminService,
  type StatsSection,
  type DailyDataPoint,
  type AdminStatsOverview,
  type AdminStatsRAG,
  type AdminStatsAgents,
  type AdminStatsResources,
} from "@/services"
import { BarChart } from "@/components/admin/stats/BarChart"
import { MetricBlock } from "@/components/admin/stats/MetricBlock"
import { MetricDetailPanel } from "@/components/admin/stats/MetricDetailPanel"
import { StatsBreadcrumb } from "@/components/admin/stats/StatsBreadcrumb"

type DetailByTab = Record<StatsSection, string | null>

const detailLabels: Record<string, string> = {
  "overview.users": "Users",
  "overview.messages": "Messages",
  "overview.tokens": "Tokens",
  "overview.spend": "Spend",
  "overview.agentRuns": "Agent Runs",
  "overview.pipelineJobs": "Pipeline Jobs",
  "rag.stores": "Knowledge Stores",
  "rag.pipelines": "Pipelines",
  "rag.jobs": "Jobs",
  "rag.failures": "Failures",
  "agents.runs": "Runs",
  "agents.failures": "Failures",
  "agents.tokens": "Tokens",
  "agents.queueTime": "Queue Time",
  "resources.tools": "Tools",
  "resources.models": "Models",
  "resources.artifacts": "Artifacts",
  "resources.providers": "Providers",
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
    </div>
  )
}

function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-4">
      <AlertCircle className="h-8 w-8 text-red-500" />
      <p className="text-sm text-muted-foreground">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  )
}

function formatCompact(value: number) {
  return value.toLocaleString()
}

function formatDuration(ms?: number | null) {
  if (!ms && ms !== 0) return "—"
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function StatusDot({ rate }: { rate: number }) {
  return (
    <span
      className={cn(
        "w-2 h-2 rounded-full",
        rate >= 90 ? "bg-green-500" : rate >= 75 ? "bg-amber-500" : "bg-red-500"
      )}
    />
  )
}

function SummaryRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}

function formatDate(value: Date) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, "0")
  const day = String(value.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

function parseDate(value?: string) {
  if (!value) return null
  const parsed = new Date(`${value}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return null
  return parsed
}

function addDays(value: Date, amount: number) {
  const next = new Date(value)
  next.setDate(next.getDate() + amount)
  return next
}

function buildRangeDates(start: string, end: string) {
  const startDate = parseDate(start)
  const endDate = parseDate(end)
  if (!startDate || !endDate) return []
  const dates: string[] = []
  let cursor = startDate
  while (cursor <= endDate) {
    dates.push(formatDate(cursor))
    cursor = addDays(cursor, 1)
  }
  return dates
}

function resolveDateRange(days: number, range?: { start?: string; end?: string } | null) {
  const today = new Date()
  const endDate = parseDate(range?.end) ?? today
  const startDate = parseDate(range?.start) ?? addDays(endDate, -(days - 1))
  return { start: formatDate(startDate), end: formatDate(endDate) }
}

function fillDailyRange(data: DailyDataPoint[], rangeDates: string[]) {
  if (!rangeDates.length) return data
  const lookup = new Map(data.map((item) => [item.date, item.value]))
  return rangeDates.map((date) => ({
    date,
    value: lookup.get(date) ?? 0,
  }))
}

function buildRollingAverage(data: DailyDataPoint[], windowSize: number) {
  if (!data.length) return data
  const size = Math.max(1, Math.min(windowSize, data.length))
  return data.map((point, index) => {
    const start = Math.max(0, index - size + 1)
    const slice = data.slice(start, index + 1)
    const average = slice.reduce((acc, item) => acc + item.value, 0) / slice.length
    return {
      date: point.date,
      value: Number(average.toFixed(2)),
    }
  })
}

function toChartData(record?: Record<string, number> | null): DailyDataPoint[] {
  if (!record) return []
  return Object.entries(record)
    .sort((a, b) => b[1] - a[1])
    .map(([key, value]) => ({
      date: key.replace(/_/g, " "),
      value,
    }))
}

function getRecordValue(
  record: Record<string, number> | null | undefined,
  keys: string[]
) {
  if (!record) return 0
  const normalized = Object.fromEntries(
    Object.entries(record).map(([key, value]) => [key.toLowerCase(), value])
  )
  for (const key of keys) {
    const value = normalized[key.toLowerCase()]
    if (typeof value === "number") return value
  }
  return 0
}

function GraphCard({
  title,
  value,
  subValue,
  periodLabel,
  data,
  color = "#8b5cf6",
  showLabels = true,
  onClick,
}: {
  title: string;
  value: string | number;
  subValue?: string;
  periodLabel?: string;
  data: DailyDataPoint[];
  color?: string;
  showLabels?: boolean;
  onClick?: () => void;
}) {
  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "text-left border rounded-lg p-4 transition-all",
          "hover:border-muted-foreground/40 hover:shadow-sm",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
        )}
      >
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-sm font-medium">{title}</h3>
          {periodLabel && <span className="text-xs text-muted-foreground">{periodLabel}</span>}
        </div>
        <div className="text-xl font-semibold">{value}</div>
        {subValue && <div className="text-xs text-muted-foreground mb-3">{subValue}</div>}
        <BarChart data={data} height={160} color={color} showLabels={showLabels} />
      </button>
    )
  }

  return (
    <div className="text-left border rounded-lg p-4 transition-all">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-medium">{title}</h3>
        {periodLabel && <span className="text-xs text-muted-foreground">{periodLabel}</span>}
      </div>
      <div className="text-xl font-semibold">{value}</div>
      {subValue && <div className="text-xs text-muted-foreground mb-3">{subValue}</div>}
      <BarChart data={data} height={160} color={color} showLabels={showLabels} />
    </div>
  )
}

function StatusRow({ label, rate }: { label: string; rate: number }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <div className="flex items-center gap-1.5">
        <StatusDot rate={rate} />
        <span className="font-medium">{rate.toFixed(1)}%</span>
      </div>
    </div>
  )
}

export default function AdminStatsPage() {
  const [activeTab, setActiveTab] = useState<StatsSection>("overview")
  const [days, setDays] = useState(7)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [customStart, setCustomStart] = useState("")
  const [customEnd, setCustomEnd] = useState("")
  const [appliedRange, setAppliedRange] = useState<{ start?: string; end?: string } | null>(null)
  const [isDateOpen, setIsDateOpen] = useState(false)
  const [dateError, setDateError] = useState<string | null>(null)
  const datePopoverRef = useRef<HTMLDivElement>(null)

  const [detailByTab, setDetailByTab] = useState<DetailByTab>({
    overview: null,
    rag: null,
    agents: null,
    resources: null,
  })

  const [overview, setOverview] = useState<AdminStatsOverview | null>(null)
  const [rag, setRAG] = useState<AdminStatsRAG | null>(null)
  const [agents, setAgents] = useState<AdminStatsAgents | null>(null)
  const [resources, setResources] = useState<AdminStatsResources | null>(null)

  const activeDetailId = detailByTab[activeTab]

  const rangeDates = useMemo(() => {
    const resolved = resolveDateRange(days, appliedRange)
    return buildRangeDates(resolved.start, resolved.end)
  }, [days, appliedRange?.start, appliedRange?.end])

  const emptyRangeSeries = useMemo(
    () => rangeDates.map((date) => ({ date, value: 0 })),
    [rangeDates]
  )

  useEffect(() => {
    if (!isDateOpen) return
    function handleClickOutside(e: MouseEvent) {
      if (datePopoverRef.current && !datePopoverRef.current.contains(e.target as Node)) {
        setIsDateOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [isDateOpen])

  const loadStats = async (section: StatsSection) => {
    setLoading(true)
    setError(null)

    try {
      const response = await adminService.getStatsSummary(
        section,
        days,
        appliedRange?.start,
        appliedRange?.end
      )

      switch (section) {
        case "overview":
          setOverview(response.overview || null)
          break
        case "rag":
          setRAG(response.rag || null)
          break
        case "agents":
          setAgents(response.agents || null)
          break
        case "resources":
          setResources(response.resources || null)
          break
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load stats")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadStats(activeTab)
  }, [activeTab, days, appliedRange?.start, appliedRange?.end])

  const handleTabChange = (value: string) => {
    setActiveTab(value as StatsSection)
  }

  const setDetail = (id: string | null) => {
    setDetailByTab(prev => ({ ...prev, [activeTab]: id }))
  }

  const applyCustomRange = () => {
    if (!customStart && !customEnd) return
    if (customStart && customEnd && customStart > customEnd) {
      setDateError("Start must be before end")
      return
    }
    setDateError(null)
    setAppliedRange({
      start: customStart || undefined,
      end: customEnd || undefined,
    })
    setIsDateOpen(false)
  }

  const clearCustomRange = () => {
    setAppliedRange(null)
    setCustomStart("")
    setCustomEnd("")
    setDateError(null)
    setIsDateOpen(false)
  }

  const usePreset = (presetDays: number) => {
    setDays(presetDays)
    setAppliedRange(null)
    setCustomStart("")
    setCustomEnd("")
    setDateError(null)
  }

  const ragFailureCount = useMemo(() => {
    if (!rag) return 0
    return (
      rag.jobs_by_status.FAILED ||
      rag.jobs_by_status.failed ||
      0
    )
  }, [rag])

  const ragTotalJobs = useMemo(() => {
    if (!rag) return 0
    return rag.jobs_by_day.reduce((acc, item) => acc + item.value, 0)
  }, [rag])

  const ragJobsByDayFilled = useMemo(() => {
    if (!rag) return []
    return fillDailyRange(rag.jobs_by_day, rangeDates)
  }, [rag, rangeDates])

  const ragJobsRollingAvg = useMemo(() => {
    return buildRollingAverage(ragJobsByDayFilled, 7)
  }, [ragJobsByDayFilled])

  const overviewDailyActiveFilled = useMemo(() => {
    if (!overview) return []
    return fillDailyRange(overview.daily_active_users, rangeDates)
  }, [overview, rangeDates])

  const overviewSpendFilled = useMemo(() => {
    if (!overview) return []
    return fillDailyRange(overview.spend_by_day, rangeDates)
  }, [overview, rangeDates])

  const overviewTokensFilled = useMemo(() => {
    if (!overview) return []
    return fillDailyRange(overview.tokens_by_day, rangeDates)
  }, [overview, rangeDates])

  const agentsRunsFilled = useMemo(() => {
    if (!agents) return []
    return fillDailyRange(agents.runs_by_day, rangeDates)
  }, [agents, rangeDates])

  const agentsTokensFilled = useMemo(() => {
    if (!agents) return []
    return fillDailyRange(agents.tokens_by_day, rangeDates)
  }, [agents, rangeDates])

  const agentsRunsRollingAvg = useMemo(() => {
    return buildRollingAverage(agentsRunsFilled, 7)
  }, [agentsRunsFilled])

  const resourceToolsByTypeChart = useMemo(() => {
    if (!resources) return []
    return toChartData(resources.tools_by_type)
  }, [resources])

  const resourceModelsByCapabilityChart = useMemo(() => {
    if (!resources) return []
    return toChartData(resources.models_by_capability)
  }, [resources])

  const resourceArtifactsByCategoryChart = useMemo(() => {
    if (!resources) return []
    return toChartData(resources.artifacts_by_category)
  }, [resources])

  const breadcrumbItems = useMemo(() => {
    if (!activeDetailId) return []
    return [
      { label: "Usage", onClick: () => setDetail(null) },
      { label: activeTab.charAt(0).toUpperCase() + activeTab.slice(1), onClick: () => setDetail(null) },
      { label: detailLabels[activeDetailId] || "Detail", active: true },
    ]
  }, [activeDetailId, activeTab])

  const periodLabel = appliedRange
    ? (appliedRange.start && appliedRange.end ? `${appliedRange.start} – ${appliedRange.end}` : "Custom")
    : `${days}d`

  return (
    <div className="flex flex-col h-full w-full overflow-hidden">
      <header className="h-12 flex items-center justify-between px-4 bg-background z-30 shrink-0">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Admin</span>
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
          <span className="font-medium">Stats</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex border rounded-md overflow-hidden">
            <button
              onClick={() => usePreset(7)}
              className={cn(
                "px-3 py-1.5 text-xs transition-colors",
                days === 7 && !appliedRange
                  ? "bg-muted font-medium"
                  : "text-muted-foreground hover:bg-muted/50"
              )}
            >
              7 days
            </button>
            <button
              onClick={() => usePreset(30)}
              className={cn(
                "px-3 py-1.5 text-xs transition-colors",
                days === 30 && !appliedRange
                  ? "bg-muted font-medium"
                  : "text-muted-foreground hover:bg-muted/50"
              )}
            >
              30 days
            </button>
            <button
              onClick={() => usePreset(90)}
              className={cn(
                "px-3 py-1.5 text-xs transition-colors",
                days === 90 && !appliedRange
                  ? "bg-muted font-medium"
                  : "text-muted-foreground hover:bg-muted/50"
              )}
            >
              90 days
            </button>
          </div>

          <div className="relative" ref={datePopoverRef}>
            <button
              onClick={() => setIsDateOpen(!isDateOpen)}
              className={cn(
                "flex items-center gap-1.5 border rounded-md px-2.5 py-1.5 text-xs transition-colors",
                appliedRange
                  ? "border-primary/40 bg-primary-soft text-foreground font-medium"
                  : "text-muted-foreground hover:bg-muted/50"
              )}
            >
              <Calendar className="h-3.5 w-3.5" />
              {appliedRange?.start && appliedRange?.end
                ? `${appliedRange.start} – ${appliedRange.end}`
                : "Custom"}
            </button>

            {isDateOpen && (
              <div className="absolute top-full mt-1.5 end-0 bg-background border rounded-lg shadow-lg p-3 z-50 w-[260px]">
                <div className="flex flex-col gap-2">
                  <div className="flex items-center gap-2">
                    <label className="text-xs text-muted-foreground w-8 shrink-0">From</label>
                    <input
                      type="date"
                      value={customStart}
                      onChange={(e) => { setCustomStart(e.target.value); setDateError(null) }}
                      className="flex-1 text-xs border rounded-md px-2 py-1 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="text-xs text-muted-foreground w-8 shrink-0">To</label>
                    <input
                      type="date"
                      value={customEnd}
                      onChange={(e) => { setCustomEnd(e.target.value); setDateError(null) }}
                      className="flex-1 text-xs border rounded-md px-2 py-1 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring"
                    />
                  </div>
                  {dateError && (
                    <p className="text-xs text-red-500">{dateError}</p>
                  )}
                  <div className="flex gap-2 mt-0.5 pt-2 border-t">
                    <Button variant="default" size="sm" className="h-6 px-3 text-xs flex-1" onClick={applyCustomRange}>
                      Apply
                    </Button>
                    {appliedRange && (
                      <Button variant="outline" size="sm" className="h-6 px-3 text-xs" onClick={clearCustomRange}>
                        Clear
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>

          <Button variant="outline" size="sm" className="h-8 gap-2 text-xs">
            <Download className="h-3.5 w-3.5" />
            Export
          </Button>
        </div>
      </header>

      <Tabs
        value={activeTab}
        onValueChange={handleTabChange}
        className="w-full flex flex-col flex-1 min-h-0"
      >
        <div className="flex flex-col bg-background z-20 px-6 pt-4 pb-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {activeDetailId ? (
                <StatsBreadcrumb items={breadcrumbItems} />
              ) : (
                <h2 className="text-2xl font-semibold tracking-tight">Usage</h2>
              )}
            </div>
            <TabsList className="ml-auto">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="rag">RAG</TabsTrigger>
              <TabsTrigger value="agents">Agents</TabsTrigger>
              <TabsTrigger value="resources">Resources</TabsTrigger>
            </TabsList>
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-auto">
          {loading ? (
            <LoadingState />
          ) : error ? (
            <ErrorState message={error} onRetry={() => loadStats(activeTab)} />
          ) : (
            <div>
              {/* ── OVERVIEW ── */}
              <TabsContent value="overview" className="mt-0 border-none p-0 focus-visible:ring-0">
                {overview && (
                  activeDetailId ? (
                    <div className="px-6 py-4">
                      <MetricDetailPanel
                        tab="overview"
                        detailId={activeDetailId}
                        overview={overview}
                        rangeDates={rangeDates}
                      />
                    </div>
                  ) : (
                    <div className="flex flex-col lg:flex-row lg:items-start gap-6 px-6 py-4">
                      <div className="flex-1 min-w-0">
                        <div className="space-y-6">
                          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 items-start">
                            <MetricBlock
                              title="Users"
                              value={formatCompact(overview.total_users)}
                              subValue={`${formatCompact(overview.new_users)} new`}
                              icon={Users}
                              onClick={() => setDetail("overview.users")}
                            />
                            <MetricBlock
                              title="Active Users"
                              value={formatCompact(overview.active_users)}
                              subValue={`${formatCompact(overview.total_users)} total`}
                              icon={Activity}
                              onClick={() => setDetail("overview.users")}
                            />
                            <MetricBlock
                              title="Messages"
                              value={formatCompact(overview.total_messages)}
                              subValue={`${overview.avg_messages_per_chat.toFixed(1)} avg / chat`}
                              icon={MessageSquare}
                              onClick={() => setDetail("overview.messages")}
                            />
                            <MetricBlock
                              title="Chats"
                              value={formatCompact(overview.total_chats)}
                              subValue={`${formatCompact(overview.total_users)} users`}
                              icon={MessageSquare}
                              onClick={() => setDetail("overview.messages")}
                            />
                            <MetricBlock
                              title="Tokens"
                              value={`${(overview.total_tokens / 1000).toFixed(1)}K`}
                              subValue={`$${overview.estimated_spend_usd.toFixed(2)} spend`}
                              icon={Cpu}
                              onClick={() => setDetail("overview.tokens")}
                            />
                            <MetricBlock
                              title="Spend"
                              value={`$${overview.estimated_spend_usd.toFixed(2)}`}
                              subValue={`${(overview.total_tokens / 1000).toFixed(1)}K tokens`}
                              icon={Server}
                              onClick={() => setDetail("overview.spend")}
                            />
                            <MetricBlock
                              title="Agent Runs"
                              value={formatCompact(overview.agent_runs)}
                              subValue={`${formatCompact(overview.agent_runs_failed)} failed`}
                              icon={Activity}
                              onClick={() => setDetail("overview.agentRuns")}
                            />
                            <MetricBlock
                              title="Pipeline Jobs"
                              value={formatCompact(overview.pipeline_jobs)}
                              subValue={`${formatCompact(overview.pipeline_jobs_failed)} failed`}
                              icon={Wrench}
                              onClick={() => setDetail("overview.pipelineJobs")}
                            />
                          </div>
                          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 items-start">
                            <GraphCard
                              title="Daily Active Users"
                              value={formatCompact(overview.active_users)}
                              subValue="Active in period"
                              periodLabel={periodLabel}
                              data={overviewDailyActiveFilled}
                              color="#10b981"
                              onClick={() => setDetail("overview.users")}
                            />
                            <GraphCard
                              title="Spend Trend"
                              value={`$${overview.estimated_spend_usd.toFixed(2)}`}
                              subValue="Estimated spend"
                              periodLabel={periodLabel}
                              data={overviewSpendFilled}
                              color="#f59e0b"
                              onClick={() => setDetail("overview.spend")}
                            />
                            <GraphCard
                              title="Token Usage"
                              value={`${(overview.total_tokens / 1000).toFixed(1)}K`}
                              subValue="Tokens used"
                              periodLabel={periodLabel}
                              data={overviewTokensFilled}
                              color="#8b5cf6"
                              onClick={() => setDetail("overview.tokens")}
                            />
                          </div>
                        </div>
                      </div>

                      <aside className="w-full lg:w-72 shrink-0 lg:sticky lg:top-0 flex flex-col gap-4 lg:border-l lg:border-border/60 lg:pl-4">
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <h3 className="text-sm font-medium">Token Usage</h3>
                            <span className="text-xs text-muted-foreground">{periodLabel}</span>
                          </div>
                          <p className="text-xl font-semibold mb-3">{(overview.total_tokens / 1000).toFixed(1)}K</p>
                          <BarChart data={overviewTokensFilled} height={140} color="#8b5cf6" />
                        </div>
                        <div>
                          <h3 className="text-sm font-medium mb-3">Period Summary</h3>
                          <div className="space-y-2.5 text-sm">
                            <SummaryRow label="Total chats" value={formatCompact(overview.total_chats)} />
                            <SummaryRow
                              label="Avg msg / user"
                              value={overview.total_users ? (overview.total_messages / overview.total_users).toFixed(1) : "—"}
                            />
                            <SummaryRow label="Pipeline jobs" value={formatCompact(overview.pipeline_jobs)} />
                            <StatusRow
                              label="Agent success"
                              rate={overview.agent_runs ? (1 - overview.agent_runs_failed / overview.agent_runs) * 100 : 100}
                            />
                          </div>
                        </div>
                      </aside>
                    </div>
                  )
                )}
              </TabsContent>

              {/* ── RAG ── */}
              <TabsContent value="rag" className="mt-0 border-none p-0 focus-visible:ring-0">
                {rag && (
                  activeDetailId ? (
                    <div className="px-6 py-4">
                      <MetricDetailPanel
                        tab="rag"
                        detailId={activeDetailId}
                        rag={rag}
                        rangeDates={rangeDates}
                      />
                    </div>
                  ) : (
                    <div className="flex flex-col lg:flex-row lg:items-start gap-6 px-6 py-4">
                      <div className="flex-1 min-w-0">
                        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3 items-start">
                          <MetricBlock
                            title="Pipelines"
                            value={formatCompact(rag.pipeline_count)}
                            subValue={`${formatCompact(rag.top_pipelines.length)} active`}
                            icon={Activity}
                            onClick={() => setDetail("rag.pipelines")}
                          />
                          <MetricBlock
                            title="Failures"
                            value={formatCompact(ragFailureCount)}
                            subValue={`${formatCompact(rag.recent_failed_jobs.length)} recent`}
                            icon={AlertCircle}
                            onClick={() => setDetail("rag.failures")}
                          />
                          <MetricBlock
                            title="Knowledge Stores"
                            value={formatCompact(rag.knowledge_store_count)}
                            subValue={`${formatCompact(rag.total_chunks)} chunks`}
                            icon={Database}
                            onClick={() => setDetail("rag.stores")}
                          />
                        </div>
                        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 mt-4">
                          <GraphCard
                            title="Pipeline Jobs"
                            value={formatCompact(ragTotalJobs)}
                            subValue="Last period"
                            periodLabel={periodLabel}
                            data={ragJobsByDayFilled}
                            color="#8b5cf6"
                            onClick={() => setDetail("rag.jobs")}
                          />
                          <GraphCard
                            title="Jobs Rolling Avg"
                            value={ragJobsRollingAvg.length
                              ? ragJobsRollingAvg[ragJobsRollingAvg.length - 1].value.toFixed(1)
                              : "0"}
                            subValue="7-day rolling average"
                            periodLabel={periodLabel}
                            data={ragJobsRollingAvg}
                            color="#10b981"
                            onClick={() => setDetail("rag.jobs")}
                          />
                        </div>
                      </div>

                      <aside className="w-full lg:w-72 shrink-0 lg:sticky lg:top-0 flex flex-col gap-4 lg:border-l lg:border-border/60 lg:pl-4">
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <h3 className="text-sm font-medium">Pipeline Jobs</h3>
                            <span className="text-xs text-muted-foreground">{periodLabel}</span>
                          </div>
                          <p className="text-xl font-semibold mb-3">{formatCompact(ragTotalJobs)}</p>
                          <BarChart data={ragJobsByDayFilled} height={140} color="#8b5cf6" />
                        </div>
                        <div>
                          <h3 className="text-sm font-medium mb-3">Job Health</h3>
                          <div className="space-y-2.5 text-sm">
                            <SummaryRow label="Avg duration" value={formatDuration(rag.avg_job_duration_ms)} />
                            <SummaryRow label="P95 duration" value={formatDuration(rag.p95_job_duration_ms)} />
                            <SummaryRow label="Recent jobs" value={formatCompact(rag.recent_jobs.length)} />
                            <StatusRow
                              label="Success rate"
                              rate={ragTotalJobs ? (1 - ragFailureCount / ragTotalJobs) * 100 : 100}
                            />
                          </div>
                        </div>
                      </aside>
                    </div>
                  )
                )}
              </TabsContent>

              {/* ── AGENTS ── */}
              <TabsContent value="agents" className="mt-0 border-none p-0 focus-visible:ring-0">
                {agents && (
                  activeDetailId ? (
                    <div className="px-6 py-4">
                      <MetricDetailPanel
                        tab="agents"
                        detailId={activeDetailId}
                        agents={agents}
                        rangeDates={rangeDates}
                      />
                    </div>
                  ) : (
                    <div className="flex flex-col lg:flex-row lg:items-start gap-6 px-6 py-4">
                      <div className="flex-1 min-w-0">
                        <div className="space-y-6">
                          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 items-start">
                            <MetricBlock
                              title="Runs"
                              value={formatCompact(agents.total_runs)}
                              subValue={`${agents.failure_rate.toFixed(1)}% failure`}
                              icon={Activity}
                              onClick={() => setDetail("agents.runs")}
                            />
                            <MetricBlock
                              title="Failures"
                              value={formatCompact(agents.total_failed)}
                              subValue={`${formatCompact(agents.recent_failures.length)} recent`}
                              icon={AlertCircle}
                              onClick={() => setDetail("agents.failures")}
                            />
                            <MetricBlock
                              title="Failure Rate"
                              value={`${agents.failure_rate.toFixed(1)}%`}
                              subValue={`${formatCompact(agents.total_failed)} failed`}
                              icon={AlertCircle}
                              onClick={() => setDetail("agents.failures")}
                            />
                            <MetricBlock
                              title="Agents"
                              value={formatCompact(agents.agent_count)}
                              subValue="Active agents"
                              icon={Users}
                              onClick={() => setDetail("agents.runs")}
                            />
                            <MetricBlock
                              title="Tokens Used"
                              value={formatCompact(agents.tokens_used_total)}
                              subValue="Total tokens"
                              icon={Cpu}
                              onClick={() => setDetail("agents.tokens")}
                            />
                            <MetricBlock
                              title="Avg Run Time"
                              value={formatDuration(agents.avg_run_duration_ms)}
                              subValue={`P95 ${formatDuration(agents.p95_run_duration_ms)}`}
                              icon={Timer}
                              onClick={() => setDetail("agents.runs")}
                            />
                            <MetricBlock
                              title="P95 Run Time"
                              value={formatDuration(agents.p95_run_duration_ms)}
                              subValue="P95 duration"
                              icon={Timer}
                              onClick={() => setDetail("agents.runs")}
                            />
                            <MetricBlock
                              title="Queue Time"
                              value={formatDuration(agents.avg_queue_time_ms)}
                              subValue="Avg queue"
                              icon={Timer}
                              onClick={() => setDetail("agents.queueTime")}
                            />
                          </div>
                          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 items-start">
                            <GraphCard
                              title="Run Trend"
                              value={formatCompact(agents.total_runs)}
                              subValue="Runs by day"
                              periodLabel={periodLabel}
                              data={agentsRunsFilled}
                              color="#8b5cf6"
                              onClick={() => setDetail("agents.runs")}
                            />
                            <GraphCard
                              title="Tokens by Day"
                              value={formatCompact(agents.tokens_used_total)}
                              subValue="Tokens used"
                              periodLabel={periodLabel}
                              data={agentsTokensFilled}
                              color="#10b981"
                              onClick={() => setDetail("agents.tokens")}
                            />
                            <GraphCard
                              title="Runs Rolling Avg"
                              value={agentsRunsRollingAvg.length
                                ? agentsRunsRollingAvg[agentsRunsRollingAvg.length - 1].value.toFixed(1)
                                : "0"}
                              subValue="7-day rolling average"
                              periodLabel={periodLabel}
                              data={agentsRunsRollingAvg}
                              color="#f97316"
                              onClick={() => setDetail("agents.runs")}
                            />
                          </div>
                        </div>
                      </div>

                      <aside className="w-full lg:w-72 shrink-0 lg:sticky lg:top-0 flex flex-col gap-4 lg:border-l lg:border-border/60 lg:pl-4">
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <h3 className="text-sm font-medium">Agent Runs</h3>
                            <span className="text-xs text-muted-foreground">{periodLabel}</span>
                          </div>
                          <p className="text-xl font-semibold mb-3">{formatCompact(agents.total_runs)}</p>
                          <BarChart data={agentsRunsFilled} height={140} color="#8b5cf6" />
                        </div>
                        <div>
                          <h3 className="text-sm font-medium mb-3">Performance</h3>
                          <div className="space-y-2.5 text-sm">
                            <SummaryRow label="Avg queue time" value={formatDuration(agents.avg_queue_time_ms)} />
                            <SummaryRow label="Avg run duration" value={formatDuration(agents.avg_run_duration_ms)} />
                            <SummaryRow label="P95 duration" value={formatDuration(agents.p95_run_duration_ms)} />
                            <StatusRow label="Success rate" rate={100 - agents.failure_rate} />
                          </div>
                        </div>
                      </aside>
                    </div>
                  )
                )}
              </TabsContent>

              {/* ── RESOURCES ── */}
              <TabsContent value="resources" className="mt-0 border-none p-0 focus-visible:ring-0">
                {resources && (
                  activeDetailId ? (
                    <div className="px-6 py-4">
                      <MetricDetailPanel
                        tab="resources"
                        detailId={activeDetailId}
                        resources={resources}
                        rangeDates={rangeDates}
                      />
                    </div>
                  ) : (
                    <div className="flex flex-col lg:flex-row lg:items-start gap-6 px-6 py-4">
                      <div className="flex-1 min-w-0">
                        <div className="space-y-6">
                          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 items-start">
                            <MetricBlock
                              title="Tools"
                              value={formatCompact(resources.tool_count)}
                              subValue={`${formatCompact(Object.keys(resources.tools_by_type).length)} types`}
                              icon={Wrench}
                              onClick={() => setDetail("resources.tools")}
                            />
                            <MetricBlock
                              title="Published Tools"
                              value={formatCompact(getRecordValue(resources.tools_by_status, ["published"]))}
                              subValue="Published"
                              icon={Wrench}
                              onClick={() => setDetail("resources.tools")}
                            />
                            <MetricBlock
                              title="Models"
                              value={formatCompact(resources.model_count)}
                              subValue={`${formatCompact(Object.keys(resources.models_by_capability).length)} capabilities`}
                              icon={Cpu}
                              onClick={() => setDetail("resources.models")}
                            />
                            <MetricBlock
                              title="Artifacts"
                              value={formatCompact(resources.artifact_count)}
                              subValue={`${formatCompact(Object.keys(resources.artifacts_by_category).length)} categories`}
                              icon={Database}
                              onClick={() => setDetail("resources.artifacts")}
                            />
                            <MetricBlock
                              title="Active Artifacts"
                              value={formatCompact(getRecordValue(resources.artifacts_by_active, ["active"]))}
                              subValue="Active"
                              icon={Database}
                              onClick={() => setDetail("resources.artifacts")}
                            />
                            <MetricBlock
                              title="Providers"
                              value={formatCompact(resources.provider_bindings_by_provider.length)}
                              subValue="Bindings"
                              icon={Server}
                              onClick={() => setDetail("resources.providers")}
                            />
                          </div>
                          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 items-start">
                            <GraphCard
                              title="Tools by Type"
                              value={formatCompact(Object.keys(resources.tools_by_type).length)}
                              subValue="Tool categories"
                              data={resourceToolsByTypeChart}
                              color="#06b6d4"
                              showLabels={false}
                              onClick={() => setDetail("resources.tools")}
                            />
                            <GraphCard
                              title="Models by Capability"
                              value={formatCompact(Object.keys(resources.models_by_capability).length)}
                              subValue="Capability groups"
                              data={resourceModelsByCapabilityChart}
                              color="#8b5cf6"
                              showLabels={false}
                              onClick={() => setDetail("resources.models")}
                            />
                            <GraphCard
                              title="Artifacts by Category"
                              value={formatCompact(Object.keys(resources.artifacts_by_category).length)}
                              subValue="Artifact categories"
                              data={resourceArtifactsByCategoryChart.length
                                ? resourceArtifactsByCategoryChart
                                : emptyRangeSeries}
                              color="#f97316"
                              showLabels={false}
                              onClick={() => setDetail("resources.artifacts")}
                            />
                          </div>
                        </div>
                      </div>

                      <aside className="w-full lg:w-72 shrink-0 lg:sticky lg:top-0 flex flex-col gap-4 lg:border-l lg:border-border/60 lg:pl-4">
                        <div>
                          <h3 className="text-sm font-medium mb-3">Resource Health</h3>
                          <div className="space-y-2.5 text-sm">
                            <div className="flex items-center justify-between">
                              <span className="text-muted-foreground">Published tools</span>
                              <Badge variant="outline">
                                {getRecordValue(resources.tools_by_status, ["published"])}
                              </Badge>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-muted-foreground">Active artifacts</span>
                              <Badge variant="outline">
                                {getRecordValue(resources.artifacts_by_active, ["active"])}
                              </Badge>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-muted-foreground">Provider bindings</span>
                              <Badge variant="outline">{resources.provider_bindings_by_provider.length}</Badge>
                            </div>
                          </div>
                        </div>
                        <div>
                          <h3 className="text-sm font-medium mb-3">Tools by Type</h3>
                          <div className="space-y-2.5 text-sm">
                            {Object.entries(resources.tools_by_type).map(([type, count]) => (
                              <SummaryRow
                                key={type}
                                label={type.charAt(0).toUpperCase() + type.slice(1)}
                                value={count}
                              />
                            ))}
                          </div>
                        </div>
                      </aside>
                    </div>
                  )
                )}
              </TabsContent>
            </div>
          )}
        </div>
      </Tabs>
    </div>
  )
}
