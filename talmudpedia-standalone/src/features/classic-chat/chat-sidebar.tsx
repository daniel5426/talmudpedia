import * as React from "react";
import {
  ChevronsUpDown,
  MoreHorizontal,
  PenSquare,
  RefreshCcw,
  Share2,
  Trash2,
} from "lucide-react";

import {
  Avatar,
  AvatarFallback,
  AvatarImage,
} from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";

import { useSession } from "./session-context";
import type { TemplateThread } from "./types";

type ChatSidebarProps = {
  activeThreadId: string;
  hasMoreHistory: boolean;
  onLoadMoreHistory: () => void;
  onNewChat: () => void;
  onSelectThread: (threadId: string) => void;
  threads: TemplateThread[];
};

export function ChatSidebar({
  activeThreadId,
  hasMoreHistory,
  onLoadMoreHistory,
  onNewChat,
  onSelectThread,
  threads,
}: ChatSidebarProps) {
  const { isLoading, resetSession, session } = useSession();

  const { open, openMobile, isMobile } = useSidebar();
  const isExpanded = open || openMobile;
  const chatListRef = React.useRef<HTMLDivElement | null>(null);

  const fallbackInitials = session?.displayName
    ? session.displayName.slice(0, 2).toUpperCase()
    : "LU";

  const handleChatScroll = React.useCallback(() => {
    if (!chatListRef.current || !hasMoreHistory) return;
    const node = chatListRef.current;
    const reachedBottom =
      node.scrollTop + node.clientHeight >= node.scrollHeight - 48;
    if (reachedBottom) {
      onLoadMoreHistory();
    }
  }, [hasMoreHistory, onLoadMoreHistory]);

  return (
    <Sidebar collapsible="icon" className="z-50 shadow-none">
      <SidebarHeader>
        <div
          className={`flex items-center gap-1 p-2 ${
            isExpanded ? "justify-between" : "justify-center"
          }`}
        >
          {isExpanded ? (
            <div className="flex-1 overflow-hidden">
              <p className="truncate text-xs font-semibold uppercase tracking-[0.18em] text-sidebar-foreground/55">
                Talmudpedia Standalone
              </p>
            </div>
          ) : null}
          <SidebarTrigger aria-label="Toggle sidebar" className="size-8" />
        </div>
      </SidebarHeader>

      <SidebarContent className="flex h-full flex-col gap-4">
        <SidebarGroup>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                onClick={onNewChat}
                className="cursor-pointer"
                tooltip="New chat"
              >
                <PenSquare className="size-4" />
                <span>New chat</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>

        {isExpanded ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <SidebarGroup className="flex h-full flex-col">
              <SidebarGroupLabel className="font-semibold">
                Previous Chats
              </SidebarGroupLabel>
              <div className="min-h-0 flex-1 overflow-hidden rounded-2xl p-2">
                <div
                  ref={chatListRef}
                  onScroll={handleChatScroll}
                  className="flex h-full flex-col gap-1 overflow-y-auto pl-2 text-left"
                >
                  <SidebarMenu className="space-y-1">
                    {threads.map((thread) => (
                      <SidebarMenuItem key={thread.id}>
                        <SidebarMenuButton
                          onClick={() => onSelectThread(thread.id)}
                          isActive={activeThreadId === thread.id}
                          className="group justify-between gap-2 cursor-pointer"
                        >
                          <span className="flex-1 truncate">{thread.title}</span>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <div
                                role="button"
                                className="cursor-pointer p-1 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-foreground"
                              >
                                <MoreHorizontal className="h-4 w-4" />
                                <span className="sr-only">More</span>
                              </div>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent className="w-44" side="bottom" align="end">
                              <DropdownMenuItem className="cursor-pointer">
                                <Share2 className="mr-2 h-4 w-4" />
                                <span>Share</span>
                              </DropdownMenuItem>
                              <DropdownMenuItem className="cursor-pointer text-destructive focus:text-destructive">
                                <Trash2 className="mr-2 h-4 w-4" />
                                <span>Delete</span>
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    ))}
                  </SidebarMenu>
                  {hasMoreHistory ? (
                    <div className="py-2 text-center text-xs text-muted-foreground">
                      Loading more chats...
                    </div>
                  ) : null}
                </div>
              </div>
            </SidebarGroup>
          </div>
        ) : null}
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton
                  size="lg"
                  className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground cursor-pointer"
                  tooltip={session?.displayName || "Local user"}
                >
                  <Avatar className="h-8 w-8 rounded-lg shrink-0">
                    <AvatarImage src="" alt={session?.displayName || "Local user"} />
                    <AvatarFallback className="rounded-lg bg-sidebar-primary text-sidebar-primary-foreground text-xs font-medium">
                      {fallbackInitials}
                    </AvatarFallback>
                  </Avatar>
                  <div className="grid flex-1 text-sm leading-tight text-left">
                    <span className="truncate font-medium">
                      {isLoading ? "Loading local session..." : session?.displayName || "Local user"}
                    </span>
                    <span className="truncate text-xs text-muted-foreground">
                      {session?.userId || "Cookie-backed development identity"}
                    </span>
                  </div>
                  <ChevronsUpDown className="ml-auto size-4 shrink-0" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg"
                side={isMobile ? "bottom" : "right"}
                align="end"
                sideOffset={4}
              >
                <DropdownMenuLabel className="p-0 font-normal">
                  <div className="flex items-center gap-2 px-1 py-1.5 text-sm text-left">
                    <Avatar className="h-8 w-8 rounded-lg">
                      <AvatarImage src="" alt={session?.displayName || "Local user"} />
                      <AvatarFallback className="rounded-lg bg-sidebar-primary text-sidebar-primary-foreground text-xs font-medium">
                        {fallbackInitials}
                      </AvatarFallback>
                    </Avatar>
                    <div className="grid flex-1 text-sm leading-tight text-left">
                      <span className="truncate font-medium">{session?.displayName || "Local user"}</span>
                      <span className="truncate text-xs">{session?.userId || "Pending session"}</span>
                    </div>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuGroup>
                  <DropdownMenuItem
                    className="cursor-pointer"
                    onClick={() => {
                      void resetSession().then(() => {
                        window.location.reload();
                      });
                    }}
                  >
                    <RefreshCcw className="mr-2 size-4" />
                    Reset local session
                  </DropdownMenuItem>
                </DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  );
}
