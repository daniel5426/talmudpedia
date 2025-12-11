"use client";

import * as React from "react";
import { ChevronLeft, ChevronRight, Book, Folder } from "lucide-react";
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
  const [tree, setTree] = React.useState<TreeNode[]>([]);
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
  const updateChildren = React.useCallback((nodes: TreeNode[], slug: string, children: TreeNode[]): TreeNode[] => {
    const apply = (list: TreeNode[]): TreeNode[] => {
      return list.map((node) => {
        if (node.slug === slug) {
          return { ...node, children };
        }
        if (node.children) {
          return { ...node, children: apply(node.children) };
        }
        return node;
      });
    };
    return apply(nodes);
  }, []);
  const loadChildren = React.useCallback(async (node: TreeNode) => {
    if (!node.hasChildren || node.children || !node.slug) {
      return node;
    }
    setLoadingSlug(node.slug);
    try {
      const children = await libraryService.getChildren(node.slug);
      setTree((prev) => updateChildren(prev, node.slug as string, children));
      setLoadingSlug(null);
      return { ...node, children };
    } catch {
      setError("Failed to load library menu");
      setLoadingSlug(null);
      return node;
    }
  }, [updateChildren]);
  React.useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await libraryService.getRoot();
        if (cancelled) {
          return;
        }
        setTree(data);
        setLoading(false);
        const savedTitles = initialLibraryPathTitles.current;
        if (savedTitles.length === 0) {
          return;
        }
        const newPath: TreeNode[] = [];
        let currentLevel = data;
        for (const title of savedTitles) {
          const node = currentLevel.find((n: TreeNode) => n.title === title);
          if (!node) {
            break;
          }
          let withChildren = node;
          if (node.hasChildren && !node.children && node.slug) {
            withChildren = await loadChildren(node);
          }
          newPath.push(withChildren);
          currentLevel = withChildren.children || [];
        }
        if (!cancelled) {
          setPath(newPath);
          setLibraryPathTitles(newPath.map((n) => n.title));
        }
      } catch {
        if (!cancelled) {
          setError("Failed to load library menu");
          setLoading(false);
        }
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [loadChildren, setLibraryPathTitles]);

  const currentLevel = path.length === 0 ? tree : path[path.length - 1].children || [];
  const currentTitle = path.length === 0 
    ? (isRTL ? "הספרייה" : "Library")
    : (isRTL && path[path.length - 1].heTitle ? path[path.length - 1].heTitle : path[path.length - 1].title);

  const handleNavigate = async (node: TreeNode) => {
    const hasChildren = (node.children && node.children.length > 0) || node.hasChildren;
    if (hasChildren) {
      let withChildren = node;
      if (node.hasChildren && !node.children && node.slug) {
        withChildren = await loadChildren(node);
      }
      const newPath = [...path, withChildren];
      setPath(newPath);
      setLibraryPathTitles(newPath.map(n => n.title));
      return;
    }
    if (node.ref) {
      setActiveSource(node.ref);
    }
  };

  const handleGoUp = () => {
    if (path.length > 0) {
      const newPath = path.slice(0, -1);
      setPath(newPath);
      setLibraryPathTitles(newPath.map(n => n.title));
    } else {
      onBack(); // Exit library mode if at root
    }
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
      </div>
      
      <div className="flex-1 overflow-y-auto">
        <div className="p-0 space-y-0" dir={direction}>
          {currentLevel.map((node, idx) => (
            <SidebarMenuButton
              key={node.slug ?? idx}
              className={cn(
                "w-full font-normal min-w-0",
                isRTL ? "justify-start text-right" : "justify-start text-left",
                isCollapsed ? "m-2" : "m-0"
              )}
              onClick={() => handleNavigate(node)}
              disabled={loadingSlug === node.slug}
              tooltip={(isRTL && node.heTitle) ? node.heTitle : node.title}
            >
              {node.type === "category" ? (
                <Folder className={cn("h-4 w-4 text-muted-foreground", isRTL ? "ml-1" : "mr-1")} />
              ) : (
                <Book className={cn(" h-4 w-4 text-muted-foreground", isRTL ? "ml-1" : "mr-1")} />
              )}
              <span
                dir={direction}
                className={cn("truncate flex-1", isRTL ? "text-right" : "text-left")}
              >
                {(isRTL && node.heTitle) ? node.heTitle : node.title}
              </span>
              {(node.hasChildren || (node.children && node.children.length > 0)) && (
                <ChevronRight className={cn(" h-4 w-4 opacity-50", isRTL ? "rotate-180 mr-auto" : "ml-auto")} />
              )}
            </SidebarMenuButton>
          ))}
          {currentLevel.length === 0 && (
            <div className="text-center text-muted-foreground text-sm py-4">
              No items found
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
