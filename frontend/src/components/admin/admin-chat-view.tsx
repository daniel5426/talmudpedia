"use client"

import { useEffect } from "react"
import { useLayoutStore } from "@/lib/store/useLayoutStore"
import { ChatPane } from "@/components/layout/ChatPane"
import { SourceListPane } from "@/components/layout/SourceListPane"
import { SourceViewerPane } from "@/components/layout/SourceViewerPane"
import { cn } from "@/lib/utils"
import { GripVertical } from "lucide-react"
import React from "react"
import { CustomBreadcrumb, BreadcrumbItemProps } from "@/components/ui/custom-breadcrumb"
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "../ui/sheet"
import { useDirection } from "../direction-provider"
import { useIsMobile } from "@/hooks/use-mobile"
interface AdminChatViewProps {
  chatId: string
  breadcrumbs: BreadcrumbItemProps[]
}

export function AdminChatView({ chatId, breadcrumbs }: AdminChatViewProps) {
  const { setActiveChatId, isSourceListOpen, activeSource, sourceViewerWidth, setSourceViewerWidth, toggleSourceList } = useLayoutStore()
  const [lastActiveSource, setLastActiveSource] = React.useState<string | null>(null)
  const [isResizing, setIsResizing] = React.useState(false)
  const sourceViewerRef = React.useRef<HTMLDivElement>(null)
  const pendingWidthRef = React.useRef<number | null>(null)
  const { direction } = useDirection()
  const isMobile = useIsMobile()  
  useEffect(() => {
    if (chatId) {
      setActiveChatId(chatId)
    }
    return () => setActiveChatId(null)
  }, [chatId, setActiveChatId])

  useEffect(() => {
    if (activeSource) {
      setLastActiveSource(activeSource)
    }
  }, [activeSource])

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing || !sourceViewerRef.current) return
      
      const sidebarOffset = isSourceListOpen ? 256 : 0
      const newWidth = e.clientX - sidebarOffset
      
      if (newWidth >= 400 && newWidth <= 1200) {
        sourceViewerRef.current.style.width = `${newWidth}px`
        pendingWidthRef.current = newWidth
      }
    }

    const handleMouseUp = () => {
      if (pendingWidthRef.current !== null) {
        setSourceViewerWidth(pendingWidthRef.current)
        pendingWidthRef.current = null
      }
      setIsResizing(false)
    }

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = 'ew-resize'
      document.body.style.userSelect = 'none'
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isResizing, setSourceViewerWidth, isSourceListOpen])

  return (
    <div className="flex flex-col h-full w-full">
       <div className="p-4 border-b shrink-0">
          <CustomBreadcrumb items={breadcrumbs} />
       </div>
       <div className="flex-1 flex overflow-hidden min-h-0">
                    {/* Chat Pane */}
                    <div className="flex-1 min-w-0 flex flex-col min-h-0">
             <ChatPane noHeader={true} />
          </div>

            {/* Center Pane: Source Viewer (Collapsible / Non-Mobile only) */}
            {!isMobile && (
              <div
                ref={sourceViewerRef}
                className={cn(
                  "shrink-0 min-w-0 z-50 overflow-hidden relative",
                  !isResizing && "transition-all duration-300 ease-in-out",
                  activeSource ? "opacity-100" : "opacity-0"
                )}
                style={{ 
                  width: activeSource ? sourceViewerWidth : 0,
                  willChange: isResizing ? 'width' : 'auto'
                }}
              >
                <SourceViewerPane 
                  sourceId={activeSource || lastActiveSource} 
                />
                
                {/* Resize Handle */}
                {activeSource && (
                  <div
                    className="absolute z-52 right-0 top-0 bottom-0 w-[0.9px] bg-border cursor-ew-resize flex items-center justify-center group"
                    onMouseDown={() => setIsResizing(true)}
                  >
                    <div className="absolute inset-y-0 -left-1 -right-1" />
                    <GripVertical className="h-4 z-52 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                )}
              </div>
            )}

            {isMobile ? (
              <Sheet open={isSourceListOpen} onOpenChange={toggleSourceList}>
                <SheetContent side={direction === "rtl" ? "right" : "left"} className="p-0 sm:max-w-xs w-[85%]">
                  <SheetHeader className="sr-only">
                    <SheetTitle>רשימת מקורות</SheetTitle>
                  </SheetHeader>
                  <SourceListPane />
                </SheetContent>
              </Sheet>
            ) : (
              <div
                className={cn(
                  " transition-all duration-300 ease-in-out h-full",
                  isSourceListOpen ? "w-64 border-r" : "w-0 opacity-0 overflow-hidden"
                )}
              >
                <SourceListPane />
              </div>
            )}

       </div>
    </div>
  )
}
