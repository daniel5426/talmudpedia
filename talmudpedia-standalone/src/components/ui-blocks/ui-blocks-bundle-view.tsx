import type { UIBlock, UIBlocksBundle } from "@agents24/ui-blocks-contract";
import { Fragment } from "react";

import { BarBlock } from "./blocks/bar-block";
import { CompareBlock } from "./blocks/compare-block";
import { KPIBlock } from "./blocks/kpi-block";
import { NoteBlock } from "./blocks/note-block";
import { PieBlock } from "./blocks/pie-block";
import { TableBlock } from "./blocks/table-block";
import { cx, normalizeRow } from "./lib/layout";
import { type WidgetTheme, WidgetThemeProvider, useWidgetTheme } from "./lib/widget-theme";

function renderBlock(block: UIBlock) {
  if (block.kind === "kpi") {
    return (
      <Fragment key={block.id}>
        <KPIBlock block={block} />
      </Fragment>
    );
  }
  if (block.kind === "pie") {
    return (
      <Fragment key={block.id}>
        <PieBlock block={block} />
      </Fragment>
    );
  }
  if (block.kind === "bar") {
    return (
      <Fragment key={block.id}>
        <BarBlock block={block} />
      </Fragment>
    );
  }
  if (block.kind === "compare") {
    return (
      <Fragment key={block.id}>
        <CompareBlock block={block} />
      </Fragment>
    );
  }
  if (block.kind === "table") {
    return (
      <Fragment key={block.id}>
        <TableBlock block={block} />
      </Fragment>
    );
  }
  if (block.kind === "note") {
    return (
      <Fragment key={block.id}>
        <NoteBlock block={block} />
      </Fragment>
    );
  }
  return null;
}

function BundleViewInner({
  bundle,
  className,
}: {
  bundle: UIBlocksBundle;
  className?: string;
}) {
  const theme = useWidgetTheme();
  const normalizedRows = bundle.rows.map(normalizeRow);

  return (
    <div className={cx("space-y-4", className)}>
      {bundle.title || bundle.subtitle ? (
        <div>
          <div className={cx(theme.bundleTitle, !bundle.title && "invisible")} aria-hidden={!bundle.title}>
            {bundle.title ?? "placeholder"}
          </div>
          <div className={cx(theme.bundleSubtitle, !bundle.subtitle && "invisible")} aria-hidden={!bundle.subtitle}>
            {bundle.subtitle ?? "placeholder"}
          </div>
        </div>
      ) : null}

      {normalizedRows.map((row, index) => (
        <div key={`row-${index}`} className="grid grid-cols-1 gap-4 md:grid-cols-12">
          {row.blocks.map((block) => renderBlock(block))}
        </div>
      ))}
    </div>
  );
}

export function UIBlocksBundleView({
  bundle,
  className,
  theme,
}: {
  bundle: UIBlocksBundle;
  className?: string;
  theme?: WidgetTheme;
}) {
  if (theme) {
    return (
      <WidgetThemeProvider value={theme}>
        <BundleViewInner bundle={bundle} className={className} />
      </WidgetThemeProvider>
    );
  }

  return <BundleViewInner bundle={bundle} className={className} />;
}
