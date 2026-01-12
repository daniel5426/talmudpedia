import { 
  LayoutDashboard, 
  Settings, 
  Database, 
  Users, 
  Cpu, 
  Workflow, 
  Activity,
  MessageSquare,
  FileSearch,
  BookOpen
} from "lucide-react"

export const sidebarContent = {
  navMain: [
    {
      title: "Dashboard",
      url: "/admin",
      icon: LayoutDashboard,
      isActive: true,
    },
    {
      title: "Content",
      url: "/admin/content",
      icon: BookOpen,
      items: [
        {
          title: "Sefaria Explorer",
          url: "/admin/content/sefaria",
        },
        {
          title: "Glossary",
          url: "/admin/content/glossary",
        },
      ],
    },
    {
      title: "RAG Engine",
      url: "/admin/rag",
      icon: FileSearch,
      items: [
        {
          title: "Pipelines",
          url: "/admin/rag/pipelines",
        },
        {
          title: "Ingestion Jobs",
          url: "/admin/rag/jobs",
        },
      ],
    },
    {
      title: "Agents",
      url: "/admin/agents",
      icon: Cpu,
      items: [
        {
          title: "All Agents",
          url: "/admin/agents",
        },
        {
          title: "Models Registry",
          url: "/admin/models",
        },
        {
          title: "Tools Registry",
          url: "/admin/tools",
        },
      ],
    },
    {
      title: "Monitoring",
      url: "/admin/monitoring",
      icon: Activity,
    },
    {
      title: "Identity",
      url: "/admin/identity",
      icon: Users,
    },
    {
      title: "Settings",
      url: "/admin/settings",
      icon: Settings,
    },
  ],
}
