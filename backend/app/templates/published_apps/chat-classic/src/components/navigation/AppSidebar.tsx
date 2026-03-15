import {
  EditIcon,
  MoreHorizontal,
  Share2,
  Trash2,
} from "lucide-react";

import { useDirection } from "@/components/direction-provider";
import { ThemeCustomizer } from "@/components/theme-customizer";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
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
import type { StoredChatSession } from "@/hooks/use-template-chat";

type AppSidebarProps = {
  sessions: StoredChatSession[];
  activeSessionId: string | null;
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onShareSession: (sessionId: string) => void;
};

export function AppSidebar({
  sessions,
  activeSessionId,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onShareSession,
}: AppSidebarProps) {
  const { open: isSidebarOpen, openMobile } = useSidebar();
  const { direction } = useDirection();
  const isRTL = direction === "rtl";

  return (
    <Sidebar
      variant="floating"
      collapsible="icon"
      side={isRTL ? "right" : "left"}
      className="z-50"
    >
      <SidebarHeader>
        <div
          dir={direction}
          className={`flex items-center gap-1 p-2 ${(isSidebarOpen || openMobile) ? "justify-between" : "justify-center"}`}
        >
          {(isSidebarOpen || openMobile) ? (
            <div className="min-w-0 px-2">
              <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-muted-foreground">
                Agent Template
              </p>
            </div>
          ) : null}
          <SidebarTrigger aria-label="Toggle sidebar" className="size-8" />
        </div>
      </SidebarHeader>
      <SidebarContent className="flex h-full flex-col gap-4">
        <SidebarGroup dir={direction}>
          <SidebarGroupLabel dir={direction}>Platform</SidebarGroupLabel>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                onClick={onNewChat}
                className="cursor-pointer"
                tooltip="New Chat"
              >
                <EditIcon className="h-4 w-4" />
                <span>New Chat</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>
        {isSidebarOpen ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <SidebarGroup className="flex h-full flex-col">
              <SidebarGroupLabel dir={direction} className="font-semibold">
                Previous Chats
              </SidebarGroupLabel>
              <div className="min-h-0 flex-1 overflow-hidden rounded-2xl p-2" dir={direction}>
                <div
                  className={`flex h-full flex-col gap-1 overflow-y-auto ${isRTL ? "pr-2 text-right" : "pl-2 text-left"}`}
                >
                  <SidebarMenu className="space-y-1" dir={direction}>
                    {sessions.length === 0 ? (
                      <div className="rounded-2xl border border-dashed border-border/70 px-4 py-6 text-sm text-muted-foreground">
                        Your saved local conversations will appear here.
                      </div>
                    ) : (
                      sessions.map((session) => (
                        <SidebarMenuItem key={session.id}>
                          <SidebarMenuButton
                            dir={direction}
                            onClick={() => onSelectSession(session.id)}
                            isActive={activeSessionId === session.id}
                            className={`group justify-between gap-2 cursor-pointer ${isRTL ? "text-right" : "text-left"}`}
                          >
                            <span className="flex min-w-0 flex-1 flex-col">
                              <span className="truncate">{session.title}</span>
                              <span className="truncate text-[11px] text-muted-foreground">
                                {new Date(session.updatedAt).toLocaleDateString()}
                              </span>
                            </span>
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
                              <DropdownMenuContent className="w-48" side="bottom" align="end">
                                <DropdownMenuItem
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    onShareSession(session.id);
                                  }}
                                  className="cursor-pointer"
                                >
                                  <Share2 className="mr-2 h-4 w-4" />
                                  <span>Share</span>
                                </DropdownMenuItem>
                                <DropdownMenuItem
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    onDeleteSession(session.id);
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
                      ))
                    )}
                  </SidebarMenu>
                </div>
              </div>
            </SidebarGroup>
          </div>
        ) : null}
      </SidebarContent>
      <SidebarFooter dir={direction}>
        <div className="flex items-center gap-2">
          <ThemeCustomizer />
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
