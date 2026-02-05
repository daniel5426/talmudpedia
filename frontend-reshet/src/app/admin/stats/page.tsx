"use client"

import { useEffect, useMemo, useState } from "react"
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

export default function AdminStatsPage() {
  const [activeTab, setActiveTab] = useState<StatsSection>("overview")
  const [days, setDays] = useState(7)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [customStart, setCustomStart] = useState("")
  const [customEnd, setCustomEnd] = useState("")
  const [appliedRange, setAppliedRange] = useState<{ start?: string; end?: string } | null>(null)

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
      setError("Start date must be before end date.")
      return
    }
    setAppliedRange({
      start: customStart || undefined,
      end: customEnd || undefined,
    })
  }

  const clearCustomRange = () => {
    setAppliedRange(null)
    setCustomStart("")
    setCustomEnd("")
  }

  const usePreset = (presetDays: number) => {
    setDays(presetDays)
    setAppliedRange(null)
    setCustomStart("")
    setCustomEnd("")
  }

  const ragFailureCount = useMemo(() => {
    if (!rag) return 0
    return (
      rag.jobs_by_status.FAILED ||
      rag.jobs_by_status.failed ||
      0
    )
  }, [rag])

  const breadcrumbItems = useMemo(() => {
    if (!activeDetailId) return []
    return [
      { label: "Usage", onClick: () => setDetail(null) },
      { label: activeTab.charAt(0).toUpperCase() + activeTab.slice(1), onClick: () => setDetail(null) },
      { label: detailLabels[activeDetailId] || "Detail", active: true },
    ]
  }, [activeDetailId, activeTab])

  return (
    <div className="flex flex-col h-full w-full overflow-hidden">
      <header className="h-12 border-b flex items-center justify-between px-4 bg-background z-30 shrink-0">
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
          <div className="flex items-center gap-2 border rounded-md px-2 py-1.5">
            <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
            <input
              type="date"
              value={customStart}
              onChange={(event) => setCustomStart(event.target.value)}
              className="bg-transparent text-xs text-muted-foreground focus:outline-none"
            />
            <span className="text-xs text-muted-foreground">to</span>
            <input
              type="date"
              value={customEnd}
              onChange={(event) => setCustomEnd(event.target.value)}
              className="bg-transparent text-xs text-muted-foreground focus:outline-none"
            />
            <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={applyCustomRange}>
              Apply
            </Button>
            {appliedRange && (
              <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={clearCustomRange}>
                Clear
              </Button>
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
          <div className="flex items-center justify-between mb-2">
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
            <div className="mt-4">
              <TabsContent value="overview" className="mt-0 border-none p-0 focus-visible:ring-0">
                {overview && (
                  <div className="p-6 space-y-6">
                    {activeDetailId ? (
                      <MetricDetailPanel tab="overview" detailId={activeDetailId} overview={overview} />
                    ) : (
                      <>
                        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
                          <MetricBlock
                            title="Users"
                            value={formatCompact(overview.total_users)}
                            subValue={`${formatCompact(overview.new_users)} new`}
                            icon={Users}
                            sparkline={overview.daily_active_users}
                            onClick={() => setDetail("overview.users")}
                          />
                          <MetricBlock
                            title="Messages"
                            value={formatCompact(overview.total_messages)}
                            subValue={`${formatCompact(overview.total_chats)} chats`}
                            icon={MessageSquare}
                            onClick={() => setDetail("overview.messages")}
                          />
                          <MetricBlock
                            title="Tokens"
                            value={`${(overview.total_tokens / 1000).toFixed(1)}K`}
                            subValue={`$${overview.estimated_spend_usd.toFixed(2)} spend`}
                            icon={Cpu}
                            sparkline={overview.tokens_by_day}
                            onClick={() => setDetail("overview.tokens")}
                          />
                          <MetricBlock
                            title="Spend"
                            value={`$${overview.estimated_spend_usd.toFixed(2)}`}
                            subValue={`${(overview.total_tokens / 1000).toFixed(1)}K tokens`}
                            icon={Server}
                            sparkline={overview.spend_by_day}
                            onClick={() => setDetail("overview.spend")}
                          />
                          <MetricBlock
                            title="Agent Runs"
                            value={formatCompact(overview.agent_runs)}
                            subValue={`${formatCompact(overview.agent_runs_failed)} failed`}
                            icon={Activity}
                            onClick={() => setDetail("overview.agentRuns")}
                          />
                        </div>
                        <div className="border rounded-lg p-6">
                          <div className="flex items-center justify-between mb-4">
                            <div>
                              <h3 className="text-sm font-medium">Token Usage</h3>
                              <p className="text-2xl font-semibold mt-1">
                                {(overview.total_tokens / 1000).toFixed(1)}K tokens
                              </p>
                            </div>
                          </div>
                          <BarChart data={overview.tokens_by_day} height={200} color="#8b5cf6" />
                        </div>
                      </>
                    )}
                  </div>
                )}
              </TabsContent>

              <TabsContent value="rag" className="mt-0 border-none p-0 focus-visible:ring-0">
                {rag && (
                  <div className="p-6 space-y-6">
                    {activeDetailId ? (
                      <MetricDetailPanel tab="rag" detailId={activeDetailId} rag={rag} />
                    ) : (
                      <>
                        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                          <MetricBlock
                            title="Knowledge Stores"
                            value={formatCompact(rag.knowledge_store_count)}
                            subValue={`${formatCompact(rag.total_chunks)} chunks`}
                            icon={Database}
                            onClick={() => setDetail("rag.stores")}
                          />
                          <MetricBlock
                            title="Pipelines"
                            value={formatCompact(rag.pipeline_count)}
                            subValue={`${formatCompact(rag.top_pipelines.length)} active`}
                            icon={Activity}
                            onClick={() => setDetail("rag.pipelines")}
                          />
                          <MetricBlock
                            title="Jobs"
                            value={formatCompact(rag.jobs_by_day.reduce((acc, item) => acc + item.value, 0))}
                            subValue="Last period"
                            icon={Cpu}
                            sparkline={rag.jobs_by_day}
                            onClick={() => setDetail("rag.jobs")}
                          />
                          <MetricBlock
                            title="Failures"
                            value={formatCompact(ragFailureCount)}
                            subValue={`${formatCompact(rag.recent_failed_jobs.length)} recent`}
                            icon={AlertCircle}
                            onClick={() => setDetail("rag.failures")}
                          />
                        </div>
                        <div className="border rounded-lg p-6">
                          <h3 className="text-sm font-medium mb-4">Pipeline Jobs</h3>
                          <BarChart data={rag.jobs_by_day} height={150} color="#8b5cf6" />
                        </div>
                      </>
                    )}
                  </div>
                )}
              </TabsContent>

              <TabsContent value="agents" className="mt-0 border-none p-0 focus-visible:ring-0">
                {agents && (
                  <div className="p-6 space-y-6">
                    {activeDetailId ? (
                      <MetricDetailPanel tab="agents" detailId={activeDetailId} agents={agents} />
                    ) : (
                      <>
                        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                          <MetricBlock
                            title="Runs"
                            value={formatCompact(agents.total_runs)}
                            subValue={`${agents.failure_rate.toFixed(1)}% failure`}
                            icon={Activity}
                            sparkline={agents.runs_by_day}
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
                            title="Tokens"
                            value={formatCompact(agents.tokens_used_total)}
                            subValue="Usage tokens"
                            icon={Cpu}
                            sparkline={agents.tokens_by_day}
                            onClick={() => setDetail("agents.tokens")}
                          />
                          <MetricBlock
                            title="Queue Time"
                            value={formatDuration(agents.avg_queue_time_ms)}
                            subValue={`P95 ${formatDuration(agents.p95_run_duration_ms)}`}
                            icon={Timer}
                            onClick={() => setDetail("agents.queueTime")}
                          />
                        </div>
                        <div className="border rounded-lg p-6">
                          <h3 className="text-sm font-medium mb-4">Agent Runs</h3>
                          <BarChart data={agents.runs_by_day} height={150} color="#8b5cf6" />
                        </div>
                      </>
                    )}
                  </div>
                )}
              </TabsContent>

              <TabsContent value="resources" className="mt-0 border-none p-0 focus-visible:ring-0">
                {resources && (
                  <div className="p-6 space-y-6">
                    {activeDetailId ? (
                      <MetricDetailPanel tab="resources" detailId={activeDetailId} resources={resources} />
                    ) : (
                      <>
                        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                          <MetricBlock
                            title="Tools"
                            value={formatCompact(resources.tool_count)}
                            subValue={`${formatCompact(Object.keys(resources.tools_by_type).length)} types`}
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
                            title="Providers"
                            value={formatCompact(resources.provider_bindings_by_provider.length)}
                            subValue="Bindings"
                            icon={Server}
                            onClick={() => setDetail("resources.providers")}
                          />
                        </div>
                        <div className="border rounded-lg p-6">
                          <h3 className="text-sm font-medium mb-4">Resource Health</h3>
                          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                            <div className="flex items-center justify-between rounded-lg border p-4 text-sm">
                              <span>Active tools</span>
                              <Badge variant="outline">{resources.tools_by_status.PUBLISHED || 0}</Badge>
                            </div>
                            <div className="flex items-center justify-between rounded-lg border p-4 text-sm">
                              <span>Active artifacts</span>
                              <Badge variant="outline">{resources.artifacts_by_active.active || 0}</Badge>
                            </div>
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </TabsContent>
            </div>
          )}
        </div>
      </Tabs>
    </div>
  )
}
