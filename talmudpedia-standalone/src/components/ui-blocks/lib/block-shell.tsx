import type { PropsWithChildren } from "react";

import type { UIBlock } from "@agents24/ui-blocks-contract";

import { cx, spanClass } from "./layout";
import { useWidgetTheme } from "./widget-theme";

export function BlockShell({
  block,
  children,
}: PropsWithChildren<{ block: UIBlock }>) {
  const theme = useWidgetTheme();

  return (
    <section
      className={cx(
        "col-span-1 overflow-hidden",
        theme.card,
        spanClass(block.span),
      )}
    >
      <div className="px-4 pt-4 pb-2">
        <div className={theme.title}>{block.title}</div>
        <div className={cx(theme.subtitle, !block.subtitle && "invisible")} aria-hidden={!block.subtitle}>
          {block.subtitle ?? "placeholder"}
        </div>
      </div>
      <div className="px-4 pb-4">{children}</div>
      {block.footnote ? (
        <div className={cx("px-4 py-2", theme.footnoteBorder, theme.footnote)}>
          {block.footnote}
        </div>
      ) : null}
    </section>
  );
}
