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
        <div className="glass-panel rounded-xl border border-border/70 px-3 py-2 shadow-sm">
          <div className="flex items-center gap-3">
            <span className="h-2 w-2 rounded-full bg-primary/70" />
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{title}</p>
              {subtitle ? (
                <p className="truncate text-[11px] text-muted-foreground">
                  {subtitle}
                </p>
              ) : null}
            </div>
          </div>
        </div>
        <div className="flex-1" />
      </div>
    </div>
  );
}
