import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder } from "util";

import { AppsBuilderWorkspace } from "@/features/apps-builder/workspace/AppsBuilderWorkspace";
import { publishedAppsService, publishedRuntimeService } from "@/services";

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
    listAuthTemplates: jest.fn(),
    update: jest.fn(),
    listUsers: jest.fn(),
    updateUser: jest.fn(),
    listDomains: jest.fn(),
    createDomain: jest.fn(),
    deleteDomain: jest.fn(),
    listCodingAgentCheckpoints: jest.fn(),
    createRevision: jest.fn(),
    createRevisionPreviewToken: jest.fn(),
    publish: jest.fn(),
    getPublishJobStatus: jest.fn(),
    ensureDraftDevSession: jest.fn(),
    syncDraftDevSession: jest.fn(),
    heartbeatDraftDevSession: jest.fn(),
    resetTemplate: jest.fn(),
    createCodingAgentRun: jest.fn(),
    streamCodingAgentRun: jest.fn(),
    restoreCodingAgentCheckpoint: jest.fn(),
  },
  publishedRuntimeService: {
    getPreviewRuntime: jest.fn(),
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

jest.mock("@/components/ai-elements/conversation", () => ({
  Conversation: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ConversationContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ConversationScrollButton: () => null,
}));

jest.mock("@/components/ai-elements/loader", () => ({
  Loader: () => <span>loading</span>,
}));

jest.mock("@/components/ai-elements/message", () => ({
  Message: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  MessageContent: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div className={className}>{children}</div>
  ),
  MessageResponse: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

jest.mock("@/components/ai-elements/tool", () => ({
  Tool: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ToolHeader: ({ title }: { title?: string }) => <div>{title}</div>,
  ToolContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ToolOutput: ({ output, errorText }: { output?: unknown; errorText?: string }) => (
    <pre>
      {errorText ||
        (typeof output === "string"
          ? output
          : output
            ? JSON.stringify(output)
            : "")}
    </pre>
  ),
}));

jest.mock("@/components/ai-elements/prompt-input", () => {
  const PromptInputTextarea = React.forwardRef(function PromptInputTextarea(
    props: React.ComponentPropsWithoutRef<"textarea">,
    ref: React.ForwardedRef<HTMLTextAreaElement>,
  ) {
    return <textarea ref={ref} name="message" {...props} />;
  });

  return {
    PromptInput: ({
      children,
      onSubmit,
      ...props
    }: {
      children: React.ReactNode;
      onSubmit: (message: { text: string; files: any[] }) => void | Promise<void>;
    }) => (
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const formData = new FormData(event.currentTarget);
          void onSubmit({ text: String(formData.get("message") || ""), files: [] });
        }}
        {...props}
      >
        {children}
      </form>
    ),
    PromptInputBody: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    PromptInputFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    PromptInputTools: () => <div />,
    PromptInputSubmit: ({ children, ...props }: React.ComponentPropsWithoutRef<"button">) => (
      <button type="submit" {...props}>
        {children || "Submit"}
      </button>
    ),
    PromptInputTextarea,
  };
});

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
    description: "Builder app description",
    logo_url: null,
    visibility: "public",
    auth_enabled: true,
    auth_providers: ["password"],
    auth_template_key: "auth-classic",
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
  let openSpy: jest.SpyInstance;

  const openConfigTab = async () => {
    const configTab = await screen.findByRole("tab", { name: "Config" });
    fireEvent.mouseDown(configTab);
    fireEvent.click(configTab);
    await screen.findByRole("button", { name: /^overview$/i });
  };

  const openCodeSection = async () => {
    await openConfigTab();
    fireEvent.click(screen.getByRole("button", { name: /^code$/i }));
    await screen.findByLabelText("Code Editor");
  };

  beforeEach(() => {
    openSpy = jest.spyOn(window, "open").mockImplementation(() => null);
    (publishedAppsService.getBuilderState as jest.Mock).mockResolvedValue(makeState());
    (publishedAppsService.listAuthTemplates as jest.Mock).mockResolvedValue([
      {
        key: "auth-classic",
        name: "Classic Auth",
        description: "Classic auth layout",
        thumbnail: "classic",
        tags: ["default"],
        style_tokens: {},
      },
      {
        key: "auth-split",
        name: "Split Auth",
        description: "Split auth layout",
        thumbnail: "split",
        tags: ["split"],
        style_tokens: {},
      },
    ]);
    (publishedAppsService.update as jest.Mock).mockResolvedValue(makeState().app);
    (publishedAppsService.listUsers as jest.Mock).mockResolvedValue([]);
    (publishedAppsService.updateUser as jest.Mock).mockResolvedValue({
      user_id: "user-1",
      email: "user@example.com",
      membership_status: "blocked",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      active_sessions: 0,
    });
    (publishedAppsService.listDomains as jest.Mock).mockResolvedValue([]);
    (publishedAppsService.createDomain as jest.Mock).mockResolvedValue({
      id: "domain-1",
      host: "app.example.com",
      status: "pending",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    (publishedAppsService.deleteDomain as jest.Mock).mockResolvedValue({ status: "deleted", id: "domain-1" });
    (publishedAppsService.listCodingAgentCheckpoints as jest.Mock).mockResolvedValue([
      {
        checkpoint_id: "rev-2",
        run_id: "run-1",
        app_id: "app-1",
        revision_id: "rev-2",
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
    (publishedAppsService.createRevisionPreviewToken as jest.Mock).mockResolvedValue({
      revision_id: "rev-3",
      preview_token: "published-preview-token",
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
    (publishedAppsService.createCodingAgentRun as jest.Mock).mockResolvedValue({
      run_id: "run-1",
      status: "queued",
      surface: "published_app_coding_agent",
      published_app_id: "app-1",
      base_revision_id: "rev-1",
      result_revision_id: null,
      checkpoint_revision_id: null,
      error: null,
      created_at: new Date().toISOString(),
      started_at: null,
      completed_at: null,
    });
    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValue({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"run.accepted","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"run","payload":{"status":"queued"},"diagnostics":[]}\n\n',
            'data: {"event":"assistant.delta","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:01Z","stage":"assistant","payload":{"content":"Applying patch"},"diagnostics":[]}\n\n',
            'data: {"event":"revision.created","run_id":"run-1","app_id":"app-1","seq":3,"ts":"2026-02-16T19:00:02Z","stage":"revision","payload":{"revision_id":"rev-2","file_count":4},"diagnostics":[]}\n\n',
            'data: {"event":"checkpoint.created","run_id":"run-1","app_id":"app-1","seq":4,"ts":"2026-02-16T19:00:03Z","stage":"checkpoint","payload":{"checkpoint_id":"rev-2","revision_id":"rev-2"},"diagnostics":[]}\n\n',
            'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":5,"ts":"2026-02-16T19:00:04Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "text/event-stream" }),
    });
    (publishedAppsService.restoreCodingAgentCheckpoint as jest.Mock).mockResolvedValue({
      checkpoint_id: "rev-2",
      revision: makeState().current_draft_revision,
      run_id: "run-1",
    });
    (publishedRuntimeService.getPreviewRuntime as jest.Mock).mockResolvedValue({
      app_id: "app-1",
      slug: "builder-app",
      revision_id: "rev-3",
      runtime_mode: "vite_static",
      preview_url:
        "http://127.0.0.1:8000/api/py/public/apps/preview/revisions/rev-3/assets/index.html?preview_token=published-preview-token",
      asset_base_url: "http://127.0.0.1:8000/api/py/public/apps/preview/revisions/rev-3/assets/",
      api_base_path: "/api/py",
    });
    jest.spyOn(window, "confirm").mockReturnValue(true);
  });

  afterEach(() => {
    openSpy.mockRestore();
    jest.clearAllMocks();
  });

  it("renders builder tabs and saves draft revision", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalledWith("app-1"));
    await screen.findByRole("tab", { name: "Preview" });
    expect(screen.getByRole("tab", { name: "Config" })).toBeInTheDocument();
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

  it("does not sync draft preview while ensure is still starting", async () => {
    let resolveEnsure: (value: unknown) => void = () => {};
    const pendingEnsure = new Promise((resolve) => {
      resolveEnsure = resolve;
    });
    (publishedAppsService.ensureDraftDevSession as jest.Mock).mockReturnValueOnce(pendingEnsure);

    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalledWith("app-1"));
    await waitFor(() => expect(publishedAppsService.ensureDraftDevSession).toHaveBeenCalledWith("app-1"));

    await new Promise((resolve) => setTimeout(resolve, 1200));
    expect(publishedAppsService.syncDraftDevSession).not.toHaveBeenCalled();

    resolveEnsure({
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

    await waitFor(() => {
      expect(screen.getByTitle("App Preview")).toHaveAttribute(
        "src",
        "https://preview.local/sandbox/session-1/",
      );
    });
  });

  it("reuses running draft preview session when switching tabs", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalledWith("app-1"));
    await waitFor(() => expect(publishedAppsService.ensureDraftDevSession).toHaveBeenCalledWith("app-1"));
    await waitFor(() =>
      expect(screen.getByTitle("App Preview")).toHaveAttribute("src", "https://preview.local/sandbox/session-1/"),
    );

    (publishedAppsService.ensureDraftDevSession as jest.Mock).mockClear();

    await openConfigTab();
    const previewTab = screen.getByRole("tab", { name: "Preview" });
    fireEvent.mouseDown(previewTab);
    fireEvent.click(previewTab);

    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(publishedAppsService.ensureDraftDevSession).not.toHaveBeenCalled();
    expect(screen.queryByText("Starting draft preview...")).not.toBeInTheDocument();
  });

  it("surfaces an immediate publish-job failure without polling", async () => {
    (publishedAppsService.publish as jest.Mock).mockResolvedValueOnce({
      job_id: "job-failed",
      app_id: "app-1",
      status: "failed",
      error: "Celery workers are running but publish task is missing",
      diagnostics: [{ message: "Celery workers are running but publish task is missing" }],
      created_at: new Date().toISOString(),
      started_at: null,
      finished_at: new Date().toISOString(),
    });

    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalledWith("app-1"));
    fireEvent.click(await screen.findByRole("button", { name: /publish/i }));

    await waitFor(() => {
      expect(screen.getByText("Celery workers are running but publish task is missing")).toBeInTheDocument();
    });
    expect(publishedAppsService.getPublishJobStatus).not.toHaveBeenCalled();
  });

  it("renders a hierarchical file tree and supports folder collapse/expand", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await openCodeSection();
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

    await openCodeSection();

    await waitFor(() => expect(screen.getByRole("button", { name: "Button.tsx" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "components" })).toBeInTheDocument();
  });

  it("uses html language mode and suppresses validation decorations in builder editor", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await openCodeSection();

    const editor = await screen.findByLabelText("Code Editor");
    expect(editor).toHaveAttribute("data-language", "html");
    expect(editor).toHaveAttribute("data-suppress-validation", "true");
  });

  it("saves overview settings from config section", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await openConfigTab();
    await screen.findByRole("heading", { name: "Overview" });

    fireEvent.change(screen.getByDisplayValue("Builder App"), { target: { value: "Builder App Updated" } });
    fireEvent.click(screen.getByRole("button", { name: /Save Overview/i }));

    await waitFor(() => {
      expect(publishedAppsService.update).toHaveBeenCalledWith(
        "app-1",
        expect.objectContaining({
          name: "Builder App Updated",
          visibility: "public",
          auth_template_key: "auth-classic",
        }),
      );
    });
  });

  it("loads users section and blocks a user", async () => {
    (publishedAppsService.listUsers as jest.Mock).mockResolvedValueOnce([
      {
        user_id: "user-1",
        email: "user@example.com",
        full_name: "User One",
        membership_status: "active",
        active_sessions: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]);
    (publishedAppsService.updateUser as jest.Mock).mockResolvedValueOnce({
      user_id: "user-1",
      email: "user@example.com",
      full_name: "User One",
      membership_status: "blocked",
      active_sessions: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    render(<AppsBuilderWorkspace appId="app-1" />);

    await openConfigTab();
    fireEvent.click(screen.getByRole("button", { name: /^users$/i }));

    await waitFor(() => expect(publishedAppsService.listUsers).toHaveBeenCalledWith("app-1"));
    await screen.findByText(/user@example.com/i);
    fireEvent.click(screen.getByRole("button", { name: /Block/i }));

    await waitFor(() => {
      expect(publishedAppsService.updateUser).toHaveBeenCalledWith(
        "app-1",
        "user-1",
        { membership_status: "blocked" },
      );
    });
  });

  it("loads domains section and creates a custom domain request", async () => {
    (publishedAppsService.listDomains as jest.Mock).mockResolvedValueOnce([]);
    (publishedAppsService.createDomain as jest.Mock).mockResolvedValueOnce({
      id: "domain-1",
      host: "app.example.com",
      status: "pending",
      notes: "Support domain",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    render(<AppsBuilderWorkspace appId="app-1" />);

    await openConfigTab();
    fireEvent.click(screen.getByRole("button", { name: /^domains$/i }));

    await waitFor(() => expect(publishedAppsService.listDomains).toHaveBeenCalledWith("app-1"));
    fireEvent.change(screen.getByPlaceholderText("app.example.com"), { target: { value: "app.example.com" } });
    fireEvent.change(screen.getByPlaceholderText("Notes (optional)"), { target: { value: "Support domain" } });
    fireEvent.click(screen.getByRole("button", { name: /Add Domain/i }));

    await waitFor(() => {
      expect(publishedAppsService.createDomain).toHaveBeenCalledWith(
        "app-1",
        { host: "app.example.com", notes: "Support domain" },
      );
    });
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
      expect(publishedAppsService.createCodingAgentRun).toHaveBeenCalledWith(
        "app-1",
        expect.objectContaining({ input: "Make it bold", base_revision_id: "rev-1" }),
      );
      expect(publishedAppsService.streamCodingAgentRun).toHaveBeenCalledWith("app-1", "run-1");
    });

    await waitFor(() => {
      expect(screen.getByText(/Revision created/i)).toBeInTheDocument();
      expect(screen.getByText(/Checkpoint created/i)).toBeInTheDocument();
    });
  });

  it("restores the latest coding-agent checkpoint from quick action", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    fireEvent.click(await screen.findByRole("button", { name: /Restore Last Checkpoint/i }));

    await waitFor(() => {
      expect(publishedAppsService.listCodingAgentCheckpoints).toHaveBeenCalledWith("app-1", 1);
      expect(publishedAppsService.restoreCodingAgentCheckpoint).toHaveBeenCalledWith(
        "app-1",
        "rev-2",
        { run_id: "run-1" },
      );
    });
  });

  it("opens draft preview when clicking Open Preview", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await waitFor(() => expect(publishedAppsService.ensureDraftDevSession).toHaveBeenCalled());
    (publishedAppsService.ensureDraftDevSession as jest.Mock).mockClear();
    openSpy.mockClear();

    fireEvent.click(screen.getByRole("button", { name: /open preview/i }));

    await waitFor(() => {
      expect(publishedAppsService.ensureDraftDevSession).toHaveBeenCalledWith("app-1");
      expect(window.open).toHaveBeenCalledWith(
        "https://preview.local/sandbox/session-1/",
        "_blank",
        "noopener,noreferrer",
      );
    });
  });

  it("opens published runtime URL when app is published", async () => {
    const publishedState = makeState();
    publishedState.app.status = "published";
    publishedState.app.published_url = "https://apps.example.com/support/";
    (publishedAppsService.getBuilderState as jest.Mock).mockResolvedValueOnce(publishedState);

    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByRole("button", { name: /open app/i });
    (publishedAppsService.ensureDraftDevSession as jest.Mock).mockClear();
    openSpy.mockClear();

    fireEvent.click(screen.getByRole("button", { name: /open app/i }));

    await waitFor(() => {
      expect(window.open).toHaveBeenCalledWith(
        "https://apps.example.com/support/",
        "_blank",
        "noopener,noreferrer",
      );
    });
    expect(publishedAppsService.ensureDraftDevSession).not.toHaveBeenCalled();
    expect(publishedRuntimeService.getPreviewRuntime).not.toHaveBeenCalled();
  });

  it("opens published revision via preview runtime proxy for local apps domains", async () => {
    const publishedState = makeState();
    publishedState.app.status = "published";
    publishedState.app.published_url = "https://support-app.apps.localhost";
    publishedState.app.current_published_revision_id = "rev-3";
    publishedState.preview_token = "preview-token";
    (publishedAppsService.getBuilderState as jest.Mock).mockResolvedValueOnce(publishedState);

    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByRole("button", { name: /open app/i });
    openSpy.mockClear();

    fireEvent.click(screen.getByRole("button", { name: /open app/i }));

    await waitFor(() => {
      expect(publishedAppsService.createRevisionPreviewToken).toHaveBeenCalledWith("app-1", "rev-3");
      expect(publishedRuntimeService.getPreviewRuntime).toHaveBeenCalledWith("rev-3", "published-preview-token");
      expect(window.open).toHaveBeenCalledWith(
        "http://127.0.0.1:8000/api/py/public/apps/preview/revisions/rev-3/assets/index.html?preview_token=published-preview-token",
        "_blank",
        "noopener,noreferrer",
      );
    });
  });

});
