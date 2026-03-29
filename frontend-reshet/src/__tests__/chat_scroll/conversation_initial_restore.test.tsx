import React from "react";
import { render, screen } from "@testing-library/react";

const stickToBottomMock = jest.fn();

jest.mock("use-stick-to-bottom", () => {
  const React = require("react");

  const StickToBottom = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => {
    stickToBottomMock(props);
    return <div data-testid="stick-to-bottom">{children}</div>;
  };

  StickToBottom.Content = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => (
    <div data-testid="stick-to-bottom-content" {...props}>{children}</div>
  );

  return {
    StickToBottom,
    useStickToBottomContext: () => ({
      isAtBottom: true,
      scrollToBottom: jest.fn(),
    }),
  };
});

import { Conversation } from "@/components/ai-elements/conversation";

describe("Conversation initial restore behavior", () => {
  beforeEach(() => {
    stickToBottomMock.mockClear();
  });

  it("uses instant initial bottom positioning by default", () => {
    render(<Conversation>content</Conversation>);

    expect(screen.getByTestId("stick-to-bottom")).toBeInTheDocument();
    expect(stickToBottomMock).toHaveBeenCalledWith(
      expect.objectContaining({
        initial: "instant",
        resize: "instant",
        role: "log",
      }),
    );
  });

  it("allows explicit auto initial positioning when a surface opts in", () => {
    render(<Conversation initialScrollBehavior="auto">content</Conversation>);

    expect(stickToBottomMock).toHaveBeenCalledWith(
      expect.objectContaining({
        initial: "auto",
      }),
    );
  });

  it("allows explicit auto resize follow mode when a surface opts in", () => {
    render(<Conversation resizeScrollBehavior="auto">content</Conversation>);

    expect(stickToBottomMock).toHaveBeenCalledWith(
      expect.objectContaining({
        resize: "auto",
      }),
    );
  });
});
