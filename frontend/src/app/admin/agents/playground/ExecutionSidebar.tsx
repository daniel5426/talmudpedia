"use client";

import React from "react";
import {
  Activity
} from "lucide-react";
import { ExecutionStep } from "@/hooks/useAgentRunController";
import { cn } from "@/lib/utils";
import { ExecutionTrace } from "@/components/agent-builder/ExecutionTrace";

interface ExecutionSidebarProps {
  steps: ExecutionStep[];
  className?: string;
}

export function ExecutionSidebar({ steps, className }: ExecutionSidebarProps) {
  return (
    <div className={cn("flex flex-col h-full border-l bg-muted/10", className)}>
      <div className="p-4 border-b bg-background flex items-center gap-2">
        <Activity className="size-4 text-primary" />
        <h2 className="font-semibold text-sm uppercase tracking-wider">Execution Trace</h2>
      </div>

      <ExecutionTrace steps={steps} className="bg-transparent" />
    </div>
  );
}
