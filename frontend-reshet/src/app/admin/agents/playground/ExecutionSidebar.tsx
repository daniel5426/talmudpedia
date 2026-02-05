"use client";

import React from "react";
import { ExecutionStep } from "@/hooks/useAgentRunController";
import { cn } from "@/lib/utils";
import { ExecutionTrace } from "@/components/agent-builder/ExecutionTrace";

interface ExecutionSidebarProps {
  steps: ExecutionStep[];
  className?: string;
}

export function ExecutionSidebar({ steps, className }: ExecutionSidebarProps) {
  return (
    <div className={cn("flex flex-col h-full min-h-0 overflow-y-auto border-l bg-muted/10", className)}>
      <ExecutionTrace steps={steps} className="bg-transparent" />
    </div>
  );
}
