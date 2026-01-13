"use client";

import { useEffect, useState } from "react";
import { MessageSquare, MoreHorizontal, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { chatService } from "@/services";
import { Chat } from "@/services/types";
import { useLayoutStore } from "@/lib/store/useLayoutStore";

import {
    SidebarGroup,
    SidebarGroupLabel,
    SidebarMenu,
    SidebarMenuAction,
    SidebarMenuButton,
    SidebarMenuItem,
    useSidebar,
} from "@/components/ui/sidebar";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export function NavHistory() {
    const [chats, setChats] = useState<Chat[]>([]);
    const pathname = usePathname();
    const router = useRouter();
    const { isMobile } = useSidebar();
    const activeChatId = useLayoutStore((state) => state.activeChatId);

    useEffect(() => {
        chatService.list({ limit: 20 }).then((res) => {
            setChats(res.items || []);
        }).catch(err => {
            console.error("Failed to fetch chats", err);
        });
    }, [activeChatId]);

    const handleDelete = async (id: string) => {
        try {
            await chatService.delete(id);
            setChats((prev) => prev.filter((c) => c.id !== id));
            if (activeChatId === id) {
                router.push("/chat");
            }
        } catch (error) {
            console.error("Failed to delete chat", error);
        }
    };

    return (
        <SidebarGroup>
            <SidebarGroupLabel dir="rtl">שיחות אחרונות</SidebarGroupLabel>
            <SidebarMenu>
                {chats.map((item) => (
                    <SidebarMenuItem key={item.id} dir="rtl">
                        <SidebarMenuButton asChild isActive={activeChatId === item.id}>
                            <Link href={`/chat?chatId=${item.id}`}>
                                <MessageSquare className="h-4 w-4" />
                                <span>{item.title || "שיחה ללא כותרת"}</span>
                            </Link>
                        </SidebarMenuButton>
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <SidebarMenuAction showOnHover>
                                    <MoreHorizontal />
                                    <span className="sr-only">עוד</span>
                                </SidebarMenuAction>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent
                                className="w-48 rounded-lg"
                                side={isMobile ? "bottom" : "right"}
                                align={isMobile ? "end" : "start"}
                            >
                                <DropdownMenuItem onClick={() => handleDelete(item.id)} className="text-destructive focus:text-destructive cursor-pointer">
                                    <Trash2 className="ml-2 h-4 w-4" />
                                    <span>מחק שיחה</span>
                                </DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    </SidebarMenuItem>
                ))}
            </SidebarMenu>
        </SidebarGroup>
    );
}
