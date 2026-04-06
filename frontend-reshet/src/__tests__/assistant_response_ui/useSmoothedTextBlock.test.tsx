import { act, renderHook } from "@testing-library/react";

import { useSmoothedTextBlock } from "@/hooks/useSmoothedTextBlock";

describe("useSmoothedTextBlock", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.spyOn(window, "requestAnimationFrame").mockImplementation((callback: FrameRequestCallback) => {
      return window.setTimeout(() => callback(performance.now()), 16);
    });
    jest.spyOn(window, "cancelAnimationFrame").mockImplementation((handle: number) => {
      window.clearTimeout(handle);
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  it("keeps draining after streaming completes instead of snapping to the final text", () => {
    const { result, rerender } = renderHook(
      ({ blockId, text, isStreaming, animateOnMount }) =>
        useSmoothedTextBlock(blockId, text, isStreaming, { animateOnMount }),
      {
        initialProps: {
          blockId: "block-1",
          text: "Hello world",
          isStreaming: true,
          animateOnMount: false,
        },
      },
    );

    act(() => {
      rerender({
        blockId: "block-1",
        text: "Hello world",
        isStreaming: false,
        animateOnMount: false,
      });
    });

    expect(result.current).not.toBe("Hello world");
    expect(result.current.length).toBeGreaterThanOrEqual(0);

    act(() => {
      jest.advanceTimersByTime(400);
    });

    expect(result.current).toBe("Hello world");
  });

  it("can animate a just-finished block on first mount", () => {
    const { result } = renderHook(() =>
      useSmoothedTextBlock("block-2", "Fast final response", false, {
        animateOnMount: true,
      }),
    );

    expect(result.current).toBe("");

    act(() => {
      jest.advanceTimersByTime(500);
    });

    expect(result.current).toBe("Fast final response");
  });
});
