"use client"

import { useEffect, useState } from "react"
import { AlertCircle, Loader2 } from "lucide-react"

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
  const [projectId, setProjectId] = useState("")
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
        if (projectData[0]) setProjectId(projectData[0].id)
      })
      .catch((error) => setError(formatHttpErrorMessage(error, "Failed to load limits.")))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!projectId) return
    void settingsLimitsService
      .getProjectLimits(projectId)
      .then(setProjectLimit)
      .catch((error) => setError(formatHttpErrorMessage(error, "Failed to load project limits.")))
  }, [projectId])

  const saveOrgLimit = async () => {
    setOrgSaving(true)
    setError(null)
    try {
      setOrgLimit(
        await settingsLimitsService.updateOrganizationLimits({
          monthly_token_limit: orgLimit?.monthly_token_limit ?? null,
        })
      )
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to save organization limits."))
    } finally {
      setOrgSaving(false)
    }
  }

  const saveProjectLimit = async () => {
    if (!projectId) return
    setProjectSaving(true)
    setError(null)
    try {
      setProjectLimit(
        await settingsLimitsService.updateProjectLimits(projectId, {
          monthly_token_limit: projectLimit?.monthly_token_limit ?? null,
        })
      )
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to save project limits."))
    } finally {
      setProjectSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-sm font-medium text-foreground">Limits</h2>
        <p className="mt-0.5 text-xs text-muted-foreground/70">
          Set monthly token limits at organization and project level.
        </p>
      </div>

      <ErrorBanner message={error} />

      {loading ? (
        <p className="py-8 text-center text-xs text-muted-foreground">Loading…</p>
      ) : (
        <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
          <div className="space-y-4">
            <div className="border-b border-border/40 pb-2">
              <h3 className="text-sm font-semibold text-foreground">Organization</h3>
              <p className="mt-0.5 text-xs text-muted-foreground/60">
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
                        ? {
                            ...current,
                            monthly_token_limit: event.target.value ? Number(event.target.value) : null,
                          }
                        : current
                    )
                  }
                  placeholder="No limit set"
                  className="h-9 max-w-xs"
                />
              </div>
              <Button size="sm" onClick={saveOrgLimit} disabled={orgSaving}>
                {orgSaving && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                Save
              </Button>
            </div>
          </div>

          <div className="space-y-4">
            <div className="border-b border-border/40 pb-2">
              <h3 className="text-sm font-semibold text-foreground">Project Override</h3>
              <p className="mt-0.5 text-xs text-muted-foreground/60">
                Override the organization default for a specific project.
              </p>
            </div>
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-muted-foreground">Project</Label>
                <Select
                  value={projectId || "__none__"}
                  onValueChange={(value) => setProjectId(value === "__none__" ? "" : value)}
                >
                  <SelectTrigger className="h-9 max-w-xs">
                    <SelectValue placeholder="Project" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">Select project</SelectItem>
                    {projects.map((project) => (
                      <SelectItem key={project.id} value={project.id}>
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
                        ? {
                            ...current,
                            monthly_token_limit: event.target.value ? Number(event.target.value) : null,
                          }
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
              <Button size="sm" onClick={saveProjectLimit} disabled={projectSaving || !projectId}>
                {projectSaving && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                Save Override
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
