"use client";

import * as React from "react";
import Image from "next/image";
import { Settings2, Bot, Library, Trash2, ChevronRightIcon, MoreHorizontal, Share2, FileText, LayoutDashboard, Users, MessageSquare, LogIn, Database, ShieldCheck, History, Landmark, Workflow, Settings, Play, Code2 } from "lucide-react";

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
import { chatService, Chat } from "@/services";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ThemeCustomizer } from "./theme-customizer";
import { useDirection } from "@/components/direction-provider";
import { DirectionToggle } from "./direction-toggle";
import { LibraryMenu } from "@/components/library-menu";
import { TenantSwitcher } from "@/components/tenant-switcher";
import { useAuthStore } from "@/lib/store/useAuthStore";
import { usePathname, useRouter } from "next/navigation";

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
      title: "Organization",
      url: "/admin/organization",
      icon: Landmark,
      items: [],
    },
    {
      title: "Security & Roles",
      url: "/admin/security",
      icon: ShieldCheck,
      items: [],
    },
    {
      title: "Audit Logs",
      url: "/admin/audit",
      icon: History,
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
    {
      title: "RAG Management",
      url: "/admin/rag",
      icon: Database,
      items: [
        {
          title: "Dashboard",
          url: "/admin/rag",
          icon: LayoutDashboard,
        },
        {
          title: "Pipeline Builder",
          url: "/admin/pipelines",
          icon: Workflow,
        },
        {
          title: "Operators",
          url: "/admin/rag/operators",
          icon: Code2,
        },
      ],
    },
    {
      title: "Agents Management",
      url: "/admin/agents",
      icon: Bot,
      items: [
        {
          title: "All Agents",
          url: "/admin/agents",
          icon: Bot,
        },
        {
          title: "Playground",
          url: "/admin/agents/playground",
          icon: Play,
        },
        {
          title: "Models Registry",
          url: "/admin/models",
          icon: Database,
        },
        {
          title: "Tools Registry",
          url: "/admin/tools",
          icon: Settings2,
        },
      ],
    },
  ]
};

const CHAT_PAGE_SIZE = 20;
type FetchMode = "reset" | "append";

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { toggleSidebar, open: isSidebarOpen, openMobile, isMobile } = useSidebar();
  const { activeChatId, setActiveChatId } = useLayoutStore();
  const [chats, setChats] = React.useState<Chat[]>([]);
  const [isFetchingChats, setIsFetchingChats] = React.useState(false);
  const chatListRef = React.useRef<HTMLDivElement | null>(null);
  const paginationCursorRef = React.useRef<string | null>(null);
  const isFetchingRef = React.useRef(false);
  const previousChatIdRef = React.useRef<string | null | undefined>(undefined);
  const { direction } = useDirection();
  const isRTL = direction === "rtl";
  const { isLibraryMode, setLibraryMode } = useLayoutStore();

  const user = useAuthStore((state) => state.user);
  const router = useRouter();
  const pathname = usePathname();
  const isAdminPath = pathname?.startsWith("/admin");

  const navItems = React.useMemo(() => {
    const rawItems = isAdminPath ? data.adminNavMain : data.navMain;
    return rawItems.map(item => ({
      ...item,
      isActive: pathname === item.url || (item.items?.some(sub => {
        if (sub.title === "Playground" && pathname?.includes("/admin/agents/playground")) return true;
        return pathname === sub.url;
      }) ?? false),
      items: item.items?.map(sub => {
        const isPlayground = sub.title === "Playground";
        const isActive = isPlayground ? pathname?.includes("/admin/agents/playground") : pathname === sub.url;

        return {
          ...sub,
          isActive: !!isActive
        };
      })
    }));
  }, [isAdminPath, pathname]);

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

      const response = await chatService.list(params);
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
      router.push("/auth/login");
      return;
    }
    if (pathname !== '/chat') {
      router.push("/chat");
    }
    setActiveChatId(null);
  }, [setActiveChatId, user, router, pathname]);

  const handleSidebarToggle = React.useCallback(() => {
    toggleSidebar();
  }, [toggleSidebar]);

  const handleDeleteChat = React.useCallback(
    async (chatId: string) => {
      if (!confirm("Are you sure you want to delete this chat?")) return;
      await chatService.delete(chatId);
      if (activeChatId === chatId) setActiveChatId(null);
      fetchChats("reset");
    },
    [activeChatId, fetchChats, setActiveChatId]
  );

  const handleShareChat = React.useCallback((chatId: string) => {
    const url = chatService.getShareUrl(chatId);
    navigator.clipboard.writeText(url);
    alert("Link copied to clipboard!");
  }, []);

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
    <Sidebar collapsible="icon" side={direction === "rtl" ? "right" : "left"} className="z-50 shadow-none border" {...props}>
      <SidebarHeader>
        <div dir={direction} className="flex items-center justify-between gap-2">
          {logoButton}
          {(isSidebarOpen || openMobile) && <SidebarTrigger
            aria-label="Toggle sidebar"
            className="size-8" />}
        </div>
      </SidebarHeader>
      <SidebarContent className="flex h-full flex-col gap-4">
        {isLibraryMode ? (
          <LibraryMenu onBack={() => setLibraryMode(false)} />
        ) : (
          <>
            {user && (user.role === "admin" || isAdminPath) && (
              <div className="px-2 pt-2">
                <TenantSwitcher />
              </div>
            )}
            <div className=" ">
              <NavMain
                items={navItems}
                handleNewChat={handleNewChat}
                handleLibraryToggle={() => setLibraryMode(true)}
                direction={direction}
              />
            </div>
            {!isAdminPath && isSidebarOpen && <div className="flex min-h-0 flex-1 flex-col">
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
                              router.push(`/chat?chatId=${chat.id}`);
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
            </div>}
          </>
        )}
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
            role: user.role,
            org_role: user.org_role
          }} />
        ) : (
          <SidebarMenu dir={direction}>
            <SidebarMenuItem>
              <SidebarMenuButton dir={direction} asChild size="lg" className={`${isRTL ? "rtl" : "ltr"}`}>
                <a href="/auth/login" dir={direction} className={`${isRTL ? "rtl" : "ltr"}`}>
                  <div dir={direction} className={`grid flex-1  text-sm leading-tight ${isRTL ? "text-right" : "text-left"}`}>
                    <span className="truncate font-semibold" >התחברות</span>
                    <span className="truncate text-xs">התחבר לחשבון שלך</span>
                  </div>
                  <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                    <LogIn className="size-4" />
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
