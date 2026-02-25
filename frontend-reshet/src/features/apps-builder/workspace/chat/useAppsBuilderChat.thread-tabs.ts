import { useEffect, useMemo, useState, type WheelEvent } from "react";

import type { CodingAgentChatSession } from "@/services";

import type { TimelineItem } from "./chat-model";
import { isUserTimelineItem } from "./chat-model";

export type ThreadTab =
  | {
    id: string;
    kind: "session";
    session: CodingAgentChatSession;
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
  timeline: TimelineItem[];
  onActivateDraftChat: () => void;
  onLoadChatSession: (sessionId: string) => Promise<void>;
  onStartNewChat: () => void;
};

export function useAppsBuilderChatThreadTabs({
  chatSessions,
  activeChatSessionId,
  timeline,
  onActivateDraftChat,
  onLoadChatSession,
  onStartNewChat,
}: UseAppsBuilderChatThreadTabsOptions) {
  const [openThreadTabIds, setOpenThreadTabIds] = useState<string[]>([]);
  const [hasDraftThreadTab, setHasDraftThreadTab] = useState(false);
  const [sessionTitleHints, setSessionTitleHints] = useState<Record<string, string>>({});

  useEffect(() => {
    const normalizedActiveId = String(activeChatSessionId || "").trim();
    if (!normalizedActiveId) return;
    setOpenThreadTabIds((prev) => (prev.includes(normalizedActiveId) ? prev : [...prev, normalizedActiveId]));
  }, [activeChatSessionId]);

  const draftThreadTitle = useMemo(() => {
    const lastUserPrompt = [...timeline]
      .reverse()
      .find((item) => isUserTimelineItem(item) && String(item.description || "").trim().length > 0);
    const raw = String(lastUserPrompt?.description || "").trim();
    if (!raw) {
      return "New chat";
    }
    const collapsed = raw.split(/\s+/).join(" ").trim();
    if (!collapsed) {
      return "New chat";
    }
    return collapsed.length <= 80 ? collapsed : `${collapsed.slice(0, 77).trimEnd()}...`;
  }, [timeline]);

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
        tabs.push({
          id: session.id,
          kind: "session",
          session,
        });
        seen.add(session.id);
        continue;
      }
      tabs.push({
        id: sessionId,
        kind: "provisional",
        sessionId,
        title: String(sessionTitleHints[sessionId] || "").trim() || "New chat",
      });
      seen.add(sessionId);
    }

    if (activeId && !seen.has(activeId)) {
      const activeSession = byId.get(activeId);
      if (activeSession) {
        tabs.push({
          id: activeSession.id,
          kind: "session",
          session: activeSession,
        });
        seen.add(activeSession.id);
      } else if (hasDraftThreadTab) {
        tabs.push({
          id: activeId,
          kind: "provisional",
          sessionId: activeId,
          title: String(sessionTitleHints[activeId] || "").trim() || draftThreadTitle,
        });
        seen.add(activeId);
      }
    }

    if (hasDraftThreadTab) {
      tabs.push({
        id: "__draft__",
        kind: "draft",
        title: draftThreadTitle,
      });
    }
    return tabs;
  }, [activeChatSessionId, chatSessions, draftThreadTitle, hasDraftThreadTab, openThreadTabIds, sessionTitleHints]);

  const handleOpenThreadTab = (sessionId: string) => {
    const normalizedId = String(sessionId || "").trim();
    if (!normalizedId) {
      return;
    }
    const knownTitle = String(chatSessions.find((item) => item.id === normalizedId)?.title || "").trim();
    if (knownTitle) {
      setSessionTitleHints((prev) => {
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
        ? activeTab.kind === "session"
          ? activeTab.session.title
          : activeTab.title
        : draftThreadTitle;
      setSessionTitleHints((prev) => {
        const nextTitle = String(activeTitle || "").trim() || "New chat";
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
