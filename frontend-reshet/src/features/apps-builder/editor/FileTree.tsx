"use client";

import React, { useMemo, useState } from "react";
import { ChevronRight, FileCode2, Folder, FolderOpen, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

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

const fileIconColor = (name: string): string => {
  const lower = name.toLowerCase();
  if (lower.endsWith(".tsx") || lower.endsWith(".ts")) return "text-blue-500";
  if (lower.endsWith(".jsx") || lower.endsWith(".js")) return "text-yellow-500";
  if (lower.endsWith(".css")) return "text-purple-500";
  if (lower.endsWith(".html") || lower.endsWith(".htm")) return "text-orange-500";
  if (lower.endsWith(".json")) return "text-amber-400";
  return "text-muted-foreground";
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
};

export function FileTree({
  files,
  selectedFile,
  onSelectFile,
  onDeleteFile,
}: FileTreeProps) {
  const sortedPaths = useMemo(() => Object.keys(files).sort(), [files]);
  const treeNodes = useMemo(() => buildFileTree(sortedPaths), [sortedPaths]);
  const directoryPaths = useMemo(() => collectDirectoryPaths(treeNodes), [treeNodes]);
  const activePath = selectedFile && files[selectedFile] !== undefined ? selectedFile : sortedPaths[0] || null;

  // Track directories the user has explicitly expanded or collapsed.
  // `manualCollapsed` takes priority over auto-expansion of active-file ancestors.
  const [manualExpanded, setManualExpanded] = useState<Set<string>>(new Set());
  const [manualCollapsed, setManualCollapsed] = useState<Set<string>>(new Set());

  const expandedDirectories = useMemo(() => {
    const next = new Set<string>();
    // Auto-expand ancestors of the active file (unless user manually collapsed them)
    if (activePath) {
      ancestorDirectories(activePath).forEach((directoryPath) => {
        if (!manualCollapsed.has(directoryPath)) {
          next.add(directoryPath);
        }
      });
    }
    // Add all manually expanded directories (that still exist)
    manualExpanded.forEach((directoryPath) => {
      if (directoryPaths.has(directoryPath)) {
        next.add(directoryPath);
      }
    });
    return next;
  }, [activePath, directoryPaths, manualExpanded, manualCollapsed]);

  const toggleDirectory = (path: string) => {
    if (expandedDirectories.has(path)) {
      // Collapse: add to manualCollapsed, remove from manualExpanded
      setManualCollapsed((prev) => new Set(prev).add(path));
      setManualExpanded((prev) => {
        const next = new Set(prev);
        next.delete(path);
        return next;
      });
    } else {
      // Expand: add to manualExpanded, remove from manualCollapsed
      setManualExpanded((prev) => new Set(prev).add(path));
      setManualCollapsed((prev) => {
        const next = new Set(prev);
        next.delete(path);
        return next;
      });
    }
  };

  const renderTreeNode = (node: TreeNode, depth: number): React.JSX.Element => {
    if (node.type === "directory") {
      const isExpanded = expandedDirectories.has(node.path);
      return (
        <div key={node.path}>
          <button
            type="button"
            onClick={() => toggleDirectory(node.path)}
            className="flex w-full items-center gap-1.5 rounded-md py-1.5 pr-2 text-left text-xs transition-colors hover:bg-muted"
            style={{ paddingLeft: `${depth * 16 + 8}px` }}
          >
            <ChevronRight
              className={cn(
                "h-3 w-3 shrink-0 text-muted-foreground transition-transform duration-150",
                isExpanded && "rotate-90",
              )}
              aria-hidden="true"
            />
            {isExpanded ? (
              <FolderOpen className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            ) : (
              <Folder className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            )}
            <span className="truncate font-medium">{node.name}</span>
          </button>
          {isExpanded && (
            <div className="relative">
              <div
                className="absolute bottom-0 top-0 border-l border-border/40"
                style={{ left: `${depth * 16 + 16}px` }}
              />
              {node.children.map((child) => renderTreeNode(child, depth + 1))}
            </div>
          )}
        </div>
      );
    }

    const isActive = node.path === activePath;
    return (
      <div key={node.path} className="group flex items-center">
        <button
          type="button"
          onClick={() => onSelectFile(node.path)}
          className={cn(
            "flex min-w-0 flex-1 items-center gap-2 rounded-md py-1.5 pr-2 text-left text-xs transition-colors",
            isActive ? "bg-primary/10 text-primary font-medium" : "text-foreground/80 hover:bg-muted",
          )}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
        >
          <FileCode2 className={cn("h-3.5 w-3.5 shrink-0", isActive ? "text-primary" : fileIconColor(node.name))} />
          <span className="truncate">{node.name}</span>
        </button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
          onClick={() => onDeleteFile(node.path)}
        >
          <Trash2 className="h-3 w-3 text-muted-foreground hover:text-destructive" />
        </Button>
      </div>
    );
  };

  return (
    <ScrollArea className="min-h-0 flex-1">
      <div className="p-2">
        <div className="space-y-0.5">
          {treeNodes.length === 0 ? (
            <p className="px-2 py-4 text-center text-xs text-muted-foreground">No files yet.</p>
          ) : (
            treeNodes.map((node) => renderTreeNode(node, 0))
          )}
        </div>
      </div>
    </ScrollArea>
  );
}
