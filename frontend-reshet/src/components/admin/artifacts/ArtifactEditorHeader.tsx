"use client"

import { Bot, ChevronDown, Clock3, Database, Loader2, PanelLeft, Play, Plus, RefreshCw, Save, Upload, Wrench } from "lucide-react"

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
  controlsDisabled?: boolean
  sidebarOpen: boolean
  isAgentPanelOpen: boolean
  isPublishing: boolean
  isPublished: boolean
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
  onStartNewChat: () => void
  onOpenChatHistory: () => void
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
  controlsDisabled = false,
  sidebarOpen,
  isAgentPanelOpen,
  isPublishing,
  isPublished,
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
  onStartNewChat,
  onOpenChatHistory,
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
    <AdminPageHeader contentClassName="h-12 items-center" scrollEffectMode="none">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <CustomBreadcrumb items={breadcrumbItems} />
      </div>
      {viewMode === "list" ? (
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={onRefreshArtifacts} disabled={controlsDisabled}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" disabled={controlsDisabled}>
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
            disabled={controlsDisabled}
            className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
            title={sidebarOpen ? "Hide file explorer" : "Show file explorer"}
          >
            <PanelLeft className="!size-[17px]" />
          </Button>
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
          <div className="mr-1 flex items-center">
            <div
              className={cn(
                "flex items-center rounded-full p-1 transition-all duration-200 ease-out",
                isAgentPanelOpen ? "gap-1 border border-border/70 bg-background/80 backdrop-blur-sm" : "gap-0 border-transparent bg-transparent",
              )}>
              <div
                className={cn(
                  "flex items-center overflow-hidden transition-all duration-200 ease-out",
                  isAgentPanelOpen ? "mr-1 max-w-24 opacity-100" : "mr-0 max-w-0 opacity-0",
                )}
                aria-hidden={!isAgentPanelOpen}
              >
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={onStartNewChat}
                  disabled={controlsDisabled || !isAgentPanelOpen}
                  className="h-6 w-6 rounded-full text-muted-foreground hover:text-foreground"
                  title="Create new chat"
                  aria-label="Create new chat"
                  tabIndex={isAgentPanelOpen ? 0 : -1}
                >
                  <Plus className="h-3.5 w-3.5" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={onOpenChatHistory}
                  disabled={controlsDisabled || !isAgentPanelOpen}
                  className="h-6 w-6 rounded-full text-muted-foreground hover:text-foreground"
                  title="Chat history"
                  aria-label="Chat history"
                  tabIndex={isAgentPanelOpen ? 0 : -1}
                >
                  <Clock3 className="h-3.5 w-3.5" />
                </Button>
              </div>
              <Button
                size="sm"
                variant="ghost"
                onClick={onToggleAgentPanel}
                disabled={controlsDisabled}
                className="relative z-10 h-6 w-6 shrink-0 rounded-full p-0 text-muted-foreground hover:text-foreground"
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
            </div>
          </div>
          <Button size="sm" variant="outline" onClick={onRunTest} disabled={controlsDisabled}>
            <Play className="mr-2 h-4 w-4 fill-current" />
            Test
          </Button>
          <Button size="sm" onClick={onSave} disabled={controlsDisabled || isSaving || disableSave}>
            {isSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
            Save
          </Button>
          {showPublish || isPublished ? (
            <Button
              size="sm"
              variant="outline"
              onClick={isPublished ? undefined : onPublish}
              disabled={controlsDisabled || isPublished || isPublishing || isSaving}
            >
              {isPublishing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
              {isPublished ? "Published" : "Publish"}
            </Button>
          ) : null}
        </div>
      )}
    </AdminPageHeader>
  )
}
