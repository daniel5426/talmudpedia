import { render, waitFor } from "@testing-library/react";

import PublishedAppPage from "@/app/published/[appSlug]/page";
import { publishedRuntimeService } from "@/services";

const replaceMock = jest.fn();

jest.mock("next/navigation", () => ({
  useParams: () => ({ appSlug: "support-app" }),
  useRouter: () => ({ replace: replaceMock }),
}));

jest.mock("@/lib/react-artifacts/compiler", () => ({
  compileReactArtifactProject: jest.fn(async () => ({ ok: true, output: "console.log('ok')" })),
}));

jest.mock("@/services", () => ({
  publishedRuntimeService: {
    getConfig: jest.fn(),
    getMe: jest.fn(),
    listChats: jest.fn(),
  },
}));

describe("Published runtime auth gate", () => {
  beforeEach(() => {
    replaceMock.mockReset();
    window.localStorage.clear();
    (publishedRuntimeService.getConfig as jest.Mock).mockResolvedValue({
      id: "app-1",
      tenant_id: "tenant-1",
      agent_id: "agent-1",
      name: "Support App",
      slug: "support-app",
      status: "published",
      auth_enabled: true,
      auth_providers: ["password"],
      published_url: "https://support-app.apps.localhost",
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("redirects to login when auth is enabled and no app token is present", async () => {
    render(<PublishedAppPage />);

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/published/support-app/login");
    });
  });
});
