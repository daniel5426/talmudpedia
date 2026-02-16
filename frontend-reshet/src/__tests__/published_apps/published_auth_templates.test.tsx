import { render, screen, waitFor } from "@testing-library/react";

import PublishedAppLoginPage from "@/app/published/[appSlug]/login/page";
import PublishedAppSignupPage from "@/app/published/[appSlug]/signup/page";
import { publishedRuntimeService } from "@/services";

const replaceMock = jest.fn();

jest.mock("next/navigation", () => ({
  useParams: () => ({ appSlug: "support-app" }),
  useRouter: () => ({ replace: replaceMock }),
}));

jest.mock("@/services", () => ({
  publishedRuntimeService: {
    getConfig: jest.fn(),
    getMe: jest.fn(),
    login: jest.fn(),
    signup: jest.fn(),
    getGoogleStartUrl: jest.fn(() => "https://accounts.google.com"),
  },
}));

describe("Published auth template rendering", () => {
  beforeEach(() => {
    replaceMock.mockReset();
    window.localStorage.clear();
    (publishedRuntimeService.getMe as jest.Mock).mockRejectedValue(new Error("no token"));
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("renders login page with split auth template branding", async () => {
    (publishedRuntimeService.getConfig as jest.Mock).mockResolvedValueOnce({
      id: "app-1",
      tenant_id: "tenant-1",
      agent_id: "agent-1",
      name: "Support App",
      description: "Custom login description",
      logo_url: "https://cdn.example.com/logo.png",
      slug: "support-app",
      status: "published",
      visibility: "public",
      auth_enabled: true,
      auth_providers: ["password", "google"],
      auth_template_key: "auth-split",
      published_url: "https://support-app.apps.localhost",
    });

    render(<PublishedAppLoginPage />);

    await waitFor(() => expect(publishedRuntimeService.getConfig).toHaveBeenCalledWith("support-app"));
    expect(await screen.findByText("Support App")).toBeInTheDocument();
    expect(screen.getAllByText("Custom login description").length).toBeGreaterThan(0);
    expect(screen.getAllByAltText("Support App logo").length).toBeGreaterThan(0);
  });

  it("renders signup page with minimal auth template content", async () => {
    (publishedRuntimeService.getConfig as jest.Mock).mockResolvedValueOnce({
      id: "app-1",
      tenant_id: "tenant-1",
      agent_id: "agent-1",
      name: "Support App",
      description: "Custom signup description",
      logo_url: "https://cdn.example.com/logo.png",
      slug: "support-app",
      status: "published",
      visibility: "public",
      auth_enabled: true,
      auth_providers: ["password"],
      auth_template_key: "auth-minimal",
      published_url: "https://support-app.apps.localhost",
    });

    render(<PublishedAppSignupPage />);

    await waitFor(() => expect(publishedRuntimeService.getConfig).toHaveBeenCalledWith("support-app"));
    expect(screen.getAllByText("Create Account").length).toBeGreaterThan(0);
    expect(screen.getByText("Custom signup description")).toBeInTheDocument();
    expect(screen.getByAltText("Support App logo")).toBeInTheDocument();
  });
});
