import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder } from "util";

import { AppsBuilderWorkspace } from "@/features/apps-builder/workspace/AppsBuilderWorkspace";
import { publishedAppsService } from "@/services";

const setOpenMock = jest.fn();
const mockCodeEditor = jest.fn(
  ({
    value,
    onChange,
    language,
    suppressValidationDecorations,
  }: {
    value: string;
    onChange: (value: string) => void;
    language?: string;
    suppressValidationDecorations?: boolean;
  }) => (
    <textarea
      aria-label="Code Editor"
      data-language={language || ""}
      data-suppress-validation={String(Boolean(suppressValidationDecorations))}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
);

(global as any).TextDecoder = TextDecoder;

jest.mock("@/services", () => ({
  publishedAppsService: {
    getBuilderState: jest.fn(),
    getBuilderCheckpoints: jest.fn(),
    createRevision: jest.fn(),
    publish: jest.fn(),
    getPublishJobStatus: jest.fn(),
    ensureDraftDevSession: jest.fn(),
    syncDraftDevSession: jest.fn(),
    heartbeatDraftDevSession: jest.fn(),
    resetTemplate: jest.fn(),
    streamBuilderChat: jest.fn(),
    undoLastBuilderRun: jest.fn(),
    revertBuilderFile: jest.fn(),
  },
}));

jest.mock("@/components/ui/sidebar", () => ({
  useSidebar: () => ({ setOpen: setOpenMock }),
}));

jest.mock("@/lib/react-artifacts/compiler", () => ({
  compileReactArtifactProject: jest.fn(async () => ({ ok: true, output: "console.log('ok')" })),
}));

jest.mock("@/components/ui/code-editor", () => ({
  CodeEditor: (props: Parameters<typeof mockCodeEditor>[0]) => mockCodeEditor(props),
}));

const makeFiles = () => ({
  "index.html": "<!doctype html><html><body><div id='root'></div></body></html>",
  "src/main.tsx": "import './App';",
  "src/App.tsx": "export function App() { return <div>Hello</div>; }",
  "src/components/Button.tsx": "export function Button() { return <button>Click</button>; }",
});

const makeState = (files: Record<string, string> = makeFiles()) => ({
  app: {
    id: "app-1",
    tenant_id: "tenant-1",
    agent_id: "agent-1",
    name: "Builder App",
    slug: "builder-app",
    status: "draft",
    auth_enabled: true,
    auth_providers: ["password"],
    template_key: "chat-classic",
    current_draft_revision_id: "rev-1",
    current_published_revision_id: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  templates: [
    {
      key: "chat-classic",
      name: "Classic Dialogue",
      description: "Classic",
      thumbnail: "classic",
      tags: ["chat"],
      entry_file: "src/main.tsx",
      style_tokens: {},
    },
    {
      key: "chat-neon",
      name: "Neon Console",
      description: "Neon",
      thumbnail: "neon",
      tags: ["chat"],
      entry_file: "src/main.tsx",
      style_tokens: {},
    },
  ],
  current_draft_revision: {
    id: "rev-1",
    published_app_id: "app-1",
    kind: "draft",
    template_key: "chat-classic",
    entry_file: "src/main.tsx",
    build_status: "succeeded",
    build_seq: 1,
    files,
    created_at: new Date().toISOString(),
  },
  current_published_revision: null,
  preview_token: "preview-token",
  draft_dev: null,
});

describe("AppsBuilderWorkspace", () => {
  const openCodeTab = async () => {
    const codeTab = await screen.findByRole("tab", { name: "Code" });
    fireEvent.mouseDown(codeTab);
    fireEvent.click(codeTab);
    await waitFor(() => expect(codeTab).toHaveAttribute("data-state", "active"));
  };

  beforeEach(() => {
    (publishedAppsService.getBuilderState as jest.Mock).mockResolvedValue(makeState());
    (publishedAppsService.getBuilderCheckpoints as jest.Mock).mockResolvedValue([
      {
        turn_id: "turn-1",
        request_id: "req-1",
        revision_id: "rev-2",
        source_revision_id: "rev-1",
        checkpoint_type: "auto_run",
        checkpoint_label: "AI run req-1",
        assistant_summary: "applied update",
        created_at: new Date().toISOString(),
      },
    ]);
    (publishedAppsService.ensureDraftDevSession as jest.Mock).mockResolvedValue({
      session_id: "session-1",
      app_id: "app-1",
      revision_id: "rev-1",
      status: "running",
      preview_url: "https://preview.local/sandbox/session-1/",
      idle_timeout_seconds: 180,
      last_activity_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 180_000).toISOString(),
      last_error: null,
    });
    (publishedAppsService.syncDraftDevSession as jest.Mock).mockResolvedValue({
      session_id: "session-1",
      app_id: "app-1",
      revision_id: "rev-1",
      status: "running",
      preview_url: "https://preview.local/sandbox/session-1/",
      idle_timeout_seconds: 180,
      last_activity_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 180_000).toISOString(),
      last_error: null,
    });
    (publishedAppsService.heartbeatDraftDevSession as jest.Mock).mockResolvedValue({
      session_id: "session-1",
      app_id: "app-1",
      revision_id: "rev-1",
      status: "running",
      preview_url: "https://preview.local/sandbox/session-1/",
      idle_timeout_seconds: 180,
      last_activity_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 180_000).toISOString(),
      last_error: null,
    });
    (publishedAppsService.createRevision as jest.Mock).mockResolvedValue({
      id: "rev-2",
      published_app_id: "app-1",
      kind: "draft",
      template_key: "chat-classic",
      entry_file: "src/main.tsx",
      build_status: "queued",
      build_seq: 2,
      files: {
        "src/main.tsx": "import './App';",
        "src/App.tsx": "export function App() { return <div>Updated</div>; }",
        "index.html": "<!doctype html><html><body><div id='root'></div></body></html>",
      },
      source_revision_id: "rev-1",
      created_at: new Date().toISOString(),
    });
    (publishedAppsService.publish as jest.Mock).mockResolvedValue({
      job_id: "job-1",
      app_id: "app-1",
      status: "queued",
      diagnostics: [],
      created_at: new Date().toISOString(),
    });
    (publishedAppsService.getPublishJobStatus as jest.Mock).mockResolvedValue({
      job_id: "job-1",
      app_id: "app-1",
      status: "succeeded",
      published_revision_id: "rev-3",
      diagnostics: [],
      created_at: new Date().toISOString(),
      started_at: new Date().toISOString(),
      finished_at: new Date().toISOString(),
    });
    (publishedAppsService.resetTemplate as jest.Mock).mockResolvedValue({
      id: "rev-4",
      published_app_id: "app-1",
      kind: "draft",
      template_key: "chat-neon",
      entry_file: "src/main.tsx",
      build_status: "queued",
      build_seq: 3,
      files: makeState().current_draft_revision.files,
      source_revision_id: "rev-1",
      created_at: new Date().toISOString(),
    });
    (publishedAppsService.streamBuilderChat as jest.Mock).mockResolvedValue({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"status","stage":"start","request_id":"req-1","data":{"content":"Builder request accepted"}}\n\n',
            'data: {"event":"token","stage":"assistant_response","request_id":"req-1","data":{"content":"Applying patch"}}\n\n',
            'data: {"event":"file_changes","stage":"patch_ready","request_id":"req-1","data":{"base_revision_id":"rev-1","result_revision_id":"rev-2","summary":"applied update","changed_paths":["src/App.tsx"],"operations":[{"op":"upsert_file","path":"src/App.tsx","content":"export function App() { return <div>From Patch</div>; }"}]}}\n\n',
            'data: {"event":"checkpoint_created","stage":"checkpoint","request_id":"req-1","data":{"revision_id":"rev-2","source_revision_id":"rev-1","checkpoint_type":"auto_run","checkpoint_label":"AI run req-1"}}\n\n',
            'data: {"event":"done","type":"done","stage":"complete","request_id":"req-1"}\n\n',
          ];
          let cursor = 0;
          return {
            read: async () => {
              if (cursor >= chunks.length) return { done: true, value: undefined };
              const next = chunks[cursor++];
              return { done: false, value: new Uint8Array(Buffer.from(next, "utf-8")) };
            },
          };
        },
      },
    });
    (publishedAppsService.undoLastBuilderRun as jest.Mock).mockResolvedValue({
      revision: makeState().current_draft_revision,
      restored_from_revision_id: "rev-1",
      checkpoint_turn_id: "turn-1",
      request_id: "undo-1",
    });
    (publishedAppsService.revertBuilderFile as jest.Mock).mockResolvedValue({
      revision: makeState().current_draft_revision,
      reverted_path: "src/App.tsx",
      from_revision_id: "rev-1",
      request_id: "revert-1",
    });
    jest.spyOn(window, "confirm").mockReturnValue(true);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("renders builder tabs and saves draft revision", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalledWith("app-1"));
    await screen.findByRole("tab", { name: "Preview" });
    expect(screen.getByRole("tab", { name: "Code" })).toBeInTheDocument();
    expect(setOpenMock).toHaveBeenCalledWith(false);

    fireEvent.click(screen.getByRole("button", { name: /save draft/i }));

    await waitFor(() => {
      expect(publishedAppsService.createRevision).toHaveBeenCalledWith(
        "app-1",
        expect.objectContaining({
          base_revision_id: "rev-1",
          entry_file: "src/main.tsx",
        }),
      );
    });
  });

  it("renders a hierarchical file tree and supports folder collapse/expand", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await openCodeTab();
    await waitFor(() => expect(screen.getByRole("button", { name: "src" })).toBeInTheDocument());

    expect(screen.queryByRole("button", { name: "src/components/Button.tsx" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "src" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "components" })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "components" }));
    expect(screen.getByRole("button", { name: "Button.tsx" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "components" }));
    expect(screen.queryByRole("button", { name: "Button.tsx" })).not.toBeInTheDocument();
  });

  it("auto-expands ancestor folders when selected file is nested", async () => {
    (publishedAppsService.getBuilderState as jest.Mock).mockResolvedValueOnce(
      makeState({
        "src/components/Button.tsx": "export function Button() { return <button>Click</button>; }",
        "src/main.tsx": "import './App';",
      }),
    );

    render(<AppsBuilderWorkspace appId="app-1" />);

    await openCodeTab();

    await waitFor(() => expect(screen.getByRole("button", { name: "Button.tsx" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "components" })).toBeInTheDocument();
  });

  it("uses html language mode and suppresses validation decorations in builder editor", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await openCodeTab();

    const editor = await screen.findByLabelText("Code Editor");
    expect(editor).toHaveAttribute("data-language", "html");
    expect(editor).toHaveAttribute("data-suppress-validation", "true");
  });

  it("switches template with destructive confirmation", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findAllByRole("combobox");

    fireEvent.click(screen.getAllByRole("combobox")[0]);
    fireEvent.click(screen.getByText("Neon Console"));

    await waitFor(() => {
      expect(window.confirm).toHaveBeenCalled();
      expect(publishedAppsService.resetTemplate).toHaveBeenCalledWith("app-1", "chat-neon");
    });
  });

  it("streams builder run and renders timeline cards", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Refactor the header and align spacing with the hero...");

    fireEvent.change(screen.getByPlaceholderText("Refactor the header and align spacing with the hero..."), {
      target: { value: "Make it bold" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(publishedAppsService.streamBuilderChat).toHaveBeenCalledWith(
        "app-1",
        expect.objectContaining({ input: "Make it bold", base_revision_id: "rev-1" }),
      );
    });

    await waitFor(() => {
      expect(screen.getByText(/Files changed/i)).toBeInTheDocument();
      expect(screen.getByText(/Checkpoint created/i)).toBeInTheDocument();
    });
  });

  it("calls undo endpoint from quick action", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: /Undo Last Run/i }));

    await waitFor(() => {
      expect(publishedAppsService.undoLastBuilderRun).toHaveBeenCalledWith(
        "app-1",
        expect.objectContaining({ base_revision_id: "rev-1" }),
      );
    });
  });

  it("calls revert file endpoint from quick action", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: /Revert File/i }));

    await waitFor(() => {
      expect(publishedAppsService.revertBuilderFile).toHaveBeenCalledWith(
        "app-1",
        expect.objectContaining({
          from_revision_id: "rev-2",
        }),
      );
    });
  });
});
