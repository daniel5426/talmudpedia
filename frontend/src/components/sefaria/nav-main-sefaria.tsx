"use client";

import { ChevronLeft, ChevronRight, EditIcon, Book, type LucideIcon } from "lucide-react";
import Link from "next/link";

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
import { DirectionMode } from "@/components/direction-provider";
import { cn } from "@/lib/utils";

export function NavMain({
  items,
  handleNewChat,
  handleLibraryToggle,
  direction,
}: {
  items: {
    title: string;
    url: string;
    icon?: LucideIcon;
    isActive?: boolean;
    items?: {
      title: string;
      url: string;
      icon?: LucideIcon;
      isActive?: boolean;
    }[];
  }[];
  handleNewChat: () => void;
  handleLibraryToggle?: () => void;
  direction: DirectionMode;
}) {
  const isRTL = direction === "rtl";
  return (
    <SidebarGroup dir={direction}>
      <SidebarGroupLabel dir={direction}>Platform</SidebarGroupLabel>
      <SidebarMenu>
        {items.map((item) => {
          const hasSubItems = item.items && item.items.length > 0;
          
          if (hasSubItems) {
            return (
              <Collapsible
                key={item.title}
                asChild
                defaultOpen={item.isActive}
                className="group/collapsible"
              >
                <SidebarMenuItem>
                  <CollapsibleTrigger asChild>
                    <SidebarMenuButton asChild tooltip={item.title} className="cursor-pointer" isActive={item.isActive}>
                      <Link href={item.url}>
                        {item.icon && <item.icon />}
                        <span>{item.title}</span>
                        {!isRTL && <ChevronRight className="ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90" />}
                        {isRTL && <ChevronLeft className="mr-auto transition-transform duration-200 group-data-[state=open]/collapsible:-rotate-90" />}
                      </Link>
                    </SidebarMenuButton>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <SidebarMenuSub className={cn("border-l-0", !isRTL ? "border-l" : "border-r")}>
                      {item.items?.map((subItem) => (
                        <SidebarMenuSubItem key={subItem.title} dir={direction}>
                          <SidebarMenuSubButton asChild isActive={subItem.isActive}>
                            <Link href={subItem.url} className="flex items-center gap-2">
                              {subItem.icon && <subItem.icon className="h-4 w-4" />}
                              <span>{subItem.title}</span>
                            </Link>
                          </SidebarMenuSubButton>
                        </SidebarMenuSubItem>
                      ))}
                    </SidebarMenuSub>
                  </CollapsibleContent>
                </SidebarMenuItem>
              </Collapsible>
            )
          } else {
            return (
              <SidebarMenuItem key={item.title}>
                <SidebarMenuButton asChild tooltip={item.title} className="cursor-pointer" isActive={item.isActive}>
                  <Link href={item.url}>
                    {item.icon && <item.icon />}
                    <span>{item.title}</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )
          }
        })}
        <SidebarMenuItem>
        <SidebarMenuButton
          onClick={handleNewChat}
          key="new-chat"
          className="cursor-pointer"
          tooltip="שיחה חדשה"
        >
          <EditIcon className=" h-4 w-4 " />
          <span className="">שיחה חדשה</span>
        </SidebarMenuButton>
        </SidebarMenuItem>
        {handleLibraryToggle && (
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={handleLibraryToggle}
              key="library"
              className="cursor-pointer"
              tooltip="ספרייה"
            >
              <Book className="h-4 w-4" />
              <span>ספרייה</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        )}
      </SidebarMenu>
    </SidebarGroup>
  )
}
