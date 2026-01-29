"use client"
import { ChatWorkspace } from "@/components/layout/ChatPane"
import { Conversation } from "@/components/ai-elements/conversation"
import { useDirection } from "@/components/direction-provider"
import { cn } from "@/lib/utils"
import { ChatController } from "@/components/layout/useChatController"

interface ExecutionPanelProps {
    controller: ChatController
    className?: string
}

export function ExecutionPanel({ controller, className }: ExecutionPanelProps) {
    const { direction } = useDirection()

    return (
        <div className={cn("flex flex-col h-full bg-background w-full overflow-hidden", className)}>
            <div className="flex-1 relative border-none flex min-h-full flex-col overflow-hidden bg-(--chat-background)">
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
