"use client";

import React from "react";
import { useLayoutStore } from "@/lib/store/useLayoutStore";
import { cn, convertToHebrew } from "@/lib/hebrewUtils";
import { Button } from "@/components/ui/button";
import { X, Settings2, BookOpen, Type, Languages } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { GlassCard } from "@/components/ui/glass-card";
import { TextSelectionPopup } from "@/components/ui/text-selection-popup";
import { nanoid } from "nanoid";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
} from "@/components/ui/dropdown-menu";
import {
  sourceService,
  MultiPageTextData,
  SinglePageTextData,
} from "@/services";
import { useIsMobile } from "@/hooks/use-mobile";
import { SourceSiblingsModal } from "./SourceSiblingsModal";

interface SourceViewerPaneProps {
  sourceId: string | null;
}

type FontSize = "small" | "medium" | "large" | "xlarge";
type LayoutMode = "continuous" | "segmented";

export function SourceViewerPane({ sourceId }: SourceViewerPaneProps) {
  // Use selector to prevent unnecessary re-renders
  const setActiveSource = useLayoutStore((state) => state.setActiveSource);
  const activeSource = useLayoutStore((state) => state.activeSource);
  const activePagesAfter = useLayoutStore((state) => state.activePagesAfter);
  const activeTotalSegments = useLayoutStore((state) => state.activeTotalSegments);
  const setSelectedText = useLayoutStore((state) => state.setSelectedText);
  const refreshTrigger = useLayoutStore((state) => state.refreshTrigger);
  const isMobile = useIsMobile();

  const [selectionPopup, setSelectionPopup] = React.useState<{
    x: number;
    y: number;
  } | null>(null);
  const [selectedTextContent, setSelectedTextContent] = React.useState<string>("");
  const [selectionRects, setSelectionRects] = React.useState<Array<{
    left: number;
    top: number;
    width: number;
    height: number;
  }>>([]);

  const [textData, setTextData] = React.useState<MultiPageTextData | null>(
    null
  );
  const [isLoading, setIsLoading] = React.useState(false);
  const [isLoadingTop, setIsLoadingTop] = React.useState(false);
  const [isLoadingBottom, setIsLoadingBottom] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [fontSize, setFontSize] = React.useState<FontSize>("medium");
  const [layoutMode, setLayoutMode] = React.useState<LayoutMode>("segmented");
  const [canLoadMore, setCanLoadMore] = React.useState({
    top: true,
    bottom: true,
  });
  const [currentRef, setCurrentRef] = React.useState(sourceId || "");
  const [isTopVisible, setIsTopVisible] = React.useState(false);
  const [isBottomVisible, setIsBottomVisible] = React.useState(false);
  const [initialScrollComplete, setInitialScrollComplete] =
    React.useState(false);
  const [siblingsModalOpen, setSiblingsModalOpen] = React.useState(false);
  const [highlightedGlobalIndices, setHighlightedGlobalIndices] = React.useState<number[]>([]);
  const segmentRefs = React.useRef<(HTMLDivElement | HTMLSpanElement | null)[]>(
    []
  );
  const pageContainerRefs = React.useRef<(HTMLDivElement | null)[]>([]);
  const scrollAreaRef = React.useRef<HTMLDivElement>(null);
  const topSentinelRef = React.useRef<HTMLDivElement>(null);
  const bottomSentinelRef = React.useRef<HTMLDivElement>(null);
  const containerRef = React.useRef<HTMLDivElement>(null);
  const isScrollingProgrammatically = React.useRef(false);
  const hasScrolledToHighlight = React.useRef(false);
  const ignoreSourceUpdateRef = React.useRef(false);
  const scrollTimeoutRef = React.useRef<NodeJS.Timeout | null>(null);

  // Cleanup refs on unmount to prevent memory leaks
  React.useEffect(() => {
    return () => {
      segmentRefs.current = [];
      pageContainerRefs.current = [];
    };
  }, []);

  // Update currentRef when sourceId changes
  // Clear scroll timeout when activeSource becomes null (pane closed)
  React.useEffect(() => {
    if (!activeSource && scrollTimeoutRef.current) {
      clearTimeout(scrollTimeoutRef.current);
      scrollTimeoutRef.current = null;
      ignoreSourceUpdateRef.current = false;
    }
  }, [activeSource]);

  // Update currentRef when sourceId changes
  React.useEffect(() => {
    if (sourceId) {
      setCurrentRef(sourceId.trim());
    }
  }, [sourceId]);

  // Resize ref arrays when textData changes to prevent memory leaks
  React.useEffect(() => {
    if (textData) {
      const totalSegments = textData.pages.reduce(
        (acc, page) => acc + page.segments.length,
        0
      );
      const totalPages = textData.pages.length;

      // Trim or expand segment refs array
      if (segmentRefs.current.length > totalSegments) {
        segmentRefs.current.length = totalSegments;
      }

      // Trim or expand page refs array
      if (pageContainerRefs.current.length > totalPages) {
        pageContainerRefs.current.length = totalPages;
      }
    }
  }, [textData]);

  // Convert single page to multi-page format
  const convertToMultiPage = (data: SinglePageTextData): MultiPageTextData => {
    const highlightIndices = data.highlight_indices || [];
    return {
      pages: [
        {
          ref: data.ref,
          segments: data.segments,
          highlight_index: highlightIndices.length > 0 ? highlightIndices[0] : null,
          highlight_indices: highlightIndices,
        },
      ],
      main_page_index: 0,
      index_title: data.index_title,
      version_title: data.version_title,
      language: data.language,
    };
  };

  // Initial load with multiple pages
  React.useEffect(() => {
    if (!sourceId) return;

    // If this update was triggered by our own scroll handler, ignore it
    if (ignoreSourceUpdateRef.current) {
      ignoreSourceUpdateRef.current = false;
      return;
    }

    // If this is a user navigation, cancel any pending scroll updates
    if (scrollTimeoutRef.current) {
      clearTimeout(scrollTimeoutRef.current);
      scrollTimeoutRef.current = null;
    }

    // Reset state for new source navigation
    hasScrolledToHighlight.current = false;
    setInitialScrollComplete(false);
    setHighlightedGlobalIndices([]); // Clear highlights when loading new source
    segmentRefs.current = []; // CRITICAL: Clear old element references
    pageContainerRefs.current = [];
    setCanLoadMore({ top: true, bottom: true });

    async function fetchText() {
      setIsLoading(true);
      setTextData(null); // CRITICAL: Clear stale data to prevent 'ghost scrolls'
      setError(null);

      // Reset scroll to top before loading new source to ensure consistent scrolling behavior
      const scrollViewport = scrollAreaRef.current?.querySelector(
        "[data-radix-scroll-area-viewport]"
      ) as HTMLElement;
      if (scrollViewport) {
        scrollViewport.scrollTop = 0;
      }

      try {
        const data = await sourceService.getInitial(
          sourceId!,
          0,
          activePagesAfter ?? 2
        );

        // Check if backend specifies pagination support
        setCanLoadMore(
          "can_load_more" in data && data.can_load_more
            ? data.can_load_more
            : { top: true, bottom: true }
        );

        // Check if it's multi-page or single-page response
        if ("pages" in data) {
          setTextData(data as MultiPageTextData);
        } else {
          setTextData(convertToMultiPage(data as SinglePageTextData));
        }
      } catch (err) {
        console.error(err);
        setError(err instanceof Error ? err.message : "Failed to load text.");
      } finally {
        setIsLoading(false);
      }
    }
    fetchText();
  }, [sourceId, refreshTrigger, activePagesAfter]);

  // Calculate global segment index and find highlighted segments
  const calculateHighlights = React.useCallback(() => {
    if (!textData) {
      setHighlightedGlobalIndices([]);
      return;
    }

    // Only highlight if activeTotalSegments is provided (meaning it came from search, not library)
    if (!activeTotalSegments) {
      setHighlightedGlobalIndices([]);
      return;
    }

    let globalIndex = 0;
    const calculatedHighlights: number[] = [];

    // First pass: Find all backend-provided highlights
    const backendHighlights: number[] = [];
    textData.pages.forEach((page, pageIndex) => {
      page.segments.forEach((_, segmentIndex) => {
        const isHighlighted =
          (pageIndex === textData.main_page_index &&
            page.highlight_index !== null &&
            page.highlight_index === segmentIndex) ||
          (page.highlight_indices && page.highlight_indices.includes(segmentIndex));

        if (isHighlighted) {
          backendHighlights.push(globalIndex);
        }
        globalIndex++;
      });
    });

    // Fallback: If no backend highlights, try to find the segment from activeSource ref
    if (backendHighlights.length === 0 && activeSource) {
      // Improved regex to handle colons, spaces, and commas followed by numbers
      const match = activeSource.match(/[:\s,]+(\d+)(?:-\d+)?$/);
      if (match) {
        const segNum = parseInt(match[1], 10);
        const targetIndex = segNum - 1;
        
        let currentIndex = 0;
        textData.pages.forEach((page, pageIndex) => {
          page.segments.forEach((_, segmentIndex) => {
            if (pageIndex === textData.main_page_index && segmentIndex === targetIndex) {
              backendHighlights.push(currentIndex);
            }
            currentIndex++;
          });
        });
      }
    }

    // If we have total segments count, we can manually determine the range starting from the first highlight
    if (backendHighlights.length > 0 && activeTotalSegments > 1) {
      const start = backendHighlights[0];
      for (let i = 0; i < activeTotalSegments; i++) {
        calculatedHighlights.push(start + i);
      }
    } else {
      // Use backend-provided highlights (or our parsed fallback)
      calculatedHighlights.push(...backendHighlights);
    }

    setHighlightedGlobalIndices(calculatedHighlights);
  }, [textData, activeTotalSegments, activeSource]);

  // Recalculate highlights whenever textData or related dependencies change
  React.useEffect(() => {
    calculateHighlights();
  }, [calculateHighlights]);

  // Scroll to highlighted segment when data loads
  React.useEffect(() => {
    if (!textData || hasScrolledToHighlight.current) return;

    // Only scroll if we have highlights (i.e., loaded from search, not library)
    if (highlightedGlobalIndices.length === 0) {
      setInitialScrollComplete(true);
      return;
    }

    let retryCount = 0;
    const maxRetries = 30; // 3 seconds
    let lastOffsetTop = -1;
    let stableCount = 0;
    
    const attemptScroll = () => {
      // Re-verify we still have data and haven't scrolled yet
      if (!textData) return;

      const targetIndex = highlightedGlobalIndices[0];
      if (targetIndex === undefined) {
        setInitialScrollComplete(true);
        return;
      }
      const targetElement = segmentRefs.current[targetIndex] as HTMLElement;
      const scrollViewport = scrollAreaRef.current?.querySelector(
        "[data-radix-scroll-area-viewport]"
      ) as HTMLElement;

      if (targetElement && scrollViewport && targetElement.offsetHeight > 0) {
        const currentOffsetTop = targetElement.offsetTop;
        
        // Wait for the layout to reach a steady state
        // Use >= 0 because elements at the top have offset 0
        if (currentOffsetTop >= 0 && currentOffsetTop === lastOffsetTop) {
          stableCount++;
        } else {
          lastOffsetTop = currentOffsetTop;
          stableCount = 0;
        }

        // Once the target has stopped 'jumping' for 300ms, we trigger the final scroll
        if (stableCount >= 3) {
          isScrollingProgrammatically.current = true;
          hasScrolledToHighlight.current = true;

          const viewportHeight = scrollViewport.clientHeight;
          const targetScrollTop = currentOffsetTop - (viewportHeight * 0.3);
          
          // Smoother, more controlled scroll
          scrollViewport.scrollTo({
            top: targetScrollTop,
            behavior: "smooth"
          });
          
          // Hold the lock for 1200ms to allow the smooth animation to finish
          setTimeout(() => {
            isScrollingProgrammatically.current = false;
            setInitialScrollComplete(true);
          }, 1500); // Increased timeout slightly to ensure completion
          return;
        }

        retryCount++;
        setTimeout(attemptScroll, 100);
      } else if (retryCount < maxRetries) {
        retryCount++;
        setTimeout(attemptScroll, 100);
      } else {
        setInitialScrollComplete(true);
      }
    };

    const timer = setTimeout(attemptScroll, 100);
    return () => clearTimeout(timer);
  }, [textData, highlightedGlobalIndices]);

  // Load previous pages
    const loadPreviousPages = React.useCallback(async () => {
    if (
      isLoadingTop ||
      !canLoadMore.top ||
      !textData ||
      textData.pages.length === 0
    )
      return;

    setIsLoadingTop(true);
    const firstPage = textData.pages[0];

    try {
      const data = await sourceService.getBefore(firstPage.ref);

      if ("pages" in data && data.pages.length > 1) {
        // Get only the pages before the first page (exclude the first page itself which is the last in the response)
        const newPages = data.pages.slice(0, -1);

        if (newPages.length > 0) {
          // Save current scroll position relative to the first visible element
          const scrollViewport = scrollAreaRef.current?.querySelector(
            "[data-radix-scroll-area-viewport]"
          );
          const oldScrollHeight = scrollViewport?.scrollHeight || 0;
          const oldScrollTop = scrollViewport?.scrollTop || 0;

          // Prepend new pages
          setTextData((prev) =>
            prev
              ? {
                  ...prev,
                  pages: [...newPages, ...prev.pages],
                  main_page_index: prev.main_page_index + newPages.length,
                }
              : null
          );

          // We need to restore scroll position immediately after render
          // We'll use a ref to store the adjustment needed
          scrollAdjustmentRef.current = { oldScrollHeight, oldScrollTop };
        } else {
          setCanLoadMore((prev) => ({ ...prev, top: false }));
        }
      } else {
        setCanLoadMore((prev) => ({ ...prev, top: false }));
      }
    } catch (err) {
      console.error("Error loading previous pages:", err);
      setCanLoadMore((prev) => ({ ...prev, top: false }));
    } finally {
      setIsLoadingTop(false);
    }
  }, [isLoadingTop, canLoadMore.top, textData]);

  // Scroll restoration effect
  const scrollAdjustmentRef = React.useRef<{
    oldScrollHeight: number;
    oldScrollTop: number;
  } | null>(null);

  React.useLayoutEffect(() => {
    if (scrollAdjustmentRef.current) {
      const scrollViewport = scrollAreaRef.current?.querySelector(
        "[data-radix-scroll-area-viewport]"
      );
      if (scrollViewport) {
        const newScrollHeight = scrollViewport.scrollHeight;
        const { oldScrollHeight, oldScrollTop } = scrollAdjustmentRef.current;
        const heightDiff = newScrollHeight - oldScrollHeight;

        // Only adjust if height increased (content added)
        if (heightDiff > 0) {
          scrollViewport.scrollTop = oldScrollTop + heightDiff;
        }
      }
      scrollAdjustmentRef.current = null;
    }
  }, [textData]);

  // Load next pages
  const loadNextPages = React.useCallback(async () => {
    if (
      isLoadingBottom ||
      !canLoadMore.bottom ||
      !textData ||
      textData.pages.length === 0
    )
      return;

    setIsLoadingBottom(true);
    const lastPage = textData.pages[textData.pages.length - 1];

    try {
      const data = await sourceService.getAfter(lastPage.ref);

      if ("pages" in data && data.pages.length > 1) {
        // Get only the pages after the last page (exclude the last page itself which is the first in the response)
        const newPages = data.pages.slice(1);

        if (newPages.length > 0) {
          setTextData((prev) =>
            prev
              ? {
                  ...prev,
                  pages: [...prev.pages, ...newPages],
                }
              : null
          );
        } else {
          setCanLoadMore((prev) => ({ ...prev, bottom: false }));
        }
      } else {
        setCanLoadMore((prev) => ({ ...prev, bottom: false }));
      }
    } catch (err) {
      console.error("Error loading next pages:", err);
      setCanLoadMore((prev) => ({ ...prev, bottom: false }));
    } finally {
      setIsLoadingBottom(false);
    }
  }, [isLoadingBottom, canLoadMore.bottom, textData]);

  // Intersection Observer for infinite scroll
  React.useEffect(() => {
    const scrollViewport = scrollAreaRef.current?.querySelector(
      "[data-radix-scroll-area-viewport]"
    );
    if (!scrollViewport) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.target === topSentinelRef.current) {
            setIsTopVisible(entry.isIntersecting);
          } else if (entry.target === bottomSentinelRef.current) {
            setIsBottomVisible(entry.isIntersecting);
          }
        });
      },
      {
        root: scrollViewport,
        rootMargin: "400px", // Load well before reaching the edge
        threshold: 0,
      }
    );

    if (topSentinelRef.current) observer.observe(topSentinelRef.current);
    if (bottomSentinelRef.current) observer.observe(bottomSentinelRef.current);

    return () => observer.disconnect();
  }, [textData]); // Re-attach when textData changes (DOM updates)

  // Trigger loads based on visibility
  React.useEffect(() => {
    if (
      isTopVisible &&
      canLoadMore.top &&
      !isLoadingTop &&
      !isLoading &&
      initialScrollComplete
    ) {
      loadPreviousPages();
    }
  }, [
    isTopVisible,
    canLoadMore.top,
    isLoadingTop,
    isLoading,
    loadPreviousPages,
    initialScrollComplete,
  ]);

  React.useEffect(() => {
    if (
      isBottomVisible &&
      canLoadMore.bottom &&
      !isLoadingBottom &&
      !isLoading &&
      initialScrollComplete
    ) {
      loadNextPages();
    }
  }, [
    isBottomVisible,
    canLoadMore.bottom,
    isLoadingBottom,
    isLoading,
    loadNextPages,
    initialScrollComplete,
  ]);

  // Scroll detection
  React.useEffect(() => {
    const scrollViewport = scrollAreaRef.current?.querySelector(
      "[data-radix-scroll-area-viewport]"
    );
    if (!scrollViewport) return;

    const handleScroll = () => {
      if (isScrollingProgrammatically.current) return;

      // Update current visible page reference
      if (textData && textData.pages.length > 0) {
        const viewportRect = scrollViewport.getBoundingClientRect();
        for (let i = 0; i < textData.pages.length; i++) {
          const pageEl = pageContainerRefs.current[i];
          if (pageEl) {
            const rect = pageEl.getBoundingClientRect();
            // Calculate position relative to viewport top
            const top = rect.top - viewportRect.top;
            const bottom = rect.bottom - viewportRect.top;

            // Check if this page is the main one visible
            // We consider a page "current" if its top is above the middle of the viewport
            // and its bottom is below the top of the viewport
            if (top < viewportRect.height / 2 && bottom > 0) {
              // If the pane is closed (activeSource is null), don't update the store
              // This prevents reopening the pane when it's animating out
              if (!activeSource) return;

              const rawPageRef = textData.pages[i].ref.trim();
              // Normalize the page ref the same way store does for reliable comparison
              const pageRef = rawPageRef.replace(/\s*:\s*/g, ":").replace(/\s+/g, " ");
              
              const isActiveRefSamePage = activeSource && (
                activeSource === pageRef || 
                activeSource.startsWith(pageRef + ":") || 
                activeSource.startsWith(pageRef + " ") ||
                activeSource.startsWith(pageRef + ",")
              );

              if (currentRef !== rawPageRef && !isActiveRefSamePage) {
                setCurrentRef(rawPageRef);
                
                if (scrollTimeoutRef.current) {
                  clearTimeout(scrollTimeoutRef.current);
                }
                
                scrollTimeoutRef.current = setTimeout(() => {
                  // Final check - only update if still on that page and not scrolling programmatically
                  if (isScrollingProgrammatically.current) return;
                  
                  ignoreSourceUpdateRef.current = true;
                  // Only update the page reference, leave targeting info intact if on same page
                  setActiveSource(rawPageRef);
                }, 500);
              }
              break;
            }
          }
        }
      }
    };

    scrollViewport.addEventListener("scroll", handleScroll);
    return () => scrollViewport.removeEventListener("scroll", handleScroll);
  }, [textData, canLoadMore, isLoadingTop, isLoadingBottom, currentRef, activeSource, setActiveSource]);

  const openSiblings = React.useCallback(() => {
    if (!currentRef) return;
    setSiblingsModalOpen(true);
  }, [currentRef]);

  const handleSelection = React.useCallback(() => {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
      setSelectionPopup(null);
      setSelectionRects([]);
      return;
    }

    const text = selection.toString().trim();
    if (!text) {
      setSelectionPopup(null);
      setSelectionRects([]);
      return;
    }

    if (!containerRef.current) return;

    setSelectedTextContent(text);

    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    const containerRect = containerRef.current.getBoundingClientRect();

    const allRects = Array.from(range.getClientRects());
    
    const textRects = allRects.filter((r) => {
      return r.height < 40;
    });
    
    const relativeRects = (textRects.length > 0 ? textRects : allRects).map((r) => ({
      left: r.left - containerRect.left,
      top: r.top - containerRect.top,
      width: r.width,
      height: r.height,
    }));
    
    setSelectionRects(relativeRects);

    setSelectionPopup({
      x: rect.left + rect.width / 2,
      y: rect.top,
    });
    
    setTimeout(() => {
      const sel = window.getSelection();
      if (sel) {
        sel.removeAllRanges();
      }
    }, 50);
  }, []);

  const handleCopy = React.useCallback(async () => {
    if (selectedTextContent) {
      try {
        await navigator.clipboard.writeText(selectedTextContent);
        setSelectionPopup(null);
        setSelectedTextContent("");
        setSelectionRects([]);
        setTimeout(() => {
          const selection = window.getSelection();
          if (selection) {
            selection.removeAllRanges();
          }
        }, 50);
      } catch (err) {
        console.error("Failed to copy text:", err);
      }
    }
  }, [selectedTextContent]);

  const handleAskChat = () => {
    if (selectedTextContent) {
      setSelectedText({
        id: nanoid(),
        text: selectedTextContent,
        sourceRef: currentRef,
      });
      
      setSelectionPopup(null);
      setSelectedTextContent("");
      setSelectionRects([]);
      
      setTimeout(() => {
        const selection = window.getSelection();
        if (selection) {
          selection.removeAllRanges();
        }
      }, 50);
    }
  };

  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!selectedTextContent || !selectionPopup) return;
      
      const isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
      const isCopyShortcut = isMac 
        ? (e.metaKey && e.key === "c")
        : (e.ctrlKey && e.key === "c");
      
      if (isCopyShortcut) {
        e.preventDefault();
        handleCopy();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedTextContent, selectionPopup, handleCopy]);

  // Update selection overlay positions when scrolling
  React.useEffect(() => {
    const scrollViewport = scrollAreaRef.current?.querySelector(
      "[data-radix-scroll-area-viewport]"
    );
    if (!scrollViewport) return;

    const handleScroll = () => {
      // Clear selection overlay and popup when scrolling
      if (selectionPopup || selectionRects.length > 0) {
        setSelectionPopup(null);
        setSelectionRects([]);
        setSelectedTextContent("");
      }
    };

    scrollViewport.addEventListener("scroll", handleScroll);
    return () => scrollViewport.removeEventListener("scroll", handleScroll);
  }, [selectionPopup, selectionRects]);

  const getFontSizeClass = () => {
    const sizes = {
      small: "text-base",
      medium: "text-lg",
      large: "text-xl",
      xlarge: "text-2xl",
    };
    return sizes[fontSize];
  };

  const isHebrew = textData?.language === "he";

  // Group segments by page for rendering with page headers
  const pageGroups: Array<{
    pageRef: string;
    heRef?: string;
    segments: Array<{
      segment: string;
      globalIndex: number;
      isHighlighted: boolean;
    }>;
  }> = [];

  let globalIndex = 0;

  if (textData) {
    textData.pages.forEach((page) => {
      const pageSegments: Array<{
        segment: string;
        globalIndex: number;
        isHighlighted: boolean;
      }> = [];

      page.segments.forEach((segment) => {
        const isHighlighted = highlightedGlobalIndices.includes(globalIndex);

        pageSegments.push({
          segment,
          globalIndex,
          isHighlighted,
        });
        globalIndex++;
      });

      pageGroups.push({
        pageRef: page.ref,
        heRef: page.he_ref,
        segments: pageSegments,
      });
    });
  }

  return (
    <div ref={containerRef} className="flex flex-col flex-1 z-50 min-w-20 h-full bg-primary-soft relative">
      {/* Reader Controls Header */}
      <header className={cn(
        "sticky top-0 z-50 bg-transparent pt-2 pb-4",
        isMobile ? "px-2" : "px-0"
      )}>
        <GlassCard
          variant="no_border"
          className={cn(
            "flex items-center z-52 bg-white hover:bg-primary-soft/80 transition-all duration-300 shadow-md justify-between px-4 py-[6px]",
            isMobile ? "mx-0" : "mx-2"
          )}
        >
          {/* Right: Display Settings */}
          <div className="flex items-center gap-1" dir="rtl">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                  <Settings2 className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel dir="rtl">
                  הגדרות תצוגה
                </DropdownMenuLabel>
                <DropdownMenuSeparator />

                <DropdownMenuLabel
                  dir="rtl"
                  className="text-xs font-normal text-muted-foreground flex items-center gap-2"
                >
                  <Type className="h-3 w-3" />
                  גודל גופן
                </DropdownMenuLabel>
                <DropdownMenuRadioGroup
                  dir="rtl"
                  value={fontSize}
                  onValueChange={(v) => setFontSize(v as FontSize)}
                >
                  <DropdownMenuRadioItem dir="rtl" value="small">
                    קטן
                  </DropdownMenuRadioItem>
                  <DropdownMenuRadioItem dir="rtl" value="medium">
                    בינוני
                  </DropdownMenuRadioItem>
                  <DropdownMenuRadioItem dir="rtl" value="large">
                    גדול
                  </DropdownMenuRadioItem>
                  <DropdownMenuRadioItem dir="rtl" value="xlarge">
                    גדול מאוד
                  </DropdownMenuRadioItem>
                </DropdownMenuRadioGroup>

                <DropdownMenuSeparator />

                <DropdownMenuLabel
                  dir="rtl"
                  className="text-xs font-normal text-muted-foreground flex items-center gap-2"
                >
                  <Languages className="h-3 w-3" />
                  סגנון תצוגה
                </DropdownMenuLabel>
                <DropdownMenuRadioGroup
                  dir="rtl"
                  value={layoutMode}
                  onValueChange={(v) => setLayoutMode(v as LayoutMode)}
                >
                  <DropdownMenuRadioItem dir="rtl" value="segmented">
                    מחולק
                  </DropdownMenuRadioItem>
                  <DropdownMenuRadioItem dir="rtl" value="continuous">
                    רציף
                  </DropdownMenuRadioItem>
                </DropdownMenuRadioGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          {/* Center: Title and Version Info */}
          <div className={cn("flex-1", isMobile ? "px-1" : "px-4")}>
            {textData && (
              <div className="text-center">
                <div className="flex items-center justify-center gap-2">
                  <h1
                    className={cn(
                      "font-semibold cursor-pointer hover:text-primary transition-colors truncate max-w-[150px] sm:max-w-none",
                      isMobile ? "text-sm" : "text-base"
                    )}
                    dir={isHebrew ? "rtl" : "ltr"}
                    onClick={openSiblings}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        openSiblings();
                      }
                    }}
                  >
                    {(() => {
                      const heTitle = textData?.he_title || textData?.heRef || textData?.he_ref;
                      // Find the current visible page based on currentRef (now using full refs)
                      const currentPage = textData?.pages?.find((page) => page.ref === currentRef);
                      
                      if (isHebrew) {
                        if (currentPage?.full_he_ref) return currentPage.full_he_ref;
                        if (currentPage?.he_ref) return currentPage.he_ref;
                        if (textData?.full_he_ref) return textData.full_he_ref;
                        if (textData?.he_ref) return textData.he_ref;
                        if (heTitle) return heTitle;
                        return convertToHebrew(currentRef);
                      }

                      // Non-Hebrew path
                      if (currentPage?.ref) return currentPage.ref;
                      return currentRef;
                    })()}
                  </h1>
                </div>
              </div>
            )}
          </div>

          {/* Left: Close button */}
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setActiveSource(null)}
              className="h-8 w-8 cursor-pointer"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </GlassCard>
      </header>

      {/* Text Content */}
      <ScrollArea
        ref={scrollAreaRef}
        className={cn(
          "h-full -mt-[29px]",
          isMobile ? "px-2" : "px-6"
        )}
      >
        <div className={cn(
          "max-w-4xl mx-auto py-8 pb-102",
          isMobile ? "px-2" : "px-6"
        )}>
          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <div className="flex flex-col items-center gap-3">
                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary"></div>
                <p className="text-sm text-muted-foreground">טוען טקסט...</p>
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center py-20">
              <div className="text-center max-w-md">
                <div className="text-destructive mb-2">⚠️</div>
                <p className="text-sm text-muted-foreground">{error}</p>
              </div>
            </div>
          ) : textData ? (
            <>
              <div ref={topSentinelRef} className="h-px w-full " />
              {/* Loading indicator for top */}
              {isLoadingTop && (
                <div className="flex justify-center py-4">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
                </div>
              )}

              <div
                dir={isHebrew ? "rtl" : "ltr"}
                onMouseUp={handleSelection}
              >
                {layoutMode === "segmented" ? (
                  // Segmented view with page headers
                  <div className="space-y-6">
                    {pageGroups.map((pageGroup, pageGroupIndex) => (
                      <div
                        key={`${pageGroup.pageRef}-${pageGroupIndex}`}
                        className="page-group"
                        ref={(el) => {
                          pageContainerRefs.current[pageGroupIndex] = el;
                        }}
                        data-page-ref={pageGroup.pageRef}
                      >
                        {/* Page Title Header */}
                        <div className="mb-4 pb-1 border-b-4 w-fit mx-auto justify-center">
                          <h2
                            className="text-lg font-semibold text-foreground/80"
                            dir={isHebrew ? "rtl" : "ltr"}
                          >
                            {(() => {
                              // If available, use Hebrew Ref directly for Hebrew context
                              if (pageGroup.heRef && isHebrew) {
                                  const heIndexTitle = textData?.he_title || "";
                                  let display = pageGroup.heRef.replace(heIndexTitle, "").trim();
                                  display = display.replace(/^,\s*/, "");
                                  // Prefer the most specific token (last segment after comma/space)
                                  if (display.includes(",")) {
                                    display = display.split(",").slice(-1)[0].trim();
                                  }
                                  const parts = display.split(/\s+/).filter(Boolean);
                                  if (parts.length > 0) {
                                    display = parts[parts.length - 1];
                                  }
                                  return display;
                              }
                              // Strip index title from page ref to show only the section (e.g. "10b")
                              const indexTitle = textData?.index_title || "";
                              const displayRef = pageGroup.pageRef.replace(indexTitle, "").trim();
                              return convertToHebrew(displayRef || pageGroup.pageRef);
                            })()}
                          </h2>
                        </div>

                        {/* Page Segments */}
                        <div className="space-y-1">
                          {pageGroup.segments.map((item) => (
                            <div
                              key={`${pageGroup.pageRef}-${item.globalIndex}`}
                              ref={(el) => {
                                segmentRefs.current[item.globalIndex] = el;
                              }}
                              className={`
                                flex gap-3
                                ${getFontSizeClass()}
                                leading-relaxed
                                py-2 px-3
                                rounded-sm
                                ${
                                  item.isHighlighted
                                    ? "bg-yellow-100 dark:bg-yellow-900/20 shadow-sm"
                                    : ""
                                }
                              `}
                            >
                              {/* Segment text */}
                              <span
                                className={`
                                  flex-1
                                  ${
                                    isHebrew
                                      ? "font-hebrew order-1"
                                      : "font-sans order-2"
                                  }
                                `}
                                dangerouslySetInnerHTML={{
                                  __html: item.segment,
                                }}
                              />
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  // Continuous view with truly flowing text and margin numbers
                  <div className="space-y-6">
                    {pageGroups.map((pageGroup, pageGroupIndex) => (
                      <div
                        key={`${pageGroup.pageRef}-${pageGroupIndex}`}
                        className="page-group"
                        ref={(el) => {
                          pageContainerRefs.current[pageGroupIndex] = el;
                        }}
                        data-page-ref={pageGroup.pageRef}
                      >
                        {/* Page Title Header */}
                        <div className="mb-4 pb-1 border-b-4 w-fit mx-auto justify-center">
                          <h2
                            className="text-lg font-semibold text-foreground/80"
                            dir={isHebrew ? "rtl" : "ltr"}
                          >
                            {(() => {
                              // If available, use Hebrew Ref directly for Hebrew context
                              if (pageGroup.heRef && isHebrew) {
                                  const heIndexTitle = textData?.he_title || "";
                                  let display = pageGroup.heRef.replace(heIndexTitle, "").trim();
                                  display = display.replace(/^,\s*/, "");
                                  if (display.includes(",")) {
                                    display = display.split(",").slice(-1)[0].trim();
                                  }
                                  const parts = display.split(/\s+/).filter(Boolean);
                                  if (parts.length > 0) {
                                    display = parts[parts.length - 1];
                                  }
                                  return display;
                              }
                              // Strip index title from page ref to show only the section (e.g. "10b")
                              const indexTitle = textData?.index_title || "";
                              const displayRef = pageGroup.pageRef.replace(indexTitle, "").trim();
                              return convertToHebrew(displayRef || pageGroup.pageRef);
                            })()}
                          </h2>
                        </div>

                        {/* Page Segments - Continuous flowing text without numbers */}
                        <div className="flex gap-3">
                          {/* Flowing text content */}
                          <div
                            className={`
                              flex-1
                              ${getFontSizeClass()}
                              leading-relaxed
                              ${
                                isHebrew
                                  ? "order-1 font-hebrew"
                                  : "order-2 font-sans"
                              }
                            `}
                            dir={isHebrew ? "rtl" : "ltr"}
                          >
                            {pageGroup.segments.map((item) => (
                              <span
                                key={`${pageGroup.pageRef}-${item.globalIndex}`}
                                ref={(el) => {
                                  segmentRefs.current[item.globalIndex] = el;
                                }}
                                className={`
                                  ${
                                    item.isHighlighted
                                      ? "bg-yellow-100 dark:bg-yellow-900/20 px-1 rounded"
                                      : ""
                                  }
                                `}
                                dangerouslySetInnerHTML={{
                                  __html: item.segment + " ",
                                }}
                              />
                            ))}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Loading indicator for bottom */}
              {isLoadingBottom && (
                <div className="flex justify-center py-4">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
                </div>
              )}
              <div ref={bottomSentinelRef} className="h-px w-full" />
            </>
          ) : (
            <div className="flex items-center justify-center py-20">
              <div className="text-center">
                <BookOpen className="h-12 w-12 text-muted-foreground/50 mx-auto mb-3" />
                <p className="text-sm text-muted-foreground">
                  Select a source to view
                </p>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Custom selection overlay - shows exact selected text */}
      {selectionRects.length > 0 && (
        <div className="pointer-events-none absolute inset-0 z-99">
          {selectionRects.map((rect, index) => (
            <div
              key={index}
              className="absolute bg-primary/20 border border-primary/30"
              style={{
                left: `${rect.left}px`,
                top: `${rect.top}px`,
                width: `${rect.width}px`,
                height: `${rect.height}px`,
              }}
            />
          ))}
        </div>
      )}

      <TextSelectionPopup 
        position={selectionPopup} 
        onAskChat={handleAskChat}
        onCopy={handleCopy}
      />
      <SourceSiblingsModal
        open={siblingsModalOpen}
        onOpenChange={setSiblingsModalOpen}
        currentRef={currentRef || sourceId}
      />
    </div>
  );
}
