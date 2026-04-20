"use client";

import { useMemo } from "react";

import { Textarea } from "@/components/ui/textarea";

import {
  getSpreadsheetColumnLabel,
  parseDelimitedTextSheet,
  updateDelimitedTextCell,
} from "./fileSpaceSpreadsheetUtils";

type FileSpaceDelimitedTextEditorProps = {
  path: string;
  mimeType: string | null;
  value: string;
  mode: "grid" | "raw";
  onChange: (nextValue: string) => void;
};

export function FileSpaceDelimitedTextEditor({
  path,
  mimeType,
  value,
  mode,
  onChange,
}: FileSpaceDelimitedTextEditorProps) {
  const sheet = useMemo(
    () => parseDelimitedTextSheet(value, { path, mimeType }),
    [mimeType, path, value],
  );
  const rowCount = Math.max(sheet.rows.length, 1);
  const columnCount = Math.max(sheet.columnCount, 1);

  if (mode === "raw") {
    return (
      <div className="relative flex h-full w-full flex-col">
        <div className="relative flex-1 min-h-0">
          <Textarea
            value={value}
            onChange={(event) => onChange(event.target.value)}
            className="absolute inset-0 h-full w-full resize-none rounded-none border-0 bg-transparent px-5 py-4 font-mono text-sm leading-relaxed focus-visible:ring-0 focus-visible:ring-offset-0"
            spellCheck={false}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <div className="flex-1 min-h-0 overflow-auto px-5 py-4">
        {sheet.error ? (
          <div className="mb-3 rounded-lg border border-amber-500/20 bg-amber-500/8 px-3 py-2 text-xs text-amber-700">
            Parse warning: {sheet.error}
          </div>
        ) : null}
        <div className="min-w-max overflow-hidden  border bg-background">
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-muted/80 backdrop-blur">
              <tr>
                <th className="w-14 border-b border-r bg-muted px-3 py-2 text-left text-xs font-semibold text-muted-foreground">
                  #
                </th>
                {Array.from({ length: columnCount }).map((_, columnIndex) => (
                  <th
                    key={`column-${columnIndex}`}
                    className="min-w-40 border-b border-r px-3 py-2 text-left text-xs font-semibold text-muted-foreground last:border-r-0"
                  >
                    {getSpreadsheetColumnLabel(columnIndex)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: rowCount }).map((_, rowIndex) => (
                <tr key={`row-${rowIndex}`} className="align-top">
                  <td className="border-b border-r bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                    {rowIndex + 1}
                  </td>
                  {Array.from({ length: columnCount }).map(
                    (__, columnIndex) => (
                      <td
                        key={`cell-${rowIndex}-${columnIndex}`}
                        className="border-b border-r p-0 last:border-r-0"
                      >
                        <input
                          aria-label={`Cell ${getSpreadsheetColumnLabel(columnIndex)}${rowIndex + 1}`}
                          value={sheet.rows[rowIndex]?.[columnIndex] ?? ""}
                          onChange={(event) =>
                            onChange(
                              updateDelimitedTextCell(
                                value,
                                rowIndex,
                                columnIndex,
                                event.target.value,
                                {
                                  path,
                                  mimeType,
                                },
                              ),
                            )
                          }
                          className="h-11 w-full min-w-40 bg-transparent px-3 py-2 outline-none transition-colors focus:bg-accent/30"
                        />
                      </td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
