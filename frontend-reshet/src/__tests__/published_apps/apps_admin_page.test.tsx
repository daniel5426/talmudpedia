import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import AppsPage from "@/app/admin/apps/page";
import { agentService, publishedAppsService } from "@/services";

const pushMock = jest.fn();

jest.mock("@/services", () => ({
  agentService: {
    listAgents: jest.fn(),
  },
  publishedAppsService: {
    list: jest.fn(),
    listTemplates: jest.fn(),
    listAuthTemplates: jest.fn(),
    create: jest.fn(),
    remove: jest.fn(),
  },
}));

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

jest.mock("@/components/direction-provider", () => ({
  useDirection: () => ({ direction: "ltr" }),
}));

jest.mock("next/link", () => {
  return ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>;
});

describe("Apps admin page", () => {
  beforeEach(() => {
    (publishedAppsService.list as jest.Mock).mockResolvedValue([
      {
        id: "app-1",
        tenant_id: "tenant-1",
        agent_id: "agent-1",
        name: "Support",
        slug: "support",
        status: "draft",
        visibility: "public",
        auth_enabled: true,
        auth_providers: ["password"],
        auth_template_key: "auth-classic",
        template_key: "chat-classic",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]);
    (agentService.listAgents as jest.Mock).mockResolvedValue({
      agents: [
        {
          id: "agent-1",
          tenant_id: "tenant-1",
          name: "Published Agent",
          slug: "published-agent",
          status: "published",
          version: 1,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      total: 1,
    });
    (publishedAppsService.listTemplates as jest.Mock).mockResolvedValue([
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
        key: "fresh-start",
        name: "Fresh Start",
        description: "Minimal starter",
        thumbnail: "fresh",
        tags: ["minimal"],
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
    ]);
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
    (publishedAppsService.create as jest.Mock).mockResolvedValue({
      id: "app-new",
      tenant_id: "tenant-1",
      agent_id: "agent-1",
      name: "New App",
      slug: "new-app",
      status: "draft",
      visibility: "public",
      template_key: "chat-neon",
      auth_template_key: "auth-classic",
      auth_enabled: true,
      auth_providers: ["password"],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("renders apps list and creates a new app", async () => {
    render(<AppsPage />);

    await waitFor(() => expect(publishedAppsService.list).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByText("Loading apps...")).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /add new/i }));
    fireEvent.change(screen.getByLabelText("App Name"), { target: { value: "New App" } });
    fireEvent.click(screen.getByRole("button", { name: /neon console/i }));
    fireEvent.click(screen.getByRole("button", { name: "Create App" }));

    await waitFor(() => {
      expect(publishedAppsService.create).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "New App",
          template_key: "chat-neon",
          auth_template_key: "auth-classic",
          agent_id: "agent-1",
        })
      );
    });
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/apps/app-new"));
  });

  it("supports selecting fresh-start template on create", async () => {
    render(<AppsPage />);

    await waitFor(() => expect(publishedAppsService.list).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: /add new/i }));
    fireEvent.change(screen.getByLabelText("App Name"), { target: { value: "Fresh App" } });
    fireEvent.click(screen.getByRole("button", { name: /fresh start/i }));
    fireEvent.click(screen.getByRole("button", { name: "Create App" }));

    await waitFor(() => {
      expect(publishedAppsService.create).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Fresh App",
          template_key: "fresh-start",
          auth_template_key: "auth-classic",
          agent_id: "agent-1",
        })
      );
    });
  });
});
