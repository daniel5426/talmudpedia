import * as React from "react";
import { Button } from "@/components/ui/button";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { libraryService, type LibrarySiblingsResponse, type LibraryNode } from "@/services/library";
import { useLayoutStore } from "@/lib/store/useLayoutStore";
import { cn } from "@/lib/utils";
import { useDirection } from "../direction-provider";
import { convertToHebrew } from "@/lib/hebrewUtils";
import { Folder } from "lucide-react";

interface SourceSiblingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentRef: string | null;
}

export function SourceSiblingsModal({ open, onOpenChange, currentRef }: SourceSiblingsModalProps) {
  const [data, setData] = React.useState<LibrarySiblingsResponse | null>(null);
  const [headerTitle, setHeaderTitle] = React.useState<string>("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const { direction } = useDirection();
  const setActiveSource = useLayoutStore((state) => state.setActiveSource);
  const setLibraryMode = useLayoutStore((state) => state.setLibraryMode);
  const setLibraryPathTitles = useLayoutStore((state) => state.setLibraryPathTitles);
  const previousDataRef = React.useRef<LibrarySiblingsResponse | null>(null);
  const itemRefs = React.useRef<Record<string, HTMLDivElement | null>>({});

  React.useEffect(() => {
    let cancelled = false;
    if (!open) {
      return;
    }
    if (!currentRef) {
      setError("No source selected");
      setData(null);
      return;
    }
    const previous = previousDataRef.current;
    if (previous && (previous.path_he?.length || previous.path?.length)) {
      const fallback = previous.path_he?.slice(-1)[0] || previous.path?.slice(-1)[0];
      if (fallback) {
        setHeaderTitle(fallback);
      }
    } else {
      setHeaderTitle(convertToHebrew(currentRef) || currentRef);
    }
    setLoading(true);
    setError(null);
    libraryService
      .getSiblings(currentRef)
      .then((res) => {
        if (!cancelled) {
          setData(res);
          previousDataRef.current = res;
          const fallback =
            res.path_he?.slice(-1)[0] ||
            res.path?.slice(-1)[0] ||
            res.parent?.heTitle ||
            res.parent?.title ||
            res.current_ref;
          if (fallback) {
            setHeaderTitle(fallback);
          }
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err?.message || "Failed to load siblings");
          setData(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, currentRef]);

  const parentTitle =
    data?.parent?.heTitle ||
    data?.parent?.title ||
    (data?.parent_path_he && data.parent_path_he.length > 0
      ? data.parent_path_he[data.parent_path_he.length - 1]
      : data?.parent_path && data.parent_path.length > 0
        ? data.parent_path[data.parent_path.length - 1]
        : null) ||
    (data?.path_he && data.path_he.length > 1 ? data.path_he[data.path_he.length - 2] : null) ||
    (data?.path && data.path.length > 1 ? data.path[data.path.length - 2] : null) ||
    "";

  const handleSelect = (item: Partial<LibraryNode>) => {
    if (!item.ref) return;
    setActiveSource(item.ref);
    onOpenChange(false);
  };

  const handleOpenSidebar = () => {
    if (!data) return;
    const path = data.parent_path && data.parent_path.length > 0 ? data.parent_path : data.path || [];
    setLibraryMode(true);
    setLibraryPathTitles(path);
    onOpenChange(false);
  };

  const isCurrent = (item: Partial<LibraryNode>) => {
    if (!data) return false;
    if (item.ref && item.ref === data.current_ref) return true;
    return false;
  };

  React.useEffect(() => {
    if (!open || !data || !data.siblings) return;
    const current = data.siblings.find((s) => s.ref === data.current_ref);
    const key = current?.ref || current?.slug || current?.title || "current";
    if (key && itemRefs.current[key]) {
      itemRefs.current[key]?.scrollIntoView({ block: "center" });
    }
  }, [open, data]);

  const itemKey = (item: Partial<LibraryNode>, idx: number) =>
    `${item.ref || item.slug || item.title || "sibling"}-${idx}`;

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      showCloseButton={false}
      className="w-auto max-w-fit sm:max-w-[80vw] p-0"
      commandProps={{ shouldFilter: false, className: "w-auto min-w-[280px] max-w-[80vw]" }}
    >
      <div className="flex items-center justify-between px-4 pt-4" dir={direction}>
        <div className="flex flex-col">
          <span className="text-xs text-muted-foreground">
            {"רשימת מקורות"}
          </span>
          <span className="text-base font-semibold">
            {headerTitle || parentTitle || data?.path_he?.slice(-1)[0] || data?.path?.slice(-1)[0] || currentRef || ""}
          </span>
        </div>
        <Button variant="outline" size="sm" onClick={handleOpenSidebar}>
          <Folder className="size-4" />
        </Button>
      </div>
      <div className="siblings-scroll-container max-h-[340px] min-h-[340px] overflow-y-scroll border-0" style={{ scrollbarWidth: 'thin', scrollbarColor: 'hsl(var(--border)) transparent' } as React.CSSProperties}>
        <style>{`
          .siblings-scroll-container {
            border: none !important;
          }
          .siblings-scroll-container::-webkit-scrollbar {
            display: block !important;
            width: 8px !important;
            background: transparent !important;
            border: none !important;
            -webkit-appearance: none !important;
            appearance: none !important;
          }
          .siblings-scroll-container::-webkit-scrollbar-track {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            -webkit-box-shadow: none !important;
            -webkit-border-radius: 0 !important;
            border-radius: 0 !important;
          }
          .siblings-scroll-container::-webkit-scrollbar-thumb {
            background-color: hsl(var(--border)) !important;
            border-radius: 4px !important;
            border: none !important;
            -webkit-box-shadow: none !important;
            box-shadow: none !important;
            outline: none !important;
          }
          .siblings-scroll-container::-webkit-scrollbar-thumb:hover {
            background-color: hsl(var(--muted-foreground) / 0.5) !important;
          }
          .siblings-scroll-container::-webkit-scrollbar-corner {
            background: transparent !important;
            border: none !important;
          }
        `}</style>
        <CommandList className="overflow-visible">
          <CommandEmpty className="flex items-center text-sm justify-center min-h-28">
            {loading ? <Shimmer className="text-sm">טוען...</Shimmer> : error ? error : "לא נמצאו פריטים"}
          </CommandEmpty>
          {loading ? (
            <CommandGroup>
              {Array.from({ length: 6 }).map((_, idx) => (
                <CommandItem key={`skeleton-${idx}`} disabled>
                  <div className="flex min-w-0 flex-1 flex-col gap-1">
                    <div className="h-4 w-40 rounded bg-muted animate-pulse" />
                    <div className="h-3 w-24 rounded bg-muted animate-pulse" />
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
          ) : data && data.siblings && data.siblings.length > 0 ? (
            <CommandGroup>
              {data.siblings.map((item, idx) => (
                <CommandItem
                  key={itemKey(item, idx)}
                  value={`${item.title || ""} ${item.heTitle || ""}`}
                  onSelect={() => handleSelect(item)}
                  className={cn(
                    "flex items-center gap-2",
                    isCurrent(item) ? "bg-primary/10 border border-primary/30" : ""
                  )}
                  ref={(el) => {
                    const key = itemKey(item, idx);
                    itemRefs.current[key] = el;
                  }}
                >
                  <div className="flex min-w-0 flex-col" dir={direction}>
                    <span className="truncate">{item.heTitle || item.title}</span>
                    {item.title && item.heTitle ? (
                      <span className="truncate text-xs text-muted-foreground">{item.title}</span>
                    ) : null}
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
          ) : null}
        </CommandList>
      </div>
    </CommandDialog>
  );
}
