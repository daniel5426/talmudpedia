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
      "flex w-full flex-wrap items-start justify-center gap-2",
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
        "h-auto max-w-full cursor-pointer rounded-full px-4 whitespace-normal text-wrap",
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
