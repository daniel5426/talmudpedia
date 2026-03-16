import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { PreviewCanvas } from "@/features/apps-builder/preview/PreviewCanvas";

describe("PreviewCanvas auth channel", () => {
  it("posts preview auth token on load and token refresh", async () => {
    jest.useFakeTimers();
    try {
      const { rerender } = render(
        <PreviewCanvas
          previewUrl="https://preview.local/sandbox/session-1/"
          previewAuthToken="preview-auth-token-1"
          devStatus="running"
          devError={null}
        />,
      );

      const frame = await screen.findByTestId("preview-iframe");
      const postMessage = jest.fn();
      Object.defineProperty(frame, "contentWindow", {
        configurable: true,
        value: { postMessage },
      });

      fireEvent.load(frame);
      await act(async () => {
        jest.advanceTimersByTime(600);
      });

      await waitFor(() => {
        expect(postMessage).toHaveBeenCalledWith(
          expect.objectContaining({
            type: "talmudpedia.preview-auth.v1",
            token: "preview-auth-token-1",
          }),
          "https://preview.local",
        );
      });

      rerender(
        <PreviewCanvas
          previewUrl="https://preview.local/sandbox/session-1/"
          previewAuthToken="preview-auth-token-2"
          devStatus="running"
          devError={null}
        />,
      );

      await act(async () => {
        jest.advanceTimersByTime(250);
      });

      await waitFor(() => {
        expect(postMessage).toHaveBeenCalledWith(
          expect.objectContaining({
            type: "talmudpedia.preview-auth.v1",
            token: "preview-auth-token-2",
          }),
          "https://preview.local",
        );
      });
    } finally {
      jest.useRealTimers();
    }
  });

  it("keeps iframe src stable when only the preview auth token rotates", async () => {
    const { rerender } = render(
      <PreviewCanvas
        previewUrl="https://preview.local/sandbox/session-1/"
        previewAuthToken="preview-auth-token-1"
        devStatus="running"
        devError={null}
      />,
    );

    const frame = await screen.findByTestId("preview-iframe");
    const initialSrc = frame.getAttribute("src");
    expect(initialSrc).toContain("runtime_token=preview-auth-token-1");

    rerender(
      <PreviewCanvas
        previewUrl="https://preview.local/sandbox/session-1/"
        previewAuthToken="preview-auth-token-2"
        devStatus="running"
        devError={null}
      />,
    );

    expect(frame.getAttribute("src")).toBe(initialSrc);
  });
});
