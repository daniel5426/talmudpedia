import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import AppsPage from "@/app/admin/apps/page";
import { agentService, publishedAppsService } from "@/services";

const pushMock = jest.fn();

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

jest.mock("@/services", () => ({
  agentService: {
    listAgents: jest.fn(),
  },
  publishedAppsService: {
    list: jest.fn(),
    listStats: jest.fn(),
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
    (publishedAppsService.listStats as jest.Mock).mockResolvedValue({
      start_date: "2026-03-15",
      end_date: "2026-03-22",
      items: [
        {
          app_id: "app-1",
          start_date: "2026-03-15",
          end_date: "2026-03-22",
          approximate: false,
          visits: 120,
          unique_visitors: 45,
          agent_runs: 30,
          failed_runs: 2,
          tokens: 5400,
          threads: 10,
          app_accounts: 8,
          active_sessions: 3,
          visits_by_day: [
            { date: "2026-03-15", value: 10 },
            { date: "2026-03-16", value: 20 },
            { date: "2026-03-17", value: 15 },
          ],
          runs_by_day: [
            { date: "2026-03-15", value: 5 },
            { date: "2026-03-16", value: 8 },
            { date: "2026-03-17", value: 4 },
          ],
          tokens_by_day: [
            { date: "2026-03-15", value: 1000 },
            { date: "2026-03-16", value: 2000 },
            { date: "2026-03-17", value: 1500 },
          ],
          visit_surface_breakdown: {},
          visit_auth_state_breakdown: {},
        },
      ],
    });
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

  it("renders the apps list before create resources finish loading", async () => {
    const agentsDeferred = deferred<{ agents: Array<Record<string, unknown>>; total: number }>();
    const templatesDeferred = deferred<
      Array<{
        key: string;
        name: string;
        description: string;
        thumbnail: string;
        tags: string[];
        entry_file: string;
        style_tokens: Record<string, string>;
      }>
    >();
    const authTemplatesDeferred = deferred<
      Array<{
        key: string;
        name: string;
        description: string;
        thumbnail: string;
        tags: string[];
        style_tokens: Record<string, string>;
      }>
    >();

    (agentService.listAgents as jest.Mock).mockReturnValueOnce(agentsDeferred.promise);
    (publishedAppsService.listTemplates as jest.Mock).mockReturnValueOnce(templatesDeferred.promise);
    (publishedAppsService.listAuthTemplates as jest.Mock).mockReturnValueOnce(authTemplatesDeferred.promise);

    render(<AppsPage />);

    expect(await screen.findByText("Support")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /add new/i }));
    expect(screen.getByText("Loading published agents...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create App" })).toBeDisabled();

    agentsDeferred.resolve({
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
    templatesDeferred.resolve([
      {
        key: "chat-classic",
        name: "Classic Dialogue",
        description: "Classic",
        thumbnail: "classic",
        tags: ["chat"],
        entry_file: "src/main.tsx",
        style_tokens: {},
      },
    ]);
    authTemplatesDeferred.resolve([
      {
        key: "auth-classic",
        name: "Classic Auth",
        description: "Classic auth layout",
        thumbnail: "classic",
        tags: ["default"],
        style_tokens: {},
      },
    ]);

    await waitFor(() => {
      expect(screen.queryByText("Loading published agents...")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Classic Dialogue")).toBeInTheDocument();
  });

  it("fetches and displays inline stats for apps", async () => {
    render(<AppsPage />);

    await waitFor(() => expect(publishedAppsService.listStats).toHaveBeenCalledWith({ days: 7 }));
    expect(await screen.findByText("Support")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("visits")).toBeInTheDocument();
      expect(screen.getByText("runs")).toBeInTheDocument();
      expect(screen.getByText("tok")).toBeInTheDocument();
    });
  });

  it("shows app list while stats are still loading", async () => {
    const statsDeferred = deferred<{
      start_date: string;
      end_date: string;
      items: Array<Record<string, unknown>>;
    }>();
    (publishedAppsService.listStats as jest.Mock).mockReturnValueOnce(statsDeferred.promise);

    render(<AppsPage />);

    expect(await screen.findByText("Support")).toBeInTheDocument();

    statsDeferred.resolve({
      start_date: "2026-03-15",
      end_date: "2026-03-22",
      items: [],
    });

    await waitFor(() => {
      expect(screen.getByText("no stats yet")).toBeInTheDocument();
    });
  });

  it("degrades cleanly when stats fail to load", async () => {
    (publishedAppsService.listStats as jest.Mock).mockRejectedValueOnce(new Error("Network error"));

    render(<AppsPage />);

    expect(await screen.findByText("Support")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("no stats yet")).toBeInTheDocument();
    });
  });

  it("changes stats period when date range buttons are clicked", async () => {
    render(<AppsPage />);

    await waitFor(() => expect(publishedAppsService.listStats).toHaveBeenCalledWith({ days: 7 }));
    expect(await screen.findByText("Support")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "30d" }));

    await waitFor(() => {
      expect(publishedAppsService.listStats).toHaveBeenCalledWith({ days: 30 });
    });
  });
});
