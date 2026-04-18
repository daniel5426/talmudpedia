export function useAppsBuilderChatSessionActions() {
  return {
    sendBuilderChat: async (_rawInput: string) => undefined,
    removeQueuedPrompt: (_promptId: string) => undefined,
    answerPendingQuestion: async (_answers: string[][]) => undefined,
    stopCurrentRun: () => undefined,
    startNewChat: () => undefined,
  };
}
