"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type BootSkeletonProps = {
  previewViewport: "desktop" | "mobile";
};

export function AppsBuilderWorkspaceBootSkeleton({ previewViewport }: BootSkeletonProps) {
  return (
    <div data-testid="apps-builder-boot-skeleton" className="flex h-dvh min-h-0 w-full overflow-hidden bg-background">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex h-11 shrink-0 items-center gap-3 border-b border-border/50 px-3">
          <div className="flex min-w-0 items-center gap-3">
            <Skeleton className="h-4 w-4 rounded-sm" />
            <Skeleton className="h-4 w-40" />
          </div>

          <div className="flex flex-1 items-center justify-center">
            <Skeleton className="h-7 w-44 rounded-md" />
          </div>

          <div className="ml-auto flex items-center gap-1.5">
            <Skeleton className="h-7 w-7 rounded-md" />
            <Skeleton className="h-7 w-7 rounded-md" />
            <Skeleton className="h-7 w-14 rounded-md" />
            <Skeleton className="h-7 w-16 rounded-md" />
          </div>
        </header>

        <div className={cn("flex min-h-0 flex-1 items-start justify-center", previewViewport === "mobile" ? "bg-muted/30 p-4" : "")}>
          <div
            className={cn(
              "h-full",
              previewViewport === "mobile"
                ? "w-[390px] overflow-hidden rounded-xl border border-border/60 shadow-sm"
                : "w-full",
            )}
          >
            <div className="flex h-full w-full flex-col bg-white p-5">
              <Skeleton className="h-6 w-40" />
              <Skeleton className="mt-4 h-3 w-64" />
              <Skeleton className="mt-2 h-3 w-52" />
              <div className="mt-6 grid flex-1 gap-4 md:grid-cols-2">
                <Skeleton className="h-28 w-full" />
                <Skeleton className="h-28 w-full" />
                <Skeleton className="h-28 w-full" />
                <Skeleton className="h-28 w-full" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="flex h-full w-10 shrink-0 flex-col items-center border-l border-border/60 bg-muted/20 pt-3">
        <Skeleton className="h-8 w-8 rounded-md" />
      </div>
    </div>
  );
}

export function UsersListSkeleton() {
  return (
    <div data-testid="apps-builder-users-skeleton" className="space-y-2">
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="flex items-center justify-between rounded-md border border-border/60 p-3">
          <div className="space-y-2">
            <Skeleton className="h-3.5 w-44" />
            <Skeleton className="h-3 w-64" />
          </div>
          <Skeleton className="h-8 w-20 rounded-md" />
        </div>
      ))}
    </div>
  );
}

export function DomainsListSkeleton() {
  return (
    <div data-testid="apps-builder-domains-skeleton" className="space-y-2">
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="flex items-center justify-between rounded-md border border-border/60 p-3">
          <div className="space-y-2">
            <Skeleton className="h-3.5 w-44" />
            <Skeleton className="h-3 w-52" />
          </div>
          <Skeleton className="h-8 w-20 rounded-md" />
        </div>
      ))}
    </div>
  );
}
