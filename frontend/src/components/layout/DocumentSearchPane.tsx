"use client";

import React, { useState, useRef } from "react";
import Image from "next/image";
import { DocumentSearchInputArea } from "@/components/DocumentSearchInputArea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { GlassCard } from "@/components/ui/glass-card";
import { useLayoutStore } from "@/lib/store/useLayoutStore";
import { motion, AnimatePresence, LayoutGroup } from "framer-motion";
import { convertToHebrew } from "@/lib/hebrewUtils";

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
  const setActiveSource = useLayoutStore((state) => state.setActiveSource);

  const handleSearch = async (message: { text: string; files: any[] }) => {
    if (!message.text.trim()) return;

    const searchQuery = message.text.trim();
    setQuery(searchQuery);
    setLoading(true);
    setHasSearched(true);

    try {
      const response = await fetch("http://localhost:8000/search", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: searchQuery,
          limit: 20,
        }),
      });

      if (!response.ok) {
        throw new Error(`Search failed: ${response.statusText}`);
      }

      const data = await response.json();
      setResults(data.results || []);
    } catch (error) {
      console.error("Search error:", error);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const handleCardClick = (doc: any) => {
    // Open the source viewer with this document
    setActiveSource(doc.ref);
    console.log("doc.ref", doc.ref);
  };


  return (
    <LayoutGroup>
      <div className="relative flex flex-col h-full bg-[linear-gradient(to_bottom_right,#cce4e6,#008E96)]">
        <div
          dir="ltr"
          className="absolute inset-0 pointer-events-none overflow-visible z-0"
        >
          <Image
            src="/kesher.png"
            alt="Kesher Logo"
            width={1800}
            height={1800}
            className="absolute w-[min(70vw,700px)] opacity-20 -translate-x-[40%] -translate-y-[20%] top-1/4"
            priority
          />
          <Image
            src="/kesher.png"
            alt="Kesher Logo"
            width={1800}
            height={1800}
            className="absolute w-[min(70vw,700px)] opacity-20 translate-x-[40%] translate-y-[50%] right-0"
            priority
          />
          <Image
            src="/kesher.png"
            alt="Kesher Logo"
            width={1800}
            height={1800}
            className="absolute w-[min(70vw,200px)] opacity-90 -translate-x-[10%] translate-y-[10%] right-0 filter brightness-0 invert"
            priority
          />
        </div>
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
                          <div className="flex items-center gap-2 text-lg">
                            {convertToHebrew(doc.title)}
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
