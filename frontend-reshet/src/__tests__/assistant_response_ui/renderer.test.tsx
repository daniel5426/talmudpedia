import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { AssistantResponseTimeline } from "@/components/ai-elements/assistant-response-timeline";
import type { ChatRenderBlock } from "@/services/chat-presentation";

jest.mock("@/components/ai-elements/message", () => ({
  MessageResponse: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

describe("AssistantResponseTimeline", () => {
  it("renders text, tool blocks, and inline approval actions together", () => {
    const onApprovalAction = jest.fn();
    const blocks: ChatRenderBlock[] = [
      {
        id: "tool-1",
        kind: "tool_call",
        runId: "run-1",
        seq: 1,
        status: "running",
        source: { event: "tool.started", stage: "tool" },
        tool: {
          toolCallId: "call-1",
          toolName: "platform sdk",
          toolSlug: "platform-agents",
          action: "agents.nodes.validate",
          displayName: "Validate agent graph",
          summary: "Validate agent graph against the current contract and return structured validation errors and warnings.",
          title: "Validate agent nodes",
        },
      },
      {
        id: "text-1",
        kind: "assistant_text",
        runId: "run-1",
        seq: 2,
        status: "complete",
        text: "Graph looks valid.",
        source: { event: "assistant.text", stage: "assistant" },
      },
      {
        id: "approval-1",
        kind: "approval_request",
        runId: "run-1",
        seq: 3,
        status: "pending",
        text: "Do you wish to continue?",
        source: { event: "approval.request", stage: "assistant" },
      },
    ];

    render(<AssistantResponseTimeline blocks={blocks} onApprovalAction={onApprovalAction} />);

    expect(screen.getByText("Validate agent nodes")).toBeInTheDocument();
    expect(screen.getByText("Graph looks valid.")).toBeInTheDocument();
    expect(screen.getByText("Do you wish to continue?")).toBeInTheDocument();
    expect(screen.queryByText("Validate agent graph against the current contract and return structured validation errors and warnings.")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /validate agent nodes/i }));
    expect(screen.getByText("Validate agent graph against the current contract and return structured validation errors and warnings.")).toBeInTheDocument();
    expect(screen.getByText("Validate agent nodes").closest("p")?.className || "").toContain("text-transparent");

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onApprovalAction).toHaveBeenCalledWith("approve");
  });

  it("only shimmers the latest active tool row while streaming", () => {
    const blocks: ChatRenderBlock[] = [
      {
        id: "tool-1",
        kind: "tool_call",
        runId: "run-2",
        seq: 1,
        status: "running",
        source: { event: "tool.started", stage: "tool" },
        tool: {
          toolCallId: "call-1",
          toolName: "platform sdk",
          title: "List agent nodes",
        },
      },
      {
        id: "tool-2",
        kind: "tool_call",
        runId: "run-2",
        seq: 2,
        status: "running",
        source: { event: "tool.started", stage: "tool" },
        tool: {
          toolCallId: "call-2",
          toolName: "platform sdk",
          title: "Get agent schemas",
        },
      },
    ];

    const { container } = render(<AssistantResponseTimeline blocks={blocks} isLoading />);

    expect(screen.getByText("List agent nodes").closest("p")?.className || "").not.toContain("text-transparent");
    expect(screen.getByText("Get agent schemas").closest("p")?.className || "").toContain("text-transparent");
    expect(container.querySelectorAll(".text-transparent").length).toBe(1);
  });
});
