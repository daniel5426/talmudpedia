import type { UIBlocksRow } from "@agents24/ui-blocks-contract";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function spanClass(span: number): string {
  if (span === 12) return "md:col-span-12";
  if (span === 11) return "md:col-span-11";
  if (span === 10) return "md:col-span-10";
  if (span === 9) return "md:col-span-9";
  if (span === 8) return "md:col-span-8";
  if (span === 7) return "md:col-span-7";
  if (span === 6) return "md:col-span-6";
  if (span === 5) return "md:col-span-5";
  if (span === 4) return "md:col-span-4";
  if (span === 3) return "md:col-span-3";
  return "md:col-span-3";
}

export function normalizeRow(row: UIBlocksRow): UIBlocksRow {
  const blocks = row.blocks;
  const totalSpan = blocks.reduce((sum, block) => sum + block.span, 0);

  if (blocks.length === 1 && blocks[0]?.span !== 12) {
    return { blocks: blocks.map((block) => ({ ...block, span: 12 })) };
  }
  if (totalSpan >= 12) {
    return row;
  }
  if (blocks.length === 2) {
    return { blocks: blocks.map((block) => ({ ...block, span: 6 })) };
  }
  if (blocks.length === 3) {
    return { blocks: blocks.map((block) => ({ ...block, span: 4 })) };
  }
  if (blocks.length === 4) {
    return { blocks: blocks.map((block) => ({ ...block, span: 3 })) };
  }
  return row;
}
