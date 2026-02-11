import { useMemo, useState } from "react";
import { BookIcon, SearchIcon } from "../icons";
import type { SourceItem } from "./types";

type SourceListPaneProps = {
  sources: SourceItem[];
  activeSourceId: string | null;
  onSelectSource: (sourceId: string) => void;
  onClose: () => void;
};

export function SourceListPane({ sources, activeSourceId, onSelectSource, onClose }: SourceListPaneProps) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return sources;
    return sources.filter((item) => {
      const text = `${item.title} ${item.preview} ${item.category}`.toLowerCase();
      return text.includes(normalized);
    });
  }, [query, sources]);

  return (
    <div className="source-list">
      <header className="source-list-header">
        <div className="source-list-title">Source List</div>
        <button type="button" className="ghost-button" onClick={onClose}>Close</button>
      </header>

      <div className="source-search">
        <SearchIcon width={14} height={14} />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search source placeholders"
        />
      </div>

      <div className="source-list-content" role="list">
        {filtered.length === 0 ? (
          <div className="source-empty">No matching sources.</div>
        ) : (
          filtered.map((source) => (
            <button
              key={source.id}
              type="button"
              className={`source-list-item ${source.id === activeSourceId ? "active" : ""}`}
              onClick={() => onSelectSource(source.id)}
            >
              <div className="source-list-item-head">
                <BookIcon width={14} height={14} />
                <span>{source.title}</span>
              </div>
              <p>{source.preview}</p>
              <small>{source.category}</small>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
