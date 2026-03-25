"use client"

import { Bot, ChevronDown, Database, Loader2, PanelLeft, Play, Plus, RefreshCw, Save, Upload, Wrench } from "lucide-react"

import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { ArtifactVersionsDropdown } from "@/components/admin/artifacts/ArtifactVersionsDropdown"
import { CustomBreadcrumb, type BreadcrumbItemProps } from "@/components/ui/custom-breadcrumb"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { KesherLogo } from "@/components/kesher-logo"
import { cn } from "@/lib/utils"
import type { ArtifactKind, ArtifactLanguage, ArtifactVersionListItem } from "@/services/artifacts"
import { ARTIFACT_KIND_OPTIONS } from "@/components/admin/artifacts/artifactEditorState"

type ViewMode = "list" | "create" | "edit"

type ArtifactEditorHeaderProps = {
  viewMode: ViewMode
  displayName: string
  sidebarOpen: boolean
  isAgentPanelOpen: boolean
  isPublishing: boolean
  isSaving: boolean
  disableSave: boolean
  showPublish: boolean
  showVersions: boolean
  versionsOpen: boolean
  artifactVersions: ArtifactVersionListItem[]
  versionsLoading: boolean
  applyingRevisionId: string | null
  hasUnsavedChanges: boolean
  onRefreshArtifacts: () => void
  onCreateArtifact: (kind: ArtifactKind, language: ArtifactLanguage) => void
  onToggleSidebar: () => void
  onToggleAgentPanel: () => void
  onVersionsOpenChange: (open: boolean) => void
  onSelectVersion: (revisionId: string) => void
  onPublish: () => void
  onRunTest: () => void
  onSave: () => void
}

function kindIcon(kind: ArtifactKind) {
  if (kind === "agent_node") return Bot
  if (kind === "rag_operator") return Database
  return Wrench
}

export function ArtifactEditorHeader({
  viewMode,
  displayName,
  sidebarOpen,
  isAgentPanelOpen,
  isPublishing,
  isSaving,
  disableSave,
  showPublish,
  showVersions,
  versionsOpen,
  artifactVersions,
  versionsLoading,
  applyingRevisionId,
  hasUnsavedChanges,
  onRefreshArtifacts,
  onCreateArtifact,
  onToggleSidebar,
  onToggleAgentPanel,
  onVersionsOpenChange,
  onSelectVersion,
  onPublish,
  onRunTest,
  onSave,
}: ArtifactEditorHeaderProps) {
  const breadcrumbItems: BreadcrumbItemProps[] = [
    { label: "Artifacts", href: "/admin/artifacts", active: viewMode === "list" },
  ]

  if (viewMode === "create") {
    breadcrumbItems.push({ label: "New Artifact", active: true })
  }

  if (viewMode === "edit") {
    breadcrumbItems.push({
      label: displayName || "Edit Artifact",
      active: true,
      statusDot: hasUnsavedChanges ? "primary" : undefined,
    })
  }

  return (
    <AdminPageHeader contentClassName="h-12 items-center">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <CustomBreadcrumb items={breadcrumbItems} />
      </div>
      {viewMode === "list" ? (
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={onRefreshArtifacts}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm">
                <Plus className="mr-2 h-4 w-4" />
                New Artifact
                <ChevronDown className="ml-1 h-4 w-4 opacity-50" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuLabel>Select Artifact Type</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {ARTIFACT_KIND_OPTIONS.map((option) => {
                const Icon = kindIcon(option.value)
                return (
                  <DropdownMenuItem
                    key={option.value}
                    className="flex cursor-default flex-col items-start gap-2 py-3"
                    onSelect={(event) => event.preventDefault()}
                  >
                    <div className="flex items-center gap-2 font-medium text-foreground">
                      <Icon className="h-4 w-4 text-muted-foreground" />
                      <span>{option.label}</span>
                    </div>
                    <span className="text-[11px] leading-tight text-muted-foreground">
                      {option.description}
                    </span>
                    <div className="flex items-center gap-2">
                      <Button size="sm" variant="outline" onClick={() => onCreateArtifact(option.value, "javascript")}>
                        js
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => onCreateArtifact(option.value, "python")}>
                        py
                      </Button>
                    </div>
                  </DropdownMenuItem>
                )
              })}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={onToggleSidebar}
            className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
            title={sidebarOpen ? "Hide file explorer" : "Show file explorer"}
          >
            <PanelLeft className="!size-[17px]" />
          </Button>
          {showPublish ? (
            <Button
              size="sm"
              variant="outline"
              onClick={onPublish}
              disabled={isPublishing || isSaving}
            >
              {isPublishing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
              Publish
            </Button>
          ) : null}
          {showVersions ? (
            <ArtifactVersionsDropdown
              open={versionsOpen}
              onOpenChange={onVersionsOpenChange}
              versions={artifactVersions}
              isLoading={versionsLoading}
              applyingRevisionId={applyingRevisionId}
              hasUnsavedChanges={hasUnsavedChanges}
              onSelectVersion={onSelectVersion}
            />
          ) : null}
          <Button
            size="sm"
            variant="ghost"
            onClick={onToggleAgentPanel}
            className="mr-1 h-8 w-8 text-muted-foreground hover:text-foreground"
            title={isAgentPanelOpen ? "Close coding agent panel" : "Open coding agent panel"}
          >
            <KesherLogo
              size={23}
              className={cn(
                "h-4 w-4 transition-transform duration-200",
                isAgentPanelOpen ? "rotate-90 text-foreground" : "text-sky-600",
              )}
            />
          </Button>
          <Button size="sm" variant="outline" onClick={onRunTest}>
            <Play className="mr-2 h-4 w-4 fill-current" />
            Test
          </Button>
          <Button size="sm" onClick={onSave} disabled={isSaving || disableSave}>
            {isSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
            Save
          </Button>
        </div>
      )}
    </AdminPageHeader>
  )
}
