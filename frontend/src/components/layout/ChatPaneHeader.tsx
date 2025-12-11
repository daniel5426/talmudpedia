import * as React from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Search, MoreHorizontal, Share2, Trash2 } from "lucide-react";

interface ChatPaneHeaderProps {
  chatId?: string | null;
  onSearchOpen: () => void;
  onShareChat: () => void;
  onDeleteChat: () => void;
  isEmptyState: boolean;
}

export function ChatPaneHeader({
  chatId,
  onSearchOpen,
  onShareChat,
  onDeleteChat,
  isEmptyState,
}: ChatPaneHeaderProps) {
  const backgroundStyles = isEmptyState
    ? { backgroundColor: "transparent" }
    : {
        background: "linear-gradient(to top, rgba(255,255,255,0) 0%, rgba(255,255,255,0.8) 60%, #ffffff 100%)",
      };

  return (
    <div
      className="absolute top-0 py-2.5 left-0 right-0 z-20 w-full px-4 transition-all duration-500 ease-out-in"
      style={{ containerType: "inline-size", ...backgroundStyles }}
    >
      <div className="flex items-center gap-2">
        {/* Left side: Dropdown menu (only if chatId) and Search */}
        <div className="flex items-center gap-2">
          {chatId && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="flex items-center border text-muted-foreground shadow-none gap-2"
                >
                  <MoreHorizontal className="h-4 w-4" />
                  <span className="sr-only">More options</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-48" side="bottom" align="start">
                <DropdownMenuItem onClick={onShareChat} className="cursor-pointer focus:bg-sidebar">
                  <Share2 className="mr-2 h-4 w-4" />
                  <span>שתף</span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={onDeleteChat}
                  className="cursor-pointer text-red-600 focus:text-red-600 focus:bg-sidebar"
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  <span>מחק</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}

          {/* Search button with container query responsive behavior */}
          <Button
            variant="outline"
            dir="rtl"
            size="sm"
            className="search-button relative flex items-center gap-2 border text-muted-foreground h-8 rounded-[0.5rem] text-sm font-normal shadow-none"
            onClick={onSearchOpen}
          >
            <Search className="h-4 w-8 shrink-0" />
            <span className="search-text-lg hidden">חפש בספריה...</span>
            <span className="search-text-md hidden">חפש...</span>
            <span className="search-kbd bg-muted pointer-events-none top-[0.3rem] right-[0.3rem] h-5 items-center gap-1 rounded border px-1.5 font-mono text-[10px] font-medium opacity-100 select-none hidden">
              <span className="text-xs">⌘</span>K
            </span>
          </Button>
        </div>

        {/* Right side: Empty for now, can be expanded later */}
        <div className="flex-1" />
      </div>

      {/* Container query styles */}
      <style jsx>{`
        @container (min-width: 400px) {
          .search-button {
            padding-right: 3rem;
          }
          .search-text-md {
            display: inline-flex;
          }
          .search-kbd {
            display: flex;
          }
        }
        @container (min-width: 600px) {
          .search-button {
            width: 26rem;
          }
          .search-text-md {
            display: none;
          }
          .search-text-lg {
            display: inline-flex;
          }
        }
      `}</style>
    </div>
  );
}
