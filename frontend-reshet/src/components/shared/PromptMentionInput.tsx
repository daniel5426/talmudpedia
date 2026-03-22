"use client"

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
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
  id?: string
  value: string
  onChange: (value: string) => void
  surface?: string
  availableVariables?: Array<{ name: string; type?: string }>
  placeholder?: string
  className?: string
  multiline?: boolean
  onMentionClick?: (promptId: string, mentionIndex: number) => void
}

type MentionSuggestion =
  | { kind: "prompt"; key: string; prompt: PromptMentionRecord }
  | { kind: "variable"; key: string; variable: { name: string; type?: string } }

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PromptMentionInput({
  id,
  value,
  onChange,
  surface,
  availableVariables = [],
  placeholder,
  className,
  multiline = true,
  onMentionClick,
}: PromptMentionInputProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const [nameMap, setNameMap] = useState<Record<string, string>>({})
  const [showMentionMenu, setShowMentionMenu] = useState(false)
  const [mentionQuery, setMentionQuery] = useState("")
  const [mentionResults, setMentionResults] = useState<PromptMentionRecord[]>([])
  const [mentionLoading, setMentionLoading] = useState(false)
  const [selectedMentionIdx, setSelectedMentionIdx] = useState(0)
  const [menuPosition, setMenuPosition] = useState<{ top: number; left: number }>({ top: 0, left: 0 })
  const [isFocused, setIsFocused] = useState(false)
  const mentionSearchTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const isComposingRef = useRef(false)
  const suppressInputRef = useRef(false)
  const pendingSerializedCursorOffsetRef = useRef<number | null>(null)
  const anchorRectRef = useRef<DOMRect | null>(null)

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
  const variableResults = useMemo(
    () =>
      availableVariables.filter((variable) => {
        if (!mentionQuery.trim()) {
          return true
        }
        const normalizedQuery = mentionQuery.trim().toLowerCase()
        return variable.name.toLowerCase().includes(normalizedQuery)
      }),
    [availableVariables, mentionQuery]
  )
  const suggestionItems = useMemo<MentionSuggestion[]>(
    () => [
      ...variableResults.map((variable) => ({
        kind: "variable" as const,
        key: `variable:${variable.name}`,
        variable,
      })),
      ...mentionResults.map((prompt) => ({
        kind: "prompt" as const,
        key: `prompt:${prompt.id}`,
        prompt,
      })),
    ],
    [variableResults, mentionResults]
  )

  // Search mentions when query changes
  useEffect(() => {
    if (!showMentionMenu) return
    if (mentionSearchTimeoutRef.current) {
      clearTimeout(mentionSearchTimeoutRef.current)
    }
    mentionSearchTimeoutRef.current = setTimeout(async () => {
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
        editor.appendChild(document.createTextNode(""))
      }
    }

    if (pendingSerializedCursorOffsetRef.current === null && savedOffset >= 0 && isFocused) {
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

  useLayoutEffect(() => {
    const pendingSerializedOffset = pendingSerializedCursorOffsetRef.current
    const editor = editorRef.current
    if (pendingSerializedOffset === null || !editor) {
      return
    }

    let frameId = 0
    let attempts = 0

    const restore = () => {
      const currentEditor = editorRef.current
      if (!currentEditor) return
      currentEditor.focus()
      restoreSelectionFromSerializedOffset(currentEditor, pendingSerializedOffset)
      setIsFocused(true)
      attempts += 1
      if (attempts >= 3) {
        pendingSerializedCursorOffsetRef.current = null
        return
      }
      frameId = window.requestAnimationFrame(restore)
    }

    frameId = window.requestAnimationFrame(restore)
    return () => window.cancelAnimationFrame(frameId)
  }, [segments, value])

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
    anchorRectRef.current = rect
    const root = rootRef.current
    const menu = menuRef.current
    if (!root || !menu) {
      setMenuPosition({
        top: 0,
        left: 0,
      })
      return
    }
    setMenuPosition(positionMenu(rect, menu, root))
  }, [])

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

  // -----------------------------------------------------------------------
  // Handle input events
  // -----------------------------------------------------------------------

  const handleInput = useCallback(() => {
    if (suppressInputRef.current || isComposingRef.current) return

    const editor = editorRef.current
    if (!editor) return

    const rawText = extractValueFromDOM()

    const cursorOffset = getCursorPlainTextOffset(editor)
    if (cursorOffset !== null) {
      const textBeforeCursor = getEditorPlainText(editor).slice(0, cursorOffset)
      const atMatch = textBeforeCursor.match(/@([^\s@]*)$/)
      if (atMatch) {
        setMentionQuery(atMatch[1])
        setShowMentionMenu(true)
        updateMenuPosition()
        onChange(rawText)
        return
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

      const plainCursorOffset = getCursorPlainTextOffset(editor)
      if (plainCursorOffset === null) return

      const plainText = getEditorPlainText(editor)
      const textBefore = plainText.slice(0, plainCursorOffset)
      const atMatch = textBefore.match(/@([^\s@]*)$/)
      if (!atMatch) return

      const queryStart = atMatch.index ?? 0
      const serializedValue = extractValueFromDOM()
      const serializedFrom = mapPlainOffsetToSerializedOffset(editor, queryStart)
      const serializedTo = mapPlainOffsetToSerializedOffset(editor, plainCursorOffset)
      const newValue =
        serializedValue.slice(0, serializedFrom) +
        `[[prompt:${mention.id}]]` +
        serializedValue.slice(serializedTo)

      pendingSerializedCursorOffsetRef.current = serializedFrom + `[[prompt:${mention.id}]]`.length
      setShowMentionMenu(false)
      onChange(newValue)
    },
    [extractValueFromDOM, onChange]
  )

  const insertVariableAlias = useCallback(
    (variableName: string) => {
      const editor = editorRef.current
      if (!editor) return

      const plainCursorOffset = getCursorPlainTextOffset(editor)
      if (plainCursorOffset === null) return

      const plainText = getEditorPlainText(editor)
      const textBefore = plainText.slice(0, plainCursorOffset)
      const atMatch = textBefore.match(/@([^\s@]*)$/)
      if (!atMatch) return

      const queryStart = atMatch.index ?? 0
      const serializedValue = extractValueFromDOM()
      const serializedFrom = mapPlainOffsetToSerializedOffset(editor, queryStart)
      const serializedTo = mapPlainOffsetToSerializedOffset(editor, plainCursorOffset)
      const variableToken = `{{ ${variableName} }}`
      const nextValue =
        serializedValue.slice(0, serializedFrom) +
        variableToken +
        serializedValue.slice(serializedTo)

      pendingSerializedCursorOffsetRef.current = serializedFrom + variableToken.length
      setShowMentionMenu(false)
      onChange(nextValue)
    },
    [extractValueFromDOM, onChange]
  )

  // -----------------------------------------------------------------------
  // Keyboard navigation for mention menu
  // -----------------------------------------------------------------------

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!showMentionMenu) {
        const deletionApplied = handleAdjacentMentionDeletion(
          e,
          editorRef.current,
          value,
          onChange,
          (nextSerializedOffset) => {
            pendingSerializedCursorOffsetRef.current = nextSerializedOffset
          }
        )
        if (deletionApplied) {
          return
        }
      }

      if (!showMentionMenu || suggestionItems.length === 0) return

      if (e.key === "ArrowDown") {
        e.preventDefault()
        setSelectedMentionIdx((i) => (i + 1) % suggestionItems.length)
      } else if (e.key === "ArrowUp") {
        e.preventDefault()
        setSelectedMentionIdx((i) => (i - 1 + suggestionItems.length) % suggestionItems.length)
      } else if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault()
        const selected = suggestionItems[selectedMentionIdx]
        if (!selected) {
          return
        }
        if (selected.kind === "prompt") {
          insertMention(selected.prompt)
          return
        }
        insertVariableAlias(selected.variable.name)
      } else if (e.key === "Escape") {
        e.preventDefault()
        setShowMentionMenu(false)
      }
    },
    [showMentionMenu, suggestionItems, selectedMentionIdx, insertMention, insertVariableAlias, value, onChange]
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
    <div ref={rootRef} className="relative">
      <div
        id={id}
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
      {showMentionMenu && (
        <div
          ref={menuRef}
          className="absolute z-[120] bg-popover text-popover-foreground shadow-lg rounded-lg border border-border p-1 max-h-[240px] overflow-auto min-w-[240px]"
          style={{ top: menuPosition.top, left: menuPosition.left }}
        >
          {mentionLoading ? (
            <div className="px-2 py-2 text-xs text-muted-foreground">Loading prompts...</div>
          ) : null}
          {!mentionLoading && suggestionItems.length === 0 ? (
            <div className="px-2 py-2 text-xs text-muted-foreground">No matches found.</div>
          ) : null}
          {suggestionItems.map((item, idx) => (
            <div
              key={item.key}
              className={cn(
                "flex items-center gap-2 px-2 py-1.5 text-xs rounded-md cursor-pointer",
                idx === selectedMentionIdx
                  ? "bg-accent text-accent-foreground"
                  : "hover:bg-muted"
              )}
              onMouseDown={(e) => {
                e.preventDefault()
                if (item.kind === "prompt") {
                  insertMention(item.prompt)
                  return
                }
                insertVariableAlias(item.variable.name)
              }}
            >
              {item.kind === "prompt" ? (
                <BookOpen className="h-3.5 w-3.5 text-blue-500 shrink-0" />
              ) : (
                <span className="flex h-3.5 w-3.5 items-center justify-center text-[10px] font-semibold text-emerald-600 shrink-0">
                  #
                </span>
              )}
              <div className="flex flex-col min-w-0">
                <span className="font-medium truncate">
                  {item.kind === "prompt" ? item.prompt.name : item.variable.name}
                </span>
                {item.kind === "prompt" && item.prompt.description ? (
                  <span className="text-[10px] text-muted-foreground truncate">
                    {item.prompt.description}
                  </span>
                ) : item.kind === "variable" ? (
                  <span className="text-[10px] text-muted-foreground truncate">
                    {item.variable.type || "Variable"}
                  </span>
                ) : null}
              </div>
              {item.kind === "prompt" ? (
                <span className="ml-auto text-[10px] text-muted-foreground/60 shrink-0">
                  {item.prompt.scope}
                </span>
              ) : null}
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
  const centeredLeft = anchorLeft
  const left = Math.min(
    Math.max(viewportPadding, centeredLeft),
    Math.max(viewportPadding, rootRect.width - menuWidth - viewportPadding)
  )
  return { top, left }
}

function getEditorPlainText(editor: HTMLDivElement): string {
  return editor.textContent || ""
}

function getCursorPlainTextOffset(editor: HTMLDivElement): number | null {
  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0 || !editor.contains(selection.anchorNode)) {
    return null
  }
  const range = selection.getRangeAt(0).cloneRange()
  const prefix = range.cloneRange()
  prefix.selectNodeContents(editor)
  prefix.setEnd(range.endContainer, range.endOffset)
  return prefix.toString().length
}

function mapPlainOffsetToSerializedOffset(editor: HTMLDivElement, plainOffset: number): number {
  let plainCount = 0
  let serializedCount = 0
  for (let i = 0; i < editor.childNodes.length; i++) {
    const child = editor.childNodes[i]
    const childText = child.textContent || ""
    const plainLength = childText.length
    const serializedLength =
      child instanceof HTMLElement && child.dataset.promptId
        ? `[[prompt:${child.dataset.promptId}]]`.length
        : plainLength

    if (plainOffset <= plainCount + plainLength) {
      if (child instanceof HTMLElement && child.dataset.promptId) {
        return plainOffset <= plainCount ? serializedCount : serializedCount + serializedLength
      }
      return serializedCount + Math.max(0, plainOffset - plainCount)
    }

    plainCount += plainLength
    serializedCount += serializedLength
  }
  return serializedCount
}

function restoreSelectionFromSerializedOffset(editor: HTMLDivElement, serializedOffset: number) {
  const selection = window.getSelection()
  if (!selection) return

  let serializedCount = 0
  for (let i = 0; i < editor.childNodes.length; i++) {
    const child = editor.childNodes[i]
    const serializedLength =
      child instanceof HTMLElement && child.dataset.promptId
        ? `[[prompt:${child.dataset.promptId}]]`.length
        : (child.textContent || "").length

    if (serializedOffset <= serializedCount + serializedLength) {
      const range = document.createRange()
      if (child instanceof HTMLElement && child.dataset.promptId) {
        if (serializedOffset <= serializedCount) {
          range.setStartBefore(child)
        } else {
          const trailingNode = ensureTrailingTextNode(editor, child)
          range.setStart(trailingNode, 0)
        }
      } else {
        range.setStart(child, Math.max(0, Math.min(serializedOffset - serializedCount, serializedLength)))
      }
      range.collapse(true)
      selection.removeAllRanges()
      selection.addRange(range)
      return
    }

    serializedCount += serializedLength
  }

  const range = document.createRange()
  range.selectNodeContents(editor)
  range.collapse(false)
  selection.removeAllRanges()
  selection.addRange(range)
}

function ensureTrailingTextNode(editor: HTMLDivElement, mentionNode: HTMLElement): Text {
  const nextSibling = mentionNode.nextSibling
  if (nextSibling?.nodeType === Node.TEXT_NODE) {
    return nextSibling as Text
  }
  const textNode = document.createTextNode("")
  editor.insertBefore(textNode, nextSibling)
  return textNode
}

function handleAdjacentMentionDeletion(
  event: React.KeyboardEvent,
  editor: HTMLDivElement | null,
  value: string,
  onChange: (value: string) => void,
  setPendingCursorOffset: (offset: number) => void
) {
  if (!editor || (event.key !== "Backspace" && event.key !== "Delete")) {
    return false
  }

  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0 || !selection.isCollapsed) {
    return false
  }

  const range = selection.getRangeAt(0)
  if (!editor.contains(range.startContainer)) {
    return false
  }

  const nearbyTextDeletion = handleTextDeletionNearMention(
    event.key,
    range,
    editor,
    value,
    onChange,
    setPendingCursorOffset
  )
  if (nearbyTextDeletion) {
    event.preventDefault()
    return true
  }

  const adjacentMention =
    event.key === "Backspace"
      ? getMentionBeforeCaret(range)
      : getMentionAfterCaret(range)

  if (!adjacentMention) {
    return false
  }

  event.preventDefault()
  const mentionIndex = Number(adjacentMention.dataset.mentionIndex)
  if (Number.isNaN(mentionIndex)) {
    return false
  }

  const segments = parseToSegments(value, {})
  const serializedStart = getSerializedOffsetForSegmentIndex(segments, mentionIndex)
  const updatedValue = serializeSegments(segments.filter((_, idx) => idx !== mentionIndex))
  setPendingCursorOffset(serializedStart)
  onChange(updatedValue)
  return true
}

function handleTextDeletionNearMention(
  key: "Backspace" | "Delete" | string,
  range: Range,
  editor: HTMLDivElement,
  value: string,
  onChange: (value: string) => void,
  setPendingCursorOffset: (offset: number) => void
) {
  if (range.startContainer.nodeType !== Node.TEXT_NODE) {
    return false
  }

  const textNode = range.startContainer as Text
  const textValue = textNode.textContent || ""
  const previousMention = findMentionSibling(textNode.previousSibling, "backward")
  const nextMention = findMentionSibling(textNode.nextSibling, "forward")
  const plainCursorOffset = getCursorPlainTextOffset(editor)

  if (plainCursorOffset === null) {
    return false
  }

  if (key === "Backspace" && previousMention && range.startOffset > 0) {
    const serializedOffset = mapPlainOffsetToSerializedOffset(editor, plainCursorOffset)
    const nextValue = value.slice(0, serializedOffset - 1) + value.slice(serializedOffset)
    setPendingCursorOffset(serializedOffset - 1)
    onChange(nextValue)
    return true
  }

  if (key === "Delete" && nextMention && range.startOffset < textValue.length) {
    const serializedOffset = mapPlainOffsetToSerializedOffset(editor, plainCursorOffset)
    const nextValue = value.slice(0, serializedOffset) + value.slice(serializedOffset + 1)
    setPendingCursorOffset(serializedOffset)
    onChange(nextValue)
    return true
  }

  return false
}

function getMentionBeforeCaret(range: Range): HTMLElement | null {
  const { startContainer, startOffset } = range
  if (startContainer.nodeType === Node.TEXT_NODE) {
    if (startOffset > 0) {
      return null
    }
    return findMentionSibling(startContainer.previousSibling, "backward")
  }
  const childBefore = startContainer.childNodes[startOffset - 1] || null
  return findMentionSibling(childBefore, "backward")
}

function getMentionAfterCaret(range: Range): HTMLElement | null {
  const { startContainer, startOffset } = range
  if (startContainer.nodeType === Node.TEXT_NODE) {
    const text = startContainer.textContent || ""
    if (startOffset < text.length) {
      return null
    }
    return findMentionSibling(startContainer.nextSibling, "forward")
  }
  const childAfter = startContainer.childNodes[startOffset] || null
  return findMentionSibling(childAfter, "forward")
}

function findMentionSibling(node: Node | null, direction: "backward" | "forward"): HTMLElement | null {
  let current = node
  while (current) {
    if (current instanceof HTMLElement && current.dataset.promptId) {
      return current
    }
    if (current.nodeType === Node.TEXT_NODE && (current.textContent || "").length > 0) {
      return null
    }
    current = direction === "backward" ? current.previousSibling : current.nextSibling
  }
  return null
}

function getSerializedOffsetForSegmentIndex(segments: MentionSegment[], segmentIndex: number) {
  let offset = 0
  for (let i = 0; i < segmentIndex; i++) {
    const segment = segments[i]
    offset +=
      segment.type === "mention"
        ? `[[prompt:${segment.promptId}]]`.length
        : segment.text.length
  }
  return offset
}
