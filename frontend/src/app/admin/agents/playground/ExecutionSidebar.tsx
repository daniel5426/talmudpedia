"use client";

import React, { useState } from "react";
import { 
  ChevronRight, 
  ChevronDown, 
  CheckCircle2, 
  Circle, 
  Loader2, 
  AlertCircle,
  Terminal,
  Activity,
  Code2,
  Database
} from "lucide-react";
import { ExecutionStep } from "./useAgentRunController";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";

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
      
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-4">
          {steps.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
              <Terminal className="size-8 opacity-20" />
              <p className="text-xs italic">No execution trace yet</p>
            </div>
          ) : (
            <div className="relative space-y-4">
              {/* Timeline line */}
              <div className="absolute left-[11px] top-2 bottom-2 w-0.5 bg-border" />
              
              {steps.map((step, idx) => (
                <StepItem key={step.id || idx} step={step} />
              ))}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

function StepItem({ step }: { step: ExecutionStep }) {
  const [isExpanded, setIsExpanded] = useState(false);
  
  const getIcon = () => {
    switch (step.status) {
      case "completed":
        return <CheckCircle2 className="size-5 text-green-500 bg-background" />;
      case "running":
        return <Loader2 className="size-5 text-primary animate-spin bg-background" />;
      case "error":
        return <AlertCircle className="size-5 text-destructive bg-background" />;
      default:
        return <Circle className="size-5 text-muted-foreground bg-background" />;
    }
  };

  const getTypeIcon = () => {
    switch (step.type) {
      case "tool":
        return <Database className="size-3" />;
      case "node":
        return <Code2 className="size-3" />;
      default:
        return <Terminal className="size-3" />;
    }
  };

  return (
    <div className="relative pl-8 group">
      <div className="absolute left-0 top-0.5 z-10">
        {getIcon()}
      </div>
      
      <div className="flex flex-col gap-1">
        <button 
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-2 text-left hover:text-primary transition-colors"
        >
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-[10px] font-mono text-muted-foreground uppercase bg-muted px-1.5 py-0.5 rounded flex items-center gap-1">
              {getTypeIcon()}
              {step.type}
            </span>
            <h3 className="text-sm font-medium truncate">{step.name}</h3>
          </div>
          {isExpanded ? <ChevronDown className="size-3 shrink-0" /> : <ChevronRight className="size-3 shrink-0" />}
        </button>
        
        <span className="text-[10px] text-muted-foreground font-mono">
          {step.timestamp.toLocaleTimeString()}
        </span>

        {isExpanded && (
          <div className="mt-2 space-y-2 animate-in fade-in slide-in-from-top-1 duration-200">
            {step.input && (
              <div className="space-y-1">
                <span className="text-[10px] font-bold uppercase text-muted-foreground">Input</span>
                <pre className="p-2 bg-muted/50 rounded text-[10px] font-mono overflow-auto max-h-40 whitespace-pre-wrap">
                  {JSON.stringify(step.input, null, 2)}
                </pre>
              </div>
            )}
            {step.output && (
              <div className="space-y-1">
                <span className="text-[10px] font-bold uppercase text-muted-foreground">Output</span>
                <pre className="p-2 bg-muted/50 rounded text-[10px] font-mono overflow-auto max-h-40 whitespace-pre-wrap">
                  {JSON.stringify(step.output, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
