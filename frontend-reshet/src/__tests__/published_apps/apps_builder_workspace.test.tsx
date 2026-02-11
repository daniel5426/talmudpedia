import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder } from "util";

import { AppsBuilderWorkspace } from "@/features/apps-builder/workspace/AppsBuilderWorkspace";
import { publishedAppsService, publishedRuntimeService } from "@/services";

const setOpenMock = jest.fn();

// eslint-disable-next-line @typescript-eslint/no-explicit-any
(global as any).TextDecoder = TextDecoder;

jest.mock("@/services", () => ({
  publishedAppsService: {
    getBuilderState: jest.fn(),
    getRevisionBuildStatus: jest.fn(),
    createRevision: jest.fn(),
    publish: jest.fn(),
    resetTemplate: jest.fn(),
    streamBuilderChat: jest.fn(),
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
  CodeEditor: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => (
    <textarea aria-label="Code Editor" value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}));

const makeState = () => ({
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
    files: {
      "src/main.tsx": "import './App';",
      "src/App.tsx": "export function App() { return <div>Hello</div>; }",
    },
    created_at: new Date().toISOString(),
  },
  current_published_revision: null,
  preview_token: "preview-token",
});

describe("AppsBuilderWorkspace", () => {
  beforeEach(() => {
    (publishedAppsService.getBuilderState as jest.Mock).mockResolvedValue(makeState());
    (publishedAppsService.getRevisionBuildStatus as jest.Mock).mockResolvedValue({
      revision_id: "rev-1",
      build_status: "succeeded",
      build_seq: 1,
      build_error: null,
      template_runtime: "vite_static",
    });
    (publishedRuntimeService.getPreviewRuntime as jest.Mock).mockResolvedValue({
      app_id: "app-1",
      slug: "builder-app",
      revision_id: "rev-1",
      runtime_mode: "vite_static",
      preview_url: "https://preview.local/rev-1/",
      asset_base_url: "https://preview.local/rev-1/",
      api_base_path: "/api/py",
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
      },
      source_revision_id: "rev-1",
      created_at: new Date().toISOString(),
    });
    (publishedAppsService.publish as jest.Mock).mockResolvedValue({
      ...makeState().app,
      status: "published",
      current_published_revision_id: "rev-3",
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
            'data: {"event":"patch_ops","stage":"patch_ready","request_id":"req-1","data":{"base_revision_id":"rev-1","summary":"applied update","operations":[{"op":"upsert_file","path":"src/App.tsx","content":"export function App() { return <div>From Patch</div>; }"}]}}\n\n',
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

  it("switches template with destructive confirmation", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());
    await screen.findByRole("combobox");

    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByText("Neon Console"));

    await waitFor(() => {
      expect(window.confirm).toHaveBeenCalled();
      expect(publishedAppsService.resetTemplate).toHaveBeenCalledWith("app-1", "chat-neon");
    });
  });

  it("applies chat patch operations and persists a new revision", async () => {
    render(<AppsBuilderWorkspace appId="app-1" />);

    await waitFor(() => expect(publishedAppsService.getBuilderState).toHaveBeenCalled());

    fireEvent.change(screen.getByPlaceholderText("Make the header more bold..."), {
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
      expect(publishedAppsService.createRevision).toHaveBeenCalledWith(
        "app-1",
        expect.objectContaining({
          base_revision_id: "rev-1",
          operations: [
            expect.objectContaining({ op: "upsert_file", path: "src/App.tsx" }),
          ],
        }),
      );
    });
  });
});
