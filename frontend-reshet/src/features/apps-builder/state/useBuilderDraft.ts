import type { BuilderPatchOp } from "@/services";

const normalizePath = (path: string): string => path.replace(/\\/g, "/").replace(/^\/+/, "");

export const applyBuilderPatchOperations = (
  files: Record<string, string>,
  entryFile: string,
  operations: BuilderPatchOp[],
): { files: Record<string, string>; entryFile: string } => {
  const nextFiles = { ...files };
  let nextEntryFile = entryFile;

  operations.forEach((operation) => {
    if (operation.op === "upsert_file") {
      const path = normalizePath(operation.path);
      nextFiles[path] = operation.content;
      return;
    }

    if (operation.op === "delete_file") {
      const path = normalizePath(operation.path);
      delete nextFiles[path];
      if (nextEntryFile === path) {
        nextEntryFile = "src/main.tsx";
      }
      return;
    }

    if (operation.op === "rename_file") {
      const fromPath = normalizePath(operation.from_path);
      const toPath = normalizePath(operation.to_path);
      if (nextFiles[fromPath] !== undefined) {
        nextFiles[toPath] = nextFiles[fromPath];
        delete nextFiles[fromPath];
        if (nextEntryFile === fromPath) {
          nextEntryFile = toPath;
        }
      }
      return;
    }

    if (operation.op === "set_entry_file") {
      nextEntryFile = normalizePath(operation.entry_file);
    }
  });

  if (!nextFiles[nextEntryFile]) {
    const fallback = Object.keys(nextFiles).sort()[0];
    if (fallback) {
      nextEntryFile = fallback;
    }
  }

  return {
    files: nextFiles,
    entryFile: nextEntryFile,
  };
};
