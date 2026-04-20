"use client"

import { Eye, FileSpreadsheet, FileText, Loader2, Plus, RefreshCw, Save } from "lucide-react"

import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { CustomBreadcrumb, type BreadcrumbItemProps } from "@/components/ui/custom-breadcrumb"
import { Button } from "@/components/ui/button"

type ViewMode = "list" | "detail"

type FileSpaceEditorHeaderProps = {
  viewMode: ViewMode
  spaceName?: string
  spaceId?: string
  controlsDisabled?: boolean
  hasUnsavedChanges?: boolean
  isSaving?: boolean
  onRefresh: () => void
  onCreateSpace?: () => void
  onSaveAll?: () => void
  onArchiveSpace?: () => void
  previewTextToggle?: {
    visible: boolean
    rawTextActive: boolean
    formattedMode: "spreadsheet" | "preview"
    onToggle: () => void
  }
}

export function FileSpaceEditorHeader({
  viewMode,
  spaceName,
  spaceId,
  controlsDisabled = false,
  hasUnsavedChanges = false,
  isSaving = false,
  onRefresh,
  onCreateSpace,
  onSaveAll,
  onArchiveSpace,
  previewTextToggle,
}: FileSpaceEditorHeaderProps) {
  const breadcrumbItems: BreadcrumbItemProps[] = [
    { label: "Files", href: "/admin/files", active: viewMode === "list" },
  ]

  if (viewMode === "detail" && spaceId) {
    breadcrumbItems.push({
      label: spaceName || "File Space",
      href: `/admin/files/${spaceId}`,
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
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded-full text-muted-foreground hover:bg-transparent hover:text-foreground"
            onClick={onRefresh}
            disabled={controlsDisabled}
            aria-label="Refresh file spaces"
            title="Refresh file spaces"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button size="sm" onClick={onCreateSpace} disabled={controlsDisabled}>
            <Plus className="mr-2 h-4 w-4" />
            New File Space
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded-full text-muted-foreground hover:bg-transparent hover:text-foreground"
            onClick={onRefresh}
            disabled={controlsDisabled}
            aria-label="Refresh file preview"
            title="Refresh file preview"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
          {previewTextToggle?.visible ? (
            <Button
              variant="ghost"
              size="icon"
              className={`h-8 w-8 rounded-full hover:bg-transparent ${
                previewTextToggle.rawTextActive
                  ? "text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              onClick={previewTextToggle.onToggle}
              disabled={controlsDisabled}
              aria-label={previewTextToggle.rawTextActive ? "Switch to formatted view" : "Switch to raw text view"}
              title={previewTextToggle.rawTextActive ? "Switch to formatted view" : "Switch to raw text view"}
            >
              {previewTextToggle.rawTextActive ? (
                previewTextToggle.formattedMode === "spreadsheet" ? (
                  <FileSpreadsheet className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )
              ) : (
                <FileText className="h-4 w-4" />
              )}
            </Button>
          ) : null}
          <Button
            variant="outline"
            size="sm"
            onClick={onSaveAll}
            disabled={controlsDisabled || !hasUnsavedChanges || isSaving}
          >
            {isSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
            Save
          </Button>
          <Button variant="outline" size="sm" onClick={onArchiveSpace} disabled={controlsDisabled}>
            Archive
          </Button>
        </div>
      )}
    </AdminPageHeader>
  )
}
