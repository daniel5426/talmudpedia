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
import { cn } from "@/lib/utils";

import { useLocale } from "./locale-context";
import { useSession } from "./session-context";
import type { TemplateThread } from "./types";

type ChatSidebarProps = {
  activeThreadId: string;
  hasMoreHistory: boolean;
  onLoadMoreHistory: () => void;
  onNewChat: () => void;
  onRemoveThread: (threadId: string) => void | Promise<void>;
  onSelectThread: (threadId: string) => void;
  threads: TemplateThread[];
};

export function ChatSidebar({
  activeThreadId,
  onNewChat,
  onRemoveThread,
  onSelectThread,
  threads,
}: ChatSidebarProps) {
  const { isRtl, locale } = useLocale();
  const { isLoading, resetSession, session } = useSession();

  const { open, openMobile, isMobile } = useSidebar();
  const isExpanded = open || openMobile;
  const chatListRef = React.useRef<HTMLDivElement | null>(null);

  const fallbackInitials = session?.displayName
    ? session.displayName.slice(0, 2).toUpperCase()
    : "LU";




  return (
    <Sidebar
      side={isRtl ? "right" : "left"}
      collapsible="icon"
      className={cn(
        "z-50 shadow-none",
        isRtl ? "border-l border-sidebar-border" : "border-r border-sidebar-border",
      )}
    >
      <SidebarHeader>
        <div
          className={`flex items-center gap-1 p-2 ${
            isExpanded ? "justify-between" : "justify-center"
          }`}
        >
          {isExpanded ? (
            <div className="flex-1 overflow-hidden flex items-center">
              <img src="/pricoLogo.png" alt="Prico AI Logo" className="h-6 w-auto object-contain" />
            </div>
          ) : null}
          <SidebarTrigger aria-label="Toggle sidebar" className="!size-8 cursor-pointer" />
        </div>
      </SidebarHeader>

      <SidebarContent className="flex h-full flex-col gap-4">
        <SidebarGroup>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                onClick={onNewChat}
                className={cn(
                  "cursor-pointer bg-[#E6C97A] hover:bg-[#C9A34D] text-[#0B2A5B] hover:text-[#0B2A5B] transition-colors",
                  locale === "he" ? "text-[0.90rem] font-medium leading-6" : "text-sm",
                )}
                tooltip={locale === "he" ? "צ'אט חדש" : "New chat"}
              >
                <PenSquare className="" />
                <span>{locale === "he" ? "צ'אט חדש" : "New chat"}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>

        {isExpanded ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <SidebarGroup className="flex h-full flex-col">
              <SidebarGroupLabel
                className={cn(
                  "font-semibold text-sidebar-foreground/80",
                  locale === "he" ? "text-[0.90rem] tracking-normal leading-6" : "text-xs uppercase tracking-[0.12em]",
                )}
              >
                {locale === "he" ? "צ'אטים קודמים" : "Previous Chats"}
              </SidebarGroupLabel>
              <div className="min-h-0 flex-1 overflow-hidden rounded-md p-2">
                <div
                  ref={chatListRef}
                  className={cn(
                    "flex h-full flex-col gap-1 overflow-y-auto pl-2 no-scrollbar",
                    isRtl ? "text-right" : "text-left",
                  )}
                >
                  <SidebarMenu className="space-y-1">
                    {threads.map((thread) => (
                      <SidebarMenuItem key={thread.id}>
                        <SidebarMenuButton
                          onClick={() => onSelectThread(thread.id)}
                          isActive={activeThreadId === thread.id}
                          className="group justify-between gap-2 cursor-pointer data-active:bg-muted data-active:text-sidebar-foreground hover:bg-muted/50 active:bg-muted active:text-sidebar-foreground"
                        >
                          <span className="flex-1 truncate">{thread.title}</span>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <div
                                role="button"
                                className="cursor-pointer p-1 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-foreground"
                              >
                                <MoreHorizontal className="h-4 w-4" />
                                <span className="sr-only">{locale === "he" ? "עוד" : "More"}</span>
                              </div>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent className="w-44" side="bottom" align="end">
                              <DropdownMenuItem className="cursor-pointer">
                                <Share2 className="mr-2 h-4 w-4" />
                                <span>{locale === "he" ? "שתף" : "Share"}</span>
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                className="cursor-pointer text-destructive focus:text-destructive"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  void onRemoveThread(thread.id);
                                }}
                              >
                                <Trash2 className="mr-2 h-4 w-4" />
                                <span>{locale === "he" ? "מחק" : "Delete"}</span>
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    ))}
                  </SidebarMenu>

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
                  tooltip={session?.displayName || (locale === "he" ? "משתמש מקומי" : "Local user")}
                >
                  <Avatar className="h-8 w-8 rounded-lg shrink-0">
                    <AvatarImage src="" alt={session?.displayName || (locale === "he" ? "משתמש מקומי" : "Local user")} />
                    <AvatarFallback className="rounded-lg bg-sidebar-primary text-sidebar-primary-foreground text-xs font-medium">
                      {fallbackInitials}
                    </AvatarFallback>
                  </Avatar>
                  <div className={cn("grid flex-1 text-sm leading-tight", isRtl ? "text-right" : "text-left")}>
                    <span className="truncate font-medium">
                      {isLoading
                        ? locale === "he"
                          ? "טוען סשן מקומי..."
                          : "Loading local session..."
                        : session?.displayName || (locale === "he" ? "משתמש מקומי" : "Local user")}
                    </span>
                    <span className="truncate text-xs text-muted-foreground">
                      {session?.userId || (locale === "he" ? "זהות פיתוח מבוססת קוקי" : "Cookie-backed development identity")}
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
                      <AvatarImage src="" alt={session?.displayName || (locale === "he" ? "משתמש מקומי" : "Local user")} />
                      <AvatarFallback className="rounded-lg bg-sidebar-primary text-sidebar-primary-foreground text-xs font-medium">
                        {fallbackInitials}
                      </AvatarFallback>
                    </Avatar>
                    <div className={cn("grid flex-1 text-sm leading-tight", isRtl ? "text-right" : "text-left")}>
                      <span className="truncate font-medium">
                        {session?.displayName || (locale === "he" ? "משתמש מקומי" : "Local user")}
                      </span>
                      <span className="truncate text-xs">
                        {session?.userId || (locale === "he" ? "סשן בהמתנה" : "Pending session")}
                      </span>
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
                    {locale === "he" ? "אפס סשן מקומי" : "Reset local session"}
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
