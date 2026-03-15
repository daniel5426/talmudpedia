import { Search } from "lucide-react";

interface ChatPaneHeaderProps {
  title: string;
  subtitle?: string;
  isEmptyState: boolean;
}

export function ChatPaneHeader({
  title,
  subtitle,
  isEmptyState,
}: ChatPaneHeaderProps) {
  const backgroundStyles = isEmptyState
    ? { backgroundColor: "transparent" }
    : {
        background:
          "linear-gradient(to top, color-mix(in oklch, var(--chat-background) 0%, transparent) 0%, color-mix(in oklch, var(--chat-background) 80%, transparent) 60%, var(--chat-background) 100%)",
      };

  return (
    <div
      className="absolute left-0 right-0 top-0 z-20 w-full px-4 py-2.5 transition-all duration-500 ease-out"
      style={backgroundStyles}
    >
      <div className="flex items-center gap-2">
        <div className="flex shadow-md items-center gap-1 rounded-lg bg-background">
          <button
            type="button"
            className="relative flex h-8 items-center gap-2 rounded-[0.5rem] px-3 text-sm font-normal text-muted-foreground"
          >
            <Search className="h-4 w-4 shrink-0" />
            <span className="hidden min-[400px]:inline-flex">
              Search and actions coming next
            </span>
            <span className="inline-flex min-[400px]:hidden">
              Search
            </span>
            <span className="ml-2 hidden h-5 items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium min-[560px]:inline-flex">
              <span className="text-xs">⌘</span>K
            </span>
          </button>
        </div>

        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{title}</div>
          {subtitle ? (
            <div className="truncate text-[11px] text-muted-foreground">
              {subtitle}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
