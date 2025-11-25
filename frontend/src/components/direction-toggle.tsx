"use client";

import { Languages } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDirection } from "@/components/direction-provider";

export function DirectionToggle() {
  const { direction, toggleDirection } = useDirection();

  const label = direction === "rtl" ? "עברית" : "Français";

  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-9 w-9"
      onClick={toggleDirection}
      aria-label="Toggle interface direction"
    >
      <Languages className="h-4 w-4" />
      <span className="sr-only">{label}</span>
    </Button>
  );
}

