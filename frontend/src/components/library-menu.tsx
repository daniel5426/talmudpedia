"use client";

import * as React from "react";
import { ChevronLeft, ChevronRight, Book, Folder } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SidebarMenuButton, useSidebar } from "@/components/ui/sidebar";
import { Skeleton } from "@/components/ui/skeleton";
import { useDirection } from "./direction-provider";
import { cn } from "@/lib/utils";
import { useLayoutStore } from "@/lib/store/useLayoutStore";

interface TreeNode {
  title: string;
  heTitle?: string;
  type: "category" | "book" | "text";
  children?: TreeNode[];
  ref?: string;
}

interface LibraryMenuProps {
  onBack: () => void; // To exit library mode
}

export function LibraryMenu({ onBack }: LibraryMenuProps) {
  const [tree, setTree] = React.useState<TreeNode[]>([]);
  const [path, setPath] = React.useState<TreeNode[]>([]);
  const { libraryPathTitles, setLibraryPathTitles, setActiveSource } = useLayoutStore();
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const { direction } = useDirection();
  const isRTL = direction === "rtl";
  const { state } = useSidebar()
  const isCollapsed = state === "collapsed";
  React.useEffect(() => {
    // In dev, we might need full URL. In prod, relative /api/library/menu
    fetch("http://localhost:8000/api/library/menu")
      .then(async (res) => {
        if (!res.ok) throw new Error("Failed to load library");
        return res.json();
      })
      .then((data) => {
        setTree(data);
        setLoading(false);
        
        // Reconstruct path from persisted titles
        if (libraryPathTitles.length > 0) {
          const newPath: TreeNode[] = [];
          let currentLevel = data;
          
          for (const title of libraryPathTitles) {
            const node = currentLevel.find((n: TreeNode) => n.title === title);
            if (node) {
              newPath.push(node);
              currentLevel = node.children || [];
            } else {
              break; // Path mismatch, stop reconstruction
            }
          }
          setPath(newPath);
        }
      })
      .catch((err) => {
        console.error(err);
        setError("Failed to load library menu");
        setLoading(false);
      });
  }, []);

  const currentLevel = path.length === 0 ? tree : path[path.length - 1].children || [];
  const currentTitle = path.length === 0 
    ? (isRTL ? "הספרייה" : "Library")
    : (isRTL && path[path.length - 1].heTitle ? path[path.length - 1].heTitle : path[path.length - 1].title);

  const handleNavigate = (node: TreeNode) => {
    if (node.children && node.children.length > 0) {
      const newPath = [...path, node];
      setPath(newPath);
      setLibraryPathTitles(newPath.map(n => n.title));
    } else {
      console.log("Open text:", node);
      if (node.ref) {
        setActiveSource(node.ref);
      }
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
              key={idx}
              className={cn(
                "w-full font-normal min-w-0",
                isRTL ? "justify-start text-right" : "justify-start text-left",
                isCollapsed ? "m-2" : "m-0"
              )}
              onClick={() => handleNavigate(node)}
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
              {node.children && node.children.length > 0 && (
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
