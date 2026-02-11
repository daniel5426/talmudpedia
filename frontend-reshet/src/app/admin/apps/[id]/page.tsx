"use client";

import { useParams } from "next/navigation";

import { AppsBuilderWorkspace } from "@/features/apps-builder/workspace/AppsBuilderWorkspace";

export default function AppBuilderPage() {
  const params = useParams<{ id: string }>();
  const appId = params?.id;

  if (!appId) {
    return <div className="p-6 text-sm text-destructive">Missing app id.</div>;
  }

  return <AppsBuilderWorkspace appId={appId} />;
}
