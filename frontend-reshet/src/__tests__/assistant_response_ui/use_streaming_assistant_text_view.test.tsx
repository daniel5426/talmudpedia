import { act, renderHook } from "@testing-library/react";

import { useStreamingAssistantTextView } from "@/components/ai-elements/useStreamingAssistantTextView";

describe("useStreamingAssistantTextView", () => {
  let timestamp = 0;
  let nextHandle = 1;
  let frameQueue: Array<{ id: number; callback: FrameRequestCallback }> = [];

  beforeEach(() => {
    timestamp = 0;
    nextHandle = 1;
    frameQueue = [];
    Object.assign(globalThis, {
      requestAnimationFrame: (callback: FrameRequestCallback) => {
        const id = nextHandle++;
        frameQueue.push({ id, callback });
        return id;
      },
      cancelAnimationFrame: (id: number) => {
        frameQueue = frameQueue.filter((entry) => entry.id !== id);
      },
    });
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: jest.fn().mockImplementation(() => ({
        matches: false,
        media: "(prefers-reduced-motion: reduce)",
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        addListener: jest.fn(),
        removeListener: jest.fn(),
        onchange: null,
        dispatchEvent: jest.fn(),
      })),
    });
  });

  function flushFrame(stepMs = 16) {
    const frame = frameQueue.shift();
    if (!frame) {
      return;
    }
    timestamp += stepMs;
    act(() => {
      frame.callback(timestamp);
    });
  }

  it("reveals streaming text progressively instead of snapping immediately", () => {
    const { result, rerender } = renderHook(
      ({ isStreaming, streamId, text }) =>
        useStreamingAssistantTextView({ isStreaming, streamId, text }),
      {
        initialProps: {
          isStreaming: true,
          streamId: "assistant-1",
          text: "",
        },
      },
    );

    expect(result.current).toBe("");

    rerender({
      isStreaming: true,
      streamId: "assistant-1",
      text: "Streaming text",
    });

    expect(result.current).toBe("");

    flushFrame();

    expect(result.current.length).toBeGreaterThan(0);
    expect(result.current.length).toBeLessThan("Streaming text".length);
  });

  it("snaps to the full text once streaming completes", () => {
    const { result, rerender } = renderHook(
      ({ isStreaming, streamId, text }) =>
        useStreamingAssistantTextView({ isStreaming, streamId, text }),
      {
        initialProps: {
          isStreaming: true,
          streamId: "assistant-1",
          text: "Streaming text",
        },
      },
    );

    flushFrame();

    rerender({
      isStreaming: false,
      streamId: "assistant-1",
      text: "Streaming text completed",
    });

    expect(result.current).toBe("Streaming text completed");
  });

  it("resets visual pacing for a new streaming segment id", () => {
    const { result, rerender } = renderHook(
      ({ isStreaming, streamId, text }) =>
        useStreamingAssistantTextView({ isStreaming, streamId, text }),
      {
        initialProps: {
          isStreaming: true,
          streamId: "assistant-1",
          text: "First segment",
        },
      },
    );

    flushFrame();
    expect(result.current.length).toBeGreaterThan(0);

    rerender({
      isStreaming: true,
      streamId: "assistant-2",
      text: "Second segment",
    });

    expect(result.current).toBe("");
  });
});
