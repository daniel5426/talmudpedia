import { CircleDashed, Search, Terminal } from "lucide-react";

import { cn } from "@/lib/utils";

interface MockExecutionSidebarProps {
  className?: string;
}

const MOCK_STEPS = [
  { icon: Search, title: "Loaded thread context", detail: "Hydrated previous assistant steps for the active thread." },
  { icon: Terminal, title: "Runtime stream attached", detail: "Connected the published app runtime stream to the chat workspace." },
  { icon: CircleDashed, title: "Waiting for next tool call", detail: "The execution sidebar is visually ported from the playground for now." },
];

export function MockExecutionSidebar({ className }: MockExecutionSidebarProps) {
  return (
    <div className={cn("flex h-full min-h-0 flex-col overflow-y-auto bg-transparent", className)}>
      <div className="border-b px-4 py-3">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Execution Trace
        </div>
      </div>
      <div className="space-y-4 p-4">
        {MOCK_STEPS.map((step) => {
          const Icon = step.icon;
          return (
            <div key={step.title} className="rounded-2xl border bg-background/70 p-3">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Icon className="size-4 text-primary" />
                {step.title}
              </div>
              <p className="mt-1 text-sm text-muted-foreground">{step.detail}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
