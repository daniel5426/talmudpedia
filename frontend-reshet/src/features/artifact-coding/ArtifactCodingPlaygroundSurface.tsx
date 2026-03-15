"use client";

import { useCallback, useState } from "react";

import type { ArtifactCodingScopeMode } from "@/services/artifacts";

import { ArtifactCodingChatPanel } from "./ArtifactCodingChatPanel";
import { useArtifactCodingChat } from "./useArtifactCodingChat";

type ArtifactCodingPlaygroundSurfaceProps = {
  tenantSlug?: string;
  tenantId?: string | null;
  initialChatSessionId?: string | null;
  onChatSessionIdChange?: (sessionId: string | null) => void;
};

export function ArtifactCodingPlaygroundSurface({
  tenantSlug,
  tenantId,
  initialChatSessionId,
  onChatSessionIdChange,
}: ArtifactCodingPlaygroundSurfaceProps) {
  const [draftSnapshot, setDraftSnapshot] = useState<Record<string, unknown>>({});
  const scopeMode: ArtifactCodingScopeMode = "standalone";
  const {
    isSending,
    isStopping,
    timeline,
    activeThinkingSummary,
    chatSessions,
    activeChatSessionId,
    startNewChat,
    loadChatSession,
    sendMessage,
    stopCurrentRun,
    chatModels,
    selectedRunModelLabel,
    isModelSelectorOpen,
    setIsModelSelectorOpen,
    setSelectedRunModelId,
    pendingQuestion,
    isAnsweringQuestion,
    runningSessionIds,
    hasOlderHistory,
    isLoadingOlderHistory,
    loadOlderHistory,
    answerPendingQuestion,
    revertingRunId,
    revertToRun,
  } = useArtifactCodingChat({
    tenantSlug,
    tenantId,
    artifactId: null,
    draftKey: "",
    isCreateMode: true,
    scopeMode,
    initialChatSessionId: initialChatSessionId || null,
    getDraftSnapshot: () => draftSnapshot,
    onApplyDraftSnapshot: setDraftSnapshot,
    onResetDraftSnapshot: () => setDraftSnapshot({}),
    onActiveChatSessionChange: onChatSessionIdChange,
    onError: (message) => {
      if (message) {
        console.error("Artifact coding playground error", message);
      }
    },
  });

  const handleLoadChatSession = useCallback(
    async (sessionId: string) => {
      await loadChatSession(sessionId);
    },
    [loadChatSession],
  );

  return (
    <div className="flex h-full min-w-0 flex-1">
      <ArtifactCodingChatPanel
        isOpen={true}
        layoutMode="playground"
        isSending={isSending}
        isStopping={isStopping}
        timeline={timeline}
        activeThinkingSummary={activeThinkingSummary}
        chatSessions={chatSessions}
        activeChatSessionId={activeChatSessionId}
        onStartNewChat={startNewChat}
        onOpenHistory={() => undefined}
        onLoadChatSession={handleLoadChatSession}
        onSendMessage={sendMessage}
        onStopRun={stopCurrentRun}
        chatModels={chatModels}
        selectedRunModelLabel={selectedRunModelLabel}
        isModelSelectorOpen={isModelSelectorOpen}
        onModelSelectorOpenChange={setIsModelSelectorOpen}
        onSelectModelId={setSelectedRunModelId}
        pendingQuestion={pendingQuestion}
        isAnsweringQuestion={isAnsweringQuestion}
        runningSessionIds={runningSessionIds}
        hasOlderHistory={hasOlderHistory}
        isLoadingOlderHistory={isLoadingOlderHistory}
        onLoadOlderHistory={loadOlderHistory}
        onAnswerQuestion={answerPendingQuestion}
        revertingRunId={revertingRunId}
        onRevertToRun={revertToRun}
      />
    </div>
  );
}
