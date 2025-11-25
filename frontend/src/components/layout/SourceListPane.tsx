"use client";

import React, { useState } from "react";
import { useLayoutStore } from "@/lib/store/useLayoutStore";
import { cn, convertToHebrew } from "@/lib/hebrewUtils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { BookOpen, X, Search, PanelLeftIcon } from "lucide-react";
import { GlassCard } from "../ui/glass-card";

export function SourceListPane() {
  // Use selectors to prevent unnecessary re-renders
  const setActiveSource = useLayoutStore((state) => state.setActiveSource);
  const toggleSourceList = useLayoutStore((state) => state.toggleSourceList);
  const sourceList = useLayoutStore((state) => state.sourceList);
  const setSourceList = useLayoutStore((state) => state.setSourceList);
  
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
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between p-2 pt-[12px]">
        {isSearchOpen ? (
          <Input
            placeholder="חפש מקורות..."
            dir="rtl"
            className="flex-1 py-0 mr-2 rounded-sm border-none shadow-none bg-muted text-right"
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
            className="h-9 w-9"
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
            <GlassCard
              key={source.id}
              onClick={() => setActiveSource(source.metadata.ref)} // Using ref as ID for now
              variant="no_border"
              className="p-2"
            >
              <div className="items-center gap-2 mb-1">
                <span className="font-medium text-sm truncate">
                  {convertToHebrew(source.metadata.ref)}
                </span>
              </div>
              <p className="text-xs text-muted-foreground pl-6 line-clamp-2">
                {source.metadata.text}
              </p>
            </GlassCard>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
