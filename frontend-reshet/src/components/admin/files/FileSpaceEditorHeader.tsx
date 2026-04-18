"use client"

import { Loader2, Plus, RefreshCw, Save } from "lucide-react"

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
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={controlsDisabled}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <Button size="sm" onClick={onCreateSpace} disabled={controlsDisabled}>
            <Plus className="mr-2 h-4 w-4" />
            New File Space
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={controlsDisabled}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
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
