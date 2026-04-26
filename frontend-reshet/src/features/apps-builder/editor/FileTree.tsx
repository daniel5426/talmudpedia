"use client";

import { useMemo } from "react";

import { PierreFileTree, type PierreFileTreeAction } from "@/components/file-tree/PierreFileTree";

export type TreeNode = DirectoryNode | FileNode;

export type DirectoryNode = {
  type: "directory";
  name: string;
  path: string;
  children: TreeNode[];
};

export type FileNode = {
  type: "file";
  name: string;
  path: string;
};

export const inferLanguage = (path: string): string => {
  const lowerPath = path.toLowerCase();

  if (lowerPath.endsWith(".tsx") || lowerPath.endsWith(".ts")) return "typescript";
  if (lowerPath.endsWith(".jsx") || lowerPath.endsWith(".js")) return "javascript";
  if (lowerPath.endsWith(".html") || lowerPath.endsWith(".htm")) return "html";
  if (lowerPath.endsWith(".css")) return "css";
  if (lowerPath.endsWith(".json")) return "json";
  if (lowerPath.endsWith(".md") || lowerPath.endsWith(".markdown")) return "markdown";
  if (lowerPath.endsWith(".yml") || lowerPath.endsWith(".yaml")) return "yaml";
  if (lowerPath.endsWith(".xml") || lowerPath.endsWith(".svg")) return "xml";
  return "plaintext";
};

type MutableDirectory = {
  name: string;
  path: string;
  directories: Map<string, MutableDirectory>;
  files: FileNode[];
};

const compareNames = (left: { name: string }, right: { name: string }): number =>
  left.name.localeCompare(right.name, undefined, { sensitivity: "base" });

const toDirectoryNode = (directory: MutableDirectory): DirectoryNode => {
  const nestedDirectories = Array.from(directory.directories.values())
    .sort(compareNames)
    .map(toDirectoryNode);
  const nestedFiles = [...directory.files].sort(compareNames);
  return {
    type: "directory",
    name: directory.name,
    path: directory.path,
    children: [...nestedDirectories, ...nestedFiles],
  };
};

export const buildFileTree = (paths: string[]): TreeNode[] => {
  const root: MutableDirectory = {
    name: "",
    path: "",
    directories: new Map(),
    files: [],
  };

  for (const path of paths) {
    const parts = path.split("/").filter(Boolean);
    if (parts.length === 0) {
      continue;
    }

    let cursor = root;
    for (let index = 0; index < parts.length - 1; index += 1) {
      const segment = parts[index];
      const segmentPath = cursor.path ? `${cursor.path}/${segment}` : segment;
      const existing = cursor.directories.get(segment);
      if (existing) {
        cursor = existing;
        continue;
      }
      const nextDirectory: MutableDirectory = {
        name: segment,
        path: segmentPath,
        directories: new Map(),
        files: [],
      };
      cursor.directories.set(segment, nextDirectory);
      cursor = nextDirectory;
    }

    const fileName = parts[parts.length - 1];
    cursor.files.push({
      type: "file",
      name: fileName,
      path,
    });
  }

  const rootDirectories = Array.from(root.directories.values()).sort(compareNames).map(toDirectoryNode);
  const rootFiles = [...root.files].sort(compareNames);
  return [...rootDirectories, ...rootFiles];
};

export const collectDirectoryPaths = (nodes: TreeNode[]): Set<string> => {
  const paths = new Set<string>();
  const walk = (node: TreeNode) => {
    if (node.type !== "directory") {
      return;
    }
    paths.add(node.path);
    node.children.forEach(walk);
  };

  nodes.forEach(walk);
  return paths;
};

export const ancestorDirectories = (filePath: string): string[] => {
  const parts = filePath.split("/").filter(Boolean);
  const ancestors: string[] = [];
  for (let index = 0; index < parts.length - 1; index += 1) {
    ancestors.push(parts.slice(0, index + 1).join("/"));
  }
  return ancestors;
};

type FileTreeProps = {
  files: Record<string, string>;
  selectedFile: string | null;
  onSelectFile: (path: string) => void;
  onDeleteFile: (path: string) => void;
  onCreateFile?: (path: string) => void;
  readOnly?: boolean;
};

export function FileTree({
  files,
  selectedFile,
  onSelectFile,
  onDeleteFile,
  onCreateFile,
  readOnly = false,
}: FileTreeProps) {
  const sortedPaths = useMemo(() => Object.keys(files).sort(), [files]);
  const activePath = selectedFile && files[selectedFile] !== undefined ? selectedFile : sortedPaths[0] || null;
  const actions = useMemo<PierreFileTreeAction[]>(() => {
    if (readOnly) return [];
    const nextAvailableFilePath = (directory: string): string => {
      const prefix = directory ? `${directory}/` : "";
      let index = 1;
      while (true) {
        const candidate = `${prefix}new-file-${index}.tsx`;
        if (files[candidate] === undefined) return candidate;
        index += 1;
      }
    };
    return [
      {
        label: "New file",
        icon: "new-file",
        onSelect: (path, item) => {
          if (!onCreateFile) return;
          const parent = item.kind === "directory" ? path : path.split("/").slice(0, -1).join("/");
          onCreateFile(nextAvailableFilePath(parent));
        },
      },
      {
        label: "Delete",
        icon: "delete",
        destructive: true,
        onSelect: onDeleteFile,
      },
    ];
  }, [files, onCreateFile, onDeleteFile, readOnly]);

  return (
    <div className="min-h-0 flex-1">
      <PierreFileTree
        paths={sortedPaths}
        selectedPath={activePath}
        initialExpansion="closed"
        readOnly={readOnly}
        onSelectPath={onSelectFile}
        actions={actions}
      />
    </div>
  );
}
