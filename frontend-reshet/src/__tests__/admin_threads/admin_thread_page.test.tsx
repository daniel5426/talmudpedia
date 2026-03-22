import React from "react"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import AdminThreadPage from "@/app/admin/threads/[threadId]/page"
import { adminService } from "@/services"
import { mapTurnsToMessages } from "@/hooks/useAgentThreadHistory"
import { buildExecutionStepsFromRunTrace } from "@/services/run-trace-steps"

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
  buildExecutionStepsFromRunTrace: jest.fn(),
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
  ExecutionSidebar: ({ steps }: { steps: Array<{ name: string }> }) => (
    <div data-testid="execution-sidebar">
      {steps.map((step) => (
        <div key={step.name}>{step.name}</div>
      ))}
    </div>
  ),
}))

const mockedAdminService = adminService as jest.Mocked<typeof adminService>
const mockedMapTurnsToMessages = mapTurnsToMessages as jest.MockedFunction<typeof mapTurnsToMessages>
const mockedBuildExecutionStepsFromRunTrace = buildExecutionStepsFromRunTrace as jest.MockedFunction<typeof buildExecutionStepsFromRunTrace>

describe("admin thread page", () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockedAdminService.getThread.mockResolvedValue({
      id: "thread-1",
      title: "Saved playground thread",
      status: "active",
      agent_name: "PRICO Demo Agent",
      actor_id: "actor-1",
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
    mockedBuildExecutionStepsFromRunTrace.mockResolvedValue([
      {
        id: "step-1",
        name: "Search library",
        type: "tool",
        status: "completed",
        timestamp: new Date("2026-03-22T10:00:01Z"),
      },
    ])
  })

  it("renders a read-only playground-style thread view with inline header metadata and trace toggle", async () => {
    render(<AdminThreadPage />)

    await screen.findByText("Saved answer")
    expect(screen.getByTestId("workspace-flags")).toHaveTextContent("true:true")
    expect(screen.getByText("PRICO Demo Agent")).toBeInTheDocument()
    expect(screen.getByText("actor-1")).toBeInTheDocument()
    expect(screen.getByText("active")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Trace" }))

    await waitFor(() => {
      expect(mockedBuildExecutionStepsFromRunTrace).toHaveBeenCalledWith("run-1")
      expect(screen.getByTestId("floating-panel")).toBeInTheDocument()
      expect(screen.getByText("Search library")).toBeInTheDocument()
    })
  })
})
