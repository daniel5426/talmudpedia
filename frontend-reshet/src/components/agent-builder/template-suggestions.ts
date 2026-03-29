"use client"

import type {
  AgentGraphAnalysis,
  AgentGraphTemplateSuggestion,
} from "@/services/agent"
import type { VariableSuggestionOption } from "../shared/variable-suggestions"

function toOption(
  suggestion: AgentGraphTemplateSuggestion,
  groupLabel?: string,
): VariableSuggestionOption {
  return {
    id: suggestion.id,
    displayLabel: suggestion.display_label,
    insertText: suggestion.insert_text,
    type: suggestion.type,
    groupLabel,
    nodeId: suggestion.node_id,
  }
}

export function getTemplateSuggestionsForNode(
  analysis?: AgentGraphAnalysis | null,
  nodeId?: string | null,
): VariableSuggestionOption[] {
  if (!analysis) return []

  const suggestions: VariableSuggestionOption[] = []
  const seen = new Set<string>()
  const globalSuggestions = Array.isArray(analysis.inventory.template_suggestions?.global)
    ? analysis.inventory.template_suggestions.global
    : []
  const scopedSuggestions =
    nodeId && analysis.inventory.template_suggestions?.by_node
      ? analysis.inventory.template_suggestions.by_node[nodeId] || []
      : []

  for (const suggestion of globalSuggestions) {
    if (!suggestion?.id || seen.has(suggestion.id)) continue
    seen.add(suggestion.id)
    suggestions.push(
      toOption(
        suggestion,
        suggestion.namespace === "workflow_input" ? "Workflow Input" : "State",
      ),
    )
  }

  for (const suggestion of scopedSuggestions) {
    if (!suggestion?.id || seen.has(suggestion.id)) continue
    seen.add(suggestion.id)
    suggestions.push(toOption(suggestion, "Direct Inputs"))
  }

  return suggestions
}
