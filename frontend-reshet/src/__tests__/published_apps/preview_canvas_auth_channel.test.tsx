import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { PreviewCanvas } from "@/features/apps-builder/preview/PreviewCanvas";

describe("PreviewCanvas transport behavior", () => {
  it("posts proxy-only preview auth bridge messages on load and route changes", async () => {
    const { rerender } = render(
      <PreviewCanvas
        previewUrl="https://preview.local/sandbox/session-1/"
        transportKey="session-1:1"
        transportStatus="ready"
      />,
    );

    const frame = await screen.findByTestId("preview-iframe");
    const postMessage = jest.fn();
    Object.defineProperty(frame, "contentWindow", {
      configurable: true,
      value: { postMessage },
    });

    fireEvent.load(frame);

    await waitFor(() => {
      expect(postMessage).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "talmudpedia.preview-auth.v1",
          token: null,
        }),
        "https://preview.local",
      );
    });

    rerender(
      <PreviewCanvas
        previewUrl="https://preview.local/sandbox/session-1/?preview_route=%2Fchat"
        transportKey="session-1:1"
        transportStatus="ready"
      />,
    );

    await waitFor(() => {
      expect(postMessage).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "talmudpedia.preview-auth.v1",
          token: null,
        }),
        "https://preview.local",
      );
    });
  });

  it("keeps iframe src stable when only the same-session preview route changes", async () => {
    const { rerender } = render(
      <PreviewCanvas
        previewUrl="https://preview.local/sandbox/session-1/?preview_route=%2F"
        transportKey="session-1:1"
        transportStatus="ready"
      />,
    );

    const frame = await screen.findByTestId("preview-iframe");
    const initialSrc = frame.getAttribute("src");
    expect(initialSrc).toContain("preview_route=%2F");

    rerender(
      <PreviewCanvas
        previewUrl="https://preview.local/sandbox/session-1/?preview_route=%2Fchat"
        transportKey="session-1:1"
        transportStatus="ready"
      />,
    );

    expect(screen.getByTestId("preview-iframe").getAttribute("src")).toBe(initialSrc);
  });

  it("keeps the current iframe visible while staging a same-session route change", async () => {
    const { container, rerender } = render(
      <PreviewCanvas
        previewUrl="https://preview.local/sandbox/session-1/?preview_route=%2F"
        transportKey="session-1:1"
        transportStatus="ready"
      />,
    );

    const frame = await screen.findByTestId("preview-iframe");
    fireEvent.load(frame);

    rerender(
      <PreviewCanvas
        previewUrl="https://preview.local/sandbox/session-1/?preview_route=%2Fchat"
        transportKey="session-1:1"
        transportStatus="ready"
      />,
    );

    expect(screen.getByTestId("preview-iframe").getAttribute("src")).toContain("preview_route=%2F");
    expect(container.querySelectorAll("iframe")).toHaveLength(2);

    const pendingFrame = container.querySelector('iframe[title="App Preview Pending"]');
    expect(pendingFrame).not.toBeNull();
    fireEvent.load(pendingFrame as HTMLIFrameElement);

    await waitFor(() => {
      expect(screen.getByTestId("preview-iframe").getAttribute("src")).toContain("preview_route=%2Fchat");
    });
  });

  it("keeps the iframe mounted during same-session reconnecting states", async () => {
    const { rerender } = render(
      <PreviewCanvas
        previewUrl="https://preview.local/sandbox/session-1/"
        transportKey="session-1:1"
        transportStatus="ready"
      />,
    );

    const frame = await screen.findByTestId("preview-iframe");
    fireEvent.load(frame);

    rerender(
      <PreviewCanvas
        previewUrl="https://preview.local/sandbox/session-1/"
        transportKey="session-1:1"
        transportStatus="reconnecting"
        hasUsableFrame={true}
        loadingMessage="Recovering preview sandbox..."
      />,
    );

    expect(screen.getByTestId("preview-iframe")).toBeInTheDocument();
    expect(screen.queryByTestId("preview-warmup-overlay")).not.toBeInTheDocument();
    expect(screen.getByText("Recovering preview sandbox...")).toBeInTheDocument();
  });

  it("renders staged loading steps during cold preview boot", () => {
    render(
      <PreviewCanvas
        transportStatus="booting"
        loadingMessage="Starting preview sandbox..."
        loadingState={{
          title: "Starting preview runtime",
          detail: "Starting preview sandbox...",
          steps: [
            { label: "Create live workspace", status: "complete" },
            { label: "Start preview runtime", status: "current" },
            { label: "Connect live preview", status: "pending" },
          ],
        }}
      />,
    );

    expect(screen.getByTestId("preview-warmup-overlay")).toBeInTheDocument();
    expect(screen.getByText("Starting preview runtime")).toBeInTheDocument();
    expect(screen.getByText("Create live workspace")).toBeInTheDocument();
    expect(screen.getByText("Start preview runtime")).toBeInTheDocument();
    expect(screen.getByText("Connect live preview")).toBeInTheDocument();
  });

  it("keeps the full loading overlay visible until the iframe becomes usable", async () => {
    render(
      <PreviewCanvas
        previewUrl="https://preview.local/sandbox/session-1/"
        transportKey="session-1:1"
        transportStatus="booting"
        hasUsableFrame={false}
        loadingState={{
          title: "Connecting live preview",
          detail: "Waiting for preview sandbox...",
          steps: [
            { label: "Create live workspace", status: "complete" },
            { label: "Start preview runtime", status: "complete" },
            { label: "Connect live preview", status: "current" },
          ],
        }}
      />,
    );

    expect(await screen.findByTestId("preview-iframe")).toBeInTheDocument();
    expect(screen.getByTestId("preview-warmup-overlay")).toBeInTheDocument();
  });
});
