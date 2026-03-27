import React from "react"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import AdminThreadPage from "@/app/admin/threads/[threadId]/page"
import { adminService } from "@/services"
import { mapTurnsToMessages } from "@/hooks/useAgentThreadHistory"
import { loadRunTraceInspection } from "@/services/run-trace-steps"

const mockParams = { threadId: "thread-1" }

jest.mock("next/navigation", () => ({
  useParams: () => mockParams,
}))

jest.mock("@/services", () => ({
  adminService: {
    getThread: jest.fn(),
  },
}))

jest.mock("@/hooks/useAgentThreadHistory", () => ({
  mapTurnsToMessages: jest.fn(),
}))

jest.mock("@/services/run-trace-steps", () => ({
  loadRunTraceInspection: jest.fn(),
}))

jest.mock("@/components/direction-provider", () => ({
  useDirection: () => ({ direction: "ltr" }),
}))

jest.mock("@/components/admin/AdminPageHeader", () => ({
  AdminPageHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

jest.mock("@/components/ui/custom-breadcrumb", () => ({
  CustomBreadcrumb: ({ items }: { items: Array<{ label: string }> }) => <div>{items.map((item) => item.label).join(" / ")}</div>,
}))

jest.mock("@/components/ai-elements/conversation", () => ({
  Conversation: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

jest.mock("@/components/layout/ChatPane", () => ({
  ChatWorkspace: ({
    controller,
    hideInputArea,
    hideRetryAction,
  }: {
    controller: any
    hideInputArea?: boolean
    hideRetryAction?: boolean
  }) => (
    <div>
      <div data-testid="workspace-flags">
        {String(Boolean(hideInputArea))}:{String(Boolean(hideRetryAction))}
      </div>
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
}))

jest.mock("@/components/builder", () => ({
  FloatingPanel: ({
    children,
    visible,
  }: {
    children: React.ReactNode
    visible: boolean
  }) => (visible ? <div data-testid="floating-panel">{children}</div> : null),
}))

jest.mock("@/app/admin/agents/playground/ExecutionSidebar", () => ({
  ExecutionSidebar: ({ steps, copyText }: { steps: Array<{ name: string }>; copyText?: string | null }) => (
    <div data-testid="execution-sidebar">
      {copyText ? <button type="button">Copy full trace</button> : null}
      {steps.map((step) => (
        <div key={step.name}>{step.name}</div>
      ))}
    </div>
  ),
}))

const mockedAdminService = adminService as jest.Mocked<typeof adminService>
const mockedMapTurnsToMessages = mapTurnsToMessages as jest.MockedFunction<typeof mapTurnsToMessages>
const mockedLoadRunTraceInspection = loadRunTraceInspection as jest.MockedFunction<typeof loadRunTraceInspection>

describe("admin thread page", () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockedAdminService.getThread.mockResolvedValue({
      id: "thread-1",
      title: "Saved playground thread",
      status: "active",
      agent_id: "agent-1",
      agent_name: "PRICO Demo Agent",
      actor_id: "actor-1",
      token_usage: {
        total_tokens: 12430,
      },
      turns: [],
    } as any)
    mockedMapTurnsToMessages.mockResolvedValue([
      {
        id: "assistant-1",
        role: "assistant",
        content: "Saved answer",
        createdAt: new Date("2026-03-22T10:00:00Z"),
        runId: "run-1",
      },
    ])
    mockedLoadRunTraceInspection.mockResolvedValue({
      response: {
        run_id: "run-1",
        event_count: 1,
        events: [{ event: "tool.failed" }],
      },
      serialized: JSON.stringify({ run_id: "run-1", event_count: 1, events: [{ event: "tool.failed" }] }, null, 2),
      steps: [
        {
          id: "step-1",
          name: "Search library",
          type: "tool",
          status: "completed",
          timestamp: new Date("2026-03-22T10:00:01Z"),
        },
      ],
    })
  })

  it("renders a read-only playground-style thread view with inline header metadata and trace toggle", async () => {
    render(<AdminThreadPage />)

    await screen.findByText("Saved answer")
    expect(screen.getByTestId("workspace-flags")).toHaveTextContent("true:true")
    expect(screen.queryByText("Agent")).not.toBeInTheDocument()
    expect(screen.queryByText("Actor")).not.toBeInTheDocument()
    expect(screen.queryByText("Status")).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: "PRICO Demo Agent" })).toHaveAttribute("href", "/admin/agents/agent-1/builder")
    expect(screen.getByRole("link", { name: "actor-1" })).toHaveAttribute("href", "/admin/users/actor-1")
    expect(screen.getByText("12,430 tokens")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Trace" }))

    await waitFor(() => {
      expect(mockedLoadRunTraceInspection).toHaveBeenCalledWith("run-1")
      expect(screen.getByTestId("floating-panel")).toBeInTheDocument()
      expect(screen.getByText("Search library")).toBeInTheDocument()
      expect(screen.getByRole("button", { name: "Copy full trace" })).toBeInTheDocument()
    })
  })
})
