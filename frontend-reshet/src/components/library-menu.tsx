"use client";

import * as React from "react";
import { ChevronLeft, ChevronRight, Book, Folder, Home } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SidebarMenuButton, useSidebar } from "@/components/ui/sidebar";
import { Skeleton } from "@/components/ui/skeleton";
import { libraryService } from "@/services";
import type { LibraryNode } from "@/services/library";
import { useDirection } from "./direction-provider";
import { cn } from "@/lib/utils";
import { useLayoutStore } from "@/lib/store/useLayoutStore";

type TreeNode = LibraryNode;

interface LibraryMenuProps {
  onBack: () => void; // To exit library mode
}

export function LibraryMenu({ onBack }: LibraryMenuProps) {
  const [root, setRoot] = React.useState<TreeNode[]>([]);
  const [path, setPath] = React.useState<TreeNode[]>([]);
  const { libraryPathTitles, setLibraryPathTitles, setActiveSource } = useLayoutStore();
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [loadingSlug, setLoadingSlug] = React.useState<string | null>(null);
  const initialLibraryPathTitles = React.useRef(libraryPathTitles);
  const { direction } = useDirection();
  const isRTL = direction === "rtl";
  const { state } = useSidebar()
  const isCollapsed = state === "collapsed";
  const internalUpdateRef = React.useRef(false);

  const getChildren = React.useCallback(async (node: TreeNode) => {
    if (!node.slug) return [];
    if (node.children) return node.children;
    
    setLoadingSlug(node.slug);
    try {
      const children = await libraryService.getChildren(node.slug);
      node.children = children; // Cache in the node object
      setLoadingSlug(null);
      return children;
    } catch {
      setError("Failed to load library menu");
      setLoadingSlug(null);
      return [];
    }
  }, []);

  // Sync with store path when it changes externally
  React.useEffect(() => {
    if (loading || root.length === 0) return;

    const syncPath = async () => {
      const isInternal = internalUpdateRef.current;
      internalUpdateRef.current = false;

      if (isInternal) return;

      // Check if path already matches
      const currentPathTitles = path.map(n => n.title);
      if (JSON.stringify(currentPathTitles) === JSON.stringify(libraryPathTitles)) {
        return;
      }

      // External update (e.g. from SourceSiblingsModal or Home reset)
      const newPath: TreeNode[] = [];
      let currentLevel = root;
      for (const title of libraryPathTitles) {
        const node = currentLevel.find((n) => n.title === title);
        if (!node) break;
        if (node.hasChildren && !node.children && node.slug) {
          await getChildren(node);
        }
        newPath.push(node);
        currentLevel = node.children || [];
      }
      setPath(newPath);
    };

    syncPath();
  }, [libraryPathTitles, root, loading, getChildren]);

  React.useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await libraryService.getRoot();
        if (cancelled) return;
        setRoot(data);
        setLoading(false);

        // Initial path restoration
        if (libraryPathTitles.length > 0) {
          const newPath: TreeNode[] = [];
          let currentLevel = data;
          for (const title of libraryPathTitles) {
            const node = currentLevel.find((n) => n.title === title);
            if (!node) break;
            if (node.hasChildren && !node.children && node.slug) {
              await getChildren(node);
            }
            newPath.push(node);
            currentLevel = node.children || [];
          }
          if (!cancelled) {
            setPath(newPath);
          }
        }
      } catch {
        if (!cancelled) {
          setError("Failed to load library menu");
          setLoading(false);
        }
      }
    };
    load();
    return () => { cancelled = true; };
  }, [getChildren]); // libraryPathTitles intentionally omitted here to handle it in separate effect

  const [visibleItems, setVisibleItems] = React.useState(20);

  const currentLevel = React.useMemo(() => {
    return path.length === 0 ? root : path[path.length - 1].children || [];
  }, [path, root]);

  const currentTitle = React.useMemo(() => {
    if (path.length === 0) return isRTL ? "הספרייה" : "Library";
    const last = path[path.length - 1];
    return (isRTL && last.heTitle) ? last.heTitle : last.title;
  }, [path, isRTL]);

  // Reset visible items when navigating
  React.useEffect(() => {
    setVisibleItems(20);
    
    if (currentLevel.length > 20) {
      const timer = setInterval(() => {
        setVisibleItems((prev) => {
          if (prev >= currentLevel.length) {
            clearInterval(timer);
            return prev;
          }
          return prev + 50;
        });
      }, 50);
      return () => clearInterval(timer);
    }
  }, [currentLevel]);

  const handleNavigate = async (node: TreeNode) => {
    if (node.hasChildren) {
      if (!node.children && node.slug) {
        await getChildren(node);
      }
      const newPath = [...path, node];
      setPath(newPath);
      internalUpdateRef.current = true;
      setLibraryPathTitles(newPath.map(n => n.title));
    } else if (node.ref) {
      setActiveSource(node.ref);
    }
  };

  const handleGoUp = () => {
    if (path.length > 0) {
      const newPath = path.slice(0, -1);
      setPath(newPath);
      internalUpdateRef.current = true;
      setLibraryPathTitles(newPath.map(n => n.title));
    } else {
      // Exit library mode and reset path
      setLibraryPathTitles([]);
      onBack();
    }
  };

  const handleHome = () => {
    setLibraryPathTitles([]);
    onBack();
  };

  if (loading) {
    return (
      <div className="p-4 space-y-2" dir={direction}>
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-center text-red-500" dir={direction}>
        <p>{error}</p>
        <Button variant="outline" size="sm" onClick={onBack} className="mt-2">
          Go Back
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full" dir={direction}>
      <div className="flex items-center gap-2 p-2 border-b">
        <Button variant="ghost" size="icon" onClick={handleGoUp} className="h-8 w-8">
          {isRTL ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
        <h2 className={cn("font-semibold text-sm truncate flex-1", isRTL ? "text-right" : "text-left")}>
          {currentTitle}
        </h2>
        <Button
          variant="ghost"
          size="icon"
          onClick={handleHome}
          className={cn("h-8 w-8", isRTL ? "mr-auto" : "ml-auto")}
          aria-label="Home"
        >
          <Home className="h-4 w-4" />
        </Button>
      </div>
      
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <div className="p-0 space-y-0" dir={direction}>
          {currentLevel.slice(0, visibleItems).map((node, idx) => (
            <SidebarMenuButton
              key={node.slug ?? `${node.title}-${idx}`}
              className={cn(
                "w-full font-normal min-w-0 transition-none",
                isRTL ? "justify-start text-right" : "justify-start text-left",
                isCollapsed ? "m-2" : "m-0"
              )}
              onClick={() => handleNavigate(node)}
              disabled={loadingSlug === node.slug}
              tooltip={(isRTL && node.heTitle) ? node.heTitle : node.title}
            >
              {node.type === "category" ? (
                <Folder className={cn("h-4 w-4 text-muted-foreground shrink-0", isRTL ? "ml-1" : "mr-1")} />
              ) : (
                <Book className={cn("h-4 w-4 text-muted-foreground shrink-0", isRTL ? "ml-1" : "mr-1")} />
              )}
              <span
                dir={direction}
                className={cn("truncate flex-1 h-fit leading-tight py-1", isRTL ? "text-right" : "text-left")}
              >
                {(isRTL && node.heTitle) ? node.heTitle : node.title}
              </span>
              {node.hasChildren && (
                <ChevronRight className={cn("h-4 w-4 opacity-50 shrink-0", isRTL ? "rotate-180 mr-auto" : "ml-auto")} />
              )}
            </SidebarMenuButton>
          ))}
          {currentLevel.length > visibleItems && (
            <div className="text-center text-muted-foreground text-xs py-2">
              Loading more...
            </div>
          )}
          {currentLevel.length === 0 && (
            <div className="text-center text-muted-foreground text-sm py-8 italic">
              {isRTL ? "לא נמצאו פריטים" : "No items found"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
