'use client';

import React from 'react';
import { useLayoutStore } from '@/lib/store/useLayoutStore';
import { convertToHebrew } from '@/lib/hebrewUtils';
import { Button } from '@/components/ui/button';
import { X, Settings2, BookOpen, Type, Languages } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
} from '@/components/ui/dropdown-menu';

interface SourceViewerPaneProps {
  sourceId: string | null;
}

interface PageData {
  ref: string;
  segments: string[];
  highlight_index: number | null;
  highlight_indices?: number[];
}

interface MultiPageTextData {
  pages: PageData[];
  main_page_index: number;
  index_title: string;
  version_title: string;
  language: string;
}

interface SinglePageTextData {
  ref: string;
  index_title: string;
  version_title: string;
  language: string;
  segments: string[];
  highlight_index: number | null;
  highlight_indices?: number[];
}

type FontSize = 'small' | 'medium' | 'large' | 'xlarge';
type LayoutMode = 'continuous' | 'segmented';

export function SourceViewerPane({ sourceId }: SourceViewerPaneProps) {
  const { setActiveSource } = useLayoutStore();
  const [textData, setTextData] = React.useState<MultiPageTextData | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [isLoadingTop, setIsLoadingTop] = React.useState(false);
  const [isLoadingBottom, setIsLoadingBottom] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [fontSize, setFontSize] = React.useState<FontSize>('medium');
  const [layoutMode, setLayoutMode] = React.useState<LayoutMode>('segmented');
  const [canLoadMore, setCanLoadMore] = React.useState({ top: true, bottom: true });
  const [currentRef, setCurrentRef] = React.useState(sourceId || '');
  const [isTopVisible, setIsTopVisible] = React.useState(false);
  const [isBottomVisible, setIsBottomVisible] = React.useState(false);
  const [initialScrollComplete, setInitialScrollComplete] = React.useState(false);
  const segmentRefs = React.useRef<(HTMLDivElement | HTMLSpanElement | null)[]>([]);
  const pageContainerRefs = React.useRef<(HTMLDivElement | null)[]>([]);
  const scrollAreaRef = React.useRef<HTMLDivElement>(null);
  const topSentinelRef = React.useRef<HTMLDivElement>(null);
  const bottomSentinelRef = React.useRef<HTMLDivElement>(null);
  const isScrollingProgrammatically = React.useRef(false);
  const hasScrolledToHighlight = React.useRef(false);
  // Update currentRef when sourceId changes
  React.useEffect(() => {
    if (sourceId) {
      setCurrentRef(sourceId);
    }
  }, [sourceId]);

  // Convert single page to multi-page format
  const convertToMultiPage = (data: SinglePageTextData): MultiPageTextData => {
    return {
      pages: [{
        ref: data.ref,
        segments: data.segments,
        highlight_index: data.highlight_index,
        highlight_indices: data.highlight_indices
      }],
      main_page_index: 0,
      index_title: data.index_title,
      version_title: data.version_title,
      language: data.language
    };
  };

  // Initial load with multiple pages
  React.useEffect(() => {
    if (!sourceId) return;
    
    // Reset the scroll flag when sourceId changes
    hasScrolledToHighlight.current = false;
    setInitialScrollComplete(false);
    setCanLoadMore({ top: true, bottom: true });
    
    async function fetchText() {
      setIsLoading(true);
      setError(null);
      try {
        // Load 2 pages before + main page + 2 pages after
        const res = await fetch(`/api/py/api/source/${encodeURIComponent(sourceId!)}?pages_before=2&pages_after=2`);
        if (!res.ok) {
          const errorData = await res.json();
          throw new Error(errorData.detail || 'Failed to fetch text');
        }
        const data = await res.json();
        
        // Check if it's multi-page or single-page response
        if ('pages' in data) {
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
  }, [sourceId]);

  // Calculate global segment index and find highlighted segments
  const getGlobalSegmentData = () => {
    if (!textData) return { totalSegments: 0, highlightedGlobalIndices: [] as number[] };
    
    let globalIndex = 0;
    const highlightedGlobalIndices: number[] = [];
    
    textData.pages.forEach((page, pageIndex) => {
      page.segments.forEach((_, segmentIndex) => {
        // Check for single highlight (legacy/scroll target)
        const isSingleHighlight = pageIndex === textData.main_page_index && page.highlight_index === segmentIndex;
        
        // Check for range highlight
        const isRangeHighlight = page.highlight_indices?.includes(segmentIndex);
        
        if (isSingleHighlight || isRangeHighlight) {
          highlightedGlobalIndices.push(globalIndex);
        }
        globalIndex++;
      });
    });
    
    return { totalSegments: globalIndex, highlightedGlobalIndices };
  };

  // Scroll to highlighted segment when data loads (only on initial load)
  React.useEffect(() => {
    // Only scroll to highlight if we haven't done it yet
    if (hasScrolledToHighlight.current) return;
    
    const { highlightedGlobalIndices } = getGlobalSegmentData();
    
    // Scroll to the first highlighted segment
    if (highlightedGlobalIndices.length > 0 && segmentRefs.current[highlightedGlobalIndices[0]]) {
      isScrollingProgrammatically.current = true;
      hasScrolledToHighlight.current = true; // Mark that we've scrolled
      
      setTimeout(() => {
        const targetElement = segmentRefs.current[highlightedGlobalIndices[0]];
        const scrollViewport = scrollAreaRef.current?.querySelector('[data-radix-scroll-area-viewport]');
        
        if (targetElement && scrollViewport) {
          const targetRect = targetElement.getBoundingClientRect();
          const viewportRect = scrollViewport.getBoundingClientRect();
          const targetRelativeTop = targetRect.top - viewportRect.top + scrollViewport.scrollTop;
          const viewportHeight = scrollViewport.clientHeight;
          const targetHeight = targetRect.height;
          // Scroll to 60% of viewport height (slightly below center) to reduce scroll distance and time
          const scrollPosition = targetRelativeTop - (viewportHeight * 0.6) + (targetHeight / 2);
          
          scrollViewport.scrollTo({
            top: scrollPosition,
            behavior: 'smooth'
          });
          
          setTimeout(() => {
            isScrollingProgrammatically.current = false;
            setInitialScrollComplete(true);
          }, 400);
        } else {
             // Fallback if element not found (shouldn't happen if index is valid)
             setInitialScrollComplete(true);
        }
      }, 200); // Reduced delay for faster feel
    } else if (textData) {
        // If data loaded but no highlight (or element missing), mark as done
        setInitialScrollComplete(true);
    }
  }, [textData]);

  // Load previous pages
  const loadPreviousPages = React.useCallback(async () => {
    if (isLoadingTop || !canLoadMore.top || !textData || textData.pages.length === 0) return;
    
    setIsLoadingTop(true);
    const firstPage = textData.pages[0];
    
    try {
      const res = await fetch(`/api/py/api/source/${encodeURIComponent(firstPage.ref)}?pages_before=2&pages_after=0`);
      if (!res.ok) throw new Error('Failed to fetch previous pages');
      
      const data = await res.json();
      
      if ('pages' in data && data.pages.length > 1) {
        // Get only the pages before the first page (exclude the first page itself which is the last in the response)
        const newPages = data.pages.slice(0, -1);
        
        if (newPages.length > 0) {
          // Save current scroll position relative to the first visible element
          const scrollViewport = scrollAreaRef.current?.querySelector('[data-radix-scroll-area-viewport]');
          const oldScrollHeight = scrollViewport?.scrollHeight || 0;
          const oldScrollTop = scrollViewport?.scrollTop || 0;
          
          // Prepend new pages
          setTextData(prev => prev ? {
            ...prev,
            pages: [...newPages, ...prev.pages],
            main_page_index: prev.main_page_index + newPages.length
          } : null);
          
          // We need to restore scroll position immediately after render
          // We'll use a ref to store the adjustment needed
          scrollAdjustmentRef.current = { oldScrollHeight, oldScrollTop };
        } else {
          setCanLoadMore(prev => ({ ...prev, top: false }));
        }
      } else {
        setCanLoadMore(prev => ({ ...prev, top: false }));
      }
    } catch (err) {
      console.error('Error loading previous pages:', err);
      setCanLoadMore(prev => ({ ...prev, top: false }));
    } finally {
      setIsLoadingTop(false);
    }
  }, [isLoadingTop, canLoadMore.top, textData]);

  // Scroll restoration effect
  const scrollAdjustmentRef = React.useRef<{ oldScrollHeight: number, oldScrollTop: number } | null>(null);

  React.useLayoutEffect(() => {
    if (scrollAdjustmentRef.current) {
      const scrollViewport = scrollAreaRef.current?.querySelector('[data-radix-scroll-area-viewport]');
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
    if (isLoadingBottom || !canLoadMore.bottom || !textData || textData.pages.length === 0) return;
    
    setIsLoadingBottom(true);
    const lastPage = textData.pages[textData.pages.length - 1];
    
    try {
      const res = await fetch(`/api/py/api/source/${encodeURIComponent(lastPage.ref)}?pages_before=0&pages_after=2`);
      if (!res.ok) throw new Error('Failed to fetch next pages');
      
      const data = await res.json();
      
      if ('pages' in data && data.pages.length > 1) {
        // Get only the pages after the last page (exclude the last page itself which is the first in the response)
        const newPages = data.pages.slice(1);
        
        if (newPages.length > 0) {
          setTextData(prev => prev ? {
            ...prev,
            pages: [...prev.pages, ...newPages]
          } : null);
        } else {
          setCanLoadMore(prev => ({ ...prev, bottom: false }));
        }
      } else {
        setCanLoadMore(prev => ({ ...prev, bottom: false }));
      }
    } catch (err) {
      console.error('Error loading next pages:', err);
      setCanLoadMore(prev => ({ ...prev, bottom: false }));
    } finally {
      setIsLoadingBottom(false);
    }
  }, [isLoadingBottom, canLoadMore.bottom, textData]);

  // Intersection Observer for infinite scroll
  React.useEffect(() => {
    const scrollViewport = scrollAreaRef.current?.querySelector('[data-radix-scroll-area-viewport]');
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
        rootMargin: '400px', // Load well before reaching the edge
        threshold: 0,
      }
    );

    if (topSentinelRef.current) observer.observe(topSentinelRef.current);
    if (bottomSentinelRef.current) observer.observe(bottomSentinelRef.current);

    return () => observer.disconnect();
  }, [textData]); // Re-attach when textData changes (DOM updates)

  // Trigger loads based on visibility
  React.useEffect(() => {
    if (isTopVisible && canLoadMore.top && !isLoadingTop && !isLoading && initialScrollComplete) {
      loadPreviousPages();
    }
  }, [isTopVisible, canLoadMore.top, isLoadingTop, isLoading, loadPreviousPages, initialScrollComplete]);

  React.useEffect(() => {
    if (isBottomVisible && canLoadMore.bottom && !isLoadingBottom && !isLoading && initialScrollComplete) {
      loadNextPages();
    }
  }, [isBottomVisible, canLoadMore.bottom, isLoadingBottom, isLoading, loadNextPages, initialScrollComplete]);

  // Scroll detection
  React.useEffect(() => {
    const scrollViewport = scrollAreaRef.current?.querySelector('[data-radix-scroll-area-viewport]');
    if (!scrollViewport) return;
    
    const handleScroll = () => {
      if (isScrollingProgrammatically.current) return;
      
      // Update current visible page reference
      if (textData && textData.pages.length > 0) {
        const viewportRect = scrollViewport.getBoundingClientRect();
        let foundVisible = false;

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
              if (currentRef !== textData.pages[i].ref) {
                setCurrentRef(textData.pages[i].ref);
              }
              foundVisible = true;
              break;
            }
          }
        }
      }
    };
    
    scrollViewport.addEventListener('scroll', handleScroll);
    return () => scrollViewport.removeEventListener('scroll', handleScroll);
  }, [textData, canLoadMore, isLoadingTop, isLoadingBottom, currentRef]);

  const getFontSizeClass = () => {
    const sizes = {
      small: 'text-base',
      medium: 'text-lg',
      large: 'text-xl',
      xlarge: 'text-2xl'
    };
    return sizes[fontSize];
  };

  const isHebrew = textData?.language === 'he';

  // Group segments by page for rendering with page headers
  const pageGroups: Array<{
    pageRef: string;
    segments: Array<{ segment: string; globalIndex: number; isHighlighted: boolean }>;
  }> = [];
  
  let globalIndex = 0;
  
  if (textData) {
    textData.pages.forEach((page, pageIndex) => {
      const pageSegments: Array<{ segment: string; globalIndex: number; isHighlighted: boolean }> = [];
      
      page.segments.forEach((segment, segmentIndex) => {
        const isHighlighted = (pageIndex === textData.main_page_index && segmentIndex === page.highlight_index) || 
                              (page.highlight_indices?.includes(segmentIndex) ?? false);

        pageSegments.push({
          segment,
          globalIndex,
          isHighlighted
        });
        globalIndex++;
      });
      
      pageGroups.push({
        pageRef: page.ref,
        segments: pageSegments
      });
    });
  }

  return (
    <div className="flex flex-col flex-1 min-w-0 h-full bg-background">
      {/* Reader Controls Header */}
      <header className="bg-transparent">
        <div className="flex items-center justify-between border mt-2 mx-2 px-4 py-[6px] rounded-2xl">

                    {/* Right: Display Settings */}
                    <div className="flex items-center gap-1" dir="rtl">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                  <Settings2 className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56" >
                <DropdownMenuLabel dir="rtl">Display Settings</DropdownMenuLabel>
                <DropdownMenuSeparator />
                
                <DropdownMenuLabel dir="rtl" className="text-xs font-normal text-muted-foreground flex items-center gap-2">
                  <Type className="h-3 w-3" />
                  Font Size
                </DropdownMenuLabel>
                <DropdownMenuRadioGroup dir="rtl" value={fontSize} onValueChange={(v) => setFontSize(v as FontSize)}>
                  <DropdownMenuRadioItem dir="rtl" value="small">קטן</DropdownMenuRadioItem>
                  <DropdownMenuRadioItem dir="rtl" value="medium">בינוני</DropdownMenuRadioItem>
                  <DropdownMenuRadioItem dir="rtl" value="large">גדול</DropdownMenuRadioItem>
                  <DropdownMenuRadioItem dir="rtl" value="xlarge">גדול מאוד</DropdownMenuRadioItem>
                </DropdownMenuRadioGroup>

                <DropdownMenuSeparator />
                
                <DropdownMenuLabel dir="rtl" className="text-xs font-normal text-muted-foreground flex items-center gap-2">
                  <Languages className="h-3 w-3" />
                  סגנון תצוגה
                </DropdownMenuLabel>
                <DropdownMenuRadioGroup dir="rtl" value={layoutMode} onValueChange={(v) => setLayoutMode(v as LayoutMode)}>
                  <DropdownMenuRadioItem dir="rtl" value="segmented">מחולק</DropdownMenuRadioItem>
                  <DropdownMenuRadioItem dir="rtl" value="continuous">רציף</DropdownMenuRadioItem>
                </DropdownMenuRadioGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>


          {/* Center: Title and Version Info */}
          <div className="flex-1 px-4">
            {textData && (
              <div className="text-center">
                <div className="flex items-center justify-center gap-2">
                  <BookOpen className="h-4 w-4 text-muted-foreground" />
                  <h1 className="font-semibold text-base" dir={isHebrew ? 'rtl' : 'ltr'}>
                    {convertToHebrew(currentRef)}
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
              className="h-8 w-8"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>

        </div>
      </header>

      {/* Text Content */}
      <ScrollArea ref={scrollAreaRef} className="h-full px-6">
        <div className="max-w-4xl mx-auto px-6 py-8 pb-102">
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
              <div ref={topSentinelRef} className="h-px w-full" />
              {/* Loading indicator for top */}
              {isLoadingTop && (
                <div className="flex justify-center py-4">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
                </div>
              )}
              
              <div dir={isHebrew ? 'rtl' : 'ltr'}>
                {layoutMode === 'segmented' ? (
                  // Segmented view with page headers
                  <div className="space-y-6">
                    {pageGroups.map((pageGroup, pageGroupIndex) => (
                      <div 
                        key={pageGroup.pageRef} 
                        className="page-group"
                        ref={(el) => { pageContainerRefs.current[pageGroupIndex] = el; }}
                        data-page-ref={pageGroup.pageRef}
                      >
                        {/* Page Title Header */}
                        <div className="mb-4 pb-2 border-b border-border/50">
                          <h2 
                            className="text-lg font-semibold text-foreground/80"
                            dir={isHebrew ? 'rtl' : 'ltr'}
                          >
                            {convertToHebrew(pageGroup.pageRef)}
                          </h2>
                        </div>
                        
                        {/* Page Segments */}
                        <div className="space-y-1">
                          {pageGroup.segments.map((item) => (
                            <div
                              key={`${pageGroup.pageRef}-${item.globalIndex}`}
                              ref={(el) => { segmentRefs.current[item.globalIndex] = el; }}
                              className={`
                                flex gap-3
                                ${getFontSizeClass()}
                                leading-relaxed 
                                py-2 px-3
                                rounded-sm
                                transition-all duration-200
                                cursor-pointer
                                ${item.isHighlighted
                                  ? 'bg-yellow-100 dark:bg-yellow-900/20 shadow-sm' 
                                  : 'hover:bg-accent/50'
                                }
                              `}
                            >
                              {/* Segment text */}
                              <span 
                                className={`
                                  flex-1
                                  ${isHebrew ? 'font-hebrew order-1' : 'font-sans order-2'}
                                `}
                                dangerouslySetInnerHTML={{ __html: item.segment }}
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
                        key={pageGroup.pageRef} 
                        className="page-group"
                        ref={(el) => { pageContainerRefs.current[pageGroupIndex] = el; }}
                        data-page-ref={pageGroup.pageRef}
                      >
                        {/* Page Title Header */}
                        <div className="mb-4 pb-2 border-b border-border/50">
                          <h2 
                            className="text-lg font-semibold text-foreground/80"
                            dir={isHebrew ? 'rtl' : 'ltr'}
                          >
                            {convertToHebrew(pageGroup.pageRef)}
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
                              ${isHebrew ? 'order-1 font-hebrew' : 'order-2 font-sans'}
                            `}
                            dir={isHebrew ? 'rtl' : 'ltr'}
                          >
                            {pageGroup.segments.map((item) => (
                              <span
                                key={`${pageGroup.pageRef}-${item.globalIndex}`}
                                ref={(el) => { segmentRefs.current[item.globalIndex] = el; }}
                                className={`
                                  ${item.isHighlighted
                                    ? 'bg-yellow-100 dark:bg-yellow-900/20 px-1 rounded' 
                                    : ''
                                  }
                                `}
                                dangerouslySetInnerHTML={{ __html: item.segment + ' ' }}
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
                <p className="text-sm text-muted-foreground">Select a source to view</p>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
