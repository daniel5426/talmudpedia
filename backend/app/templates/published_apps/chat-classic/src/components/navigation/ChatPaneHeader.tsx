import * as React from "react";
import { MoreHorizontal, Share2, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface ChatPaneHeaderProps {
  chatId?: string | null;
  onShareChat?: () => void;
  onDeleteChat?: () => void;
  isEmptyState: boolean;
}

export function ChatPaneHeader({
  chatId,
  onShareChat,
  onDeleteChat,
  isEmptyState,
}: ChatPaneHeaderProps) {
  const backgroundStyles = isEmptyState
    ? { backgroundColor: "transparent" }
    : {
        background:
          "linear-gradient(to top, color-mix(in oklch, var(--chat-background) 0%, transparent) 0%, color-mix(in oklch, var(--chat-background) 80%, transparent) 60%, var(--chat-background) 100%)",
      };

  return (
    <div
      className="absolute top-0 left-0 right-0 z-20 w-full px-4 py-2.5 transition-all duration-500 ease-out-in"
      style={{ containerType: "inline-size", ...backgroundStyles } as React.CSSProperties}
    >
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1 rounded-lg bg-background shadow-md border-none">
          {chatId ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild className="border-none shadow-none">
                <Button
                  variant="outline"
                  size="sm"
                  className="flex items-center gap-2 text-muted-foreground"
                >
                  <MoreHorizontal className="h-4 w-4" />
                  <span className="sr-only">More options</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-48" side="bottom" align="start">
                <DropdownMenuItem onClick={onShareChat} className="cursor-pointer focus:bg-sidebar">
                  <Share2 className="mr-2 h-4 w-4" />
                  <span>Share</span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={onDeleteChat}
                  className="cursor-pointer text-red-600 focus:bg-sidebar focus:text-red-600"
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  <span>Delete</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}

        </div>
        <div className="flex-1" />
      </div>
    </div>
  );
}
