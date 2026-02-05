"use client"
import { ChatWorkspace } from "@/components/layout/ChatPane"
import { Conversation } from "@/components/ai-elements/conversation"
import { useDirection } from "@/components/direction-provider"
import { cn } from "@/lib/utils"
import { ChatController } from "@/components/layout/useChatController"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ChevronDown, Clock, Plus } from "lucide-react"

interface ExecutionPanelProps {
    controller: ChatController
    className?: string
}

export function ExecutionPanel({ controller, className }: ExecutionPanelProps) {
    const { direction } = useDirection()
    const historyItems = (controller as any).history || []
    const startNewChat = (controller as any).startNewChat as (() => void) | undefined
    const loadHistoryChat = (controller as any).loadHistoryChat as ((item: any) => void) | undefined

    return (
        <div className={cn("flex flex-col h-full bg-background w-full overflow-hidden", className)}>
            <div className="flex-1 relative border-none flex min-h-full flex-col overflow-hidden bg-(--chat-background)">
                <div className="absolute top-3 left-3 z-20 flex items-center gap-2">
                    <button
                        type="button"
                        className="inline-flex items-center gap-1.5 rounded-md border bg-background/90 px-2.5 py-1 text-xs font-medium text-foreground shadow-sm backdrop-blur hover:bg-muted transition-colors"
                        onClick={() => startNewChat?.()}
                    >
                        <Plus className="h-3.5 w-3.5" />
                        New chat
                    </button>
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <button
                                type="button"
                                className="inline-flex items-center gap-1.5 rounded-md border bg-background/90 px-2.5 py-1 text-xs font-medium text-foreground shadow-sm backdrop-blur hover:bg-muted transition-colors"
                            >
                                <Clock className="h-3.5 w-3.5" />
                                History
                                <ChevronDown className="h-3 w-3 opacity-70" />
                            </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start" className="min-w-[220px]">
                            {historyItems.length === 0 ? (
                                <DropdownMenuItem disabled className="text-muted-foreground">
                                    No recent runs
                                </DropdownMenuItem>
                            ) : (
                                historyItems.map((item: any, index: number) => (
                                    <DropdownMenuItem
                                        key={item.id || index}
                                        onClick={() => loadHistoryChat?.(item)}
                                        className="flex flex-col items-start gap-1"
                                    >
                                        <span className="text-xs font-medium text-foreground">{item.title || "Chat"}</span>
                                        <span className="text-[11px] text-muted-foreground">
                                            {item.timestamp ? new Date(item.timestamp).toLocaleString() : "Recent"}
                                        </span>
                                    </DropdownMenuItem>
                                ))
                            )}
                            <DropdownMenuSeparator />
                            <DropdownMenuItem onClick={() => startNewChat?.()}>
                                Start new chat
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
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
