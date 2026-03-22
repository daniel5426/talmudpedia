"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import CodeMirror from "@uiw/react-codemirror"
import { json } from "@codemirror/lang-json"
import { syntaxHighlighting, defaultHighlightStyle } from "@codemirror/language"
import { RangeSetBuilder, type Extension } from "@codemirror/state"
import { Decoration, EditorView, ViewPlugin, WidgetType, type ViewUpdate } from "@codemirror/view"
import { oneDark } from "@codemirror/theme-one-dark"
import { BookOpen } from "lucide-react"
import { useTheme } from "next-themes"
import { cn } from "@/lib/utils"
import { promptsService, type PromptMentionRecord } from "@/services/prompts"
import { extractPromptIds } from "@/lib/prompt-mentions"
import {
  escapeForJsonStringContent,
  findPromptTokensInDescriptionValues,
  getJsonPromptQueryAtPosition,
  replaceJsonTextRange,
} from "@/lib/prompt-mention-json"

interface PromptMentionJsonEditorProps {
  id?: string
  ariaLabel?: string
  value: string
  onChange: (value: string) => void
  surface?: string
  height?: string
  className?: string
  onMentionClick?: (promptId: string, tokenRange: { from: number; to: number }) => void
}

class PromptTokenWidget extends WidgetType {
  constructor(
    private readonly promptId: string,
    private readonly promptName: string,
    private readonly from: number,
    private readonly to: number,
    private readonly onClick?: (promptId: string, tokenRange: { from: number; to: number }) => void
  ) {
    super()
  }

  eq(other: PromptTokenWidget) {
    return (
      this.promptId === other.promptId &&
      this.promptName === other.promptName &&
      this.from === other.from &&
      this.to === other.to
    )
  }

  toDOM() {
    const pill = document.createElement("span")
    pill.className =
      "inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 text-[11px] font-medium cursor-pointer"
    pill.textContent = `@${this.promptName}`
    pill.onclick = (event) => {
      event.preventDefault()
      event.stopPropagation()
      this.onClick?.(this.promptId, { from: this.from, to: this.to })
    }
    return pill
  }

  ignoreEvent() {
    return false
  }
}

function createPromptMentionDecorations(
  view: EditorView,
  nameMap: Record<string, string>,
  onMentionClick?: (promptId: string, tokenRange: { from: number; to: number }) => void
) {
  const builder = new RangeSetBuilder<Decoration>()
  const tokens = findPromptTokensInDescriptionValues(view.state.doc.toString(), nameMap)
  for (const token of tokens) {
    builder.add(
      token.from,
      token.to,
      Decoration.replace({
        widget: new PromptTokenWidget(token.promptId, token.name, token.from, token.to, onMentionClick),
      })
    )
  }
  return builder.finish()
}

export function PromptMentionJsonEditor({
  id,
  ariaLabel,
  value,
  onChange,
  surface,
  height = "200px",
  className,
  onMentionClick,
}: PromptMentionJsonEditorProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const { resolvedTheme } = useTheme()
  const viewRef = useRef<EditorView | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const [nameMap, setNameMap] = useState<Record<string, string>>({})
  const [showMentionMenu, setShowMentionMenu] = useState(false)
  const [mentionQuery, setMentionQuery] = useState("")
  const [mentionResults, setMentionResults] = useState<PromptMentionRecord[]>([])
  const [mentionLoading, setMentionLoading] = useState(false)
  const [selectedMentionIdx, setSelectedMentionIdx] = useState(0)
  const [menuPosition, setMenuPosition] = useState<{ top: number; left: number }>({ top: 0, left: 0 })
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const replaceRangeRef = useRef<{ from: number; to: number } | null>(null)
  const anchorRectRef = useRef<DOMRect | null>(null)

  useEffect(() => {
    const ids = extractPromptIds(value)
    const missing = ids.filter((id) => !nameMap[id])
    if (missing.length === 0) return
    Promise.all(
      missing.map((id) =>
        promptsService
          .getPrompt(id)
          .then((prompt) => [id, prompt.name] as const)
          .catch(() => [id, "Unknown Prompt"] as const)
      )
    ).then((entries) => {
      setNameMap((current) => {
        const next = { ...current }
        for (const [id, name] of entries) {
          next[id] = name
        }
        return next
      })
    })
  }, [nameMap, value])

  useEffect(() => {
    if (!showMentionMenu) return
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current)
    }
    searchTimeoutRef.current = setTimeout(async () => {
      setMentionLoading(true)
      try {
        const results = await promptsService.searchMentions({
          q: mentionQuery || undefined,
          surface: surface || undefined,
          limit: 10,
        })
        setMentionResults(results)
        setSelectedMentionIdx(0)
      } catch {
        setMentionResults([])
      } finally {
        setMentionLoading(false)
      }
    }, 150)
    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current)
      }
    }
  }, [mentionQuery, showMentionMenu, surface])

  const mentionExtension = useMemo(() => {
    return ViewPlugin.fromClass(
      class {
        decorations
        constructor(view: EditorView) {
          this.decorations = createPromptMentionDecorations(view, nameMap, onMentionClick)
        }
        update(update: ViewUpdate) {
          if (update.docChanged || update.viewportChanged) {
            this.decorations = createPromptMentionDecorations(update.view, nameMap, onMentionClick)
          }
        }
      },
      {
        decorations: (
          plugin: { decorations: ReturnType<typeof createPromptMentionDecorations> }
        ) => plugin.decorations,
      }
    )
  }, [nameMap, onMentionClick])

  const handleMentionSelection = useCallback(
    (mention: PromptMentionRecord) => {
      const view = viewRef.current
      const replaceRange = replaceRangeRef.current
      if (!view || !replaceRange) return
      setNameMap((current) => ({ ...current, [mention.id]: mention.name }))
      const nextValue = replaceJsonTextRange(
        view.state.doc.toString(),
        replaceRange.from,
        replaceRange.to,
        `[[prompt:${mention.id}]]`
      )
      onChange(nextValue)
      setShowMentionMenu(false)
      replaceRangeRef.current = null
    },
    [onChange]
  )

  const handleUpdate = useCallback(
    (update: ViewUpdate) => {
      if (!update.selectionSet && !update.docChanged) return
      const view = update.view
      const position = view.state.selection.main.head
      const query = getJsonPromptQueryAtPosition(view.state.doc.toString(), position)
      if (!query) {
        setShowMentionMenu(false)
        replaceRangeRef.current = null
        return
      }
      replaceRangeRef.current = { from: query.replaceFrom, to: query.replaceTo }
      setMentionQuery(query.query)
      setShowMentionMenu(true)
      const coords = view.coordsAtPos(position)
      if (coords) {
        const rect = new DOMRect(coords.left, coords.top, Math.max(1, coords.right - coords.left), Math.max(1, coords.bottom - coords.top))
        anchorRectRef.current = rect
        const menu = menuRef.current
        const root = rootRef.current
        setMenuPosition(menu && root ? positionMenu(rect, menu, root) : { top: 0, left: 0 })
      }
    },
    []
  )

  useEffect(() => {
    if (!showMentionMenu || !anchorRectRef.current || !menuRef.current) return
    const root = rootRef.current
    if (!root) return
    setMenuPosition(positionMenu(anchorRectRef.current, menuRef.current, root))
  }, [showMentionMenu, mentionResults, mentionLoading])

  useEffect(() => {
    if (!showMentionMenu) return
    const reposition = () => {
      const rect = anchorRectRef.current
      const menu = menuRef.current
      const root = rootRef.current
      if (!rect || !menu || !root) return
      setMenuPosition(positionMenu(rect, menu, root))
    }
    window.addEventListener("resize", reposition)
    window.addEventListener("scroll", reposition, true)
    return () => {
      window.removeEventListener("resize", reposition)
      window.removeEventListener("scroll", reposition, true)
    }
  }, [showMentionMenu])

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!showMentionMenu || mentionResults.length === 0) return false
      if (event.key === "ArrowDown") {
        event.preventDefault()
        setSelectedMentionIdx((current) => (current + 1) % mentionResults.length)
        return true
      }
      if (event.key === "ArrowUp") {
        event.preventDefault()
        setSelectedMentionIdx((current) => (current - 1 + mentionResults.length) % mentionResults.length)
        return true
      }
      if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault()
        const selected = mentionResults[selectedMentionIdx]
        if (selected) {
          handleMentionSelection(selected)
        }
        return true
      }
      if (event.key === "Escape") {
        event.preventDefault()
        setShowMentionMenu(false)
        return true
      }
      return false
    },
    [handleMentionSelection, mentionResults, selectedMentionIdx, showMentionMenu]
  )

  const extensions = useMemo<Extension[]>(
    () => [
      json(),
      syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
      mentionExtension,
      EditorView.domEventHandlers({
        keydown: (event: KeyboardEvent) => handleKeyDown(event),
        blur: () => {
          setTimeout(() => setShowMentionMenu(false), 200)
          return false
        },
      }),
    ],
    [handleKeyDown, mentionExtension]
  )

  return (
    <div ref={rootRef} className="relative">
      <div className={cn("rounded-md border border-input overflow-hidden", className)}>
        <CodeMirror
          id={id}
          aria-label={ariaLabel}
          value={value}
          height={height}
          theme={resolvedTheme === "dark" ? oneDark : "light"}
          extensions={extensions}
          onChange={(nextValue) => onChange(nextValue)}
          onUpdate={handleUpdate}
          onCreateEditor={(view) => {
            viewRef.current = view
          }}
          basicSetup={{
            lineNumbers: true,
            foldGutter: true,
            dropCursor: true,
            allowMultipleSelections: false,
            indentOnInput: true,
          }}
          className="text-xs"
        />
      </div>

      {showMentionMenu ? (
        <div
          ref={menuRef}
          className="absolute z-[120] bg-popover text-popover-foreground shadow-lg rounded-lg border border-border p-1 max-h-[240px] overflow-auto min-w-[240px]"
          style={{ top: menuPosition.top, left: menuPosition.left }}
        >
          {mentionLoading ? (
            <div className="px-2 py-2 text-xs text-muted-foreground">Loading prompts...</div>
          ) : null}
          {!mentionLoading && mentionResults.length === 0 ? (
            <div className="px-2 py-2 text-xs text-muted-foreground">No prompts found.</div>
          ) : null}
          {!mentionLoading ? mentionResults.map((result, idx) => (
            <div
              key={result.id}
              className={cn(
                "flex items-center gap-2 px-2 py-1.5 text-xs rounded-md cursor-pointer",
                idx === selectedMentionIdx ? "bg-accent text-accent-foreground" : "hover:bg-muted"
              )}
              onMouseDown={(event) => {
                event.preventDefault()
                handleMentionSelection(result)
              }}
            >
              <BookOpen className="h-3.5 w-3.5 text-blue-500 shrink-0" />
              <div className="flex flex-col min-w-0">
                <span className="font-medium truncate">{result.name}</span>
                {result.description ? (
                  <span className="text-[10px] text-muted-foreground truncate">{result.description}</span>
                ) : null}
              </div>
              <span className="ml-auto text-[10px] text-muted-foreground/60 shrink-0">{result.scope}</span>
            </div>
          )) : null}
        </div>
      ) : null}
    </div>
  )
}

export function fillPromptMentionJsonToken(value: string, tokenRange: { from: number; to: number }, fillText: string) {
  return replaceJsonTextRange(value, tokenRange.from, tokenRange.to, escapeForJsonStringContent(fillText))
}

function positionMenu(anchorRect: DOMRect, menu: HTMLDivElement, root: HTMLDivElement) {
  const gap = 8
  const viewportPadding = 8
  const rootRect = root.getBoundingClientRect()
  const menuRect = menu.getBoundingClientRect()
  const menuWidth = menuRect.width || 240
  const menuHeight = menuRect.height || 120
  const anchorTop = anchorRect.top - rootRect.top
  const anchorBottom = anchorRect.bottom - rootRect.top
  const anchorLeft = anchorRect.left - rootRect.left
  const availableHeight = Math.max(rootRect.height, window.innerHeight - rootRect.top)
  const preferredTop = anchorTop - menuHeight - gap
  const fallbackTop = anchorBottom + gap
  const top = preferredTop >= viewportPadding
    ? preferredTop
    : Math.min(fallbackTop, availableHeight - menuHeight - viewportPadding)
  const left = Math.min(
    Math.max(viewportPadding, anchorLeft),
    Math.max(viewportPadding, rootRect.width - menuWidth - viewportPadding)
  )
  return { top, left }
}
