"use client";

import React, { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { ExecutionStep } from "@/hooks/useAgentRunController";
import { cn } from "@/lib/utils";
import { ExecutionTrace } from "@/components/agent-builder/ExecutionTrace";

interface ExecutionSidebarProps {
  steps: ExecutionStep[];
  className?: string;
  copyText?: string | null;
}

export function ExecutionSidebar({ steps, className, copyText }: ExecutionSidebarProps) {
  const [copied, setCopied] = useState(false);
  const resetTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (resetTimeoutRef.current) clearTimeout(resetTimeoutRef.current);
    };
  }, []);

  const handleCopy = async () => {
    if (!copyText) return;
    try {
      await navigator.clipboard.writeText(copyText);
      setCopied(true);
      if (resetTimeoutRef.current) clearTimeout(resetTimeoutRef.current);
      resetTimeoutRef.current = setTimeout(() => setCopied(false), 1500);
    } catch (error) {
      console.error("Failed to copy full trace", error);
    }
  };

  return (
    <div className={cn("relative flex h-full min-h-0 flex-col overflow-hidden bg-transparent", className)}>
      {copyText ? (
        <button
          type="button"
          onClick={() => void handleCopy()}
          aria-label="Copy full trace"
          title="Copy full trace"
          className="absolute right-3 top-3 z-10 inline-flex h-9 w-9 items-center justify-center rounded-full border bg-background/95 text-foreground shadow-sm transition-colors hover:bg-muted"
        >
          {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
        </button>
      ) : null}
      <div className="flex-1 min-h-0">
        <ExecutionTrace steps={steps} className="min-h-0 bg-transparent" />
      </div>
    </div>
  );
}
