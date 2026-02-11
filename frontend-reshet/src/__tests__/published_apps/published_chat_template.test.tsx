import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder } from "util";

import PublishedAppPage from "@/app/published/[appSlug]/page";
import { publishedRuntimeService } from "@/services";

// JSDOM in this setup does not provide TextDecoder by default.
// The runtime page relies on it to parse SSE chunks.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
(global as any).TextDecoder = TextDecoder;

jest.mock("next/navigation", () => ({
  useParams: () => ({ appSlug: "support-app" }),
  useRouter: () => ({ replace: jest.fn() }),
}));

jest.mock("next/link", () => {
  return ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>;
});

jest.mock("@/lib/react-artifacts/compiler", () => ({
  compileReactArtifactProject: jest.fn(async () => ({ ok: true, output: "console.log('ok')" })),
}));

jest.mock("@/services", () => ({
  publishedRuntimeService: {
    getConfig: jest.fn(),
    streamChat: jest.fn(),
  },
}));

describe("Published chat template", () => {
  beforeEach(() => {
    window.localStorage.clear();
    (publishedRuntimeService.getConfig as jest.Mock).mockResolvedValue({
      id: "app-1",
      tenant_id: "tenant-1",
      agent_id: "agent-1",
      name: "Support App",
      slug: "support-app",
      status: "published",
      auth_enabled: false,
      auth_providers: ["password"],
      published_url: "https://support-app.apps.localhost",
    });

    (publishedRuntimeService.streamChat as jest.Mock).mockImplementation(async () => {
      const chunks = [
        'data: {"event":"token","data":{"content":"Hello"}}\n\n',
        'data: {"type":"done"}\n\n',
      ];
      let cursor = 0;

      return {
        headers: {
          get: () => null,
        },
        body: {
          getReader: () => ({
            read: async () => {
              if (cursor >= chunks.length) {
                return { done: true, value: undefined };
              }
              const next = chunks[cursor++];
              return { done: false, value: new Uint8Array(Buffer.from(next, "utf-8")) };
            },
          }),
        },
      } as unknown as Response;
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("streams assistant response in constant template", async () => {
    render(<PublishedAppPage />);

    await waitFor(() => expect(publishedRuntimeService.getConfig).toHaveBeenCalled());
    await screen.findByPlaceholderText("Send a message...");

    fireEvent.change(screen.getByPlaceholderText("Send a message..."), {
      target: { value: "Hi" },
    });

    const buttons = screen.getAllByRole("button");
    fireEvent.click(buttons[buttons.length - 1]);

    await waitFor(() => {
      expect(publishedRuntimeService.streamChat).toHaveBeenCalledWith(
        "support-app",
        expect.objectContaining({ input: "Hi" }),
        undefined,
      );
    });

    await waitFor(() => expect(screen.getByText("Hello")).toBeInTheDocument());
  });
});
