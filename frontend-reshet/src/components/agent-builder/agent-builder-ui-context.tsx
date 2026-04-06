"use client"

import { createContext, useContext } from "react"

export type AgentBuilderUiContextValue = {
  focusAgentTool: (nodeId: string, toolId: string) => void
  openToolDetailFromSettings: (toolId: string) => void
}

export const AgentBuilderUiContext = createContext<AgentBuilderUiContextValue | null>(null)

export function useAgentBuilderUi(): AgentBuilderUiContextValue | null {
  return useContext(AgentBuilderUiContext)
}
