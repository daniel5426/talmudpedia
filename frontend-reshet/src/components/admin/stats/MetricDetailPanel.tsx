"use client"

import { Badge } from "@/components/ui/badge"
import { BarChart } from "@/components/admin/stats/BarChart"
import {
  type StatsSection,
  type AdminStatsOverview,
  type AdminStatsRAG,
  type AdminStatsAgents,
  type AdminStatsResources,
  type DailyDataPoint,
} from "@/services"

function formatDuration(ms?: number | null) {
  if (!ms && ms !== 0) return "—"
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function fillDailyRange(data: DailyDataPoint[], rangeDates?: string[]) {
  if (!rangeDates?.length) return data
  const lookup = new Map(data.map((item) => [item.date, item.value]))
  return rangeDates.map((date) => ({
    date,
    value: lookup.get(date) ?? 0,
  }))
}

function BreakdownList({
  title,
  data,
}: {
  title: string;
  data: Record<string, number>;
}) {
  const entries = Object.entries(data)
  return (
    <div className="border rounded-lg p-4">
      <h4 className="text-sm font-medium mb-3">{title}</h4>
      {entries.length ? (
        <div className="space-y-2 text-sm">
          {entries.map(([key, value]) => (
            <div key={key} className="flex items-center justify-between">
              <span className="capitalize">{key}</span>
              <span className="font-mono">{value}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-sm text-muted-foreground">No data</div>
      )}
    </div>
  )
}

function SimpleTable({
  title,
  rows,
}: {
  title: string;
  rows: Array<{ label: string; value: string | number; meta?: string }>;
}) {
  return (
    <div className="border rounded-lg p-4">
      <h4 className="text-sm font-medium mb-3">{title}</h4>
      {rows.length ? (
        <div className="space-y-2 text-sm">
          {rows.map((row, index) => (
            <div key={`${row.label}-${index}`} className="flex items-center justify-between">
              <div className="flex flex-col">
                <span className="font-medium">{row.label}</span>
                {row.meta && <span className="text-xs text-muted-foreground">{row.meta}</span>}
              </div>
              <span className="font-mono">{row.value}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-sm text-muted-foreground">No data</div>
      )}
    </div>
  )
}

export function MetricDetailPanel({
  tab,
  detailId,
  overview,
  rag,
  agents,
  resources,
  rangeDates,
}: {
  tab: StatsSection;
  detailId: string;
  overview?: AdminStatsOverview | null;
  rag?: AdminStatsRAG | null;
  agents?: AdminStatsAgents | null;
  resources?: AdminStatsResources | null;
  rangeDates?: string[];
}) {
  if (tab === "overview" && overview) {
    if (detailId === "overview.users") {
      return (
        <div className="space-y-6">
          <div className="border rounded-lg p-6">
            <h3 className="text-sm font-medium mb-4">Daily Active Users</h3>
            <BarChart
              data={fillDailyRange(overview.daily_active_users, rangeDates)}
              height={180}
              color="#10b981"
            />
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <SimpleTable
              title="Top Users"
              rows={overview.top_users.map((user) => ({
                label: user.email,
                value: user.count,
                meta: user.full_name || undefined,
              }))}
            />
            <BreakdownList title="Messages by Role" data={overview.messages_by_role} />
          </div>
        </div>
      )
    }

    if (detailId === "overview.messages") {
      return (
        <div className="space-y-6">
          <BreakdownList title="Messages by Role" data={overview.messages_by_role} />
          <SimpleTable
            title="Top Users by Messages"
            rows={overview.top_users.map((user) => ({
              label: user.email,
              value: user.count,
              meta: user.full_name || undefined,
            }))}
          />
        </div>
      )
    }

    if (detailId === "overview.tokens") {
      return (
        <div className="space-y-6">
          <div className="border rounded-lg p-6">
            <h3 className="text-sm font-medium mb-4">Token Usage</h3>
            <BarChart
              data={fillDailyRange(overview.tokens_by_day, rangeDates)}
              height={200}
              color="#8b5cf6"
            />
          </div>
          <SimpleTable
            title="Top Models"
            rows={overview.top_models.map((model) => ({
              label: model.model_name,
              value: `${model.token_count} tokens`,
              meta: `${model.message_count} messages`,
            }))}
          />
        </div>
      )
    }

    if (detailId === "overview.spend") {
      return (
        <div className="space-y-6">
          <div className="border rounded-lg p-6">
            <h3 className="text-sm font-medium mb-4">Spend Trend</h3>
            <BarChart
              data={fillDailyRange(overview.spend_by_day, rangeDates)}
              height={200}
              color="#f59e0b"
            />
          </div>
          <SimpleTable
            title="Top Models by Tokens"
            rows={overview.top_models.map((model) => ({
              label: model.model_name,
              value: `${model.token_count} tokens`,
              meta: `${model.message_count} messages`,
            }))}
          />
        </div>
      )
    }

    if (detailId === "overview.agentRuns") {
      return (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <SimpleTable
            title="Agent Runs"
            rows={[
              { label: "Runs", value: overview.agent_runs },
              { label: "Failures", value: overview.agent_runs_failed },
            ]}
          />
          <SimpleTable
            title="Pipeline Jobs"
            rows={[
              { label: "Jobs", value: overview.pipeline_jobs },
              { label: "Failures", value: overview.pipeline_jobs_failed },
            ]}
          />
        </div>
      )
    }

    if (detailId === "overview.pipelineJobs") {
      const failureRate = overview.pipeline_jobs
        ? (overview.pipeline_jobs_failed / overview.pipeline_jobs) * 100
        : 0
      return (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <SimpleTable
            title="Pipeline Jobs"
            rows={[
              { label: "Jobs", value: overview.pipeline_jobs },
              { label: "Failures", value: overview.pipeline_jobs_failed },
              { label: "Failure rate", value: `${failureRate.toFixed(1)}%` },
            ]}
          />
          <SimpleTable
            title="Agent Runs"
            rows={[
              { label: "Runs", value: overview.agent_runs },
              { label: "Failures", value: overview.agent_runs_failed },
            ]}
          />
        </div>
      )
    }
  }

  if (tab === "rag" && rag) {
    if (detailId === "rag.stores") {
      return (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <BreakdownList title="Stores by Status" data={rag.stores_by_status} />
          <SimpleTable
            title="Knowledge Stores"
            rows={rag.knowledge_stores.map((store) => ({
              label: store.name,
              value: `${store.chunk_count} chunks`,
              meta: store.status,
            }))}
          />
        </div>
      )
    }

    if (detailId === "rag.pipelines") {
      return (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <BreakdownList title="Pipelines by Type" data={rag.pipelines_by_type} />
          <SimpleTable
            title="Top Pipelines"
            rows={rag.top_pipelines.map((pipeline) => ({
              label: pipeline.name,
              value: `${pipeline.run_count} runs`,
              meta: `${pipeline.failure_rate.toFixed(1)}% failure`,
            }))}
          />
        </div>
      )
    }

    if (detailId === "rag.jobs") {
      return (
        <div className="space-y-6">
          <div className="border rounded-lg p-6">
            <h3 className="text-sm font-medium mb-4">Jobs Trend</h3>
            <BarChart
              data={fillDailyRange(rag.jobs_by_day, rangeDates)}
              height={180}
              color="#8b5cf6"
            />
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <SimpleTable
              title="Durations"
              rows={[
                { label: "Average", value: formatDuration(rag.avg_job_duration_ms) },
                { label: "P95", value: formatDuration(rag.p95_job_duration_ms) },
              ]}
            />
            <SimpleTable
              title="Recent Jobs"
              rows={rag.recent_jobs.map((job) => ({
                label: job.pipeline_name,
                value: job.status,
              }))}
            />
          </div>
        </div>
      )
    }

    if (detailId === "rag.failures") {
      return (
        <div className="space-y-6">
          <BreakdownList title="Jobs by Status" data={rag.jobs_by_status} />
          <div className="border rounded-lg p-4">
            <h4 className="text-sm font-medium mb-3">Recent Failed Jobs</h4>
            {rag.recent_failed_jobs.length ? (
              <div className="space-y-2 text-sm">
                {rag.recent_failed_jobs.map((job) => (
                  <div key={job.id} className="flex items-center justify-between">
                    <div className="flex flex-col">
                      <span className="font-medium">{job.pipeline_name}</span>
                      {job.error_message && (
                        <span className="text-xs text-muted-foreground line-clamp-1">{job.error_message}</span>
                      )}
                    </div>
                    <Badge variant="outline">{job.status}</Badge>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">No recent failures</div>
            )}
          </div>
        </div>
      )
    }
  }

  if (tab === "agents" && agents) {
    if (detailId === "agents.runs") {
      return (
        <div className="space-y-6">
          <div className="border rounded-lg p-6">
            <h3 className="text-sm font-medium mb-4">Run Trend</h3>
            <BarChart
              data={fillDailyRange(agents.runs_by_day, rangeDates)}
              height={180}
              color="#8b5cf6"
            />
          </div>
          <BreakdownList title="Runs by Status" data={agents.runs_by_status} />
        </div>
      )
    }

    if (detailId === "agents.failures") {
      return (
        <div className="space-y-6">
          <SimpleTable
            title="Failure Rates"
            rows={[
              { label: "Failure rate", value: `${agents.failure_rate.toFixed(1)}%` },
              { label: "Total failures", value: agents.total_failed },
            ]}
          />
          <div className="border rounded-lg p-4">
            <h4 className="text-sm font-medium mb-3">Recent Failures</h4>
            {agents.recent_failures.length ? (
              <div className="space-y-2 text-sm">
                {agents.recent_failures.map((failure) => (
                  <div key={failure.run_id} className="flex items-center justify-between">
                    <div className="flex flex-col">
                      <span className="font-medium">{failure.agent_name}</span>
                      {failure.error_message && (
                        <span className="text-xs text-muted-foreground line-clamp-1">
                          {failure.error_message}
                        </span>
                      )}
                    </div>
                    <Badge variant="outline">{failure.status}</Badge>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">No recent failures</div>
            )}
          </div>
        </div>
      )
    }

    if (detailId === "agents.tokens") {
      return (
        <div className="space-y-6">
          <div className="border rounded-lg p-6">
            <h3 className="text-sm font-medium mb-4">Tokens by Day</h3>
            <BarChart
              data={fillDailyRange(agents.tokens_by_day, rangeDates)}
              height={180}
              color="#10b981"
            />
          </div>
          <SimpleTable
            title="Top Agents by Tokens"
            rows={agents.top_agents_by_tokens.map((agent) => ({
              label: agent.name,
              value: `${agent.tokens_used} tokens`,
              meta: `${agent.run_count} runs`,
            }))}
          />
        </div>
      )
    }

    if (detailId === "agents.queueTime") {
      return (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <SimpleTable
            title="Queue Time"
            rows={[
              { label: "Average", value: formatDuration(agents.avg_queue_time_ms) },
              { label: "Avg run duration", value: formatDuration(agents.avg_run_duration_ms) },
              { label: "P95 run duration", value: formatDuration(agents.p95_run_duration_ms) },
            ]}
          />
          <SimpleTable
            title="Top Users by Runs"
            rows={agents.top_users_by_runs.map((user) => ({
              label: user.email,
              value: user.count,
              meta: user.full_name || undefined,
            }))}
          />
        </div>
      )
    }
  }

  if (tab === "resources" && resources) {
    if (detailId === "resources.tools") {
      return (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <BreakdownList title="Tools by Status" data={resources.tools_by_status} />
          <BreakdownList title="Tools by Type" data={resources.tools_by_type} />
        </div>
      )
    }

    if (detailId === "resources.models") {
      return (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <BreakdownList title="Models by Capability" data={resources.models_by_capability} />
          <BreakdownList title="Models by Status" data={resources.models_by_status} />
        </div>
      )
    }

    if (detailId === "resources.artifacts") {
      return (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <BreakdownList title="Artifacts by Category" data={resources.artifacts_by_category} />
          <BreakdownList title="Artifacts by State" data={resources.artifacts_by_active} />
        </div>
      )
    }

    if (detailId === "resources.providers") {
      return (
        <SimpleTable
          title="Provider Bindings"
          rows={resources.provider_bindings_by_provider.map((provider) => ({
            label: provider.provider,
            value: provider.count,
          }))}
        />
      )
    }
  }

  return (
    <div className="text-sm text-muted-foreground">No detail data available.</div>
  )
}
