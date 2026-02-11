import { useEffect, useMemo, useRef, useState } from "react";
import { AppSidebar } from "./AppSidebar";
import { ChatPane } from "./ChatPane";
import { SourceListPane } from "./SourceListPane";
import { SourceViewerPane } from "./SourceViewerPane";
import type { ChatMessage, SourceItem } from "./types";
import { CloseIcon, GripVerticalIcon, MenuIcon } from "../icons";
import { useIsMobile } from "../../hooks/useIsMobile";

type LayoutShellProps = {
  appTitle: string;
  messages: ChatMessage[];
  input: string;
  isSending: boolean;
  runtimeError: string | null;
  onInputChange: (value: string) => void;
  onSubmit: () => void;
  sources: SourceItem[];
};

export function LayoutShell({
  appTitle,
  messages,
  input,
  isSending,
  runtimeError,
  onInputChange,
  onSubmit,
  sources,
}: LayoutShellProps) {
  const isMobile = useIsMobile();
  const workspaceRef = useRef<HTMLDivElement | null>(null);

  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isSourceListOpen, setIsSourceListOpen] = useState(true);
  const [activeSourceId, setActiveSourceId] = useState<string | null>(null);
  const [lastActiveSourceId, setLastActiveSourceId] = useState<string | null>(null);
  const [sourceViewerWidth, setSourceViewerWidth] = useState(520);
  const [isResizing, setIsResizing] = useState(false);

  const history = useMemo(() => {
    const recentUserMessages = messages
      .filter((message) => message.role === "user")
      .slice(-6)
      .map((message) => message.content.trim())
      .filter((message) => message.length > 0)
      .reverse();
    if (recentUserMessages.length > 0) return recentUserMessages;
    return ["Welcome conversation", "Design review", "Runtime notes"];
  }, [messages]);

  const activeSource = useMemo(() => {
    const direct = sources.find((source) => source.id === activeSourceId) || null;
    if (direct) return direct;
    if (!lastActiveSourceId) return null;
    return sources.find((source) => source.id === lastActiveSourceId) || null;
  }, [activeSourceId, lastActiveSourceId, sources]);

  useEffect(() => {
    if (!activeSourceId) return;
    setLastActiveSourceId(activeSourceId);
  }, [activeSourceId]);

  useEffect(() => {
    if (!isMobile) return;
    setIsSidebarOpen(false);
    setIsSourceListOpen(false);
  }, [isMobile]);

  useEffect(() => {
    if (!isResizing || isMobile) return;

    const onMouseMove = (event: MouseEvent) => {
      const host = workspaceRef.current;
      if (!host) return;
      const hostBox = host.getBoundingClientRect();
      const fromRight = hostBox.right - event.clientX;
      const nextWidth = Math.min(Math.max(fromRight, 360), 920);
      setSourceViewerWidth(nextWidth);
    };

    const onMouseUp = () => setIsResizing(false);

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    document.body.style.cursor = "ew-resize";
    document.body.style.userSelect = "none";

    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isMobile, isResizing]);

  const showViewer = Boolean(activeSource);

  return (
    <div className="layout-shell">
      {!isSidebarOpen && isMobile ? (
        <button type="button" className="mobile-sidebar-trigger" onClick={() => setIsSidebarOpen(true)}>
          <MenuIcon width={16} height={16} />
        </button>
      ) : null}

      {isMobile ? (
        isSidebarOpen ? (
          <div className="mobile-overlay" role="dialog" aria-modal="true">
            <div className="mobile-overlay-backdrop" onClick={() => setIsSidebarOpen(false)} />
            <div className="mobile-overlay-panel sidebar">
              <div className="mobile-overlay-top">
                <button type="button" className="icon-button" onClick={() => setIsSidebarOpen(false)}>
                  <CloseIcon width={14} height={14} />
                </button>
              </div>
              <AppSidebar
                isOpen
                onToggle={() => setIsSidebarOpen(false)}
                appTitle={appTitle}
                history={history}
              />
            </div>
          </div>
        ) : null
      ) : (
        <AppSidebar
          isOpen={isSidebarOpen}
          onToggle={() => setIsSidebarOpen((value) => !value)}
          appTitle={appTitle}
          history={history}
        />
      )}

      <div className="layout-content" ref={workspaceRef}>
        <main className="layout-main">
          <ChatPane
            appTitle={appTitle}
            messages={messages}
            input={input}
            isSending={isSending}
            runtimeError={runtimeError}
            onInputChange={onInputChange}
            onSubmit={onSubmit}
            onToggleSidebar={() => setIsSidebarOpen((value) => !value)}
            onToggleSourceList={() => setIsSourceListOpen((value) => !value)}
          />
        </main>

        {!isMobile ? (
          <>
            <section
              className={`layout-source-viewer ${showViewer ? "open" : "closed"}`}
              style={{ width: showViewer ? sourceViewerWidth : 0 }}
            >
              <SourceViewerPane source={activeSource} />
              {showViewer ? (
                <button
                  type="button"
                  className="resize-handle"
                  onMouseDown={() => setIsResizing(true)}
                  aria-label="Resize source viewer"
                >
                  <GripVerticalIcon width={14} height={14} />
                </button>
              ) : null}
            </section>

            <section className={`layout-source-list ${isSourceListOpen ? "open" : "closed"}`}>
              <SourceListPane
                sources={sources}
                activeSourceId={activeSourceId}
                onSelectSource={(sourceId) => setActiveSourceId(sourceId)}
                onClose={() => setIsSourceListOpen(false)}
              />
            </section>
          </>
        ) : (
          <>
            {isSourceListOpen ? (
              <div className="mobile-overlay" role="dialog" aria-modal="true">
                <div className="mobile-overlay-backdrop" onClick={() => setIsSourceListOpen(false)} />
                <div className="mobile-overlay-panel source-list">
                  <SourceListPane
                    sources={sources}
                    activeSourceId={activeSourceId}
                    onSelectSource={(sourceId) => {
                      setActiveSourceId(sourceId);
                      setIsSourceListOpen(false);
                    }}
                    onClose={() => setIsSourceListOpen(false)}
                  />
                </div>
              </div>
            ) : null}

            {showViewer ? (
              <div className="mobile-viewer" role="dialog" aria-modal="true">
                <SourceViewerPane source={activeSource} onClose={() => setActiveSourceId(null)} />
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
