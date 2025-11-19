'use client';

import React from 'react';
import { useLayoutStore } from '@/lib/store/useLayoutStore';
import { cn } from '@/lib/utils';
import { ChatPane } from '@/components/layout/ChatPane';
import { SourceListPane } from '@/components/layout/SourceListPane';
import { SourceViewerPane } from '@/components/layout/SourceViewerPane';
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/app-sidebar"

export function LayoutShell() {
  const { isSourceListOpen, activeSource } = useLayoutStore();

  return (
    <SidebarProvider className="h-full">
      <SidebarInset className="h-full">
        <div className="flex h-full w-full overflow-hidden bg-background">
          {/* Left Pane: Source List (Collapsible) */}
          <div
            className={cn(
              "border-r transition-all duration-300 ease-in-out",
              isSourceListOpen ? "w-64" : "w-0 opacity-0 overflow-hidden"
            )}
          >
            <SourceListPane />
          </div>

          {/* Center Pane: Source Viewer (Conditional) */}
          {activeSource && (
            <div className="flex-1 border-r min-w-0">
              <SourceViewerPane sourceId={activeSource} />
            </div>
          )}

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
