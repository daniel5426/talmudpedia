"use client";

import { ChevronLeft, EditIcon, type LucideIcon } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from "@/components/ui/sidebar";

export function NavMain({
  items,
  handleNewChat,
}: {
  items: {
    title: string;
    url: string;
    icon?: LucideIcon;
    isActive?: boolean;
    items?: {
      title: string;
      url: string;
    }[];
  }[];
  handleNewChat: () => void;
}) {
  return (
    <SidebarGroup>
      <SidebarGroupLabel dir="rtl">Platform</SidebarGroupLabel>
      <SidebarMenu>
        {items.map((item) => (
          <Collapsible
            key={item.title}
            asChild
            defaultOpen={item.isActive}
            className="group/collapsible"
          >
            <SidebarMenuItem dir="rtl">
              <CollapsibleTrigger asChild>
                <SidebarMenuButton tooltip={item.title} className="cursor-pointer">
                  {item.icon && <item.icon />}
                  <span>{item.title}</span>
                  <ChevronLeft className="mr-auto transition-transform duration-200 group-data-[state=open]/collapsible:-rotate-90" />
                </SidebarMenuButton>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <SidebarMenuSub className="border-l-0 border-r">
                  {item.items?.map((subItem) => (
                    <SidebarMenuSubItem key={subItem.title}>
                      <SidebarMenuSubButton asChild>
                        <a href={subItem.url}>
                          <span>{subItem.title}</span>
                        </a>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                  ))}
                </SidebarMenuSub>
              </CollapsibleContent>
            </SidebarMenuItem>
          </Collapsible>
        ))}
        <SidebarMenuItem dir="rtl">
        <SidebarMenuButton
          onClick={handleNewChat}
          dir="rtl"
          key="new-chat"
          className="text-right cursor-pointer"
          tooltip="שיחה חדשה"
        >
          <EditIcon className=" h-4 w-4 " />
          <span className="">שיחה חדשה</span>
        </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarGroup>
  )
}
