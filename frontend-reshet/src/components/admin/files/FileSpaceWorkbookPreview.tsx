"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";

import { getSpreadsheetColumnLabel } from "./fileSpaceSpreadsheetUtils";

type WorkbookSheet = {
  name: string;
  rows: string[][];
};

type WorkbookState =
  | { status: "loading"; sheets: []; error: null }
  | { status: "ready"; sheets: WorkbookSheet[]; error: null }
  | { status: "error"; sheets: []; error: string };

type FileSpaceWorkbookPreviewProps = {
  file: Blob;
};

export function FileSpaceWorkbookPreview({
  file,
}: FileSpaceWorkbookPreviewProps) {
  const [state, setState] = useState<WorkbookState>({
    status: "loading",
    sheets: [],
    error: null,
  });
  const [activeSheetName, setActiveSheetName] = useState<string>("");

  useEffect(() => {
    let disposed = false;

    const loadWorkbook = async () => {
      setState({ status: "loading", sheets: [], error: null });

      try {
        const XLSX = await import("xlsx");
        const buffer = await file.arrayBuffer();
        if (disposed) return;

        const workbook = XLSX.read(buffer, { type: "array" });
        const sheets = workbook.SheetNames.map((sheetName) => ({
          name: sheetName,
          rows: (
            XLSX.utils.sheet_to_json(workbook.Sheets[sheetName], {
              header: 1,
              raw: false,
              defval: "",
              blankrows: true,
            }) as unknown[][]
          ).map((row) =>
            Array.isArray(row) ? row.map((cell) => String(cell ?? "")) : [],
          ),
        }));

        if (disposed) return;
        setState({ status: "ready", sheets, error: null });
        setActiveSheetName((current) => current || sheets[0]?.name || "");
      } catch (error) {
        if (disposed) return;
        console.error(error);
        setState({
          status: "error",
          sheets: [],
          error: "Failed to parse workbook preview.",
        });
      }
    };

    void loadWorkbook();

    return () => {
      disposed = true;
    };
  }, [file]);

  const activeSheet = useMemo(
    () =>
      state.sheets.find((sheet) => sheet.name === activeSheetName) ||
      state.sheets[0] ||
      null,
    [activeSheetName, state.sheets],
  );
  const columnCount = Math.max(
    activeSheet?.rows.reduce((max, row) => Math.max(max, row.length), 0) ?? 0,
    1,
  );
  const rowCount = Math.max(activeSheet?.rows.length ?? 0, 1);

  if (state.status === "loading") {
    return (
      <div className="flex h-full min-h-[18rem] items-center justify-center text-sm text-muted-foreground">
        Loading workbook preview...
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="flex h-full min-h-[18rem] items-center justify-center text-sm text-destructive">
        {state.error}
      </div>
    );
  }

  if (!activeSheet) {
    return (
      <div className="flex h-full min-h-[18rem] items-center justify-center text-sm text-muted-foreground">
        Workbook is empty.
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <div className="px-5 py-3">
        <div className="flex flex-wrap gap-1.5">
          {state.sheets.map((sheet) => (
            <Button
              key={sheet.name}
              type="button"
              size="sm"
              variant="ghost"
              className={`h-8 rounded-full px-3 text-xs ${
                sheet.name === activeSheet.name
                  ? "bg-foreground text-background hover:bg-foreground/90 hover:text-background"
                  : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
              }`}
              onClick={() => setActiveSheetName(sheet.name)}
            >
              {sheet.name}
            </Button>
          ))}
        </div>
      </div>
      <div className="flex-1 min-h-0 overflow-auto px-5 py-4">
        <div className="min-w-max overflow-hidden border bg-background">
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
                <tr key={`row-${rowIndex}`}>
                  <td className="border-b border-r bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                    {rowIndex + 1}
                  </td>
                  {Array.from({ length: columnCount }).map(
                    (__, columnIndex) => (
                      <td
                        key={`cell-${rowIndex}-${columnIndex}`}
                        className="min-w-40 border-b border-r px-3 py-2 align-top text-foreground last:border-r-0"
                      >
                        {activeSheet.rows[rowIndex]?.[columnIndex] ?? ""}
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
