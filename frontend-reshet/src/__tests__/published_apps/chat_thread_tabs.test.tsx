import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { CodingAgentChatSession } from "@/services";
import type { TimelineItem } from "@/features/apps-builder/workspace/chat/chat-model";
import { useAppsBuilderChatThreadTabs } from "@/features/apps-builder/workspace/chat/useAppsBuilderChat.thread-tabs";

type HarnessProps = {
  chatSessions: CodingAgentChatSession[];
  activeChatSessionId: string | null;
  runningSessionIds: string[];
  timeline: TimelineItem[];
  sessionTitleHintsBySessionId?: Record<string, string>;
  onStartNewChat: () => void;
};

function ThreadTabsHarness({
  chatSessions,
  activeChatSessionId,
  runningSessionIds,
  timeline,
  sessionTitleHintsBySessionId,
  onStartNewChat,
}: HarnessProps) {
  const {
    threadTabs,
    handleStartNewThreadTab,
  } = useAppsBuilderChatThreadTabs({
    chatSessions,
    activeChatSessionId,
    runningSessionIds,
    timeline,
    sessionTitleHintsBySessionId,
    onActivateDraftChat: () => undefined,
    onLoadChatSession: async () => undefined,
    onStartNewChat,
  });

  return (
    <div>
      <button type="button" onClick={handleStartNewThreadTab}>
        Start new chat
      </button>
      <ul>
        {threadTabs.map((tab) => {
          const tabSessionId = tab.kind === "session"
            ? tab.session.id
            : tab.kind === "provisional"
              ? tab.sessionId
              : "__draft__";
          const tabTitle = tab.title;
          return (
            <li key={tab.id} data-testid={`tab-${tabSessionId}`}>
              {`${tabSessionId}:${tabTitle}`}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function makeSession(id: string, title: string): CodingAgentChatSession {
  const now = new Date().toISOString();
  return {
    id,
    title,
    created_at: now,
    updated_at: now,
    last_message_at: now,
  };
}

describe("chat thread tabs", () => {
  it("keeps provisional session title stable when switching away during session-list lag", async () => {
    const onStartNewChat = jest.fn();
    const promptTitle = "Build a payments settings panel";
    const localRunningId = "__local__:msg-1";
    const draftTimeline: TimelineItem[] = [
      {
        id: "u-1",
        kind: "user",
        title: "User request",
        description: promptTitle,
      } as TimelineItem,
    ];

    const { rerender } = render(
      <ThreadTabsHarness
        chatSessions={[makeSession("chat-legacy", "Legacy thread")]}
        activeChatSessionId="chat-legacy"
        runningSessionIds={[]}
        timeline={[]}
        sessionTitleHintsBySessionId={{}}
        onStartNewChat={onStartNewChat}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Start new chat" }));
    expect(onStartNewChat).toHaveBeenCalledTimes(1);

    rerender(
      <ThreadTabsHarness
        chatSessions={[makeSession("chat-legacy", "Legacy thread")]}
        activeChatSessionId={null}
        runningSessionIds={[]}
        timeline={draftTimeline}
        sessionTitleHintsBySessionId={{}}
        onStartNewChat={onStartNewChat}
      />,
    );

    rerender(
      <ThreadTabsHarness
        chatSessions={[makeSession("chat-legacy", "Legacy thread")]}
        activeChatSessionId={localRunningId}
        runningSessionIds={[localRunningId]}
        timeline={[]}
        sessionTitleHintsBySessionId={{ [localRunningId]: promptTitle }}
        onStartNewChat={onStartNewChat}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId(`tab-${localRunningId}`)).toHaveTextContent(`${localRunningId}:${promptTitle}`);
    });
    expect(screen.queryByTestId("tab-__draft__")).not.toBeInTheDocument();

    rerender(
      <ThreadTabsHarness
        chatSessions={[makeSession("chat-legacy", "Legacy thread")]}
        activeChatSessionId="chat-legacy"
        runningSessionIds={[localRunningId]}
        timeline={[]}
        sessionTitleHintsBySessionId={{ [localRunningId]: promptTitle }}
        onStartNewChat={onStartNewChat}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId(`tab-${localRunningId}`)).toHaveTextContent(`${localRunningId}:${promptTitle}`);
    });

    rerender(
      <ThreadTabsHarness
        chatSessions={[
          makeSession("chat-legacy", "Legacy thread"),
          makeSession("chat-running", promptTitle),
        ]}
        activeChatSessionId="chat-legacy"
        runningSessionIds={["chat-running"]}
        timeline={[]}
        sessionTitleHintsBySessionId={{ "chat-running": promptTitle }}
        onStartNewChat={onStartNewChat}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("tab-chat-running")).toHaveTextContent(`chat-running:${promptTitle}`);
    });
    expect(screen.getByTestId("tab-chat-legacy")).toHaveTextContent("chat-legacy:Legacy thread");
    expect(screen.getByTestId("tab-chat-running")).not.toHaveTextContent("chat-running:New chat");
  });

  it("does not auto-create a new draft tab after draft migrates to a real session", async () => {
    const onStartNewChat = jest.fn();
    const promptTitle = "Build a payments settings panel";
    const localRunningId = "__local__:msg-2";
    const draftTimeline: TimelineItem[] = [
      {
        id: "u-1",
        kind: "user",
        title: "User request",
        description: promptTitle,
      } as TimelineItem,
    ];

    const { rerender } = render(
      <ThreadTabsHarness
        chatSessions={[makeSession("chat-legacy", "Legacy thread")]}
        activeChatSessionId="chat-legacy"
        runningSessionIds={[]}
        timeline={[]}
        sessionTitleHintsBySessionId={{}}
        onStartNewChat={onStartNewChat}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Start new chat" }));

    rerender(
      <ThreadTabsHarness
        chatSessions={[makeSession("chat-legacy", "Legacy thread")]}
        activeChatSessionId={null}
        runningSessionIds={[]}
        timeline={draftTimeline}
        sessionTitleHintsBySessionId={{}}
        onStartNewChat={onStartNewChat}
      />,
    );

    rerender(
      <ThreadTabsHarness
        chatSessions={[makeSession("chat-legacy", "Legacy thread")]}
        activeChatSessionId={localRunningId}
        runningSessionIds={[localRunningId]}
        timeline={draftTimeline}
        sessionTitleHintsBySessionId={{ [localRunningId]: promptTitle }}
        onStartNewChat={onStartNewChat}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId(`tab-${localRunningId}`)).toHaveTextContent(`${localRunningId}:${promptTitle}`);
    });
    expect(screen.queryByTestId("tab-__draft__")).not.toBeInTheDocument();

    rerender(
      <ThreadTabsHarness
        chatSessions={[
          makeSession("chat-legacy", "Legacy thread"),
          makeSession("chat-running", promptTitle),
        ]}
        activeChatSessionId="chat-running"
        runningSessionIds={[]}
        timeline={draftTimeline}
        sessionTitleHintsBySessionId={{ "chat-running": promptTitle }}
        onStartNewChat={onStartNewChat}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("tab-chat-running")).toHaveTextContent(`chat-running:${promptTitle}`);
    });
    expect(screen.queryByTestId("tab-__draft__")).not.toBeInTheDocument();
  });

  it("keeps each sending local tab title stable when switching between two local sending tabs", async () => {
    const onStartNewChat = jest.fn();
    const promptOne = "Wire auth guard";
    const promptTwo = "Add usage analytics";
    const localOne = "__local__:msg-1";
    const localTwo = "__local__:msg-2";

    const { rerender } = render(
      <ThreadTabsHarness
        chatSessions={[]}
        activeChatSessionId={localOne}
        runningSessionIds={[localOne, localTwo]}
        timeline={[]}
        sessionTitleHintsBySessionId={{
          [localOne]: promptOne,
          [localTwo]: promptTwo,
        }}
        onStartNewChat={onStartNewChat}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId(`tab-${localOne}`)).toHaveTextContent(`${localOne}:${promptOne}`);
      expect(screen.getByTestId(`tab-${localTwo}`)).toHaveTextContent(`${localTwo}:${promptTwo}`);
    });

    rerender(
      <ThreadTabsHarness
        chatSessions={[]}
        activeChatSessionId={localTwo}
        runningSessionIds={[localOne, localTwo]}
        timeline={[]}
        sessionTitleHintsBySessionId={{
          [localOne]: promptOne,
          [localTwo]: promptTwo,
        }}
        onStartNewChat={onStartNewChat}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId(`tab-${localOne}`)).toHaveTextContent(`${localOne}:${promptOne}`);
      expect(screen.getByTestId(`tab-${localTwo}`)).toHaveTextContent(`${localTwo}:${promptTwo}`);
    });
  });
});
