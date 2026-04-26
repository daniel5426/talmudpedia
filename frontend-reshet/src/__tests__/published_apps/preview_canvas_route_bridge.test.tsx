import { render } from "@testing-library/react";

import { PreviewCanvas } from "@/features/apps-builder/preview/PreviewCanvas";

describe("PreviewCanvas route bridge", () => {
  it("forwards routed iframe navigation messages to the parent callback", () => {
    const handlePreviewRouteChange = jest.fn();

    render(
      <PreviewCanvas
        previewUrl="https://preview.local/sandbox/session-1/?preview_route=%2F"
        transportKey="session-1:1"
        transportStatus="ready"
        onPreviewRouteChange={handlePreviewRouteChange}
      />,
    );

    window.dispatchEvent(new MessageEvent("message", {
      origin: "https://preview.local",
      data: {
        type: "talmudpedia.preview-debug.v1",
        payload: {
          event: "preview.route_changed",
          route: "/chat",
          source: "pushState",
        },
      },
    }));

    expect(handlePreviewRouteChange).toHaveBeenCalledWith("/chat");
  });
});
