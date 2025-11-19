"use client"

import * as React from "react"
import {
  AudioWaveform,
  BookOpen,
  Bot,
  Command,
  Frame,
  GalleryVerticalEnd,
  Map,
  PieChart,
  Settings2,
  SquareTerminal,
  MessageSquare,
  Library,
} from "lucide-react"

import { NavMain } from "@/components/nav-main"
import { NavProjects } from "@/components/nav-projects"
import { NavUser } from "@/components/nav-user"
import { TeamSwitcher } from "@/components/team-switcher"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
} from "@/components/ui/sidebar"

// This is sample data.
const data = {
  user: {
    name: "Daniel Benassaya",
    email: "daniel@talmudpedia.com",
    avatar: "/avatars/shadcn.jpg",
  },
  teams: [
    {
      name: "Talmudpedia",
      logo: GalleryVerticalEnd,
      plan: "Pro",
    },
    {
      name: "Yeshiva",
      logo: AudioWaveform,
      plan: "Startup",
    },
  ],
  navMain: [
    {
      title: "Saved Chats",
      url: "#",
      icon: MessageSquare,
      isActive: true,
      items: [
        {
          title: "Shabbat 21b",
          url: "#",
        },
        {
          title: "Berachot 2a",
          url: "#",
        },
        {
          title: "Eruvin 13b",
          url: "#",
        },
      ],
    },
    {
      title: "Library",
      url: "#",
      icon: Library,
      items: [
        {
          title: "Talmud Bavli",
          url: "#",
        },
        {
          title: "Mishneh Torah",
          url: "#",
        },
        {
          title: "Shulchan Aruch",
          url: "#",
        },
      ],
    },
    {
      title: "Settings",
      url: "#",
      icon: Settings2,
      items: [
        {
          title: "General",
          url: "#",
        },
        {
          title: "Appearance",
          url: "#",
        },
        {
          title: "Account",
          url: "#",
        },
      ],
    },
  ],
  projects: [
    {
      name: "Daf Yomi",
      url: "#",
      icon: Frame,
    },
    {
      name: "Halacha Yomis",
      url: "#",
      icon: PieChart,
    },
  ],
}

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar collapsible="icon" side="right" {...props}>
      <SidebarHeader>
        <TeamSwitcher teams={data.teams} />
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={data.navMain} />
        <NavProjects projects={data.projects} />
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={data.user} />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
