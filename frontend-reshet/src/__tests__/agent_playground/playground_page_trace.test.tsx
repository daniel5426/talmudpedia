import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import PlaygroundPage from "@/app/admin/agents/playground/page";
import { agentService } from "@/services";

const mockPush = jest.fn();
const mockReplace = jest.fn();
const mockSearchState = {
  agentId: "agent-1",
  threadId: null as string | null,
};
const mockLoadHistoryChat = jest.fn();
const mockStartNewChat = jest.fn();
const mockControllerState = {
  currentThreadId: null as string | null,
  history: [] as any[],
};

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
  }),
  useSearchParams: () => ({
    get: (key: string) => {
      if (key === "agentId") return mockSearchState.agentId;
      if (key === "threadId") return mockSearchState.threadId;
      return null;
    },
    toString: () =>
      mockSearchState.threadId
        ? `agentId=${mockSearchState.agentId}&threadId=${mockSearchState.threadId}`
        : `agentId=${mockSearchState.agentId}`,
  }),
}));

jest.mock("@/services", () => ({
  agentService: {
    listAgents: jest.fn(),
    getAgent: jest.fn(),
  },
}));

jest.mock("@/hooks/useAgentRunController", () => {
  const React = require("react");

  return {
    useAgentRunController: () => {
      const [executionSteps, setExecutionSteps] = React.useState<any[]>([]);
      return {
        messages: [
          {
            id: "assistant-1",
            role: "assistant",
            content: "Saved answer",
            createdAt: new Date("2026-03-12T10:00:00Z"),
            runId: "run-1",
          },
        ],
        isLoading: false,
        isLoadingHistory: false,
        streamingContent: "",
        currentReasoning: [],
        currentResponseBlocks: [],
        executionSteps,
        executionEvents: [],
        liked: {},
        disliked: {},
        copiedMessageId: null,
        lastThinkingDurationMs: null,
        activeStreamingId: null,
        currentRunId: null,
        currentRunStatus: null,
        currentThreadId: mockControllerState.currentThreadId,
        isPaused: false,
        pendingApproval: false,
        historyLoading: false,
        history: mockControllerState.history,
        traceLoadingByMessageId: {},
        handleSubmit: jest.fn(),
        handleStop: jest.fn(),
        handleCopy: jest.fn(),
        handleLike: jest.fn(),
        handleDislike: jest.fn(),
        handleRetry: jest.fn(),
        handleLoadTrace: jest.fn(async () => {
          setExecutionSteps([
            {
              id: "tool-1",
              name: "Search library",
              type: "tool",
              status: "completed",
              timestamp: new Date("2026-03-12T10:00:01Z"),
            },
          ]);
        }),
        handleSourceClick: jest.fn(),
        upsertLiveVoiceMessage: jest.fn(),
        refresh: jest.fn(),
        textareaRef: { current: null },
        startNewChat: mockStartNewChat,
        loadHistoryChat: mockLoadHistoryChat,
      };
    },
  };
});

jest.mock("@/components/layout/ChatPane", () => ({
  ChatWorkspace: ({ controller }: { controller: any }) => (
    <div>
      {controller.messages.map((message: any) => (
        <div key={message.id}>
          <span>{message.content}</span>
          {message.runId ? (
            <button type="button" onClick={() => controller.handleLoadTrace(message)}>
              Trace
            </button>
          ) : null}
        </div>
      ))}
    </div>
  ),
}));

jest.mock("@/components/ai-elements/conversation", () => ({
  Conversation: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

jest.mock("@/components/direction-provider", () => ({
  useDirection: () => ({ direction: "ltr" }),
}));

jest.mock("@/components/ui/custom-breadcrumb", () => ({
  CustomBreadcrumb: () => <div>Breadcrumb</div>,
}));

jest.mock("@/components/admin/AdminPageHeader", () => ({
  AdminPageHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

jest.mock("@/components/ui/select", () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder}</span>,
}));

jest.mock("@/components/ui/badge", () => ({
  Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));

jest.mock("@/components/ai-elements/ReactArtifactPane", () => ({
  ReactArtifactPane: () => null,
}));

jest.mock("@/lib/react-artifacts/useReactArtifactPanel", () => ({
  useReactArtifactPanel: () => ({
    artifact: null,
    openFromMessage: jest.fn(),
    updateCode: jest.fn(),
    persistCurrent: jest.fn(),
    resetToSaved: jest.fn(),
    closePanel: jest.fn(),
  }),
}));

jest.mock("@/lib/react-artifacts/parseReactArtifact", () => ({
  parseReactArtifact: () => null,
}));

jest.mock("@/contexts/TenantContext", () => ({
  useTenant: () => ({ currentTenant: { slug: "tenant-1" } }),
}));

jest.mock("@/lib/store/useAuthStore", () => ({
  useAuthStore: (selector: (state: any) => any) =>
    selector({ user: { tenant_id: "tenant-1" } }),
}));

jest.mock("@/components/agent-builder/ExecutionHistoryDropdown", () => ({
  ExecutionHistoryDropdown: ({
    historyItems,
    onSelectHistory,
    onStartNewChat,
  }: {
    historyItems: any[];
    onSelectHistory: (item: any) => void;
    onStartNewChat: () => void;
  }) => (
    <div>
      {historyItems.length > 0 ? (
        <button type="button" onClick={() => onSelectHistory(historyItems[0])}>
          History
        </button>
      ) : null}
      <button type="button" onClick={onStartNewChat}>
        New Chat
      </button>
    </div>
  ),
}));

jest.mock("@/components/builder", () => ({
  FloatingPanel: ({ children, visible }: { children: React.ReactNode; visible: boolean }) =>
    visible ? <div data-testid="floating-panel">{children}</div> : null,
}));

jest.mock("@/app/admin/agents/playground/ExecutionSidebar", () => ({
  ExecutionSidebar: ({ steps }: { steps: Array<{ name: string }> }) => (
    <div data-testid="execution-sidebar">
      {steps.map((step) => (
        <div key={step.name}>{step.name}</div>
      ))}
    </div>
  ),
}));

const mockedAgentService = agentService as jest.Mocked<typeof agentService>;

describe("playground trace sidebar", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSearchState.agentId = "agent-1";
    mockSearchState.threadId = null;
    mockControllerState.currentThreadId = null;
    mockControllerState.history = [];
    mockLoadHistoryChat.mockReset();
    mockStartNewChat.mockReset();
    mockLoadHistoryChat.mockImplementation(async (item: any) => item);
    mockedAgentService.listAgents.mockResolvedValue({
      agents: [
        {
          id: "agent-1",
          tenant_id: "tenant-1",
          name: "Test agent",
          slug: "test-agent",
          show_in_playground: true,
          status: "draft",
          version: 1,
          created_at: "2026-03-12T10:00:00Z",
          updated_at: "2026-03-12T10:00:00Z",
        },
      ],
      total: 1,
    });
    mockedAgentService.getAgent.mockResolvedValue({
      id: "agent-1",
      tenant_id: "tenant-1",
      name: "Test agent",
      slug: "test-agent",
      show_in_playground: true,
      status: "draft",
      version: 1,
      created_at: "2026-03-12T10:00:00Z",
      updated_at: "2026-03-12T10:00:00Z",
    } as any);
  });

  it("opens the sidebar and keeps the assistant message content when trace is clicked", async () => {
    render(<PlaygroundPage />);

    expect(screen.queryByTestId("execution-sidebar")).not.toBeInTheDocument();
    expect(await screen.findByText("Saved answer")).toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: "Trace" }));

    await waitFor(() => {
      expect(screen.getByTestId("execution-sidebar")).toBeInTheDocument();
    });

    expect(screen.getByText("Search library")).toBeInTheDocument();
    expect(screen.getByText("Saved answer")).toBeInTheDocument();
  });

  it("filters hidden agents out of the selector bootstrap redirect", async () => {
    mockSearchState.agentId = null as unknown as string;
    mockedAgentService.listAgents.mockResolvedValue({
      agents: [
        {
          id: "agent-hidden",
          tenant_id: "tenant-1",
          name: "Hidden agent",
          slug: "hidden-agent",
          show_in_playground: false,
          status: "draft",
          version: 1,
          created_at: "2026-03-12T10:00:00Z",
          updated_at: "2026-03-12T10:00:00Z",
        },
        {
          id: "agent-visible",
          tenant_id: "tenant-1",
          name: "Visible agent",
          slug: "visible-agent",
          show_in_playground: true,
          status: "draft",
          version: 1,
          created_at: "2026-03-12T10:00:00Z",
          updated_at: "2026-03-12T10:00:00Z",
        },
      ],
      total: 2,
    } as any);

    render(<PlaygroundPage />);

    await waitFor(() => {
      expect(
        mockReplace.mock.calls.some(
          ([path, options]) =>
            path === "/admin/agents/playground?agentId=agent-visible"
            && JSON.stringify(options) === JSON.stringify({ scroll: false }),
        ),
      ).toBe(true);
    });
  });

  it("redirects away from a hidden agent deep link to the first visible agent", async () => {
    mockedAgentService.listAgents.mockResolvedValue({
      agents: [
        {
          id: "agent-hidden",
          tenant_id: "tenant-1",
          name: "Hidden agent",
          slug: "hidden-agent",
          show_in_playground: false,
          status: "draft",
          version: 1,
          created_at: "2026-03-12T10:00:00Z",
          updated_at: "2026-03-12T10:00:00Z",
        },
        {
          id: "agent-visible",
          tenant_id: "tenant-1",
          name: "Visible agent",
          slug: "visible-agent",
          show_in_playground: true,
          status: "draft",
          version: 1,
          created_at: "2026-03-12T10:00:00Z",
          updated_at: "2026-03-12T10:00:00Z",
        },
      ],
      total: 2,
    } as any);
    mockedAgentService.getAgent.mockResolvedValue({
      id: "agent-hidden",
      tenant_id: "tenant-1",
      name: "Hidden agent",
      slug: "hidden-agent",
      show_in_playground: false,
      status: "draft",
      version: 1,
      created_at: "2026-03-12T10:00:00Z",
      updated_at: "2026-03-12T10:00:00Z",
    } as any);

    render(<PlaygroundPage />);

    await waitFor(() => {
      expect(
        mockReplace.mock.calls.some(
          ([path, options]) =>
            path === "/admin/agents/playground?agentId=agent-visible"
            && JSON.stringify(options) === JSON.stringify({ scroll: false }),
        ),
      ).toBe(true);
    });
  });

  it("syncs the active thread id into the URL for reload persistence", async () => {
    mockControllerState.currentThreadId = "thread-live-1";

    render(<PlaygroundPage />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith(
        "/admin/agents/playground?agentId=agent-1&threadId=thread-live-1",
        { scroll: false },
      );
    });
  });

  it("keeps the same-agent thread id in the URL when history is selected", async () => {
    mockControllerState.history = [
      {
        id: "thread-1",
        threadId: "thread-1",
        agentId: "agent-1",
        title: "Thread 1",
        timestamp: 1,
        messages: [],
      },
    ];
    mockLoadHistoryChat.mockResolvedValue(mockControllerState.history[0]);

    render(<PlaygroundPage />);

    fireEvent.click(await screen.findByRole("button", { name: "History" }));

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith(
        "/admin/agents/playground?agentId=agent-1&threadId=thread-1",
        { scroll: false },
      );
    });
  });

  it("does not strip threadId from the URL after loading a thread from the URL", async () => {
    mockSearchState.threadId = "thread-1";
    mockControllerState.history = [
      {
        id: "thread-1",
        threadId: "thread-1",
        agentId: "agent-1",
        title: "Thread 1",
        timestamp: 1,
        messages: [],
      },
    ];
    mockLoadHistoryChat.mockResolvedValue(mockControllerState.history[0]);

    render(<PlaygroundPage />);

    await waitFor(() => {
      expect(mockLoadHistoryChat).toHaveBeenCalledWith(mockControllerState.history[0]);
    });

    expect(mockReplace).not.toHaveBeenCalledWith(
      "/admin/agents/playground?agentId=agent-1",
      { scroll: false },
    );
  });

  it("clears the thread id from the URL when new chat is started from history controls", async () => {
    mockSearchState.threadId = "thread-old";
    mockControllerState.currentThreadId = "thread-old";
    mockControllerState.history = [
      {
        id: "thread-old",
        threadId: "thread-old",
        agentId: "agent-1",
        title: "Thread old",
        timestamp: 1,
        messages: [],
      },
    ];

    render(<PlaygroundPage />);

    fireEvent.click(await screen.findByRole("button", { name: "New Chat" }));

    await waitFor(() => {
      expect(mockStartNewChat).toHaveBeenCalled();
      expect(mockReplace).toHaveBeenCalledWith(
        "/admin/agents/playground?agentId=agent-1",
        { scroll: false },
      );
    });

    expect(mockReplace).not.toHaveBeenCalledWith(
      "/admin/agents/playground?agentId=agent-1&threadId=thread-old",
      { scroll: false },
    );
    expect(mockLoadHistoryChat).not.toHaveBeenCalledWith(mockControllerState.history[0]);
  });
});
