"use client";

import React, { useState } from "react";
import { useLayoutStore } from "@/lib/store/useLayoutStore";
import { cn, convertToHebrew } from "@/lib/hebrewUtils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { BookOpen, X, Search, PanelLeftIcon } from "lucide-react";

export function SourceListPane() {
  const { setActiveSource, toggleSourceList, sourceList, setSourceList } = useLayoutStore();
  const [query, setQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) return;

    setIsLoading(true);
    try {
      const res = await fetch(`/api/py/search?q=${encodeURIComponent(query)}`);
      if (res.ok) {
        const data = await res.json();
        setSourceList(data.results || []);
      }
    } catch (error) {
      console.error("Search failed:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleSearch();
    }
  };

  return (
    <div className="flex flex-col h-full bg-muted/30">
      <div className="flex items-center justify-between p-2 pt-[14px] mx-2">
        {isSearchOpen ? (
          <Input
            placeholder="חפש מקורות..."
            dir="rtl"
            className="flex-1 py-0 mr-2 border-none shadow-none bg-muted text-right"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={() => !query && setIsSearchOpen(false)}
            autoFocus
          />
        ) : (
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setIsSearchOpen(true)}
            className="h-8 w-8"
          >
            <Search className="h-4 w-4" />
          </Button>
        )}
        <Button
          data-sidebar="trigger"
          data-slot="sidebar-trigger"
          variant="ghost"
          size="icon"
          className={cn("size-7")}
          onClick={toggleSourceList}
        >
          <PanelLeftIcon />
          <span className="sr-only">Toggle Source List</span>
        </Button>
      </div>

      <ScrollArea dir="rtl" className="flex-1 h-full">
        <div className="p-2 pb-80 space-y-2">
          {sourceList.length === 0 && !isLoading && (
            <p className="text-xs text-muted-foreground text-center py-4">
              {query ? "No results found." : "Search for Talmudic texts..."}
            </p>
          )}

          {sourceList.map((source) => (
            <div
              key={source.id}
              className="p-2 rounded-lg border bg-card hover:bg-accent/50 cursor-pointer transition-colors"
              onClick={() => setActiveSource(source.metadata.ref)} // Using ref as ID for now
            >
              <div className="items-center gap-2 mb-1">
                <span className="font-medium text-sm truncate">
                  {convertToHebrew(source.metadata.ref)}
                </span>
              </div>
              <p className="text-xs text-muted-foreground pl-6 line-clamp-2">
                {source.metadata.text}
              </p>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
