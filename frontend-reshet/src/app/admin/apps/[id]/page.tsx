"use client";

import { useParams } from "next/navigation";

import { AppsBuilderWorkspace } from "@/features/apps-builder/workspace/AppsBuilderWorkspace";
import { useAuthStore } from "@/lib/store/useAuthStore";

export default function AppBuilderPage() {
  const params = useParams<{ id: string }>();
  const currentProjectId = useAuthStore((state) => state.activeProject?.id ?? null);
  const appId = params?.id;

  if (!appId) {
    return <div className="p-6 text-sm text-destructive">Missing app id.</div>;
  }

  return <AppsBuilderWorkspace key={`${currentProjectId ?? "no-project"}:${appId}`} appId={appId} />;
}
