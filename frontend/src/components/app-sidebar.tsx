"use client";

import * as React from "react";
import Image from "next/image";
import { Settings2, Library, Trash2, ChevronRightIcon, MoreHorizontal, Share2 } from "lucide-react";

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

// Static data for other sections
const data = {
  user: {
    name: "Daniel Benassaya",
    email: "daniel@talmudpedia.com",
    avatar: "/avatars/shadcn.jpg",
  },
  navMain: [
    {
      title: "Library",
      url: "#",
      icon: Library,
      items: [
        { title: "Talmud Bavli", url: "#" },
        { title: "Mishneh Torah", url: "#" },
        { title: "Shulchan Aruch", url: "#" },
      ],
    },
    {
      title: "Settings",
      url: "#",
      icon: Settings2,
      items: [
        { title: "General", url: "#" },
        { title: "Appearance", url: "#" },
      ],
    },
  ],
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
    const normalizedChatId = activeChatId ?? null;
    if (
      previousChatIdRef.current !== undefined &&
      previousChatIdRef.current === normalizedChatId
    ) {
      return;
    }
    previousChatIdRef.current = normalizedChatId;
    fetchChats("reset");
  }, [activeChatId, fetchChats]);

  const handleNewChat = React.useCallback(() => {
    setActiveChatId(null);
  }, [setActiveChatId]);

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
    className="h-9 w-9 rounded-md bg-transparent hover:bg-sidebar-accent"
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
    <Sidebar collapsible="icon" side="right" className="z-50" {...props}>
      <SidebarHeader>

        <div dir="rtl" className="flex items-center justify-between gap-2">
          { logoButton}
          { isSidebarOpen && <SidebarTrigger
            aria-label="Toggle sidebar"
            className="size-8"/> }
        </div>
      </SidebarHeader>
      <SidebarContent className="flex h-full flex-col gap-4">
        <div className=" ">
          <NavMain items={data.navMain} handleNewChat={handleNewChat} />
        </div>
        <div className="flex min-h-0 flex-1 flex-col">
          <SidebarGroup className="flex h-full flex-col">
            <SidebarGroupLabel dir="rtl" className=" font-semibold">
              שיחות קודמות
            </SidebarGroupLabel>
            <div
              className="min-h-0 flex-1 overflow-hidden rounded-2xl p-2"
              dir="rtl"
            >
              <div
                ref={chatListRef}
                onScroll={handleChatScroll}
                className="flex h-full flex-col gap-1 overflow-y-auto pr-2 text-right"
              >
                <SidebarMenu className="space-y-1" dir="rtl">
                  {chats.map((chat) => (
                    <SidebarMenuItem key={`chat-${chat.id}`}>
                      <SidebarMenuButton
                        onClick={() => setActiveChatId(chat.id)}
                        isActive={activeChatId === chat.id}
                        className="group justify-between gap-2 text-right"
                      >
                        <span className="flex-1 truncate">{chat.title}</span>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <div role="button" className="opacity-0 transition-opacity group-hover:opacity-100 text-muted-foreground hover:text-foreground p-1">
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
                            >
                              <Share2 className="mr-2 h-4 w-4" />
                              <span>Share</span>
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDeleteChat(chat.id);
                              }}
                            >
                              <Trash2 className="mr-2 h-4 w-4" />
                              <span>Delete</span>
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
                {isFetchingChats && (
                  <div className="py-2 text-center text-xs text-muted-foreground">
                    Loading chats...
                  </div>
                )}
              </div>
            </div>
          </SidebarGroup>
        </div>
      </SidebarContent>
      <SidebarFooter dir="rtl">
      <ThemeCustomizer />
        <NavUser user={data.user} />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
