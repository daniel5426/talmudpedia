import type { MouseEventHandler } from "react";

export function SelectedTextCard({
  text,
  sourceRef,
  onRemove,
}: {
  text: string;
  sourceRef?: string;
  onRemove?: MouseEventHandler<HTMLButtonElement>;
}) {
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 10, padding: "8px 10px", fontSize: 12, background: "#fff" }}>
      <div style={{ fontWeight: 600 }}>{sourceRef || "Selected text"}</div>
      <div style={{ marginTop: 4, opacity: 0.85 }}>{text.slice(0, 120)}</div>
      <button type="button" onClick={onRemove} style={{ marginTop: 6 }}>Remove</button>
    </div>
  );
}
