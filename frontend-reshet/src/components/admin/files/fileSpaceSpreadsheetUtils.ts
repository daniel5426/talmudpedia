import Papa from "papaparse"

type DelimitedTextParseOptions = {
  path?: string
  mimeType?: string | null
}

export type DelimitedTextSheet = {
  delimiter: string
  rows: string[][]
  columnCount: number
  error: string | null
}

function resolvePreferredDelimiter({ path, mimeType }: DelimitedTextParseOptions): string | undefined {
  const normalizedPath = String(path || "").trim().toLowerCase()
  const normalizedMimeType = String(mimeType || "").trim().toLowerCase()

  if (normalizedPath.endsWith(".tsv") || normalizedMimeType.includes("tab-separated-values")) {
    return "\t"
  }

  return undefined
}

function normalizeRows(rows: unknown[]): string[][] {
  return rows.map((row) => {
    if (!Array.isArray(row)) return [String(row ?? "")]
    return row.map((cell) => String(cell ?? ""))
  })
}

export function parseDelimitedTextSheet(
  content: string,
  options: DelimitedTextParseOptions = {},
): DelimitedTextSheet {
  const preferredDelimiter = resolvePreferredDelimiter(options)
  const result = Papa.parse<string[]>(content, {
    delimiter: preferredDelimiter ?? "",
    skipEmptyLines: false,
  })

  const rows = normalizeRows(result.data as unknown[])
  const columnCount = rows.reduce((max, row) => Math.max(max, row.length), 0)
  const firstError = result.errors.find((error) => error.code !== "UndetectableDelimiter")

  return {
    delimiter: result.meta.delimiter || preferredDelimiter || ",",
    rows,
    columnCount,
    error: firstError?.message || null,
  }
}

export function serializeDelimitedTextSheet(rows: string[][], delimiter: string): string {
  return Papa.unparse(rows, {
    delimiter,
    newline: "\n",
  })
}

export function updateDelimitedTextCell(
  content: string,
  rowIndex: number,
  columnIndex: number,
  nextValue: string,
  options: DelimitedTextParseOptions = {},
): string {
  const sheet = parseDelimitedTextSheet(content, options)
  const nextRows = sheet.rows.map((row) => [...row])

  while (nextRows.length <= rowIndex) {
    nextRows.push([])
  }

  while ((nextRows[rowIndex]?.length ?? 0) <= columnIndex) {
    nextRows[rowIndex].push("")
  }

  nextRows[rowIndex][columnIndex] = nextValue
  return serializeDelimitedTextSheet(nextRows, sheet.delimiter)
}

export function getSpreadsheetColumnLabel(index: number): string {
  let current = index
  let label = ""

  do {
    label = String.fromCharCode(65 + (current % 26)) + label
    current = Math.floor(current / 26) - 1
  } while (current >= 0)

  return label
}
