export interface VariableSuggestionOption {
  id: string
  displayLabel: string
  insertText: string
  type?: string
  groupLabel?: string
  nodeId?: string
}

export function filterVariableSuggestions(
  suggestions: VariableSuggestionOption[],
  rawQuery: string,
): VariableSuggestionOption[] {
  const query = String(rawQuery || "").trim().toLowerCase()
  if (!query) {
    return suggestions
  }

  return suggestions.filter((suggestion) => {
    const haystacks = [
      suggestion.displayLabel,
      suggestion.insertText,
      suggestion.groupLabel,
      suggestion.type,
    ]
      .filter(Boolean)
      .map((value) => String(value).toLowerCase())

    return haystacks.some((value) => value.includes(query))
  })
}
