import { render, waitFor } from "@testing-library/react";

import PublishedAppAuthCallbackPage from "@/app/published/[appSlug]/auth/callback/page";

const replaceMock = jest.fn();

jest.mock("next/navigation", () => ({
  useParams: () => ({ appSlug: "support-app" }),
  useRouter: () => ({ replace: replaceMock }),
  useSearchParams: () => ({
    get: (key: string) => {
      if (key === "token") return "published-token";
      if (key === "appSlug") return "support-app";
      return null;
    },
  }),
}));

describe("Published auth callback flow", () => {
  beforeEach(() => {
    replaceMock.mockReset();
    window.localStorage.clear();
  });

  it("stores app token and redirects to app runtime", async () => {
    render(<PublishedAppAuthCallbackPage />);

    await waitFor(() => {
      expect(window.localStorage.getItem("published-app-auth-token:support-app")).toBe("published-token");
      expect(replaceMock).toHaveBeenCalledWith("/published/support-app");
    });
  });
});
