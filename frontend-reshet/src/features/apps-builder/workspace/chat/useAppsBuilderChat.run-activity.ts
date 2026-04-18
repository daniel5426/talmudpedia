export function useAppsBuilderChatRunActivity() {
  return {
    sessionRunActivityMap: {},
    runningSessionIds: [] as string[],
    markSessionRunActive: () => undefined,
    clearSessionRunActivity: () => undefined,
    probeSessionRunActivity: async () => undefined,
    probeSessionRunActivityBatch: async () => undefined,
  };
}
