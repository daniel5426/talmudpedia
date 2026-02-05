import React from "react";
import { KesherLogo } from "./KesherLogo";
import { cn } from "@/lib/utils";

interface BackgroundLogosProps {
  className?: string;
}

export function BackgroundLogos({ className }: BackgroundLogosProps) {
  return (
    <div
      dir="ltr"
      className={cn(
        "absolute inset-0 pointer-events-none overflow-visible z-0",
        className
      )}
    >
      <KesherLogo
        variant="background"
        className="-translate-x-[40%] -translate-y-[20%] top-1/4"
      />
      <KesherLogo
        variant="background"
        className="translate-x-[40%] translate-y-[50%] right-0"
      />
      <KesherLogo
        variant="accent"
        className="-translate-x-[10%] translate-y-[10%] right-0"
      />
    </div>
  );
}
