import type { PropsWithChildren } from "react";

import type { UIBlock } from "@agents24/ui-blocks-contract";

import { cx, spanClass } from "./layout";
import { useWidgetDensity } from "./widget-density";
import { useWidgetTheme } from "./widget-theme";

export function BlockShell({
  block,
  children,
}: PropsWithChildren<{ block: UIBlock }>) {
  const theme = useWidgetTheme();
  const density = useWidgetDensity();
  const mobileSpanClass =
    density.id === "compact"
      ? block.kind === "kpi"
        ? "col-span-1"
        : "col-span-2"
      : "col-span-1";

  return (
    <section
      className={cx(
        mobileSpanClass,
        "overflow-hidden",
        theme.card,
        spanClass(block.span),
      )}
    >
      <div className={density.shellHeaderPadding}>
        <div className={cx(theme.title, density.blockTitle)}>{block.title}</div>
        <div className={cx(theme.subtitle, density.blockSubtitle, !block.subtitle && "invisible")} aria-hidden={!block.subtitle}>
          {block.subtitle ?? "placeholder"}
        </div>
      </div>
      <div className={density.shellBodyPadding}>{children}</div>
      {block.footnote ? (
        <div className={cx(density.shellFootnotePadding, theme.footnoteBorder, theme.footnote, density.footnote)}>
          {block.footnote}
        </div>
      ) : null}
    </section>
  );
}
