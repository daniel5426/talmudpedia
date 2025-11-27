import React from "react";
import { cn } from "@/lib/utils";

interface CitationTooltipCardProps {
  title: string;
  text: string;
  className?: string;
}

export const CitationTooltipCard = ({
  title,
  text,
  className,
}: CitationTooltipCardProps) => {
  return (
    <div className={cn("flex flex-col gap-2 max-w-[300px]", className)}>
      <p className="text-lg font-bold">{title}</p>
      <p className="text-xs text-neutral-600 dark:text-neutral-400 line-clamp-6">
        {text}
      </p>
    </div>
  );
};
