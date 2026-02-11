import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import AppsPage from "@/app/admin/apps/page";
import { agentService, publishedAppsService } from "@/services";

jest.mock("@/services", () => ({
  agentService: {
    listAgents: jest.fn(),
  },
  publishedAppsService: {
    list: jest.fn(),
    create: jest.fn(),
    remove: jest.fn(),
  },
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
        auth_enabled: true,
        auth_providers: ["password"],
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
    (publishedAppsService.create as jest.Mock).mockResolvedValue({
      id: "app-new",
      tenant_id: "tenant-1",
      agent_id: "agent-1",
      name: "New App",
      slug: "new-app",
      status: "draft",
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

    fireEvent.change(screen.getByLabelText("App Name"), { target: { value: "New App" } });
    fireEvent.change(screen.getByLabelText("Slug"), { target: { value: "new-app" } });
    fireEvent.click(screen.getByRole("button", { name: "Create App" }));

    await waitFor(() => {
      expect(publishedAppsService.create).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "New App",
          slug: "new-app",
          agent_id: "agent-1",
        })
      );
    });
  });
});
