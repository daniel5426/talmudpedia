import { useMemo, useRef, useState } from "react";
import {
  Search,
  MoreHorizontal,
  Share2,
  Trash2,
  PanelLeft,
  EditIcon,
  Clock3,
} from "lucide-react";
import { createRuntimeClient, type RuntimeEvent } from "./runtime-sdk";
import { BotInputArea } from "./components/BotInputArea";
import {
  SidebarProvider,
  Sidebar,
  SidebarHeader,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarInset,
  SidebarTrigger,
  SidebarRail,
  useSidebar,
} from "./components/ui/sidebar";
import { Button } from "./components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./components/ui/dropdown-menu";
import {
  Message,
  MessageContent,
  MessageResponse,
  MessageActions,
  MessageAction,
} from "./components/ai-elements/message";
import {
  ChainOfThought,
  ChainOfThoughtHeader,
  ChainOfThoughtContent,
  ChainOfThoughtStep,
} from "./components/ai-elements/chain-of-thought";
import { DirectionProvider } from "./components/direction-provider";

type ReasoningStatus = "pending" | "complete" | "error";

type ReasoningStep = {
  id: string;
  label: string;
  status: ReasoningStatus;
  description?: string;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  reasoningSteps?: ReasoningStep[];
};

type SourceCitation = {
  title: string;
  excerpt?: string;
};

type RecentChat = {
  id: string;
  title: string;
  prompt: string;
};

const uid = () => Math.random().toString(36).slice(2, 10);

const truncate = (value: string, max: number): string => {
  const clean = value.trim();
  if (clean.length <= max) return clean;
  return `${clean.slice(0, max - 1)}…`;
};

const extractTokenChunk = (event: RuntimeEvent): string => {
  if (event.event === "token" && typeof event.data?.content === "string") {
    return event.data.content;
  }
  if (event.type === "token" && typeof event.content === "string") {
    return event.content;
  }
  return "";
};

const extractReasoningStep = (event: RuntimeEvent): ReasoningStep | null => {
  const kind = String(event.event || event.type || "").toLowerCase();
  const data = event.data || {};
  const statusRaw = typeof data.status === "string" ? data.status.toLowerCase() : "";

  const isReasoning =
    kind.includes("reason") ||
    kind.includes("think") ||
    kind.includes("retriev") ||
    kind.includes("tool") ||
    statusRaw === "pending" ||
    statusRaw === "complete";

  if (!isReasoning) return null;

  const label =
    (typeof data.label === "string" && data.label) ||
    (typeof data.stage === "string" && data.stage) ||
    (typeof data.tool === "string" && data.tool) ||
    "Reasoning";

  let status: ReasoningStatus = "pending";
  if (kind.includes("error") || statusRaw === "error") status = "error";
  else if (kind.includes("done") || kind.includes("complete") || statusRaw === "complete") status = "complete";

  const description =
    (typeof data.description === "string" && data.description) ||
    (typeof data.query === "string" && `Query: ${data.query}`) ||
    undefined;

  return {
    id: uid(),
    label,
    status,
    description,
  };
};

const extractSources = (event: RuntimeEvent): SourceCitation[] => {
  const data = event.data || {};
  const raw = (data.citations || data.sources || []) as Array<Record<string, unknown>>;
  if (!Array.isArray(raw)) return [];

  return raw.reduce<SourceCitation[]>((acc, item) => {
    const title =
      (typeof item.title === "string" && item.title) ||
      (typeof item.sourceRef === "string" && item.sourceRef) ||
      (typeof item.ref === "string" && item.ref) ||
      "";
    if (!title) return acc;

    const excerpt =
      (typeof item.description === "string" && item.description) ||
      (typeof item.excerpt === "string" && item.excerpt) ||
      undefined;
    acc.push({ title, excerpt });
    return acc;
  }, []);
};

const mergeReasoningSteps = (existing: ReasoningStep[] = [], incoming: ReasoningStep): ReasoningStep[] => {
  const idx = existing.findIndex((step) => step.label.toLowerCase() === incoming.label.toLowerCase());
  if (idx < 0) return [...existing, incoming];
  const next = [...existing];
  next[idx] = {
    ...next[idx],
    status: incoming.status,
    description: incoming.description || next[idx].description,
  };
  return next;
};

function MobileSidebarTrigger() {
  const { isMobile, openMobile, toggleSidebar } = useSidebar();

  if (!isMobile || openMobile) return null;

  return (
    <Button
      type="button"
      size="icon"
      variant="ghost"
      className="fixed right-3 top-3 z-[60] h-8 w-8 rounded-full border border-border bg-background shadow-sm md:hidden"
      onClick={() => toggleSidebar()}
      aria-label="Open sidebar"
    >
      <PanelLeft className="size-4" />
    </Button>
  );
}

function SidebarNavMain({
  onNewChat,
}: {
  onNewChat: () => void;
}) {
  return (
    <SidebarGroup>
      <SidebarGroupLabel>Platform</SidebarGroupLabel>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton className="cursor-pointer">
            <Search className="size-4" />
            <span>Search</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <SidebarMenuItem>
          <SidebarMenuButton onClick={onNewChat} className="cursor-pointer" tooltip="New Chat">
            <EditIcon className="size-4" />
            <span>New Chat</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarGroup>
  );
}

function TemplateSidebar({
  recentChats,
  onNewChat,
  onReplayChat,
  onCopyChat,
  onRemoveChat,
}: {
  recentChats: RecentChat[];
  onNewChat: () => void;
  onReplayChat: (chat: RecentChat) => void;
  onCopyChat: (chat: RecentChat) => void;
  onRemoveChat: (chat: RecentChat) => void;
}) {
  const { open: isSidebarOpen, openMobile } = useSidebar();
  const [activeRecentId, setActiveRecentId] = useState<string | null>(null);

  return (
    <Sidebar variant="floating" collapsible="icon" side="left" className="z-50">
      <SidebarHeader>
        <div className={`flex items-center gap-1 p-2 ${(isSidebarOpen || openMobile) ? "justify-between" : "justify-center"}`}>
          <SidebarTrigger aria-label="Toggle sidebar" className="size-8" />
        </div>
      </SidebarHeader>

      <SidebarContent className="flex h-full flex-col gap-4">
        <div className=" ">
          <SidebarNavMain onNewChat={onNewChat} />
        </div>

        {isSidebarOpen && (
          <div className="flex min-h-0 flex-1 flex-col">
            <SidebarGroup className="flex h-full flex-col">
              <SidebarGroupLabel className=" font-semibold">Previous Chats</SidebarGroupLabel>
              <div className="min-h-0 flex-1 overflow-hidden rounded-2xl p-2">
                <div className="flex h-full flex-col gap-1 overflow-y-auto pl-2 text-left">
                  <SidebarMenu className="space-y-1">
                    {recentChats.map((chat) => (
                      <SidebarMenuItem key={`chat-${chat.id}`}>
                        <SidebarMenuButton
                          onClick={() => {
                            setActiveRecentId(chat.id);
                            onReplayChat(chat);
                          }}
                          isActive={activeRecentId === chat.id}
                          className="group justify-between gap-2 cursor-pointer text-left"
                        >
                          <span className="flex-1 truncate">{chat.title}</span>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <div role="button" className="opacity-0 transition-opacity group-hover:opacity-100 text-muted-foreground hover:text-foreground p-1 cursor-pointer">
                                <MoreHorizontal className="h-4 w-4" />
                                <span className="sr-only">More</span>
                              </div>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent className="w-48" side="bottom" align="end">
                              <DropdownMenuItem
                                onClick={(event) => {
                                  event.stopPropagation();
                                  onCopyChat(chat);
                                }}
                                className="cursor-pointer"
                              >
                                <Share2 className="mr-2 h-4 w-4" />
                                <span>Share</span>
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                onClick={(event) => {
                                  event.stopPropagation();
                                  onRemoveChat(chat);
                                }}
                                className="cursor-pointer"
                              >
                                <Trash2 className="mr-2 h-4 w-4" />
                                <span>Delete</span>
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    ))}
                    {recentChats.length === 0 ? (
                      <div className="py-3 text-xs text-muted-foreground">No chats yet.</div>
                    ) : null}
                  </SidebarMenu>
                </div>
              </div>
            </SidebarGroup>
          </div>
        )}
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild size="lg">
              <button type="button" onClick={onNewChat}>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold">New Chat</span>
                  <span className="truncate text-xs">Start a fresh conversation</span>
                </div>
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                  <EditIcon className="size-4" />
                </div>
              </button>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}

export function App() {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sources, setSources] = useState<SourceCitation[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [chatId, setChatId] = useState<string | null>(null);
  const [hiddenRecentIds, setHiddenRecentIds] = useState<Set<string>>(new Set());

  const runtime = useMemo(() => createRuntimeClient(), []);

  const recentChats = useMemo<RecentChat[]>(() => {
    return messages
      .filter((msg) => msg.role === "user" && msg.content.trim().length > 0)
      .slice(-20)
      .reverse()
      .map((msg, idx) => ({
        id: msg.id,
        title: truncate(msg.content, 42) || `Chat ${idx + 1}`,
        prompt: msg.content,
      }))
      .filter((item) => !hiddenRecentIds.has(item.id));
  }, [messages, hiddenRecentIds]);

  const isEmptyState = messages.length === 0 && !isSending;

  const updateMessage = (id: string, updater: (value: ChatMessage) => ChatMessage) => {
    setMessages((prev) => prev.map((item) => (item.id === id ? updater(item) : item)));
  };

  const handleSubmit = async ({ text }: { text: string; files: Array<{ id: string; filename: string }> }) => {
    const prompt = text.trim();
    if (!prompt || isSending) return;

    const userId = uid();
    const assistantId = uid();

    setRuntimeError(null);
    setSources([]);
    setIsSending(true);

    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: prompt },
      { id: assistantId, role: "assistant", content: "", reasoningSteps: [] },
    ]);

    try {
      const result = await runtime.stream({ input: prompt, chat_id: chatId || undefined }, (event: RuntimeEvent) => {
        const chunk = extractTokenChunk(event);
        const reasoning = extractReasoningStep(event);
        const sourceHits = extractSources(event);

        if (event.type === "error") {
          setRuntimeError(event.content || "Runtime streaming error");
        }

        if (reasoning) {
          updateMessage(assistantId, (current) => ({
            ...current,
            reasoningSteps: mergeReasoningSteps(current.reasoningSteps || [], reasoning),
          }));
        }

        if (sourceHits.length > 0) {
          setSources((prev) => {
            const known = new Set(prev.map((item) => `${item.title}|${item.excerpt || ""}`));
            const next = [...prev];
            sourceHits.forEach((item) => {
              const key = `${item.title}|${item.excerpt || ""}`;
              if (!known.has(key)) {
                known.add(key);
                next.push(item);
              }
            });
            return next;
          });
        }

        if (!chunk) return;

        updateMessage(assistantId, (current) => ({
          ...current,
          content: `${current.content}${chunk}`,
        }));
      });

      if (result.chatId) setChatId(result.chatId);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to stream runtime response";
      setRuntimeError(message);
      updateMessage(assistantId, (current) => ({ ...current, content: message }));
    } finally {
      setIsSending(false);
    }
  };

  const handleNewChat = () => {
    setMessages([]);
    setSources([]);
    setRuntimeError(null);
    setChatId(null);
    setHiddenRecentIds(new Set());
  };

  return (
    <DirectionProvider initialDirection="ltr">
      <SidebarProvider defaultOpen className="h-full bg-transparent">
        <MobileSidebarTrigger />

        <div className="relative flex h-full w-full overflow-hidden bg-background">
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "radial-gradient(circle at 14% 18%, color-mix(in oklch, hsl(var(--tw-primary)) 8%, transparent), transparent 40%), radial-gradient(circle at 86% 8%, color-mix(in oklch, hsl(var(--tw-primary)) 10%, transparent), transparent 34%)",
            }}
          />

          <TemplateSidebar
            recentChats={recentChats}
            onNewChat={handleNewChat}
            onReplayChat={(chat) => {
              void handleSubmit({ text: chat.prompt, files: [] });
            }}
            onCopyChat={(chat) => {
              const payload = `Prompt:\n${chat.prompt}`;
              void navigator.clipboard.writeText(payload);
            }}
            onRemoveChat={(chat) => {
              setHiddenRecentIds((prev) => {
                const next = new Set(prev);
                next.add(chat.id);
                return next;
              });
            }}
          />

          <SidebarInset className="relative z-10 h-full flex-1 bg-transparent">
            <div className="flex h-full w-full flex-col overflow-hidden bg-transparent">
              {isEmptyState ? (
                <div className="mx-auto flex h-full w-full max-w-3xl flex-col items-center justify-center px-4 pb-24 text-center">
                  <p className="pb-6 text-3xl font-semibold">Ready when you are.</p>
                  <div className="w-full">
                    <BotInputArea textareaRef={textareaRef} handleSubmit={handleSubmit} isLoading={isSending} animate={false} />
                  </div>
                  {runtimeError ? (
                    <div className="mt-4 w-full rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                      {runtimeError}
                    </div>
                  ) : null}
                </div>
              ) : (
                <>
                  <section className="flex-1 overflow-y-auto px-4 pb-36 pt-6 md:px-6">
                    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
                      {messages.map((msg) => (
                        <Message
                          key={msg.id}
                          from={msg.role}
                          className={msg.role === "user" ? "max-w-none items-end" : "max-w-none"}
                        >
                          {msg.role === "assistant" && msg.reasoningSteps && msg.reasoningSteps.length > 0 ? (
                            <ChainOfThought>
                              <ChainOfThoughtHeader>Thinking</ChainOfThoughtHeader>
                              <ChainOfThoughtContent>
                                {msg.reasoningSteps.map((step) => (
                                  <ChainOfThoughtStep
                                    key={step.id}
                                    label={step.label}
                                    description={step.description}
                                    status={
                                      step.status === "error"
                                        ? "pending"
                                        : step.status === "complete"
                                          ? "complete"
                                          : "active"
                                    }
                                  />
                                ))}
                              </ChainOfThoughtContent>
                            </ChainOfThought>
                          ) : null}

                          <MessageContent>
                            <MessageResponse>{msg.content || (msg.role === "assistant" && isSending ? "Thinking..." : "")}</MessageResponse>
                          </MessageContent>

                          {msg.role === "assistant" ? (
                            <MessageActions>
                              <MessageAction onClick={() => void navigator.clipboard.writeText(msg.content || "")} label="Copy">
                                Copy
                              </MessageAction>
                              <MessageAction
                                onClick={() => void handleSubmit({ text: "Retry and improve the previous answer", files: [] })}
                                label="Retry"
                              >
                                <Clock3 className="size-4" />
                              </MessageAction>
                            </MessageActions>
                          ) : null}
                        </Message>
                      ))}

                      {sources.length > 0 ? (
                        <div className="rounded-xl border border-border bg-card/95 p-3">
                          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Sources</p>
                          <ul className="space-y-2">
                            {sources.slice(0, 8).map((source, idx) => (
                              <li key={`${source.title}-${idx}`} className="rounded-md border border-border/60 bg-background px-3 py-2">
                                <p className="text-sm font-medium">{source.title}</p>
                                {source.excerpt ? <p className="mt-1 text-xs text-muted-foreground">{source.excerpt}</p> : null}
                              </li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                    </div>
                  </section>

                  {runtimeError ? (
                    <div className="mx-4 mb-3 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive md:mx-6">
                      {runtimeError}
                    </div>
                  ) : null}

                  <footer className="absolute bottom-0 left-0 right-0 border-t border-border/80 bg-gradient-to-t from-background via-background/95 to-transparent">
                    <div className="mx-auto w-full max-w-3xl px-3 pb-3 pt-4 md:px-4 md:pb-4">
                      <BotInputArea textareaRef={textareaRef} handleSubmit={handleSubmit} isLoading={isSending} animate={false} />
                    </div>
                  </footer>
                </>
              )}
            </div>
          </SidebarInset>
        </div>
      </SidebarProvider>
    </DirectionProvider>
  );
}
