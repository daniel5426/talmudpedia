"use client";

import React, { useState, useRef } from "react";
import { DocumentSearchInputArea } from "@/components/DocumentSearchInputArea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { GlassCard } from "@/components/ui/glass-card";
import { useLayoutStore } from "@/lib/store/useLayoutStore";
import { motion, AnimatePresence, LayoutGroup } from "framer-motion";
import { searchService } from "@/services/search";
import { openSource } from "@/lib/sourceUtils";
import { BackgroundLogos } from "@/components/ui/background-logos";

const QUERY_BUBBLE_TITLE = "חפש בכל התורה כולה במשפט אחד";

interface QueryBubbleProps {
  text: string;
  variant: "intro" | "results";
}

const QueryBubble = ({ text, variant }: QueryBubbleProps) => {
  const variantClasses =
    variant === "intro"
      ? "relative z-30 mx-auto mb-6"
      : "sticky top-2 z-40 mx-auto";

  return (
    <motion.div
      layoutId="query-bubble"
      layout
      className={` shadow-md rounded-full px-4 bg-primary-soft w-fit text-center flex justify-center py-2 backdrop-blur-md ${variantClasses}`}
      transition={{
        layout: {
          duration: 0.45,
          ease: "easeInOut",
        },
      }}
    >
      <AnimatePresence mode="wait">
        <motion.p
          key={text}
          initial={{
            opacity: 0,
            y: variant === "intro" ? 20 : -20,
            scale: 0.95,
          }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{
            opacity: 0,
            y: variant === "intro" ? -20 : 20,
            scale: 0.95,
          }}
          transition={{ duration: 0.3, ease: "easeOut" }}
          className="text-lg text-center font-medium"
        >
          {text}
        </motion.p>
      </AnimatePresence>
    </motion.div>
  );
};

export function DocumentSearchPane() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  
  // Use selectors to prevent unnecessary re-renders

  const handleSearch = async (message: { text: string; files: any[] }) => {
    if (!message.text.trim()) return;

    const searchQuery = message.text.trim();
    setQuery(searchQuery);
    setLoading(true);
    setHasSearched(true);

    setHasSearched(true);

    try {
      const data = await searchService.search({ query: searchQuery, limit: 20 });
      setResults(data.results || []);
    } catch (error) {
      console.error("Search error:", error);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const handleCardClick = (doc: any) => {
    // Priority: range_ref > first_ref > ref
    const targetRef = doc.range_ref || doc.first_ref || doc.ref;

    // Use standardized openSource utility
    openSource(targetRef, { 
      pagesAfter: 2,
      totalSegments: doc.total_segments || 1
    });
  };


  return (
    <LayoutGroup>
      <div className="relative flex flex-col h-full bg-linear-to-br from-(--gradient-from) to-(--gradient-to)">
        <BackgroundLogos />
        <div className="relative z-10 flex flex-col justify-center h-full">
          <div className="flex-1 overflow-hidden relative flex items-center">
            
            {!hasSearched && !loading ? (
              <div className="flex flex-col gap-6 items-center w-full max-w-3xl mx-auto bg-transparent p-4 pb-26">
            <p className="text-3xl font-semibold">
            {QUERY_BUBBLE_TITLE}</p>
                <DocumentSearchInputArea
                  textareaRef={textareaRef}
                  handleSubmit={handleSearch}
                />
              </div>
            ) : (
              <ScrollArea className="h-full w-full">
                <div className="@container h-full">
                  <QueryBubble
                    text={query || QUERY_BUBBLE_TITLE}
                    variant="results"
                  />

                  <div className="grid grid-cols-1 @md:grid-cols-2 @lg:grid-cols-3 gap-4 pb-32 p-3 max-w-7xl mx-auto">
                    {results.map((doc) => (
                      <GlassCard
                        dir="rtl"
                        key={doc.id}
                        variant="no_border"
                        className="p-4 cursor-pointer hover:bg-accent transition-colors"
                        onClick={() => handleCardClick(doc)}
                      >
                        <div className="pb-2">
                          <div className="flex items-center gap-2 text-lg font-bold">
                            {doc.he_ref}
                          </div>
                        </div>
                        <div className="pb-2">
                          <p className="text-sm line-clamp-3 text-muted-foreground">
                            {doc.snippet}
                          </p>
                        </div>
                      </GlassCard>
                    ))}
                  </div>
                </div>
                {hasSearched && !loading && (
                  <div className="pb-3 sticky z-90 bottom-0 left-0 right-0 w-full max-w-3xl px-4 mx-auto">
                    <DocumentSearchInputArea
                      className="sticky bottom-0 left-0 right-0 w-full max-w-3xl"
                      textareaRef={textareaRef}
                      handleSubmit={handleSearch}
                    />
                  </div>
                )}
              </ScrollArea>
            )}
          </div>
          {hasSearched && loading && (
            <div className="pb-3 w-full max-w-3xl px-4 mx-auto">
              <DocumentSearchInputArea
                className="w-full max-w-3xl bg-background"
                textareaRef={textareaRef}
                handleSubmit={handleSearch}
              />
            </div>
          )}
        </div>
      </div>
    </LayoutGroup>
  );
}
