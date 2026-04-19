"use client"

import { useEffect, useState } from "react"
import {
  AlertCircle,
  Loader2,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { formatHttpErrorMessage } from "@/services/http"
import {
  settingsLimitsService,
  settingsProjectsService,
  SettingsLimit,
  SettingsProject,
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

export function LimitsSection() {
  const [orgLimit, setOrgLimit] = useState<SettingsLimit | null>(null)
  const [projects, setProjects] = useState<SettingsProject[]>([])
  const [projectSlug, setProjectSlug] = useState("")
  const [projectLimit, setProjectLimit] = useState<SettingsLimit | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [orgSaving, setOrgSaving] = useState(false)
  const [projectSaving, setProjectSaving] = useState(false)

  useEffect(() => {
    setLoading(true)
    void Promise.all([settingsLimitsService.getOrganizationLimits(), settingsProjectsService.listProjects()])
      .then(([limit, projectData]) => {
        setOrgLimit(limit)
        setProjects(projectData)
        if (projectData[0]) setProjectSlug(projectData[0].slug)
      })
      .catch((error) => setError(formatHttpErrorMessage(error, "Failed to load limits.")))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!projectSlug) return
    void settingsLimitsService
      .getProjectLimits(projectSlug)
      .then(setProjectLimit)
      .catch((error) => setError(formatHttpErrorMessage(error, "Failed to load project limits.")))
  }, [projectSlug])

  const saveOrgLimit = async () => {
    setOrgSaving(true)
    setError(null)
    try {
      const updated = await settingsLimitsService.updateOrganizationLimits({
        monthly_token_limit: orgLimit?.monthly_token_limit ?? null,
      })
      setOrgLimit(updated)
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to save organization limits."))
    } finally {
      setOrgSaving(false)
    }
  }

  const saveProjectLimit = async () => {
    if (!projectSlug) return
    setProjectSaving(true)
    setError(null)
    try {
      const updated = await settingsLimitsService.updateProjectLimits(projectSlug, {
        monthly_token_limit: projectLimit?.monthly_token_limit ?? null,
      })
      setProjectLimit(updated)
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to save project limits."))
    } finally {
      setProjectSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div>
        <h2 className="text-sm font-medium text-foreground">Limits</h2>
        <p className="text-xs text-muted-foreground/70 mt-0.5">
          Set monthly token limits at organization and project level.
        </p>
      </div>

      <ErrorBanner message={error} />

      {loading ? (
        <p className="text-xs text-muted-foreground py-8 text-center">Loading…</p>
      ) : (
        <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
          {/* ── Organization Limits ── */}
          <div className="space-y-4">
            <div className="border-b border-border/40 pb-2">
              <h3 className="text-sm font-semibold text-foreground">Organization</h3>
              <p className="text-xs text-muted-foreground/60 mt-0.5">
                Default monthly token limit for the organization.
              </p>
            </div>
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-muted-foreground">Monthly Token Limit</Label>
                <Input
                  type="number"
                  value={orgLimit?.monthly_token_limit ?? ""}
                  onChange={(event) =>
                    setOrgLimit((current) =>
                      current
                        ? { ...current, monthly_token_limit: event.target.value ? Number(event.target.value) : null }
                        : current
                    )
                  }
                  placeholder="No limit set"
                  className="h-9 max-w-xs"
                />
              </div>
              <Button size="sm" onClick={saveOrgLimit} disabled={orgSaving}>
                {orgSaving && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
                Save
              </Button>
            </div>
          </div>

          {/* ── Project Limits ── */}
          <div className="space-y-4">
            <div className="border-b border-border/40 pb-2">
              <h3 className="text-sm font-semibold text-foreground">Project Override</h3>
              <p className="text-xs text-muted-foreground/60 mt-0.5">
                Override the organization default for a specific project.
              </p>
            </div>
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-muted-foreground">Project</Label>
                <Select
                  value={projectSlug || "__none__"}
                  onValueChange={(value) => setProjectSlug(value === "__none__" ? "" : value)}
                >
                  <SelectTrigger className="h-9 max-w-xs">
                    <SelectValue placeholder="Project" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">Select project</SelectItem>
                    {projects.map((project) => (
                      <SelectItem key={project.id} value={project.slug}>
                        {project.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-muted-foreground">Monthly Token Limit</Label>
                <Input
                  type="number"
                  value={projectLimit?.monthly_token_limit ?? ""}
                  onChange={(event) =>
                    setProjectLimit((current) =>
                      current
                        ? { ...current, monthly_token_limit: event.target.value ? Number(event.target.value) : null }
                        : current
                    )
                  }
                  placeholder="Project override"
                  className="h-9 max-w-xs"
                />
                <p className="text-xs text-muted-foreground/50">
                  Effective limit: {projectLimit?.effective_monthly_token_limit ?? "Inherited / none"}
                </p>
              </div>
              <Button size="sm" onClick={saveProjectLimit} disabled={projectSaving || !projectSlug}>
                {projectSaving && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
                Save Override
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
