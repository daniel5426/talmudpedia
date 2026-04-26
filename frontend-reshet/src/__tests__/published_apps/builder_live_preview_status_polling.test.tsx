import { renderHook, waitFor } from "@testing-library/react";

import { useBuilderLivePreviewStatus } from "@/features/apps-builder/preview/useBuilderLivePreviewStatus";
import { publishedAppsService } from "@/services";

jest.mock("@/services", () => ({
  publishedAppsService: {
    getDraftDevPreviewStatus: jest.fn(),
  },
}));

const getDraftDevPreviewStatus = publishedAppsService.getDraftDevPreviewStatus as jest.Mock;

describe("useBuilderLivePreviewStatus", () => {
  beforeEach(() => {
    getDraftDevPreviewStatus.mockReset();
  });

  it("polls while enabled even when the current preview state is ready", async () => {
    getDraftDevPreviewStatus.mockResolvedValue({
      status: "ready",
      current_build_id: "build-2",
      last_successful_build_id: "build-2",
      updated_at: "2026-04-26T00:00:01Z",
    });

    const { result, unmount } = renderHook(() =>
      useBuilderLivePreviewStatus({
        previewBaseUrl: "https://preview.local/session-1/?runtime_token=token",
        sessionLivePreview: {
          status: "ready",
          current_build_id: "build-1",
          last_successful_build_id: "build-1",
          updated_at: "2026-04-26T00:00:00Z",
        },
        enabled: true,
      }),
    );

    await waitFor(() => {
      expect(getDraftDevPreviewStatus).toHaveBeenCalledWith("https://preview.local/session-1/?runtime_token=token");
    });
    await waitFor(() => {
      expect(result.current?.last_successful_build_id).toBe("build-2");
    });
    unmount();
  });

  it("does not poll a ready steady-state preview when disabled", () => {
    const { result, unmount } = renderHook(() =>
      useBuilderLivePreviewStatus({
        previewBaseUrl: "https://preview.local/session-1/?runtime_token=token",
        sessionLivePreview: {
          status: "ready",
          current_build_id: "build-1",
          last_successful_build_id: "build-1",
          updated_at: "2026-04-26T00:00:00Z",
        },
        enabled: false,
      }),
    );

    expect(getDraftDevPreviewStatus).not.toHaveBeenCalled();
    expect(result.current?.last_successful_build_id).toBe("build-1");
    unmount();
  });
});
