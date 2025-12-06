"use client";

import React from "react";
import { Button } from "@/components/ui/button";
import { MessageSquare, Copy } from "lucide-react";
import { cn } from "@/lib/utils";

interface TextSelectionPopupProps {
  position: { x: number; y: number } | null;
  onAskChat: () => void;
  onCopy: () => void;
}

export function TextSelectionPopup({ position, onAskChat, onCopy }: TextSelectionPopupProps) {
  if (!position) return null;

  return (
    <div
      className={cn(
        "fixed z-[100] animate-in fade-in-0 zoom-in-95 duration-200",
        "backdrop-blur-md bg-background/95 border border-border/50 shadow-lg rounded-lg p-1 flex gap-1"
      )}
      style={{
        left: `${position.x}px`,
        top: `${position.y}px`,
        transform: "translate(-50%, -120%)",
        pointerEvents: "auto",
      }}
      onMouseDown={(e) => {
        e.preventDefault();
      }}
    >
      <Button
        variant="ghost"
        size="sm"
        onClick={onCopy}
        className="gap-2 h-8 px-3 hover:bg-primary/10"
      >
        <Copy className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={onAskChat}
        className="gap-2 h-8 px-3 hover:bg-primary/10"
      >
        <MessageSquare className="h-4 w-4" />
        <span className="text-sm font-medium">שאל את הצ'אט</span>
      </Button>
    </div>
  );
}
