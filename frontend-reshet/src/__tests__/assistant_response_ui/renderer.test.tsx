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

    expect(container.querySelectorAll(".text-transparent").length).toBe(1);
  });

  it("shows a hover redirect for thread-backed tool calls", () => {
    const blocks: ChatRenderBlock[] = [
      {
        id: "tool-redirect",
        kind: "tool_call",
        runId: "run-3",
        seq: 1,
        status: "complete",
        source: { event: "tool.completed", stage: "tool" },
        tool: {
          toolCallId: "call-redirect",
          toolName: "agent_call",
          title: "Artifact Worker",
          threadId: "thread-child-1",
        },
      },
    ];

    render(
      <AssistantResponseTimeline
        blocks={blocks}
        getToolHref={(block) => block.tool.threadId ? `/admin/threads/${block.tool.threadId}` : null}
      />,
    );

    expect(screen.getByRole("link", { name: "Open thread for Artifact Worker" })).toHaveAttribute(
      "href",
      "/admin/threads/thread-child-1",
    );
  });

  it("renders live assistant text immediately while a run is still streaming", () => {
    const blocks: ChatRenderBlock[] = [
      {
        id: "text-live",
        kind: "assistant_text",
        runId: "run-live",
        seq: 1,
        status: "streaming",
        text: "Streaming now",
        source: { event: "assistant.delta", stage: "assistant" },
      },
    ];

    render(<AssistantResponseTimeline blocks={blocks} isLoading />);

    expect(screen.getByText("Streaming now")).toBeInTheDocument();
  });

  it("renders completed assistant text on the non-streaming branch", () => {
    const blocks: ChatRenderBlock[] = [
      {
        id: "text-complete",
        kind: "assistant_text",
        runId: "run-complete",
        seq: 1,
        status: "complete",
        text: "**Done**",
        source: { event: "assistant.text", stage: "assistant" },
      },
    ];

    render(<AssistantResponseTimeline blocks={blocks} />);

    expect(screen.getByText("**Done**")).toBeInTheDocument();
  });
});
