import { useCallback, useEffect, useMemo, useState, type WheelEvent } from "react";

import type { CodingAgentChatSession } from "@/services";

import type { TimelineItem } from "./chat-model";
import { isUserTimelineItem } from "./chat-model";
import {
  DEFAULT_THREAD_TITLE,
  isLocalSessionKey,
  normalizeThreadTitle,
} from "./useAppsBuilderChat.session-state";

function deriveTitleFromTimeline(timeline: TimelineItem[]): string {
  const lastUserPrompt = [...timeline]
    .reverse()
    .find((item) => isUserTimelineItem(item) && String(item.description || "").trim().length > 0);
  return normalizeThreadTitle(lastUserPrompt?.description);
}

export type ThreadTab =
  | {
    id: string;
    kind: "session";
    session: CodingAgentChatSession;
    title: string;
  }
  | {
    id: string;
    kind: "provisional";
    sessionId: string;
    title: string;
  }
  | {
    id: "__draft__";
    kind: "draft";
    title: string;
  };

type UseAppsBuilderChatThreadTabsOptions = {
  chatSessions: CodingAgentChatSession[];
  activeChatSessionId: string | null;
  runningSessionIds: string[];
  timeline: TimelineItem[];
  sessionTitleHintsBySessionId?: Record<string, string>;
  onActivateDraftChat: () => void;
  onLoadChatSession: (sessionId: string) => Promise<void>;
  onStartNewChat: () => void;
};

export function useAppsBuilderChatThreadTabs({
  chatSessions,
  activeChatSessionId,
  runningSessionIds,
  timeline,
  sessionTitleHintsBySessionId = {},
  onActivateDraftChat,
  onLoadChatSession,
  onStartNewChat,
}: UseAppsBuilderChatThreadTabsOptions) {
  const [openThreadTabIds, setOpenThreadTabIds] = useState<string[]>([]);
  const [hasDraftThreadTab, setHasDraftThreadTab] = useState(false);
  const [sessionTitleHints, setSessionTitleHints] = useState<Record<string, string>>({});
  const [lastDraftPromptTitle, setLastDraftPromptTitle] = useState<string>(DEFAULT_THREAD_TITLE);
  const isDraftActive = String(activeChatSessionId || "").trim().length === 0;

  useEffect(() => {
    const normalizedActiveId = String(activeChatSessionId || "").trim();
    if (!normalizedActiveId) return;
    setOpenThreadTabIds((prev) => (prev.includes(normalizedActiveId) ? prev : [...prev, normalizedActiveId]));
  }, [activeChatSessionId]);

  useEffect(() => {
    if (!chatSessions.length) {
      return;
    }
    setSessionTitleHints((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const session of chatSessions) {
        const sessionId = String(session.id || "").trim();
        const sessionTitle = String(session.title || "").trim();
        if (!sessionId || !sessionTitle || next[sessionId] === sessionTitle) {
          continue;
        }
        const existingTitle = String(next[sessionId] || "").trim();
        if (existingTitle && existingTitle !== DEFAULT_THREAD_TITLE) {
          continue;
        }
        next[sessionId] = sessionTitle;
        changed = true;
      }
      return changed ? next : prev;
    });
  }, [chatSessions]);

  useEffect(() => {
    const incoming = Object.entries(sessionTitleHintsBySessionId || {});
    if (!incoming.length) {
      return;
    }
    setSessionTitleHints((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const [rawSessionId, rawTitle] of incoming) {
        const sessionId = String(rawSessionId || "").trim();
        const sessionTitle = normalizeThreadTitle(rawTitle);
        if (!sessionId || next[sessionId] === sessionTitle) {
          continue;
        }
        const existingTitle = String(next[sessionId] || "").trim();
        if (existingTitle && existingTitle !== DEFAULT_THREAD_TITLE) {
          continue;
        }
        next[sessionId] = sessionTitle;
        changed = true;
      }
      return changed ? next : prev;
    });
  }, [sessionTitleHintsBySessionId]);

  const draftThreadTitle = useMemo(() => {
    if (!isDraftActive) {
      return DEFAULT_THREAD_TITLE;
    }
    return deriveTitleFromTimeline(timeline);
  }, [isDraftActive, timeline]);

  useEffect(() => {
    const nextDraftTitle = String(draftThreadTitle || "").trim();
    if (!hasDraftThreadTab || !nextDraftTitle || nextDraftTitle === DEFAULT_THREAD_TITLE) {
      return;
    }
    setLastDraftPromptTitle((prev) => (prev === nextDraftTitle ? prev : nextDraftTitle));
  }, [draftThreadTitle, hasDraftThreadTab]);

  useEffect(() => {
    const runningIds = Array.from(
      new Set(
        (runningSessionIds || [])
          .map((id) => String(id || "").trim())
          .filter(Boolean),
      ),
    );
    if (!runningIds.length) {
      return;
    }

    setOpenThreadTabIds((prev) => {
      let changed = false;
      const next = [...prev];
      for (const runningId of runningIds) {
        if (!next.includes(runningId)) {
          next.push(runningId);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [runningSessionIds]);

  useEffect(() => {
    const activeId = String(activeChatSessionId || "").trim();
    const runningSet = new Set(
      (runningSessionIds || [])
        .map((id) => String(id || "").trim())
        .filter(Boolean),
    );
    setOpenThreadTabIds((prev) => {
      const next = prev.filter((id) => {
        if (!isLocalSessionKey(id)) {
          return true;
        }
        if (id === activeId) {
          return true;
        }
        return runningSet.has(id);
      });
      return next.length === prev.length ? prev : next;
    });
  }, [activeChatSessionId, runningSessionIds]);

  useEffect(() => {
    if (!hasDraftThreadTab) {
      return;
    }
    const activeId = String(activeChatSessionId || "").trim();
    let localSessionId = "";
    if (activeId && isLocalSessionKey(activeId)) {
      localSessionId = activeId;
    }
    if (!localSessionId) {
      localSessionId = (runningSessionIds || [])
        .map((id) => String(id || "").trim())
        .find((id) => {
          if (!isLocalSessionKey(id)) {
            return false;
          }
          const externalTitle = normalizeThreadTitle(sessionTitleHintsBySessionId[id]);
          const internalTitle = normalizeThreadTitle(sessionTitleHints[id]);
          return externalTitle !== DEFAULT_THREAD_TITLE || internalTitle !== DEFAULT_THREAD_TITLE;
        }) || "";
    }
    if (!localSessionId) {
      return;
    }
    setOpenThreadTabIds((prev) => (prev.includes(localSessionId) ? prev : [...prev, localSessionId]));
    setHasDraftThreadTab(false);
  }, [
    activeChatSessionId,
    hasDraftThreadTab,
    runningSessionIds,
    sessionTitleHints,
    sessionTitleHintsBySessionId,
  ]);

  const resolveThreadTitle = useCallback((sessionId: string, fallbackTitle?: string) => {
    const normalizedId = String(sessionId || "").trim();
    if (!normalizedId) {
      return DEFAULT_THREAD_TITLE;
    }
    const hinted = String(sessionTitleHints[normalizedId] || "").trim();
    if (hinted) {
      return hinted;
    }
    const fallback = String(fallbackTitle || "").trim();
    return fallback || DEFAULT_THREAD_TITLE;
  }, [sessionTitleHints]);

  const threadTabs = useMemo<ThreadTab[]>(() => {
    if (chatSessions.length === 0 && !activeChatSessionId && !hasDraftThreadTab) {
      return [];
    }
    const byId = new Map(chatSessions.map((session) => [session.id, session]));
    const activeId = String(activeChatSessionId || "").trim();
    const tabs: ThreadTab[] = [];
    const seen = new Set<string>();

    for (const sessionId of openThreadTabIds) {
      if (seen.has(sessionId)) continue;
      const session = byId.get(sessionId);
      if (session) {
        const title = resolveThreadTitle(session.id, session.title);
        tabs.push({
          id: session.id,
          kind: "session",
          session,
          title,
        });
        seen.add(session.id);
        continue;
      }
      tabs.push({
        id: sessionId,
        kind: "provisional",
        sessionId,
        title: resolveThreadTitle(sessionId),
      });
      seen.add(sessionId);
    }

    if (activeId && !seen.has(activeId)) {
      const activeSession = byId.get(activeId);
      if (activeSession) {
        const title = resolveThreadTitle(activeSession.id, activeSession.title);
        tabs.push({
          id: activeSession.id,
          kind: "session",
          session: activeSession,
          title,
        });
        seen.add(activeSession.id);
      } else if (hasDraftThreadTab) {
        tabs.push({
          id: activeId,
          kind: "provisional",
          sessionId: activeId,
          title: resolveThreadTitle(activeId, draftThreadTitle),
        });
        seen.add(activeId);
      }
    }

    for (const runningSessionId of runningSessionIds) {
      const normalizedRunningId = String(runningSessionId || "").trim();
      if (!normalizedRunningId || seen.has(normalizedRunningId)) {
        continue;
      }
      const runningSession = byId.get(normalizedRunningId);
      if (runningSession) {
        const title = resolveThreadTitle(runningSession.id, runningSession.title);
        tabs.push({
          id: runningSession.id,
          kind: "session",
          session: runningSession,
          title,
        });
        seen.add(runningSession.id);
        continue;
      }
      tabs.push({
        id: normalizedRunningId,
        kind: "provisional",
        sessionId: normalizedRunningId,
        title: resolveThreadTitle(normalizedRunningId),
      });
      seen.add(normalizedRunningId);
    }

    if (hasDraftThreadTab) {
      tabs.push({
        id: "__draft__",
        kind: "draft",
        title: draftThreadTitle,
      });
    }
    return tabs;
  }, [
    activeChatSessionId,
    chatSessions,
    draftThreadTitle,
    hasDraftThreadTab,
    lastDraftPromptTitle,
    openThreadTabIds,
    resolveThreadTitle,
    runningSessionIds,
  ]);

  const handleOpenThreadTab = (sessionId: string) => {
    const normalizedId = String(sessionId || "").trim();
    if (!normalizedId) {
      return;
    }
    const knownTitle = String(chatSessions.find((item) => item.id === normalizedId)?.title || "").trim();
    if (knownTitle) {
      setSessionTitleHints((prev) => {
        const currentTitle = String(prev[normalizedId] || "").trim();
        if (currentTitle && currentTitle !== DEFAULT_THREAD_TITLE) {
          return prev;
        }
        if (prev[normalizedId] === knownTitle) {
          return prev;
        }
        return { ...prev, [normalizedId]: knownTitle };
      });
    }
    setOpenThreadTabIds((prev) => (prev.includes(normalizedId) ? prev : [...prev, normalizedId]));
    void onLoadChatSession(normalizedId);
  };

  const handleStartNewThreadTab = () => {
    const currentActiveSessionId = String(activeChatSessionId || "").trim();
    if (currentActiveSessionId) {
      const activeTab = threadTabs.find((tab) => {
        if (tab.kind === "session") {
          return tab.session.id === currentActiveSessionId;
        }
        if (tab.kind === "provisional") {
          return tab.sessionId === currentActiveSessionId;
        }
        return false;
      });
      const activeTitle = activeTab
        ? activeTab.title
        : resolveThreadTitle(currentActiveSessionId, draftThreadTitle);
      setSessionTitleHints((prev) => {
        const nextTitle = String(activeTitle || "").trim() || DEFAULT_THREAD_TITLE;
        const currentTitle = String(prev[currentActiveSessionId] || "").trim();
        if (currentTitle && currentTitle !== DEFAULT_THREAD_TITLE && nextTitle === DEFAULT_THREAD_TITLE) {
          return prev;
        }
        if (prev[currentActiveSessionId] === nextTitle) {
          return prev;
        }
        return { ...prev, [currentActiveSessionId]: nextTitle };
      });
      setOpenThreadTabIds((prev) => (
        prev.includes(currentActiveSessionId) ? prev : [...prev, currentActiveSessionId]
      ));
    }
    setHasDraftThreadTab(true);
    onStartNewChat();
  };

  const handleActivateDraftThreadTab = () => {
    setHasDraftThreadTab(true);
    onActivateDraftChat();
  };

  const handleCloseThreadTab = (tabId: string) => {
    const normalizedId = String(tabId || "").trim();
    if (!normalizedId) {
      return;
    }
    const activeId = String(activeChatSessionId || "").trim();
    const isDraftTab = normalizedId === "__draft__";
    const isActive = isDraftTab ? !activeId : normalizedId === activeId;
    if (isDraftTab) {
      setHasDraftThreadTab(false);
    } else {
      setOpenThreadTabIds((prev) => prev.filter((id) => id !== normalizedId));
      setSessionTitleHints((prev) => {
        if (!(normalizedId in prev)) {
          return prev;
        }
        const copy = { ...prev };
        delete copy[normalizedId];
        return copy;
      });
    }
    if (!isActive) {
      return;
    }
    const activeIndex = threadTabs.findIndex((tab) => tab.id === normalizedId);
    const fallback =
      (activeIndex >= 0 ? threadTabs[activeIndex + 1] : null)
      || (activeIndex > 0 ? threadTabs[activeIndex - 1] : null);
    if (fallback) {
      if (fallback.kind === "draft") {
        handleActivateDraftThreadTab();
      } else {
        handleOpenThreadTab(fallback.kind === "session" ? fallback.session.id : fallback.sessionId);
      }
      return;
    }
    onStartNewChat();
  };

  const handleTabsWheel = (event: WheelEvent<HTMLDivElement>) => {
    const node = event.currentTarget;
    if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) {
      return;
    }
    if (node.scrollWidth <= node.clientWidth) {
      return;
    }
    node.scrollLeft += event.deltaY;
    event.preventDefault();
  };

  return {
    threadTabs,
    handleOpenThreadTab,
    handleStartNewThreadTab,
    handleActivateDraftThreadTab,
    handleCloseThreadTab,
    handleTabsWheel,
  };
}
