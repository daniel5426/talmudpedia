import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import PlaygroundPage from "@/app/admin/agents/playground/page";
import { agentService } from "@/services";

const mockPush = jest.fn();
const mockReplace = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
  }),
  useSearchParams: () => ({
    get: (key: string) => {
      if (key === "agentId") return "agent-1";
      return null;
    },
    toString: () => "agentId=agent-1",
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
        isPaused: false,
        pendingApproval: false,
        historyLoading: false,
        history: [],
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
        startNewChat: jest.fn(),
        loadHistoryChat: jest.fn(),
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
  ExecutionHistoryDropdown: () => null,
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
    mockedAgentService.listAgents.mockResolvedValue({
      agents: [
        {
          id: "agent-1",
          tenant_id: "tenant-1",
          name: "Test agent",
          slug: "test-agent",
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
});
