import React from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { TextDecoder } from "util";

import { AppsBuilderWorkspace } from "@/features/apps-builder/workspace/AppsBuilderWorkspace";
import {
  listOpenCodeCodingModels,
  publishedAppsService,
  publishedRuntimeService,
  resolveAppsCodingAgentEngine,
} from "@/services";

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
    submitCodingAgentPrompt: jest.fn(),
    streamCodingAgentRun: jest.fn(),
    getCodingAgentRun: jest.fn(),
    cancelCodingAgentRun: jest.fn(),
    getCodingAgentCapabilities: jest.fn(),
    listCodingAgentChatSessions: jest.fn(),
    getCodingAgentChatSession: jest.fn(),
    getCodingAgentChatSessionActiveRun: jest.fn(),
    findCodingAgentChatSessionActiveRun: jest.fn(),
    listCodingAgentChatSessionQueue: jest.fn(),
    deleteCodingAgentChatSessionQueueItem: jest.fn(),
    restoreCodingAgentCheckpoint: jest.fn(),
  },
  resolveAppsCodingAgentEngine: jest.fn(() => "opencode"),
  publishedRuntimeService: {
    getPreviewRuntime: jest.fn(),
  },
  listOpenCodeCodingModels: jest.fn(),
}));

jest.mock("@/components/ui/sidebar", () => ({
  useSidebar: () => ({ setOpen: setOpenMock }),
}));

jest.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
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

jest.mock("@/components/ai-elements/task", () => ({
  Task: ({
    children,
    defaultOpen = true,
  }: {
    children: React.ReactNode;
    defaultOpen?: boolean;
  }) => {
    const [open, setOpen] = React.useState(Boolean(defaultOpen));
    return (
      <div data-open={open ? "true" : "false"}>
        {React.Children.map(children, (child) => {
          if (!React.isValidElement(child)) return child;
          return React.cloneElement(child as React.ReactElement<any>, { __taskOpen: open, __setTaskOpen: setOpen });
        })}
      </div>
    );
  },
  TaskTrigger: ({
    children,
    title,
    __taskOpen,
    __setTaskOpen,
  }: {
    children?: React.ReactNode;
    title: string;
    __taskOpen?: boolean;
    __setTaskOpen?: (next: boolean) => void;
  }) => {
    if (React.isValidElement(children)) {
      return React.cloneElement(children as React.ReactElement<any>, {
        onClick: (event: React.MouseEvent) => {
          (children as React.ReactElement<any>).props?.onClick?.(event);
          __setTaskOpen?.(!Boolean(__taskOpen));
        },
      });
    }
    return (
      <button type="button" onClick={() => __setTaskOpen?.(!Boolean(__taskOpen))}>
        {title}
      </button>
    );
  },
  TaskContent: ({
    children,
    __taskOpen,
  }: {
    children: React.ReactNode;
    __taskOpen?: boolean;
  }) => (Boolean(__taskOpen) ? <div>{children}</div> : null),
  TaskItem: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div className={className}>{children}</div>
  ),
  TaskItemFile: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));

jest.mock("@/components/ai-elements/shimmer", () => ({
  Shimmer: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <span data-shimmer className={className}>{children}</span>
  ),
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

jest.mock("@/components/ai-elements/model-selector", () => ({
  ModelSelector: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ModelSelectorTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  ModelSelectorContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ModelSelectorInput: (props: React.ComponentPropsWithoutRef<"input">) => <input {...props} />,
  ModelSelectorList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ModelSelectorEmpty: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ModelSelectorGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ModelSelectorItem: ({
    children,
    onSelect,
    value,
  }: {
    children: React.ReactNode;
    onSelect?: (value: string) => void;
    value?: string;
  }) => (
    <button type="button" onClick={() => onSelect?.(value || "")}>
      {children}
    </button>
  ),
  ModelSelectorName: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
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

const makeStreamResponse = (
  chunks: string[],
  options: { onCancel?: () => void } = {},
) => ({
  body: {
    getReader: () => {
      let cursor = 0;
      return {
        read: async () => {
          if (cursor >= chunks.length) return { done: true, value: undefined };
          const next = chunks[cursor++];
          return { done: false, value: new Uint8Array(Buffer.from(next, "utf-8")) };
        },
        cancel: async () => {
          options.onCancel?.();
        },
      };
    },
  },
  ok: true,
  status: 200,
  headers: new Headers({ "content-type": "text/event-stream" }),
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
    jest.resetAllMocks();
    window.localStorage.clear();
    openSpy = jest.spyOn(window, "open").mockImplementation(() => null);
    mockCodeEditor.mockImplementation(
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
      has_active_coding_runs: false,
      active_coding_run_count: 0,
      preview_url: "https://preview.local/sandbox/session-1/",
      preview_auth_token: "preview-auth-token-1",
      preview_auth_expires_at: new Date(Date.now() + 7200_000).toISOString(),
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
      has_active_coding_runs: false,
      active_coding_run_count: 0,
      preview_url: "https://preview.local/sandbox/session-1/",
      preview_auth_token: "preview-auth-token-1",
      preview_auth_expires_at: new Date(Date.now() + 7200_000).toISOString(),
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
      has_active_coding_runs: false,
      active_coding_run_count: 0,
      preview_url: "https://preview.local/sandbox/session-1/",
      preview_auth_token: "preview-auth-token-2",
      preview_auth_expires_at: new Date(Date.now() + 7200_000).toISOString(),
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
      execution_engine: "opencode",
      chat_session_id: null,
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
    (publishedAppsService.submitCodingAgentPrompt as jest.Mock).mockImplementation(
      async (appId: string, payload: Record<string, unknown>) => {
        const normalizedModelId = String(payload.model_id || "").trim() || "opencode/big-pickle";
        const legacyPayload = {
          ...payload,
          model_id: normalizedModelId,
          base_revision_id: "rev-1",
          engine: "opencode",
          enqueue_if_active: true,
        };
        const response = await (publishedAppsService.createCodingAgentRun as jest.Mock)(appId, legacyPayload);
        if (response && typeof response === "object" && "submission_status" in (response as Record<string, unknown>)) {
          return response;
        }
        if (response && typeof response === "object" && "active_run_id" in (response as Record<string, unknown>)) {
          return {
            submission_status: "queued",
            active_run_id: String((response as Record<string, unknown>).active_run_id || ""),
            queue_item: (response as Record<string, unknown>).queue_item,
          };
        }
        return {
          submission_status: "started",
          run: response,
        };
      },
    );
    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValue({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"run.accepted","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"run","payload":{"status":"queued"},"diagnostics":[]}\n\n',
            'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:00Z","stage":"tool","payload":{"tool":"write_file","span_id":"call-1","input":{"path":"src/App.tsx"}},"diagnostics":[]}\n\n',
            'data: {"event":"assistant.delta","run_id":"run-1","app_id":"app-1","seq":3,"ts":"2026-02-16T19:00:01Z","stage":"assistant","payload":{"content":"Applying patch"},"diagnostics":[]}\n\n',
            'data: {"event":"tool.completed","run_id":"run-1","app_id":"app-1","seq":4,"ts":"2026-02-16T19:00:01Z","stage":"tool","payload":{"tool":"write_file","span_id":"call-1","output":{"ok":true}},"diagnostics":[]}\n\n',
            'data: {"event":"revision.created","run_id":"run-1","app_id":"app-1","seq":5,"ts":"2026-02-16T19:00:02Z","stage":"revision","payload":{"revision_id":"rev-2","file_count":4},"diagnostics":[]}\n\n',
            'data: {"event":"checkpoint.created","run_id":"run-1","app_id":"app-1","seq":6,"ts":"2026-02-16T19:00:03Z","stage":"checkpoint","payload":{"checkpoint_id":"rev-2","revision_id":"rev-2"},"diagnostics":[]}\n\n',
            'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":7,"ts":"2026-02-16T19:00:04Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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
    (publishedAppsService.cancelCodingAgentRun as jest.Mock).mockResolvedValue({
      run_id: "run-1",
      status: "cancelled",
      execution_engine: "opencode",
      chat_session_id: null,
      surface: "published_app_coding_agent",
      published_app_id: "app-1",
      base_revision_id: "rev-1",
      result_revision_id: null,
      checkpoint_revision_id: null,
      error: null,
      created_at: new Date().toISOString(),
      started_at: new Date().toISOString(),
      completed_at: new Date().toISOString(),
    });
    (publishedAppsService.getCodingAgentRun as jest.Mock).mockResolvedValue({
      run_id: "run-1",
      status: "completed",
      execution_engine: "opencode",
      chat_session_id: null,
      surface: "published_app_coding_agent",
      published_app_id: "app-1",
      base_revision_id: "rev-1",
      result_revision_id: null,
      checkpoint_revision_id: null,
      error: null,
      created_at: new Date().toISOString(),
      started_at: new Date().toISOString(),
      completed_at: new Date().toISOString(),
    });
    (publishedAppsService.getCodingAgentCapabilities as jest.Mock).mockResolvedValue({
      app_id: "app-1",
      default_engine: "opencode",
      native_enabled: false,
      native_tool_count: 16,
      native_tools: [],
      opencode_policy: {
        tooling_mode: "delegated_to_upstream_opencode",
        repo_tool_allowlist_configured: false,
        workspace_permission_model: "external_directory_allow_patterns",
        summary: "Delegated tools",
      },
    });
    (publishedAppsService.listCodingAgentChatSessions as jest.Mock).mockResolvedValue([]);
    (publishedAppsService.getCodingAgentChatSession as jest.Mock).mockResolvedValue({
      session: {
        id: "chat-1",
        title: "Initial chat",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        last_message_at: new Date().toISOString(),
      },
      messages: [],
      run_events: [],
      paging: {
        has_more: false,
        next_before_message_id: null,
      },
    });
    (publishedAppsService.getCodingAgentChatSessionActiveRun as jest.Mock).mockRejectedValue(
      new Error("No active run"),
    );
    (publishedAppsService.findCodingAgentChatSessionActiveRun as jest.Mock).mockResolvedValue(null);
    (publishedAppsService.listCodingAgentChatSessionQueue as jest.Mock).mockResolvedValue([]);
    (publishedAppsService.deleteCodingAgentChatSessionQueueItem as jest.Mock).mockResolvedValue({
      status: "deleted",
      id: "queue-1",
    });
    (resolveAppsCodingAgentEngine as jest.Mock).mockReturnValue("opencode");
    (listOpenCodeCodingModels as jest.Mock).mockReturnValue([
      { id: "opencode/big-pickle", name: "Big Pickle", is_free: true },
      { id: "opencode/minimax-m2.5-free", name: "MiniMax M2.5 Free", is_free: true },
      { id: "opencode/gpt-5", name: "GPT 5", is_free: false },
    ]);
    (publishedRuntimeService.getPreviewRuntime as jest.Mock).mockResolvedValue({
      app_id: "app-1",
      slug: "builder-app",
      revision_id: "rev-3",
      runtime_mode: "vite_static",
      preview_url: "http://127.0.0.1:8000/api/py/public/apps/preview/revisions/rev-3/assets/index.html",
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

  it("renders a shell skeleton during the first builder-state fetch", async () => {
    let resolveState: (value: unknown) => void = () => {};
    const pendingState = new Promise((resolve) => {
      resolveState = resolve;
    });
    (publishedAppsService.getBuilderState as jest.Mock).mockReturnValueOnce(pendingState);

    render(<AppsBuilderWorkspace appId="app-1" />);

    expect(screen.getByTestId("apps-builder-boot-skeleton")).toBeInTheDocument();
    expect(screen.queryByText("Loading builder...")).not.toBeInTheDocument();

    resolveState(makeState());

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Preview" })).toBeInTheDocument();
    });
  });

  it("keeps the builder shell viewport-bounded for internal chat scrolling", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalledWith("app-1"));
    const tabsRoot = screen.getByRole("tab", { name: "Preview" }).closest("[data-slot='tabs']");
    expect(tabsRoot).toHaveClass("h-dvh", "min-h-0", "overflow-hidden");
    expect(tabsRoot).not.toHaveClass("h-screen");

    const agentPanel = screen.getByRole("button", { name: "Create new chat" }).closest("aside");
    expect(agentPanel).toHaveClass("min-h-0", "overflow-hidden");
  });

  it("shows section skeletons while users and domains are loading", async () => {
    let resolveUsers: (value: unknown) => void = () => {};
    let resolveDomains: (value: unknown) => void = () => {};
    (publishedAppsService.listUsers as jest.Mock).mockReturnValueOnce(
      new Promise((resolve) => {
        resolveUsers = resolve;
      }),
    );
    (publishedAppsService.listDomains as jest.Mock).mockReturnValueOnce(
      new Promise((resolve) => {
        resolveDomains = resolve;
      }),
    );

    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalledWith("app-1"));
    await openConfigTab();

    fireEvent.click(screen.getByRole("button", { name: /^users$/i }));
    expect(await screen.findByTestId("apps-builder-users-skeleton")).toBeInTheDocument();

    resolveUsers([]);
    await waitFor(() => {
      expect(screen.queryByTestId("apps-builder-users-skeleton")).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /^domains$/i }));
    expect(await screen.findByTestId("apps-builder-domains-skeleton")).toBeInTheDocument();

    resolveDomains([]);
    await waitFor(() => {
      expect(screen.queryByTestId("apps-builder-domains-skeleton")).not.toBeInTheDocument();
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
      has_active_coding_runs: false,
      active_coding_run_count: 0,
      preview_url: "https://preview.local/sandbox/session-1/",
      preview_auth_token: "preview-auth-token-1",
      preview_auth_expires_at: new Date(Date.now() + 7200_000).toISOString(),
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

  it("retries transient sandbox-not-running errors before surfacing preview failure", async () => {
    (publishedAppsService.ensureDraftDevSession as jest.Mock)
      .mockRejectedValueOnce(
        new Error('Draft dev controller request failed (400): {"detail":"Draft dev sandbox is not running"}'),
      )
      .mockResolvedValueOnce({
        session_id: "session-1",
        app_id: "app-1",
        revision_id: "rev-1",
        status: "running",
        has_active_coding_runs: false,
        active_coding_run_count: 0,
        preview_url: "https://preview.local/sandbox/session-1/",
        preview_auth_token: "preview-auth-token-1",
        preview_auth_expires_at: new Date(Date.now() + 7200_000).toISOString(),
        idle_timeout_seconds: 180,
        last_activity_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 180_000).toISOString(),
        last_error: null,
      });

    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalledWith("app-1"));
    await waitFor(() => expect(publishedAppsService.ensureDraftDevSession).toHaveBeenCalledTimes(2));
    expect(screen.queryByText("Draft dev sandbox is not running")).not.toBeInTheDocument();
    expect(await screen.findByTestId("preview-warmup-overlay")).toBeInTheDocument();
  });

  it("keeps preview iframe hidden until warmup completes", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalledWith("app-1"));
    await waitFor(() => expect(publishedAppsService.ensureDraftDevSession).toHaveBeenCalledWith("app-1"));

    const previewFrame = await screen.findByTestId("preview-iframe");
    expect(previewFrame).toHaveClass("opacity-0");
    expect(screen.getByTestId("preview-warmup-overlay")).toBeInTheDocument();

    fireEvent.load(previewFrame);

    await waitFor(
      () => {
        expect(previewFrame).toHaveClass("opacity-100");
      },
      { timeout: 1500 },
    );
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

  it("keeps preview iframe src stable when heartbeat rotates preview auth token", async () => {
    jest.useFakeTimers();
    try {
      render(<AppsBuilderWorkspace appId="app-1" />);

      await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalledWith("app-1"));
      await waitFor(() => expect(publishedAppsService.ensureDraftDevSession).toHaveBeenCalledWith("app-1"));
      const previewFrame = await screen.findByTitle("App Preview");
      const initialSrc = previewFrame.getAttribute("src");

      await act(async () => {
        jest.advanceTimersByTime(45_100);
      });

      await waitFor(() => expect(publishedAppsService.heartbeatDraftDevSession).toHaveBeenCalled());
      expect(previewFrame).toHaveAttribute("src", initialSrc || "");
    } finally {
      jest.useRealTimers();
    }
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
    await screen.findByDisplayValue("Builder App");

    fireEvent.change(screen.getByDisplayValue("Builder App"), { target: { value: "Builder App Updated" } });
    fireEvent.click(screen.getByRole("button", { name: /Save Changes/i }));

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
    fireEvent.click(screen.getByRole("button", { name: /^Add$/i }));

    await waitFor(() => {
      expect(publishedAppsService.createDomain).toHaveBeenCalledWith(
        "app-1",
        { host: "app.example.com", notes: "Support domain" },
      );
    });
  });

  it("renders template switch control", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    expect(await screen.findByRole("button", { name: /template/i })).toBeInTheDocument();
  });

  it("streams coding-agent run with assistant response and tool calls only", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "Make it bold" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(publishedAppsService.createCodingAgentRun).toHaveBeenCalledWith(
        "app-1",
        expect.objectContaining({ input: "Make it bold", base_revision_id: "rev-1", engine: "opencode" }),
      );
      expect(publishedAppsService.streamCodingAgentRun).toHaveBeenCalledWith("app-1", "run-1");
    });

    await waitFor(() => {
      expect(screen.getByText("Edited src/App.tsx")).toBeInTheDocument();
      expect(screen.getByText("Applying patch")).toBeInTheDocument();
    });
    expect(screen.queryByText(/Revision created/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Checkpoint created/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/revision_id/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Run accepted/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Run complete/i)).not.toBeInTheDocument();
  });

  it("surfaces revision conflict without automatic retry", async () => {
    (publishedAppsService.createCodingAgentRun as jest.Mock)
      .mockRejectedValueOnce(
        new Error(
          JSON.stringify({
            code: "REVISION_CONFLICT",
            latest_revision_id: "rev-2",
            latest_updated_at: "2026-02-17T12:48:04.089449+00:00",
            message: "Draft revision is stale",
          }),
        ),
      );

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "change button color" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(publishedAppsService.createCodingAgentRun).toHaveBeenCalledTimes(1);
    });
    expect((publishedAppsService.createCodingAgentRun as jest.Mock).mock.calls[0][1]).toEqual(
      expect.objectContaining({ base_revision_id: "rev-1" }),
    );
    expect(publishedAppsService.streamCodingAgentRun).not.toHaveBeenCalled();
  });

  it("shows running read calls with researching summary + file-specific title", async () => {
    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValueOnce({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"run.accepted","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"run","payload":{"status":"queued"},"diagnostics":[]}\n\n',
            'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:00Z","stage":"tool","payload":{"tool":"read","span_id":"call-2","input":{"path":"src/main.tsx"}},"diagnostics":[]}\n\n',
            'data: {"event":"assistant.delta","run_id":"run-1","app_id":"app-1","seq":3,"ts":"2026-02-16T19:00:01Z","stage":"assistant","payload":{"content":"Working on it"},"diagnostics":[]}\n\n',
            'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":4,"ts":"2026-02-16T19:00:01Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "inspect files" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    const exploringHeader = await screen.findByRole("button", { name: "Exploring 1 file" });
    expect(exploringHeader).toBeInTheDocument();
    expect(screen.queryByText("Reading file src/main.tsx")).not.toBeInTheDocument();
    fireEvent.click(exploringHeader);
    expect(screen.getByText("Reading file src/main.tsx")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Exploring 1 file" }).closest("[data-shimmer]")).toBeNull();
    });
  });

  it("shows filename for read calls when input wraps path under args JSON", async () => {
    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValueOnce({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"tool","payload":{"tool":"read","span_id":"call-1","input":{"args":"{\\"file_path\\":\\"src/utils/parser.ts\\"}"}},"diagnostics":[]}\n\n',
            'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:01Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "inspect parser" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    const exploringHeader = await screen.findByRole("button", { name: "Exploring 1 file" });
    fireEvent.click(exploringHeader);
    expect(screen.getByText("Reading file src/utils/parser.ts")).toBeInTheDocument();
  });

  it("sanitizes wrapped and malformed path wrappers and ignores package specifiers in read titles", async () => {
    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValueOnce({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"tool","payload":{"tool":"read","span_id":"call-1","input":{"path":"path>/private/tmp/talmudpedia-draft-dev/sandbox/.talmudpedia/stage/run-1/workspace</path"}},"diagnostics":[]}\n\n',
            'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:01Z","stage":"tool","payload":{"tool":"read","span_id":"call-2","input":{"path":"<path>/private/tmp/talmudpedia-draft-dev/sandbox/.talmudpedia/stage/run-1/workspace/src/App.tsx</path>"}},"diagnostics":[]}\n\n',
            'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":3,"ts":"2026-02-16T19:00:01Z","stage":"tool","payload":{"tool":"read","span_id":"call-3","input":{"path":"/private/tmp/talmudpedia-draft-dev/sandbox/.talmudpedia/stage/run-1/workspace/src</path"}},"diagnostics":[]}\n\n',
            'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":4,"ts":"2026-02-16T19:00:01Z","stage":"tool","payload":{"tool":"read","span_id":"call-4","input":{"path":"@radix-ui/react-slot"}},"diagnostics":[]}\n\n',
            'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":5,"ts":"2026-02-16T19:00:02Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "inspect path labels" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    const exploringHeader = await screen.findByRole("button", { name: "Exploring 4 files" });
    expect(exploringHeader.className).toContain("px-0");
    expect(exploringHeader.className).not.toContain("px-1");
    fireEvent.click(exploringHeader);
    expect(screen.getByText("Reading file workspace")).toBeInTheDocument();
    expect(screen.getByText("Reading file src")).toBeInTheDocument();
    expect(screen.getByText("Reading file src/App.tsx")).toBeInTheDocument();
    expect(screen.queryByText(/path>\/private\/tmp/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/<\/path/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/@radix-ui\/react-slot/i)).not.toBeInTheDocument();
  });

  it("keeps researching header persistent and stops shimmer after streak completion", async () => {
    let releaseSecondRead: () => void = () => undefined;
    const secondReadGate = new Promise<void>((resolve) => {
      releaseSecondRead = resolve;
    });

    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValueOnce({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"tool","payload":{"tool":"read","span_id":"call-1","input":{"path":"src/main.tsx"}},"diagnostics":[]}\n\n',
            'data: {"event":"tool.completed","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:00Z","stage":"tool","payload":{"tool":"read","span_id":"call-1","output":{"path":"src/main.tsx"}},"diagnostics":[]}\n\n',
            'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":3,"ts":"2026-02-16T19:00:01Z","stage":"tool","payload":{"tool":"read","span_id":"call-2","input":{"path":"src/App.tsx"}},"diagnostics":[]}\n\n',
            'data: {"event":"tool.completed","run_id":"run-1","app_id":"app-1","seq":4,"ts":"2026-02-16T19:00:02Z","stage":"tool","payload":{"tool":"read","span_id":"call-2","output":{"path":"src/App.tsx"}},"diagnostics":[]}\n\n',
            'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":5,"ts":"2026-02-16T19:00:03Z","stage":"tool","payload":{"tool":"write_file","span_id":"call-3","input":{"path":"src/App.tsx"}},"diagnostics":[]}\n\n',
            'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":6,"ts":"2026-02-16T19:00:04Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
          ];
          let cursor = 0;
          return {
            read: async () => {
              if (cursor === 3) {
                await secondReadGate;
              }
              if (cursor >= chunks.length) return { done: true, value: undefined };
              const next = chunks[cursor++];
              return { done: false, value: new Uint8Array(Buffer.from(next, "utf-8")) };
            },
            cancel: async () => undefined,
          };
        },
      },
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "text/event-stream" }),
    });

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "inspect then edit" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    const exploringHeader = await screen.findByRole("button", { name: "Exploring 2 files" });
    fireEvent.click(exploringHeader);
    expect(screen.getByText("Reading file src/App.tsx")).toBeInTheDocument();

    releaseSecondRead();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Exploring 2 files" })).toBeInTheDocument();
    });
    const persistedHeader = screen.getByRole("button", { name: "Exploring 2 files" });
    expect(persistedHeader.closest("[data-shimmer]")).toBeNull();
    await waitFor(() => {
      expect(screen.getByText("Editing src/App.tsx")).toBeInTheDocument();
    });
  });

  it("groups search and read tools under a single exploring section", async () => {
    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValueOnce({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"tool","payload":{"tool":"grep","span_id":"call-1","input":{"pattern":"consumeRunStream","path":"frontend-reshet/src/features/apps-builder/workspace/chat"}},"diagnostics":[]}\n\n',
            'data: {"event":"tool.completed","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:00Z","stage":"tool","payload":{"tool":"grep","span_id":"call-1","output":{"title":"consumeRunStream"}},"diagnostics":[]}\n\n',
            'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":3,"ts":"2026-02-16T19:00:01Z","stage":"tool","payload":{"tool":"read","span_id":"call-2","input":{"path":"src/main.tsx"}},"diagnostics":[]}\n\n',
            'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":4,"ts":"2026-02-16T19:00:02Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "explore files" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    const exploringHeader = await screen.findByRole("button", { name: "Exploring 1 file, 1 search" });
    fireEvent.click(exploringHeader);
    expect(screen.getByText("Searching code consumeRunStream")).toBeInTheDocument();
    expect(screen.getByText("Reading file src/main.tsx")).toBeInTheDocument();
  });

  it("does not render bash stacktrace paths as command file labels", async () => {
    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValueOnce({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"tool","payload":{"tool":"bash","span_id":"call-1","input":{"description":"Run parser test","command":"node -e \\"throw new Error(\'boom\')\\""}},"diagnostics":[]}\n\n',
            'data: {"event":"tool.completed","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:01Z","stage":"tool","payload":{"tool":"bash","span_id":"call-1","output":"Error: boom\\n    at lib/parser.js:454:16\\n    at chunks/dep-CDnG8rE7.js:36141:11\\n"},"diagnostics":[]}\n\n',
            'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":3,"ts":"2026-02-16T19:00:02Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "run parser test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("Running command");
    expect(screen.queryByText("lib/parser.js:454:16")).not.toBeInTheDocument();
    expect(screen.queryByText("chunks/dep-CDnG8rE7.js:36141:11")).not.toBeInTheDocument();
  });

  it("does not render command output package banner as a file label", async () => {
    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValueOnce({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"tool","payload":{"tool":"command","span_id":"call-1","input":{"command":"npm run build"}},"diagnostics":[]}\n\n',
            'data: {"event":"tool.completed","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:01Z","stage":"tool","payload":{"tool":"command","span_id":"call-1","output":"talmudpedia-published-app-template@0.0.1"},"diagnostics":[]}\n\n',
            'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":3,"ts":"2026-02-16T19:00:02Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "run build" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("Running command");
    expect(screen.queryByText("talmudpedia-published-app-template@0.0.1")).not.toBeInTheDocument();
  });

  it("keeps command title semantics from run to ran on completion", async () => {
    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValueOnce({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"tool","payload":{"tool":"bash","span_id":"call-1","input":{"description":"Run TypeScript type checking","command":"npm run typecheck"}},"diagnostics":[]}\n\n',
            'data: {"event":"tool.completed","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:01Z","stage":"tool","payload":{"tool":"bash","span_id":"call-1","output":"talmudpedia-published-app-template@0.0.1"},"diagnostics":[]}\n\n',
            'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":3,"ts":"2026-02-16T19:00:02Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "run typecheck" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("Ran TypeScript type checking");
    expect(screen.queryByText("Run TypeScript type checking")).not.toBeInTheDocument();
    expect(screen.queryByText("talmudpedia-published-app-template@0.0.1")).not.toBeInTheDocument();
  });

  it("renders chat input without capabilities endpoint dependency", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    expect(publishedAppsService.getCodingAgentCapabilities).not.toHaveBeenCalled();
    expect(screen.getByPlaceholderText("Plan, @ for context, / for commands")).toBeInTheDocument();
  });

  it("queues a prompt while run is active and supports removing queued items", async () => {
    let released = false;
    let releaseFirstRun: () => void = () => undefined;
    const firstRunGate = new Promise<void>((resolve) => {
      releaseFirstRun = () => {
        released = true;
        resolve();
      };
    });

    (publishedAppsService.createCodingAgentRun as jest.Mock)
      .mockResolvedValueOnce({
        run_id: "run-1",
        status: "queued",
        execution_engine: "opencode",
        chat_session_id: "chat-1",
        surface: "published_app_coding_agent",
        published_app_id: "app-1",
        base_revision_id: "rev-1",
        result_revision_id: null,
        checkpoint_revision_id: null,
        error: null,
        created_at: new Date().toISOString(),
        started_at: null,
        completed_at: null,
      })
      .mockResolvedValueOnce({
        run_id: "run-1",
        status: "running",
        execution_engine: "opencode",
        chat_session_id: "chat-1",
        surface: "published_app_coding_agent",
        published_app_id: "app-1",
        base_revision_id: "rev-1",
        result_revision_id: null,
        checkpoint_revision_id: null,
        error: null,
        created_at: new Date().toISOString(),
        started_at: new Date().toISOString(),
        completed_at: null,
      });
    (publishedAppsService.listCodingAgentChatSessionQueue as jest.Mock)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          id: "queue-1",
          chat_session_id: "chat-1",
          position: 1,
          status: "queued",
          input: "queued task",
          created_at: new Date().toISOString(),
          started_at: null,
          finished_at: null,
          error: null,
        },
      ])
      .mockResolvedValueOnce([]);
    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValueOnce({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"tool","payload":{"tool":"read","span_id":"call-2","input":{"path":"src/main.tsx"}},"diagnostics":[]}\n\n',
            'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:01Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
          ];
          let cursor = 0;
          return {
            read: async () => {
              if (cursor === 1 && !released) {
                await firstRunGate;
              }
              if (cursor >= chunks.length) return { done: true, value: undefined };
              const next = chunks[cursor++];
              return { done: false, value: new Uint8Array(Buffer.from(next, "utf-8")) };
            },
            cancel: async () => undefined,
          };
        },
      },
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "text/event-stream" }),
    });

    try {
      render(<AppsBuilderWorkspace appId="app-1" />);
      await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
      await screen.findByPlaceholderText("Plan, @ for context, / for commands");

      fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
        target: { value: "first task" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Send" }));
      await waitFor(() => expect(publishedAppsService.createCodingAgentRun).toHaveBeenCalledTimes(1));

      fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
        target: { value: "queued task" },
      });
      fireEvent.submit(screen.getByPlaceholderText("Plan, @ for context, / for commands").closest("form")!);

      const queuePanel = await screen.findByRole("region", { name: "Queued prompts" });
      expect(within(queuePanel).getByText("queued task")).toBeInTheDocument();
      expect(screen.queryAllByText("queued task")).toHaveLength(1);
      fireEvent.click(screen.getByRole("button", { name: "Remove queued prompt" }));
      await waitFor(() => {
        expect(screen.queryByRole("button", { name: "Remove queued prompt" })).not.toBeInTheDocument();
      });
      expect(publishedAppsService.deleteCodingAgentChatSessionQueueItem).not.toHaveBeenCalled();
      expect(screen.queryByRole("region", { name: "Queued prompts" })).not.toBeInTheDocument();
      expect(screen.queryByText("queued task")).not.toBeInTheDocument();
    } finally {
      releaseFirstRun();
    }
  });

  it("stops active run via cancel endpoint and continues with queued prompt", async () => {
    let firstRunReleased = false;
    let releaseFirstRun: () => void = () => undefined;
    const firstRunGate = new Promise<void>((resolve) => {
      releaseFirstRun = () => {
        firstRunReleased = true;
        resolve();
      };
    });

    (publishedAppsService.createCodingAgentRun as jest.Mock)
      .mockResolvedValueOnce({
        run_id: "run-1",
        status: "queued",
        execution_engine: "opencode",
        chat_session_id: "chat-1",
        surface: "published_app_coding_agent",
        published_app_id: "app-1",
        base_revision_id: "rev-1",
        result_revision_id: null,
        checkpoint_revision_id: null,
        error: null,
        created_at: new Date().toISOString(),
        started_at: null,
        completed_at: null,
      })
      .mockResolvedValueOnce({
        run_id: "run-1",
        status: "running",
        execution_engine: "opencode",
        chat_session_id: "chat-1",
        surface: "published_app_coding_agent",
        published_app_id: "app-1",
        base_revision_id: "rev-1",
        result_revision_id: null,
        checkpoint_revision_id: null,
        error: null,
        created_at: new Date().toISOString(),
        started_at: new Date().toISOString(),
        completed_at: null,
      });
    (publishedAppsService.listCodingAgentChatSessionQueue as jest.Mock)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          id: "queue-2",
          chat_session_id: "chat-1",
          position: 1,
          status: "queued",
          input: "second queued",
          created_at: new Date().toISOString(),
          started_at: null,
          finished_at: null,
          error: null,
        },
      ]);

    (publishedAppsService.streamCodingAgentRun as jest.Mock)
      .mockResolvedValueOnce({
        body: {
          getReader: () => {
            const chunks = [
              'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"tool","payload":{"tool":"read","span_id":"call-1","input":{"path":"src/main.tsx"}},"diagnostics":[]}\n\n',
            ];
            let cursor = 0;
            return {
              read: async () => {
                if (cursor === 1 && !firstRunReleased) {
                  await firstRunGate;
                }
                if (cursor >= chunks.length) return { done: true, value: undefined };
                const next = chunks[cursor++];
                return { done: false, value: new Uint8Array(Buffer.from(next, "utf-8")) };
              },
              cancel: async () => {
                releaseFirstRun();
              },
            };
          },
        },
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "text/event-stream" }),
      });

    try {
      render(<AppsBuilderWorkspace appId="app-1" />);
      await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
      await screen.findByPlaceholderText("Plan, @ for context, / for commands");

      fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
        target: { value: "first run" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Send" }));
      await waitFor(() => expect(publishedAppsService.createCodingAgentRun).toHaveBeenCalledTimes(1));

      fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
        target: { value: "second queued" },
      });
      fireEvent.submit(screen.getByPlaceholderText("Plan, @ for context, / for commands").closest("form")!);
      const queuePanel = await screen.findByRole("region", { name: "Queued prompts" });
      expect(within(queuePanel).getByText("second queued")).toBeInTheDocument();
      expect(screen.queryAllByText("second queued")).toHaveLength(1);

      fireEvent.click(await screen.findByRole("button", { name: "Stop" }));
      await waitFor(() => {
        expect(publishedAppsService.cancelCodingAgentRun).toHaveBeenCalledWith("app-1", "run-1");
      });

      await waitFor(() => expect(publishedAppsService.createCodingAgentRun).toHaveBeenCalledTimes(2));
      expect((publishedAppsService.createCodingAgentRun as jest.Mock).mock.calls[1][1]).toEqual(
        expect.objectContaining({ input: "second queued", enqueue_if_active: true, chat_session_id: "chat-1" }),
      );
    } finally {
      releaseFirstRun();
    }
  });

  it("continues local queued prompts when stream misses terminal event", async () => {
    const originalStallTimeout = process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_STALL_TIMEOUT_MS;
    const originalMaxDuration = process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_MAX_DURATION_MS;
    const originalReadPoll = process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_READ_POLL_TIMEOUT_MS;
    const originalAutoCancelRecovery = process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_AUTO_CANCEL_RECOVERY_ENABLED;
    process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_STALL_TIMEOUT_MS = "60";
    process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_MAX_DURATION_MS = "500";
    process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_READ_POLL_TIMEOUT_MS = "20";
    process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_AUTO_CANCEL_RECOVERY_ENABLED = "0";

    let unmount: (() => void) | null = null;
    try {
      (publishedAppsService.createCodingAgentRun as jest.Mock)
        .mockResolvedValueOnce({
          run_id: "run-1",
          status: "queued",
          execution_engine: "opencode",
          chat_session_id: "chat-1",
          surface: "published_app_coding_agent",
          published_app_id: "app-1",
          base_revision_id: "rev-1",
          result_revision_id: null,
          checkpoint_revision_id: null,
          error: null,
          created_at: new Date().toISOString(),
          started_at: null,
          completed_at: null,
        })
        .mockResolvedValueOnce({
          run_id: "run-1",
          status: "running",
          execution_engine: "opencode",
          chat_session_id: "chat-1",
          surface: "published_app_coding_agent",
          published_app_id: "app-1",
          base_revision_id: "rev-1",
          result_revision_id: null,
          checkpoint_revision_id: null,
          error: null,
          created_at: new Date().toISOString(),
          started_at: new Date().toISOString(),
          completed_at: null,
        });

      (publishedAppsService.listCodingAgentChatSessionQueue as jest.Mock)
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([
          {
            id: "queue-3",
            chat_session_id: "chat-1",
            position: 1,
            status: "queued",
            input: "second queued after stall",
            created_at: new Date().toISOString(),
            started_at: null,
            finished_at: null,
            error: null,
          },
        ])
        .mockResolvedValueOnce([
          {
            id: "queue-3",
            chat_session_id: "chat-1",
            position: 1,
            status: "queued",
            input: "second queued after stall",
            created_at: new Date().toISOString(),
            started_at: null,
            finished_at: null,
            error: null,
          },
        ]);

      const neverSettledRead = new Promise<ReadableStreamReadResult<Uint8Array>>(() => undefined);
      (publishedAppsService.streamCodingAgentRun as jest.Mock)
        .mockResolvedValueOnce({
          body: {
            getReader: () => {
              let emittedFirstChunk = false;
              return {
                read: async () => {
                  if (!emittedFirstChunk) {
                    emittedFirstChunk = true;
                    const firstChunk =
                      'data: {"event":"assistant.delta","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-22T19:00:00Z","stage":"assistant","payload":{"content":"first partial"},"diagnostics":[]}\n\n';
                    return { done: false, value: new Uint8Array(Buffer.from(firstChunk, "utf-8")) };
                  }
                  return neverSettledRead;
                },
                cancel: async () => undefined,
              };
            },
          },
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "text/event-stream" }),
        });

      const view = render(<AppsBuilderWorkspace appId="app-1" />);
      unmount = view.unmount;
      await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
      await screen.findByPlaceholderText("Plan, @ for context, / for commands");

      fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
        target: { value: "first stalled run" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Send" }));

      await screen.findByText("first partial");
      fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
        target: { value: "second queued after stall" },
      });
      fireEvent.submit(screen.getByPlaceholderText("Plan, @ for context, / for commands").closest("form")!);
      const queuePanel = await screen.findByRole("region", { name: "Queued prompts" });
      expect(within(queuePanel).getByText("second queued after stall")).toBeInTheDocument();

      expect(publishedAppsService.createCodingAgentRun).toHaveBeenCalledTimes(1);
      expect(publishedAppsService.streamCodingAgentRun).toHaveBeenCalledTimes(1);
      expect(publishedAppsService.cancelCodingAgentRun).not.toHaveBeenCalled();
    } finally {
      unmount?.();
      await new Promise((resolve) => setTimeout(resolve, 40));
      process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_STALL_TIMEOUT_MS = originalStallTimeout;
      process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_MAX_DURATION_MS = originalMaxDuration;
      process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_READ_POLL_TIMEOUT_MS = originalReadPoll;
      process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_AUTO_CANCEL_RECOVERY_ENABLED = originalAutoCancelRecovery;
    }
  });

  it("still sends cancel when stop is clicked before create-run returns a run id", async () => {
    let resolveRun: ((value: unknown) => void) | null = null;
    const createRunGate = new Promise((resolve) => {
      resolveRun = resolve;
    });

    (publishedAppsService.createCodingAgentRun as jest.Mock).mockImplementationOnce(() => createRunGate);
    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "cancel early" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    fireEvent.click(await screen.findByRole("button", { name: "Stop" }));

    resolveRun?.({
      run_id: "run-pending",
      status: "queued",
      execution_engine: "opencode",
      chat_session_id: null,
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

    await waitFor(() => {
      expect(publishedAppsService.cancelCodingAgentRun).toHaveBeenCalledWith("app-1", "run-pending");
    });
    expect(publishedAppsService.streamCodingAgentRun).not.toHaveBeenCalledWith("app-1", "run-pending");
  });

  it("renders user message immediately before create-run resolves", async () => {
    let resolveRun: ((value: unknown) => void) | null = null;
    const createRunGate = new Promise((resolve) => {
      resolveRun = resolve;
    });
    (publishedAppsService.createCodingAgentRun as jest.Mock).mockImplementationOnce(() => createRunGate);

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "instant bubble" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect((await screen.findAllByText("instant bubble")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Sending...")).toBeInTheDocument();

    resolveRun?.({
      run_id: "run-pending-ui",
      status: "queued",
      execution_engine: "opencode",
      chat_session_id: "chat-1",
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
  });

  it("streams assistant deltas incrementally instead of rendering all-at-once", async () => {
    let released = false;
    let releaseSecondChunk: () => void = () => {};
    const secondChunkGate = new Promise<void>((resolve) => {
      releaseSecondChunk = () => {
        released = true;
        resolve();
      };
    });

    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValueOnce({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"assistant.delta","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"assistant","payload":{"content":"Part A"},"diagnostics":[]}\n\n',
            'data: {"event":"assistant.delta","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:01Z","stage":"assistant","payload":{"content":" + Part B"},"diagnostics":[]}\n\n',
            'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":3,"ts":"2026-02-16T19:00:02Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
          ];
          let cursor = 0;
          return {
            read: async () => {
              if (cursor >= chunks.length) return { done: true, value: undefined };
              if (cursor === 1 && !released) {
                await secondChunkGate;
              }
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

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "stream this" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("Part A");
    releaseSecondChunk();

    await waitFor(() => {
      expect(screen.getByText("Part A + Part B")).toBeInTheDocument();
    });
  });

  it("treats post-run draft ensure lock conflicts as non-fatal", async () => {
    const sessionPayload = {
      session_id: "session-1",
      app_id: "app-1",
      revision_id: "rev-1",
      status: "running",
      has_active_coding_runs: false,
      active_coding_run_count: 0,
      preview_url: "https://preview.local/sandbox/session-1/",
      preview_auth_token: "preview-auth-token-1",
      preview_auth_expires_at: new Date(Date.now() + 7200_000).toISOString(),
      idle_timeout_seconds: 180,
      last_activity_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 180_000).toISOString(),
      last_error: null,
    };
    let ensureCalls = 0;
    (publishedAppsService.ensureDraftDevSession as jest.Mock).mockImplementation(() => {
      ensureCalls += 1;
      if (ensureCalls === 1) {
        return Promise.resolve(sessionPayload);
      }
      return Promise.reject(
        new Error(
          JSON.stringify({
            code: "CODING_AGENT_RUN_ACTIVE",
            message: "Builder edits are locked while a coding-agent run is active for this session.",
            active_run_id: "run-1",
          }),
        ),
      );
    });

    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValueOnce({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"run.accepted","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"run","payload":{"status":"queued"},"diagnostics":[]}\n\n',
            'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:01Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "ensure after terminal" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(publishedAppsService.streamCodingAgentRun).toHaveBeenCalledWith("app-1", "run-1");
    });
    await waitFor(() => {
      expect(publishedAppsService.ensureDraftDevSession).toHaveBeenCalledTimes(2);
    });
    expect(
      screen.queryByText("Builder edits are locked while a coding-agent run is active for this session."),
    ).not.toBeInTheDocument();
  });

  it("skips post-run preview ensure while another run is still active", async () => {
    const sessionPayload = {
      session_id: "session-1",
      app_id: "app-1",
      revision_id: "rev-1",
      status: "running",
      has_active_coding_runs: false,
      active_coding_run_count: 0,
      preview_url: "https://preview.local/sandbox/session-1/",
      preview_auth_token: "preview-auth-token-1",
      preview_auth_expires_at: new Date(Date.now() + 7200_000).toISOString(),
      idle_timeout_seconds: 180,
      last_activity_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 180_000).toISOString(),
      last_error: null,
    };
    const initialState = {
      ...makeState(),
      draft_dev: sessionPayload,
    };
    const activeScopeState = {
      ...makeState(),
      draft_dev: {
        ...sessionPayload,
        has_active_coding_runs: true,
        active_coding_run_count: 1,
      },
    };
    (publishedAppsService.getBuilderState as jest.Mock)
      .mockResolvedValueOnce(initialState)
      .mockResolvedValueOnce(activeScopeState)
      .mockResolvedValue(activeScopeState);
    (publishedAppsService.ensureDraftDevSession as jest.Mock).mockResolvedValue(sessionPayload);

    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValueOnce({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"run.accepted","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"run","payload":{"status":"queued"},"diagnostics":[]}\n\n',
            'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:01Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "parallel run state" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(publishedAppsService.streamCodingAgentRun).toHaveBeenCalledWith("app-1", "run-1");
    });
    const ensureCallsBeforeSend = (publishedAppsService.ensureDraftDevSession as jest.Mock).mock.calls.length;
    await waitFor(() => {
      expect(publishedAppsService.ensureDraftDevSession).toHaveBeenCalledTimes(ensureCallsBeforeSend);
    });
  });

  it("retries post-run hydration until run scope becomes idle", async () => {
    const sessionPayload = {
      session_id: "session-1",
      app_id: "app-1",
      revision_id: "rev-1",
      status: "running",
      has_active_coding_runs: false,
      active_coding_run_count: 0,
      preview_url: "https://preview.local/sandbox/session-1/",
      preview_auth_token: "preview-auth-token-1",
      preview_auth_expires_at: new Date(Date.now() + 7200_000).toISOString(),
      idle_timeout_seconds: 180,
      last_activity_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 180_000).toISOString(),
      last_error: null,
    };
    const initialState = {
      ...makeState(),
      draft_dev: sessionPayload,
    };
    const activeScopeState = {
      ...makeState(),
      draft_dev: {
        ...sessionPayload,
        has_active_coding_runs: true,
        active_coding_run_count: 1,
      },
    };
    const idleScopeState = {
      ...makeState({
        "index.html": "<!doctype html><html><body><div id='root'></div></body></html>",
        "src/main.tsx": "import './App';",
        "src/App.tsx": "export function App() { return <div>Updated by run</div>; }",
      }),
      app: {
        ...makeState().app,
        current_draft_revision_id: "rev-2",
      },
      current_draft_revision: {
        ...makeState().current_draft_revision,
        id: "rev-2",
        files: {
          "index.html": "<!doctype html><html><body><div id='root'></div></body></html>",
          "src/main.tsx": "import './App';",
          "src/App.tsx": "export function App() { return <div>Updated by run</div>; }",
        },
      },
      draft_dev: {
        ...sessionPayload,
        revision_id: "rev-2",
        has_active_coding_runs: false,
        active_coding_run_count: 0,
      },
    };
    (publishedAppsService.getBuilderState as jest.Mock)
      .mockResolvedValueOnce(initialState)
      .mockResolvedValueOnce(activeScopeState)
      .mockResolvedValueOnce(idleScopeState)
      .mockResolvedValue(idleScopeState);
    (publishedAppsService.ensureDraftDevSession as jest.Mock).mockResolvedValue(sessionPayload);

    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValueOnce({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"run.accepted","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"run","payload":{"status":"queued"},"diagnostics":[]}\n\n',
            'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:01Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "wait until idle then hydrate" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(publishedAppsService.streamCodingAgentRun).toHaveBeenCalledWith("app-1", "run-1");
    });

    const ensureCallsBeforeSend = (publishedAppsService.ensureDraftDevSession as jest.Mock).mock.calls.length;
    await waitFor(() => {
      expect(publishedAppsService.ensureDraftDevSession).toHaveBeenCalledTimes(ensureCallsBeforeSend + 1);
    });
  });

  it("reuses returned chat_session_id for subsequent messages", async () => {
    (publishedAppsService.createCodingAgentRun as jest.Mock)
      .mockResolvedValueOnce({
        run_id: "run-1",
        status: "queued",
        execution_engine: "opencode",
        chat_session_id: "chat-1",
        surface: "published_app_coding_agent",
        published_app_id: "app-1",
        base_revision_id: "rev-1",
        result_revision_id: null,
        checkpoint_revision_id: null,
        error: null,
        created_at: new Date().toISOString(),
        started_at: null,
        completed_at: null,
      })
      .mockResolvedValueOnce({
        run_id: "run-2",
        status: "queued",
        execution_engine: "opencode",
        chat_session_id: "chat-1",
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

    (publishedAppsService.streamCodingAgentRun as jest.Mock)
      .mockResolvedValueOnce({
        body: {
          getReader: () => {
            const chunks = [
              'data: {"event":"assistant.delta","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"assistant","payload":{"content":"First answer"},"diagnostics":[]}\n\n',
              'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:01Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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
      })
      .mockResolvedValueOnce({
        body: {
          getReader: () => {
            const chunks = [
              'data: {"event":"assistant.delta","run_id":"run-2","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:02Z","stage":"assistant","payload":{"content":"Second answer"},"diagnostics":[]}\n\n',
              'data: {"event":"run.completed","run_id":"run-2","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:03Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "hi" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("First answer");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "what is the first message?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Second answer");

    expect((publishedAppsService.createCodingAgentRun as jest.Mock).mock.calls).toHaveLength(2);
    const secondPayload = (publishedAppsService.createCodingAgentRun as jest.Mock).mock.calls[1][1];
    expect(secondPayload.chat_session_id).toBe("chat-1");
  });

  it("shows reasoning shimmer again for a second prompt before second stream activity arrives", async () => {
    let releaseSecondRunStart: () => void = () => undefined;
    const secondRunStartGate = new Promise<void>((resolve) => {
      releaseSecondRunStart = resolve;
    });

    (publishedAppsService.createCodingAgentRun as jest.Mock)
      .mockResolvedValueOnce({
        run_id: "run-1",
        status: "queued",
        execution_engine: "opencode",
        chat_session_id: "chat-1",
        surface: "published_app_coding_agent",
        published_app_id: "app-1",
        base_revision_id: "rev-1",
        result_revision_id: null,
        checkpoint_revision_id: null,
        error: null,
        created_at: new Date().toISOString(),
        started_at: null,
        completed_at: null,
      })
      .mockResolvedValueOnce({
        run_id: "run-2",
        status: "queued",
        execution_engine: "opencode",
        chat_session_id: "chat-1",
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

    (publishedAppsService.streamCodingAgentRun as jest.Mock)
      .mockResolvedValueOnce({
        body: {
          getReader: () => {
            const chunks = [
              'data: {"event":"assistant.delta","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"assistant","payload":{"content":"First answer"},"diagnostics":[]}\n\n',
              'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:01Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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
      })
      .mockResolvedValueOnce({
        body: {
          getReader: () => {
            const chunks = [
              'data: {"event":"tool.started","run_id":"run-2","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:02Z","stage":"tool","payload":{"tool":"read","span_id":"call-2","input":{"path":"src/main.tsx"}},"diagnostics":[]}\n\n',
              'data: {"event":"run.completed","run_id":"run-2","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:03Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
            ];
            let cursor = 0;
            return {
              read: async () => {
                if (cursor === 0) {
                  await secondRunStartGate;
                }
                if (cursor >= chunks.length) return { done: true, value: undefined };
                const next = chunks[cursor++];
                return { done: false, value: new Uint8Array(Buffer.from(next, "utf-8")) };
              },
              cancel: async () => undefined,
            };
          },
        },
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "text/event-stream" }),
      });

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "first prompt" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("First answer");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "second prompt" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getByText("Reasoning...")).toBeInTheDocument();
    });

    releaseSecondRunStart();
    await screen.findByRole("button", { name: "Exploring 1 file" });
    await waitFor(() => {
      expect(screen.queryByText("Reasoning...")).not.toBeInTheDocument();
    });
  });

  it("does not inject fallback assistant text when stream emits no assistant delta", async () => {
    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValueOnce({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"run.accepted","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"run","payload":{"status":"queued"},"diagnostics":[]}\n\n',
            'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:01Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "hi" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.queryByText(/Run accepted/i)).not.toBeInTheDocument();
    });
    expect(
      screen.queryByText("I can help with code changes in this app workspace. Tell me what you want to change."),
    ).not.toBeInTheDocument();
  });

  it("does not append default assistant text after tool calls when assistant already responded", async () => {
    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValueOnce({
      body: {
        getReader: () => {
          const chunks = [
            'data: {"event":"assistant.delta","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"assistant","payload":{"content":"Implemented the update."},"diagnostics":[]}\n\n',
            'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:01Z","stage":"tool","payload":{"tool":"read","span_id":"call-1","input":{"path":"src/main.tsx"}},"diagnostics":[]}\n\n',
            'data: {"event":"tool.completed","run_id":"run-1","app_id":"app-1","seq":3,"ts":"2026-02-16T19:00:02Z","stage":"tool","payload":{"tool":"read","span_id":"call-1","output":{"path":"src/main.tsx"}},"diagnostics":[]}\n\n',
            'data: {"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":4,"ts":"2026-02-16T19:00:03Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "apply update" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getByText("Implemented the update.")).toBeInTheDocument();
    });
    expect(
      screen.queryByText("I can help with code changes in this app workspace. Tell me what you want to change."),
    ).not.toBeInTheDocument();
  });

  it("does not show generic fallback text after non-terminal disconnect with tool activity", async () => {
    (publishedAppsService.getCodingAgentRun as jest.Mock).mockResolvedValue({
      run_id: "run-1",
      status: "completed",
      execution_engine: "opencode",
      chat_session_id: "chat-1",
      surface: "published_app_coding_agent",
      published_app_id: "app-1",
      base_revision_id: "rev-1",
      result_revision_id: "rev-2",
      checkpoint_revision_id: null,
      error: null,
      created_at: new Date().toISOString(),
      started_at: new Date().toISOString(),
      completed_at: new Date().toISOString(),
    });
    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValueOnce(
      makeStreamResponse([
        'data: {"event":"tool.started","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-25T19:00:00Z","stage":"tool","payload":{"tool":"read","span_id":"call-1","input":{"path":"src/main.tsx"}},"diagnostics":[]}\n\n',
      ]),
    );

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "tool only progress" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByRole("button", { name: "Exploring 1 file" });
    await waitFor(() => {
      expect(
        screen.queryByText("I can help with code changes in this app workspace. Tell me what you want to change."),
      ).not.toBeInTheDocument();
    });
  });

  it("parses SSE events when data prefix has no trailing space", async () => {
    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValueOnce({
      body: {
        getReader: () => {
          const chunks = [
            'data:{"event":"assistant.delta","run_id":"run-1","app_id":"app-1","seq":1,"ts":"2026-02-16T19:00:00Z","stage":"assistant","payload":{"content":"Applied red color update"},"diagnostics":[]}\n\n',
            'data:{"event":"run.completed","run_id":"run-1","app_id":"app-1","seq":2,"ts":"2026-02-16T19:00:01Z","stage":"run","payload":{"status":"completed"},"diagnostics":[]}\n\n',
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

    render(<AppsBuilderWorkspace appId="app-1" />);
    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "set red" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getByText("Applied red color update")).toBeInTheDocument();
    });
  });

  it("does not enter full-page loading state while refreshing state after a run", async () => {
    const getBuilderStateMock = publishedAppsService.getBuilderState as jest.Mock;
    getBuilderStateMock.mockReset();
    getBuilderStateMock.mockResolvedValueOnce(makeState());

    let resolveRefresh!: (value: unknown) => void;
    const refreshPromise = new Promise((resolve) => {
      resolveRefresh = resolve;
    });
    getBuilderStateMock.mockReturnValueOnce(refreshPromise);

    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalledTimes(1));
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "update spacing" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(publishedAppsService.streamCodingAgentRun).toHaveBeenCalledWith("app-1", "run-1");
    });
    expect(screen.queryByText("Loading builder...")).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText("Plan, @ for context, / for commands")).toBeInTheDocument();

    resolveRefresh(makeState());
    await waitFor(() => {
      expect(publishedAppsService.getBuilderState).toHaveBeenCalledTimes(2);
    });
  });

  it("renders model selector with Auto and chat model options", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    expect(screen.queryByLabelText("Select run engine")).not.toBeInTheDocument();
    const selectorTrigger = await screen.findByRole("button", { name: "Select run model" });
    expect(selectorTrigger).toHaveTextContent("Auto");

    fireEvent.click(selectorTrigger);
    await waitFor(() => {
      expect(screen.getByText("Big Pickle")).toBeInTheDocument();
      expect(screen.getByText("MiniMax M2.5 Free")).toBeInTheDocument();
    });
  });

  it("loads chat sessions from API, hydrates timeline, and resumes with the same chat_session_id", async () => {
    const now = new Date().toISOString();
    (publishedAppsService.listCodingAgentChatSessions as jest.Mock).mockResolvedValue([
      {
        id: "chat-1",
        title: "Past thread",
        created_at: now,
        updated_at: now,
        last_message_at: now,
      },
    ]);
    (publishedAppsService.getCodingAgentChatSession as jest.Mock).mockResolvedValueOnce({
      session: {
        id: "chat-1",
        title: "Past thread",
        created_at: now,
        updated_at: now,
        last_message_at: now,
      },
      messages: [
        { id: "m1", run_id: "run-a", role: "user", content: "Earlier prompt", created_at: now },
        { id: "m2", run_id: "run-a", role: "assistant", content: "Earlier answer", created_at: now },
      ],
    });
    (publishedAppsService.listCodingAgentChatSessionQueue as jest.Mock).mockResolvedValueOnce([]);
    (publishedAppsService.findCodingAgentChatSessionActiveRun as jest.Mock).mockResolvedValueOnce(null);
    (publishedAppsService.createCodingAgentRun as jest.Mock).mockResolvedValueOnce({
      run_id: "run-1",
      status: "queued",
      execution_engine: "opencode",
      chat_session_id: "chat-1",
      surface: "published_app_coding_agent",
      published_app_id: "app-1",
      base_revision_id: "rev-1",
      result_revision_id: null,
      checkpoint_revision_id: null,
      error: null,
      created_at: now,
      started_at: null,
      completed_at: null,
    });

    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalledWith("app-1"));
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");
    await waitFor(() =>
      expect(publishedAppsService.listCodingAgentChatSessions).toHaveBeenCalledWith("app-1", 50),
    );

    fireEvent.click(screen.getByRole("button", { name: "Chat history" }));
    const historyEntry = await screen.findByText("Past thread");
    const historyEntryButton = historyEntry.closest("button");
    expect(historyEntryButton).not.toBeNull();
    fireEvent.click(historyEntryButton!);

    await waitFor(() =>
      expect(publishedAppsService.getCodingAgentChatSession).toHaveBeenCalledWith(
        "app-1",
        "chat-1",
        expect.objectContaining({ limit: 10 }),
      ),
    );

    expect(await screen.findByText("Earlier prompt")).toBeInTheDocument();
    expect(await screen.findByText("Earlier answer")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "continue this thread" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(publishedAppsService.createCodingAgentRun).toHaveBeenCalledWith(
        "app-1",
        expect.objectContaining({ chat_session_id: "chat-1" }),
      );
    });
  });

  it("sends env-resolved engine in create-run payload", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "use opencode" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(publishedAppsService.createCodingAgentRun).toHaveBeenCalledTimes(1));
    expect((publishedAppsService.createCodingAgentRun as jest.Mock).mock.calls[0][1]).toEqual(
      expect.objectContaining({ engine: "opencode" }),
    );
  });

  it("sends selected model_id and supports changing model between messages", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.click(screen.getByRole("button", { name: "Select run model" }));
    fireEvent.click(await screen.findByText("MiniMax M2.5 Free"));

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "first request" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(publishedAppsService.createCodingAgentRun).toHaveBeenCalledTimes(1));
    expect((publishedAppsService.createCodingAgentRun as jest.Mock).mock.calls[0][1]).toEqual(
      expect.objectContaining({ model_id: "opencode/minimax-m2.5-free", engine: "opencode" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Select run model" }));
    const autoOptions = await screen.findAllByText("Auto");
    fireEvent.click(autoOptions[autoOptions.length - 1]);

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "second request" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(publishedAppsService.createCodingAgentRun).toHaveBeenCalledTimes(2));
    expect((publishedAppsService.createCodingAgentRun as jest.Mock).mock.calls[1][1]).toEqual(
      expect.objectContaining({ model_id: "opencode/big-pickle", engine: "opencode" }),
    );
  });

  it("shows actionable error when selected model is unavailable", async () => {
    (publishedAppsService.createCodingAgentRun as jest.Mock).mockRejectedValueOnce(
      new Error(
        JSON.stringify({
          code: "CODING_AGENT_MODEL_UNAVAILABLE",
          field: "model_id",
          message: "Selected model is unavailable for this tenant.",
        }),
      ),
    );

    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.click(screen.getByRole("button", { name: "Select run model" }));
    fireEvent.click(await screen.findByText("Big Pickle"));

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "use selected model" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getByText("Selected model is unavailable for this tenant.")).toBeInTheDocument();
    });
  });

  it("shows actionable error when selected engine is unavailable", async () => {
    (publishedAppsService.createCodingAgentRun as jest.Mock).mockRejectedValueOnce(
      new Error(
        JSON.stringify({
          code: "CODING_AGENT_ENGINE_UNAVAILABLE",
          field: "engine",
          message: "OpenCode engine is unavailable.",
        }),
      ),
    );

    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");

    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "use opencode engine" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getByText("OpenCode engine is unavailable.")).toBeInTheDocument();
    });
  });

  it("restores a checkpoint from per-message revert action", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByPlaceholderText("Plan, @ for context, / for commands");
    fireEvent.change(screen.getByPlaceholderText("Plan, @ for context, / for commands"), {
      target: { value: "make a change" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(publishedAppsService.streamCodingAgentRun).toHaveBeenCalledWith("app-1", "run-1"));
    fireEvent.click(await screen.findByLabelText("Revert to this point"));

    await waitFor(() => {
      expect(publishedAppsService.restoreCodingAgentCheckpoint).toHaveBeenCalledWith(
        "app-1",
        "rev-2",
        {},
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
        "http://127.0.0.1:8000/api/py/public/apps/preview/revisions/rev-3/assets/index.html",
        "_blank",
        "noopener,noreferrer",
      );
    });
  });

});
