import type { SourceItem } from "./types";

type SourceViewerPaneProps = {
  source: SourceItem | null;
  onClose?: () => void;
};

export function SourceViewerPane({ source, onClose }: SourceViewerPaneProps) {
  if (!source) {
    return (
      <div className="source-viewer empty">
        <div className="source-viewer-empty">
          <h3>Select a source</h3>
          <p>Use this panel for citations, retrieved references, and supporting context.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="source-viewer">
      <header className="source-viewer-header">
        <div>
          <div className="source-viewer-category">{source.category}</div>
          <h3>{source.title}</h3>
        </div>
        {onClose ? (
          <button type="button" className="ghost-button" onClick={onClose}>
            Close
          </button>
        ) : null}
      </header>
      <article className="source-viewer-content">{source.content}</article>
    </div>
  );
}
