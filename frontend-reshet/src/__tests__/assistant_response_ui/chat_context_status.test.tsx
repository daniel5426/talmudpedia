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
  it("renders the input-side context window state", () => {
    render(
      <ChatContextStatus
        contextStatus={{
          source: "estimated",
          model_id: "openai/gpt-5",
          max_tokens: 1_050_000,
          max_tokens_source: "provider_fallback",
          input_tokens: 4_000,
          remaining_tokens: 1_046_000,
          usage_ratio: 4_000 / 1_050_000,
        }}
      />,
    );

    const contextRoot = screen.getByTestId("context-root");
    expect(contextRoot).toHaveAttribute("data-usedtokens", "4000");
    expect(screen.getByText("Context window")).toBeInTheDocument();
    expect(screen.getByText("Estimated input")).toBeInTheDocument();
  });
});
