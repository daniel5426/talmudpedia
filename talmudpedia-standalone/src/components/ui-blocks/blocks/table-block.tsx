import type { UITableBlock } from "@agents24/ui-blocks-contract";

import { BlockShell } from "../lib/block-shell";
import { cx } from "../lib/layout";
import { useWidgetDensity } from "../lib/widget-density";
import { useWidgetTheme } from "../lib/widget-theme";

export function TableBlock({ block }: { block: UITableBlock }) {
  const theme = useWidgetTheme();
  const density = useWidgetDensity();

  return (
    <BlockShell block={block}>
      <div className="overflow-x-auto">
        <table className={cx("min-w-full border-collapse", density.tableText)}>
          <thead>
            <tr>
              {block.columns.map((column) => (
                <th
                  key={column}
                  className={cx(density.tableCellPadding, theme.tableHeader, theme.tableHeaderBorder)}
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, rowIndex) => (
              <tr key={`${block.id}-${rowIndex}`}>
                {row.map((cell, cellIndex) => (
                  <td
                    key={`${block.id}-${rowIndex}-${cellIndex}`}
                    className={cx(density.tableCellPadding, theme.tableCell, theme.tableCellBorder)}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </BlockShell>
  );
}
