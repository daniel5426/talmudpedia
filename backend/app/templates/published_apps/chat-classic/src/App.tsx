import { Bot, Loader2, Pencil, Plus, Terminal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { FloatingPanel } from "@/components/builder/FloatingPanel";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { DirectionProvider, useDirection } from "@/components/direction-provider";
import { MockExecutionSidebar } from "@/components/layout/MockExecutionSidebar";
import { PlaygroundChatWorkspace } from "@/components/layout/PlaygroundChatWorkspace";
import { AppSidebar } from "@/components/navigation/AppSidebar";
import { ThemeProvider } from "@/components/theme-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Conversation } from "@/components/ai-elements/conversation";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { useTemplateChat } from "@/hooks/use-template-chat";
import { cn } from "@/lib/utils";

const MOCK_AGENT_OPTIONS = [
  { id: "standard-agent", name: "Standard Agent", published: true },
  { id: "client-exposure", name: "Client Exposure Copilot", published: false },
];

function PlaygroundTemplatePage() {
  const {
    sessions,
    activeSession,
    activeSessionId,
    isStreaming,
    streamingAssistantId,
    runtimeError,
    textareaRef,
    selectSession,
    startNewChat,
    removeSession,
    shareSession,
    resendPrompt,
    copyMessage,
    handleSubmit,
    stopStreaming,
  } = useTemplateChat();
  const [isExecutionSidebarOpen, setIsExecutionSidebarOpen] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState(MOCK_AGENT_OPTIONS[0].id);
  const { direction } = useDirection();

  const orderedSessions = useMemo(
    () =>
      [...sessions].sort(
        (left, right) =>
          new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime(),
      ),
    [sessions],
  );

  useEffect(() => {
    document.title = activeSession?.title
      ? `${activeSession.title} | Agent Playground`
      : "Agent Playground";
  }, [activeSession?.title]);

  return (
    <SidebarProvider className="h-full bg-transparent" dir={direction}>
      <div className="relative flex h-full w-full overflow-hidden bg-background transition-colors duration-500">
        <div className="relative z-10">
          <AppSidebar
            sessions={orderedSessions}
            activeSessionId={activeSessionId}
            onNewChat={startNewChat}
            onSelectSession={selectSession}
            onDeleteSession={removeSession}
            onShareSession={shareSession}
          />
        </div>

        <SidebarInset className="relative z-10 h-full min-w-0 flex-1 bg-transparent">
          <div className="flex h-full w-full flex-col overflow-hidden bg-background [&_button]:shadow-none">
            <AdminPageHeader>
              <div className="flex items-center gap-3">
                <CustomBreadcrumb
                  items={[
                    { label: "Agents Management", href: "#" },
                    { label: "Playground", active: true },
                  ]}
                />
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md border bg-background/90 text-xs font-medium text-foreground backdrop-blur transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => setIsExecutionSidebarOpen((prev) => !prev)}
                  aria-label={isExecutionSidebarOpen ? "Hide execution traces" : "Show execution traces"}
                >
                  <Terminal className="h-3.5 w-3.5" />
                </button>

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      className="inline-flex h-8 w-8 items-center justify-center rounded-md border bg-background/90 text-xs font-medium text-foreground backdrop-blur transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
                      aria-label="Show history"
                    >
                      <Loader2 className={cn("h-3.5 w-3.5", sessions.length ? "hidden" : "block")} />
                      <span className={cn("text-sm", sessions.length ? "block" : "hidden")}>+</span>
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="max-h-[360px] w-[320px] overflow-y-auto">
                    <DropdownMenuItem onClick={startNewChat}>
                      <Plus className="mr-2 size-4" />
                      New Thread
                    </DropdownMenuItem>
                    {orderedSessions.map((session) => (
                      <DropdownMenuItem key={session.id} onClick={() => selectSession(session.id)}>
                        <div className="flex min-w-0 flex-col">
                          <span className="truncate font-medium">{session.title}</span>
                          <span className="truncate text-xs text-muted-foreground">
                            {new Date(session.updatedAt).toLocaleString()}
                          </span>
                        </div>
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>

                <Button variant="outline" size="icon" className="h-8 w-8" disabled aria-label="Edit agent" title="Edit agent">
                  <Pencil className="size-3.5" />
                </Button>

                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 gap-1.5"
                  onClick={startNewChat}
                >
                  <Plus className="size-3.5" />
                  <span>New Thread</span>
                </Button>

                <Select value={selectedAgentId} onValueChange={setSelectedAgentId}>
                  <SelectTrigger className="h-9 w-[200px] gap-2 border-none bg-muted/50 transition-colors hover:bg-muted">
                    <Bot className="size-3.5 text-primary" />
                    <SelectValue placeholder="Select Agent" />
                  </SelectTrigger>
                  <SelectContent className="max-h-[320px] w-[280px]">
                    {MOCK_AGENT_OPTIONS.map((agent) => (
                      <SelectItem key={agent.id} value={agent.id}>
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{agent.name}</span>
                          {agent.published ? (
                            <Badge variant="secondary" className="h-3 px-1 text-[8px]">
                              PUB
                            </Badge>
                          ) : null}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </AdminPageHeader>

            <main className="relative flex-1 overflow-hidden">
              <div
                className={cn(
                  "flex h-full overflow-hidden transition-[padding] duration-300",
                  isExecutionSidebarOpen && "lg:pr-[332px]",
                )}
              >
                <div className="flex min-w-0 flex-1">
                  <Conversation
                    dir={direction}
                    className="relative flex min-h-full flex-1 flex-col overflow-hidden border-none"
                    data-admin-page-scroll
                    style={{ background: "var(--chat-background)" }}
                  >
                    <PlaygroundChatWorkspace
                      activeSession={activeSession}
                      activeSessionId={activeSessionId}
                      isStreaming={isStreaming}
                      streamingAssistantId={streamingAssistantId}
                      runtimeError={runtimeError}
                      textareaRef={textareaRef}
                      onSubmit={handleSubmit}
                      onStop={stopStreaming}
                      onCopy={copyMessage}
                      onRetry={resendPrompt}
                      onShareChat={shareSession}
                      onDeleteChat={removeSession}
                    />
                  </Conversation>
                </div>
              </div>

              <FloatingPanel
                position="right"
                visible={Boolean(isExecutionSidebarOpen)}
                className="z-30 hidden w-80 lg:block"
                fullHeight={false}
              >
                <MockExecutionSidebar className="w-full" />
              </FloatingPanel>
            </main>
          </div>
        </SidebarInset>
      </div>
    </SidebarProvider>
  );
}

export function App() {
  return (
    <ThemeProvider>
      <DirectionProvider initialDirection="ltr">
        <PlaygroundTemplatePage />
      </DirectionProvider>
    </ThemeProvider>
  );
}
