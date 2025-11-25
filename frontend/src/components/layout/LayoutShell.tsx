'use client';

import React, { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { useLayoutStore } from '@/lib/store/useLayoutStore';
import { useAuthStore } from '@/lib/store/useAuthStore';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import { ChatPane } from '@/components/layout/ChatPane';
import { SourceListPane } from '@/components/layout/SourceListPane';
import { SourceViewerPane } from '@/components/layout/SourceViewerPane';
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/app-sidebar"
import { GripVertical } from 'lucide-react';
import { useDirection } from '@/components/direction-provider';

function LayoutShellContent({ children }: { children?: React.ReactNode }) {
  // Use selectors to prevent unnecessary re-renders
  const isSourceListOpen = useLayoutStore((state) => state.isSourceListOpen);
  const activeSource = useLayoutStore((state) => state.activeSource);
  const sourceViewerWidth = useLayoutStore((state) => state.sourceViewerWidth);
  const setActiveChatId = useLayoutStore((state) => state.setActiveChatId);
  const setSourceViewerWidth = useLayoutStore((state) => state.setSourceViewerWidth);
  
  const { token, setAuth } = useAuthStore();
  const [lastActiveSource, setLastActiveSource] = React.useState<string | null>(null);
  const [isResizing, setIsResizing] = React.useState(false);
  const sourceViewerRef = React.useRef<HTMLDivElement>(null);
  const pendingWidthRef = React.useRef<number | null>(null);
  const rafIdRef = React.useRef<number | null>(null);
  const searchParams = useSearchParams();

  React.useEffect(() => {
    if (token) {
      api.getMe().then((userData) => {
        setAuth(userData, token);
      }).catch((err) => {
        console.error("Failed to refresh user profile", err);
      });
    }
  }, [token, setAuth]);

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
      
      // Cancel any pending animation frame
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
      }
      
      // Use requestAnimationFrame to batch DOM updates and prevent layout thrashing
      rafIdRef.current = requestAnimationFrame(() => {
        if (!sourceViewerRef.current) return;
        
        const sidebarOffset = isSourceListOpen ? 256 : 0;
        const newWidth = e.clientX - sidebarOffset;
        
        if (newWidth >= 400 && newWidth <= 1200) {
          sourceViewerRef.current.style.width = `${newWidth}px`;
          pendingWidthRef.current = newWidth;
        }
        
        rafIdRef.current = null;
      });
    };

    const handleMouseUp = () => {
      // Cancel any pending animation frame
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
      
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
      // Cleanup
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isResizing, setSourceViewerWidth, isSourceListOpen]);
  const { direction } = useDirection();
  const isRTL = direction !== "rtl";

  return (
    <SidebarProvider className="h-full" dir={isRTL ? "rtl" : "ltr"}>
      <SidebarInset className="h-full" >
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
              "shrink-0 min-w-0 overflow-hidden relative",
              !isResizing && "transition-all duration-300 ease-in-out",
              activeSource ? "opacity-100" : "opacity-0"
            )}
            style={{ 
              width: activeSource ? sourceViewerWidth : 0,
              willChange: isResizing ? 'width' : 'auto'
            }}
          >
            <SourceViewerPane 
              key={activeSource || lastActiveSource || 'empty'} 
              sourceId={activeSource || lastActiveSource} 
            />
            
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
            {children || <ChatPane />}
          </div>
        </div>
      </SidebarInset>
      <AppSidebar />
    </SidebarProvider>
  );
}

export function LayoutShell({ children }: { children?: React.ReactNode }) {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <LayoutShellContent>{children}</LayoutShellContent>
    </Suspense>
  );
}
