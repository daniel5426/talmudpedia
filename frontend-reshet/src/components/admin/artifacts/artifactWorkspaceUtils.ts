"use client"

import type { ArtifactLanguage, ArtifactSourceFile } from "@/services/artifacts"

export type TreeNode = {
  name: string
  path: string
  kind: "directory" | "file"
  children?: TreeNode[]
}

export const ARTIFACT_CONFIG_FILE_PATH = "__CONFIG__"
export const MIN_SIDEBAR_WIDTH = 160
export const MAX_SIDEBAR_WIDTH = 480
export const DEFAULT_SIDEBAR_WIDTH = 240

const DEFAULT_NEW_FILE_BASENAME = "module"

export function nextAvailablePath(sourceFiles: ArtifactSourceFile[], directory: string, language: ArtifactLanguage): string {
  const paths = new Set(sourceFiles.map((file) => file.path))
  const extension = language === "javascript" ? "js" : "py"
  let idx = 1
  while (true) {
    const candidate = directory
      ? `${directory}/${DEFAULT_NEW_FILE_BASENAME}_${idx}.${extension}`
      : `${DEFAULT_NEW_FILE_BASENAME}_${idx}.${extension}`
    if (!paths.has(candidate)) return candidate
    idx += 1
  }
}

export function nextAvailableDirPath(sourceFiles: ArtifactSourceFile[], parent: string): string {
  const dirNames = new Set<string>()
  const prefix = parent ? `${parent}/` : ""
  sourceFiles.forEach((file) => {
    if (!file.path.startsWith(prefix)) return
    const rest = file.path.slice(prefix.length)
    const firstSegment = rest.split("/")[0]
    if (rest.includes("/")) {
      dirNames.add(firstSegment)
    }
  })

  let idx = 1
  while (true) {
    const candidate = `folder_${idx}`
    if (!dirNames.has(candidate)) return candidate
    idx += 1
  }
}

export function buildTree(sourceFiles: ArtifactSourceFile[]): TreeNode[] {
  const root: TreeNode = { name: "__root__", path: "", kind: "directory", children: [] }

  const ensureDir = (parent: TreeNode, name: string, path: string): TreeNode => {
    const existing = parent.children?.find((child) => child.name === name && child.kind === "directory")
    if (existing) return existing
    const node: TreeNode = { name, path, kind: "directory", children: [] }
    parent.children?.push(node)
    return node
  }

  sourceFiles.forEach((file) => {
    const parts = file.path.split("/").filter(Boolean)
    let current = root
    parts.forEach((part, index) => {
      const isLeaf = index === parts.length - 1
      const fullPath = parts.slice(0, index + 1).join("/")
      if (isLeaf) {
        current.children?.push({ name: part, path: fullPath, kind: "file" })
        return
      }
      current = ensureDir(current, part, fullPath)
    })
  })

  const sortNodes = (nodes: TreeNode[]): TreeNode[] =>
    nodes
      .map((node) => (node.kind === "directory" ? { ...node, children: sortNodes(node.children || []) } : node))
      .sort((left, right) => {
        if (left.kind !== right.kind) {
          return left.kind === "directory" ? -1 : 1
        }
        return left.name.localeCompare(right.name)
      })

  return sortNodes(root.children || [])
}

export function collectDirectoryPaths(nodes: TreeNode[]): string[] {
  return nodes.flatMap((node) =>
    node.kind === "directory" ? [node.path, ...collectDirectoryPaths(node.children || [])] : [],
  )
}

export function moveFilePath(oldPath: string, newParent: string, fileName: string): string {
  return newParent ? `${newParent}/${fileName}` : fileName
}

export function editorLanguageForPath(path: string): "python" | "javascript" | "typescript" {
  const normalized = String(path || "").toLowerCase()
  if (normalized.endsWith(".ts") || normalized.endsWith(".mts")) return "typescript"
  if (normalized.endsWith(".js") || normalized.endsWith(".mjs")) return "javascript"
  return "python"
}

export function normalizeImportedPath(file: File): string {
  const rawPath = String((file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name || "").trim()
  return rawPath.replaceAll("\\", "/").replace(/^\/+/, "").split("/").filter(Boolean).join("/")
}

export function buildRenamedFilePath(path: string, nextFileName: string): string {
  const trimmedName = nextFileName.trim()
  if (!trimmedName) {
    throw new Error("File name cannot be empty")
  }
  if (trimmedName.includes("/")) {
    throw new Error("File name cannot contain '/'")
  }
  const segments = path.split("/")
  segments[segments.length - 1] = trimmedName
  return segments.join("/")
}
