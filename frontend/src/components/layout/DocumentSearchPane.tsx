"use client";

import React, { useState, useRef, useEffect } from "react";
import { BotImputArea } from "@/components/BotImputArea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { GlassCard } from "@/components/ui/glass-card";
import { FileText, Search } from "lucide-react";
import { useLayoutStore } from "@/lib/store/useLayoutStore";
import { nanoid } from "nanoid";
import { KesherLoader } from "@/components/kesher-loader";

// Mock data generator
const generateMockDocs = (count: number, startIndex: number) => {
  return Array.from({ length: count }).map((_, i) => ({
    id: nanoid(),
    title: `Shulchan Arukh, Orach Chayim ${startIndex + i + 1}:${(i % 10) + 1}`,
    snippet: `This is a snippet for document ${
      startIndex + i + 1
    }. It contains some relevant text that was found during the search process. The content is just a placeholder for now.`,
    source: `Shulchan Arukh, Orach Chayim ${startIndex + i + 1}`,
    date: new Date().toLocaleDateString(),
    ref: `Shulchan Arukh, Orach Chayim ${startIndex + i + 1}:${(i % 10) + 1}`,
  }));
};

export function DocumentSearchPane() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  
  // Use selectors to prevent unnecessary re-renders
  const setActiveSource = useLayoutStore((state) => state.setActiveSource);
  const setSourceList = useLayoutStore((state) => state.setSourceList);
  const setSourceListOpen = useLayoutStore((state) => state.setSourceListOpen);

  const handleSearch = async (message: { text: string; files: any[] }) => {
    if (!message.text.trim()) return;

    setLoading(true);
    setHasSearched(true);
    // Simulate API call
    setTimeout(() => {
      const newDocs = generateMockDocs(10, 0);
      setResults(newDocs);
      setLoading(false);
    }, 1000);
  };

  const loadMore = () => {
    if (loading) return;
    setLoadingMore(true);
    // Simulate fetching more
    setTimeout(() => {
      const newDocs = generateMockDocs(10, results.length);
      setResults((prev) => [...prev, ...newDocs]);
      setLoadingMore(false);
    }, 1000);
  };

  // Infinite scroll handler
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, clientHeight, scrollHeight } = e.currentTarget;
    if (scrollHeight - scrollTop <= clientHeight + 100) {
      loadMore();
    }
  };

  const handleCardClick = (doc: any) => {
    // Open the source viewer with this document
    setActiveSource(doc.ref);

  };

  return (
    <div className="flex flex-col h-full ">
      <div className="flex-1 overflow-hidden relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-50">
            <KesherLoader />
          </div>
        )}
        {!hasSearched && !loading ? (
          <div className="flex flex-col items-center justify-center h-full max-w-3xl mx-auto w-full bg-background p-6 pb-40">
            <div className="flex flex-col pb-4 justify-center items-center text-muted-foreground">
              <Search className="w-16 h-16 mb-4 opacity-20" />
              <h2 className="text-2xl font-semibold">Document Search</h2>
              <p>Enter a query to search through the document library.</p>
            </div>
            <BotImputArea
              textareaRef={textareaRef}
              handleSubmit={handleSearch}
            />
          </div>
        ) : (
          <ScrollArea className="h-full w-full" onScrollCapture={handleScroll}>
            <div className="@container h-full p-3">
              <div className="grid grid-cols-1 @md:grid-cols-2 @lg:grid-cols-3 gap-4 pb-32 max-w-7xl mx-auto">
              {results.map((doc) => (
                <GlassCard
                  key={doc.id}
                  variant="no_border"
                  className=" p-4 "
                  onClick={() => handleCardClick(doc)}
                >
                  <div className="pb-2">
                    <div className="flex items-center gap-2 text-lg">
                      {doc.title}
                    </div>
                  </div>
                  <div className="pb-2">
                    <p className="text-sm line-clamp-3 text-muted-foreground">{doc.snippet}</p>
                  </div>
                </GlassCard>
              ))}
            </div>
            </div>
            {hasSearched && !loading && (
            <div className=" pb-3 sticky bottom-0 left-0 right-0 w-full max-w-3xl px-4 mx-auto bg-transparent">
              <BotImputArea
                className="sticky bottom-0 left-0 right-0 w-full  max-w-3xl  bg-background"
                textareaRef={textareaRef}
                handleSubmit={handleSearch}
              />
            </div>
            )}
          </ScrollArea>
        )}
      </div>
      {hasSearched && (loading) && (
        <div className="pb-3 w-full max-w-3xl px-4 mx-auto bg-transparent">
          <BotImputArea
            className="w-full max-w-3xl bg-background"
            textareaRef={textareaRef}
            handleSubmit={handleSearch}
          />
        </div>
      )}
    </div>
  );
}
