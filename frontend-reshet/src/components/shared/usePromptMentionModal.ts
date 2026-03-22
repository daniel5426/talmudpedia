"use client"

import { useCallback, useState } from "react"

export interface PromptMentionModalState<TContext> {
  promptId: string | null
  open: boolean
  context: TContext | null
}

export function usePromptMentionModal<TContext>() {
  const [state, setState] = useState<PromptMentionModalState<TContext>>({
    promptId: null,
    open: false,
    context: null,
  })

  const openPromptMentionModal = useCallback((promptId: string, context: TContext) => {
    setState({
      promptId,
      open: true,
      context,
    })
  }, [])

  const handleOpenChange = useCallback((open: boolean) => {
    setState((current) =>
      open
        ? current
        : {
            promptId: null,
            open: false,
            context: null,
          }
    )
  }, [])

  return {
    promptId: state.promptId,
    open: state.open,
    context: state.context,
    openPromptMentionModal,
    handleOpenChange,
  }
}
