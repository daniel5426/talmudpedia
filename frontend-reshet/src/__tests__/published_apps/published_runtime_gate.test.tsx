import { render, waitFor } from "@testing-library/react";

import PublishedAppPage from "@/app/published/[appSlug]/page";
import { publishedRuntimeService } from "@/services";

jest.mock("next/navigation", () => ({
  useParams: () => ({ appSlug: "support-app" }),
  useRouter: () => ({ replace: jest.fn() }),
}));

jest.mock("@/services", () => ({
  publishedRuntimeService: {
    getRuntime: jest.fn(),
  },
}));

describe("Published runtime redirect", () => {
  beforeEach(() => {
    (publishedRuntimeService.getRuntime as jest.Mock).mockResolvedValue({
      app_id: "app-1",
      slug: "support-app",
      revision_id: "rev-1",
      runtime_mode: "vite_static",
      published_url: null,
      asset_base_url: "https://support-app.apps.localhost",
      api_base_path: "/api/py",
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("shows error when runtime descriptor has no published url", async () => {
    render(<PublishedAppPage />);

    await waitFor(() => {
      expect(publishedRuntimeService.getRuntime).toHaveBeenCalledWith("support-app");
    });

    await waitFor(() => {
      expect(document.body.textContent).toContain("Published runtime URL is unavailable");
    });
  });
});
