"use client";

import { useCallback, useState } from "react";
import {
  Check,
  ChevronDown,
  Loader2,
  LogIn,
  RefreshCw,
  TriangleAlert,
  Unplug,
  Wrench,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type { IntegrationCatalogEntry } from "@/services/integration-catalog";
import type { McpAccountConnection, McpServer } from "@/services";

// ── Card state derivation ────────────────────────────────────────────────────

export type CardState =
  | "available"
  | "adding"
  | "needs_auth"
  | "connected"
  | "error";

export function deriveCardState(
  server: McpServer | null,
  connection: McpAccountConnection | null,
  catalogEntry: IntegrationCatalogEntry,
  isAdding: boolean
): CardState {
  if (isAdding) return "adding";
  if (!server) return "available";
  if (
    server.sync_status === "error" ||
    server.sync_error
  )
    return "error";
  if (
    catalogEntry.requires_user_oauth &&
    (!connection || connection.status !== "active")
  )
    return "needs_auth";
  return "connected";
}

// ── Icon renderer ────────────────────────────────────────────────────────────

function IntegrationIcon({
  entry,
  className,
}: {
  entry: IntegrationCatalogEntry;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-center rounded-xl border border-border/60 bg-muted/30 transition-colors",
        className
      )}
      style={{ color: entry.accent }}
    >
      <svg
        viewBox="0 0 24 24"
        className="h-6 w-6"
        dangerouslySetInnerHTML={{ __html: entry.icon_svg }}
      />
    </div>
  );
}

// ── Card component ───────────────────────────────────────────────────────────

interface IntegrationCardProps {
  entry: IntegrationCatalogEntry;
  server: McpServer | null;
  connection: McpAccountConnection | null;
  onAdd: (entry: IntegrationCatalogEntry) => Promise<void>;
  onConnect: (serverId: string) => Promise<void>;
  onDisconnect: (serverId: string) => Promise<void>;
  onSync: (serverId: string) => Promise<void>;
}

export function IntegrationCard({
  entry,
  server,
  connection,
  onAdd,
  onConnect,
  onDisconnect,
  onSync,
}: IntegrationCardProps) {
  const [isAdding, setIsAdding] = useState(false);
  const [isBusy, setIsBusy] = useState(false);

  const state = deriveCardState(server, connection, entry, isAdding);

  const handleAdd = useCallback(async () => {
    setIsAdding(true);
    try {
      await onAdd(entry);
    } finally {
      setIsAdding(false);
    }
  }, [entry, onAdd]);

  const handleAction = useCallback(
    async (action: () => Promise<void>) => {
      setIsBusy(true);
      try {
        await action();
      } finally {
        setIsBusy(false);
      }
    },
    []
  );

  const toolCount = server?.tool_snapshot_version
    ? server.tool_snapshot_version > 0
      ? `v${server.tool_snapshot_version}`
      : null
    : null;

  return (
    <div
      id={`integration-card-${entry.slug}`}
      className={cn(
        "group relative flex flex-col rounded-xl border bg-background p-4 transition-all duration-200",
        state === "available" &&
          "border-border/50 hover:border-border hover:shadow-sm",
        state === "adding" &&
          "border-border/50 animate-pulse",
        state === "needs_auth" &&
          "border-amber-500/40 shadow-[0_0_0_1px_rgba(245,158,11,0.08)]",
        state === "connected" &&
          "border-emerald-500/40 shadow-[0_0_0_1px_rgba(16,185,129,0.08)]",
        state === "error" &&
          "border-destructive/40 shadow-[0_0_0_1px_rgba(239,68,68,0.08)]"
      )}
    >
      {/* ── Top: Icon + Name + Status ── */}
      <div className="flex items-start gap-3">
        <IntegrationIcon entry={entry} className="h-11 w-11 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold truncate">{entry.name}</h3>
            {state === "connected" && (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600">
                <Check className="h-2.5 w-2.5" />
                Connected
              </span>
            )}
            {state === "needs_auth" && (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-600">
                <LogIn className="h-2.5 w-2.5" />
                Needs auth
              </span>
            )}
            {state === "error" && (
              <span className="inline-flex items-center gap-1 rounded-full bg-destructive/10 px-2 py-0.5 text-[10px] font-medium text-destructive">
                <TriangleAlert className="h-2.5 w-2.5" />
                Error
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground/70 line-clamp-2 leading-relaxed">
            {entry.description}
          </p>
        </div>
      </div>

      {/* ── Bottom: Action area ── */}
      <div className="mt-3 flex items-center justify-between gap-2 pt-2 border-t border-border/30">
        {/* Left: metadata */}
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground/50">
          {toolCount && (
            <span className="flex items-center gap-1">
              <Wrench className="h-3 w-3" />
              {toolCount}
            </span>
          )}
          {server?.last_synced_at && (
            <span>
              Synced{" "}
              {formatRelativeTime(server.last_synced_at)}
            </span>
          )}
        </div>

        {/* Right: action button */}
        <div className="flex items-center gap-1.5">
          {state === "available" && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-3 text-xs"
              onClick={handleAdd}
            >
              + Add
            </Button>
          )}

          {state === "adding" && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-3 text-xs"
              disabled
            >
              <Loader2 className="h-3 w-3 animate-spin mr-1.5" />
              Setting up…
            </Button>
          )}

          {state === "needs_auth" && server && (
            <Button
              size="sm"
              className="h-7 px-3 text-xs"
              onClick={() => handleAction(() => onConnect(server.id))}
              disabled={isBusy}
            >
              {isBusy ? (
                <Loader2 className="h-3 w-3 animate-spin mr-1.5" />
              ) : (
                <LogIn className="h-3 w-3 mr-1.5" />
              )}
              Connect
            </Button>
          )}

          {state === "connected" && server && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 px-2.5 text-xs"
                >
                  Manage
                  <ChevronDown className="h-3 w-3 ml-1" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44">
                <DropdownMenuItem
                  onClick={() => handleAction(() => onSync(server.id))}
                >
                  <RefreshCw className="h-3.5 w-3.5 mr-2" />
                  Sync Tools
                </DropdownMenuItem>
                {entry.requires_user_oauth && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      variant="destructive"
                      onClick={() =>
                        handleAction(() => onDisconnect(server.id))
                      }
                    >
                      <Unplug className="h-3.5 w-3.5 mr-2" />
                      Disconnect
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          )}

          {state === "error" && server && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-3 text-xs text-destructive border-destructive/30 hover:bg-destructive/5"
              onClick={() => handleAction(() => onSync(server.id))}
              disabled={isBusy}
            >
              {isBusy ? (
                <Loader2 className="h-3 w-3 animate-spin mr-1.5" />
              ) : (
                <RefreshCw className="h-3 w-3 mr-1.5" />
              )}
              Retry
            </Button>
          )}
        </div>
      </div>

      {/* Error detail */}
      {state === "error" && server?.sync_error && (
        <p className="mt-2 text-[11px] text-destructive/80 line-clamp-2">
          {server.sync_error}
        </p>
      )}
    </div>
  );
}

// ── Connected card (richer, for the "Connected" tab) ─────────────────────────

interface ConnectedIntegrationCardProps {
  entry: IntegrationCatalogEntry | null;
  server: McpServer;
  connection: McpAccountConnection | null;
  toolCount: number;
  onConnect: (serverId: string) => Promise<void>;
  onDisconnect: (serverId: string) => Promise<void>;
  onSync: (serverId: string) => Promise<void>;
}

export function ConnectedIntegrationCard({
  entry,
  server,
  connection,
  toolCount,
  onConnect,
  onDisconnect,
  onSync,
}: ConnectedIntegrationCardProps) {
  const [isBusy, setIsBusy] = useState(false);

  const handleAction = useCallback(
    async (action: () => Promise<void>) => {
      setIsBusy(true);
      try {
        await action();
      } finally {
        setIsBusy(false);
      }
    },
    []
  );

  const isError = server.sync_status === "error";
  const needsAuth =
    server.auth_mode === "oauth_user_account" &&
    (!connection || connection.status !== "active");

  return (
    <div
      className={cn(
        "flex items-center gap-4 rounded-xl border bg-background px-5 py-4 transition-all duration-200",
        isError
          ? "border-destructive/30"
          : needsAuth
            ? "border-amber-500/30"
            : "border-border/50 hover:border-border"
      )}
    >
      {/* Icon */}
      {entry ? (
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-muted/30"
          style={{ color: entry.accent }}
        >
          <svg
            viewBox="0 0 24 24"
            className="h-5 w-5"
            dangerouslySetInnerHTML={{ __html: entry.icon_svg }}
          />
        </div>
      ) : (
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-muted/30 text-muted-foreground">
          <Wrench className="h-5 w-5" />
        </div>
      )}

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium truncate">
            {entry?.name ?? server.name}
          </span>
          {isError ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-destructive/10 px-2 py-0.5 text-[10px] font-medium text-destructive">
              <TriangleAlert className="h-2.5 w-2.5" />
              Error
            </span>
          ) : needsAuth ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-600">
              <LogIn className="h-2.5 w-2.5" />
              Needs auth
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600">
              <Check className="h-2.5 w-2.5" />
              Connected
            </span>
          )}
        </div>
        <div className="mt-0.5 flex items-center gap-3 text-xs text-muted-foreground/60">
          <span className="truncate font-mono text-[11px]">
            {server.server_url}
          </span>
          {toolCount > 0 && (
            <>
              <span className="text-muted-foreground/30">·</span>
              <span>
                {toolCount} tool{toolCount !== 1 ? "s" : ""}
              </span>
            </>
          )}
          {server.last_synced_at && (
            <>
              <span className="text-muted-foreground/30">·</span>
              <span>Synced {formatRelativeTime(server.last_synced_at)}</span>
            </>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 shrink-0">
        {needsAuth ? (
          <Button
            size="sm"
            className="h-8 text-xs"
            onClick={() => handleAction(() => onConnect(server.id))}
            disabled={isBusy}
          >
            {isBusy ? (
              <Loader2 className="h-3 w-3 animate-spin mr-1.5" />
            ) : (
              <LogIn className="h-3 w-3 mr-1.5" />
            )}
            Connect Account
          </Button>
        ) : (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="h-8 text-xs">
                Manage
                <ChevronDown className="h-3 w-3 ml-1" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuItem
                onClick={() => handleAction(() => onSync(server.id))}
              >
                <RefreshCw className="h-3.5 w-3.5 mr-2" />
                Sync Tools
              </DropdownMenuItem>
              {server.auth_mode === "oauth_user_account" && connection && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    variant="destructive"
                    onClick={() =>
                      handleAction(() => onDisconnect(server.id))
                    }
                  >
                    <Unplug className="h-3.5 w-3.5 mr-2" />
                    Disconnect
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatRelativeTime(isoDateString: string): string {
  try {
    const date = new Date(isoDateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMin = Math.floor(diffMs / 60_000);
    if (diffMin < 1) return "just now";
    if (diffMin < 60)
      return `${diffMin}m ago`;
    const diffHrs = Math.floor(diffMin / 60);
    if (diffHrs < 24)
      return `${diffHrs}h ago`;
    const diffDays = Math.floor(diffHrs / 24);
    return `${diffDays}d ago`;
  } catch {
    return "";
  }
}
