import type { UITableBlock } from "@agents24/ui-blocks-contract";

import { BlockShell } from "../lib/block-shell";
import { useWidgetTheme } from "../lib/widget-theme";

export function TableBlock({ block }: { block: UITableBlock }) {
  const theme = useWidgetTheme();

  return (
    <BlockShell block={block}>
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead>
            <tr>
              {block.columns.map((column) => (
                <th
                  key={column}
                  className={`px-2 py-2 ${theme.tableHeader} ${theme.tableHeaderBorder}`}
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
                    className={`px-2 py-2 ${theme.tableCell} ${theme.tableCellBorder}`}
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
