import { act, renderHook, waitFor } from "@testing-library/react";

import { useAppsBuilderVersions } from "@/features/apps-builder/workspace/versions/useAppsBuilderVersions";
import type { AppVersionListItem, PublishedAppRevision } from "@/services";
import { publishedAppsService } from "@/services";

jest.mock("@/services", () => ({
  publishedAppsService: {
    listVersions: jest.fn(),
    getVersion: jest.fn(),
    getVersionPreviewRuntime: jest.fn(),
    restoreVersion: jest.fn(),
    publishVersion: jest.fn(),
    getPublishJobStatus: jest.fn(),
  },
}));

const mockedService = publishedAppsService as jest.Mocked<typeof publishedAppsService>;

const BASE_VERSION: AppVersionListItem = {
  id: "rev-1",
  published_app_id: "app-1",
  kind: "draft",
  template_key: "chat-classic",
  entry_file: "src/main.tsx",
  files: {},
  created_at: "2026-03-01T00:00:00Z",
  version_seq: 1,
  origin_kind: "manual_save",
  source_revision_id: null,
  is_current_draft: true,
  is_current_published: false,
};

const VERSION_PAYLOAD: PublishedAppRevision = {
  ...BASE_VERSION,
  files: {
    "src/main.tsx": "export default function App(){return <main>v1</main>;}",
  },
};

describe("useAppsBuilderVersions", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedService.listVersions.mockResolvedValue([BASE_VERSION]);
    mockedService.getVersion.mockResolvedValue(VERSION_PAYLOAD);
    mockedService.getVersionPreviewRuntime.mockResolvedValue({
      revision_id: "rev-1",
      preview_url: "http://localhost:8026/public/apps/preview/revisions/rev-1/runtime?runtime_token=abc",
      runtime_token: "abc",
      expires_at: "2026-03-01T00:00:00Z",
    });
    mockedService.restoreVersion.mockResolvedValue({
      ...VERSION_PAYLOAD,
      id: "rev-2",
      restored_from_revision_id: "rev-1",
    });
    mockedService.publishVersion.mockResolvedValue({
      job_id: "job-1",
      app_id: "app-1",
      status: "queued",
      source_revision_id: "rev-1",
      saved_draft_revision_id: null,
      published_revision_id: null,
      diagnostics: [],
      created_at: "2026-03-01T00:00:00Z",
    });
    mockedService.getPublishJobStatus.mockResolvedValue({
      job_id: "job-1",
      app_id: "app-1",
      status: "succeeded",
      source_revision_id: "rev-1",
      saved_draft_revision_id: null,
      published_revision_id: "rev-pub-1",
      diagnostics: [],
      created_at: "2026-03-01T00:00:00Z",
      started_at: "2026-03-01T00:00:01Z",
      finished_at: "2026-03-01T00:00:02Z",
    });
  });

  it("loads versions and selected version payload on init", async () => {
    const onApplyRevision = jest.fn();
    const onRefreshState = jest.fn().mockResolvedValue(undefined);
    const onError = jest.fn();

    const { result } = renderHook(() =>
      useAppsBuilderVersions({
        appId: "app-1",
        currentRevisionId: "rev-1",
        onApplyRevision,
        onRefreshState,
        onError,
      }),
    );

    await waitFor(() => {
      expect(mockedService.listVersions).toHaveBeenCalledWith("app-1", { limit: 100 });
    });

    await waitFor(() => {
      expect(mockedService.getVersion).toHaveBeenCalledWith("app-1", "rev-1");
      expect(result.current.selectedVersion?.id).toBe("rev-1");
    });
  });

  it("restores selected version through /versions/{id}/restore flow", async () => {
    const onApplyRevision = jest.fn();
    const onRefreshState = jest.fn().mockResolvedValue(undefined);
    const onError = jest.fn();

    const { result } = renderHook(() =>
      useAppsBuilderVersions({
        appId: "app-1",
        currentRevisionId: "rev-1",
        onApplyRevision,
        onRefreshState,
        onError,
      }),
    );

    await waitFor(() => {
      expect(result.current.selectedVersionId).toBe("rev-1");
    });

    await act(async () => {
      await result.current.restoreSelectedVersion();
    });

    expect(mockedService.restoreVersion).toHaveBeenCalledWith("app-1", "rev-1");
    expect(onApplyRevision).toHaveBeenCalled();
    expect(onRefreshState).toHaveBeenCalled();
  });

  it("publishes selected version through /versions/{id}/publish flow", async () => {
    const onApplyRevision = jest.fn();
    const onRefreshState = jest.fn().mockResolvedValue(undefined);
    const onError = jest.fn();

    const { result } = renderHook(() =>
      useAppsBuilderVersions({
        appId: "app-1",
        currentRevisionId: "rev-1",
        onApplyRevision,
        onRefreshState,
        onError,
      }),
    );

    await waitFor(() => {
      expect(result.current.selectedVersionId).toBe("rev-1");
    });

    await act(async () => {
      await result.current.publishSelectedVersion();
    });

    expect(mockedService.publishVersion).toHaveBeenCalledWith("app-1", "rev-1");
    expect(mockedService.getPublishJobStatus).toHaveBeenCalledWith("app-1", "job-1");
  });

  it("does not expose removed legacy revision/checkpoint service methods", () => {
    const legacy = publishedAppsService as unknown as Record<string, unknown>;
    expect(legacy.createRevision).toBeUndefined();
    expect(legacy.createRevisionPreviewToken).toBeUndefined();
    expect(legacy.listCodingAgentCheckpoints).toBeUndefined();
    expect(legacy.restoreCodingAgentCheckpoint).toBeUndefined();
  });
});
