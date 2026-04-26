import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { AppsBuilderWorkspace } from "@/features/apps-builder/workspace/AppsBuilderWorkspace";
import { agentService, publishedAppsService } from "@/services";

const ensureDraftDevSessionMock = jest.fn();
const retryEnsureDraftDevSessionMock = jest.fn();
const syncDraftDevSessionMock = jest.fn();
const refreshVersionsMock = jest.fn();
const lifecycleController: {
  afterSync?: ((options: any) => void) | null;
} = {
  afterSync: null,
};

jest.mock("@/services", () => ({
  agentService: {
    listAgents: jest.fn(),
  },
  publishedAppsService: {
    getBuilderState: jest.fn(),
    getExportOptions: jest.fn(),
    listAuthTemplates: jest.fn(),
    syncDraftDevSession: jest.fn(),
  },
  isDraftDevFailureStatus: jest.fn(() => false),
  isDraftDevServingStatus: jest.fn((status: string | null | undefined) => String(status || "").trim().toLowerCase() === "serving"),
}));

jest.mock("@/components/ui/sidebar", () => ({
  useSidebar: () => ({ setOpen: jest.fn() }),
}));

jest.mock("@/features/apps-builder/workspace/ConfigSidebar", () => ({
  ConfigSidebar: ({ onChangeSection, showCodeSaveButton, onSaveCodeDraft, isSavingCodeDraft, disableCodeSave }: any) => (
    <div>
      <button type="button" onClick={() => onChangeSection("code")}>Open Code</button>
      {showCodeSaveButton ? (
        <button type="button" disabled={Boolean(isSavingCodeDraft) || Boolean(disableCodeSave)} onClick={onSaveCodeDraft}>
          Save Code
        </button>
      ) : null}
    </div>
  ),
}));

jest.mock("@/features/apps-builder/editor/CodeEditorPanel", () => ({
  CodeEditorPanel: ({ files, selectedFile, onUpdateFile }: any) => {
    const path = files?.["src/main.tsx"] !== undefined
      ? "src/main.tsx"
      : (selectedFile || Object.keys(files || {})[0] || "src/main.tsx");
    const content = path ? files?.[path] || "" : "";
    return (
      <div>
        <div data-testid="editor-content">{content}</div>
        <button type="button" onClick={() => onUpdateFile(path, "export default function App() { return <div>new</div>; }\n")}>
          Edit File
        </button>
      </div>
    );
  },
}));

jest.mock("@/features/apps-builder/editor/FileTree", () => ({
  FileTree: () => null,
}));

jest.mock("@/features/apps-builder/preview/PreviewCanvas", () => ({
  PreviewCanvas: () => <div data-testid="preview-canvas" />,
}));

jest.mock("@/features/apps-builder/workspace/WorkspaceLoadingSkeletons", () => ({
  AppsBuilderWorkspaceBootSkeleton: () => <div>Loading workspace...</div>,
  DomainsListSkeleton: () => null,
  UsersListSkeleton: () => null,
}));

jest.mock("@/features/apps-builder/workspace/LogoPickerDialog", () => ({
  LogoPickerDialog: () => null,
}));

jest.mock("@/features/apps-builder/workspace/chat/AppsBuilderChatPanel", () => ({
  AppsBuilderChatPanel: () => null,
}));

jest.mock("@/features/apps-builder/workspace/chat/useAppsBuilderChat", () => ({
  useAppsBuilderChat: () => ({
    isAgentPanelOpen: false,
    setIsAgentPanelOpen: jest.fn(),
    isSending: false,
    isStopping: false,
    timeline: [],
    activeThinkingSummary: null,
    activeContextStatus: null,
    chatSessions: [],
    activeChatSessionId: null,
    activateDraftChat: jest.fn(),
    chatModels: [],
    setSelectedRunModelId: jest.fn(),
    isModelSelectorOpen: false,
    setIsModelSelectorOpen: jest.fn(),
    selectedRunModelLabel: null,
    queuedPrompts: [],
    pendingQuestion: null,
    isAnsweringQuestion: false,
    runningSessionIds: [],
    sendingSessionIds: [],
    sessionTitleHintsBySessionId: {},
    hasOlderHistory: false,
    isLoadingOlderHistory: false,
    loadOlderHistory: jest.fn(),
    removeQueuedPrompt: jest.fn(),
    answerPendingQuestion: jest.fn(),
    refreshChatSessionRunActivity: jest.fn(),
    sendBuilderChat: jest.fn(),
    stopCurrentRun: jest.fn(),
    startNewChat: jest.fn(),
    loadChatSession: jest.fn(),
  }),
}));

jest.mock("@/features/apps-builder/workspace/versions/useAppsBuilderVersions", () => ({
  useAppsBuilderVersions: () => ({
    versions: [],
    selectedVersion: null,
    selectedVersionId: null,
    isLoadingVersions: false,
    isLoadingVersionPreview: false,
    isRestoringVersion: false,
    isPublishingVersion: false,
    publishStatus: null,
    inspectedVersionId: null,
    inspectedPreviewUrl: null,
    inspectedPreviewNotice: null,
    refreshVersions: refreshVersionsMock,
    selectVersion: jest.fn(),
    clearInspectedVersion: jest.fn(),
    restoreSelectedVersion: jest.fn(),
    publishSelectedVersion: jest.fn(),
  }),
}));

jest.mock("@/features/apps-builder/preview/useBuilderLivePreviewStatus", () => ({
  useBuilderLivePreviewStatus: () => ({
    status: "ready",
    last_successful_build_id: "build-1",
    current_build_id: "build-1",
    error: null,
  }),
}));

jest.mock("@/features/apps-builder/preview/useBuilderPreviewTransport", () => ({
  useBuilderPreviewTransport: () => ({
    documentUrl: "https://preview.local/",
    transportKey: "session-1:1",
    status: "ready",
    hasUsableFrame: true,
    markFrameUsable: jest.fn(),
    clearUsableFrame: jest.fn(),
  }),
}));

jest.mock("@/features/apps-builder/workspace/useAppsBuilderSandboxLifecycle", () => ({
  useAppsBuilderSandboxLifecycle: (options: any) => ({
    phase: "running",
    draftDevSessionId: "session-1",
    draftDevStatus: "serving",
    draftDevError: null,
    previewAssetUrl: "https://preview.local/",
    previewTransportGeneration: 1,
    previewLoadingMessage: null,
    publishLockMessage: null,
    isReady: true,
    isBusy: false,
    canRetry: false,
    actionDisabledReason: null,
    hydrateFromBuilderSession: (session: any) => options.onSessionChange?.(session ?? null),
    ensureDraftDevSession: ensureDraftDevSessionMock,
    retryEnsureDraftDevSession: retryEnsureDraftDevSessionMock,
    syncDraftDevSession: async (...args: any[]) => {
      const result = await syncDraftDevSessionMock(...args);
      lifecycleController.afterSync?.(options);
      return result;
    },
  }),
}));

function buildState({
  revisionId,
  currentContent,
  snapshotContent,
}: {
  revisionId: string;
  currentContent: string;
  snapshotContent: string;
}) {
  return {
    app: {
      id: "app-1",
      name: "Test App",
      public_id: "test-app",
      current_draft_revision_id: revisionId,
      template_key: "classic-chat",
      logo_url: null,
      agent_id: "agent-1",
      description: "",
    },
    current_draft_revision: {
      id: revisionId,
      published_app_id: "app-1",
      kind: "draft",
      template_key: "classic-chat",
      entry_file: "src/main.tsx",
      files: {
        "index.html": "<!doctype html><html><body><div id='root'></div></body></html>",
        "src/main.tsx": currentContent,
      },
      created_at: "2026-04-23T15:00:00Z",
    },
    draft_dev: {
      session_id: "session-1",
      app_id: "app-1",
      revision_id: revisionId,
      status: "serving",
      preview_url: "https://preview.local/",
      preview_transport_generation: 1,
      workspace_revision_token: revisionId === "rev-2" ? "token-2" : "token-1",
      live_workspace_snapshot: {
        revision_id: revisionId,
        entry_file: "src/main.tsx",
        files: {
          "index.html": "<!doctype html><html><body><div id='root'></div></body></html>",
          "src/main.tsx": snapshotContent,
        },
        revision_token: revisionId === "rev-2" ? "token-2" : "token-1",
        updated_at: "2026-04-23T15:00:00Z",
      },
      live_preview: {
        status: "ready",
        current_build_id: revisionId === "rev-2" ? "build-2" : "build-1",
        last_successful_build_id: revisionId === "rev-2" ? "build-2" : "build-1",
        updated_at: "2026-04-23T15:00:00Z",
      },
      has_active_coding_runs: false,
      active_coding_run_count: 0,
      expires_at: null,
      idle_timeout_seconds: 180,
      last_activity_at: null,
      last_error: null,
    },
    templates: [],
  };
}

describe("AppsBuilderWorkspace manual save", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    lifecycleController.afterSync = null;
    ensureDraftDevSessionMock.mockResolvedValue({
      session_id: "session-1",
      status: "serving",
      preview_url: "https://preview.local/",
    });
    refreshVersionsMock.mockResolvedValue(undefined);
    (publishedAppsService.getExportOptions as jest.Mock).mockResolvedValue({
      supported: true,
      ready: true,
      reason: null,
    });
    (publishedAppsService.listAuthTemplates as jest.Mock).mockResolvedValue([]);
    (agentService.listAgents as jest.Mock).mockResolvedValue({
      items: [],
      total: 0,
      has_more: false,
      skip: 0,
      limit: 100,
      view: "summary",
    });
  });

  it("keeps the saved local code when a stale session update arrives after save", async () => {
    (publishedAppsService.getBuilderState as jest.Mock)
      .mockResolvedValueOnce(
        buildState({
          revisionId: "rev-1",
          currentContent: "export default function App() { return <div>old</div>; }\n",
          snapshotContent: "export default function App() { return <div>old</div>; }\n",
        }),
      )
      .mockResolvedValueOnce(
        buildState({
          revisionId: "rev-2",
          currentContent: "export default function App() { return <div>new</div>; }\n",
          snapshotContent: "export default function App() { return <div>new</div>; }\n",
        }),
      );

    syncDraftDevSessionMock.mockResolvedValue({
      session_id: "session-1",
      app_id: "app-1",
      revision_id: "rev-2",
      status: "serving",
      preview_url: "https://preview.local/",
      preview_transport_generation: 1,
      workspace_revision_token: "token-2",
      live_workspace_snapshot: {
        revision_id: "rev-2",
        entry_file: "src/main.tsx",
        files: {
          "index.html": "<!doctype html><html><body><div id='root'></div></body></html>",
          "src/main.tsx": "export default function App() { return <div>new</div>; }\n",
        },
        revision_token: "token-2",
        updated_at: "2026-04-23T15:01:00Z",
      },
      live_preview: {
        status: "ready",
        current_build_id: "build-2",
        last_successful_build_id: "build-2",
        updated_at: "2026-04-23T15:01:00Z",
      },
      has_active_coding_runs: false,
      active_coding_run_count: 0,
      expires_at: null,
      idle_timeout_seconds: 180,
      last_activity_at: null,
      last_error: null,
    });
    lifecycleController.afterSync = (options) => {
      window.setTimeout(() => {
        options.onSessionChange?.({
          session_id: "session-1",
          app_id: "app-1",
          revision_id: "rev-1",
          status: "serving",
          preview_url: "https://preview.local/",
          preview_transport_generation: 1,
          workspace_revision_token: "token-1",
          live_workspace_snapshot: {
            revision_id: "rev-1",
            entry_file: "src/main.tsx",
            files: {
              "index.html": "<!doctype html><html><body><div id='root'></div></body></html>",
              "src/main.tsx": "export default function App() { return <div>old</div>; }\n",
            },
            revision_token: "token-1",
            updated_at: "2026-04-23T15:01:30Z",
          },
          live_preview: {
            status: "ready",
            current_build_id: "build-1",
            last_successful_build_id: "build-1",
            updated_at: "2026-04-23T15:01:30Z",
          },
          has_active_coding_runs: false,
          active_coding_run_count: 0,
          expires_at: null,
          idle_timeout_seconds: 180,
          last_activity_at: null,
          last_error: null,
        });
      }, 0);
    };

    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "Open Code" }));

    await waitFor(() => {
      expect(screen.getByTestId("editor-content")).toHaveTextContent("old");
    });

    fireEvent.click(screen.getByRole("button", { name: "Edit File" }));
    expect(screen.getByTestId("editor-content")).toHaveTextContent("new");

    fireEvent.click(screen.getByRole("button", { name: "Save Code" }));

    await waitFor(() => expect(syncDraftDevSessionMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalledTimes(1));

    await waitFor(() => {
      expect(screen.getByTestId("editor-content")).toHaveTextContent("new");
    });
    expect(screen.queryByText("Live workspace changed while you have unsaved local edits.")).not.toBeInTheDocument();
  });
});
