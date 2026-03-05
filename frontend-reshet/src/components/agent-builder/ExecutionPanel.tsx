"use client"
import { ChatWorkspace } from "@/components/layout/ChatPane"
import { Conversation } from "@/components/ai-elements/conversation"
import { useDirection } from "@/components/direction-provider"
import { cn } from "@/lib/utils"
import { ChatController } from "@/components/layout/useChatController"
import { Plus } from "lucide-react"
import { ExecutionHistoryDropdown } from "./ExecutionHistoryDropdown"

interface ExecutionPanelProps {
    controller: ChatController
    className?: string
}

export function ExecutionPanel({ controller, className }: ExecutionPanelProps) {
    const { direction } = useDirection()
    const historyItems = (controller as any).history || []
    const historyLoading = (controller as any).historyLoading as boolean | undefined
    const startNewChat = (controller as any).startNewChat as (() => void) | undefined
    const loadHistoryChat = (controller as any).loadHistoryChat as ((item: any) => void) | undefined

    return (
        <div className={cn("flex flex-col h-full bg-background w-full overflow-hidden", className)}>
            <div className="flex-1 relative border-none flex min-h-full flex-col overflow-hidden bg-(--chat-background)">
                <div className="absolute top-3 left-3 z-20 flex items-center gap-2">
                    <button
                        type="button"
                        className="inline-flex items-center gap-1.5 rounded-md border bg-background/90 px-2.5 py-1 text-xs font-medium text-foreground backdrop-blur hover:bg-muted transition-colors"
                        onClick={() => startNewChat?.()}
                    >
                        <Plus className="h-3.5 w-3.5" />
                        New chat
                    </button>
                    <ExecutionHistoryDropdown
                        historyItems={historyItems}
                        loading={historyLoading}
                        onSelectHistory={(item) => loadHistoryChat?.(item)}
                        onStartNewChat={() => startNewChat?.()}
                    />
                </div>
                <Conversation
                    dir={direction}
                    className="flex-1 relative border-none flex min-h-full flex-col overflow-hidden"
                    targetScrollTop={controller.isLoading ? (_target: number, { scrollElement }: any) => scrollElement?.scrollTop ?? 0 : undefined}
                >
                    <ChatWorkspace
                        noBackground={true}
                        controller={controller}
                        isVoiceModeActive={false}
                        handleToggleVoiceMode={() => { }}
                    />
                </Conversation>
            </div>
        </div>
    )
}
