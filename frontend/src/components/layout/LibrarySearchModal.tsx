import * as React from "react";
import { Button } from "@/components/ui/button";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { libraryService, normalizeLibraryQuery } from "@/services";
import type { LibrarySearchResult } from "@/services/library";
import { useLayoutStore } from "@/lib/store/useLayoutStore";

interface LibrarySearchModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function LibrarySearchModal({ open, onOpenChange }: LibrarySearchModalProps) {
  const [searchQuery, setSearchQuery] = React.useState("");
  const [searchResults, setSearchResults] = React.useState<LibrarySearchResult[]>([]);
  const [searchLoading, setSearchLoading] = React.useState(false);
  const [searchError, setSearchError] = React.useState<string | null>(null);
  const searchTimeout = React.useRef<NodeJS.Timeout | null>(null);

  const setLibraryMode = useLayoutStore((state) => state.setLibraryMode);
  const setLibraryPathTitles = useLayoutStore((state) => state.setLibraryPathTitles);
  const setActiveSource = useLayoutStore((state) => state.setActiveSource);

  React.useEffect(() => {
    if (searchTimeout.current) {
      clearTimeout(searchTimeout.current);
      searchTimeout.current = null;
    }
    if (!open) {
      setSearchLoading(false);
      return;
    }
    const normalized = normalizeLibraryQuery(searchQuery);
    if (!normalized) {
      setSearchResults([]);
      setSearchError(null);
      setSearchLoading(false);
      return;
    }
    let cancelled = false;
    searchTimeout.current = setTimeout(() => {
      setSearchLoading(true);
      setSearchError(null);
      libraryService
        .search(normalized)
        .then((data) => {
          if (!cancelled) {
            setSearchResults(data);
          }
        })
        .catch((err) => {
          if (!cancelled) {
            setSearchError(err.message || "Search failed");
            setSearchResults([]);
          }
        })
        .finally(() => {
          if (!cancelled) {
            setSearchLoading(false);
          }
        });
    }, 700);
    return () => {
      cancelled = true;
      setSearchLoading(false);
      if (searchTimeout.current) {
        clearTimeout(searchTimeout.current);
        searchTimeout.current = null;
      }
    };
  }, [open, searchQuery]);

  const handleOpenLibraryResult = React.useCallback(
    (item: LibrarySearchResult) => {
      if (item.path && item.path.length > 0) {
        setLibraryMode(true);
        setLibraryPathTitles(item.path);
        onOpenChange(false);
      }
    },
    [setLibraryMode, setLibraryPathTitles, onOpenChange]
  );

  const handleOpenSourceResult = React.useCallback(
    (item: LibrarySearchResult) => {
      if (!item.ref) return;
      setActiveSource(item.ref);
      setLibraryMode(false);
      onOpenChange(false);
    },
    [setActiveSource, setLibraryMode, onOpenChange]
  );

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} commandProps={{ shouldFilter: false }}>
      <CommandInput placeholder="Search library..." value={searchQuery} onValueChange={setSearchQuery} />
      <CommandList className="max-h-[320px] min-h-[320px]">
        <CommandEmpty className="flex items-center text-sm justify-center min-h-28">
          {searchLoading ? <Shimmer className="text-sm">מחפש...</Shimmer> : searchError ? searchError : "לא נמצאו תוצאות"}
        </CommandEmpty>
        {searchLoading ? (
          <CommandGroup heading="Results">
            {Array.from({ length: 6 }).map((_, idx) => (
              <CommandItem key={`skeleton-${idx}`} disabled>
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <div className="h-4 w-40 rounded bg-muted animate-pulse" />
                  <div className="h-3 w-56 rounded bg-muted animate-pulse" />
                </div>
                <div className="h-8 w-20 rounded bg-muted animate-pulse" />
              </CommandItem>
            ))}
          </CommandGroup>
        ) : searchResults.length > 0 ? (
          <CommandGroup heading="Results">
            {searchResults.map((item, idx) => (
                <CommandItem
                  key={`${item.ref || item.slug || item.title || "item"}-${idx}`}
                  value={`${item.title} ${item.heTitle ?? ""}`}
                  onSelect={() => {
                    if (item.path && item.path.length > 0) {
                      handleOpenLibraryResult(item);
                    } else if (item.ref) {
                      handleOpenSourceResult(item);
                    }
                  }}
                >
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate">{item.heTitle}</span>
                  
                  {item.path_he && item.path_he.length > 0 ? (
                    <span className="truncate text-xs text-muted-foreground">{item.path_he.join(" / ")}</span>
                  ) : item.path && item.path.length > 0 ? (
                    <span className="truncate text-xs text-muted-foreground">{item.path.join(" / ")}</span>
                  ) : null}
                </div>
                {item.ref ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleOpenSourceResult(item);
                    }}
                  >
                    Open source
                  </Button>
                ) : null}
                {item.path && item.path.length > 0 ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleOpenLibraryResult(item);
                    }}
                  >
                    Open path
                  </Button>
                ) : null}
              </CommandItem>
            ))}
          </CommandGroup>
        ) : null}
      </CommandList>
    </CommandDialog>
  );
}
