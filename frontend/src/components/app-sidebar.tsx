"use client";

import * as React from "react";
import Image from "next/image";
import { Settings2, Library, Trash2, ChevronRightIcon, MoreHorizontal, Share2, FileText } from "lucide-react";

import { NavMain } from "@/components/nav-main";
import { NavUser } from "@/components/nav-user";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
  useSidebar,
  SidebarMenuAction,
} from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import { useLayoutStore } from "@/lib/store/useLayoutStore";
import { api, Chat } from "@/lib/api";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ThemeCustomizer } from "./theme-customizer";
import { useDirection } from "@/components/direction-provider";
import { DirectionToggle } from "./direction-toggle";

// Static data for other sections
import { useAuthStore } from "@/lib/store/useAuthStore";
import { usePathname, useRouter } from "next/navigation";
import { LayoutDashboard, Users, MessageSquare, LogIn } from "lucide-react";

const data = {
  navMain: [
    {
      title: "חיפוש בתורה ",
      url: "/document-search",
      icon: FileText,
      items: [],
    },
  ],
  adminNavMain: [
    {
      title: "לוח בקרה",
      url: "/admin/dashboard",
      icon: LayoutDashboard,
      items: [],
    },
    {
      title: "משתמשים",
      url: "/admin/users",
      icon: Users,
      items: [],
    },
    {
      title: "שיחות",
      url: "/admin/chats",
      icon: MessageSquare,
      items: [],
    },
  ]
};

const CHAT_PAGE_SIZE = 20;
type FetchMode = "reset" | "append";

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { toggleSidebar, open: isSidebarOpen } = useSidebar();
  const { activeChatId, setActiveChatId } = useLayoutStore();
  const [chats, setChats] = React.useState<Chat[]>([]);
  const [isFetchingChats, setIsFetchingChats] = React.useState(false);
  const chatListRef = React.useRef<HTMLDivElement | null>(null);
  const paginationCursorRef = React.useRef<string | null>(null);
  const isFetchingRef = React.useRef(false);
  const previousChatIdRef = React.useRef<string | null | undefined>(undefined);
  const { direction } = useDirection();
  const isRTL = direction === "rtl";
  
  const user = useAuthStore((state) => state.user);
  const router = useRouter();
  const pathname = usePathname();
  const isAdminPath = pathname?.startsWith("/admin");

  const navItems = isAdminPath ? data.adminNavMain : data.navMain;

  const fetchChats = React.useCallback(async (mode: FetchMode = "reset") => {
    if (isFetchingRef.current) return;
    if (mode === "append" && !paginationCursorRef.current) return;

    isFetchingRef.current = true;
    setIsFetchingChats(true);

    try {
      const params = {
        limit: CHAT_PAGE_SIZE,
        cursor: paginationCursorRef.current ?? undefined,
      };
      if (mode === "reset") {
        paginationCursorRef.current = null;
        params.cursor = undefined;
      }

      const response = await api.getChats(params);
      setChats((prev) => {
        if (mode === "reset") return response.items;
        const existingIds = new Set(prev.map((chat) => chat.id));
        const deduped = response.items.filter(
          (chat) => !existingIds.has(chat.id)
        );
        return [...prev, ...deduped];
      });

      paginationCursorRef.current = response.nextCursor ?? null;

      if (mode === "reset") {
        requestAnimationFrame(() => {
          if (chatListRef.current) {
            chatListRef.current.scrollTop = 0;
          }
        });
      }
    } catch (error) {
      console.error("Failed to fetch chats", error);
    } finally {
      isFetchingRef.current = false;
      setIsFetchingChats(false);
    }
  }, []);

  React.useEffect(() => {
    // Only fetch chats if user is logged in
    if (!user) {
      setChats([]);
      return;
    }

    const normalizedChatId = activeChatId ?? null;
    if (
      previousChatIdRef.current !== undefined &&
      previousChatIdRef.current === normalizedChatId
    ) {
      return;
    }
    previousChatIdRef.current = normalizedChatId;
    fetchChats("reset");
  }, [activeChatId, fetchChats, user]);

  const handleNewChat = React.useCallback(() => {
    if (!user) {
      router.push("/login");
      return;
    }
    if (isAdminPath || pathname === '/document-search') {
      router.push("/");
    }
    setActiveChatId(null);
  }, [setActiveChatId, user, router, isAdminPath, pathname]);

  const handleSidebarToggle = React.useCallback(() => {
    toggleSidebar();
  }, [toggleSidebar]);

  const handleDeleteChat = React.useCallback(
    async (chatId: string) => {
      if (!confirm("Are you sure you want to delete this chat?")) return;
      await api.deleteChat(chatId);
      if (activeChatId === chatId) setActiveChatId(null);
      fetchChats("reset");
    },
    [activeChatId, fetchChats, setActiveChatId]
  );

  const handleShareChat = React.useCallback((chatId: string) => {
    const url = `${window.location.origin}?chatId=${chatId}`;
    navigator.clipboard.writeText(url);
    alert("Link copied to clipboard!"); // Fallback since no toast
  }, []);
  console.log(direction);

  const handleChatScroll = React.useCallback(() => {
    if (!chatListRef.current) return;
    if (!paginationCursorRef.current) return;
    if (isFetchingRef.current) return;
    const node = chatListRef.current;
    const reachedBottom =
      node.scrollTop + node.clientHeight >= node.scrollHeight - 48;
    if (reachedBottom) {
      fetchChats("append");
    }
  }, [fetchChats]);

  const logoButton = (
    <Button
    size="icon"
    aria-label="Toggle sidebar logo"
    onClick={handleSidebarToggle}
    className="h-9 w-9 rounded-md bg-transparent hover:bg-sidebar-accent cursor-pointer"
  >
    <Image
      src="/kesher.png"
      alt="Kesher"
      width={40}
      height={40}
      className="h-6 w-6 rounded-md object-cover hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground"
      priority
    />
  </Button>
);

  return (
    <Sidebar variant="floating" collapsible="icon" side={direction === "rtl" ? "right" : "left"} className="z-50 shadow-none" {...props}>
      <SidebarHeader>
        <div dir={direction} className="flex items-center justify-between gap-2">

          { logoButton}
          { isSidebarOpen && <SidebarTrigger
            aria-label="Toggle sidebar"
            className="size-8"/> }
        </div>
      </SidebarHeader>
      <SidebarContent className="flex h-full flex-col gap-4">
        <div className=" ">
          <NavMain items={navItems} handleNewChat={handleNewChat} direction={direction} />
        </div>
        { !isAdminPath && isSidebarOpen && <div className="flex min-h-0 flex-1 flex-col">
          <SidebarGroup className="flex h-full flex-col">
            <SidebarGroupLabel dir={direction} className=" font-semibold">
              שיחות קודמות
            </SidebarGroupLabel>
            <div
              className="min-h-0 flex-1 overflow-hidden rounded-2xl p-2"
              dir={direction}
            >
              <div
                ref={chatListRef}
                onScroll={handleChatScroll}
                className={`flex h-full flex-col gap-1 overflow-y-auto ${isRTL ? "pr-2 text-right" : "pl-2 text-left"}`}
              >
                <SidebarMenu className="space-y-1" dir={direction}>
                  {chats.map((chat) => (
                    <SidebarMenuItem key={`chat-${chat.id}`}>
                      <SidebarMenuButton
                        dir={direction}
                        onClick={() => {
                          if (pathname === '/document-search') {
                            router.push('/');
                          }
                          setActiveChatId(chat.id);
                        }}
                        isActive={activeChatId === chat.id}
                        className={`group justify-between gap-2 cursor-pointer ${isRTL ? "text-right" : "text-left"}`}
                      >
                        <span className="flex-1 truncate">{chat.title}</span>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <div role="button" className="opacity-0 transition-opacity group-hover:opacity-100 text-muted-foreground hover:text-foreground p-1 cursor-pointer">
                              <MoreHorizontal className="h-4 w-4" />
                              <span className="sr-only">More</span>
                            </div>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent
                            className="w-48"
                            side="bottom"
                            align="end"
                            >
                            <DropdownMenuItem
                              onClick={(e) => {
                                e.stopPropagation();
                                handleShareChat(chat.id);
                              }}
                              className="cursor-pointer"
                            >
                              <Share2 className="mr-2 h-4 w-4" />
                              <span>Share</span>
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDeleteChat(chat.id);
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
                  {!user && (
                    <div className="py-4 text-center text-sm text-muted-foreground">
                      Please login to view chats
                    </div>
                  )}
                </SidebarMenu>
                {isFetchingChats && (
                  <div className="py-2 text-center text-xs text-muted-foreground">
                    Loading chats...
                  </div>
                )}
              </div>
            </div>
          </SidebarGroup>
        </div> } 
      </SidebarContent>
      <SidebarFooter dir={direction}>
        <div className={`flex items-center gap-2 ${isRTL ? "justify-start" : "justify-start"}`}>
          {isSidebarOpen ? <DirectionToggle /> : null}
          {<ThemeCustomizer />}
        </div>
        {user ? (
          <NavUser user={{
            name: user.full_name || user.email.split('@')[0],
            email: user.email,
            avatar: user.avatar || "/avatars/shadcn.jpg",
            role: user.role
          }} />
        ) : (
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton asChild size="lg">
                <a href="/login">
                  <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                    <LogIn className="size-4" />
                  </div>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-semibold">Log in</span>
                    <span className="truncate text-xs">Sign in to your account</span>
                  </div>
                </a>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        )}
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
