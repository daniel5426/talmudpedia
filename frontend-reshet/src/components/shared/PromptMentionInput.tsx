"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { cn } from "@/lib/utils"
import { promptsService } from "@/services/prompts"
import type { PromptMentionRecord } from "@/services/prompts"
import {
  extractPromptIds,
  parseToSegments,
  serializeSegments,
  fillMention,
  type MentionSegment,
} from "@/lib/prompt-mentions"
import { BookOpen } from "lucide-react"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PromptMentionInputProps {
  value: string
  onChange: (value: string) => void
  surface?: string
  placeholder?: string
  className?: string
  multiline?: boolean
  onMentionClick?: (promptId: string, mentionIndex: number) => void
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PromptMentionInput({
  value,
  onChange,
  surface,
  placeholder,
  className,
  multiline = true,
  onMentionClick,
}: PromptMentionInputProps) {
  const editorRef = useRef<HTMLDivElement>(null)
  const [nameMap, setNameMap] = useState<Record<string, string>>({})
  const [showMentionMenu, setShowMentionMenu] = useState(false)
  const [mentionQuery, setMentionQuery] = useState("")
  const [mentionResults, setMentionResults] = useState<PromptMentionRecord[]>([])
  const [selectedMentionIdx, setSelectedMentionIdx] = useState(0)
  const [menuPosition, setMenuPosition] = useState<{ top: number; left: number }>({ top: 0, left: 0 })
  const [isFocused, setIsFocused] = useState(false)
  const mentionSearchTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const isComposingRef = useRef(false)
  const suppressInputRef = useRef(false)

  // Hydrate name map for any prompt IDs in the persisted value
  useEffect(() => {
    const ids = extractPromptIds(value)
    if (ids.length === 0) return
    const missing = ids.filter((id) => !nameMap[id])
    if (missing.length === 0) return
    // Fetch each missing prompt
    Promise.all(
      missing.map((id) =>
        promptsService
          .getPrompt(id)
          .then((p) => [id, p.name] as const)
          .catch(() => [id, "Unknown Prompt"] as const)
      )
    ).then((entries) => {
      setNameMap((prev) => {
        const next = { ...prev }
        for (const [id, name] of entries) {
          next[id] = name
        }
        return next
      })
    })
  }, [value]) // eslint-disable-line react-hooks/exhaustive-deps

  const segments = useMemo(
    () => parseToSegments(value, nameMap),
    [value, nameMap]
  )

  // Search mentions when query changes
  useEffect(() => {
    if (!showMentionMenu) return
    if (mentionSearchTimeoutRef.current) {
      clearTimeout(mentionSearchTimeoutRef.current)
    }
    mentionSearchTimeoutRef.current = setTimeout(async () => {
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
      }
    }, 150)
    return () => {
      if (mentionSearchTimeoutRef.current) {
        clearTimeout(mentionSearchTimeoutRef.current)
      }
    }
  }, [mentionQuery, showMentionMenu, surface])

  // -----------------------------------------------------------------------
  // Rendering the editor DOM from segments
  // -----------------------------------------------------------------------

  const renderEditorContent = useCallback(() => {
    const editor = editorRef.current
    if (!editor) return

    // Save cursor position info before re-render
    const sel = window.getSelection()
    let savedOffset = -1
    let savedNodeIndex = -1
    if (sel && sel.rangeCount > 0 && editor.contains(sel.anchorNode)) {
      const range = sel.getRangeAt(0)
      // Walk through child nodes to find position
      let charCount = 0
      for (let i = 0; i < editor.childNodes.length; i++) {
        const child = editor.childNodes[i]
        if (child === range.startContainer || child.contains(range.startContainer)) {
          savedNodeIndex = i
          savedOffset = charCount + range.startOffset
          break
        }
        charCount += (child.textContent || "").length
      }
    }

    suppressInputRef.current = true

    // Clear and rebuild
    editor.innerHTML = ""

    if (segments.length === 0) {
      // Empty state - just leave it empty, placeholder via CSS
      suppressInputRef.current = false
      return
    }

    for (let i = 0; i < segments.length; i++) {
      const seg = segments[i]
      if (seg.type === "text") {
        const textNode = document.createTextNode(seg.text)
        editor.appendChild(textNode)
      } else {
        const pill = document.createElement("span")
        pill.className =
          "inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 rounded bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 text-[11px] font-medium cursor-pointer select-none align-baseline whitespace-nowrap"
        pill.contentEditable = "false"
        pill.dataset.promptId = seg.promptId
        pill.dataset.mentionIndex = String(i)
        pill.textContent = `@${seg.name}`
        pill.addEventListener("click", (e) => {
          e.preventDefault()
          e.stopPropagation()
          onMentionClick?.(seg.promptId, i)
        })
        editor.appendChild(pill)
      }
    }

    // Restore cursor position
    if (savedOffset >= 0 && isFocused) {
      try {
        const newSel = window.getSelection()
        if (newSel) {
          let charCount = 0
          for (let i = 0; i < editor.childNodes.length; i++) {
            const child = editor.childNodes[i]
            const len = (child.textContent || "").length
            if (charCount + len >= savedOffset) {
              if (child.nodeType === Node.TEXT_NODE) {
                const range = document.createRange()
                range.setStart(child, Math.min(savedOffset - charCount, len))
                range.collapse(true)
                newSel.removeAllRanges()
                newSel.addRange(range)
              }
              break
            }
            charCount += len
          }
        }
      } catch {
        // Ignore cursor restoration errors
      }
    }

    suppressInputRef.current = false
  }, [segments, onMentionClick, isFocused])

  useEffect(() => {
    renderEditorContent()
  }, [renderEditorContent])

  // -----------------------------------------------------------------------
  // Extract plain text from editor DOM, producing serialized string
  // -----------------------------------------------------------------------

  const extractValueFromDOM = useCallback((): string => {
    const editor = editorRef.current
    if (!editor) return value

    const newSegments: MentionSegment[] = []
    for (let i = 0; i < editor.childNodes.length; i++) {
      const child = editor.childNodes[i]
      if (child.nodeType === Node.TEXT_NODE) {
        const text = child.textContent || ""
        if (text) newSegments.push({ type: "text", text })
      } else if (child instanceof HTMLElement && child.dataset.promptId) {
        newSegments.push({
          type: "mention",
          promptId: child.dataset.promptId,
          name: (child.textContent || "").replace(/^@/, ""),
        })
      } else {
        // Other elements (e.g. BR) -> treat as newline
        const text = child.textContent || ""
        if (text) newSegments.push({ type: "text", text })
        else if (child.nodeName === "BR") newSegments.push({ type: "text", text: "\n" })
      }
    }

    return serializeSegments(newSegments)
  }, [value])

  // -----------------------------------------------------------------------
  // Mention menu positioning
  // -----------------------------------------------------------------------

  const updateMenuPosition = useCallback(() => {
    const sel = window.getSelection()
    if (!sel || sel.rangeCount === 0) return
    const range = sel.getRangeAt(0)
    const rect = range.getBoundingClientRect()
    setMenuPosition({
      top: rect.bottom + 4,
      left: rect.left,
    })
  }, [])

  // -----------------------------------------------------------------------
  // Handle input events
  // -----------------------------------------------------------------------

  const handleInput = useCallback(() => {
    if (suppressInputRef.current || isComposingRef.current) return

    const editor = editorRef.current
    if (!editor) return

    const rawText = extractValueFromDOM()

    // Detect @mention trigger
    const sel = window.getSelection()
    if (sel && sel.rangeCount > 0) {
      const range = sel.getRangeAt(0)
      const node = range.startContainer
      if (node.nodeType === Node.TEXT_NODE) {
        const text = node.textContent || ""
        const offset = range.startOffset
        const textBefore = text.slice(0, offset)
        const atMatch = textBefore.match(/@([^\s@]*)$/)
        if (atMatch) {
          setMentionQuery(atMatch[1])
          setShowMentionMenu(true)
          updateMenuPosition()
          onChange(rawText)
          return
        }
      }
    }

    setShowMentionMenu(false)
    onChange(rawText)
  }, [extractValueFromDOM, onChange, updateMenuPosition])

  // -----------------------------------------------------------------------
  // Insert a mention
  // -----------------------------------------------------------------------

  const insertMention = useCallback(
    (mention: PromptMentionRecord) => {
      const editor = editorRef.current
      if (!editor) return

      // Update name map
      setNameMap((prev) => ({ ...prev, [mention.id]: mention.name }))

      // Find and replace the @query text with a mention token
      const sel = window.getSelection()
      if (!sel || sel.rangeCount === 0) return

      const range = sel.getRangeAt(0)
      const node = range.startContainer
      if (node.nodeType !== Node.TEXT_NODE) return

      const text = node.textContent || ""
      const offset = range.startOffset
      const textBefore = text.slice(0, offset)
      const atMatch = textBefore.match(/@([^\s@]*)$/)
      if (!atMatch) return

      const atStart = atMatch.index!
      const beforeAt = text.slice(0, atStart)
      const afterCursor = text.slice(offset)

      // Rebuild: set text before @, then the entire string with mention token, then text after
      const newValue =
        extractValueFromDOM().slice(0, (() => {
          // Calculate the byte position of the @ in the serialized value
          let charCount = 0
          for (let i = 0; i < editor.childNodes.length; i++) {
            const child = editor.childNodes[i]
            if (child === node) {
              return charCount + atStart
            }
            charCount += (child.textContent || "").length
          }
          return charCount
        })()) +
        `[[prompt:${mention.id}]]` +
        afterCursor

      setShowMentionMenu(false)
      onChange(newValue)
    },
    [extractValueFromDOM, onChange]
  )

  // -----------------------------------------------------------------------
  // Keyboard navigation for mention menu
  // -----------------------------------------------------------------------

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!showMentionMenu || mentionResults.length === 0) return

      if (e.key === "ArrowDown") {
        e.preventDefault()
        setSelectedMentionIdx((i) => (i + 1) % mentionResults.length)
      } else if (e.key === "ArrowUp") {
        e.preventDefault()
        setSelectedMentionIdx((i) => (i - 1 + mentionResults.length) % mentionResults.length)
      } else if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault()
        const selected = mentionResults[selectedMentionIdx]
        if (selected) insertMention(selected)
      } else if (e.key === "Escape") {
        e.preventDefault()
        setShowMentionMenu(false)
      }
    },
    [showMentionMenu, mentionResults, selectedMentionIdx, insertMention]
  )

  // -----------------------------------------------------------------------
  // Fill a mention with prompt content
  // -----------------------------------------------------------------------

  const handleFillMention = useCallback(
    async (mentionIndex: number) => {
      const seg = segments[mentionIndex]
      if (!seg || seg.type !== "mention") return
      try {
        const prompt = await promptsService.getPrompt(seg.promptId)
        const newSegments = fillMention(segments, mentionIndex, prompt.content)
        onChange(serializeSegments(newSegments))
      } catch {
        // ignore
      }
    },
    [segments, onChange]
  )

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  const isEmpty = !value

  return (
    <div className="relative">
      <div
        ref={editorRef}
        contentEditable
        suppressContentEditableWarning
        role="textbox"
        aria-multiline={multiline}
        aria-placeholder={placeholder}
        data-placeholder={placeholder}
        className={cn(
          "w-full rounded-lg border border-input bg-muted/40 px-3 py-2 text-[13px] text-foreground outline-none transition-colors",
          "focus:ring-1 focus:ring-ring focus:ring-offset-0",
          "placeholder:text-muted-foreground/40",
          "[&:empty]:before:content-[attr(data-placeholder)] [&:empty]:before:text-muted-foreground/40 [&:empty]:before:pointer-events-none",
          multiline ? "min-h-[60px] whitespace-pre-wrap break-words" : "min-h-[36px] h-9 overflow-hidden whitespace-nowrap",
          className
        )}
        onInput={handleInput}
        onKeyDown={handleKeyDown}
        onFocus={() => setIsFocused(true)}
        onBlur={() => {
          setIsFocused(false)
          // Delay closing menu so click events can fire
          setTimeout(() => setShowMentionMenu(false), 200)
        }}
        onCompositionStart={() => { isComposingRef.current = true }}
        onCompositionEnd={() => {
          isComposingRef.current = false
          handleInput()
        }}
      />

      {/* Mention search dropdown */}
      {showMentionMenu && mentionResults.length > 0 && (
        <div
          className="fixed z-[120] bg-popover text-popover-foreground shadow-lg rounded-lg border border-border p-1 max-h-[240px] overflow-auto min-w-[240px]"
          style={{ top: menuPosition.top, left: menuPosition.left }}
        >
          {mentionResults.map((result, idx) => (
            <div
              key={result.id}
              className={cn(
                "flex items-center gap-2 px-2 py-1.5 text-xs rounded-md cursor-pointer",
                idx === selectedMentionIdx
                  ? "bg-accent text-accent-foreground"
                  : "hover:bg-muted"
              )}
              onMouseDown={(e) => {
                e.preventDefault()
                insertMention(result)
              }}
            >
              <BookOpen className="h-3.5 w-3.5 text-blue-500 shrink-0" />
              <div className="flex flex-col min-w-0">
                <span className="font-medium truncate">{result.name}</span>
                {result.description && (
                  <span className="text-[10px] text-muted-foreground truncate">
                    {result.description}
                  </span>
                )}
              </div>
              <span className="ml-auto text-[10px] text-muted-foreground/60 shrink-0">
                {result.scope}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Export the fill handler for use by the PromptModal
// ---------------------------------------------------------------------------

export { fillMention as fillMentionSegment }
