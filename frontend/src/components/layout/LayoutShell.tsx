'use client';

import React, { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { useLayoutStore } from '@/lib/store/useLayoutStore';
import { cn } from '@/lib/utils';
import { ChatPane } from '@/components/layout/ChatPane';
import { SourceListPane } from '@/components/layout/SourceListPane';
import { SourceViewerPane } from '@/components/layout/SourceViewerPane';
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/app-sidebar"
import { GripVertical } from 'lucide-react';

function LayoutShellContent() {
  const { isSourceListOpen, activeSource, sourceViewerWidth, setActiveChatId, setSourceViewerWidth } = useLayoutStore();
  const [lastActiveSource, setLastActiveSource] = React.useState<string | null>(null);
  const [isResizing, setIsResizing] = React.useState(false);
  const sourceViewerRef = React.useRef<HTMLDivElement>(null);
  const pendingWidthRef = React.useRef<number | null>(null);
  const searchParams = useSearchParams();

  React.useEffect(() => {
    const chatId = searchParams.get('chatId');
    if (chatId) {
      setActiveChatId(chatId);
    }
  }, [searchParams, setActiveChatId]);

  React.useEffect(() => {
    if (activeSource) {
      setLastActiveSource(activeSource);
    }
  }, [activeSource]);

  React.useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing || !sourceViewerRef.current) return;
      
      const sidebarOffset = isSourceListOpen ? 256 : 0;
      const newWidth = e.clientX - sidebarOffset;
      
      if (newWidth >= 400 && newWidth <= 1200) {
        sourceViewerRef.current.style.width = `${newWidth}px`;
        pendingWidthRef.current = newWidth;
      }
    };

    const handleMouseUp = () => {
      if (pendingWidthRef.current !== null) {
        setSourceViewerWidth(pendingWidthRef.current);
        pendingWidthRef.current = null;
      }
      setIsResizing(false);
    };

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'ew-resize';
      document.body.style.userSelect = 'none';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isResizing, setSourceViewerWidth, isSourceListOpen]);

  return (
    <SidebarProvider className="h-full">
      <SidebarInset className="h-full">
        <div className="flex h-full w-full overflow-hidden bg-background">
          {/* Left Pane: Source List (Collapsible) */}
          <div
            className={cn(
              "border-r transition-all duration-300 ease-in-out h-full",
              isSourceListOpen ? "w-64" : "w-0 opacity-0 overflow-hidden"
            )}
          >
            <SourceListPane />
          </div>

          {/* Center Pane: Source Viewer (Collapsible) */}
          <div
            ref={sourceViewerRef}
            className={cn(
              "shrink-0 min-w-0 transition-all duration-300 ease-in-out overflow-hidden relative",
              activeSource ? "opacity-100" : "opacity-0"
            )}
            style={{ width: activeSource ? sourceViewerWidth : 0 }}
          >
            <SourceViewerPane sourceId={activeSource || lastActiveSource} />
            
            {/* Resize Handle */}
            {activeSource && (
              <div
                className="absolute right-0 top-0 bottom-0 w-[0.9px] bg-border cursor-ew-resize flex items-center justify-center group"
                onMouseDown={() => setIsResizing(true)}
              >
                <div className="absolute inset-y-0 -left-1 -right-1" />
                <GripVertical className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
            )}
          </div>

          {/* Right/Main Pane: Chat */}
          <div className="flex-1 min-w-0 flex flex-col min-h-0">
            <ChatPane />
          </div>
        </div>
      </SidebarInset>
      <AppSidebar side="right" />
    </SidebarProvider>
  );
}

export function LayoutShell() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <LayoutShellContent />
    </Suspense>
  );
}
