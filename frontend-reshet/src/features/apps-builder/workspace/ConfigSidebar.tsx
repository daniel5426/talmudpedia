"use client";

import { ArrowLeft, Code, Globe, LayoutDashboard, Users } from "lucide-react";

import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { FileTree } from "@/features/apps-builder/editor/FileTree";

type ConfigSection = "overview" | "users" | "domains" | "code";

const sections = [
  { key: "overview" as const, label: "Overview", icon: LayoutDashboard },
  { key: "users" as const, label: "Users", icon: Users },
  { key: "domains" as const, label: "Domains", icon: Globe },
  { key: "code" as const, label: "Code", icon: Code },
];

type ConfigSidebarProps = {
  configSection: ConfigSection;
  onChangeSection: (section: ConfigSection) => void;
  onBackFromCode: () => void;
  files: Record<string, string>;
  selectedFile: string | null;
  onSelectFile: (path: string) => void;
  onDeleteFile: (path: string) => void;
};

export function ConfigSidebar({
  configSection,
  onChangeSection,
  onBackFromCode,
  files,
  selectedFile,
  onSelectFile,
  onDeleteFile,
}: ConfigSidebarProps) {
  if (configSection === "code") {
    return (
      <aside className="flex w-72 shrink-0 flex-col border-r border-border/60 bg-muted/20">
        <div className="px-3 py-2.5">
          <button
            type="button"
            onClick={onBackFromCode}
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="h-3 w-3" />
            Back to Config
          </button>
        </div>
        <Separator />
        <FileTree
          files={files}
          selectedFile={selectedFile}
          onSelectFile={onSelectFile}
          onDeleteFile={onDeleteFile}
        />
      </aside>
    );
  }

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-border/60 bg-muted/20">
      <div className="space-y-0.5 p-2">
        {sections.map((section) => (
          <button
            key={section.key}
            type="button"
            onClick={() => onChangeSection(section.key)}
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors",
              configSection === section.key
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <section.icon className="h-3.5 w-3.5 shrink-0" />
            <span>{section.label}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}
