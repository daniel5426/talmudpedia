"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ComponentProps } from "react";
import { useCallback } from "react";

export type SuggestionsProps = ComponentProps<"div">;

export const Suggestions = ({
  className,
  children,
  ...props
}: SuggestionsProps) => (
  <div
    className={cn(
      "grid w-full grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3",
      className,
    )}
    {...props}
  >
    {children}
  </div>
);

export type SuggestionProps = Omit<ComponentProps<typeof Button>, "onClick"> & {
  suggestion: string;
  onClick?: (suggestion: string) => void;
};

export const Suggestion = ({
  suggestion,
  onClick,
  className,
  variant = "outline",
  size = "sm",
  children,
  ...props
}: SuggestionProps) => {
  const handleClick = useCallback(() => {
    onClick?.(suggestion);
  }, [onClick, suggestion]);

  return (
    <Button
      className={cn(
        "h-auto min-h-11 w-full cursor-pointer rounded-2xl border-[#D7C08A] bg-white/85 px-4 py-3 text-left whitespace-normal text-wrap text-[#0B2A5B] shadow-[0_8px_30px_rgba(11,42,91,0.06)] transition-all hover:border-[#C9A34D] hover:bg-[#FFF9E8] hover:text-[#0B2A5B]",
        className,
      )}
      onClick={handleClick}
      size={size}
      type="button"
      variant={variant}
      {...props}
    >
      {children || suggestion}
    </Button>
  );
};
