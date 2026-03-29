import React from "react";
import { render, screen } from "@testing-library/react";

import { ChatContextStatus } from "@/components/ai-elements/chat-context-status";

jest.mock("@/components/ai-elements/context", () => ({
  Context: ({
    children,
    usedTokens,
    maxTokens,
  }: {
    children: React.ReactNode;
    usedTokens: number;
    maxTokens: number;
  }) => (
    <div data-testid="context-root" data-usedtokens={usedTokens} data-maxtokens={maxTokens}>
      {children}
    </div>
  ),
  ContextTrigger: () => <div>trigger</div>,
  ContextContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ContextContentHeader: () => <div>header</div>,
  ContextContentBody: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ContextContentFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

describe("ChatContextStatus", () => {
  it("keeps the context meter on estimated context size after actual usage arrives", () => {
    render(
      <ChatContextStatus
        contextStatus={{
          model_id: "openai/gpt-5",
          max_tokens: 1_050_000,
          max_tokens_source: "provider_fallback",
          reserved_output_tokens: 8_192,
          estimated_input_tokens: 4_000,
          estimated_total_tokens: 12_192,
          estimated_remaining_tokens: 1_037_808,
          estimated_usage_ratio: 0.0116,
          near_limit: false,
          compaction_recommended: false,
          source: "estimated_plus_actual",
          actual_usage: {
            input_tokens: 4_100,
            output_tokens: 700,
            total_tokens: 4_800,
          },
        }}
      />,
    );

    const contextRoot = screen.getByTestId("context-root");
    expect(contextRoot).toHaveAttribute("data-usedtokens", "12192");
    expect(screen.getByText("Context estimate")).toBeInTheDocument();
  });
});
