import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { AppsBuilderChatPanel } from "@/features/apps-builder/workspace/chat/AppsBuilderChatPanel";
import { AppsBuilderChatTimeline } from "@/features/apps-builder/workspace/chat/AppsBuilderChatTimeline";
import { AppsBuilderVersionHistoryPanel } from "@/features/apps-builder/workspace/chat/AppsBuilderVersionHistoryPanel";
import type { TimelineItem } from "@/features/apps-builder/workspace/chat/chat-model";

jest.mock("@/components/ai-elements/conversation", () => {
  const Context = React.createContext(null);

  function Conversation({ children, className }: { children: React.ReactNode; className?: string }) {
    const scrollRef = React.useRef<HTMLDivElement | null>(null);
    const value = {
      scrollRef,
      scrollToBottom: jest.fn(),
      isAtBottom: true,
    };
    return (
      <Context.Provider value={value}>
        <div role="log" className={className}>
          <div ref={scrollRef} data-testid="mock-scroll-container">
            {children}
          </div>
        </div>
      </Context.Provider>
    );
  }

  function ConversationContent({ children, className }: { children: React.ReactNode; className?: string }) {
    return <div className={className}>{children}</div>;
  }

  function ConversationScrollButton() {
    return null;
  }

  function useStickToBottomContext() {
    const value = React.useContext(Context);
    if (!value) {
      throw new Error("missing conversation context");
    }
    return value;
  }

  return {
    Conversation,
    ConversationContent,
    ConversationScrollButton,
    useStickToBottomContext,
  };
});

jest.mock("@/components/ai-elements/model-selector", () => ({
  ModelSelector: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ModelSelectorContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ModelSelectorEmpty: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ModelSelectorGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ModelSelectorInput: () => <input aria-label="Search models" />,
  ModelSelectorItem: ({ children, onSelect }: { children: React.ReactNode; onSelect?: () => void }) => (
    <button type="button" onClick={onSelect}>{children}</button>
  ),
  ModelSelectorList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ModelSelectorName: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  ModelSelectorTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

jest.mock("@/components/ai-elements/prompt-input", () => ({
  PromptInput: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PromptInputBody: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PromptInputFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PromptInputSubmit: (props: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button type="button" {...props} />,
  PromptInputTextarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} />,
}));

jest.mock("@/components/ai-elements/message", () => ({
  Message: ({ children, className }: { children: React.ReactNode; className?: string }) => <div className={className}>{children}</div>,
  MessageContent: ({ children, className }: { children: React.ReactNode; className?: string }) => <div className={className}>{children}</div>,
  MessageResponse: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

jest.mock("@/components/ai-elements/shimmer", () => ({
  Shimmer: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <span className={`text-transparent ${className || ""}`.trim()}>{children}</span>
  ),
}));

jest.mock("@/components/ai-elements/task", () => ({
  Task: ({ children, className }: { children: React.ReactNode; className?: string }) => <div className={className}>{children}</div>,
  TaskContent: ({ children, className }: { children: React.ReactNode; className?: string }) => <div className={className}>{children}</div>,
  TaskItem: ({ children, className }: { children: React.ReactNode; className?: string }) => <div className={className}>{children}</div>,
  TaskItemFile: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  TaskTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

jest.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

jest.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

function makeTimelineItem(partial: Partial<TimelineItem>): TimelineItem {
  return {
    id: partial.id || "timeline-item",
    kind: partial.kind || "assistant",
    title: partial.title || "Timeline item",
    ...partial,
  };
}

describe("apps builder chat panel behaviors", () => {
  it("does not keep exploration rows shimmering once their tool events are completed", () => {
    const timeline: TimelineItem[] = [
      makeTimelineItem({
        id: "user-1",
        kind: "user",
        title: "User request",
        description: "Inspect the workspace",
      }),
      makeTimelineItem({
        id: "tool-read",
        kind: "tool",
        title: "Reading file",
        toolName: "read_file",
        toolPath: "src/app.tsx",
        toolStatus: "completed",
      }),
      makeTimelineItem({
        id: "tool-search",
        kind: "tool",
        title: "Searching code",
        toolName: "grep",
        toolDetail: "Header",
        toolStatus: "completed",
      }),
    ];

    const { container } = render(
      <AppsBuilderChatTimeline
        timeline={timeline}
        isSending
        activeThinkingSummary=""
        isLoadingOlderHistory={false}
        hasRunningTool={false}
        hasCurrentRunAssistantStream={false}
        lastToolAfterCurrentUserIsExploration
        topSentinelRef={{ current: null }}
      />,
    );

    expect(screen.getByText("Exploring 1 file, 1 search")).toBeInTheDocument();
    expect(container.querySelector(".text-transparent")).not.toBeInTheDocument();
  });

  it("shows the tab-to-chat fade after the conversation scroll container leaves the top", async () => {
    const { container } = render(
      <AppsBuilderChatPanel
        isOpen
        isSending={false}
        isStopping={false}
        timeline={[
          makeTimelineItem({
            id: "assistant-1",
            kind: "assistant",
            title: "Assistant",
            description: "Done",
          }),
        ]}
        activeThinkingSummary=""
        chatSessions={[]}
        activeChatSessionId={null}
        onActivateDraftChat={() => undefined}
        onStartNewChat={() => undefined}
        onOpenHistory={() => undefined}
        onLoadChatSession={async () => undefined}
        onSendMessage={async () => undefined}
        onStopRun={() => undefined}
        chatModels={[]}
        selectedRunModelLabel="Auto"
        isModelSelectorOpen={false}
        onModelSelectorOpenChange={() => undefined}
        onSelectModelId={() => undefined}
        queuedPrompts={[]}
        pendingQuestion={null}
        isAnsweringQuestion={false}
        isSendBlockedBySandbox={false}
        sendBlockedReason={null}
        runningSessionIds={[]}
        sendingSessionIds={[]}
        sessionTitleHintsBySessionId={{}}
        hasOlderHistory={false}
        isLoadingOlderHistory={false}
        onLoadOlderHistory={async () => undefined}
        onRemoveQueuedPrompt={() => undefined}
        onAnswerQuestion={async () => undefined}
        versions={[]}
        selectedVersionId={null}
        selectedVersion={null}
        isLoadingVersions={false}
        isRestoringVersion={false}
        isPublishingVersion={false}
        publishStatus={null}
        onRefreshVersions={() => undefined}
        onSelectVersion={() => undefined}
        onRestoreVersion={() => undefined}
        onPublishVersion={() => undefined}
        onViewCodeVersion={() => undefined}
      />,
    );

    const fade = container.querySelector('[aria-hidden="true"]');
    const scrollContainer = screen.getByTestId("mock-scroll-container");

    expect(fade).toHaveClass("opacity-0");

    Object.defineProperty(scrollContainer, "scrollTop", {
      value: 24,
      writable: true,
      configurable: true,
    });
    fireEvent.scroll(scrollContainer);

    await waitFor(() => {
      expect(fade).toHaveClass("opacity-100");
    });
  });

  it("replaces the tabs row with version history when the versions button is opened", async () => {
    const onRefreshVersions = jest.fn();
    render(
      <AppsBuilderChatPanel
        isOpen
        isSending={false}
        isStopping={false}
        timeline={[]}
        activeThinkingSummary=""
        chatSessions={[]}
        activeChatSessionId={null}
        onActivateDraftChat={() => undefined}
        onStartNewChat={() => undefined}
        onOpenHistory={() => undefined}
        onLoadChatSession={async () => undefined}
        onSendMessage={async () => undefined}
        onStopRun={() => undefined}
        chatModels={[]}
        selectedRunModelLabel="Auto"
        isModelSelectorOpen={false}
        onModelSelectorOpenChange={() => undefined}
        onSelectModelId={() => undefined}
        queuedPrompts={[]}
        pendingQuestion={null}
        isAnsweringQuestion={false}
        isSendBlockedBySandbox={false}
        sendBlockedReason={null}
        runningSessionIds={[]}
        sendingSessionIds={[]}
        sessionTitleHintsBySessionId={{}}
        hasOlderHistory={false}
        isLoadingOlderHistory={false}
        onLoadOlderHistory={async () => undefined}
        onRemoveQueuedPrompt={() => undefined}
        onAnswerQuestion={async () => undefined}
        versions={[]}
        selectedVersionId={null}
        selectedVersion={null}
        isLoadingVersions={false}
        isRestoringVersion={false}
        isPublishingVersion={false}
        publishStatus={null}
        onRefreshVersions={onRefreshVersions}
        onSelectVersion={() => undefined}
        onRestoreVersion={() => undefined}
        onPublishVersion={() => undefined}
        onViewCodeVersion={() => undefined}
      />,
    );

    expect(screen.getByLabelText("Create new chat")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Version history"));

    await waitFor(() => {
      expect(screen.getByText(/version history/i)).toBeInTheDocument();
    });
    expect(screen.queryByLabelText("Create new chat")).not.toBeInTheDocument();
    expect(onRefreshVersions).toHaveBeenCalledTimes(1);
  });

  it("wraps long version titles inside the version card instead of overflowing", () => {
    const longTitle = "Build a very long settings experience with multiple nested sections, forms, validation states, audit logs, billing controls, and deployment notes that should wrap cleanly inside the card";

    render(
      <AppsBuilderVersionHistoryPanel
        versions={[
          {
            id: "version-1",
            version_seq: 1,
            origin_kind: "coding_run",
            run_prompt_preview: longTitle,
            created_at: new Date("2026-03-07T12:00:00Z").toISOString(),
            is_current_draft: false,
          } as never,
        ]}
        selectedVersionId={null}
        selectedVersion={null}
        isLoadingVersions={false}
        isRestoringVersion={false}
        isPublishingVersion={false}
        publishStatus={null}
        onClose={() => undefined}
        onRefreshVersions={() => undefined}
        onSelectVersion={() => undefined}
        onRestoreVersion={() => undefined}
        onPublishVersion={() => undefined}
        onViewCodeVersion={() => undefined}
        onOpenHistory={() => undefined}
      />,
    );

    const title = screen.getByText(longTitle);
    expect(title).toHaveClass("line-clamp-3");
    expect(title).toHaveClass("whitespace-normal");
  });
});
