"use client";

import { useMemo } from "react";
import { ChevronLeft, Code2, EllipsisVertical, Loader2, MessageSquare, RefreshCw, Rocket, RotateCcw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { AppVersionListItem, PublishedAppRevision } from "@/services";

type AppsBuilderVersionHistoryPanelProps = {
  versions: AppVersionListItem[];
  selectedVersionId: string | null;
  selectedVersion: PublishedAppRevision | null;
  isLoadingVersions: boolean;
  isRestoringVersion: boolean;
  isPublishingVersion: boolean;
  publishStatus: string | null;
  onClose: () => void;
  onRefreshVersions: () => void;
  onSelectVersion: (versionId: string) => void;
  onRestoreVersion: (versionId?: string) => void;
  onPublishVersion: (versionId?: string) => void;
  onViewCodeVersion: (versionId: string) => void;
  onOpenHistory: () => void;
};

function buildVersionTitle(version: AppVersionListItem): string {
  const runPreview = String(version.run_prompt_preview || "").trim();
  if (runPreview) return runPreview;
  const source = String(version.origin_kind || "unknown").replace(/_/g, " ");
  return `Version ${version.version_seq ?? "?"} • ${source}`;
}

export function AppsBuilderVersionHistoryPanel({
  versions,
  selectedVersionId,
  selectedVersion,
  isLoadingVersions,
  isRestoringVersion,
  isPublishingVersion,
  publishStatus,
  onClose,
  onRefreshVersions,
  onSelectVersion,
  onRestoreVersion,
  onPublishVersion,
  onViewCodeVersion,
  onOpenHistory,
}: AppsBuilderVersionHistoryPanelProps) {
  const selectedVersionFilesCount = useMemo(
    () => Object.keys(selectedVersion?.files || {}).length,
    [selectedVersion],
  );

  return (
    <>
      <div className="flex h-9 shrink-0 items-center justify-between border-b border-border/60 px-2">
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground hover:text-foreground"
            onClick={onClose}
            aria-label="Back to chat"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <h3 className="text-sm font-semibold">Version History</h3>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-muted-foreground hover:text-foreground"
          onClick={onRefreshVersions}
          disabled={isLoadingVersions}
          aria-label="Refresh versions"
        >
          {isLoadingVersions ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
        </Button>
      </div>

      <ScrollArea className="min-h-0 flex-1 px-2 py-2">
        <div className="space-y-2">
          {isLoadingVersions && versions.length === 0 ? (
            <>
              <Skeleton className="h-20 w-full rounded-xl" />
              <Skeleton className="h-20 w-full rounded-xl" />
              <Skeleton className="h-20 w-full rounded-xl" />
            </>
          ) : null}

          {versions.map((version) => {
            const isSelected = selectedVersionId === version.id;
            return (
              <article
                key={version.id}
                className={cn(
                  "rounded-xl border px-3 py-2.5 transition-colors",
                  isSelected
                    ? "border-primary/40 bg-primary/10"
                    : "border-border/60 bg-background/70 hover:border-border hover:bg-background",
                )}
              >
                <div className="flex items-start gap-2">
                  <button
                    type="button"
                    className="min-w-0 flex-1 text-left"
                    onClick={() => onSelectVersion(version.id)}
                  >
                    <div className="truncate text-sm font-semibold">{buildVersionTitle(version)}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {new Date(version.created_at).toLocaleString()}
                    </div>
                  </button>
                  <div className="flex shrink-0 items-center gap-1">
                    {version.is_current_draft ? <Badge className="h-6 bg-primary/15 text-primary">Current</Badge> : null}
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-foreground">
                          <EllipsisVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-52">
                        <DropdownMenuItem
                          onClick={() => {
                            onPublishVersion(version.id);
                          }}
                          disabled={isPublishingVersion || isRestoringVersion}
                        >
                          <Rocket className="h-3.5 w-3.5" />
                          Publish this version
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => {
                            onRestoreVersion(version.id);
                          }}
                          disabled={isRestoringVersion || isPublishingVersion}
                        >
                          {isRestoringVersion ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
                          Revert to this version
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => {
                            onSelectVersion(version.id);
                            onViewCodeVersion(version.id);
                          }}
                        >
                          <Code2 className="h-3.5 w-3.5" />
                          View code
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => {
                            onClose();
                            onOpenHistory();
                          }}
                        >
                          <MessageSquare className="h-3.5 w-3.5" />
                          Go to chat
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              </article>
            );
          })}

          {!isLoadingVersions && versions.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border/60 px-3 py-8 text-center text-xs text-muted-foreground">
              No versions yet.
            </div>
          ) : null}
        </div>
      </ScrollArea>

      <div className="shrink-0 border-t border-border/60 px-3 py-2 text-[11px] text-muted-foreground">
        {isRestoringVersion
          ? "Reverting version..."
          : publishStatus
            ? `Publish status: ${publishStatus}`
            : selectedVersion
              ? `Selected files: ${selectedVersionFilesCount}`
              : "Select a version for publish, restore, or code view."}
      </div>
    </>
  );
}
